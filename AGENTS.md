# hopper

---

## Hopper - Persistent Memory

This project uses [Hopper](https://github.com/apathy-ca/hopper) for persistent memory across AI agent sessions.

**Storage:** `.hopper/` in this directory (tasks, knowledge, memory).

### Quick commands

```bash
hopper task add "Note or task"              # Store something
hopper task list                            # See open tasks
hopper task status <id> in_progress -f     # Claim a task
hopper task status <id> completed -f       # Complete a task
hopper task heartbeat <id>                  # Signal still working
hopper context                              # Recent learnings + open tasks
```

### Agent identity

Identify yourself with `platform:task-name` when claiming work:
- `opencode:my-task`, `claude:acm-rewrite`, `kilocode:prh-transfer`, `human:james`
- Never use generic names like `main`.

### Session lifecycle

On start: `hopper task list` → check `in_progress` tasks → claim or create your task.
During work: heartbeat every 10-15 min. On end: mark `completed` or release to `open`.

### Knowledge base

Agent knowledge is available in `.hopper/knowledge/` — coding standards, design
patterns, agent roles, and workflows relevant to this project type.

```bash
hopper knowledge list                       # See what's available
hopper knowledge show                       # View hopper usage guide
hopper knowledge update-agent-files        # Re-sync AGENTS.md/CLAUDE.md to latest
```
