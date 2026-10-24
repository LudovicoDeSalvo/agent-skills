#!/usr/bin/env python3
"""Counterfactual docs replay: real code history fixed, only project-memory maintenance re-run.

    python3 replay.py HARVEST OUT --skill=SKILL.md --projects=proj-a,proj-b:15 [--retention]
    python3 replay.py --compare OUT                 # old-vs-new table (also --judge to run layer B on the last step)
    python3 replay.py --selftest

For each harvested session (post-install, in order) that wrote memory: check out the commit that best matches the
end of the session in a copy of the repo whose history has memory files stripped, overlay the memory files
carried from the previous replay step, and ask the session's agent (claude/codex, original model) to do the
memory maintenance from a session digest using the SKILL.md under test. Steps are cached in
OUT/<skill-md5>/<project>/step-NN/ (docs/, meta.json, a.json, agent.log), so a baseline is replayed once.
"""
import datetime, hashlib, json, os, shutil, string, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check  # noqa: E402

INSTALLED = "2026-09-10T07:01"
WORK = "/tmp/pm-replay-work"  # away from the harvest so agents cannot stumble on the real docs
ROOT_DOCS = {"README.md", "AGENTS.md", "CLAUDE.md", "CHANGELOG.md"}
CLAUDE_TOOLS = "Read,Grep,Glob,Edit,Write,Bash"
CLAUDE_ALLOW = ["Read", "Grep", "Glob", "Edit", "Write", "Bash(git log:*)", "Bash(git status:*)", "Bash(git diff:*)",
                "Bash(git show:*)", "Bash(git branch:*)", "Bash(git rev-parse:*)", "Bash(ls:*)", "Bash(wc:*)"]
BLOAT_RULES = {"R-05", "R-12", "R-13", "R-14", "R-21", "R-22", "R-24"}  # redundancy, stale/unpruned, diary, misrouted history
RETENTION = {"type": "object", "required": ["facts"], "properties": {"facts": {"type": "array", "items": {
    "type": "object", "required": ["index", "verdict"],
    "properties": {"index": {"type": "integer"}, "verdict": {"enum": ["present", "partial", "absent", "contradicted"]},
                   "where": {"type": "string"}}}}}}


def is_mem(rel):
    return rel in ROOT_DOCS or (rel.startswith("docs/") and rel.count("/") == 1)


def git(repo, *a, **kw):
    return subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True, check=True, **kw).stdout


