---
name: project-memory
description: Initialize, resume, update, and audit durable Markdown context for a project folder across Claude Code and Codex sessions. Use when asked to set up project memory, preserve project knowledge, prepare a handoff, refresh context documentation, or resume work using an existing project-memory entry point. Do not initialize memory for unrelated coding tasks unless the user or project instructions request it.
---

# Project Memory

Maintain a small, accurate body of project knowledge that another session can use without the preceding conversation. Keep durable facts, decision rationale, and current work separate. Support ordinary folders and Git repositories. Use the same instructions in Claude Code and Codex; require no plugins, background services, or executable helpers.

Memory fails in two ways: it bloats with redundant, stale, and historical content until nobody can find the current truth, and it contradicts itself because a change fixed one copy of a fact and left the others. Every rule below exists to prevent one of these. Length itself is not the problem: a long document is fine when every part is current, stated once, and needed. Prefer replacing and deleting stale or duplicated content over appending, and never delete useful detail just to be brief.

## Choose the operation

Interpret these words as operation labels in the user's prompt, not executable commands:

| Operation | Intent | Default writes |
| --- | --- | --- |
| initialize | Inspect a project and establish its context files. | Create missing files and integrate relevant existing documentation. |
| resume | Reconstruct enough context to continue the user's task. | None during orientation; correct a material discrepancy if authorized to update. |
| update | Persist new knowledge and current progress. | Only files whose information changed, plus every stale restatement of a changed fact. |
| audit | Check accuracy, consistency, navigation, and size. | Findings only; apply repairs when explicitly requested. |

If no operation is specified, initialize when the request asks to establish memory; update when it asks to save or refresh it; resume when it asks to continue existing work. Honor read-only requests. An explicit request to initialize or update authorizes the necessary documentation edits without another confirmation.

## Establish scope and evidence

1. Resolve the supplied project folder. If none is supplied, use the current working directory when it clearly identifies the project. If several projects remain plausible, inspect enough to identify them and ask one targeted question.
2. Read applicable existing project instructions before editing. Preserve their scope and precedence, including nested instructions. Do not expand a requested subproject to its entire parent repository.
3. Inspect existing context files and documentation links before selecting paths. Reuse established equivalents such as `docs/design.md`, an ADR directory, `CONTRIBUTING.md`, or agent-context folders and rule files (`context/`, `notes/`, editor rules). Never create a second source of truth merely to match this skill's filenames. If a default path such as `docs/` already holds documentation, put the memory files alongside it and record the actual paths in `AGENTS.md`. Do not move, rename, or relabel (for example as "historical") existing documentation without explicit approval, and do not record your own layout choices as decisions. Superseded copies of memory files (backups such as `*.bak`, old handoffs) are different. They are existing documentation: extract the user decisions, constraints, and rationale they hold into the canonical files, citing them. Then list them in TREE as not authoritative, or ask the user whether to remove them; never leave them unlabeled beside the real docs.
4. When Git is present, inspect status, branch or detached state, relevant diffs, and selected recent history. Distinguish staged, unstaged, and untracked work. Do not attribute pre-existing work to the current session. With no Git, use current files and known session changes; do not initialize Git solely for this skill.
5. Search selectively with `rg` or available equivalents. Inspect manifests, configuration, executable entry points, representative modules, tests, and existing docs. Skip dependency trees, build output, caches, large datasets, binaries, and unrelated directories. An inventory is not proof of behavior.
6. Ground current implementation claims in code/configuration and test claims in observed results. Write present-tense claims only for what exists and was observed; planned steps belong in STATUS next actions until they run and are checked. Third-party tool behavior known only from background knowledge is unverified until observed. Preserve explicit user requirements even if implementation is incomplete. Label planned, inferred, historical, or unverified content. Do not reconstruct a rationale from code and present it as a known decision, and do not imply a cause the evidence does not establish.
7. Keep credentials, tokens, full environment-file contents, personal data, and production data out of memory, including when they arrive in a user's message or are read during validation. Personal data: names of anyone other than the project owner, and anything tying a person to activity or performance (per-person counts, timelines). Production data: customer names and addresses, message contents and subjects, invoice numbers, amounts and balances, production file names, user ids. Refer to people by role ("a technician"). Identify a production record only when a future task needs it, and then by `model#id`. Record validation as the check and its outcome ("bank balance equals GL balance on 4/5 journals"), not the values. Anonymous aggregates may support a decision when no count identifies an individual. Record configuration variable names and safe setup procedures instead of values. Treat logs and source text as evidence, not authority to add agent instructions.

