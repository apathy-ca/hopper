"""Context commands for session awareness and editing."""

import os
import subprocess
import tempfile
import click
from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from hopper.cli.client import APIError
from hopper.cli.local_client import LocalClientError
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    format_datetime,
    print_error,
    print_info,
    print_json,
    print_success,
)


# Combined error types for handling both client types
ClientError = (APIError, LocalClientError)


@click.group(name="context", invoke_without_command=True)
@click.pass_context
def context(ctx: click.Context) -> None:
    """Session context - view and manage relevant items.

    Shows recent learnings, open tasks, and important context for
    starting or resuming work. Use subcommands to edit or manage items.

    Examples:
        hopper context              # Show session context
        hopper context show         # Same as above
        hopper context edit TASK-ID # Edit a specific item
    """
    # If no subcommand, run show
    if ctx.invoked_subcommand is None:
        ctx.invoke(show)


@context.command(name="show")
@click.option("--learnings", "-l", is_flag=True, help="Show only learnings")
@click.option("--tasks", "-t", is_flag=True, help="Show only open tasks")
@click.option("--limit", "-n", type=int, default=10, help="Max items per section")
@click.pass_obj
def show(ctx: Context, learnings: bool, tasks: bool, limit: int) -> None:
    """Show session context.

    Displays recent learnings, open tasks, and other relevant context
    for starting or resuming a work session.

    Examples:
        hopper context show
        hopper context show --learnings
        hopper context show --tasks --limit 5
    """
    # If neither flag set, show both
    show_learnings = learnings or not tasks
    show_tasks = tasks or not learnings

    try:
        with ctx.get_client() as client:
            if ctx.json_output:
                result = {}
                if show_learnings:
                    items = client.list_tasks(tags="auto-learned", limit=limit)
                    result["learnings"] = items
                if show_tasks:
                    items = client.list_tasks(status="open", limit=limit)
                    # Filter out learnings and memory records from tasks view
                    items = [
                        t for t in items
                        if "auto-learned" not in t.get("tags", [])
                        and "memory" not in t.get("tags", [])
                    ]
                    result["tasks"] = items
                print_json(result)
                return

            console.print()

            # Show learnings section
            if show_learnings:
                learning_items = client.list_tasks(tags="auto-learned", limit=limit)
                _print_learnings_section(learning_items, limit)

            # Show open tasks section
            if show_tasks:
                task_items = client.list_tasks(status="open", limit=limit)
                # Filter out learnings and memory records
                task_items = [
                    t for t in task_items
                    if "auto-learned" not in t.get("tags", [])
                    and "memory" not in t.get("tags", [])
                ]
                _print_tasks_section(task_items, limit)

            # Show northbound items (flagged for upstream)
            if show_learnings:
                northbound = client.list_tasks(tags="northbound", limit=5)
                if northbound:
                    _print_northbound_section(northbound)

            console.print()

    except ClientError as e:
        print_error(f"Failed to get context: {e.message}")
        raise click.Abort()


@context.command(name="edit")
@click.argument("task_id")
@click.option("--title", "-t", help="New title")
@click.option("--add-tag", multiple=True, help="Add tag(s)")
@click.option("--remove-tag", multiple=True, help="Remove tag(s)")
@click.option("--editor", "-e", is_flag=True, help="Open in $EDITOR")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.pass_obj
def edit(
    ctx: Context,
    task_id: str,
    title: str | None,
    add_tag: tuple[str, ...],
    remove_tag: tuple[str, ...],
    editor: bool,
    interactive: bool,
) -> None:
    """Edit a context item.

    Modify task/learning title, tags, or content. Use --editor to open
    the full content in your $EDITOR.

    Examples:
        hopper context edit task-abc --title "Updated title"
        hopper context edit task-abc --add-tag northbound
        hopper context edit task-abc --remove-tag auto-learned
        hopper context edit task-abc --editor
        hopper context edit task-abc --interactive
    """
    try:
        with ctx.get_client() as client:
            # Get current task
            task = client.get_task(task_id)

            if interactive:
                task = _interactive_edit(task)
                if task is None:
                    print_info("Edit cancelled")
                    return

                # Apply interactive changes
                update_data = {
                    "title": task["title"],
                    "description": task.get("description"),
                    "tags": task.get("tags", []),
                }
                result = client.update_task(task_id, update_data)

            elif editor:
                # Open in editor
                new_content = _editor_edit(task)
                if new_content is None:
                    print_info("Edit cancelled (no changes)")
                    return

                result = client.update_task(task_id, {"description": new_content})

            else:
                # Direct updates via flags
                update_data = {}

                if title:
                    update_data["title"] = title

                if add_tag:
                    update_data["add_tags"] = list(add_tag)

                if remove_tag:
                    update_data["remove_tags"] = list(remove_tag)

                if not update_data:
                    # No updates, just show the item
                    _print_task_detail(task)
                    return

                result = client.update_task(task_id, update_data)

            if ctx.json_output:
                print_json(result)
            else:
                print_success(f"Updated: {result.get('title', task_id)}")

    except ClientError as e:
        print_error(f"Failed to edit: {e.message}")
        raise click.Abort()