def ts(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


def clip(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n] + f" …[+{len(s) - n}]"


def sessions_to_replay(hdir, name, limit=None):
    out = []
    for f in os.listdir(os.path.join(hdir, "sessions")):
        s = json.load(open(os.path.join(hdir, "sessions", f)))
        if (s.get("start") or "") < INSTALLED or not s.get("end"):
            continue
        if any(w["project"] == name for w in s["memory_writes"]):
            out.append(s)
    out.sort(key=lambda s: s["start"])
    return out[:limit] if limit else out


def prepare_repos(hdir, name, md5):
    """-> (orig, filtered) clones under WORK/<skill-md5>/<name> (one checkout per concurrent run). Filtered history has every memory file removed."""
    base = os.path.join(WORK, md5, name)
    orig, filt = os.path.join(base, "orig"), os.path.join(base, "filtered")
    if not os.path.isdir(filt):
        shutil.rmtree(base, ignore_errors=True)
        os.makedirs(base)
        bundle = os.path.join(hdir, "git.bundle")
        for d in (orig, filt):
            subprocess.run(["git", "clone", "-q", bundle, d], check=True)
            for ref in git(d, "for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").split():
                b = ref.split("/", 1)[1]
                if b != "HEAD":
                    subprocess.run(["git", "-C", d, "branch", "-q", "-f", b, ref], capture_output=True)
        rm = "git rm -r --cached --ignore-unmatch -q -- " + " ".join(sorted(ROOT_DOCS)) + " ':(glob)docs/*'"
        subprocess.run(["git", "-C", filt, "filter-branch", "-f", "--index-filter", rm, "--", "--branches"],
                       check=True, capture_output=True, env={**os.environ, "FILTER_BRANCH_SQUELCH_WARNING": "1"})
        subprocess.run(["git", "-C", filt, "remote", "remove", "origin"], check=True)
        for d in (orig, filt):
            subprocess.run(["git", "-C", d, "config", "user.name", "replay"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "replay@localhost"], check=True)
    return orig, filt


def commits(repo):
    out = []
    for line in git(repo, "log", "--branches", "--format=%H %cI").splitlines():
        h, d = line.split(" ", 1)
        out.append((ts(d), h))
    return sorted(out)


def pick_commit(cs, start, end, next_start):
    """First commit landing between session end and next session start (the session's work, committed);
    else latest commit at or before session end; else the earliest commit."""
    after = [h for d, h in cs if end <= d < next_start]
    if after:
        return after[0]
    before = [h for d, h in cs if d <= end]
    return before[-1] if before else cs[0][1]


def initial_docs(orig, first_start):
    """Memory files as they existed in the real repo at the first replayed session's start (pre-existing docs)."""
    before = [h for d, h in commits(orig) if d <= first_start]
    if not before:
        return {}
    h = before[-1]
    files = [p for p in git(orig, "ls-tree", "-r", "--name-only", h).splitlines() if is_mem(p)]
    return {p: git(orig, "show", f"{h}:{p}") for p in files}


def digest(s, name):
    prompts = "\n".join(f"{i}. [{p['ts'][:16]}] {clip(p['text'], 1500)}" for i, p in enumerate(s["user_prompts"], 1))
    agg = {}
    for f in s["other_files_changed"]:
        if f["project"] == name:
            a = agg.setdefault(f["path"], [0, 0])
            a[0] += f.get("plus") or 0
            a[1] += f.get("minus") or 0
    files = "\n".join(f"- {p} +{a}/-{b}" for p, (a, b) in sorted(agg.items())) or "(none recorded)"
    cmds = s["commands"]
    if len(cmds) > 120:
        cmds = cmds[:40] + [{"cmd": f"… {len(cmds) - 120} commands omitted …", "error": None}] + cmds[-80:]
    commands = "\n".join(f"- {'error ' if c.get('error') else ''}`{clip(c['cmd'], 240).replace(chr(10), ' ⏎ ')}`"
                         for c in cmds) or "(none)"
    return prompts or "(none)", files, commands, clip(s.get("final_message"), 4000) or "(none)"


def operation(s, carried):
    calls = [c for c in s.get("skill_calls", []) if c.get("skill") == "project-memory"]
    explicit = [p["text"] for p in s["user_prompts"] if "project-memory" in p["text"]]
    if not any(k in carried for k in ("AGENTS.md", "docs/STATUS.md")):  # nothing to update yet: this is the init
        how = f"`{calls[0].get('args')}`" if calls and calls[0].get("args") else f"`{clip(explicit[0], 600)}`" if explicit else "(as the session requested)"
        return f"The user asked to initialize project memory with the project-memory skill: {how}\nDo that now."
    if calls or explicit or s.get("explicit_ts"):
        asks = "; ".join(f"`{clip(c.get('args') or '', 400)}`" for c in calls) or "; ".join(f"`{clip(e, 400)}`" for e in explicit)
        return (f"During the session the user invoked the project-memory skill ({asks or 'via a skill command'}). "
                f"Perform the memory update/checkpoint that the session called for, now that its work is done.")
    return ("The project's AGENTS.md memory protocol applies. Before handing back, update the project memory as "
            "that protocol requires for this session's work.")


def run_agent(s, prompt_text, repo, log):
    model = s.get("model")
    if s["agent"] == "claude":
        cmd = ["claude", "-p", "--safe-mode", "--no-session-persistence", "--output-format", "json",
               "--tools", CLAUDE_TOOLS, "--allowedTools", ",".join(CLAUDE_ALLOW)]
        cmd += ["--model", model] if model and model.startswith("claude") else []
        env = os.environ
    else:
        home = tempfile.mkdtemp(prefix="cxhome-")  # hides ~/.agents/skills; auth stays in the real CODEX_HOME
        cmd = ["codex", "exec", "--ignore-user-config", "--ephemeral", "--disable", "hooks", "--disable", "plugins",
               "-s", "workspace-write", "-C", repo, "-o", log + ".last", "-"]
        cmd[2:2] = ["-m", model] if model else []
        env = {**os.environ, "HOME": home, "CODEX_HOME": os.path.expanduser("~/.codex")}
    t0 = datetime.datetime.now()
    r = subprocess.run(cmd, input=prompt_text, cwd=repo, capture_output=True, text=True, env=env, timeout=5400)
    secs = (datetime.datetime.now() - t0).total_seconds()
    with open(log, "w") as f:
        f.write(r.stdout + "\n--- stderr ---\n" + r.stderr)
    cost, err = 0.0, None
    if s["agent"] == "claude":
        try:
            d = json.loads(r.stdout)
            cost, err = d.get("total_cost_usd") or 0, d.get("result") if d.get("is_error") else None
        except ValueError:
            err = f"exit {r.returncode}: {r.stderr[-400:]}"
    elif r.returncode:
        err = f"exit {r.returncode}: {r.stderr[-400:]}"
    return {"secs": round(secs), "cost": cost, "error": err, "returncode": r.returncode}


def materialize(repo, sha, carried):
    git(repo, "checkout", "-q", "-f", "--detach", sha)
    git(repo, "clean", "-fdxq")
    for p in [p for p in git(repo, "ls-files").splitlines() if is_mem(p)]:
        os.remove(os.path.join(repo, p))
    for p, t in carried.items():
        os.makedirs(os.path.dirname(os.path.join(repo, p)) or repo, exist_ok=True)
        with open(os.path.join(repo, p), "w") as f:
            f.write(t)
    if carried:
        git(repo, "add", "-f", "--", *carried)
        git(repo, "commit", "-q", "-m", "docs: project memory")
    return git(repo, "rev-parse", "HEAD").strip()


def harvest_state(repo):
    """Memory files now in the working tree + paths of non-memory files the agent touched."""
    docs = {}
    for p in sorted(set(git(repo, "ls-files").splitlines()) | set(git(repo, "ls-files", "-o", "--exclude-standard").splitlines())):
        if is_mem(p) and os.path.isfile(os.path.join(repo, p)):
            docs[p] = open(os.path.join(repo, p), encoding="utf-8", errors="replace").read()
    touched = [l[3:] for l in git(repo, "status", "--porcelain").splitlines() if not is_mem(l[3:].strip('"'))]
    return docs, touched


def write_step(sdir, docs, repo, meta):
    shutil.rmtree(os.path.join(sdir, "docs"), ignore_errors=True)
    for p, t in docs.items():
        os.makedirs(os.path.dirname(os.path.join(sdir, "docs", p)), exist_ok=True)
        with open(os.path.join(sdir, "docs", p), "w") as f:
            f.write(t)
    with open(os.path.join(sdir, "skipped.txt"), "w") as f:  # file list so check.py can resolve doc links
        f.write("".join(f"{p}\tin repo\n" for p in git(repo, "ls-files").splitlines() if not is_mem(p)))
    a = check.check(sdir)
    a.pop("events", None)
    json.dump(a, open(os.path.join(sdir, "a.json"), "w"), indent=1)
    json.dump(meta, open(os.path.join(sdir, "meta.json"), "w"), indent=1)


def replay_project(hroot, out, skill_path, name, limit):
    hdir = os.path.join(hroot, name)
    md5 = hashlib.md5(open(skill_path, "rb").read()).hexdigest()[:8]
    pdir = os.path.join(out, md5, name)
    os.makedirs(pdir, exist_ok=True)
    orig, repo = prepare_repos(hdir, name, md5)
    ss = sessions_to_replay(hdir, name, limit)
    cs = commits(repo)
    carried = initial_docs(orig, ts(ss[0]["start"]))
    skill = open(skill_path).read()
    tmpl = string.Template(open(os.path.join(HERE, "prompts", "replay.md")).read())
    for i, s in enumerate(ss):
        sdir = os.path.join(pdir, f"step-{i:02d}")
        mp = os.path.join(sdir, "meta.json")
        if os.path.exists(mp) and not json.load(open(mp)).get("error"):
            carried = {os.path.relpath(os.path.join(d, f), os.path.join(sdir, "docs")): open(os.path.join(d, f)).read()
                       for d, _, fs in os.walk(os.path.join(sdir, "docs")) for f in fs}
            continue
        os.makedirs(sdir, exist_ok=True)
        nxt = ts(s["end"]) + datetime.timedelta(days=1)  # later commits belong to later work
        nxt = min(nxt, ts(ss[i + 1]["start"])) if i + 1 < len(ss) else nxt
        sha = pick_commit(cs, ts(s["start"]), ts(s["end"]), nxt)
        head = materialize(repo, sha, carried)
        prompts, files, commands, final = digest(s, name)
        text = tmpl.substitute(operation=operation(s, carried), agents_md=carried.get("AGENTS.md", "(no AGENTS.md yet)"),
                               agent=s["agent"], model=s.get("model"), start=s["start"][:16], end=s["end"][:16],
                               commit=sha[:10], prompts=prompts, files=files, commands=commands, final=final, skill=skill)
        res = run_agent(s, text, repo, os.path.join(sdir, "agent.log"))
        docs, touched = harvest_state(repo)
        meta = {"session": s["id"], "agent": s["agent"], "model": s.get("model"), "commit": sha, "head": head,
                "start": s["start"], "end": s["end"], "code_touched": touched, **res}
        write_step(sdir, docs, repo, meta)
        a = json.load(open(os.path.join(sdir, "a.json")))
        print(f"{name} step-{i:02d} {s['agent']:6} {s['start'][:10]} STATUS={a['lines'].get('docs/STATUS.md', '-'):>5} "
              f"AGENTS={a['lines'].get('AGENTS.md', '-'):>4} DECISIONS={a['lines'].get('docs/DECISIONS.md', '-'):>5} "
              f"${res['cost']:.2f} {res['secs']}s{' ERROR ' + str(res['error'])[:120] if res['error'] else ''}"
              f"{' CODE TOUCHED ' + str(touched[:3]) if touched else ''}", flush=True)
        if res["error"]:
            break
        carried = docs
    return pdir


def done_steps(pdir, upto=None):
    steps = sorted(d for d in os.listdir(pdir) if os.path.exists(os.path.join(pdir, d, "meta.json")))
    return steps[:upto] if upto else steps


def retention(pdir, facts_path, upto=None):
    """Share of facts (from the real final docs) recoverable from the last replay step's docs."""
    steps = done_steps(pdir, upto)
    sdir = os.path.join(pdir, steps[-1])
    facts = json.load(open(facts_path))["facts"]
    listing = "\n".join(f"{i}. [{f['category']}] {f['fact']}" for i, f in enumerate(facts, 1))
    text = ("The directory `docs/` holds a project's memory documentation. For each numbered fact below, decide whether "
            "a new agent reading only these docs could recover it: present (stated), partial (incomplete or only "
            "implied), absent, or contradicted (docs say otherwise). Give the file in `where` when present/partial/"
            f"contradicted. Read all docs first.\n\n{listing}")
    cmd = ["claude", "-p", "--safe-mode", "--no-session-persistence", "--model", "claude-opus-5-5", "--output-format",
           "json", "--tools", "Read,Grep,Glob", "--allowedTools", "Read,Grep,Glob", "--json-schema", json.dumps(RETENTION)]
    r = subprocess.run(cmd, input=text, cwd=sdir, capture_output=True, text=True, timeout=3600)
    d = json.loads(r.stdout)
    verdicts = d["structured_output"]["facts"]
    score = sum({"present": 1, "partial": 0.5}.get(v["verdict"], 0) for v in verdicts) / max(len(facts), 1)
    res = {"step": steps[-1], "score": round(score, 3), "verdicts": verdicts, "cost": d.get("total_cost_usd")}
    json.dump(res, open(os.path.join(sdir, "retention.json"), "w"), indent=1)
    return res


def judge_step(pdir, name, upto=None):
    """Layer-B judge of the last replay step, against the baseline SKILL.md and rubric (same standard for every
    skill version under test)."""
    import judge
    steps = done_steps(pdir, upto)
    sdir = os.path.join(pdir, steps[-1])
    md5 = os.path.basename(os.path.dirname(pdir))
    filt = os.path.join(WORK, md5, name, "filtered")
    meta = json.load(open(os.path.join(sdir, "meta.json")))
    jdir = os.path.join(sdir, "judge")
    shutil.rmtree(jdir, ignore_errors=True)
    shutil.copytree(os.path.join(sdir, "docs"), os.path.join(jdir, "docs"))
    os.makedirs(os.path.join(jdir, "code"))
    arch = subprocess.run(["git", "-C", filt, "archive", meta["commit"]], capture_output=True, check=True).stdout
    subprocess.run(["tar", "x", "-C", os.path.join(jdir, "code")], input=arch, check=True)
    with open(os.path.join(jdir, "gitlog.txt"), "w") as f:
        f.write(git(filt, "log", meta["commit"], "--date=iso-strict", "--format=%x1e%H%x09%P%x09%ad%x09%an%x09%s", "--numstat"))
    index = ["This is a replay: the docs were produced by re-running memory maintenance once per real session "
             "(step-00 = init, later steps = update). No session digests or events.jsonl exist; attribute op from the step list."]
    for st in steps:
        m, a = (json.load(open(os.path.join(pdir, st, x))) for x in ("meta.json", "a.json"))
        index.append(f"- {st} {m['agent']} {m['model']} {m['start'][:16]} commit={m['commit'][:8]} lines after: "
                     + ", ".join(f"{k.split('/')[-1]}={v}" for k, v in a["lines"].items()))
    a = json.load(open(os.path.join(sdir, "a.json")))
    res, cost = judge.claude(judge.prompt("judge.md", project=name, layer_a=json.dumps(a, indent=1),
                                          session_index="\n".join(index)), jdir, judge.FINDINGS, os.path.join(sdir, "b.log"))
    json.dump(res, open(os.path.join(sdir, "b.json"), "w"), indent=1, ensure_ascii=False)
    return res, cost


def compare(out):
    """Old-vs-new table per project against the win criteria."""
    rows = {}
    common = {}  # compare skills over the same number of sessions
    for md5 in os.listdir(out):
        for name in (os.listdir(os.path.join(out, md5)) if os.path.isdir(os.path.join(out, md5)) else []):
            n = len(done_steps(os.path.join(out, md5, name)))
            common[name] = min(common.get(name, n), n)
    for md5 in sorted(os.listdir(out)):
        if not os.path.isdir(os.path.join(out, md5)):
            continue
        for name in sorted(os.listdir(os.path.join(out, md5))):
            pdir = os.path.join(out, md5, name)
            steps = done_steps(pdir, common[name])
            a = [json.load(open(os.path.join(pdir, s, "a.json"))) for s in steps]
            meta = [json.load(open(os.path.join(pdir, s, "meta.json"))) for s in steps]
            ln = lambda f: [x["lines"].get(f, 0) for x in a]
            bp = os.path.join(pdir, steps[-1], "b.json")
            sev, bloat = {k: 0 for k in "HML"}, 0
            for f in (json.load(open(bp))["findings"] if os.path.exists(bp) else []):
                sev[f["severity"]] += 1
                bloat += f["severity"] in "HM" and f["rule_id"] in BLOAT_RULES
            rp = os.path.join(pdir, steps[-1], "retention.json")
            rows.setdefault(name, []).append({
                "skill": md5, "steps": len(steps), "max_STATUS": max(ln("docs/STATUS.md")), "max_AGENTS": max(ln("AGENTS.md")),
                "over_cap_steps": sum(1 for s, g in zip(ln("docs/STATUS.md"), ln("AGENTS.md")) if s > 120 or g > 120),
                "final": {f.split("/")[-1]: v for f, v in a[-1]["lines"].items()},
                "dup": a[-1].get("dup_lines", 0), "diary": (a[-1].get("status") or {}).get("dated_lines", 0),
                "done": (a[-1].get("status") or {}).get("done_items", 0),
                "B": sev if os.path.exists(bp) else None, "bloat": bloat if os.path.exists(bp) else None,
                "retention": json.load(open(rp))["score"] if os.path.exists(rp) else None,
                "cost": round(sum(m.get("cost") or 0 for m in meta), 2), "code_touched": sum(1 for m in meta if m["code_touched"])})
    for name, rs in rows.items():
        print(f"\n== {name}")
        print(f"{'skill':9} {'steps':>5} {'maxST':>6} {'maxAG':>6} {'dup':>4} {'diary':>5} {'done':>4} {'bloat':>5} {'B H/M/L':>9} {'retain':>7} {'cost':>7} {'code!':>5}  final lines")
        for r in rs:
            b = "/".join(str(r["B"][k]) for k in "HML") if r["B"] else "-"
            print(f"{r['skill']:9} {r['steps']:5} {r['max_STATUS']:6} {r['max_AGENTS']:6} {r['dup']:4} {r['diary']:5} {r['done']:4} {r['bloat'] if r['bloat'] is not None else '-':>5} {b:>9} "
                  f"{r['retention'] if r['retention'] is not None else '-':>7} {r['cost']:7} {r['code_touched']:5}  {r['final']}")
    json.dump(rows, open(os.path.join(out, "compare.json"), "w"), indent=1)


def main(argv):
    if argv[:1] == ["--compare"]:
        return compare(argv[1])
    hroot, out = argv[0], argv[1]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in argv[2:])
    if os.path.abspath(out).startswith(check.REPO + os.sep):
        sys.exit("refusing to write replay output inside the repo")
    for spec in opt["projects"].split(","):
        name, _, lim = spec.partition(":")
        lim = int(lim) if lim else None
        if "score-only" in opt:  # score existing steps, replay nothing new
            md5 = hashlib.md5(open(opt["skill"], "rb").read()).hexdigest()[:8]
            pdir = os.path.join(out, md5, name)
        else:
            pdir = replay_project(hroot, out, opt["skill"], name, lim)
        facts = os.path.join(os.path.dirname(os.path.normpath(hroot)), "results", name, "facts.json")
        if "retention" in opt and os.path.exists(facts):
            r = retention(pdir, facts, lim)
            print(f"{name} retention {r['score']} at {r['step']}")
        if "judge" in opt:
            res, cost = judge_step(pdir, name, lim)
            print(f"{name} judge H/M/L " + "/".join(str(sum(f["severity"] == k for f in res["findings"])) for k in "HML") + f" ${cost:.2f}")


