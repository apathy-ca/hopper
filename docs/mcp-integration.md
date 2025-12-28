# Hopper MCP Integration

Complete guide for using Hopper with Claude Desktop and other MCP clients.

## Overview

The Hopper MCP (Model Context Protocol) server allows Claude and other AI assistants to interact with Hopper for intelligent task routing and orchestration. This enables zero-friction task capture during conversations without requiring context switches.

## Features

### MCP Tools

The Hopper MCP server provides the following tools:

#### Task Management
- `hopper_create_task` - Create a new task with automatic routing
- `hopper_list_tasks` - List and filter tasks by status, priority, project, or tags
- `hopper_get_task` - Get detailed information about a specific task
- `hopper_update_task` - Update task fields (title, description, priority, tags)
- `hopper_update_task_status` - Change task status (pending, in_progress, completed, cancelled)

#### Project Management
- `hopper_list_projects` - List all registered projects
- `hopper_get_project` - Get project details and configuration
- `hopper_create_project` - Register new projects (GitHub, GitLab, etc.)
- `hopper_get_project_tasks` - Get tasks for a specific project

#### Routing
- `hopper_route_task` - Manually route a task to a destination
- `hopper_get_routing_suggestions` - Preview routing decisions before creating tasks

### MCP Resources

Browse Hopper data using URI patterns:

#### Task Resources
- `hopper://tasks` - All tasks
- `hopper://tasks/pending` - Pending tasks only
- `hopper://tasks/in_progress` - In-progress tasks
- `hopper://tasks/completed` - Completed tasks
- `hopper://tasks/{task_id}` - Specific task details

#### Project Resources
- `hopper://projects` - All registered projects
- `hopper://projects/{project_id}` - Project details with recent tasks

## Installation

### Prerequisites