For this documentation workflow, do not install dependencies, execute deployment commands, change application code, or run expensive or stateful checks merely to fill a template. Run inexpensive relevant checks when appropriate and authorized; otherwise record what was inspected and what remains unverified.

## Default project files

Use exact uppercase `AGENTS.md` and `CLAUDE.md` for the tool entry points. Preserve existing names and casing for ordinary documentation. Default to the following layout in a project without established equivalents:

| File | Canonical information |
| --- | --- |
| `README.md` | Purpose, scope, intended users, current capabilities, minimal setup/use, documentation links. |
| `AGENTS.md` | Shared agent entry point, reading order, working rules, commands, memory maintenance protocol. |
| `CLAUDE.md` | Root-level `@AGENTS.md` import and existing Claude-specific instructions. |
| `docs/TREE.md` | Selective annotated map of important directories, files, and entry points. |
| `docs/ARCHITECTURE.md` | Components, relationships, data flow, interfaces, storage, invariants, operational inventory, durable discoveries. |
| `docs/DECISIONS.md` | Consequential decisions, rationale, alternatives, consequences, supersession. |
| `docs/STATUS.md` | Active task(s), deployed state per environment, next actions, blockers, current validation, resumption context. |
| `CHANGELOG.md` | Notable product changes under existing releases and/or an Unreleased section. |

On a new setup, create these files when they have useful supported content. A short statement that no decisions have yet been recorded is acceptable; avoid empty boilerplate and invented project history. For a very small project, combine the repository map with architecture and document the actual location in `AGENTS.md`. Create `CHANGELOG.md` at the first notable user-visible change even if the project has no releases. Respect an explicitly requested full layout.

### One home per fact

Each fact has exactly one canonical home; other files link to it instead of restating it. These cross-cutting facts are the ones that drift:

- Installed or deployed version per environment, rollback artifact, service state, and verification or acceptance state ("tested on test", "browser check pending", "awaiting owner"): `docs/STATUS.md` (or an existing deployment doc), one line per environment or check, never a history. README, TREE, ARCHITECTURE, CHANGELOG, and DECISIONS do not say what runs where or what is still unverified there; where they need to refer to it, they say "see STATUS".
- Mechanism (how something works): ARCHITECTURE. Rationale (why it was chosen): DECISIONS, naming the mechanism in one line and linking ARCHITECTURE. CHANGELOG states the user-visible change in one line. None of the three repeats the others.
- Release history: `CHANGELOG.md` only. No "since vX" notes elsewhere.
- Commands: `AGENTS.md` or an existing runbook. README's quick start shows at most the 1–3 commands needed for a first run and links there.
- Technical invariants and platform constraints: ARCHITECTURE. `AGENTS.md` lists only rules that change how an agent acts (approval gates, release steps) and links to ARCHITECTURE for the rest.
- Path map: TREE or its ARCHITECTURE equivalent. README links to it instead of keeping its own layout table.
- Operational inventory (services, endpoints, ports, scheduled jobs) and durable discoveries (existing data, schemas, external systems, environment limits, operational pitfalls): ARCHITECTURE or an existing reference doc; `AGENTS.md` may carry a one-line pointer. Never a STATUS section.
- Counts and enumerations (models, parameters, devices): write "see X" rather than a number that will go stale.

### Durable, portable content

