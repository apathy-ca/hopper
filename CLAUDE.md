# Hopper - Claude Agent Instructions

## Hopper Usage

See [AGENTS.md](./AGENTS.md) for the full Hopper usage guide — task lifecycle, agent identity, status values, CLI reference, and multi-agent coordination. All conventions in AGENTS.md apply here.

## Claude-Specific: /hopper Skill

Use the `/hopper` skill for fast access to common commands. See `.claude/skills/hopper.md` for the full skill reference.

## Claude Web Integration (MCP)

Hopper can be used with Claude Web via MCP. This requires a running Hopper server.

### Setup

1. **Start the Hopper server:**
   ```bash
   hopper server start --host 0.0.0.0 --port 8080
   ```

2. **Register for MCP access:**
   ```bash
   hopper mcp init-token --server https://your-server.com
   # Output: hpr_abc123...
   ```

3. **Configure Claude Web** with the token:
   ```json
   {
     "mcp_servers": [{
       "type": "url",
       "url": "https://your-server.com/mcp/sse/",
       "name": "hopper",
       "authorization_token": "hpr_abc123..."
     }]
   }
   ```

### Token Management

```bash
hopper mcp tokens --server <url>           # List your tokens
hopper mcp revoke <prefix> --server <url>  # Revoke a token
```

---

## Hopper - Persistent Memory
<!-- hopper-agent-files: v4 -->

This project uses [Hopper](https://github.com/apathy-ca/hopper) for persistent memory across AI agent sessions.

**Storage:** `.hopper/` in this directory (tasks, knowledge, memory).

### Quick commands

```bash
hopper task add "Note or task"              # Store something
hopper task list                            # See open tasks (--json, --ids-only, --assignee X)
hopper task get <id> --json                 # Full task as JSON
hopper task add "Title" --id-only           # Print only the new task ID
hopper task status <id> in_progress -f     # Claim a task
hopper task status <id> completed -f       # Complete a task
hopper task heartbeat <id>                  # Signal still working
hopper task note <id> "finding: ..."        # Leave an attributed note on any task
hopper context                              # Recent learnings + open tasks
hopper sync                                 # Push/pull with the shared server
```

### Agent identity

Identify yourself with `platform:task-name` when claiming work:
- `opencode:my-task`, `claude:acm-rewrite`, `kilocode:prh-transfer`, `human:james`
- Never use generic names like `main`.
- Set `HOPPER_IDENTITY=platform:you` (or pass `--by`) so records you create are
  attributed to you (`created_by`), not just your machine.

### Notes & attribution

- Leave a finding on a task another agent owns with `hopper task note <id> "..."`.
  Notes are append-only and never overwrite the description, so hand-offs are
  safe; they render in `hopper task get`.
- Every record stamps an immutable `created_by`. Notes and creator both travel
  with the task through `hopper sync` to the shared board.

### Recording memories

When you store a memory, say how you know it and cite what backs it:

```bash
hopper memory add "Sync batches at 512KB" --subject project:hopper \
  --how-known "read in code at src/hopper/upstream/sync.py" \
  --evidence src/hopper/upstream/sync.py --evidence t1a2b3c4d
```

- `--how-known`: a few words — "observed in test run", "told by user",
  "read in code at X". A guess is fine if you say it is one.
- `--evidence` (repeatable): task ids, commit shas, or file paths relative to
  the project root. `hopper doctor` flags memories whose evidence is gone.
- `--salient [--salient-for 3d]`: flag a memory worth revisiting; the flag
  lapses after the window (default 3d).

### Session lifecycle

On start: `hopper sync` → `hopper task list` → check `in_progress` tasks → claim or create your task.
During work: heartbeat every 10-15 min; `hopper sync` periodically (task writes stay local until you sync).
On end: mark `completed` or release to `open`, then `hopper sync` to push your work.

### Knowledge base

Agent knowledge is available in `.hopper/knowledge/` — coding standards, design
patterns, agent roles, and workflows relevant to this project type.

```bash
hopper knowledge list                       # See what's available
hopper knowledge show                       # View hopper usage guide
hopper knowledge update-agent-files        # Re-sync AGENTS.md/CLAUDE.md to latest
```
