#!/usr/bin/env python3
"""Harvest project-memory output from a host. Runs ON the host, stdlib only.

    ssh HOST python3 - --dry-run [--exclude=a,b] [--bundle=c,d] < extract.py   # report what would be pulled
    ssh HOST python3 - [--exclude=a,b] [--bundle=c,d] < extract.py | tar xzm -C DEST
    --exclude: folders that are not skill output (third-party, stubs, data); --bundle: git repos to ship whole
    (history needed by replay.py)
    python3 extract.py --selftest

Raw transcripts never leave the host: only per-session digests are emitted.
"""
import collections, fnmatch, glob, io, json, os, re, subprocess, sys, tarfile, time

HOME = os.path.expanduser("~")
EXCLUDE, BUNDLE = set(), set()  # set from --exclude / --bundle
ROOT_DOCS = {"README.md", "AGENTS.md", "CLAUDE.md", "CHANGELOG.md"}
MEM_NAME = r"(?:AGENTS|CLAUDE|README|CHANGELOG|STATUS|DECISIONS|ARCHITECTURE|TREE|INCIDENTS|RUNBOOK)\.md"
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".css", ".scss", ".html", ".sh", ".bash",
            ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".xml", ".sql", ".md", ".go", ".rs", ".php", ".rb",
            ".java", ".cs", ".service", ".timer", ".csv_template"}
CODE_NAMES = {"Dockerfile", "Makefile", "Caddyfile", "package.json", "tsconfig.json", "jsconfig.json", "requirements.txt",
              "Procfile", "crontab"}
DENY = [".env", ".env.*", "*.env", "*.key", "*.pem", "*.p12", "*.pfx", "*.crt", "id_rsa*", "id_ed25519*", "tctoken*",
        "*session*", "*cred*", "*secret*", "*token*", "auth_info*", "*.sqlite*", "*.db", "*.orig.bak"]
PRUNE = {".git", "data", "logs", "log", "venv", ".venv", "env", "node_modules", "__pycache__", "target", "dist",
         "build", ".cache", ".pytest_cache", ".mypy_cache", "backups", "backup", "exports", "graphify-out"}
DENY_DIR = ["auth", "auth.*", "auth_*", "*baileys*"]
MAX_CODE, MAX_DOC, MAX_TXT = 200_000, 2_000_000, 4000

# ---------- scrubbing ----------
SCRUB = [
    ("privkey", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<REDACTED:privkey>"),
    ("url_cred", re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"), "<REDACTED:cred>"),
    ("jwt", re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}"), "<REDACTED:jwt>"),
    ("apikey", re.compile(r"\b(?:sk-(?:ant-)?[\w-]{20,}|ghp_\w{30,}|github_pat_\w{20,}|gho_\w{30,}|xox[abprs]-[\w-]{10,}"
                          r"|AKIA[0-9A-Z]{16}|AIza[\w-]{35}|glpat-[\w-]{20,})"), "<REDACTED:apikey>"),
    ("telegram", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"), "<REDACTED:tgtoken>"),
    ("bearer", re.compile(r"(?i)\bbearer\s+[\w.~+/=-]{20,}"), "Bearer <REDACTED>"),
    ("assign_quoted", re.compile(r"(?i)(\b\w*(?:key|token|secret|passw(?:or)?d|pwd|apikey)\w*[\"']?\s*[:=]\s*)([\"'])[^\"'\s]{6,}\2"),
     r"\1\2<REDACTED>\2"),
    ("assign_env", re.compile(r"(?im)^(\s*(?:export\s+)?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD)[A-Z0-9_]*=)(?![\"']?<REDACTED)\S{4,}"),
     r"\1<REDACTED>"),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){3,7}(?: ?[A-Z0-9]{1,3})?\b"), "<REDACTED:iban>"),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-z]{2,}\b", re.I), "<email>"),
    ("phone", re.compile(r"(?<![\w+])(?:\+\d{2}[ .-]?\d{2,4}[ .-]?\d{3,4}[ .-]?\d{3,4}|3\d{2}[ .-]\d{3}[ .-]?\d{3,4})(?!\d)"), "<phone>"),
]
redactions = collections.Counter()


