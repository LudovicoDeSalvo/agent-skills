#!/usr/bin/env python3
"""Layer B: LLM judge of harvested project-memory docs, worst-edit review, fact extraction, report.

    python3 judge.py HARVEST RESULTS [--only=p1,p2] [--steps=b,edits,facts,report] [--facts=p1,p2] [--force]
    --facts: projects to extract fact lists for (the ones replay.py will replay)

Needs layer A first (check.py HARVEST RESULTS). Each call is an isolated `claude -p --safe-mode` confined to the
project's harvest dir with read-only tools. Outputs are cached per project; --force recomputes.
"""
import collections, concurrent.futures, glob, json, os, string, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SKILL = os.path.join(HERE, "SKILL.baseline.md")  # rubric line refs point into this version (md5 9eb16f55)
INSTALLED = "2026-09-10T07:01"
MODEL = "claude-opus-5-5"
OPS = ["init", "update", "protocol", "pre-skill", "unknown"]

FINDINGS = {"type": "object", "required": ["summary", "strengths", "findings"], "properties": {
    "summary": {"type": "string"},
    "strengths": {"type": "array", "items": {"type": "string"}},
    "findings": {"type": "array", "items": {"type": "object", "required": [
        "rule_id", "skill_line", "file", "severity", "op", "agent", "evidence", "explanation", "skill_gap", "suggested_rule_change"],
        "properties": {"rule_id": {"type": "string"}, "skill_line": {"type": "string"}, "file": {"type": "string"},
                       "severity": {"enum": ["H", "M", "L"]}, "op": {"enum": OPS},
                       "agent": {"enum": ["claude", "codex", "both", "unknown"]}, "evidence": {"type": "string"},
                       "explanation": {"type": "string"}, "skill_gap": {"type": "boolean"},
                       "suggested_rule_change": {"type": "string"}}}}}}
EDITS = {"type": "object", "required": ["edits"], "properties": {"edits": {"type": "array", "items": {
    "type": "object", "required": ["index", "verdict", "rule_ids", "skill_gap", "explanation", "should_have"],
    "properties": {"index": {"type": "integer"}, "verdict": {"enum": ["ok", "violation"]},
                   "rule_ids": {"type": "array", "items": {"type": "string"}}, "skill_gap": {"type": "boolean"},
                   "explanation": {"type": "string"}, "should_have": {"type": "string"}}}}}}
FACTS = {"type": "object", "required": ["facts"], "properties": {"facts": {"type": "array", "items": {
    "type": "object", "required": ["category", "fact", "source"],
    "properties": {"category": {"enum": ["objective", "state", "command", "component", "invariant", "decision",
                                         "blocker", "hazard"]},
                   "fact": {"type": "string"}, "source": {"type": "string"}}}}}}


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def numbered(p):
    return "".join(f"{i:4d}  {l}" for i, l in enumerate(read(p).splitlines(True), 1))


def prompt(name, **kw):
    return string.Template(read(os.path.join(HERE, "prompts", name))).substitute(
        skill=numbered(SKILL), rubric=read(os.path.join(HERE, "rubric.md")), installed=INSTALLED, **kw)


def claude(text, cwd, schema, log, tools="Read,Grep,Glob"):
    cmd = ["claude", "-p", "--safe-mode", "--no-session-persistence", "--model", MODEL, "--output-format", "json"]
    cmd += ["--tools", tools or ""] + (["--allowedTools", tools] if tools else [])
    if schema:
        cmd += ["--json-schema", json.dumps(schema)]
    r = subprocess.run(cmd, input=text, cwd=cwd, capture_output=True, text=True, timeout=3600)
    with open(log, "w") as f:
        f.write(r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr else ""))
    try:
        d = json.loads(r.stdout)
    except ValueError:
        raise RuntimeError(f"claude failed ({r.returncode}): {r.stderr[-500:]}")
    out = d.get("structured_output") if schema else d.get("result")
    if d.get("is_error") or out is None:
        raise RuntimeError(f"claude error: {str(d.get('result'))[:500]}")
    return out, d.get("total_cost_usd") or 0


def sessions(hdir):
    out = [json.load(open(f)) for f in glob.glob(os.path.join(hdir, "sessions", "*.json"))]
    return sorted(out, key=lambda s: s.get("start") or "")


