# project-memory rubric

Each rule restates a requirement of `skills/project-memory/SKILL.md`; `L` = line(s) in SKILL.md at md5 9eb16f55.
Severity guide: **H** misleads or blocks a future session / leaks data; **M** wastes reader context or erodes trust; **L** cosmetic.
`GAP` = harmful pattern no rule covers, or a rule too vague to have prevented it.

| ID | L | Rule |
| --- | --- | --- |
| R-01 | 30 | Implementation claims grounded in code/config; test claims in observed results. |
| R-02 | 30, 76 | Implemented behavior separated from plans/assumptions; planned/inferred/historical/unverified labeled. |
| R-03 | 30, 58, 172 | No rationale reconstructed from code and presented as a known decision; no invented dates. |
| R-04 | 31, 76 | No credentials, tokens, personal records, production data, or full env-file contents. |
| R-05 | 27, 52 | One canonical home per fact; existing equivalents reused; other files link instead of duplicating. |
| R-06 | 50 | No empty boilerplate, invented history, or invented roadmap. |
| R-07 | 52 | Project docs relative and portable; no machine-specific skill install paths; useful without the skill. |
| R-08 | 60, 68, 71-79 | AGENTS.md has one `## Project memory` section with the protocol adapted to real paths, not fenced. |
| R-09 | 61, 64 | CLAUDE.md = `@AGENTS.md` import + Claude-specific content; no duplicate loading, cycles, or doc imports. |
| R-10 | 74, 82, 136 | AGENTS.md concise (~60-120 lines), facts linked not stored; no invented policies or constraints. |
| R-11 | 58, 156-172 | DECISIONS holds consequential decisions with known rationale in the template; accepted only with evidence; supersession linked. |
| R-12 | 77, 174-205 | STATUS is a current snapshot (~one screen, <120 lines per task) in the handoff structure; stale details replaced. |
| R-13 | 205 | STATUS holds no transcripts, long command logs, or chronological diary. |
| R-14 | 111 | After completion obsolete steps removed; "no active task" recorded when true; no invented follow-up. |
| R-15 | 112 | Several active tasks → labeled sections or task files with a short index; one task not overwriting another. |
| R-16 | 110 | Status date changes only with substantive content; branch/base commit recorded when it identifies unfinished work. |
| R-17 | 109 | Failed attempts recorded as symptom/scope/result/retry-condition, not repetitive logs. |
| R-18 | 106 | Focused edits, not whole-file regenerations. |
| R-19 | 108 | Checkpoint at milestones/discoveries; not every file after every tool call. |
| R-20 | 113 | Repeated update with no new evidence leaves files unchanged. |
| R-21 | 77, 207-209 | CHANGELOG: notable product changes only, existing convention or Unreleased; no invented versions/dates; no memory-refresh or task-progress entries. |
| R-22 | 119-127 | README: purpose, scope, supported vs planned capabilities, quick start, doc links; no duplicated long runbooks. |
| R-23 | 138-140 | TREE: selective map of important paths; no generated inventories, line numbers, or symbol listings. |
| R-24 | 142-152 | ARCHITECTURE: current vs target separated; no copied code or exhaustive API inventories; links to rationale. |
| R-25 | 215 | Local links and referenced paths exist (future paths labeled). |
| R-26 | 216 | Documented commands exist where claimed, with correct working directory. |
| R-27 | 196-198 | Validation lists commands actually run with results; checks not run identified. |
| R-28 | 107 | No reset/stash/stage/commit/push/branch change merely to save memory. |
| R-29 | 26, 112 | Scope respected: subproject not expanded to parent; other contributors' tasks and user-written docs preserved. |
| R-30 | 221 | Final diff free of duplication, placeholder residue, timestamp churn, sensitive content, out-of-scope edits. |