def scrub(text):
    for name, rx, rep in SCRUB:
        text, n = rx.subn(rep, text)
        redactions[name] += n
    return text


def clip(s, n=MAX_TXT):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"\n…[+{len(s) - n} chars]"


# ---------- projects ----------
def projects():
    out = {"_home": HOME}
    for d in sorted(os.listdir(HOME)):
        p = os.path.join(HOME, d)
        if d.startswith(".") or d in EXCLUDE or not os.path.isdir(p):
            continue
        if os.path.exists(os.path.join(p, "AGENTS.md")) or os.path.exists(os.path.join(p, "docs", "STATUS.md")):
            out[d] = p
    return out


def is_git(root):
    return root != HOME and os.path.isdir(os.path.join(root, ".git"))


def is_mem(rel):
    return rel in ROOT_DOCS or (rel.startswith("docs/") and rel.count("/") == 1)


def owner(path, projs, cwd=None):
    """(project, relpath) for an absolute or cwd-relative path, or (None, None)."""
    p = os.path.normpath(path if os.path.isabs(path) else os.path.join(cwd or HOME, path))
    if not p.startswith(HOME + "/"):
        return None, None
    rel = p[len(HOME) + 1:]
    top = rel.split("/", 1)[0]
    if top in projs and top != "_home":
        return top, rel[len(top) + 1:]
    if is_mem(rel):
        return "_home", rel
    return None, None


def denied(name):
    n = name.lower()
    return next((pat for pat in DENY if fnmatch.fnmatch(n, pat)), None)


def read_text(path, cap):
    try:
        size = os.path.getsize(path)
        if size > cap:
            return None, f"size {size}"
        with open(path, "rb") as f:
            b = f.read()
        if b"\0" in b[:8192]:
            return None, "binary"
        return b.decode("utf-8", "replace"), None
    except OSError as e:
        return None, f"error {e.__class__.__name__}"


def collect_files(name, root):
    """-> docs{rel:text}, code{rel:text}, skipped[(rel,reason)]"""
    docs, code, skipped = {}, {}, []
    if root == HOME:
        cands = [r for r in ("AGENTS.md", "CLAUDE.md") if os.path.exists(os.path.join(HOME, r))]
        cands += ["docs/" + f for f in sorted(os.listdir(os.path.join(HOME, "docs")))] if os.path.isdir(os.path.join(HOME, "docs")) else []
        for rel in cands:
            t, why = read_text(os.path.join(HOME, rel), MAX_DOC)
            (docs.__setitem__(rel, t) if t is not None else skipped.append((rel, why)))
        return docs, code, skipped
    if is_git(root):
        out = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard", "-z"],
                             capture_output=True, check=True).stdout.decode("utf-8", "replace")
        rels = [r for r in out.split("\0") if r]
    else:
        rels = []
        for d, dirs, files in os.walk(root):
            keep = []
            for x in dirs:
                rd = os.path.relpath(os.path.join(d, x), root)
                why = ("pruned dir" if x in PRUNE or x.startswith(".") or any(fnmatch.fnmatch(x.lower(), d) for d in DENY_DIR)
                       else (f"deny {denied(x)}" if denied(x) else None))
                (skipped.append((rd + "/", why)) if why else keep.append(x))
            dirs[:] = keep
            rels += [os.path.relpath(os.path.join(d, f), root) for f in files]
    for rel in sorted(rels):
        base = os.path.basename(rel)
        path = os.path.join(root, rel)
        if os.path.islink(path) or not os.path.isfile(path):
            continue
        if is_mem(rel):
            t, why = read_text(path, MAX_DOC)
            (docs.__setitem__(rel, t) if t is not None else skipped.append((rel, why)))
            continue
        pat = denied(base) or next((denied(part) for part in rel.split("/")[:-1] if denied(part)), None)
        if pat:
            skipped.append((rel, f"deny {pat}"))
            continue
        if not is_git(root) and os.path.splitext(base)[1].lower() not in CODE_EXT and base not in CODE_NAMES:
            skipped.append((rel, "ext not allowlisted"))
            continue
        t, why = read_text(path, MAX_CODE)
        (code.__setitem__(rel, t) if t is not None else skipped.append((rel, why)))
    return docs, code, skipped


