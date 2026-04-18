# hopper

## Hopper - Persistent Memory

This project uses [Hopper](https://github.com/apathy-ca/hopper) for persistent memory across AI agent sessions.

**Storage:** `.hopper/` in this directory (tasks, knowledge, memory).

### Quick commands

```bash
hopper task add "Note or task"   # Store something
hopper task list                 # See open tasks
hopper context                   # Recent learnings + open tasks
```

### What to store

- Architecture decisions and rationale
- User preferences discovered during the session
- Project patterns (`Pattern: all API routes use /api/v1 prefix`)
- Feedback on what worked / didn't
- Session handoff notes before ending a conversation

### Knowledge base

Agent knowledge is available in `.hopper/knowledge/` — coding standards, design
patterns, agent roles, and workflows relevant to this project type.

```bash
hopper knowledge list   # See what's available
hopper knowledge show   # View hopper usage guide
```
