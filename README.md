# Hopper

**Intelligent Task Routing and Orchestration System for Multi-Agent Workflows**

Hopper is a universal, multi-instance, hierarchical task queue designed for human-AI collaborative workflows. It intelligently routes tasks to appropriate AI agents, manages project context, and learns from routing decisions over time.

## Features

- **Universal Intake**: Tasks from any source (MCP, CLI, HTTP, webhooks)
- **Intelligent Routing**: Rules-based, LLM-powered, or Sage-managed strategies
- **Multi-Instance Architecture**: Global → Project → Orchestration hierarchy
- **3-Tier Memory System**: Working → Episodic → Consolidated memory
- **Platform Integration**: Bidirectional sync with GitHub/GitLab
- **Federation Support**: Multi-Hopper coordination

## Quick Start

### Prerequisites

- Python 3.11 or higher
- Docker and Docker Compose (for development environment)
- Git

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd hopper
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package in development mode:
```bash
pip install -e ".[dev]"
```

### Development Setup

1. Start the development environment:
```bash
docker-compose up -d
```

2. Run database migrations:
```bash
alembic upgrade head
```

3. Run tests:
```bash
pytest
```

### Running Hopper

#### CLI
```bash
hopper add "Implement user authentication"
hopper list
hopper route <task-id>
```

#### API Server
```bash
uvicorn hopper.api.main:app --reload
```

Visit http://localhost:8000/docs for the interactive API documentation.

#### MCP Server
Configure in Claude Desktop's `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "hopper": {
      "command": "hopper",
      "args": ["mcp-server"]
    }
  }
}
```

## Project Structure

```
hopper/
├── src/hopper/          # Main package
│   ├── models/          # SQLAlchemy data models
│   ├── api/             # FastAPI REST API
│   ├── mcp/             # MCP server implementation
│   ├── cli/             # Command-line interface
│   ├── intelligence/    # Routing strategies
│   ├── memory/          # Memory systems
│   └── config/          # Configuration management
├── tests/               # Test suite
├── docs/                # Documentation
├── scripts/             # Utility scripts
└── pyproject.toml       # Project configuration
```

## Development

### Code Quality

Format code with Black:
```bash
black src/ tests/
```

Lint with Ruff:
```bash
ruff check src/ tests/
```

Type check with mypy:
```bash
mypy src/
```

### Running Tests

Run all tests:
```bash
pytest
```

With coverage:
```bash
pytest --cov=hopper --cov-report=html
```

## Documentation

- [Specification](docs/Hopper.Specification.md)
- [Implementation Plan](plans/Hopper-Implementation-Plan.md)
- [API Documentation](http://localhost:8000/docs) (when running)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

MIT License - See LICENSE file for details

## Status

**Current Phase**: Phase 1 - Core Foundation
**Version**: 0.1.0 (Alpha)
