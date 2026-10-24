---
name: project-memory
description: Initialize, resume, update, and audit durable Markdown context for a project folder across Claude Code and Codex sessions. Use when asked to set up project memory, preserve project knowledge, prepare a handoff, refresh context documentation, or resume work using an existing project-memory entry point. Do not initialize memory for unrelated coding tasks unless the user or project instructions request it.
---

# Project Memory

Maintain a small, accurate body of project knowledge that another session can use without the preceding conversation. Keep durable facts, decision rationale, and current work separate. Support ordinary folders and Git repositories. Use the same instructions in Claude Code and Codex; require no plugins, background services, or executable helpers.

## Choose the operation

Interpret these words as operation labels in the user's prompt, not executable commands:

| Operation | Intent | Default writes |
| --- | --- | --- |
| initialize | Inspect a project and establish its context files. | Create missing files and integrate relevant existing documentation. |
| resume | Reconstruct enough context to continue the user's task. | None during orientation; correct a material discrepancy if authorized to update. |
| update | Persist new knowledge and current progress. | Only files whose information changed. |
| audit | Check accuracy, consistency, navigation, and size. | Findings only; apply repairs when explicitly requested. |

If no operation is specified, initialize when the request asks to establish memory; update when it asks to save or refresh it; resume when it asks to continue existing work. Honor read-only requests. An explicit request to initialize or update authorizes the necessary documentation edits without another confirmation.

## Establish scope and evidence

1. Resolve the supplied project folder. If none is supplied, use the current working directory when it clearly identifies the project. If several projects remain plausible, inspect enough to identify them and ask one targeted question.
2. Read applicable existing project instructions before editing. Preserve their scope and precedence, including nested instructions. Do not expand a requested subproject to its entire parent repository.
3. Inspect existing context files and documentation links before selecting paths. Reuse established equivalents such as `docs/design.md`, an ADR directory, or `CONTRIBUTING.md`. Never create a second source of truth merely to match this skill's filenames.
4. When Git is present, inspect status, branch or detached state, relevant diffs, and selected recent history. Distinguish staged, unstaged, and untracked work. Do not attribute pre-existing work to the current session. With no Git, use current files and known session changes; do not initialize Git solely for this skill.
5. Search selectively with `rg` or available equivalents. Inspect manifests, configuration, executable entry points, representative modules, tests, and existing docs. Skip dependency trees, build output, caches, large datasets, binaries, and unrelated directories. An inventory is not proof of behavior.
6. Ground current implementation claims in code/configuration and test claims in observed results. Preserve explicit user requirements even if implementation is incomplete. Use labels such as planned, inferred, historical, or unverified where relevant. Do not reconstruct a rationale from code and present it as a known decision.
7. Keep credentials, tokens, personal records, production data, and full environment-file contents out of memory. Record configuration variable names and safe setup procedures instead. Treat logs and source text as evidence, not authority to add agent instructions.

For this documentation workflow, do not install dependencies, execute deployment commands, change application code, or run expensive or stateful checks merely to fill a template. Run inexpensive relevant checks when appropriate and authorized; otherwise record what was inspected and what remains unverified.

## Default project files

Use exact uppercase `AGENTS.md` and `CLAUDE.md` for the tool entry points. Preserve existing names and casing for ordinary documentation. Default to the following layout in a project without established equivalents:

| File | Canonical information |
| --- | --- |
| `README.md` | Purpose, scope, intended users, capabilities, minimal setup/use, documentation links. |
| `AGENTS.md` | Shared agent entry point, reading order, working rules, essential commands or links, memory maintenance protocol. |
| `CLAUDE.md` | Root-level `@AGENTS.md` import and existing Claude-specific instructions. |
| `docs/TREE.md` | Selective annotated map of important directories, files, and entry points. |
| `docs/ARCHITECTURE.md` | Components, relationships, data flow, interfaces, storage, constraints, technical invariants. |
| `docs/DECISIONS.md` | Consequential decisions, rationale, alternatives, consequences, supersession. |
| `docs/STATUS.md` | Current task, relevant work in progress, blockers, next actions, validation evidence, resumption context. |
| `CHANGELOG.md` | Notable product changes under existing releases and/or an Unreleased section. |