def session_index(hdir):
    lines = []
    for s in sessions(hdir):
        mem = collections.defaultdict(lambda: [0, 0])
        for w in s["memory_writes"]:
            mem[w["file"].split("/")[-1]][0] += w.get("plus") or 0
            mem[w["file"].split("/")[-1]][1] += w.get("minus") or 0
        first = (s["user_prompts"][0]["text"] if s["user_prompts"] else "").replace("\n", " ")[:160]
        pre = " PRE-SKILL" if (s.get("start") or "") < INSTALLED else ""
        lines.append(f"- {s['agent']} `{s['file']}` {(s.get('start') or '')[:16]}{pre} model={s.get('model')} "
                     f"prompts={len(s['user_prompts'])} explicit={bool(s.get('explicit_ts'))} "
                     f"mem={dict((k, f'+{a}/-{b}') for k, (a, b) in mem.items())} | {first}")
    return "\n".join(lines) or "(no sessions recorded)"


def layer_a(rdir):
    a = json.load(open(os.path.join(rdir, "a.json")))
    if isinstance(a.get("git"), dict) and "curve" in a["git"]:
        a["git"]["curve"] = {f: [c[0], c[-1]] for f, c in a["git"]["curve"].items()}  # first/last point only
    return json.dumps(a, indent=1)


def worst_edits(hdir, n=5):
    evs = [json.loads(l) for l in open(os.path.join(hdir, "events.jsonl"))]
    evs = [e for e in evs if (e.get("ts") or "") >= INSTALLED and e.get("plus") is not None]
    evs.sort(key=lambda e: (e.get("plus") or 0) - (e.get("minus") or 0), reverse=True)
    status = [e for e in evs if e["file"] == "docs/STATUS.md"][:2]
    pick = status + [e for e in evs if e not in status][: n - len(status)]
    by_id = {(s["agent"], s["id"]): s for s in sessions(hdir)}
    blocks = []
    for i, e in enumerate(pick, 1):
        s = by_id.get((e["agent"], e["session"]), {})
        w = next((w for w in s.get("memory_writes", []) if w["ts"] == e["ts"] and w["file"] == e["file"]), {})
        before = [p for p in s.get("user_prompts", []) if (p["ts"] or "") <= (e["ts"] or "")]
        blocks.append(f"### Edit {i} — {e['file']} +{e['plus']}/-{e['minus']} agent={e['agent']} model={e.get('model')} "
                      f"trigger={e.get('trigger')} tool={e.get('tool')} kind={e.get('kind')} session={s.get('file')} ts={e['ts']}\n"
                      f"Preceding user prompt: {(before[-1]['text'] if before else '(none)')[:1500]}\n"
                      f"```diff\n{(w.get('patch') or '(patch unavailable)')[:12000]}\n```")
    return pick, "\n\n".join(blocks)


def run_project(step, name, hroot, rroot, force):
    hdir, rdir = os.path.join(hroot, name), os.path.join(rroot, name)
    out = os.path.join(rdir, {"b": "b.json", "edits": "edits.json", "facts": "facts.json"}[step])
    if os.path.exists(out) and not force:
        return name, 0, "cached"
    log = out[:-5] + ".log"
    if step == "b":
        res, cost = claude(prompt("judge.md", project=name, layer_a=layer_a(rdir), session_index=session_index(hdir)),
                           hdir, FINDINGS, log)
    elif step == "edits":
        pick, blocks = worst_edits(hdir)
        if not pick:
            return name, 0, "no edits"
        res, cost = claude(prompt("edit-review.md", project=name, n=len(pick), edits=blocks), hdir, EDITS, log)
        for e in res["edits"]:
            if 1 <= e["index"] <= len(pick):
                e["event"] = pick[e["index"] - 1]
    else:
        res, cost = claude(prompt("facts.md", project=name), hdir, FACTS, log)
    with open(out, "w") as f:
        json.dump(res, f, indent=1, ensure_ascii=False)
    return name, cost, "ok"


