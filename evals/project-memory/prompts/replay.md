You are a coding agent working in this repository (your current working directory). A working session in this
repository has just finished; its digest is below. The code changes it made are already in the checkout, or are
described in the digest if they were never committed. You did that work, and now must do the project-memory
maintenance for it.

$operation

Rules for this run:
- Edit only project-memory documentation (README.md, AGENTS.md, CLAUDE.md, CHANGELOG.md, files directly in docs/).
  Do not change application code, do not commit, and do not run builds, tests, or deployments: rely on the
  commands and results in the digest as the validation evidence of the session.
- Use the instructions of the project-memory skill below. They are the skill exactly as installed.

## Project instructions loaded at session start (CLAUDE.md → AGENTS.md)

$agents_md

## Session digest

Agent: $agent · model: $model · started $start · ended $end · checkout: $commit

### User prompts, in order
$prompts

### Files changed in the session (other than memory docs), +added/-removed lines
$files

### Commands run (error = non-zero exit or tool error)
$commands

### Agent's final message to the user
$final

## The project-memory skill (SKILL.md)

$skill