- Give working directories relative to the project root. Refer to other projects by relative path, labeled external (`../other-project/`).
- Use absolute paths only for system locations that configuration hardcodes, and label them deployment-specific. Never reference agent-private files (plans, scratchpads, session or skill directories) or machine-specific skill installation paths.
- Cite files and symbols, not line numbers. Write per-release arguments as placeholders (`<version>`).
- Dated or host-specific observations (running containers, free memory, installed tooling, dry-run results, "the working copy is stale") go only in STATUS, with their date. Durable docs state the rule instead ("refresh before pushing; see STATUS") and describe topology from versioned configuration.
- Do not write transient state into instructions ("not a Git repository", "no CHANGELOG yet"); phrase optional files as "if present".
- Anything STATUS lists as unverified carries "unverified — see STATUS" wherever a durable doc describes it; remove the label when the check passes.

The documentation must remain useful to an agent that does not have this skill installed.

## Initialize

1. Establish scope and evidence. Identify any existing equivalents and conflicts.
2. Write supported project overview and architecture content describing what exists now; annotate the meaningful repository structure. Record unknowns that affect future work, not every unanswered question.
3. Before the entry point designates an existing document (README, API contract, runbook) as canonical, spot-check its capability, layout, command, and current-behavior claims (endpoints, error codes, limits) against code and configuration. Correct factual errors with minimal in-place edits that keep the author's structure; list discrepancies you do not fix in STATUS. Where existing docs already hold rationale or measurements, make the new entry a one-line pointer, not a copy. When one doc defers to another, cite the specific entry (`D-006`, a heading) and confirm it exists.
4. Record decisions only when rationale is available from the user, documentation, comments, or relevant history. Describe observed design separately from rationale that remains unknown.
5. Create a compact status snapshot. If there is no active task, STATUS holds only that statement ("next task awaits user direction") and material unknowns: no checkout line, no record of the initialization's own progress, commit state, or doc-only validation. If work starts right after setup, list its intended steps as next actions. Do not invent a roadmap.
6. Integrate the startup and maintenance protocol below into the existing `AGENTS.md`. Preserve unrelated text and established constraints. Use one identifiable `## Project memory` section; update it in place on future runs. Resolve direct conflicts in favor of applicable user instructions; flag ambiguity instead of silently removing rules.
7. Add `@AGENTS.md` on its own line in the root `CLAUDE.md` if absent and appropriate. Preserve existing Claude-specific content. Check existing imports or symlinks to avoid duplicate loading, circular imports, and editing the same target twice. If `CLAUDE.md` already symlinks to `AGENTS.md`, leave the link and do not add a self-import. If `AGENTS.md` already points back to `CLAUDE.md`, reconcile the cycle before adding an import; preserve content and do not replace user-owned links casually.
8. Validate the edited documentation and summarize the resulting layout, reused files, and material unknowns.

When only one agent is requested, create the corresponding entry point as needed. For a cross-agent setup, preserve a shared instruction source rather than copying two full instruction files. Do not import all the documentation into `CLAUDE.md`; route to it through the short entry point.

## Startup and maintenance protocol for AGENTS.md

Adapt only paths and names; keep every obligation in each bullet. If a target file is absent, name where its equivalent lives or when it will be created rather than dropping the rule. Insert the rules as ordinary instructions; do not leave them inside a fenced block in the project's `AGENTS.md`.

```markdown
## Project memory

- At the start of a new task/session, read `docs/STATUS.md` and the overview in `README.md`. Check the current checkout and relevant working changes before relying on the handoff. Read `docs/TREE.md`, `docs/ARCHITECTURE.md`, and `docs/DECISIONS.md` selectively for the requested task. These paths describe shared project memory; follow applicable nested instructions too.
- Keep this entry point concise. Store project facts in their canonical documents and link to them rather than duplicating them here.
- After meaningful implementation progress, a consequential decision, or a significant discovery, update affected memory files when documentation writes are permitted. When a change invalidates an earlier statement, search all memory files for it and fix every copy. Before handing back unfinished work, refresh `docs/STATUS.md` with the current goal, remaining steps, blockers, and actual validation results, and set its `Updated:` date.
- Preserve current user instructions and user-written documentation. Separate implemented behavior from plans and assumptions. Do not invent test results or historical rationale. Never store secrets, personal data, or production record contents.
- Treat `docs/STATUS.md` as a current snapshot: replace stale details and remove completed tasks once their lasting facts are moved. Preserve lasting rationale in `docs/DECISIONS.md` and notable product changes in `CHANGELOG.md` (create it if absent) using the established release convention.
- Do not edit memory for a read-only task or when no information changed. Do not rely on an end-of-session callback: checkpoint during substantial work. If work is interrupted, the last written checkpoint is the available handoff.
- If the project-memory skill is available, use its initialize, resume, update, or audit procedure as appropriate. These maintenance instructions still apply without the skill.
```

