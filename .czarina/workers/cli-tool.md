# Worker: CLI Tool

**Branch:** cz1/feat/cli-tool
**Dependencies:** api-core
**Duration:** 2 days

## Mission

Build a powerful CLI tool for managing Hopper tasks, projects, and instances. This provides a developer-friendly interface for power users and automation.

## Background

Phase 1 Week 2 includes CLI implementation with:
- Task management commands (`hopper add`, `hopper list`, etc.)
- Project and instance management
- Configuration management
- Rich terminal output with formatting
- Interactive prompts for complex operations

## Tasks

### Task 1: CLI Framework Setup

1. Create `src/hopper/cli/main.py`:
   - Click application setup
   - Command groups
   - Global options (--config, --verbose, --json)
   - Version information

2. Create `src/hopper/cli/config.py`:
   - CLI configuration management
   - API endpoint configuration
   - Authentication token storage
   - Profile support (dev, prod, etc.)

3. Create `src/hopper/cli/client.py`:
   - HTTP client wrapper for API
   - Authentication handling
   - Error handling and retries
   - Response parsing

4. Create `src/hopper/cli/output.py`:
   - Rich terminal output utilities
   - Table formatting
   - Color-coded status
   - JSON output mode
   - Progress bars and spinners

5. Create `src/hopper/cli/__init__.py`:
   - Export CLI app

**Checkpoint:** Commit CLI framework

### Task 2: Task Management Commands

Reference: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (CLI requirements)

1. Create `src/hopper/cli/commands/task.py`:
   - `hopper task add` - Create a new task
     - Interactive prompts for title, description, priority
     - Support for tags (--tag or -t)
     - Project assignment (--project or -p)
     - Quick mode with just title: `hopper task add "Fix bug"`

   - `hopper task list` - List tasks
     - Filter by status (--status)
     - Filter by priority (--priority)
     - Filter by project (--project)
     - Filter by tags (--tag)
     - Sort options (--sort-by)
     - Output formats: table (default), json, compact

   - `hopper task get <task_id>` - Get task details
     - Show full task information
     - Show routing history
     - Show related tasks

   - `hopper task update <task_id>` - Update task
     - Update title (--title)
     - Update description (--description)
     - Update priority (--priority)
     - Add/remove tags (--add-tag, --remove-tag)
     - Interactive mode for multiple changes

   - `hopper task status <task_id> <new_status>` - Change status
     - Validate status transitions
     - Confirm before status change
     - Show status history

   - `hopper task delete <task_id>` - Delete task
     - Confirmation prompt
     - Soft delete
     - Force delete option (--force)

   - `hopper task search <query>` - Search tasks
     - Full-text search
     - Search in title and description
     - Filter search results

2. Add helpful shortcuts:
   - `hopper add` → `hopper task add`
   - `hopper ls` → `hopper task list`

**Checkpoint:** Commit task commands

### Task 3: Project Management Commands

1. Create `src/hopper/cli/commands/project.py`:
   - `hopper project create` - Create new project
     - Interactive prompts for name, description
     - Configuration setup

   - `hopper project list` - List projects
     - Show project statistics (task counts)
     - Table or JSON output

   - `hopper project get <project_id>` - Get project details
     - Show project configuration
     - Show task summary
     - Show recent activity

   - `hopper project update <project_id>` - Update project
     - Update configuration
     - Interactive mode

   - `hopper project delete <project_id>` - Delete project
     - Confirmation with task count warning
     - Handle tasks (reassign or delete)

   - `hopper project tasks <project_id>` - List project tasks
     - Same filtering as `task list`

**Checkpoint:** Commit project commands

### Task 4: Instance Management Commands

1. Create `src/hopper/cli/commands/instance.py`:
   - `hopper instance create` - Create Hopper instance
     - Scope selection (global, project, orchestration)
     - Parent instance selection
     - Configuration

   - `hopper instance list` - List instances
     - Filter by scope
     - Show hierarchy

   - `hopper instance get <instance_id>` - Get instance details
     - Show configuration
     - Show child instances
     - Show task queue

   - `hopper instance tree` - Show instance hierarchy
     - ASCII tree visualization
     - Color-coded by scope

   - `hopper instance start <instance_id>` - Start instance
   - `hopper instance stop <instance_id>` - Stop instance
   - `hopper instance status <instance_id>` - Get instance status