def git_meta(root):
    g = lambda *a: subprocess.run(["git", "-C", root, *a], capture_output=True, text=True, errors="replace").stdout
    log = g("log", "--all", "--date=iso-strict", "--format=%x1e%H%x09%P%x09%ad%x09%an%x09%s", "--numstat")
    return {"head": g("rev-parse", "HEAD").strip(), "branch": g("branch", "--show-current").strip(),
            "status": g("status", "--porcelain")}, log


def bundle(root):
    tmp = f"/tmp/pm-eval-{os.getpid()}-{os.path.basename(root)}.bundle"
    try:
        subprocess.run(["git", "-C", root, "bundle", "create", tmp, "--all"], capture_output=True, check=True)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def host_snapshot():
    cmds = ["crontab -l", "systemctl list-units --type=service,timer --no-pager --plain",
            "systemctl --user list-units --type=service,timer,slice --no-pager --plain",
            "systemctl list-timers --all --no-pager", "docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'",
            "ls -la ~/.config/systemd/user/", "cat ~/.config/systemd/user/*.service ~/.config/systemd/user/*.slice",
            "cat /etc/default/earlyoom",
            "find ~ -maxdepth 3 \\( -name 'docker-compose*.yml' -o -name 'compose*.yml' \\) -not -path '*/node_modules/*'",
            "grep -oE '^[[:space:]]*(function[[:space:]]+)?[A-Za-z_][A-Za-z0-9_-]*[[:space:]]*\\(\\)' ~/.bashrc"]
    out = []
    for c in cmds:
        try:
            r = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=20, errors="replace")
            out.append(f"$ {c}\n{r.stdout}{r.stderr}")
        except subprocess.TimeoutExpired:
            out.append(f"$ {c}\n<timeout>")
    return "\n".join(out)


# ---------- transcripts ----------
ASKED = re.compile(MEM_NAME + r"|handoff|memor|document|\bdocs?\b|\bstatus\b|checkpoint", re.I)
EXPLICIT = re.compile(r"[/$]project-memory\b")
MEM_PATH = r"""['"]?((?:~?/|\.{0,2}/)?[\w./-]*?""" + MEM_NAME + r""")(?![\w.~-])['"]?"""
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1([^\n]*)\n(.*?)\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
SEG_WRITES = [
    ("rewrite", re.compile(r"(?<![>&\d])>\s*" + MEM_PATH)),
    ("append", re.compile(r">>\s*" + MEM_PATH)),
    ("tee", re.compile(r"\btee\s+(?:-a\s+)?" + MEM_PATH)),
    ("rm", re.compile(r"\brm\s+(?:-\w+\s+)*(?:--\s+)?" + MEM_PATH)),
    ("mv", re.compile(r"\b(?:mv|cp)\s+(?:-\w+\s+)*\S+\s+" + MEM_PATH)),
]
PY_WRITE = re.compile(r"""(?:Path\(\s*|open\(\s*)['"]([^'"]*?""" + MEM_NAME + r""")['"]""")


def bash_targets(cmd):
    """[(path, kind, plus)] for memory files a shell command writes. Heredoc bodies are data, not commands."""
    out, bodies = [], []

    def stash(m):
        bodies.append(m.group(4))
        return f"<<H{len(bodies) - 1}{m.group(3)}\n"
    flat = HEREDOC.sub(stash, cmd)
    for seg in re.split(r"&&|\|\||;|\n|\|(?!\|)", flat):
        hd = re.search(r"<<H(\d+)", seg)
        for kind, rx in SEG_WRITES:
            for m in rx.finditer(seg):
                plus = bodies[int(hd.group(1))].count("\n") + 1 if hd and kind in ("rewrite", "append", "tee") else None
                out.append((m.group(1), kind, plus))
        if re.search(r"\b(?:sed|perl)\s+(?:-\w*i|-i)", seg):
            out += [(m.group(1), "sed", None) for m in re.finditer(MEM_PATH, seg)]
    for b in bodies:
        if re.search(r"write_text|\.write\(|open\([^)]*['\"][wa]", b):
            out += [(m.group(1), "python", None) for m in PY_WRITE.finditer(b)]
    return out


