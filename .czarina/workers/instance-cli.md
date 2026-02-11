# Worker Identity: instance-cli

**Role:** Code
**Agent:** claude
**Branch:** cz2/feat/instance-cli
**Phase:** 2
**Dependencies:** scope-behaviors

## Mission

Build CLI commands for instance management and visualization. Create an intuitive command-line interface for managing Hopper instances, viewing the instance hierarchy as a tree, and monitoring instance status. This gives users full control over multi-instance Hopper from the terminal.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/instance-cli-knowledge.md`

This includes:
- Click CLI framework patterns
- Rich library for terminal visualization
- CLI testing patterns
- Command organization best practices

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Examine the existing CLI structure and patterns:**

```bash
# Look at the CLI structure
ls -la src/hopper/cli/
ls -la src/hopper/cli/commands/

# Read the main CLI entry point
cat src/hopper/cli/main.py

# Read an existing command file for the pattern
cat src/hopper/cli/commands/tasks.py 2>/dev/null || cat $(ls src/hopper/cli/commands/*.py | head -1)

# Check how Rich is used in the project
grep -r "from rich" src/hopper/ | head -10
```

**Then:** Create `src/hopper/cli/commands/instances.py` starting with the `list` and `tree` commands.

## Objectives

1. **Create Instance Commands** (`src/hopper/cli/commands/instances.py`)
   ```python
   @click.group()
   def instance():
       """Manage Hopper instances."""

   @instance.command()
   def list(): ...      # List instances (with filters)

   @instance.command()
   def create(): ...    # Create instance

   @instance.command()
   def show(): ...      # Show instance details

   @instance.command()
   def tree(): ...      # Show hierarchy tree

   @instance.command()
   def start(): ...     # Start instance

   @instance.command()
   def stop(): ...      # Stop instance

   @instance.command()
   def status(): ...    # Status dashboard
   ```

2. **Implement Tree Visualization** (using Rich)
   ```
   $ hopper instance tree

   hopper-global (GLOBAL) [running]
   ├── czarina (PROJECT) [running]
   │   ├── czarina-run-001 (ORCHESTRATION) [running] - 5 tasks
   │   └── czarina-run-002 (ORCHESTRATION) [stopped]
   └── sark (PROJECT) [running]
       └── sark-analysis (ORCHESTRATION) [running] - 2 tasks
   ```

3. **Implement Status Dashboard**
   ```
   $ hopper instance status

   ┌─────────────────────────────────────────────────────┐
   │ Hopper Instance Status                              │
   ├─────────────────────────────────────────────────────┤
   │ Global: hopper-global                    [running]  │
   │ Projects: 3 active, 1 stopped                       │
   │ Orchestrations: 4 active, 2 stopped                 │
   │ Total Tasks: 127 (42 in progress)                   │
   └─────────────────────────────────────────────────────┘
   ```

4. **Add Instance Filtering to Task Commands**
   - `hopper task list --instance=czarina-run-001`
   - `hopper task add "..." --instance=czarina`

5. **Add Delegation Commands**
   - `hopper task delegate <task-id> --to=<instance-id>`
   - `hopper task delegations <task-id>` - Show delegation chain

6. **Register Commands in Main CLI**
   - Add instance command group to main.py
   - Ensure proper command organization

7. **Write Tests**
   - `tests/cli/test_instance_commands.py`
   - Test all commands with mock API calls
   - Test tree visualization output
   - Test status dashboard output

## Deliverables

- [ ] `src/hopper/cli/commands/instances.py` - Instance commands
- [ ] Tree visualization with Rich
- [ ] Status dashboard
- [ ] Updated `src/hopper/cli/main.py` - Commands registered
- [ ] Updated task commands with instance filtering
- [ ] Delegation CLI commands
- [ ] `tests/cli/test_instance_commands.py` - Unit tests

## Success Criteria

- [ ] Can manage instances entirely from CLI
- [ ] Tree visualization clearly shows hierarchy with colors and status
- [ ] Status dashboard provides quick overview at a glance
- [ ] Instance filtering works on all relevant commands
- [ ] All commands have proper help text and examples
- [ ] 90%+ test coverage on new code

## Context

### CLI Architecture

The Hopper CLI uses:
- **Click** - Command line framework
- **Rich** - Terminal formatting and visualization
- **httpx** or similar for API calls

### Command Categories

```
hopper instance list          # List all instances
hopper instance tree          # Show hierarchy tree
hopper instance create        # Create new instance
hopper instance show <id>     # Show instance details
hopper instance start <id>    # Start instance
hopper instance stop <id>     # Stop instance
hopper instance status        # Dashboard view

hopper task list --instance=<id>    # Filter tasks by instance
hopper task delegate <task> --to=<instance>  # Delegate task
hopper task delegations <task>      # Show delegation chain
```

### Rich Tree Example

```python
from rich.tree import Tree
from rich.console import Console

console = Console()

tree = Tree("hopper-global (GLOBAL) [green][running][/green]")
czarina = tree.add("czarina (PROJECT) [green][running][/green]")
czarina.add("czarina-run-001 (ORCHESTRATION) [green][running][/green] - 5 tasks")
czarina.add("czarina-run-002 (ORCHESTRATION) [red][stopped][/red]")

console.print(tree)
```

### Status Colors

- 🟢 RUNNING - green
- 🟡 STARTING/STOPPING - yellow
- 🔴 STOPPED/ERROR - red
- ⚪ CREATED - white
- 🟠 PAUSED - orange

### Existing CLI Patterns

Look at existing commands for:
- Option/argument handling
- Error handling and user feedback
- Output formatting
- API client usage

## Notes

- Use Rich's Tree, Panel, and Table for visualization
- Add `--format` option for json/table/tree output where appropriate
- Include `--quiet` and `--verbose` flags
- Support both ID and name for instance identification
- Add confirmation prompts for destructive operations (stop, delete)
- Consider adding shell completion support
