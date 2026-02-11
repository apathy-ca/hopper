# Knowledge Base: instance-cli

Custom knowledge for the Instance CLI worker, extracted from agent-knowledge library.

## Click CLI Framework Patterns

### Command Group Structure

```python
import click
from rich.console import Console

console = Console()

@click.group()
def instance():
    """Manage Hopper instances.

    Create, list, and manage instances across the hierarchy.

    Examples:
        hopper instance list
        hopper instance tree
        hopper instance create --name "my-project" --scope PROJECT
    """
    pass

@instance.command()
@click.option("--scope", type=click.Choice(["GLOBAL", "PROJECT", "ORCHESTRATION"]))
@click.option("--status", type=click.Choice(["running", "stopped", "paused"]))
@click.option("--parent", help="Filter by parent instance ID")
@click.option("--format", type=click.Choice(["table", "json"]), default="table")
def list(scope, status, parent, format):
    """List all instances with optional filters.

    Examples:
        hopper instance list
        hopper instance list --scope PROJECT
        hopper instance list --status running --format json
    """
    # Implementation
    pass

@instance.command()
@click.argument("instance_id")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed output")
def show(instance_id, verbose):
    """Show details for a specific instance.

    Examples:
        hopper instance show abc123
        hopper instance show abc123 --verbose
    """
    pass
```

### Async Commands with Click

```python
import asyncio
from functools import wraps

def async_command(f):
    """Decorator to run async functions in Click commands."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))
    return wrapper

@instance.command()
@click.argument("instance_id")
@async_command
async def start(instance_id):
    """Start an instance."""
    async with get_api_client() as client:
        response = await client.post(f"/api/v1/instances/{instance_id}/start")
        if response.status_code == 200:
            console.print(f"[green]Instance {instance_id} started[/green]")
        else:
            console.print(f"[red]Error: {response.json()['detail']}[/red]")
```

## Rich Library Patterns

### Tree Visualization

```python
from rich.tree import Tree
from rich.console import Console
from rich import print as rprint

console = Console()

def render_instance_tree(root_instance, children_map):
    """Render instance hierarchy as Rich tree.

    Args:
        root_instance: Root HopperInstance
        children_map: Dict mapping instance_id to list of children
    """
    def get_status_color(status):
        colors = {
            "running": "green",
            "starting": "yellow",
            "stopping": "yellow",
            "stopped": "red",
            "paused": "blue",
            "error": "red bold",
            "created": "white",
            "terminated": "dim",
        }
        return colors.get(status, "white")

    def format_instance(inst):
        color = get_status_color(inst.status)
        task_count = inst.runtime_metadata.get("task_count", 0)
        tasks_str = f" - {task_count} tasks" if task_count else ""
        return f"{inst.name} ({inst.scope}) [{color}][{inst.status}][/{color}]{tasks_str}"

    def add_children(tree_node, instance):
        for child in children_map.get(instance.id, []):
            child_node = tree_node.add(format_instance(child))
            add_children(child_node, child)

    tree = Tree(format_instance(root_instance))
    add_children(tree, root_instance)

    console.print(tree)
```

### Status Dashboard with Panels

```python
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich.live import Live

def render_status_dashboard(status_data):
    """Render instance status dashboard."""
    # Main status panel
    status_text = f"""
[bold]Global:[/bold] {status_data['global_name']} [{status_data['global_status']}]
[bold]Projects:[/bold] {status_data['active_projects']} active, {status_data['stopped_projects']} stopped
[bold]Orchestrations:[/bold] {status_data['active_orchestrations']} active
[bold]Total Tasks:[/bold] {status_data['total_tasks']} ({status_data['in_progress_tasks']} in progress)
    """

    main_panel = Panel(
        status_text.strip(),
        title="Hopper Instance Status",
        border_style="blue",
    )

    console.print(main_panel)

def render_instance_table(instances):
    """Render instances as a Rich table."""
    table = Table(title="Instances")

    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="magenta")
    table.add_column("Status")
    table.add_column("Tasks", justify="right")
    table.add_column("Parent")

    for inst in instances:
        status_color = get_status_color(inst.status)
        table.add_row(
            inst.name,
            inst.scope,
            f"[{status_color}]{inst.status}[/{status_color}]",
            str(inst.task_count or 0),
            inst.parent_name or "-",
        )

    console.print(table)
```

### Progress and Spinners

```python
from rich.progress import Progress, SpinnerColumn, TextColumn
import time

def with_spinner(message):
    """Context manager for spinner during operations."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(message, total=None)
        yield progress
        progress.update(task, completed=True)

# Usage
async def create_instance_with_progress(name, scope):
    with with_spinner(f"Creating instance {name}..."):
        result = await api_client.create_instance(name, scope)
    console.print(f"[green]✓[/green] Created instance: {result.id}")
```

## CLI Testing Patterns

### Click Test Runner

