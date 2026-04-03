"""Task management commands."""

import click
from rich.prompt import Confirm, Prompt

from hopper.cli.client import APIError
from hopper.cli.local_client import LocalClientError
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_json,
    print_success,
    print_task_detail,
    print_task_table,
)


# Combined error types for handling both client types
ClientError = (APIError, LocalClientError)


@click.group(name="task")
def task() -> None:
    """Manage Hopper tasks.

    Tasks are the core units of work in Hopper. You can create, list, update,
    and manage tasks through this command group.
    """
    pass


@task.command(name="add")
@click.argument("title", required=False)
@click.option("--description", "-d", help="Task description (short summary)")
@click.option(
    "--brief-file",
    "-b",
    type=click.Path(exists=True, readable=True),
    help="Path to a markdown file whose content becomes the task body. "
    "Use for full worker briefs. Overrides --description.",
)
@click.option(
    "--priority",
    "-p",
    type=click.Choice(["low", "medium", "high", "urgent"]),
    default="medium",
    help="Task priority",
)
@click.option("--tag", "-t", multiple=True, help="Add tags (can be used multiple times)")
@click.option("--project", help="Project ID or name")
@click.option(
    "--status",
    type=click.Choice(["open", "in_progress", "blocked", "completed", "cancelled"]),
    default="open",
    help="Initial status",
)
@click.option(
    "--non-interactive", is_flag=True, help="Skip all interactive prompts (for scripted use)"
)
@click.option(
    "--assign", "-a", help="Assign to an agent or user (e.g. 'claude:main', 'opencode:acm', 'human:james')"
)
@click.pass_obj
def add_task(
    ctx: Context,
    title: str | None,
    description: str | None,
    brief_file: str | None,
    priority: str,
    tag: tuple[str, ...],
    project: str | None,
    status: str,
    non_interactive: bool,
    assign: str | None,
) -> None:
    """Create a new task.

    If TITLE is not provided, you'll be prompted to enter it interactively.

    Use --brief-file to attach a full markdown document as the task body.
    This is the primary mechanism for storing worker instruction briefs in hopper.

    Examples:
        hopper task add "Fix login bug"
        hopper task add "Add dark mode" -p high -t feature -t ui
        hopper task add "[backend] Build API" --brief-file .czarina/workers/backend.md -t czarina
        hopper task add --project my-project
    """
    import sys

    # Interactive mode if no title provided
    if not title:
        if non_interactive:
            print_error("Title is required (use --non-interactive with an explicit title)")
            raise click.Abort()
        title = Prompt.ask("[bold]Task title[/bold]")
        if not title:
            print_error("Title is required")
            raise click.Abort()

    # Load brief file content — overrides description
    brief_content: str | None = None
    if brief_file:
        with open(brief_file) as f:
            brief_content = f.read()
    elif description is None and not non_interactive and not tag:
        # Interactive prompts for additional fields only when not in quick mode
        if Confirm.ask("Add description?", default=False):
            description = Prompt.ask("[bold]Description[/bold]", default="")

        if Confirm.ask("Add tags?", default=False):
            tags_input = Prompt.ask("[bold]Tags (comma-separated)[/bold]", default="")
            tag = tuple(t.strip() for t in tags_input.split(",") if t.strip())

    # Build task data
    task_data: dict[str, object] = {
        "title": title,
        "status": status,
        "priority": priority,
    }

    if tag:
        task_data["tags"] = list(tag)

    if project:
        task_data["project_id"] = project

    if assign:
        task_data["assigned_to"] = assign

    # Create task — use brief path when a full brief is provided
    try:
        with ctx.get_client() as client:
            if brief_content is not None:
                if not hasattr(client, "create_task_with_brief"):
                    print_error("--brief-file requires local mode (use --local flag)")
                    raise click.Abort()
                result = client.create_task_with_brief(task_data, brief_content)  # type: ignore[union-attr]
            else:
                if description:
                    task_data["description"] = description
                result = client.create_task(task_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Created task: {result.get('id', '')}")
            print_task_detail(result)

    except ClientError as e:
        print_error(f"Failed to create task: {e.message}")
        raise click.Abort()


@task.command(name="list")
@click.option("--status", help="Filter by status")
@click.option("--priority", help="Filter by priority")
@click.option("--project", help="Filter by project ID or name")
@click.option("--tag", multiple=True, help="Filter by tags")
@click.option(
    "--sort-by",
    type=click.Choice(["created", "updated", "priority", "status"]),
    default="created",
    help="Sort field",
)
@click.option("--limit", type=int, default=50, help="Maximum number of tasks to show")
@click.option("--compact", is_flag=True, help="Use compact table layout")
@click.pass_obj
def list_tasks(
    ctx: Context,
    status: str | None,
    priority: str | None,
    project: str | None,
    tag: tuple[str, ...],
    sort_by: str,
    limit: int,
    compact: bool,
) -> None:
    """List tasks with optional filters.

    Examples:
        hopper task list
        hopper task list --status open
        hopper task list --priority high --tag bug
        hopper task list --project my-project --compact
    """
    # Build query parameters
    params = {
        "limit": limit,
        "sort_by": sort_by,
    }

    if status:
        params["status"] = status
    if priority:
        params["priority"] = priority
    if project:
        params["project"] = project
    if tag:
        params["tags"] = ",".join(tag)

    # Fetch tasks
    try:
        with ctx.get_client() as client:
            tasks = client.list_tasks(**params)

        if ctx.json_output:
            print_json(tasks)
        else:
            print_task_table(tasks, compact=compact)
            if tasks:
                print_info(f"Showing {len(tasks)} task(s)")

    except ClientError as e:
        print_error(f"Failed to list tasks: {e.message}")
        raise click.Abort()


@task.command(name="get")
@click.argument("task_id")
@click.option(
    "--with-lessons", is_flag=True, help="Append relevant high-confidence lessons to the task body"
)
@click.option(
    "--project", default=None, help="Project slug to filter lessons by (used with --with-lessons)"
)
@click.pass_obj
def get_task(ctx: Context, task_id: str, with_lessons: bool, project: str | None) -> None:
    """Get detailed information about a task.

    Use --with-lessons to include high-confidence lessons from previous workers
    relevant to this task's project and domain. This is the primary way workers
    receive accumulated knowledge when starting a new task.

    Examples:
        hopper task get abc12345
        hopper task get abc12345 --with-lessons --project my-api
    """
    try:
        with ctx.get_client() as client:
            if with_lessons and hasattr(client, "get_task_with_lessons"):
                task = client.get_task_with_lessons(task_id, project_slug=project)  # type: ignore[union-attr]
            else:
                task = client.get_task(task_id)

        if ctx.json_output:
            print_json(task)
        else:
            print_task_detail(task)

    except ClientError as e:
        print_error(f"Failed to get task: {e.message}")
        raise click.Abort()


@task.command(name="update")
@click.argument("task_id")
@click.option("--title", help="New title")
@click.option("--description", help="New description")
@click.option(
    "--priority", type=click.Choice(["low", "medium", "high", "urgent"]), help="New priority"
)
@click.option("--add-tag", multiple=True, help="Add tags")
@click.option("--remove-tag", multiple=True, help="Remove tags")
@click.option("--assign", "-a", help="Assign to an agent or user")
@click.option("--unassign", is_flag=True, help="Clear assignment")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.pass_obj
def update_task(
    ctx: Context,
    task_id: str,
    title: str | None,
    description: str | None,
    priority: str | None,
    add_tag: tuple[str, ...],
    remove_tag: tuple[str, ...],
    assign: str | None,
    unassign: bool,
    interactive: bool,
) -> None:
    """Update a task.

    Examples:
        hopper task update abc12345 --title "New title"
        hopper task update abc12345 --priority high
        hopper task update abc12345 --add-tag bug --remove-tag feature
        hopper task update abc12345 --interactive
    """
    # Interactive mode
    if interactive:
        try:
            with ctx.get_client() as client:
                current = client.get_task(task_id)

            print_task_detail(current)
            console.print("\n[bold]Update task (press Enter to keep current value):[/bold]\n")

            title = Prompt.ask("Title", default=current.get("title", ""))
            description = Prompt.ask("Description", default=current.get("description", ""))
            priority = Prompt.ask(
                "Priority",
                choices=["low", "medium", "high", "urgent"],
                default=current.get("priority", "medium"),
            )

        except ClientError as e:
            print_error(f"Failed to get task: {e.message}")
            raise click.Abort()

    # Build update data
    update_data = {}

    if title:
        update_data["title"] = title
    if description:
        update_data["description"] = description
    if priority:
        update_data["priority"] = priority

    # Handle tags
    if add_tag or remove_tag:
        update_data["add_tags"] = list(add_tag)
        update_data["remove_tags"] = list(remove_tag)

    # Handle assignment
    if assign:
        update_data["assigned_to"] = assign
    elif unassign:
        update_data["assigned_to"] = None

    if not update_data:
        print_error("No updates specified")
        raise click.Abort()

    # Update task
    try:
        with ctx.get_client() as client:
            result = client.update_task(task_id, update_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Updated task: {task_id}")
            print_task_detail(result)

    except ClientError as e:
        print_error(f"Failed to update task: {e.message}")
        raise click.Abort()


@task.command(name="status")
@click.argument("task_id")
@click.argument(
    "new_status", type=click.Choice(["open", "in_progress", "blocked", "completed", "cancelled"])
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.option("--assign", "-a", help="Assign to an agent or user while changing status")
@click.pass_obj
def change_status(ctx: Context, task_id: str, new_status: str, force: bool, assign: str | None) -> None:
    """Change task status.

    Examples:
        hopper task status abc12345 in_progress
        hopper task status abc12345 in_progress --assign claude:acm-rewrite
        hopper task status abc12345 completed
    """
    # Confirmation
    if not force:
        if not Confirm.ask(f"Change status to '{new_status}'?", default=True):
            print_info("Cancelled")
            return

    # Update status (and optionally assignment)
    update_data: dict[str, object] = {"status": new_status}
    if assign:
        update_data["assigned_to"] = assign

    try:
        with ctx.get_client() as client:
            result = client.update_task(task_id, update_data)

        if ctx.json_output:
            print_json(result)
        else:
            msg = f"Changed status to: {new_status}"
            if assign:
                msg += f" (assigned to {assign})"
            print_success(msg)

    except ClientError as e:
        print_error(f"Failed to change status: {e.message}")
        raise click.Abort()


@task.command(name="delete")
@click.argument("task_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def delete_task(ctx: Context, task_id: str, force: bool) -> None:
    """Delete a task.

    Examples:
        hopper task delete abc12345
        hopper task delete abc12345 --force
    """
    # Get task info for confirmation
    if not force:
        try:
            with ctx.get_client() as client:
                task = client.get_task(task_id)
            console.print(f"\n[bold]Task to delete:[/bold] {task.get('title', '')}\n")
        except ClientError:
            pass

        if not Confirm.ask("[bold red]Delete this task?[/bold red]", default=False):
            print_info("Cancelled")
            return

    # Delete task
    try:
        with ctx.get_client() as client:
            client.delete_task(task_id)

        print_success(f"Deleted task: {task_id}")

    except ClientError as e:
        print_error(f"Failed to delete task: {e.message}")
        raise click.Abort()


@task.command(name="search")
@click.argument("query")
@click.option("--status", help="Filter by status")
@click.option("--priority", help="Filter by priority")
@click.option("--project", help="Filter by project")
@click.option("--limit", type=int, default=50, help="Maximum results")
@click.option("--compact", is_flag=True, help="Compact layout")
@click.pass_obj
def search_tasks(
    ctx: Context,
    query: str,
    status: str | None,
    priority: str | None,
    project: str | None,
    limit: int,
    compact: bool,
) -> None:
    """Search tasks by title and description.

    Examples:
        hopper task search "login bug"
        hopper task search "authentication" --status open
    """
    params = {"limit": limit}

    if status:
        params["status"] = status
    if priority:
        params["priority"] = priority
    if project:
        params["project"] = project

    try:
        with ctx.get_client() as client:
            results = client.search_tasks(query, **params)

        if ctx.json_output:
            print_json(results)
        else:
            print_task_table(results, compact=compact)
            if results:
                print_info(f"Found {len(results)} task(s) matching '{query}'")
            else:
                print_info(f"No tasks found matching '{query}'")

    except ClientError as e:
        print_error(f"Search failed: {e.message}")
        raise click.Abort()


@task.command(name="delegate")
@click.argument("task_id")
@click.option("--to", "target_instance", required=True, help="Target instance ID")
@click.option(
    "--type",
    "delegation_type",
    type=click.Choice(["route", "decompose", "escalate", "reassign"]),
    default="route",
    help="Delegation type",
)
@click.option("--notes", help="Delegation notes")
@click.pass_obj
def delegate_task(
    ctx: Context,
    task_id: str,
    target_instance: str,
    delegation_type: str,
    notes: str | None,
) -> None:
    """Delegate a task to another instance.

    Examples:
        hopper task delegate TASK-001 --to project-123
        hopper task delegate TASK-001 --to orch-456 --type route
        hopper task delegate TASK-001 --to project-789 --notes "Complex task"
    """
    delegation_data = {
        "task_id": task_id,
        "target_instance_id": target_instance,
        "delegation_type": delegation_type,
    }

    if notes:
        delegation_data["notes"] = notes

    try:
        with ctx.get_client() as client:
            result = client.delegate_task(task_id, delegation_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Delegated task {task_id} to {target_instance}")
            console.print(f"[dim]Delegation ID: {result.get('id', '')}[/dim]")

    except ClientError as e:
        print_error(f"Failed to delegate task: {e.message}")
        raise click.Abort()


@task.command(name="delegations")
@click.argument("task_id")
@click.pass_obj
def show_delegations(ctx: Context, task_id: str) -> None:
    """Show the delegation chain for a task.

    Examples:
        hopper task delegations TASK-001
    """
    try:
        with ctx.get_client() as client:
            result = client.get_task_delegations(task_id)

        if ctx.json_output:
            print_json(result)
        else:
            delegations = result.get("delegations", [])

            if not delegations:
                print_info(f"Task {task_id} has no delegations")
                return

            console.print(f"\n[bold cyan]Delegation Chain for {task_id}[/bold cyan]\n")

            # Show current location
            current = result.get("current_instance_id")
            origin = result.get("origin_instance_id")

            if origin:
                console.print(f"[bold]Origin:[/bold] {origin}")
            if current:
                console.print(f"[bold]Current:[/bold] {current}")

            console.print()

            # Show delegation history
            from rich import box
            from rich.table import Table

            table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
            table.add_column("#", style="dim", width=3)
            table.add_column("From", style="dim")
            table.add_column("To")
            table.add_column("Type")
            table.add_column("Status", justify="center")
            table.add_column("When", style="dim")

            from hopper.cli.output import format_datetime, get_status_style

            for i, delegation in enumerate(delegations, 1):
                source = (
                    delegation.get("source_instance_id", "—")[:12]
                    if delegation.get("source_instance_id")
                    else "—"
                )
                target = (
                    delegation.get("target_instance_id", "—")[:12]
                    if delegation.get("target_instance_id")
                    else "—"
                )
                dtype = delegation.get("delegation_type", "route")
                status = delegation.get("status", "pending")
                when = format_datetime(delegation.get("delegated_at"))

                table.add_row(
                    str(i),
                    source,
                    target,
                    dtype,
                    f"[{get_status_style(status)}]{status}[/]",
                    when,
                )

            console.print(table)
            console.print(f"\n[dim]Total delegations: {len(delegations)}[/dim]\n")

    except ClientError as e:
        print_error(f"Failed to get delegations: {e.message}")
        raise click.Abort()


def _parse_duration(value: str) -> int:
    """Parse a human-friendly duration string into minutes.

    Accepts: 30m, 2h, 1h30m, 90, 4h, etc.
    Plain numbers are treated as minutes.
    """
    import re
    value = value.strip().lower()

    # Plain number = minutes
    if value.isdigit():
        return int(value)

    total = 0
    # Match hours and/or minutes
    match = re.match(r"(?:(\d+)h)?(?:(\d+)m?)?$", value)
    if match:
        hours = int(match.group(1) or 0)
        mins = int(match.group(2) or 0)
        total = hours * 60 + mins

    if total <= 0:
        raise click.BadParameter(f"Cannot parse duration: '{value}' (try '30m', '2h', '1h30m')")
    return total


@task.command(name="heartbeat")
@click.argument("task_id")
@click.option(
    "--expect", "-e",
    help="When to expect the next heartbeat (e.g. '30m', '2h', '1h30m'). "
    "Use when starting a long-running process so stale detection won't fire early."
)
@click.pass_obj
def task_heartbeat(ctx: Context, task_id: str, expect: str | None) -> None:
    """Signal that an agent is still working on a task.

    Updates the last_heartbeat timestamp to now. Agents should call this
    periodically (e.g. every 10-15 minutes) to indicate they're alive.

    Use --expect before long-running work (GPU jobs, data generation) to tell
    the stale detector not to flag you prematurely.

    Examples:
        hopper task heartbeat abc12345
        hopper task heartbeat abc12345 --expect 2h
        hopper task heartbeat abc12345 -e 30m
    """
    expect_minutes = _parse_duration(expect) if expect else None

    try:
        with ctx.get_client() as client:
            if not hasattr(client, "heartbeat_task"):
                print_error("Heartbeat requires local mode")
                raise click.Abort()
            result = client.heartbeat_task(task_id, expect_minutes=expect_minutes)

        if ctx.json_output:
            print_json(result)
        else:
            assigned = result.get("assigned_to", "unknown")
            msg = f"Heartbeat updated for {task_id} (assigned to {assigned})"
            if expect_minutes:
                msg += f" — next expected in {expect}"
            print_success(msg)

    except ClientError as e:
        print_error(f"Failed to update heartbeat: {e.message}")
        raise click.Abort()


@task.command(name="stale")
@click.option(
    "--minutes", "-m", type=int, default=30,
    help="Minutes without heartbeat to consider stale (default: 30)"
)
@click.option("--compact", is_flag=True, help="Compact layout")
@click.pass_obj
def stale_tasks(ctx: Context, minutes: int, compact: bool) -> None:
    """Find in-progress tasks whose agent has gone silent.

    Lists assigned, in_progress tasks where the last heartbeat is older
    than the threshold. These tasks likely belong to agents that crashed
    or ended without cleaning up.

    Examples:
        hopper task stale
        hopper task stale --minutes 60
    """
    try:
        with ctx.get_client() as client:
            if not hasattr(client, "list_stale_tasks"):
                print_error("Stale detection requires local mode")
                raise click.Abort()
            tasks = client.list_stale_tasks(minutes=minutes)

        if ctx.json_output:
            print_json(tasks)
        else:
            if tasks:
                print_task_table(tasks, compact=compact)
                print_info(
                    f"Found {len(tasks)} stale task(s) "
                    f"(no heartbeat in {minutes}+ minutes)"
                )
            else:
                print_info(f"No stale tasks (threshold: {minutes} minutes)")

    except ClientError as e:
        print_error(f"Failed to check stale tasks: {e.message}")
        raise click.Abort()


# Shortcuts
@click.command(name="add")
@click.argument("title", required=False)
@click.option("--description", "-d", help="Task description")
@click.option(
    "--priority", "-p", type=click.Choice(["low", "medium", "high", "urgent"]), default="medium"
)
@click.option("--tag", "-t", multiple=True, help="Add tags")
@click.option("--project", help="Project ID or name")
@click.pass_context
def add_shortcut(ctx: click.Context, title: str | None, **kwargs: any) -> None:
    """Quick add task (shortcut for 'hopper task add')."""
    ctx.invoke(add_task, title=title, **kwargs)


@click.command(name="ls")
@click.option("--status", help="Filter by status")
@click.option("--priority", help="Filter by priority")
@click.option("--project", help="Filter by project")
@click.option("--tag", multiple=True, help="Filter by tags")
@click.option("--compact", is_flag=True, help="Compact layout")
@click.pass_context
def ls_shortcut(ctx: click.Context, **kwargs: any) -> None:
    """Quick list tasks (shortcut for 'hopper task list')."""
    ctx.invoke(list_tasks, sort_by="created", limit=50, **kwargs)
