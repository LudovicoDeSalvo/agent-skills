Working directory = harvest of project `$project`: `docs/` (current memory docs), `code/`, `gitlog.txt`.
Extract the facts a fresh agent session must be able to recover from this project's memory to continue work
safely: current objective and state, how to build/run/test/deploy (commands + working dir), key components and
invariants, consequential decisions (with their one-line rationale), active blockers and open questions,
hazards (production systems, data that must not be touched). Verify against `code/` and `gitlog.txt` when cheap;
drop facts that are stale or contradicted. At most 40 facts, most important first. Each fact must be one
self-contained sentence checkable against a document ("The deploy target is X", not "see deploy section").
Output only the JSON required by the schema.