def selftest():
    u = datetime.timezone.utc
    d = lambda h: datetime.datetime(2026, 10, 1, h, tzinfo=u)
    cs = [(d(1), "a"), (d(5), "b"), (d(9), "c")]
    assert pick_commit(cs, d(2), d(4), d(8)) == "b"  # committed after the session, before the next one
    assert pick_commit(cs, d(2), d(6), d(7)) == "b"  # nothing in the gap: latest before end
    assert pick_commit(cs, d(0), d(0), d(1)) == "a"  # nothing before: earliest
    assert is_mem("docs/STATUS.md") and is_mem("CLAUDE.md") and not is_mem("docs/faq/a.md") and not is_mem("src/x.md")
    s = {"skill_calls": [{"skill": "project-memory", "args": "initialize shared project memory"}], "user_prompts": []}
    assert "initialize" in operation(s, {})
    assert "update" in operation(s, {"AGENTS.md": "x"})
    assert "protocol" in operation({"skill_calls": [], "user_prompts": []}, {"AGENTS.md": "x"})
    assert "initialize" in operation({"skill_calls": [], "user_prompts": [], "explicit_ts": "t"}, {})
    print("selftest ok")


if __name__ == "__main__":
    selftest() if sys.argv[1:2] == ["--selftest"] else main(sys.argv[1:])
