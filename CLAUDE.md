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
