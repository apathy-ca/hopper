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
<!-- hopper-agent-files: v1 -->

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