def plusminus(lines):
    return sum(l.startswith("+") for l in lines), sum(l.startswith("-") for l in lines)


def new_session(sid, agent, path):
    return {"id": sid, "agent": agent, "file": os.path.basename(path), "model": None, "start": None, "end": None,
            "cwd": None, "user_prompts": [], "explicit_ts": None, "skill_calls": [], "memory_writes": [],
            "other_files_changed": [], "commands": [], "final_message": None}


def add_write(s, projs, ts, path, plus, minus, tool, patch=None, cwd=None, kind="edit"):
    proj, rel = owner(path, projs, cwd)
    if not proj:
        return
    if is_mem(rel):
        s["memory_writes"].append({"project": proj, "file": rel, "ts": ts, "tool": tool, "kind": kind,
                                   "plus": plus, "minus": minus, "patch": clip(patch, 20000) if patch else None})
    else:
        s["other_files_changed"].append({"project": proj, "path": rel, "ts": ts, "plus": plus, "minus": minus})


def bash_mem_writes(s, projs, ts, cmd, cwd):
    for path, kind, plus in bash_targets(cmd):
        add_write(s, projs, ts, path.replace("~", HOME, 1), plus, None, "bash?", patch=cmd, cwd=cwd, kind=kind)


def prompt_text(c):
    if isinstance(c, str):
        txt = c
    else:
        txt = "\n".join(b.get("text", "") for b in c if b.get("type") == "text")
    if not txt or txt.startswith(("<local-command", "<system-reminder>")) or "tool_result" in txt[:30]:
        return None
    m = re.search(r"<command-name>(.*?)</command-name>.*?(?:<command-args>(.*?)</command-args>)?", txt, re.S)
    return f"{m.group(1)} {m.group(2) or ''}".strip() if m else txt


