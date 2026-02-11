"""Rich terminal output utilities."""

import json
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()


# Status color mapping
STATUS_COLORS = {
    "open": "blue",
    "in_progress": "yellow",
    "blocked": "red",
    "completed": "green",
    "cancelled": "dim",
    "pending": "cyan",
    "active": "green",
    "inactive": "dim",
    "running": "green",
    "stopped": "red",
    # Instance statuses
    "created": "cyan",
    "starting": "yellow",
    "stopping": "yellow",
    "paused": "yellow",
    "error": "red",
    "terminated": "dim",
    # Delegation statuses
    "accepted": "green",
    "rejected": "red",
}

# Priority color mapping
PRIORITY_COLORS = {
    "low": "dim",
    "medium": "blue",
    "high": "yellow",
    "urgent": "red",
}


def print_json(data: Any) -> None:
    """Print data as formatted JSON.

    Args:
        data: Data to print as JSON
    """
    console.print_json(json.dumps(data, default=str, indent=2))


def format_datetime(dt: datetime | str | None) -> str:
    """Format datetime for display.

    Args:
        dt: Datetime object or ISO string

    Returns:
        Formatted datetime string
    """
    if dt is None:
        return "—"

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return dt

    now = datetime.now(dt.tzinfo)
    diff = now - dt

    if diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds >= 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds >= 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "just now"


def get_status_style(status: str) -> str:
    """Get Rich style for a status.

    Args:
        status: Status string

    Returns:
        Rich style string
    """
    color = STATUS_COLORS.get(status.lower(), "white")
    return f"bold {color}"


def get_priority_style(priority: str) -> str:
    """Get Rich style for a priority.

    Args:
        priority: Priority string

    Returns:
        Rich style string
    """
    color = PRIORITY_COLORS.get(priority.lower(), "white")
    return f"bold {color}"