def report(hroot, rroot):
    rows, gaps, edits = [], [], []
    sev = collections.defaultdict(collections.Counter)
    by_op, by_agent = collections.Counter(), collections.Counter()
    for name in sorted(os.listdir(rroot)):
        bp = os.path.join(rroot, name, "b.json")
        if not os.path.exists(bp):
            continue
        b, a = json.load(open(bp)), json.load(open(os.path.join(rroot, name, "a.json")))
        c = collections.Counter(f["severity"] for f in b["findings"])
        rows.append(f"| {name} | {a['lines'].get('docs/STATUS.md', '-')} | {a['lines'].get('docs/DECISIONS.md', '-')} | "
                    f"{a['lines'].get('AGENTS.md', '-')} | {c['H']} | {c['M']} | {c['L']} | {b['summary'][:160]} |")
        for f in b["findings"]:
            sev[f["rule_id"]][f["severity"]] += 1
            by_op[(f["op"], f["severity"])] += 1
            by_agent[(f["agent"], f["severity"])] += 1
            if f["skill_gap"]:
                gaps.append({"project": name, **f})
        ep = os.path.join(rroot, name, "edits.json")
        if os.path.exists(ep):
            edits += [{"project": name, **e} for e in json.load(open(ep))["edits"]]
    proj_per_rule = collections.defaultdict(set)
    for name in os.listdir(rroot):
        bp = os.path.join(rroot, name, "b.json")
        if os.path.exists(bp):
            for f in json.load(open(bp))["findings"]:
                proj_per_rule[f["rule_id"]].add(name)
    rule_rows = sorted(sev, key=lambda r: (-len(proj_per_rule[r]), -sev[r]["H"]))
    md = ["# project-memory eval report\n", f"SKILL.md md5 9eb16f55 · judge {MODEL}\n",
          "## Per project\n", "| project | STATUS | DECISIONS | AGENTS | H | M | L | judge summary |", "|---|---|---|---|---|---|---|---|",
          *rows, "\n## Findings by rule\n", "| rule | projects | H | M | L |", "|---|---|---|---|---|",
          *[f"| {r} | {len(proj_per_rule[r])} | {sev[r]['H']} | {sev[r]['M']} | {sev[r]['L']} |" for r in rule_rows],
          "\n## By operation / agent (H+M)\n",
          "| op | H | M |", "|---|---|---|", *[f"| {o} | {by_op[(o, 'H')]} | {by_op[(o, 'M')]} |" for o in OPS],
          "", "| agent | H | M |", "|---|---|---|",
          *[f"| {g} | {by_agent[(g, 'H')]} | {by_agent[(g, 'M')]} |" for g in ["claude", "codex", "both", "unknown"]],
          "\n## Worst edits\n", "| project | file | +/- | agent | trigger | verdict | rules | gap | should have |", "|---|---|---|---|---|---|---|---|---|",
          *[f"| {e['project']} | {e.get('event', {}).get('file')} | +{e.get('event', {}).get('plus')}/-{e.get('event', {}).get('minus')} | "
            f"{e.get('event', {}).get('agent')} | {e.get('event', {}).get('trigger')} | {e['verdict']} | {', '.join(e['rule_ids'])} | "
            f"{'yes' if e['skill_gap'] else ''} | {e['should_have'][:200]} |" for e in edits]]
    synth_in = json.dumps({"skill_gap_findings": gaps, "edit_reviews": edits,
                           "rule_counts": {r: dict(sev[r], projects=len(proj_per_rule[r])) for r in rule_rows}},
                          ensure_ascii=False)[:400000]
    text = (f"You are improving SKILL.md (below, with line numbers) from an evaluation of its real output across "
            f"{len(rows)} projects. Input JSON holds findings the judges flagged as skill gaps, reviews of the "
            f"largest edits, and rule counts. Write Markdown with: `## Failure patterns` — at most 8 patterns ranked by "
            f"impact (projects affected × severity), each with: what happens, evidence (projects, counts), the SKILL.md "
            f"lines responsible and why the wording fails, and `Proposed change:` with exact replacement/added wording. "
            f"Then `## Keep` — behaviors that work and must survive a rewrite. Be concrete and brief; no preamble.\n\n"
            f"INPUT:\n{synth_in}\n\nSKILL.md:\n```\n{numbered(SKILL)}\n```")
    synth, cost = claude(text, rroot, None, os.path.join(rroot, "report.log"), tools=None)
    with open(os.path.join(rroot, "report.md"), "w") as f:
        f.write("\n".join(md) + "\n\n" + synth + "\n")
    return cost


def main(argv):
    hroot, rroot = argv[0], argv[1]
    opt = dict(a[2:].split("=", 1) if "=" in a else (a[2:], "1") for a in argv[2:])
    steps = opt.get("steps", "b,edits,facts,report").split(",")
    names = [n for n in sorted(os.listdir(hroot)) if os.path.isdir(os.path.join(hroot, n))]
    if "only" in opt:
        names = [n for n in names if n in opt["only"].split(",")]
    total = 0.0
    for step in [s for s in steps if s != "report"]:
        todo = [n for n in names if step != "facts" or n in opt.get("facts", "").split(",")]
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            futs = {ex.submit(run_project, step, n, hroot, rroot, "force" in opt): n for n in todo}
            for fu in concurrent.futures.as_completed(futs):
                try:
                    n, cost, status = fu.result()
                    total += cost
                    print(f"{step:6} {n:24} {status:8} ${cost:.2f}", flush=True)
                except Exception as e:
                    print(f"{step:6} {futs[fu]:24} FAILED   {e}", flush=True)
    if "report" in steps:
        total += report(hroot, rroot)
        print(f"report → {os.path.join(rroot, 'report.md')}")
    print(f"total ${total:.2f}")


if __name__ == "__main__":
    main(sys.argv[1:])