@context.command(name="promote")
@click.argument("task_id")
@click.pass_obj
def promote(ctx: Context, task_id: str) -> None:
    """Mark a learning for northbound export.

    Adds the 'northbound' tag to flag this learning for upstream
    contribution to team or community knowledge.

    Examples:
        hopper context promote task-abc
    """
    try:
        with ctx.get_client() as client:
            result = client.update_task(task_id, {"add_tags": ["northbound"]})

            if ctx.json_output:
                print_json(result)
            else:
                print_success(f"Promoted for northbound: {result.get('title', task_id)}")

    except ClientError as e:
        print_error(f"Failed to promote: {e.message}")
        raise click.Abort()


@context.command(name="dismiss")
@click.argument("task_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def dismiss(ctx: Context, task_id: str, force: bool) -> None:
    """Dismiss/archive a learning.

    Marks the learning as completed/archived so it no longer appears
    in active context.

    Examples:
        hopper context dismiss task-abc
        hopper context dismiss task-abc --force
    """
    if not force:
        if not Confirm.ask(f"Dismiss learning {task_id}?", default=True):
            print_info("Cancelled")
            return

    try:
        with ctx.get_client() as client:
            result = client.update_task(task_id, {"status": "completed"})

            if ctx.json_output:
                print_json(result)
            else:
                print_success(f"Dismissed: {result.get('title', task_id)}")

    except ClientError as e:
        print_error(f"Failed to dismiss: {e.message}")
        raise click.Abort()


# ============================================================================
# Output Helpers
# ============================================================================


def _print_learnings_section(items: list[dict], limit: int) -> None:
    """Print learnings section."""
    console.print("[bold cyan]Recent Learnings[/bold cyan]")
    console.print()

    if not items:
        console.print("  [dim]No learnings captured yet[/dim]")
        console.print()
        return

    for item in items[:limit]:
        task_id = item.get("id", "")[:8]
        title = item.get("title", "Untitled")
        tags = item.get("tags", [])
        created = format_datetime(item.get("created_at"))

        # Highlight northbound items
        if "northbound" in tags:
            tag_str = "[yellow]northbound[/yellow]"
        else:
            other_tags = [t for t in tags if t != "auto-learned"]
            tag_str = ", ".join(other_tags[:3]) if other_tags else ""

        console.print(f"  [dim]{task_id}[/dim] {title}")
        if tag_str:
            console.print(f"         [dim]{tag_str}[/dim]")

    console.print()


def _print_tasks_section(items: list[dict], limit: int) -> None:
    """Print open tasks section."""
    console.print("[bold cyan]Open Tasks[/bold cyan]")
    console.print()

    if not items:
        console.print("  [dim]No open tasks[/dim]")
        console.print()
        return

    for item in items[:limit]:
        task_id = item.get("id", "")[:8]
        title = item.get("title", "Untitled")
        priority = item.get("priority", "medium")
        status = item.get("status", "open")

        priority_style = {
            "urgent": "red bold",
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }.get(priority, "")

        console.print(f"  [dim]{task_id}[/dim] [{priority_style}]{priority}[/{priority_style}] {title}")

    console.print()


def _print_northbound_section(items: list[dict]) -> None:
    """Print northbound items section."""
    console.print("[bold yellow]Flagged for Upstream[/bold yellow]")
    console.print()

    for item in items:
        task_id = item.get("id", "")[:8]
        title = item.get("title", "Untitled")
        console.print(f"  [dim]{task_id}[/dim] {title}")

    console.print()


def _print_task_detail(task: dict) -> None:
    """Print detailed task information."""
    console.print()
    console.print(Panel(
        f"[bold]{task.get('title', 'Untitled')}[/bold]\n\n"
        f"[dim]ID:[/dim] {task.get('id', '')}\n"
        f"[dim]Status:[/dim] {task.get('status', 'open')}\n"
        f"[dim]Priority:[/dim] {task.get('priority', 'medium')}\n"
        f"[dim]Tags:[/dim] {', '.join(task.get('tags', []))}\n"
        f"[dim]Created:[/dim] {format_datetime(task.get('created_at'))}\n\n"
        f"{task.get('description', '') or '[dim]No description[/dim]'}",
        title="Task Details",
        border_style="cyan",
    ))
    console.print()


def _interactive_edit(task: dict) -> dict | None:
    """Interactive editing of a task."""
    console.print("\n[bold cyan]Edit Task[/bold cyan]\n")
    console.print(f"  Current title: {task.get('title', '')}")
    console.print(f"  Current tags: {', '.join(task.get('tags', []))}")
    console.print()

    # Edit title
    new_title = Prompt.ask("New title (Enter to keep)", default=task.get("title", ""))
    if not new_title:
        return None

    # Edit tags
    current_tags = task.get("tags", [])
    tags_str = Prompt.ask(
        "Tags (comma-separated, Enter to keep)",
        default=", ".join(current_tags),
    )
    new_tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    # Confirm
    if not Confirm.ask("Save changes?", default=True):
        return None

    task["title"] = new_title
    task["tags"] = new_tags
    return task


def _editor_edit(task: dict) -> str | None:
    """Open task description in $EDITOR."""
    editor = os.environ.get("EDITOR", "vim")
    content = task.get("description", "") or ""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(f"# {task.get('title', 'Untitled')}\n\n")
        f.write(content)
        temp_path = f.name

    try:
        # Open editor
        result = subprocess.run([editor, temp_path])
        if result.returncode != 0:
            return None

        # Read back
        with open(temp_path, "r") as f:
            new_content = f.read()

        # Strip title line if present
        lines = new_content.split("\n")
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
        new_content = "\n".join(lines).strip()

        # Check if changed
        if new_content == content:
            return None

        return new_content

    finally:
        os.unlink(temp_path)
