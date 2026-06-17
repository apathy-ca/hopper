"""Context commands for session awareness and editing."""

import os
import subprocess
import tempfile

import click
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

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

    Shows relevant memory, open tasks, and important context for
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
@click.option("--memory", "-m", is_flag=True, help="Show only memory")
@click.option("--tasks", "-t", is_flag=True, help="Show only open tasks")
@click.option("--limit", "-n", type=int, default=10, help="Max items per section")
@click.option(
    "--summary",
    "-s",
    is_flag=True,
    help="LLM-generated narrative summary instead of raw record list (requires ANTHROPIC_API_KEY)",
)
@click.option("--subject", help="Filter summary to this subject (only with --summary)")
@click.pass_obj
def show(
    ctx: Context, memory: bool, tasks: bool, limit: int, summary: bool, subject: str | None
) -> None:
    """Show session context.

    Displays relevant memory (agent knowledge), open tasks, and other
    context for starting or resuming a work session. Memory is the
    headline; tasks are secondary.

    Use --summary for an LLM-generated narrative instead of a raw list.

    Examples:
        hopper context show
        hopper context show --memory
        hopper context show --tasks --limit 5
        hopper context show --summary
        hopper context show --summary --subject project:waypoint
    """
    if summary:
        from rich.markdown import Markdown

        from hopper.memory.session_summary import run_session_summary

        try:
            with ctx.get_client() as client:
                result = run_session_summary(client, subject=subject)
        except ClientError as e:
            print_error(f"Failed to get context: {e.message}")
            raise click.Abort() from e

        if "error" in result:
            print_error(result["error"])
            raise click.Abort()
        if result.get("skipped"):
            print_info(result.get("reason", "Nothing to summarise"))
            return
        console.print()
        console.print(Markdown(result["summary"]))
        console.print()
        return

    # If neither flag set, show both
    show_memory = memory or not tasks
    show_tasks = tasks or not memory

    try:
        with ctx.get_client() as client:
            if ctx.json_output:
                result = {}
                if show_memory:
                    result["memory"] = client.list_tasks(kind="memory", limit=limit)
                if show_tasks:
                    # Open Tasks shows only kind=task — non-task kinds
                    # (memory, job, idea, …) are segmented out by type.
                    result["tasks"] = client.list_tasks(status="open", kind="task", limit=limit)
                print_json(result)
                return

            console.print()

            # Show memory section (the knowledge layer)
            if show_memory:
                memory_items = client.list_tasks(kind="memory", limit=limit)
                _print_memory_section(memory_items, limit)

            # Show open tasks section — only kind=task
            if show_tasks:
                task_items = client.list_tasks(status="open", kind="task", limit=limit)
                _print_tasks_section(task_items, limit)

            # Show northbound items (flagged for upstream)
            if show_memory:
                northbound = client.list_tasks(tags="northbound", limit=5)
                if northbound:
                    _print_northbound_section(northbound)

            # Show last consolidation timestamp from instance metadata
            if show_memory:
                _print_consolidation_status(client)

            console.print()

    except ClientError as e:
        print_error(f"Failed to get context: {e.message}")
        raise click.Abort() from e


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
        raise click.Abort() from e


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
        raise click.Abort() from e


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
        raise click.Abort() from e


# ============================================================================
# Output Helpers
# ============================================================================


def _print_memory_section(items: list[dict], limit: int) -> None:
    """Print memory section (agent knowledge)."""
    console.print("[bold cyan]Memory[/bold cyan]")
    console.print()

    if not items:
        console.print("  [dim]No memory captured yet[/dim]")
        console.print()
        return

    for item in items[:limit]:
        task_id = item.get("id", "")[:8]
        title = item.get("title", "Untitled")
        subject = item.get("subject")

        console.print(f"  [dim]{task_id}[/dim] {title}")
        if subject:
            console.print(f"         [dim]{subject}[/dim]")

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

        priority_style = {
            "urgent": "red bold",
            "high": "red",
            "medium": "yellow",
            "low": "dim",
        }.get(priority, "")

        console.print(
            f"  [dim]{task_id}[/dim] [{priority_style}]{priority}[/{priority_style}] {title}"
        )

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


def _print_consolidation_status(client: object) -> None:
    """Show last memory consolidation timestamp from instance metadata."""
    from hopper.storage.sqlite import SQLiteStorage

    if not isinstance(client.storage, SQLiteStorage):
        return

    from sqlalchemy import text

    instance_id = getattr(client.config, "instance_id", ".hopper")

    try:
        with client.storage.session() as session:
            row = session.execute(
                text("SELECT runtime_metadata FROM hopper_instances WHERE id = :id"),
                {"id": instance_id},
            ).fetchone()
    except Exception:
        return

    if not row or not row[0]:
        return

    import json

    meta = json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
    last_at = meta.get("last_consolidation_at")
    if not last_at:
        return

    console.print(f"[dim]Last consolidation: {last_at}[/dim]")
    console.print()


def _print_task_detail(task: dict) -> None:
    """Print detailed task information."""
    console.print()
    console.print(
        Panel(
            f"[bold]{task.get('title', 'Untitled')}[/bold]\n\n"
            f"[dim]ID:[/dim] {task.get('id', '')}\n"
            f"[dim]Status:[/dim] {task.get('status', 'open')}\n"
            f"[dim]Priority:[/dim] {task.get('priority', 'medium')}\n"
            f"[dim]Tags:[/dim] {', '.join(task.get('tags', []))}\n"
            f"[dim]Created:[/dim] {format_datetime(task.get('created_at'))}\n\n"
            f"{task.get('description', '') or '[dim]No description[/dim]'}",
            title="Task Details",
            border_style="cyan",
        )
    )
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
        with open(temp_path) as f:
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