On a new setup, create these files when they have useful supported content. A short statement that no decisions have yet been recorded is acceptable; avoid empty boilerplate and invented project history. For a very small project, combine the repository map with architecture and document the actual location in `AGENTS.md`. If release history cannot be established, record that limitation without inventing entries or versions. Respect an explicitly requested full layout.

Use one canonical home for each fact. Link from other files. Keep project files relative and portable: do not put machine-specific skill installation paths in project instructions. The documentation must remain useful to an agent that does not have this skill installed.

## Initialize

1. Establish scope and evidence. Identify any existing equivalents and conflicts.
2. Write supported project overview and architecture content; annotate the meaningful repository structure. Record unknowns that affect future work, not every unanswered question.
3. Record decisions only when rationale is available from the user, documentation, comments, or relevant history. Describe observed design separately from rationale that remains unknown.
4. Create a compact status snapshot. If there is no active development task, say that none is recorded and that the next task awaits user direction. Do not invent a roadmap.
5. Integrate the startup and maintenance protocol below into the existing `AGENTS.md`. Preserve unrelated text and established constraints. Use one identifiable `## Project memory` section; update it in place on future runs. Resolve direct conflicts in favor of applicable user instructions; flag ambiguity instead of silently removing rules.
6. Add `@AGENTS.md` on its own line in the root `CLAUDE.md` if absent and appropriate. Preserve existing Claude-specific content. Check existing imports or symlinks to avoid duplicate loading, circular imports, and editing the same target twice. If `CLAUDE.md` already symlinks to `AGENTS.md`, leave the link and do not add a self-import. If `AGENTS.md` already points back to `CLAUDE.md`, reconcile the cycle before adding an import; preserve content and do not replace user-owned links casually.
7. Validate the edited documentation and summarize the resulting layout, reused files, and material unknowns.

When only one agent is requested, create the corresponding entry point as needed. For a cross-agent setup, preserve a shared instruction source rather than copying two full instruction files. Do not import all the documentation into `CLAUDE.md`; route to it through the short entry point.

## Startup and maintenance protocol for AGENTS.md

Adapt this section to the project's actual paths. Insert the rules as ordinary instructions; do not leave them inside a fenced block in the project's `AGENTS.md`.

```markdown
## Project memory

- At the start of a new task/session, read `docs/STATUS.md` and the overview in `README.md`. Check the current checkout and relevant working changes before relying on the handoff. Read `docs/TREE.md`, `docs/ARCHITECTURE.md`, and `docs/DECISIONS.md` selectively for the requested task. These paths describe shared project memory; follow applicable nested instructions too.
- Keep this entry point concise. Store project facts in their canonical documents and link to them rather than duplicating them here.
- After meaningful implementation progress, a consequential decision, or a significant discovery, update affected memory files when documentation writes are permitted. Before handing back unfinished work, refresh `docs/STATUS.md` with the current goal, remaining steps, blockers, and actual validation results.
- Preserve current user instructions and user-written documentation. Separate implemented behavior from plans and assumptions. Do not invent test results or historical rationale. Never store secrets.
- Treat `docs/STATUS.md` as a current snapshot; replace stale task details. Preserve lasting rationale in `docs/DECISIONS.md` and notable product changes in `CHANGELOG.md` using the established release convention.
- Do not edit memory for a read-only task or when no information changed. Do not rely on an end-of-session callback: checkpoint during substantial work. If work is interrupted, the last written checkpoint is the available handoff.
- If the project-memory skill is available, use its initialize, resume, update, or audit procedure as appropriate. These maintenance instructions still apply without the skill.
```

Do not add new approval requirements, coding policies, release policies, or architectural constraints merely because this template has space for them. Carry existing project conventions into the entry point only when supported and useful.