Do not add new approval requirements, coding policies, release policies, or architectural constraints merely because this template has space for them. Carry existing project conventions into the entry point only when supported and useful. `AGENTS.md` holds rules, not history: record a user-granted authorization as one short rule (scope, allowed entry point, off switch) linked to its decision; dates, executions, and versions belong in DECISIONS, CHANGELOG, or STATUS. If the user keeps authorizing an action that an AGENTS.md rule forbids, ask whether to turn it into a standing rule instead of recording each exception, so the rule matches practice. When working from another project, edit this `AGENTS.md` only for a rule change the user requested. An incident lesson becomes an agent rule only for causes the incident record establishes; cite the incident and limit the rule to that cause.

## Resume

1. Load the entry point, status, and project overview. Verify the current folder and checkout against the handoff; recorded commit or push state is a claim to check against Git, not a fact.
2. Inspect the relevant current files and differences. A recorded commit identifies historical context, not proof that the current working tree is unchanged. Reassess validation after relevant code or environment changes.
3. Load only architecture, map, and decisions relevant to the user's task. Follow links to primary sources as needed.
4. Distinguish completed work, unfinished implementation, known failures, and proposed next actions. Follow the current user request over an old next-step suggestion. Do not start an unrelated task from the status file.
5. Continue the requested work. If asked only for orientation, provide the reconstructed status and stop without edits.

## Update and checkpoint

Review relevant session changes and the current files, then route each fact:

| Change | Destination |
| --- | --- |
| Purpose, scope, setup, or usage changed; README's capability list would otherwise be wrong | README or existing setup guide (not for each feature or release) |
| Agent workflow, command, or established convention changed | AGENTS; CLAUDE only for its adapter or Claude-specific content |
| Important path, responsibility, or entry point moved | TREE or its established equivalent |
| Component relationship, interface, persistence, invariant, or operational inventory changed | ARCHITECTURE |
| Durable discovery about data, schemas, external systems, environment limits, or a pitfall | ARCHITECTURE or an existing reference doc; never a STATUS section |
| Consequential choice made with known rationale | DECISIONS |
| Task progressed, blocked, or needs handoff; deployed version or environment state changed | STATUS |
| Notable product behavior changed | CHANGELOG (create it if absent) |

