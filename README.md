# Hopper CLI

Command-line interface for managing Hopper tasks, projects, and instances.

## Installation

```bash
pip install -e .
```

## Quick Start

```bash
# Initialize Hopper configuration
hopper init

# Create a task
hopper task add "Fix login bug"

# List tasks
hopper task list

# Get help
hopper --help
```

## Features

- **Task Management**: Create, list, update, and delete tasks
- **Project Management**: Organize tasks into projects
- **Instance Management**: Manage Hopper instances (Global, Project, Orchestration)
- **Rich Terminal Output**: Beautiful tables and colored output
- **JSON Mode**: Machine-readable output for scripting
- **Configuration Profiles**: Multiple environment support (dev, prod, etc.)

## Configuration

Configuration is stored in `~/.hopper/config.yaml`:

```yaml
active_profile: default
profiles:
  default:
    api:
      endpoint: http://localhost:8000
      timeout: 30
    auth:
      token: your-token-here
```

## Commands

### Task Management

```bash
hopper task add "Task title"          # Create task
hopper task list                      # List tasks
hopper task get <id>                  # Get task details
hopper task update <id>               # Update task
hopper task status <id> <status>      # Change status
hopper task delete <id>               # Delete task
hopper task search <query>            # Search tasks
```

### Project Management

```bash
hopper project create                 # Create project
hopper project list                   # List projects
hopper project get <id>               # Get project details
hopper project update <id>            # Update project
hopper project delete <id>            # Delete project
```

### Instance Management

```bash
hopper instance create                # Create instance
hopper instance list                  # List instances
hopper instance tree                  # Show instance hierarchy
hopper instance start <id>            # Start instance
hopper instance stop <id>             # Stop instance
hopper instance status <id>           # Get instance status
```

### Configuration

```bash
hopper init                           # Initialize configuration
hopper config get <key>               # Get config value
hopper config set <key> <value>       # Set config value
hopper config list                    # List configuration
hopper auth login                     # Authenticate
hopper auth logout                    # Clear credentials
hopper auth status                    # Check auth status
```

## Global Options

- `--config, -c`: Path to configuration file
- `--verbose, -v`: Enable verbose output
- `--json`: Output in JSON format
- `--help`: Show help message

## Development

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/ tests/

# Lint code
ruff check src/ tests/

# Type check
mypy src/
```

## License

MIT