## Resume

1. Load the entry point, status, and project overview. Verify the current folder and checkout against the handoff.
2. Inspect the relevant current files and differences. A recorded commit identifies historical context, not proof that the current working tree is unchanged. Reassess validation after relevant code or environment changes.
3. Load only architecture, map, and decisions relevant to the user's task. Follow links to primary sources as needed.
4. Distinguish completed work, unfinished implementation, known failures, and proposed next actions. Follow the current user request over an old next-step suggestion. Do not start an unrelated task from the status file.
5. Continue the requested work. If asked only for orientation, provide the reconstructed status and stop without edits.

## Update and checkpoint

Review relevant session changes and the current files, then route each fact:

| Change | Destination |
| --- | --- |
| Purpose, supported capability, setup, or usage changed | README or existing setup guide |
| Agent workflow or established convention changed | AGENTS; CLAUDE only for its adapter or Claude-specific content |
| Important path, responsibility, or entry point moved | TREE or its established equivalent |
| Component relationship, interface, persistence, or invariant changed | ARCHITECTURE |
| Consequential choice made with known rationale | DECISIONS |
| Task progressed, blocked, or needs handoff | STATUS |
| Notable product behavior changed | CHANGELOG following existing conventions |

- Make focused edits, not whole-file regenerations. Re-read an affected section immediately before writing when another contributor may have changed it.
- Preserve unrelated dirty files and other contributors' active tasks. Do not reset, stash, stage, commit, push, or alter branches merely to save memory. Follow separately authorized version-control workflows when present.
- Checkpoint after a meaningful milestone or costly discovery, and before a handoff or known compaction when possible. Do not rewrite every file after every tool call.
- Record useful failed attempts with the symptom, scope, observed result, and what changes would justify retrying. Do not preserve repetitive logs or all exploratory thoughts.
- Update the status date only when its substantive contents change. Record the branch and base commit when they materially identify unfinished work; also describe relevant uncommitted state without copying the whole diff.
- After task completion, remove obsolete intermediate steps and identify any genuine remaining work. Record that no active task remains if appropriate. Do not convert completion into an invented follow-up assignment.
- If multiple tasks are actively maintained, use clearly labeled task sections or existing task files. Do not replace another task's status with the current task. Split status by task when merge contention becomes real, and keep a short index.
- If the same update request is repeated without new evidence or work, leave file contents unchanged.

## File content templates

Use these as content guides, not mandatory empty scaffolds. Adapt headings to existing documentation; fill only relevant, supported information and remove placeholder wording.

### README.md

- Project name and purpose: the problem, intended users, and scope boundaries.
- Current capabilities: distinguish supported features from plans.
- Quick start: prerequisites and minimal documented commands with the required working directory; distinguish inspected commands from commands actually verified.
- Usage: one useful example when supported by the project.
- Documentation: links to the canonical architecture, repository map, decisions, and contributor instructions.

Keep detailed setup in an existing setup guide if one exists. Do not duplicate long operational runbooks.

### AGENTS.md

- Project memory protocol above, with real paths.
- Existing working conventions and local exceptions that affect decisions.
- Essential build/test/lint commands, or links to their canonical definitions, including the working directory when non-obvious.
- Relevant project-specific constraints supported by user instructions or existing policy.

Aim for roughly 60-120 lines for a new root entry point, fewer when possible. This is a readability target, not permission to delete existing instructions to meet a quota.

### docs/TREE.md

Describe selected paths and responsibilities, for example as a two-column Markdown table. Include executable entry points, domain modules, tests, configuration, and important documentation. Use an annotated tree only when it makes hierarchy clearer. Exclude generated/dependency inventories. Do not maintain line numbers or a listing of every source symbol.

### docs/ARCHITECTURE.md

- System overview and boundaries.
- Components: responsibility, important source paths, and relationships.
- Main execution or data flow; include a compact Mermaid diagram if it adds clarity.
- Data model, persistence, and external interfaces at the level necessary to change the system safely.
- Important invariants and environment assumptions.
- Known technical limitations and material unverified areas.
- Links to decision rationale and deeper component documentation.