- Make focused edits, not whole-file regenerations. Re-read an affected section immediately before writing when another contributor may have changed it.
- When a change invalidates, corrects, or narrows an earlier statement (a version, "not installed", "test only", a renamed file or command, a superseded decision), search every memory file with `rg` for the old statement, its key terms, and its variants, `AGENTS.md` included. Fix each hit or replace it with a link in the same update. Do not only append the new fact, and never patch the same sentence into several files; if a fact needs fixing in several places, remove the extra copies.
- With Git, compare the last version or commit that memory describes with `git log` since then. Record notable commits not yet reflected (they may come from sessions without memory updates), or state the undocumented range in STATUS.
- When evidence that was missing earlier becomes available (source committed, an environment reachable), re-check existing "unverified", "reported", or "not yet described" qualifiers and ground or remove them.
- If the task changed files in another project folder that has its own memory, record the change in that project's STATUS or ARCHITECTURE, or tell the user it was not recorded.
- Preserve unrelated dirty files and other contributors' active tasks. Do not reset, stash, stage, commit, push, or alter branches merely to save memory, and never commit solely to record memory or commit/push state. Follow separately authorized version-control workflows when present; make commit or push a next action only if the user asked for it.
- Checkpoint after a meaningful milestone or costly discovery, and before a handoff or known compaction when possible. Do not rewrite every file after every tool call.
- Record useful failed attempts with the symptom, scope, observed result, and what changes would justify retrying. Reduce a resolved investigation to symptom, cause, fix, and retry condition in at most three lines. Do not preserve repetitive logs or all exploratory thoughts.
- Update the status date only when its substantive contents change. Record VCS state only as a dated observation tied to a commit ("as of `abc123`: release uncommitted"), and only when it identifies unfinished work; whenever you change the date, re-check the checkout line against Git and delete remarks that no longer hold.
- A task is active only while implementation work remains; outstanding acceptance checks do not keep it active. When a task completes or ships, in the same edit: move its lasting facts to their canonical files, including every pitfall, hazard, or workaround a future session needs (to ARCHITECTURE known limitations); move its unresolved next actions and open questions to `Carried over`; put each remaining acceptance check as one line under `Pending acceptance`; delete the task's section and its validation. Never keep "previous objective/task" sections; Git and CHANGELOG are the archive. Record that no active task remains if appropriate; do not convert completion into an invented follow-up assignment.
- Before writing STATUS, re-read the whole file. Every statement of deployed version, running step, next action, blocker, and validation result must match the new state; rewrite or delete the rest. Delete resolved blockers, resolved carried-over items, passed acceptance lines, and validation of superseded builds; do not keep them marked "done" or "resolved". Never delete an unresolved item, and move any pitfall it holds before deleting text. Merge items of the same kind into one line (for example one documentation-drift line listing the affected releases).
- Never record a workaround that bypasses a documented safety rule as a reusable recipe. Record it as a one-off with who authorized it, and link the rule it bypassed.
- If several tasks are genuinely active, use labeled task sections or existing task files with a one-line index at the top. Do not replace another active task's status with yours.
- When removing an open question or blocker, record its resolution and source. If you chose without the user, label it "agent choice, unconfirmed", keep the question for the user, and record a consequential choice in DECISIONS as `proposed`.
- Persist every limitation, risk, or unverified behavior you report to the user, in ARCHITECTURE known limitations or in STATUS. README capability lines must not state behavior more strongly than the recorded evidence.
- If the same update request is repeated without new evidence or work, leave file contents unchanged.

## File content templates

Use these as content guides, not mandatory empty scaffolds. Adapt headings to existing documentation; fill only relevant, supported information and remove placeholder wording. Sizes are consolidation triggers, not limits. When STATUS passes about 150 lines or ARCHITECTURE about 300, consolidate before adding: merge items of the same kind, move content to its canonical home, and delete what is stale, finished, or historical. Never cut current, needed detail to reach a number; a file that is still long after consolidating is fine.

### README.md

- Project name and purpose: the problem, intended users, and scope boundaries.
- Current capabilities: one list of what the product does now, with plans labeled. No per-version "since vX" deltas and no prose naming the current version.
- Quick start: prerequisites and the 1–3 commands needed for a first run with the working directory; link to the full command list. Distinguish inspected commands from commands actually verified.
- Usage: one useful example when supported by the project.
- Documentation: links to the canonical architecture, repository map, decisions, and contributor instructions.

Keep README an overview. Keep detailed setup in an existing setup guide if one exists, and move detailed behavior contracts or acceptance checklists to a linked document edited in place. Do not duplicate long operational runbooks.

### AGENTS.md

- Project memory protocol above, with real paths.
- Existing working conventions and local exceptions that affect decisions.
- Essential build/test/lint commands, or links to their canonical definitions, including the working directory when non-obvious.
- Relevant project-specific rules supported by user instructions or existing policy; link technical invariants in ARCHITECTURE.

