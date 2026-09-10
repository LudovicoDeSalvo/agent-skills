# Project Memory

A shared skill for Claude Code and Codex that maintains Markdown project context between sessions: overview, agent instructions, repository map, architecture, decisions, current status, and changelog.

## Install

Requires Node.js/npm and Git.

Install for both agents across all local projects:

```bash
npx --yes skills add LudovicoDeSalvo/agent-skills --skill project-memory --agent claude-code codex --global --copy --yes
```

Verify installation:

```bash
npx --yes skills ls -g
```

Run these commands in the environment where your agents run (Windows, macOS, Linux, or WSL).

## Use

Open your project folder in the agent. Initialize its memory once:

**Codex**

```text
$project-memory initialize shared project memory in this folder. Use the full eight-file layout, reusing existing equivalent documentation.
```

**Claude Code**

```text
/project-memory initialize shared project memory in this folder. Use the full eight-file layout, reusing existing equivalent documentation.
```

For subsequent tasks, send the appropriate prompt inside your agent:

| Action | Codex | Claude Code |
| --- | --- | --- |
| Resume | `$project-memory resume this project and summarize the next steps.` | `/project-memory resume this project and summarize the next steps.` |
| Save progress | `$project-memory update context and prepare a handoff.` | `/project-memory update context and prepare a handoff.` |
| Audit | `$project-memory audit context without editing files.` | `/project-memory audit context without editing files.` |
| Repair | `$project-memory audit and repair outdated context.` | `/project-memory audit and repair outdated context.` |

Initialization adds project instructions for ongoing maintenance. The skill runs through the agent; it is not a background service.

## Update the installed skill

```bash
npx --yes skills update project-memory --global --yes
```

This updates the skill instructions. Use the **Save progress** prompt to update an individual project's context files.