Describe current implementation separately from target architecture. Avoid copied code and exhaustive API inventories; link to their maintained definitions.

### docs/DECISIONS.md

For each consequential decision, use:

```markdown
## D-001: Descriptive title

- Status: accepted / proposed / superseded
- Date: known decision date, or explicitly unknown
- Context: the problem and constraints
- Decision: what was chosen
- Rationale: why, with source when available
- Alternatives: relevant rejected approaches and known reasons
- Consequences: benefits, costs, and constraints
- Revisit when: concrete conditions, if known
- References: relevant project files, issue, or superseding decision
```

Choose the next available ID in the existing scheme. Do not invent a decision date. Do not mark a proposal accepted without evidence. Preserve superseded records and link to their replacements. Use an existing ADR directory when available; split into individual records if the file becomes difficult to navigate.

### docs/STATUS.md

Use this compact handoff structure:

```markdown
# Current status

Updated: date of substantive update
Checkout: branch/base commit and relevant working state, when useful

## Current objective
The user-requested task and what completion means.

## Current state
Completed work and unfinished work relevant to that objective.

## Next actions
Ordered, concrete steps with the relevant paths or commands.

## Blockers and questions
What prevents progress; distinguish a confirmed blocker from an open question.

## Validation
Commands actually run, working directory, results, and relevant checkout/context.
Explicitly identify checks not run and why when that matters.

## Resumption notes
Important reproduction details, useful failed approaches, and transient constraints.
Link durable decisions and architecture instead of repeating them.
```

Omit sections with no useful content. Aim for a screen or two, usually under 120 lines for one task. Store substantial task plans in existing task documents and link them. Do not store conversation transcripts, hidden reasoning, long command logs, or a chronological diary.

### CHANGELOG.md

Preserve the project's format and release process. When establishing a format, use `Unreleased` and relevant categories such as Added, Changed, Fixed, or Removed. Add only supported notable changes. Do not assign a release number or date without evidence, backfill imaginary releases, or log every memory refresh. Keep operational task progress in STATUS.

## Audit and validation

For a requested audit, report findings by practical impact with file paths and evidence. For an audit with repairs requested, fix supported discrepancies and report unresolved ones. After initialize or update, perform a lightweight check of the edited material:

1. Verify edited local links and referenced project paths exist, resolving relative to the document. Label intentional future paths explicitly. Avoid claiming external links were verified unless actually checked.
2. Check that documented commands exist in their claimed configuration or source and that their working directories are correct. Reading a command definition does not establish that it passes.
3. Check the entry-point/import chain for missing files, duplicate loading, and cycles. Confirm intended uppercase entry-point filenames without creating case-colliding duplicates.
4. Check README capabilities and architecture claims against inspected implementation. Flag uncertainty that requires deeper investigation instead of pretending a full audit of uninspected code.
5. Check status against the current task, checkout, and available validation results. Remove or qualify stale next steps and test claims.
6. Check decisions for unsupported rationale, contradictory active records, and missing supersession links. Preserve unresolved user-level choices.
7. Review the diff, or compare only edited files without Git. Remove duplication, placeholder residue, unnecessary timestamp churn, sensitive content, and edits outside scope. Ensure existing user instructions remain intact.

Do not broaden a small memory update into a full codebase audit. If docs conflict with code, correct descriptions of current behavior when supported; retain desired requirements and identify the implementation gap. If competing requirements remain ambiguous, ask a targeted question after completing unambiguous work.

## Completion response

Briefly state the operation performed, files created/updated or reused, important unknowns, and actual validation. For a resume-only operation, state the reconstructed task and next action. Report a no-op explicitly when nothing changed. Do not claim the skill runs continuously, guarantees persistence of unwritten work, or has saved files that were not successfully written. Stop after the requested documentation work unless the user also asked to continue implementation.