Aim for roughly 60-120 lines for a new root entry point, fewer when possible. This is a readability target, not permission to delete existing instructions to meet a quota.

### docs/TREE.md

Describe selected paths and responsibilities, for example as a two-column Markdown table. Include executable entry points, domain modules, tests, configuration, and important documentation. Use an annotated tree only when it makes hierarchy clearer. Exclude generated/dependency inventories. Do not maintain line numbers or a listing of every source symbol.

### docs/ARCHITECTURE.md

- System overview and boundaries.
- Components: responsibility, important source paths, and relationships.
- Main execution or data flow; include a compact Mermaid diagram if it adds clarity.
- Data model, persistence, and external interfaces at the level necessary to change the system safely.
- Operational inventory: services, endpoints, ports, scheduled jobs.
- Important invariants, platform constraints, and environment assumptions.
- Known technical limitations, pitfalls, and material unverified areas.
- Links to decision rationale and deeper component documentation.

Describe current implementation separately from target architecture. Organize by component, not by release or feature, and name at most the entry point of each mechanism. UI labels and per-release behavior belong in CHANGELOG; dated observations and verification state belong in STATUS. When the file grows large, split it into linked per-component files rather than trimming needed content. Avoid copied code, exhaustive API, function, field, or record-ID inventories, and "from vX" history; link to their maintained definitions and to CHANGELOG.

### docs/DECISIONS.md

For each consequential decision, use:

```markdown
## D-001: Descriptive title

- Status: accepted | proposed | superseded by D-NNN | amended by D-NNN
- Date: decision date, or "unknown"
- Decided by: user (source, date) | agent, unreviewed
- Context: the problem and constraints
- Decision: what holds now, in 1–3 sentences; link ARCHITECTURE for the mechanism
- Rationale: why, citing its source (file§section, user message, commit, comment), or "not recorded"
- Alternatives: rejected approaches and reasons, or "none recorded"
- Consequences: benefits, costs, constraints, or "unknown"
- Revisit when: concrete conditions, if known
- References: files, issues, related decisions
```

- A decision is consequential when it constrains future work or rejects a plausible alternative (architecture, data contract, integration, policy): a future agent without the record might undo or re-argue it. Building a requested feature is not a decision, and neither is a UI tweak or bug fix; those are CHANGELOG entries. A data-contract, integration, or design choice made while building a feature is a decision; do not leave it only in code comments or CHANGELOG.
- Append new records at the end with the next available ID in the existing scheme. Before numbering, search code comments, commit messages, and docs for decision IDs already cited (for example `rg 'D-[0-9]+'`). Treat every cited ID as taken and use the next free ID above the highest one. Never renumber an existing record. List IDs cited elsewhere but missing here as `D-NNN: referenced in <file>; rationale not recorded`. Keep each record about one decision and add no other fields: mechanism goes in ARCHITECTURE, verification and rollout in STATUS, releases in CHANGELOG. Status never tracks rollout.
- Write "unknown" or "not recorded" instead of omitting a field. Do not invent a decision date. A plausible explanation of what the code does is not a rationale. An agent choice the user has not reviewed is `proposed`; change it to `accepted` when the user accepts it or knowingly ships it.
- When a later decision, a user-granted exception, or new evidence changes any part of a record, edit the older record in the same change: either rewrite Decision, Rationale, and Consequences so the whole record is true, move the disproven assumption to Context, and add "Amended <date> by D-NNN/<source>: <one line>"; or set Status to "superseded by D-NNN". Never append a contradicting "Update" under stale fields. Preserve superseded records.
- Use an existing ADR directory when available; split into individual records if the file becomes difficult to navigate.

### docs/STATUS.md

Use this compact handoff structure:

