"""Rich terminal output utilities."""

import json
from datetime import datetime
from typing import Any

from rich import box
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

console = Console()
error_console = Console(stderr=True)


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


def _lerp_color(ratio: float) -> tuple[int, int, int]:
    """Interpolate green→yellow→red for a 0.0–1.0+ ratio."""
    ratio = max(0.0, min(ratio, 1.0))
    if ratio <= 0.5:
        t = ratio / 0.5
        return (int(0x22 + (0xCC - 0x22) * t), 0xCC, 0x22)
    else:
        t = (ratio - 0.5) / 0.5
        return (0xCC, int(0xCC - (0xCC - 0x22) * t), 0x22)


def gradient_text(text: str, ratio: float) -> str:
    """Color each character of text as a gradient bar.

    Characters up to the ratio point are colored on a green→red scale
    matching their position. Characters past the ratio point are dim.
    If ratio >= 1.0, the whole word is red and ' STALE' is appended.

    Example at 75%: green 'in_prog' → orange 'r' → dim 'ess'
    """
    if ratio >= 1.0:
        return f"[bold #ff2222]{text} STALE[/]"

    n = len(text)
    split = int(n * ratio)
    parts: list[str] = []

    for i, ch in enumerate(text):
        if i < split:
            # Color each char on the green→red scale based on its position
            char_ratio = i / n
            r, g, b = _lerp_color(char_ratio)
            parts.append(f"[bold #{r:02x}{g:02x}{b:02x}]{ch}[/]")
        elif i == split:
            # The boundary character — use the overall ratio color
            r, g, b = _lerp_color(ratio)
            parts.append(f"[bold #{r:02x}{g:02x}{b:02x}]{ch}[/]")
        else:
            # Remaining chars are dim
            parts.append(f"[dim]{ch}[/]")

    return "".join(parts)


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
        table.add_column("Assigned", style="dim")
        table.add_column("Tags", style="dim")
        table.add_column("Created", style="dim", justify="right")

    # Add rows
    for task in tasks:
        task_id = str(task.get("id", ""))[:8]
        title = task.get("title", "")
        status = task.get("status", "unknown")
        priority = task.get("priority", "medium")
        is_child = bool(task.get("parent_id"))

        # Indent children
        if is_child:
            title = f"  └ {title}"

        # Truncate title if too long
        if len(title) > 50 and compact:
            title = title[:47] + "..."

        # Build status display with staleness gradient
        children_info = task.get("children")
        stale_ratio = task.get("stale_ratio")

        if children_info:
            done = children_info["done"]
            total = children_info["total"]
            status_display = f"[{get_status_style(status)}]{status}[/] [{done}/{total}]"
        elif stale_ratio is not None:
            status_display = gradient_text(status, stale_ratio)
        else:
            status_display = f"[{get_status_style(status)}]{status}[/]"

        row = [
            task_id,
            title,
            status_display,
            f"[{get_priority_style(priority)}]{priority}[/]",
        ]

        if not compact:
            assigned = task.get("assigned_to") or "—"
            tags = ", ".join(task.get("tags", [])) or "—"
            created = format_datetime(task.get("created_at"))
            row.extend([assigned, tags, created])

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

    # Parent
    if parent_id := task.get("parent_id"):
        console.print(f"Parent: [dim]{parent_id[:8]}[/dim]")

    # Assignment
    if assigned_to := task.get("assigned_to"):
        parts = [f"Assigned: [bold]{assigned_to}[/bold]"]
        if heartbeat := task.get("last_heartbeat"):
            parts.append(f"last heartbeat: {format_datetime(heartbeat)}")
        if expected := task.get("expected_heartbeat"):
            parts.append(f"next expected: {format_datetime(expected)}")
        console.print(parts[0] + (" (" + ", ".join(parts[1:]) + ")" if len(parts) > 1 else ""))

    # Creator attribution (immutable, stamped at creation)
    if created_by := task.get("created_by"):
        line = f"Created by: [bold]{created_by}[/bold]"
        if did := task.get("created_by_did"):
            line += f" [dim]({did[:16]}…)[/dim]"
        console.print(line)
    elif did := task.get("created_by_did"):
        console.print(f"Created by: [dim]{did[:16]}…[/dim]")

    # Child rollup
    if children := task.get("children"):
        total = children["total"]
        done = children["done"]
        by_status = children.get("by_status", {})
        parts = [f"{k}: {v}" for k, v in sorted(by_status.items())]
        console.print(f"Children: [bold]{done}/{total} done[/bold]  ({', '.join(parts)})")

    # Description
    if description := task.get("description"):
        console.print(f"\n[bold]Description:[/bold]\n{description}")

    # Project
    if project := task.get("project"):
        console.print(f"\n[bold]Project:[/bold] {project.get('name', '')}")

    # Tags
    if tags := task.get("tags"):
        console.print(f"[bold]Tags:[/bold] {', '.join(tags)}")

    # Notes (append-only, attributed) — newest last
    if notes := task.get("notes"):
        console.print("\n[bold]Notes:[/bold]")
        print_task_notes(notes)

    # Metadata
    console.print(f"\n[dim]Created: {format_datetime(task.get('created_at'))}[/dim]")
    if updated_at := task.get("updated_at"):
        console.print(f"[dim]Updated: {format_datetime(updated_at)}[/dim]")

    console.print()


def print_task_notes(notes: list[dict[str, Any]]) -> None:
    """Render a task's append-only note stream (oldest first).

    Each note shows its UTC timestamp and author on a dim header line, followed
    by the (possibly multi-line, markdown) body indented beneath it.
    """
    for note in notes:
        ts = format_datetime(note.get("ts"))
        author = note.get("author", "unknown")
        console.print(f"  [dim]{ts} · {author}[/dim]")
        body = note.get("body", "")
        for line in (body.splitlines() or [""]):
            console.print(f"    {line}")


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
                        label += (
                            f" [dim]([/dim][yellow]{active_task_count} active[/yellow][dim])[/dim]"
                        )

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
    error_console.print(f"[bold red]✗[/bold red] {message}")


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
