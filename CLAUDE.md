# Hopper - Persistent Memory for AI Agents

Hopper is your **long-term memory system**. Use it to persist notes, track tasks, record feedback, and maintain context across sessions.

## Why Use Hopper?

As an AI agent, your context resets between sessions. Hopper solves this:

- **Remember things** - Store notes, decisions, and learnings
- **Track work** - Tasks persist across conversations
- **Record feedback** - Capture what worked, what didn't
- **Project context** - Maintain project-specific knowledge

## Quick Start: /hopper Skill

Use the `/hopper` skill for fast access:

```
/hopper add "Remember: user prefers TypeScript over JavaScript"
/hopper add "TODO: Refactor auth module" --priority high
/hopper add "FEEDBACK: Test coverage approach worked well" --tag feedback
/hopper list
/hopper done <task-id>
```

See `.claude/skills/hopper.md` for full command reference.

## Use Cases

### Long-term Notes
```
/hopper add "Architecture decision: Using event sourcing for audit trail"
/hopper add "User preference: Always run tests before committing"
```

### Project Feedback
```
/hopper add "What worked: Breaking changes into small PRs" --tag feedback
/hopper add "Issue: CI takes too long, consider parallelization" --tag feedback
```

### Task Tracking
```
/hopper add "Implement caching layer" --priority high --tag backend
/hopper add "Write API documentation" --tag docs
/hopper list --status open
```

### Session Handoff
Before ending a session, record state:
```
/hopper add "SESSION: Completed auth refactor, next step is testing"
```

## Storage

Tasks are stored locally in `.hopper/` as markdown files. They persist across sessions and can be version controlled.

## Adding Hopper to a Project

```bash
cd /path/to/project
hopper init
```

This creates:
```
.hopper/
├── config.yaml      # Instance config
├── tasks/           # Tasks and learnings (markdown)
├── knowledge/       # Agent knowledge (synced from GitHub)
│   ├── hopper-usage.md        # Built-in usage guide
│   └── agent-knowledge/       # Synced patterns & standards
├── memory/          # Patterns and episodes
├── feedback/        # Routing feedback
└── .index/          # Cache (gitignored, regenerated)
```

**What gets committed:** Everything except `.hopper/.index/` (auto-added to .gitignore).

**Knowledge sync:** On init, Hopper clones relevant sections from [agent-knowledge](https://github.com/apathy-ca/agent-knowledge) based on detected project type (Python, MCP, Czarina, etc.).

## Knowledge Commands

```bash
hopper knowledge list      # Show available knowledge
hopper knowledge sync      # Re-sync from GitHub
hopper knowledge show      # Display hopper-usage.md
hopper knowledge refresh   # Update built-in docs
```

## Multi-Agent Coordination

Hopper tracks which agent owns which task and whether they're still alive.

### Agent Identity

Identify yourself with `platform:task-name` when claiming work:
- `claude:acm-rewrite`, `opencode:consensus-gen`, `human:james`
- The name describes the work, not your role. Never use generic names like `main`.

### Claiming and Releasing Work

```bash
# Claim a task
hopper task status <id> in_progress --assign "claude:my-task" -f

# Release when done
hopper task status <id> completed -f

# Release without completing (stopping early)
hopper task update <id> --unassign
hopper task status <id> open -f
```

### Heartbeats

Signal that you're still working. Call every 10-15 minutes of active work:

```bash
hopper task heartbeat <id>

# Before long-running work (GPU jobs, data generation)
hopper task heartbeat <id> --expect 4h
```

The `--expect` flag tells the stale detector not to flag you early. Without it, tasks are considered stale after 30 minutes of silence.

### Stale Detection

```bash
hopper task stale              # Find abandoned tasks (30 min default)
hopper task stale --minutes 60 # Custom threshold
```

The list view shows staleness as a per-character color gradient on the status text: green chars fade to red as the heartbeat ages. No separate command needed.

### Parent-Child Tasks

```bash
hopper task add "Subtask" --parent <parent-id>
hopper task children <parent-id>    # List children with rollup
hopper task get <parent-id>          # Shows done/total
hopper task update <id> --unparent   # Remove from parent
```

### Task Granularity

One task per logical initiative, not per execution step. A 25-model GPU sweep is one task, not 25. Use tags for filtering and descriptions for details.

### ID Prefix Matching

All commands accept truncated IDs. `hopper task get t7232` resolves to the full ID if unambiguous.

## Full CLI

```bash
hopper task list                     # Sorted by status then priority
hopper task list --tag gpu --compact # Filter and compact view
hopper task add "Task" --priority high --assign "claude:worker" --parent <id>
hopper task update <id> --assign "claude:x" --parent <id>
hopper task search "keyword"
hopper task delete <id> -f
hopper knowledge sync --full
hopper github import owner/repo --all
```

---

**Bottom line**: Whenever you learn something worth remembering, need to track work, or want to leave notes for future sessions - use `/hopper`.