- Python 3.11 or higher
- Hopper API server running (default: http://localhost:8080)
- Claude Desktop or another MCP-compatible client

### Install Hopper

```bash
# Install from source
pip install -e .

# Or install with pip (when published)
pip install hopper
```

### Verify Installation

```bash
hopper mcp test
```

This will verify:
- Python version compatibility
- Required dependencies are installed
- MCP server can be loaded
- Configuration is valid

## Configuration

### Environment Variables

Configure the MCP server using environment variables:

```bash
# API Configuration
export HOPPER_API_BASE_URL="http://localhost:8080"
export HOPPER_API_TOKEN="your-api-token"

# Server Behavior
export HOPPER_AUTO_ROUTE_TASKS="true"
export HOPPER_DEFAULT_PRIORITY="medium"
export HOPPER_DEFAULT_TASK_LIMIT="10"

# Context Management
export HOPPER_ENABLE_CONTEXT_PERSISTENCE="true"
export HOPPER_CONTEXT_CACHE_TTL="3600"

# Logging
export HOPPER_LOG_LEVEL="INFO"
export HOPPER_ENABLE_DEBUG="false"
```

### Claude Desktop Setup

1. **Generate Configuration**

```bash
hopper mcp config
```

This displays the configuration snippet to add to Claude Desktop.

2. **Locate Claude Desktop Config File**

Platform-specific locations:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

3. **Add Hopper to Configuration**

Edit the config file and add:

```json
{
  "mcpServers": {
    "hopper": {
      "command": "python",
      "args": ["-m", "hopper.mcp.main"],
      "env": {
        "HOPPER_API_BASE_URL": "http://localhost:8080",
        "HOPPER_API_TOKEN": "your-api-token-here"
      }
    }
  }
}
```

4. **Restart Claude Desktop**

After updating the configuration, restart Claude Desktop for changes to take effect.

5. **Verify Connection**

In Claude Desktop, the Hopper MCP server should appear in the MCP settings. You can test it by asking Claude to list your tasks:

```
"Can you list my pending tasks from Hopper?"
```

## Usage Examples

### Creating Tasks from Conversations

**User**: "We should add dark mode support to the web interface"

**Claude**: "Good idea! Want me to add that to Hopper?"

**User**: "Yes, put it in Hopper"

**Claude**: [calls hopper_create_task]
```
✅ Task created: "Add dark mode support to web interface"
Task ID: task-abc123
Routed to: web-frontend
Priority: medium
URL: https://github.com/your-org/web-frontend/issues/42
```

### Listing and Filtering Tasks

```
"Show me all high-priority tasks"
"What tasks are in progress?"
"List all tasks tagged with 'bug' in the api project"
```

### Routing Tasks

```
"Route task-abc123 to the backend project"
"Where would you route a task about database migrations?"
```

### Managing Projects

```
"List all registered projects"
"Show me the hopper project details"
"What tasks are pending for the web-frontend project?"
```

## Troubleshooting

### MCP Server Not Appearing in Claude Desktop

1. **Check Configuration File Location**
   ```bash
   hopper mcp config
   ```
   Verify you're editing the correct file path.

2. **Validate JSON Syntax**
   Use a JSON validator to ensure the config file is valid.

3. **Check Logs**
   Claude Desktop logs can help diagnose connection issues.

### Connection Errors

**Issue**: "API Error (401): Unauthorized"

**Solution**: Set a valid API token:
```bash
export HOPPER_API_TOKEN="your-valid-token"
```

**Issue**: "API Error: Connection refused"

**Solution**: Ensure the Hopper API server is running:
```bash
# Check if API is accessible
curl http://localhost:8080/health
```

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
hopper mcp start --debug
```

Or in Claude Desktop config:
```json
{
  "env": {
    "HOPPER_LOG_LEVEL": "DEBUG",
    "HOPPER_ENABLE_DEBUG": "true"
  }
}
```

## Advanced Configuration

### Custom API Endpoint

For production deployments or custom API servers:

```json
{
  "env": {
    "HOPPER_API_BASE_URL": "https://hopper.example.com",
    "HOPPER_API_TOKEN": "${HOPPER_TOKEN}"
  }
}
```

### Disable Auto-Routing

To manually specify projects for all tasks:

```json
{
  "env": {
    "HOPPER_AUTO_ROUTE_TASKS": "false"
  }
}
```

### Custom Defaults

```json
{
  "env": {
    "HOPPER_DEFAULT_PRIORITY": "high",
    "HOPPER_DEFAULT_TASK_LIMIT": "20"
  }
}
```

## Context Management

The MCP server maintains conversation context:

- **Recent Tasks**: Tracks recently created tasks
- **Active Project**: Remembers the current project context
- **Conversation Metadata**: Stores conversation-specific data

Context persists across MCP connections and is stored in `~/.hopper/mcp_context.json`.

### Clearing Context

To clear all context:

```python
# Via API or CLI (when available)
hopper mcp clear-context
```

## Security Considerations

1. **API Token Storage**: Never commit API tokens to version control
2. **Environment Variables**: Use environment variables or secure secret management
3. **Token Rotation**: Regularly rotate API tokens
4. **Network Security**: Use HTTPS for production API endpoints
5. **Access Control**: Restrict API access using tokens with minimal required permissions

## Development and Testing

### Running Tests

```bash
# Test MCP server configuration
hopper mcp test

# Start server with debug logging
hopper mcp start --debug
```

### Testing with MCP Inspector

The MCP Inspector is a useful tool for testing MCP servers:

```bash
# Install MCP Inspector
npm install -g @modelcontextprotocol/inspector

# Run inspector with Hopper
mcp-inspector python -m hopper.mcp.main
```

## API Reference

See the full API documentation for detailed information about:
- Tool parameters and responses
- Resource URI patterns
- Error codes and handling
- Rate limiting and quotas

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/hopper/issues
- Documentation: https://hopper.example.com/docs
- Community: https://discord.gg/hopper

## License

Hopper MCP integration is part of Hopper and is licensed under the MIT License.
