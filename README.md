# Hopper - Intelligent Task Routing & Orchestration

**Universal task queue for human-AI collaborative workflows**

Hopper is an intelligent task management system that routes work to the right destinations (GitHub, GitLab, Jira, etc.) and supports AI orchestration systems as first-class executors.

## Features

- **Universal Intake**: Create tasks from anywhere (MCP, CLI, HTTP API, webhooks)
- **Intelligent Routing**: Automatically route tasks based on content and learned patterns
- **Multi-Executor Support**: Route to humans, AI systems (Czarina, SARK), or other executors
- **Bidirectional Sync**: Keep GitHub/GitLab issues in sync with Hopper
- **Learning Memory**: Improve routing over time with feedback loops
- **MCP Integration**: Zero-friction task capture from Claude conversations

## Quick Start

### Installation

```bash
pip install hopper
```

### Configure for Claude Desktop

```bash
# Generate MCP configuration
hopper mcp config

# Test configuration
hopper mcp test

# Start MCP server
hopper mcp start
```

See [docs/mcp-integration.md](docs/mcp-integration.md) for complete setup instructions.

## Usage

### Creating Tasks from Claude

Simply say: "Put this in Hopper" during any conversation with Claude

```
User: "We should add dark mode to the web interface"
Claude: "Want me to add that to Hopper?"
User: "Yes"
Claude: ✅ Task created and routed to web-frontend
```

### CLI Usage

```bash
# Create a task
hopper task create "Add user authentication" --project backend

# List tasks
hopper task list --status pending

# Route a task
hopper task route task-123 --project backend
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Intake Layer                        │
│  MCP · CLI · HTTP API · Email · Webhooks               │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                 Hopper Core                             │
│  • Task Storage (SQLite/PostgreSQL)                    │
│  • Routing Engine (Rules + Learning + LLM)            │
│  • Memory System (Episodic + Semantic + Procedural)    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│                Execution Layer                          │
│  GitHub · GitLab · Jira · Czarina · SARK · Humans     │
└─────────────────────────────────────────────────────────┘
```

## MCP Tools

The Hopper MCP server provides:

### Task Management
- `hopper_create_task` - Create tasks with auto-routing
- `hopper_list_tasks` - List and filter tasks
- `hopper_get_task` - Get task details
- `hopper_update_task` - Update task fields
- `hopper_update_task_status` - Change task status

### Project Management
- `hopper_list_projects` - List registered projects
- `hopper_get_project` - Get project details
- `hopper_create_project` - Register new projects
- `hopper_get_project_tasks` - Get tasks for a project

### Routing
- `hopper_route_task` - Manually route tasks
- `hopper_get_routing_suggestions` - Preview routing

## MCP Resources

Browse Hopper data via URIs:

- `hopper://tasks` - All tasks
- `hopper://tasks/pending` - Pending tasks
- `hopper://tasks/{id}` - Specific task
- `hopper://projects` - All projects
- `hopper://projects/{id}` - Specific project

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/hopper.git
cd hopper

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run with coverage
pytest --cov=hopper tests/
```

### Project Structure

```
hopper/
├── src/hopper/
│   ├── api/          # FastAPI REST API
│   ├── cli/          # Click CLI commands
│   ├── mcp/          # MCP server implementation
│   │   ├── server.py
│   │   ├── tools/    # MCP tool modules
│   │   └── resources/# MCP resource modules
│   ├── models/       # Data models
│   ├── intelligence/ # Routing and learning
│   ├── memory/       # Memory system
│   └── config/       # Configuration
├── tests/           # Test suite
├── docs/            # Documentation
└── .hopper/         # Configuration files
```

## Testing

```bash
# Run all tests
pytest

# Run MCP tests only
pytest tests/mcp/

# Run with coverage
pytest --cov=hopper --cov-report=html

# Test MCP server
hopper mcp test
```

## Configuration

Environment variables:

```bash
# API Configuration
HOPPER_API_BASE_URL=http://localhost:8080
HOPPER_API_TOKEN=your-token

# MCP Server
HOPPER_AUTO_ROUTE_TASKS=true
HOPPER_DEFAULT_PRIORITY=medium
HOPPER_LOG_LEVEL=INFO
```

See [.hopper/mcp-server.json](.hopper/mcp-server.json) for complete configuration options.

## Documentation

- [MCP Integration Guide](docs/mcp-integration.md) - Complete MCP setup and usage
- [Architecture](docs/architecture.md) - System design and components
- [API Reference](docs/api-reference.md) - REST API documentation

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- Issues: https://github.com/your-org/hopper/issues
- Discussions: https://github.com/your-org/hopper/discussions
- Discord: https://discord.gg/hopper

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern web framework
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
- [Click](https://click.palletsprojects.com/) - CLI framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