def print_task_table(tasks: list[dict[str, Any]], compact: bool = False) -> None:
    """Print tasks as a formatted table.

    Args:
        tasks: List of task dictionaries
        compact: Use compact layout
    """
    if not tasks:
        console.print("[dim]No tasks found[/dim]")
        return

    table = Table(
        box=box.SIMPLE if compact else box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )

    # Add columns
    table.add_column("ID", style="dim", width=8)
    table.add_column("Title", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Priority", justify="center")

    if not compact:
        table.add_column("Project", style="dim")
        table.add_column("Tags", style="dim")
        table.add_column("Created", style="dim", justify="right")

    # Add rows
    for task in tasks:
        task_id = str(task.get("id", ""))[:8]
        title = task.get("title", "")
        status = task.get("status", "unknown")
        priority = task.get("priority", "medium")

        # Truncate title if too long
        if len(title) > 50 and compact:
            title = title[:47] + "..."

        row = [
            task_id,
            title,
            f"[{get_status_style(status)}]{status}[/]",
            f"[{get_priority_style(priority)}]{priority}[/]",
        ]

        if not compact:
            project = task.get("project", {}).get("name", "—")
            tags = ", ".join(task.get("tags", [])) or "—"
            created = format_datetime(task.get("created_at"))
            row.extend([project, tags, created])

        table.add_row(*row)

    console.print(table)


def print_task_detail(task: dict[str, Any]) -> None:
    """Print detailed task information.

    Args:
        task: Task dictionary
    """
    status = task.get("status", "unknown")
    priority = task.get("priority", "medium")

    console.print(f"\n[bold cyan]Task {task.get('id', '')}[/bold cyan]")
    console.print(f"[bold]{task.get('title', '')}[/bold]\n")

    # Status and priority
    console.print(
        f"Status: [{get_status_style(status)}]{status}[/]  "
        f"Priority: [{get_priority_style(priority)}]{priority}[/]"
    )

    # Description
    if description := task.get("description"):
        console.print(f"\n[bold]Description:[/bold]\n{description}")

    # Project
    if project := task.get("project"):
        console.print(f"\n[bold]Project:[/bold] {project.get('name', '')}")

    # Tags
    if tags := task.get("tags"):
        console.print(f"[bold]Tags:[/bold] {', '.join(tags)}")

    # Metadata
    console.print(f"\n[dim]Created: {format_datetime(task.get('created_at'))}[/dim]")
    if updated_at := task.get("updated_at"):
        console.print(f"[dim]Updated: {format_datetime(updated_at)}[/dim]")

    console.print()


def print_project_table(projects: list[dict[str, Any]]) -> None:
    """Print projects as a formatted table.

    Args:
        projects: List of project dictionaries
    """
    if not projects:
        console.print("[dim]No projects found[/dim]")
        return

    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")

    table.add_column("ID", style="dim", width=8)
    table.add_column("Name", style="bold")
    table.add_column("Description", style="dim")
    table.add_column("Tasks", justify="center")
    table.add_column("Created", style="dim", justify="right")

    for project in projects:
        project_id = str(project.get("id", ""))[:8]
        name = project.get("name", "")
        description = project.get("description", "")
        task_count = project.get("task_count", 0)
        created = format_datetime(project.get("created_at"))

        # Truncate description
        if len(description) > 50:
            description = description[:47] + "..."

        table.add_row(project_id, name, description, str(task_count), created)

    console.print(table)


def print_instance_tree(instances: list[dict[str, Any]], show_tasks: bool = True) -> None:
    """Print instance hierarchy as a tree.

    Args:
        instances: List of instance dictionaries
        show_tasks: Show task counts per instance
    """
    if not instances:
        console.print("[dim]No instances found[/dim]")
        return

    # Build tree structure
    tree = Tree("[bold cyan]Hopper Instances[/bold cyan]")

    # Group by parent
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for instance in instances:
        parent_id = instance.get("parent_id")
        if parent_id not in by_parent:
            by_parent[parent_id] = []
        by_parent[parent_id].append(instance)

    def add_instances(parent_node: Tree, parent_id: str | None) -> None:
        """Recursively add instances to tree."""
        for instance in by_parent.get(parent_id, []):
            scope = instance.get("scope", "unknown")
            name = instance.get("name", "")
            status = instance.get("status", "inactive")
            instance_id = instance.get("id", "")

            # Color-code by scope
            scope_colors = {
                "global": "magenta",
                "project": "blue",
                "orchestration": "green",
            }
            scope_color = scope_colors.get(scope.lower(), "white")

            # Build label with name, scope, and status
            label = (
                f"[{scope_color}]{name}[/{scope_color}] "
                f"[dim]({scope})[/dim] "
                f"[{get_status_style(status)}]{status}[/]"
            )

            # Add task count if available and enabled
            if show_tasks:
                task_count = instance.get("task_count", 0)
                active_task_count = instance.get("active_task_count", 0)
                if task_count > 0:
                    label += f" [dim]│[/dim] [cyan]{task_count} task(s)[/cyan]"
                    if active_task_count > 0:
                        label += f" [dim]([/dim][yellow]{active_task_count} active[/yellow][dim])[/dim]"

            # Add child instance count if available
            child_count = instance.get("child_instance_count", len(by_parent.get(instance_id, [])))
            if child_count > 0:
                label += f" [dim]│[/dim] [magenta]{child_count} child instance(s)[/magenta]"

            node = parent_node.add(label)
            add_instances(node, instance_id)

    # Add root instances (those with no parent)
    add_instances(tree, None)

    console.print(tree)


def print_success(message: str) -> None:
    """Print success message.

    Args:
        message: Success message
    """
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    """Print error message.

    Args:
        message: Error message
    """
    console.print(f"[bold red]✗[/bold red] {message}", err=True)


def print_warning(message: str) -> None:
    """Print warning message.

    Args:
        message: Warning message
    """
    console.print(f"[bold yellow]![/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print info message.

    Args:
        message: Info message
    """
    console.print(f"[bold blue]ℹ[/bold blue] {message}")
