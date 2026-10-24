#!/usr/bin/env python3
"""Layer A: mechanical checks of harvested project-memory docs against SKILL.md rules.

    python3 check.py HARVEST_DIR OUT_DIR      # writes OUT_DIR/<proj>/a.json, prints summary
    python3 check.py --secrets HARVEST_DIR    # high-confidence secret re-scan; exit 1 on any hit
    python3 check.py --selftest
"""
import collections, json, os, re, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT = ["README.md", "AGENTS.md", "CLAUDE.md", "CHANGELOG.md",
           "docs/TREE.md", "docs/ARCHITECTURE.md", "docs/DECISIONS.md", "docs/STATUS.md"]
LIMITS = {"docs/STATUS.md": 120, "AGENTS.md": 120}  # orientation only: bloat is judged by dup/diary/prune, not size
SECRET = [
    ("privkey", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("apikey", re.compile(r"\b(?:sk-(?:ant-)?[\w-]{20,}|ghp_\w{30,}|github_pat_\w{20,}|xox[abprs]-[\w-]{10,}|AKIA[0-9A-Z]{16}|AIza[\w-]{35})")),
    ("jwt", re.compile(r"\beyJ[\w-]{10,}\.[\w-]{10,}\.[\w-]{10,}")),
    ("telegram", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b")),
    ("url_cred", re.compile(r"://(?!<REDACTED)[^/\s:@]+:[^/\s@]{3,}@")),
    ("env_secret", re.compile(r"(?m)^\s*(?:export\s+)?[A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*=(?!<REDACTED)[^\s$<{]{8,}")),
]
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICK_PATH = re.compile(r"`([\w.-]+(?:/[\w.-]+)+/?)`")
PLACEHOLDER = re.compile(r"\bTBD\b|\bTODO\b|\bXXX\b|placeholder|lorem ipsum|<(?:date|path|name|description|project)>|\[insert", re.I)
DATED_LINE = re.compile(r"^(?:#+|[-*]|\|)\s*\**\s*(?:\d{4}-\d{2}-\d{2})", re.M)
DONE_LINE = re.compile(r"^\s*[-*]\s*(?:\[x\]|✅|~~|(?:done|completed|fixed|implemented)\b)", re.I | re.M)
DEC_HEAD = re.compile(r"^#{2,3}\s*(D-?\d+|ADR-?\d+)\b[:\s]*(.*)$", re.M)
DEC_FIELDS = ["Status", "Date", "Context", "Decision", "Rationale", "Alternatives", "Consequences"]
SKILL_INSTALLED = "2026-09-10T07:01"  # ~/.agents/skills/project-memory mtime on the VPS; earlier writes are not the skill's


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def load(hdir):
    docs = {}
    droot = os.path.join(hdir, "docs")
    for d, _, fs in os.walk(droot):
        for f in fs:
            docs[os.path.relpath(os.path.join(d, f), droot)] = read(os.path.join(d, f))
    code = set()
    croot = os.path.join(hdir, "code")
    for d, _, fs in os.walk(croot):
        code |= {os.path.relpath(os.path.join(d, f), croot) for f in fs}
    skipped = {l.split("\t")[0] for l in read(os.path.join(hdir, "skipped.txt")).splitlines()} \
        if os.path.exists(os.path.join(hdir, "skipped.txt")) else set()
    events = [json.loads(l) for l in read(os.path.join(hdir, "events.jsonl")).splitlines()] \
        if os.path.exists(os.path.join(hdir, "events.jsonl")) else []
    gitlog = read(os.path.join(hdir, "gitlog.txt")) if os.path.exists(os.path.join(hdir, "gitlog.txt")) else ""
    meta = json.loads(read(os.path.join(hdir, "meta.json"))) if os.path.exists(os.path.join(hdir, "meta.json")) else {}
    return docs, code, skipped, events, gitlog, meta


def path_exists(rel, known):
    rel = rel.rstrip("/")
    return rel in known or any(k.startswith(rel + "/") for k in known)


def strip_fences(t):
    return re.sub(r"```.*?```", "", t, flags=re.S)


def decisions(t):
    heads = list(DEC_HEAD.finditer(t))
    out = []
    for i, h in enumerate(heads):
        body = t[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(t)]
        fields = {f: bool(re.search(rf"^\s*[-*]?\s*\**{f}\**\s*:", body, re.M | re.I)) for f in DEC_FIELDS}
        status = re.search(r"^\s*[-*]?\s*\**Status\**\s*:\s*\**\s*(\w+)", body, re.M | re.I)
        date = re.search(r"^\s*[-*]?\s*\**Date\**\s*:\s*(.+)$", body, re.M | re.I)
        out.append({"id": h.group(1), "lines": body.count("\n"), "missing": [f for f, ok in fields.items() if not ok],
                    "status": status.group(1).lower() if status else None, "date": date.group(1).strip() if date else None})
    return out


def git_growth(gitlog, files):
    """Line count per memory file after each commit, oldest first, from numstat."""
    commits = []
    for rec in gitlog.split("\x1e")[1:]:
        lines = rec.strip("\n").split("\n")
        h, _, date = (lines[0].split("\t") + ["", "", ""])[:3]
        stats = [l.split("\t") for l in lines[1:] if l.count("\t") == 2]
        commits.append((date, h[:10], stats))
    commits.sort()
    size, curve = collections.Counter(), collections.defaultdict(list)
    for date, h, stats in commits:
        for a, d, path in stats:
            if path in files and a != "-":
                size[path] += int(a) - int(d)
                curve[path].append([date[:10], h, size[path]])
    return dict(curve), len(commits), (commits[-1][0] if commits else None)


def event_stats(events):
    by_file = collections.defaultdict(lambda: collections.Counter())
    for e in events:
        c = by_file[e["file"]]
        c["writes"] += 1
        c["plus"] += e.get("plus") or 0
        c["minus"] += e.get("minus") or 0
        c[f"trigger:{e.get('trigger')}"] += 1
        c[f"agent:{e.get('agent')}"] += 1
        c[f"kind:{e.get('kind')}"] += 1
        c[f"plus:{e.get('agent')}"] += e.get("plus") or 0
        c[f"minus:{e.get('agent')}"] += e.get("minus") or 0
        if e.get("trigger") in ("explicit", "protocol", "user-asked"):
            c[f"plus:{e['trigger']}"] += e.get("plus") or 0
            c[f"minus:{e['trigger']}"] += e.get("minus") or 0
    out = {}
    for f, c in by_file.items():
        tot = c["plus"] + c["minus"]
        out[f] = dict(c, append_ratio=round(c["plus"] / tot, 2) if tot else None,
                      sessions=len({e["session"] for e in events if e["file"] == f}))
    return out


def check(hdir):
    docs, code, skipped, events, gitlog, meta = load(hdir)
    name = os.path.basename(os.path.normpath(hdir))
    known = set(docs) | code | skipped
    home = name == "_home"
    r = {"project": name, "git": meta.get("git"), "findings": []}
    add = lambda rule, sev, file, msg: r["findings"].append({"rule": rule, "severity": sev, "file": file, "msg": msg})

    r["lines"] = {f: t.count("\n") for f, t in sorted(docs.items())}
    expected = ["AGENTS.md", "CLAUDE.md", "docs/STATUS.md"] if home else DEFAULT
    r["missing"] = [f for f in expected if f not in docs]
    for f in r["missing"]:
        add("A-layout", "L", f, "default file absent (ok if equivalent documented in AGENTS.md)")
    for f, lim in LIMITS.items():
        n = r["lines"].get(f, 0)
        if n > lim:
            add("A-size", "L", f, f"{n} lines (orientation ~{lim}); check for redundancy and stale content")

    claude, agents = docs.get("CLAUDE.md", ""), docs.get("AGENTS.md", "")
    if "CLAUDE.md" in docs:
        if not re.search(r"^@AGENTS\.md\s*$", claude, re.M):
            add("A-entry", "H", "CLAUDE.md", "no `@AGENTS.md` import line")
        if claude.strip() and claude.strip() == agents.strip():
            add("A-entry", "H", "CLAUDE.md", "full copy of AGENTS.md (duplicate loading)")
    if re.search(r"^@CLAUDE\.md\s*$", agents, re.M):
        add("A-entry", "H", "AGENTS.md", "imports CLAUDE.md (cycle)")
    if agents and "## Project memory" not in agents:
        add("A-entry", "M", "AGENTS.md", "no `## Project memory` section")

    for f in docs:
        if re.search(r"\.(orig|rej|bak)$|~$", f):
            add("A-stray", "M", f, "stray backup/patch file in memory docs")
    for f in skipped:
        if re.search(r"(?:AGENTS|CLAUDE|STATUS|DECISIONS|README)\.md[.~]", f):
            add("A-stray", "L", f, "stray memory-file backup in project")

    broken = collections.defaultdict(list)
    for f, t in docs.items():
        if not f.endswith(".md"):
            continue
        base = os.path.dirname(f)
        # links resolve relative to the document; TREE backtick paths relative to the project root
        refs = [(r, os.path.normpath(os.path.join(base, r.split("#")[0]))) for r in LINK.findall(t)]
        refs += [(r, r) for r in TICK_PATH.findall(strip_fences(t))] if f.endswith("TREE.md") else []
        for ref, tgt in refs:
            if not ref.split("#")[0] or re.match(r"^[a-z]+:|^/|^~", ref):
                continue
            if tgt.startswith("..") or home and tgt.split("/")[0] not in ("docs", "AGENTS.md", "CLAUDE.md"):
                continue  # outside the project / home links into project folders: not harvested as files
            if not path_exists(tgt, known):
                broken[f].append(ref)
    for f, refs in broken.items():
        add("A-links", "M" if len(refs) > 2 else "L", f, f"{len(refs)} unresolved paths: {', '.join(sorted(set(refs))[:8])}")

    for f, t in docs.items():
        n = len(PLACEHOLDER.findall(strip_fences(t)))
        if n:
            add("A-placeholder", "L", f, f"{n} placeholder-like tokens")

    st = docs.get("docs/STATUS.md", "")
    if st:
        upd = re.search(r"Updated:\s*\**\s*(\d{4}-\d{2}-\d{2})", st)
        r["status"] = {"updated": upd.group(1) if upd else None, "dated_lines": len(DATED_LINE.findall(st)),
                       "done_items": len(DONE_LINE.findall(st)), "h2": len(re.findall(r"^## ", st, re.M))}
        if not upd:
            add("A-status", "L", "docs/STATUS.md", "no `Updated:` date")
        if r["status"]["dated_lines"] > 5:
            add("A-diary", "H" if r["status"]["dated_lines"] > 20 else "M", "docs/STATUS.md",
                f"{r['status']['dated_lines']} date-led lines/headings (chronological diary)")
        if r["status"]["done_items"] > 15:
            add("A-prune", "M", "docs/STATUS.md", f"{r['status']['done_items']} completed items retained")

    dec = docs.get("docs/DECISIONS.md", "")
    if dec:
        ds = decisions(dec)
        ids = [d["id"] for d in ds]
        r["decisions"] = {"count": len(ds), "avg_lines": round(sum(d["lines"] for d in ds) / len(ds), 1) if ds else 0,
                          "statuses": dict(collections.Counter(d["status"] for d in ds)),
                          "missing_fields": dict(collections.Counter(m for d in ds for m in d["missing"])),
                          "dup_ids": [i for i, c in collections.Counter(ids).items() if c > 1]}
        if r["decisions"]["dup_ids"]:
            add("A-decisions", "M", "docs/DECISIONS.md", f"duplicate ids {r['decisions']['dup_ids']}")
        if ds and r["decisions"]["avg_lines"] > 40:
            add("A-decisions", "M", "docs/DECISIONS.md", f"avg {r['decisions']['avg_lines']} lines/decision (log, not decisions?)")
        sup = [d["id"] for d in ds if d["status"] == "superseded"]
        for i in sup:
            body = dec[dec.find(i):]
            if not re.search(r"(?:superseded by|see|replaced by)\s+\[?D-?\d+", body[:3000], re.I):
                add("A-decisions", "L", "docs/DECISIONS.md", f"{i} superseded without link to replacement")

    long_lines = collections.defaultdict(set)
    for f, t in docs.items():
        for l in strip_fences(t).splitlines():
            l = l.strip()
            if len(l) >= 100:
                long_lines[l].add(f)
    dups = [(l, sorted(fs)) for l, fs in long_lines.items() if len(fs) > 1]
    r["dup_lines"] = len(dups)
    if len(dups) > 3:
        pairs = collections.Counter(" + ".join(fs) for _, fs in dups)
        add("A-dup", "M", ", ".join(pairs.most_common(1)[0][0].split(" + ")), f"{len(dups)} long lines verbatim in 2+ files; top: {dict(pairs.most_common(3))}")

    r["pre_skill_writes"] = sum(1 for e in events if (e.get("ts") or "") < SKILL_INSTALLED)
    r["events"] = event_stats([e for e in events if (e.get("ts") or "") >= SKILL_INSTALLED])
    s = r["events"].get("docs/STATUS.md")
    if s and s["writes"] >= 10 and (s["append_ratio"] or 0) > 0.7:
        add("A-accrete", "H", "docs/STATUS.md", f"{s['writes']} writes, {s['plus']}+/{s['minus']}- (append ratio {s['append_ratio']})")
    if gitlog:
        curve, n_commits, last = git_growth(gitlog, set(DEFAULT))
        r["git"] = {"commits": n_commits, "last_commit": last, "curve": curve}
        if st and r["status"]["updated"] and last and r["status"]["updated"] < last[:10]:
            add("A-stale", "L", "docs/STATUS.md", f"Updated {r['status']['updated']} < last commit {last[:10]}")
    return r


def secrets(hdir):
    hits = []
    for d, _, fs in os.walk(hdir):
        for f in fs:
            if f.endswith(".bundle"):
                continue
            p = os.path.join(d, f)
            for i, line in enumerate(read(p).splitlines(), 1):
                for name, rx in SECRET:
                    if rx.search(line):
                        hits.append((os.path.relpath(p, hdir), i, name))
    for h in hits:
        print("%s:%d %s" % h)
    print(f"{len(hits)} secret hits")
    return hits


def main(hroot, out):
    if os.path.abspath(out).startswith(REPO + os.sep):
        sys.exit("refusing to write results inside the repo")
    rows = []
    for name in sorted(os.listdir(hroot)):
        hdir = os.path.join(hroot, name)
        if not os.path.isdir(hdir):
            continue
        r = check(hdir)
        os.makedirs(os.path.join(out, name), exist_ok=True)
        with open(os.path.join(out, name, "a.json"), "w") as f:
            json.dump(r, f, indent=1)
        sev = collections.Counter(x["severity"] for x in r["findings"])
        st = r["events"].get("docs/STATUS.md", {})
        rows.append((name, r["lines"].get("docs/STATUS.md", "-"), r["lines"].get("AGENTS.md", "-"),
                     r["lines"].get("docs/DECISIONS.md", "-"), st.get("writes", 0), st.get("append_ratio", "-"),
                     sev["H"], sev["M"], sev["L"]))
    print(f"{'project':24} {'STATUS':>6} {'AGENTS':>6} {'DECIS':>6} {'St.wr':>6} {'app%':>5}  H  M  L")
    for row in rows:
        print("%-24s %6s %6s %6s %6s %5s %2d %2d %2d" % row)


def selftest():
    with tempfile.TemporaryDirectory() as t:
        h = os.path.join(t, "proj")
        os.makedirs(os.path.join(h, "docs", "docs"))
        os.makedirs(os.path.join(h, "code", "src"))
        open(os.path.join(h, "code", "src", "app.py"), "w").write("x")
        open(os.path.join(h, "docs", "CLAUDE.md"), "w").write("hello\n")
        open(os.path.join(h, "docs", "AGENTS.md"), "w").write("## Project memory\nsee [s](docs/STATUS.md) [x](src/gone.py)\n")
        open(os.path.join(h, "docs", "docs", "STATUS.md"), "w").write(
            "# Current status\n" + "".join(f"- 2026-10-{i:02d} did thing\n" for i in range(1, 30)) + "x\n" * 150)
        open(os.path.join(h, "docs", "docs", "DECISIONS.md.orig"), "w").write("x")
        open(os.path.join(h, "docs", "docs", "DECISIONS.md"), "w").write(
            "## D-001: A\n- Status: accepted\n- Date: unknown\n## D-001: B\n- Status: superseded\n")
        open(os.path.join(h, "events.jsonl"), "w").write("".join(
            json.dumps({"session": str(i), "ts": "2026-10-01T00:00", "file": "docs/STATUS.md", "plus": 10, "minus": 1, "trigger": "explicit",
                        "agent": "claude", "kind": "edit"}) + "\n" for i in range(12)))
        r = check(h)
        rules = {(x["rule"], x["file"]) for x in r["findings"]}
        assert ("A-entry", "CLAUDE.md") in rules, rules
        assert ("A-size", "docs/STATUS.md") in rules
        assert ("A-diary", "docs/STATUS.md") in rules
        assert ("A-stray", "docs/DECISIONS.md.orig") in rules
        assert ("A-decisions", "docs/DECISIONS.md") in rules
        assert ("A-accrete", "docs/STATUS.md") in rules
        assert any(x["rule"] == "A-links" and "src/gone.py" in x["msg"] and "STATUS" not in x["msg"] for x in r["findings"]), r["findings"]
        open(os.path.join(h, "leak.txt"), "w").write("API_TOKEN=abcdefghijkl\n")
        assert len(secrets(h)) == 1
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--selftest"]:
        selftest()
    elif a[:1] == ["--secrets"]:
        sys.exit(1 if secrets(a[1]) else 0)
    else:
        main(*a)
