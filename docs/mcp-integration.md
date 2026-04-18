# Hopper MCP Integration

Guide for connecting Hopper to Claude Web and other MCP clients via SSE.

## Overview

Hopper exposes an MCP (Model Context Protocol) server over SSE (Server-Sent Events) at `/mcp/sse/` on the main API server. This lets Claude Web and other remote MCP clients manage tasks, send heartbeats, search patterns, and submit feedback — all without a local Hopper install.

## Quick Start

1. **Start the server** (runs API + MCP + upstream sync on one port):
   ```bash
   hopper server start --host 0.0.0.0 --port 8080
   ```

2. **Register a token** (links your DID identity to a Bearer token):
   ```bash
   hopper mcp init-token --server https://your-server.com
   # Output: hpr_abc123...
   ```

3. **Add to Claude Web** (Settings → MCP Servers):
   ```json
   {
     "type": "url",
     "url": "https://your-server.com/mcp/sse/",
     "name": "hopper",
     "authorization_token": "hpr_abc123..."
   }
   ```

## Server Setup

The unified Hopper server runs on a single port and provides:

| Path | Description |
|------|-------------|
| `/health` | Health check |
| `/docs` | Interactive API docs |
| `/mcp/sse/` | MCP SSE endpoint (Claude Web) |
| `/mcp/register` | Token registration |
| `/mcp/tokens` | List your tokens |
| `/upstream/sync` | DID-authenticated task sync |
| `/upstream/admin/*` | DID registry management |
| `/api/v1/tasks` | REST task API |

### Systemd (auto-start on boot)

The server ships with a systemd user unit:

```bash
systemctl --user enable hopper-upstream.service
systemctl --user start hopper-upstream.service
systemctl --user status hopper-upstream.service
```

The unit file is at `~/.config/systemd/user/hopper-upstream.service`.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOPPER_MCP_TOKEN` | — | Simple shared Bearer token (dev/legacy) |
| `HOPPER_MCP_ALLOWED_DIDS` | — | Comma-separated list of allowed DIDs |
| `HOPPER_MCP_DID_OPEN` | `false` | Allow any valid DID signature |
| `HOPPER_SERVER_PATH` | `~/.hopper` | Token store location |
| `HOPPER_UPSTREAM_STORAGE` | `~/.hopper/upstream-data` | Upstream sync data directory |

## Authentication

Three methods are supported, checked in order:

### 1. Registered Token (recommended)

Tokens are DID-linked `hpr_` Bearer tokens. Generate with `hopper mcp init-token`.

**Multiple instances**: register separate tokens per project:
```bash
hopper mcp init-token -s https://server.com -i work -p /path/to/work/.hopper
hopper mcp init-token -s https://server.com -i personal
```

Each token routes MCP tool calls to the right `.hopper` directory.

### 2. DID Auth (direct cryptographic)

```
Authorization: DID did:key:z6Mk... <base64-signature>
```

Set `HOPPER_MCP_ALLOWED_DIDS` to restrict which DIDs can connect, or `HOPPER_MCP_DID_OPEN=true` for any valid signature.

### 3. Simple Token (dev/legacy)

```bash
export HOPPER_MCP_TOKEN="your-secret"
```

Pass as `authorization_token` in the MCP config. No DID identity — all requests share one storage path.

### No Auth

If none of the above are configured, the server allows unauthenticated access. Suitable for localhost-only deployments.

## MCP Tools

### Task Management

| Tool | Description |
|------|-------------|
| `hopper_create_task` | Create a task (title, description, priority, tags) |
| `hopper_list_tasks` | List with filters (status, priority, tags, limit) |
| `hopper_get_task` | Get a task by ID (supports prefix matching) |
| `hopper_update_task` | Update any fields including assignment and parent |
| `hopper_update_task_status` | Quick status change |
| `hopper_delete_task` | Permanently delete a task |
| `hopper_search_tasks` | Full-text search across titles and descriptions |
| `hopper_heartbeat` | Signal still working (prevents stale detection) |
| `hopper_list_stale_tasks` | Find tasks with silent/timed-out agents |
| `hopper_get_task_children` | List subtasks with rollup |

### Instance / Project

| Tool | Description |
|------|-------------|
| `hopper_list_instances` | List Hopper instances |
| `hopper_list_projects` | List projects |

### Pattern & Learning

| Tool | Description |
|------|-------------|
| `hopper_match_patterns` | Find routing patterns matching tags/text/priority |
| `hopper_submit_feedback` | Rate a task's routing/execution |
| `hopper_get_learning_statistics` | Overall learning stats |
| `hopper_list_patterns` | List routing patterns |
| `hopper_create_pattern` | Create a new routing pattern |

## Token Management

```bash
# Generate token
hopper mcp init-token --server https://your-server.com

# List your tokens
hopper mcp tokens --server https://your-server.com

# Revoke a token (by prefix)
hopper mcp revoke hpr_abc123 --server https://your-server.com
```

## Claude Desktop (stdio mode)

For local Claude Desktop (not Claude Web), use stdio transport instead:

```json
{
  "mcpServers": {
    "hopper": {
      "command": "hopper",
      "args": ["mcp", "start"],
      "env": {
        "HOPPER_API_BASE_URL": "http://localhost:8080"
      }
    }
  }
}
```

The stdio MCP server connects to the local API server and proxies tool calls through it.

## Troubleshooting

**SSE connection refused**: Check `hopper server status` or `systemctl --user status hopper-upstream.service`.

**401 Unauthorized**: Token may be expired or stored in wrong path. Run `hopper mcp init-token` again.

**403 DID not authorized**: If `HOPPER_MCP_ALLOWED_DIDS` is set, your DID isn't on the list.

**Tools return errors**: Check that `~/.hopper/` exists and is writable. Run `hopper task list` locally to verify storage is healthy.
