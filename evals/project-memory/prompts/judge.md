You are auditing the Markdown "project memory" that coding agents maintained for one project while following
the instructions in SKILL.md (reproduced below with line numbers). Your job is to find where the produced docs
violate SKILL.md, and — more importantly — why: which instruction was ignored, ambiguous, or missing.

Working directory = the harvest of project `$project`:
- `docs/` — the memory files as they are now (README, AGENTS, CLAUDE, CHANGELOG, docs/*.md).
- `code/` — project source (secret-scrubbed; `<REDACTED…>`, `<email>` are scrubber marks, not doc defects).
- `gitlog.txt` — git log with numstat (absent when not a git repo). `meta.json` — git head/status.
- `sessions/*.json` — digests of agent sessions: user prompts, memory_writes (with patch + trigger), other files changed, commands.
- `events.jsonl` — one line per memory-file write: file, ts, agent, trigger (explicit = skill was invoked earlier in that
  session; user-asked = last user prompt mentioned docs/memory; protocol = neither, agent followed AGENTS.md on its own).
Writes before $installed predate the skill and must not be blamed on it (mark op `pre-skill`).

Mechanical (layer A) results already computed — do not repeat them as findings unless you add the cause:
```json
$layer_a
```

Session index:
$session_index

Rubric (cite rule ids):
$rubric

SKILL.md:
```
$skill
```

Method: read every memory doc fully. Check claims against `code/`, `gitlog.txt`, and session evidence; sample, do not
audit all code. For each problem decide which operation produced it (init / update / protocol / pre-skill) using
events.jsonl and session patches, and which agent. Prefer few well-evidenced findings over many weak ones; merge
repeats of the same defect into one finding. Also note what works well (strengths) so a rewrite does not lose it.
`skill_gap` = true when SKILL.md's wording plausibly allowed or encouraged the defect (vague, conflicting, missing);
then give `suggested_rule_change` as concrete SKILL.md wording. Quote evidence briefly (<300 chars, paraphrase
customer data). Output only the JSON object required by the schema.