**Checkpoint:** Commit instance commands

### Task 5: Configuration and Setup Commands

1. Create `src/hopper/cli/commands/config.py`:
   - `hopper init` - Initialize Hopper configuration
     - Create config directory
     - Set up API endpoint
     - Generate API key
     - Test connection

   - `hopper config get <key>` - Get configuration value
   - `hopper config set <key> <value>` - Set configuration value
   - `hopper config list` - List all configuration

   - `hopper auth login` - Authenticate with API
     - Get JWT token or API key
     - Store credentials securely

   - `hopper auth logout` - Clear credentials

   - `hopper auth status` - Check authentication status

2. Create `src/hopper/cli/commands/server.py`:
   - `hopper server start` - Start Hopper API server
   - `hopper server stop` - Stop API server
   - `hopper server status` - Check server status
   - `hopper server logs` - Tail server logs

**Checkpoint:** Commit configuration commands

### Task 6: Testing and Documentation

1. Create `tests/cli/conftest.py`:
   - CLI test runner fixture
   - Mock API responses
   - Temporary config directory

2. Create `tests/cli/test_task_commands.py`:
   - Test all task commands
   - Test command parsing
   - Test output formatting
   - Test error handling

3. Create `tests/cli/test_project_commands.py`:
   - Test all project commands

4. Create `tests/cli/test_instance_commands.py`:
   - Test all instance commands

5. Create `tests/cli/test_config_commands.py`:
   - Test configuration management
   - Test authentication

6. Create `tests/cli/test_output.py`:
   - Test table formatting
   - Test JSON output
   - Test color output

7. Create `docs/cli-guide.md`:
   - CLI overview
   - Installation instructions
   - Command reference with examples
   - Configuration guide
   - Common workflows
   - Troubleshooting

8. Add shell completion:
   - Bash completion script
   - Zsh completion script
   - Fish completion script
   - Installation instructions

**Checkpoint:** Commit tests and documentation

## Deliverables

- [ ] CLI framework with Click and Rich
- [ ] Task management commands (add, list, get, update, status, delete, search)
- [ ] Project management commands
- [ ] Instance management commands
- [ ] Configuration and authentication commands
- [ ] Server management commands
- [ ] Rich terminal output with colors and tables
- [ ] JSON output mode for scripting
- [ ] Shell completion scripts
- [ ] Comprehensive test suite
- [ ] CLI user guide with examples

## Success Criteria

- ✅ `hopper --help` shows all commands
- ✅ `hopper task add "Fix bug"` creates a task
- ✅ `hopper task list` shows tasks in a nice table
- ✅ `hopper task list --json` outputs JSON
- ✅ Can filter and search tasks effectively
- ✅ Can manage projects via CLI
- ✅ Can manage instances via CLI
- ✅ `hopper init` sets up configuration
- ✅ Authentication works with stored credentials
- ✅ Error messages are clear and helpful
- ✅ All commands have `--help` documentation
- ✅ Shell completion works
- ✅ Tests pass with good coverage

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md`
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- Click documentation: https://click.palletsprojects.com/
- Rich documentation: https://rich.readthedocs.io/

## Notes

- Use Click for command framework (integrates well with FastAPI ecosystem)
- Use Rich for beautiful terminal output
- Configuration file should be in `~/.hopper/config.yaml` or similar
- Store API keys securely (consider using keyring library)
- Support environment variables for configuration (12-factor app)
- Interactive prompts should have sensible defaults
- JSON mode should be parseable by jq and other tools
- Consider adding `--dry-run` flag for destructive operations
- Color output should be disabled when piped or in CI
- Progress indicators for long-running operations
- Consider adding plugin system for custom commands (future)
