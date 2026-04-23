# hopper

## Hopper - Persistent Memory for AI Agents

Hopper is your **long-term memory system**. Use it to persist notes, track tasks, record feedback, and maintain context across sessions.

**Storage:** `.hopper/` in this directory (tasks, knowledge, memory). All data is markdown files — no database required in local mode.

---

## Quick Start

```bash
hopper task add "Note or task"   # Store something
hopper task list                 # See open tasks
hopper context                   # Recent learnings + open tasks
```

---

## Session Lifecycle

**On session start, every agent MUST:**
1. Run `hopper task list` to see all tasks and their status
2. Read details on relevant tasks: `hopper task get <id>`
3. Check for `in_progress` tasks to avoid duplicating work another agent is doing
4. If picking up a task: `hopper task status <id> in_progress --assign <identity> -f`
5. If creating new work: `hopper task add "<title>" --assign <identity> --status in_progress`

**During work:**
- Run `hopper task heartbeat <id>` every 10-15 minutes of active work
- Before long-running processes: `hopper task heartbeat <id> --expect 2h`

**On session end:**
- Mark tasks completed: `hopper task status <id> completed -f`
- If stopping early: `hopper task update <id> --unassign` then `hopper task status <id> open -f`
- If blocked: `hopper task status <id> blocked -f`

---

## Agent Identity

Identify yourself with `platform:task-name` when claiming work:

Format: `platform:task-name`
- Platform: `claude`, `opencode`, `kilocode`, `human`, etc.
- Task name: short descriptor of the work (2-3 words, hyphenated)

Examples:
- `opencode:agents-md-fix` — OpenCode agent fixing AGENTS.md
- `claude:acm-rewrite` — Claude agent rewriting the ACM document
- `kilocode:prh-transfer` — Kilo Code agent on PRH transfer tests
- `human:james` — James working directly

**Never use**: `agent:main`, `claude:main`, `claude:session1`, or any generic name.

---

## Status Values

| Status | Meaning |
|--------|---------|
| `open` | Ready to pick up, nobody working on it |
| `in_progress` | An agent is actively working on this right now |
| `blocked` | Waiting on another task or external dependency |
| `completed` | Done |
| `cancelled` | Abandoned |

---

## Task Granularity

One task per logical initiative, not per execution step. A 25-model GPU sweep is one task, not 25. Use tags for filtering (`--tag gpu`) and descriptions for details. Pipeline steps belong in logs, not Hopper.

---

## Full CLI Reference

```bash
# Task management
hopper task list                              # All tasks, sorted by status then priority
hopper task list --status open                # Filter by status
hopper task list --tag gpu --compact          # Filter by tag, compact view
hopper task add "Title" --priority high       # Add a task
hopper task add "Title" --assign "opencode:my-work" --status in_progress
hopper task get <id>                          # Full task details
hopper task update <id> --assign "opencode:x" # Update fields
hopper task update <id> --unassign            # Release without completing
hopper task status <id> in_progress -f        # Change status (no confirmation)
hopper task status <id> completed -f
hopper task status <id> open -f
hopper task status <id> blocked -f
hopper task heartbeat <id>                    # Signal still working
hopper task heartbeat <id> --expect 4h        # Signal with expected duration
hopper task stale                             # Find abandoned tasks (30 min default)
hopper task stale --minutes 60               # Custom threshold
hopper task search "keyword"
hopper task delete <id> -f
hopper task children <parent-id>
hopper task add "Subtask" --parent <parent-id>

# Session context
hopper context                                # Recent learnings + open tasks
hopper ls                                     # Shortcut for task list

# Knowledge base
hopper knowledge list                         # Show available knowledge
hopper knowledge show                         # Display hopper-usage.md
hopper knowledge sync                         # Re-sync from GitHub
hopper knowledge refresh                      # Update built-in docs

# Sync (upstream server)
hopper sync                                   # Push/pull with upstream server
```

---

## ID Prefix Matching

All commands accept truncated IDs. `hopper task get t7232` resolves to the full ID if unambiguous.

---

## Stale Detection

Tasks are considered stale when an assigned agent stops heartbeating (default: 30 minutes). The task list view shows staleness as a color gradient on the status text. If you find a stale task from a dead agent, you may reassign it to yourself.

---

## Parent-Child Tasks

```bash
hopper task add "Subtask" --parent <parent-id>
hopper task children <parent-id>    # List children with rollup
hopper task get <parent-id>         # Shows done/total count
hopper task update <id> --unparent  # Remove from parent
```

---

## Knowledge Base

Agent knowledge is available in `.hopper/knowledge/` — coding standards, design patterns, agent roles, and workflows relevant to this project type.

```bash
hopper knowledge list   # See what's available
hopper knowledge show   # View hopper usage guide
```

---

## Adding Hopper to a Project

```bash
cd /path/to/project
hopper init
```

Creates `.hopper/` with `config.yaml`, `tasks/`, `knowledge/`, `memory/`, `feedback/`. `.hopper/` is gitignored by default.
