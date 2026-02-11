# Hopper

**Intelligent Task Routing and Orchestration System for Multi-Agent Workflows**

Hopper is a universal, multi-instance, hierarchical task queue designed for human-AI collaborative workflows. It intelligently routes tasks to appropriate AI agents, manages project context, and learns from routing decisions over time.

## Features

### Core (Phase 1)
- **Universal Intake**: Tasks from any source (MCP, CLI, HTTP, webhooks)
- **Intelligent Routing**: Rules-based routing with configurable strategies
- **Task Management**: Full CRUD operations with status tracking, priorities, and tags
- **Project Organization**: Group tasks by project with custom configurations

### Multi-Instance Support (Phase 2)
- **Hierarchical Instances**: Global → Project → Orchestration architecture
- **Task Delegation**: Route tasks down the hierarchy, bubble completion up
- **Scope Behaviors**: Each scope level has specialized routing logic
- **Delegation Tracking**: Full traceability of task movement between instances

### Planned Features
- **3-Tier Memory System**: Working → Episodic → Consolidated memory (Phase 3)
- **LLM Routing**: AI-powered routing decisions (Phase 4)
- **Platform Integration**: Bidirectional sync with GitHub/GitLab (Phase 5)
- **Federation Support**: Multi-Hopper coordination (Phase 6)

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
# Task management
hopper task add "Implement user authentication"
hopper task list
hopper task list --status open --priority high

# Instance management (Phase 2)
hopper instance list
hopper instance tree                    # Show hierarchy
hopper instance create "My Project" --scope project --parent <global-id>
hopper instance start <instance-id>

# Task delegation (Phase 2)
hopper task delegate <task-id> --to <instance-id>
hopper task delegations <task-id>       # Show delegation chain
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
├── src/hopper/              # Main package
│   ├── models/              # SQLAlchemy data models
│   │   ├── task.py          # Task model
│   │   ├── hopper_instance.py  # Instance model
│   │   └── task_delegation.py  # Delegation tracking (Phase 2)
│   ├── api/                 # FastAPI REST API
│   │   └── routes/          # API endpoints
│   │       ├── tasks.py
│   │       ├── instances.py    # Instance CRUD (Phase 2)
│   │       └── delegations.py  # Delegation API (Phase 2)
│   ├── delegation/          # Delegation protocol (Phase 2)
│   │   ├── delegator.py     # Task delegation logic
│   │   ├── router.py        # Instance routing
│   │   └── completion.py    # Completion bubbling
│   ├── intelligence/        # Routing strategies
│   │   ├── rules/           # Rules-based routing
│   │   └── scopes/          # Scope behaviors (Phase 2)
│   ├── mcp/                 # MCP server implementation
│   ├── cli/                 # Command-line interface
│   ├── memory/              # Memory systems
│   └── config/              # Configuration management
├── tests/                   # Test suite
│   └── phase2/              # Phase 2 tests
├── docs/                    # Documentation
├── plans/                   # Implementation plans
└── pyproject.toml           # Project configuration
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
- [Multi-Instance Guide](docs/multi-instance-guide.md) - Hierarchical instance architecture
- [Implementation Plan](plans/Hopper-Implementation-Plan.md)
- [Phase 2 Plan](plans/Phase-2-Multi-Instance-Plan.md) - Multi-instance implementation details
- [API Documentation](http://localhost:8000/docs) (when running)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## License

MIT License - See LICENSE file for details

## Instance Hierarchy

Hopper uses a hierarchical instance architecture:

```
Global Hopper (scope=GLOBAL)
├── Routes tasks to appropriate projects
├── Never executes tasks directly
│
├── Project Hopper: my-project (scope=PROJECT)
│   ├── Decides: handle directly or delegate to orchestration
│   ├── Tracks project-level metrics
│   │
│   └── Orchestration Hopper (scope=ORCHESTRATION)
│       ├── Manages worker task queue
│       └── Executes tasks
│
└── Project Hopper: another-project (scope=PROJECT)
    └── ...
```

**Task Flow:**
1. Tasks enter at Global level
2. Global routes to appropriate Project based on content/tags
3. Project decides: handle directly or delegate to Orchestration
4. Orchestration executes and reports completion
5. Completion bubbles back up the chain

See [Multi-Instance Guide](docs/multi-instance-guide.md) for details.

## Status

**Current Phase**: Phase 2 - Multi-Instance Support (Complete)
**Version**: 2.0.0

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | Complete | Core Foundation |
| Phase 2 | Complete | Multi-Instance Support |
| Phase 3 | Planned | Memory & Learning |
| Phase 4 | Planned | Intelligence Layer (LLM) |
| Phase 5 | Planned | Platform Integration |
| Phase 6 | Planned | Federation |