```python
from click.testing import CliRunner
import pytest

@pytest.fixture
def cli_runner():
    """Fixture for CLI testing."""
    return CliRunner()

def test_instance_list(cli_runner, mock_api):
    """Test instance list command."""
    mock_api.get_instances.return_value = [
        {"name": "test", "scope": "PROJECT", "status": "running"}
    ]

    result = cli_runner.invoke(instance, ["list"])

    assert result.exit_code == 0
    assert "test" in result.output
    assert "PROJECT" in result.output

def test_instance_tree(cli_runner, mock_api):
    """Test instance tree command."""
    mock_api.get_hierarchy.return_value = {
        "root": {"name": "global", "scope": "GLOBAL"},
        "children": [{"name": "project-1", "scope": "PROJECT"}]
    }

    result = cli_runner.invoke(instance, ["tree"])

    assert result.exit_code == 0
    assert "global" in result.output
    assert "project-1" in result.output
```

### Mocking API Calls

```python
from unittest.mock import AsyncMock, patch

@pytest.fixture
def mock_api():
    """Mock API client for CLI tests."""
    with patch("hopper.cli.commands.instances.api_client") as mock:
        mock.get_instances = AsyncMock()
        mock.get_instance = AsyncMock()
        mock.create_instance = AsyncMock()
        mock.start_instance = AsyncMock()
        mock.stop_instance = AsyncMock()
        yield mock

def test_start_instance_success(cli_runner, mock_api):
    """Test starting an instance."""
    mock_api.start_instance.return_value = {"status": "started"}

    result = cli_runner.invoke(instance, ["start", "instance-123"])

    assert result.exit_code == 0
    assert "started" in result.output.lower()
    mock_api.start_instance.assert_called_once_with("instance-123")

def test_start_instance_not_found(cli_runner, mock_api):
    """Test starting non-existent instance."""
    mock_api.start_instance.side_effect = Exception("Instance not found")

    result = cli_runner.invoke(instance, ["start", "invalid-id"])

    assert result.exit_code != 0 or "not found" in result.output.lower()
```

## Command Organization

### Main CLI Entry Point

```python
# src/hopper/cli/main.py
import click
from hopper.cli.commands.tasks import task
from hopper.cli.commands.instances import instance

@click.group()
@click.version_option()
def cli():
    """Hopper - Intelligent Task Management System.

    Manage tasks and instances across a hierarchical multi-instance system.
    """
    pass

# Register command groups
cli.add_command(task)
cli.add_command(instance)

if __name__ == "__main__":
    cli()
```

### Adding Instance Filter to Task Commands

```python
# Modify existing task command
@task.command()
@click.option("--instance", "-i", help="Filter by instance ID or name")
@click.option("--status", type=click.Choice(["pending", "in_progress", "completed"]))
def list(instance, status):
    """List tasks with optional filters.

    Examples:
        hopper task list
        hopper task list --instance czarina-run-001
        hopper task list --status pending --instance my-project
    """
    filters = {}
    if instance:
        filters["instance_id"] = resolve_instance_id(instance)
    if status:
        filters["status"] = status

    tasks = api_client.get_tasks(**filters)
    render_task_table(tasks)
```

## Delegation CLI Commands

```python
@task.command()
@click.argument("task_id")
@click.option("--to", "target", required=True, help="Target instance ID or name")
@click.option("--type", "delegation_type",
              type=click.Choice(["route", "decompose", "escalate"]),
              default="route")
@async_command
async def delegate(task_id, target, delegation_type):
    """Delegate a task to another instance.

    Examples:
        hopper task delegate task-123 --to project-abc
        hopper task delegate task-123 --to orchestration-001 --type route
    """
    target_id = await resolve_instance_id(target)

    with with_spinner(f"Delegating task {task_id}..."):
        result = await api_client.delegate_task(
            task_id, target_id, delegation_type
        )

    console.print(f"[green]✓[/green] Task delegated to {target}")
    console.print(f"  Delegation ID: {result['delegation_id']}")

@task.command()
@click.argument("task_id")
def delegations(task_id):
    """Show delegation chain for a task.

    Example:
        hopper task delegations task-123
    """
    chain = api_client.get_delegation_chain(task_id)

    if not chain:
        console.print("No delegations for this task")
        return

    console.print(f"\n[bold]Delegation Chain for {task_id}[/bold]\n")

    for i, d in enumerate(chain):
        arrow = "→" if i < len(chain) - 1 else "•"
        status_color = "green" if d.status == "completed" else "yellow"
        console.print(
            f"  {d.source_instance_name} {arrow} {d.target_instance_name} "
            f"[{status_color}][{d.status}][/{status_color}]"
        )
```

## Best Practices

### DO
- Use Rich for all output formatting
- Include `--format json` option for scripting
- Add helpful examples in docstrings
- Use spinners for operations that take time
- Confirm destructive operations (stop, delete)
- Support both ID and name for instance references

### DON'T
- Use print() directly (use console.print)
- Expose raw API errors to users
- Skip error handling for API calls
- Forget help text for commands and options

## References

- Click documentation: https://click.palletsprojects.com/
- Rich documentation: https://rich.readthedocs.io/
- Testing patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/`