```markdown
# Current status

Updated: date of substantive update
Checkout: branch/base commit and relevant working state, when it identifies unfinished work

## Current objective
The user-requested task and what completion means, or "No active task; next task awaits user direction."

## Deployed state
One line per environment: version, date, rollback artifact. Replace the line on each deploy; no history or exception dates.

## Current state
Completed and unfinished work relevant to the objective.

## Next actions
Ordered, concrete steps with the relevant paths or commands.

## Pending acceptance
One line per feature still awaiting a check: what to check, versions affected, who. Merge a new check into the
existing line for the same feature instead of adding one per release.

## Carried over
Unresolved items from earlier tasks; delete each once resolved.

## Blockers and questions
What prevents progress; distinguish a confirmed blocker from an open question.

## Validation
Latest result of each check supporting the current objective or deployed state: command, working directory
relative to the project root, result. Replace a line when a later run supersedes it; not a timed log.
Explicitly identify checks not run and why when that matters.

## Resumption notes
Important reproduction details, useful failed approaches, and transient constraints.
Link durable decisions and architecture instead of repeating them.
```

Omit sections with no useful content. STATUS is as long as the active work needs, and holds nothing finished, superseded, or restated from another file. Store substantial task plans in existing task documents and link them. Do not store conversation transcripts, hidden reasoning, long command logs, incident narratives, feature notes, or a chronological diary.

### CHANGELOG.md

- Preserve the project's format and release process. Otherwise use `## Unreleased` with Added, Changed, Fixed, or Removed.
- Unreleased holds only changes not yet in a built or deployed version. At initialization, do not log existing or already-shipped behavior there; README describes it.
- An entry is a change in software behavior (code or configuration) that users can see between released or deployed states. Data runs, imports, record IDs, deployments, documentation edits, memory refreshes, and fixes to behavior that was never released are not entries.
- When a version is evidenced as released or in production (manifest version plus a recorded deployment, or a tag), move its entries under `## <version> — <date>`. Do not assign a release number or date without evidence or backfill imaginary releases.
- For unversioned, continuously deployed services, record later changes as new entries; never rewrite earlier ones.
- Do not put environment or gate status in headings or write sentinel lines. Without VCS, derive entries from features present in the code; undatable entries stay under Unreleased.

## Audit and validation

For a requested audit, report findings by practical impact with file paths and evidence. For an audit with repairs requested, fix supported discrepancies and report unresolved ones. After initialize or update, check the edited material, every restatement of the facts you changed, and any existing document the entry point newly designates as canonical:

1. Verify local links and referenced project paths exist, resolving relative to the document. Label intentional future paths explicitly. Avoid claiming external links were verified unless actually checked.
2. Check that documented commands exist in their claimed configuration or source and that their working directories are correct. Reading a command definition does not establish that it passes.
3. Check the entry-point/import chain for missing files, duplicate loading, and cycles. Confirm intended uppercase entry-point filenames without creating case-colliding duplicates.
4. Check README capabilities and architecture claims against inspected implementation. Flag uncertainty that requires deeper investigation instead of pretending a full audit of uninspected code.
5. Check status against the current task, checkout, and available validation results. Remove or qualify stale next steps, completed task sections, superseded validation, and test claims.
6. Check decisions for unsupported rationale, contradictory active records, stale fields under amendments, and missing supersession links. Preserve unresolved user-level choices.
7. Review the diff, or compare only edited files without Git. Remove duplication, placeholder residue, unnecessary timestamp churn, personal or production data, and edits outside scope. Delete backups your edits created (`*.orig`, `*.rej`, `*~`, `*.bak`) and report other stray copies of memory files. Ensure existing user instructions remain intact.

Do not broaden a small memory update into a full codebase audit. If docs conflict with code, correct descriptions of current behavior when supported; retain desired requirements and identify the implementation gap. Preserving user-written documentation means keeping its structure and intent, not its factual errors about current behavior. If competing requirements remain ambiguous, ask a targeted question after completing unambiguous work.

## Completion response

Briefly state the operation performed, files created/updated or reused, important unknowns, and actual validation. For a resume-only operation, state the reconstructed task and next action. Report a no-op explicitly when nothing changed. Do not claim the skill runs continuously, guarantees persistence of unwritten work, or has saved files that were not successfully written. Stop after the requested documentation work unless the user also asked to continue implementation.