def parse_claude(path, projs):
    s = new_session(os.path.basename(path)[:-6], "claude", path)
    tools, models = {}, collections.Counter()
    for line in open(path, errors="replace"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ts = r.get("timestamp")
        if ts:
            s["start"] = s["start"] or ts
            s["end"] = ts
        s["cwd"] = s["cwd"] or r.get("cwd")
        msg = r.get("message") or {}
        c = msg.get("content")
        if r.get("type") == "assistant" and isinstance(c, list):
            models[msg.get("model")] += 1
            for b in c:
                if b.get("type") == "tool_use":
                    tools[b["id"]] = (b["name"], b.get("input") or {})
                    if b["name"] == "Skill":
                        s["skill_calls"].append({"ts": ts, **(b.get("input") or {})})
                        if (b.get("input") or {}).get("skill") == "project-memory":
                            s["explicit_ts"] = s["explicit_ts"] or ts
                elif b.get("type") == "text" and b.get("text", "").strip():
                    s["final_message"] = b["text"]
        elif r.get("type") == "user" and not r.get("isMeta") and not r.get("isCompactSummary"):
            if isinstance(c, list) and any(b.get("type") == "tool_result" for b in c):
                tur = r.get("toolUseResult") if isinstance(r.get("toolUseResult"), dict) else {}
                for b in c:
                    if b.get("type") != "tool_result" or b.get("tool_use_id") not in tools:
                        continue
                    name, inp = tools[b["tool_use_id"]]
                    err = bool(b.get("is_error"))
                    if name == "Bash":
                        s["commands"].append({"ts": ts, "cmd": clip(inp.get("command", ""), 400), "error": err})
                        diff = tur.get("bashEditDiff") or {}
                        for fd in diff.get("files") or []:  # exact diffs recorded by Claude Code
                            lines = [l for h in fd.get("hunks") or [] for l in h.get("lines", [])]
                            p, m = plusminus(lines)
                            add_write(s, projs, ts, fd.get("filePath", ""), p, m, "bash", "\n".join(lines),
                                      cwd=r.get("cwd"), kind="bash")
                        if not diff.get("files") and not err:
                            bash_mem_writes(s, projs, ts, inp.get("command", ""), r.get("cwd"))
                    elif name in ("Edit", "Write") and not err:
                        lines = [l for h in (tur.get("structuredPatch") or []) for l in h.get("lines", [])]
                        p, m = plusminus(lines)
                        kind = "edit"
                        if name == "Write" and not tur.get("originalFile"):
                            kind, p, m = "create", (inp.get("content") or "").count("\n") + 1, 0
                            lines = ["+" + l for l in (inp.get("content") or "").split("\n")]
                        elif name == "Write":
                            kind = "rewrite"
                        add_write(s, projs, ts, inp.get("file_path", ""), p, m, name, "\n".join(lines), kind=kind)
            else:
                t = prompt_text(c)
                if t:
                    s["user_prompts"].append({"ts": ts, "text": clip(t, 3000)})
                    if EXPLICIT.search(t):
                        s["explicit_ts"] = s["explicit_ts"] or ts
    s["model"] = models.most_common(1)[0][0] if models else None
    return s


JS_STR = re.compile(r'"((?:[^"\\]|\\.)*?\*\*\* Begin Patch(?:[^"\\]|\\.)*?)"|`([^`]*?\*\*\* Begin Patch[^`]*?)`', re.S)
PATCH_FILE = re.compile(r"^\*\*\* (Add|Update|Delete) File: (.+)$", re.M)
JSON_FIELD = lambda k: re.compile(r'"%s"\s*:\s*("(?:[^"\\]|\\.)*")' % k)


def codex_patches(text):
    """Yield (action, path, patch_body) from raw patch text or JS source containing patch string literals."""
    bodies = [text] if text.lstrip().startswith("*** Begin Patch") else []
    for m in JS_STR.finditer(text):
        if m.group(1) is not None:
            try:
                bodies.append(json.loads('"' + m.group(1) + '"'))
            except ValueError:
                pass
        else:
            bodies.append(m.group(2))
    for body in bodies:
        heads = list(PATCH_FILE.finditer(body))
        for i, h in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
            yield h.group(1), h.group(2).strip(), body[h.end():end]


def parse_codex(path, projs):
    s = new_session(None, "codex", path)
    pending = {}
    for line in open(path, errors="replace"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ts, p = r.get("timestamp"), r.get("payload") or {}
        if ts:
            s["start"] = s["start"] or ts
            s["end"] = ts
        t = r.get("type")
        if t == "session_meta":
            s["id"], s["cwd"] = p.get("id") or p.get("session_id"), p.get("cwd")
        elif t == "turn_context":
            s["model"] = p.get("model") or s["model"]
        elif p.get("type") == "user_message":
            txt = p.get("message") or ""
            if txt.strip():
                s["user_prompts"].append({"ts": ts, "text": clip(txt, 3000)})
                if EXPLICIT.search(txt):
                    s["explicit_ts"] = s["explicit_ts"] or ts
        elif p.get("type") == "message" and p.get("role") == "user":
            txt = "".join(b.get("text", "") for b in p.get("content") or [])
            if "<skill" in txt and "project-memory" in txt:
                s["explicit_ts"] = s["explicit_ts"] or ts
        elif p.get("type") in ("custom_tool_call", "function_call"):
            src = p.get("input") if p["type"] == "custom_tool_call" else p.get("arguments")
            src = src or ""
            wd = s["cwd"]
            m = JSON_FIELD("workdir").search(src)
            if m:
                try:
                    wd = json.loads(m.group(1))
                except ValueError:
                    pass
            for action, fpath, body in codex_patches(src):
                pl, mi = plusminus([l for l in body.split("\n") if not l.startswith("***")])
                add_write(s, projs, ts, fpath, pl, mi, "apply_patch", body, cwd=wd,
                          kind={"Add": "create", "Delete": "delete"}.get(action, "edit"))
            cmds = []
            for m in JSON_FIELD("cmd").finditer(src):
                try:
                    cmds.append(json.loads(m.group(1)))
                except ValueError:
                    pass
            if p["type"] == "function_call" and not cmds:
                try:
                    a = json.loads(src)
                    c = a.get("cmd") or a.get("command")
                    cmds = [" ".join(c) if isinstance(c, list) else c] if c else []
                except ValueError:
                    pass
            for c in cmds:
                if "*** Begin Patch" in c:
                    continue
                entry = {"ts": ts, "cmd": clip(c, 400), "error": None}
                s["commands"].append(entry)
                pending.setdefault(p.get("call_id"), []).append(entry)
                bash_mem_writes(s, projs, ts, c, wd)
        elif p.get("type") in ("custom_tool_call_output", "function_call_output"):
            out = p.get("output")
            out = "".join(b.get("text", "") for b in out) if isinstance(out, list) else str(out or "")
            m = re.search(r"(?i)(?:exit code|exited with code)\D{0,3}(\d+)", out)
            for e in pending.pop(p.get("call_id"), []):
                e["error"] = (m.group(1) != "0") if m else None
        elif p.get("type") == "task_complete" and p.get("last_agent_message"):
            s["final_message"] = p["last_agent_message"]
    s["id"] = s["id"] or os.path.basename(path)[:-6]
    return s


def classify(s):
    """Tag each memory write: explicit (skill in context) / user-asked / protocol."""
    prompts = s["user_prompts"]
    for w in s["memory_writes"]:
        if s["explicit_ts"] and w["ts"] and w["ts"] >= s["explicit_ts"]:
            w["trigger"] = "explicit"
            continue
        last = [p for p in prompts if p["ts"] and w["ts"] and p["ts"] <= w["ts"]]
        w["trigger"] = "user-asked" if last and ASKED.search(last[-1]["text"]) else "protocol"


def sessions(projs):
    files = [("claude", f) for f in glob.glob(f"{HOME}/.claude/projects/*/*.jsonl")]
    files += [("codex", f) for f in glob.glob(f"{HOME}/.codex/sessions/**/*.jsonl", recursive=True)]
    for agent, f in sorted(files):
        try:
            s = (parse_claude if agent == "claude" else parse_codex)(f, projs)
        except Exception as e:  # one corrupt transcript must not sink the harvest
            print(f"warn: {f}: {e}", file=sys.stderr)
            continue
        classify(s)
        touched = {w["project"] for w in s["memory_writes"] + s["other_files_changed"]}
        cwd_proj = owner(os.path.join(s["cwd"] or HOME, "AGENTS.md"), projs)[0] if s["cwd"] else None
        if cwd_proj:
            touched.add(cwd_proj)
        if touched:
            yield s, touched


def scrub_obj(o):
    if isinstance(o, str):
        return scrub(o)
    if isinstance(o, list):
        return [scrub_obj(x) for x in o]
    if isinstance(o, dict):
        return {k: scrub_obj(v) for k, v in o.items()}
    return o


# ---------- main ----------
def main(argv):
    dry = "--dry-run" in argv
    for a in argv:
        if a.startswith(("--exclude=", "--bundle=")):
            (EXCLUDE if a.startswith("--exclude=") else BUNDLE).update(a.split("=", 1)[1].split(","))
    only = next((a.split("=", 1)[1].split(",") for a in argv if a.startswith("--only=")), None)
    projs = projects()
    if only:
        projs = {k: v for k, v in projs.items() if k in only}
    tar = None if dry else tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz")
    report = []

    def put(name, data):
        if tar:
            b = data if isinstance(data, bytes) else data.encode()
            ti = tarfile.TarInfo(name)
            ti.size, ti.mtime = len(b), int(time.time())
            tar.addfile(ti, io.BytesIO(b))

    per_proj = collections.defaultdict(list)
    for s, touched in sessions(projs):
        for pr in touched:
            if pr in projs:
                per_proj[pr].append(s)

    for name, root in projs.items():
        docs, code, skipped = collect_files(name, root)
        for rel, t in docs.items():
            put(f"{name}/docs/{rel}", scrub(t))
        for rel, t in code.items():
            put(f"{name}/code/{rel}", scrub(t))
        meta = {"project": name, "git": is_git(root), "docs": sorted(docs), "n_code": len(code)}
        if is_git(root):
            gm, log = git_meta(root)
            meta.update(gm)
            put(f"{name}/gitlog.txt", scrub(log))
            if name in BUNDLE and not dry:
                put(f"{name}/git.bundle", bundle(root))
        if name == "_home":
            put("_home/hoststate.txt", scrub(host_snapshot()))
        events = []
        for s in per_proj.get(name, []):
            clean = scrub_obj(s)
            put(f"{name}/sessions/{s['agent']}-{s['id']}.json", json.dumps(clean, indent=1, ensure_ascii=False))
            events += [{"session": s["id"], "agent": s["agent"], "model": s["model"], **{k: v for k, v in w.items() if k != "patch"}}
                       for w in clean["memory_writes"] if w["project"] == name]
        events.sort(key=lambda e: e["ts"] or "")
        put(f"{name}/events.jsonl", "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
        put(f"{name}/skipped.txt", "".join(f"{r}\t{why}\n" for r, why in skipped))
        put(f"{name}/meta.json", json.dumps(meta, indent=1))
        report.append((name, meta, skipped, per_proj.get(name, []), events))

    put("_redactions.json", json.dumps(redactions, indent=1))
    if tar:
        tar.close()
        return
    for name, meta, skipped, sess, events in report:
        trig = collections.Counter(e["trigger"] for e in events)
        agents = collections.Counter(s["agent"] for s in sess)
        print(f"\n== {name}  git={meta['git']}  docs={len(meta['docs'])}  code={meta['n_code']}  "
              f"sessions={dict(agents)}  mem_writes={len(events)} {dict(trig)}"
              + ("  +bundle" if name in BUNDLE else ""))
        by = collections.defaultdict(list)
        for r, why in skipped:
            by[why.split(" ")[0] if why.startswith(("size", "error")) else why].append(r)
        for why, rs in sorted(by.items(), key=lambda x: -len(x[1])):
            print(f"   skip {len(rs):5d}  {why:24s} e.g. {', '.join(rs[:4])}")
    print("\nREDACTIONS", dict(redactions))


def selftest():
    assert scrub("API_KEY=abc123xyz") == "API_KEY=<REDACTED>"
    assert "<REDACTED>" in scrub('password = "hunter2hunter2"')
    assert scrub("password = request.params['password']") == "password = request.params['password']"
    assert scrub("mail mario.rossi@example.it now") == "mail <email> now"
    assert scrub("IBAN IT60X0542811101000000123456 ok") == "IBAN <REDACTED:iban> ok"
    assert scrub("tel +39 333 1234567") == "tel <phone>"
    assert scrub("version 19.0.1.1.135 port 57984") == "version 19.0.1.1.135 port 57984"
    assert scrub("postgres://u:pw@db/x") == "postgres://<REDACTED:cred>@db/x"
    js = 'const patch = "*** Begin Patch\\n*** Update File: /home/u/p/docs/STATUS.md\\n@@\\n-old\\n+new\\n+more\\n*** End Patch";'
    (a, p, body), = codex_patches(js)
    assert (a, p) == ("Update", "/home/u/p/docs/STATUS.md")
    assert plusminus([l for l in body.split("\n") if not l.startswith("***")]) == (2, 1)
    assert is_mem("docs/STATUS.md") and is_mem("AGENTS.md") and not is_mem("docs/faq/x.md")
    s = {"explicit_ts": None, "user_prompts": [{"ts": "1", "text": "aggiorna la documentazione"}],
         "memory_writes": [{"ts": "2"}]}
    classify(s)
    assert s["memory_writes"][0]["trigger"] == "user-asked"
    t = lambda c: [(p, k) for p, k, _ in bash_targets(c)]
    assert t("cd x && sed -n 1,200p a.py; grep -rn foo docs/STATUS.md >/dev/null | head") == []
    assert t("cat > docs/ARCHITECTURE.md <<'EOF'\nsee docs/STATUS.md\nEOF") == [("docs/ARCHITECTURE.md", "rewrite")]
    assert bash_targets("cat <<'EOF' > docs/STATUS.md\na\nb\nEOF")[0][2] == 2
    assert t("python3 - <<'EOF'\np = pathlib.Path(\"README.md\")\np.write_text(s)\nEOF") == [("README.md", "python")]
    assert t("python3 - <<'EOF'\nprint(open('docs/STATUS.md').read())\nEOF") == []
    assert t("sed -i 's/a/b/' docs/STATUS.md") == [("docs/STATUS.md", "sed")]
    assert t("echo x >> CHANGELOG.md && rm -- docs/STATUS.md.orig") == [("CHANGELOG.md", "append")]
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main(sys.argv[1:])
