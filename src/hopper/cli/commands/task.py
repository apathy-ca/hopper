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
    print_task_notes,
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
    "--assign", "-a", help="Assign to an agent or user (e.g. 'claude:acm-rewrite', 'human:james')"
)
@click.option(
    "--by",
    "created_by",
    envvar="HOPPER_IDENTITY",
    help="Creator identity to record (e.g. 'human:james'). Defaults to --assign. "
    "Immutable once set; also settable via HOPPER_IDENTITY.",
)
@click.option("--parent", help="Parent task ID (creates a child task)")
@click.option(
    "--author-did",
    envvar="HOPPER_DID",
    hidden=True,
    help="DID of the author (agents must supply this)",
)
@click.option(
    "--author-location",
    envvar="HOPPER_LOCATION",
    hidden=True,
    help="Location context for this write",
)
@click.option("--kind", hidden=True, default="task", help="Record kind (task/idea/note/memory/…)")
@click.option("--subject", hidden=True, help="Memory subject (memory records only)")
@click.option("--scope", hidden=True, help="Memory scope (memory records only)")
@click.option("--provenance", hidden=True, help="Memory provenance (memory records only)")
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
    created_by: str | None,
    parent: str | None,
    author_did: str | None,
    author_location: str | None,
    kind: str,
    subject: str | None = None,
    scope: str | None = None,
    provenance: str | None = None,
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
    if created_by:
        task_data["created_by"] = created_by
    if parent:
        task_data["parent_id"] = parent
    if author_did:
        task_data["author_did"] = author_did
    if author_location:
        task_data["author_location"] = author_location
    if kind and kind != "task":
        task_data["kind"] = kind
    if subject:
        task_data["subject"] = subject
    if scope:
        task_data["scope"] = scope
    if provenance:
        task_data["provenance"] = provenance

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
        raise click.Abort() from e


@task.command(name="list")
@click.option("--status", help="Filter by status")
@click.option("--priority", help="Filter by priority")
@click.option("--project", help="Filter by project ID or name")
@click.option("--tag", multiple=True, help="Filter by tags")
@click.option(
    "--sort-by",
    type=click.Choice(["created", "updated", "priority", "status"]),
    default="status",
    help="Sort field (default: status then priority)",
)
@click.option("--limit", type=int, default=50, help="Maximum number of tasks to show")
@click.option("--compact", is_flag=True, help="Use compact table layout")
@click.option("--ids-only", is_flag=True, help="Output task IDs only, one per line (for scripting)")
@click.option(
    "--kind",
    help="Filter by record kind (task/memory/job/idea/note/reference/inbox/log)",
)
@click.option(
    "--all-kinds",
    is_flag=True,
    help="Show every kind (jobs, memory, ideas, …), not just tasks",
)
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
    ids_only: bool,
    kind: str | None = None,
    all_kinds: bool = False,
) -> None:
    """List tasks with optional filters.

    By default this shows only records of kind=task; jobs, memory, ideas and
    other non-task kinds are excluded so the task list stays focused. Use
    --kind to view a specific kind or --all-kinds to see everything.

    Examples:
        hopper task list
        hopper task list --status open
        hopper task list --priority high --tag bug
        hopper task list --project my-project --compact
        hopper task list --kind memory
        hopper task list --all-kinds
    """
    # Build query parameters
    params = {
        "limit": limit,
        "sort_by": sort_by,
    }

    # Default segmentation: task-oriented views show only kind=task. An
    # explicit --kind selects a different kind; --all-kinds disables the
    # filter entirely so nothing is truly hidden.
    if kind:
        params["kind"] = kind
    elif not all_kinds:
        params["kind"] = "task"

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

        if ids_only:
            for task in tasks:
                click.echo(task["id"])
        elif ctx.json_output:
            print_json(tasks)
        else:
            print_task_table(tasks, compact=compact)
            if tasks:
                print_info(f"Showing {len(tasks)} task(s)")

    except ClientError as e:
        print_error(f"Failed to list tasks: {e.message}")
        raise click.Abort() from e


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
            elif hasattr(client, "get_task_with_rollup"):
                task = client.get_task_with_rollup(task_id)
            else:
                task = client.get_task(task_id)

        if ctx.json_output:
            print_json(task)
        else:
            print_task_detail(task)

    except ClientError as e:
        print_error(f"Failed to get task: {e.message}")
        raise click.Abort() from e


@task.command(name="note")
@click.argument("task_id")
@click.argument("body")
@click.option(
    "--from",
    "from_",
    help="Author identity, e.g. 'claude:my-task'. Defaults to 'unknown'.",
)
@click.pass_obj
def add_note(ctx: Context, task_id: str, body: str, from_: str | None) -> None:
    """Append an attributed, timestamped note to a task.

    Notes are append-only — they never overwrite the description, so it is safe
    to leave a finding on a task another agent (or a human) owns. Notes render
    under the task in `hopper task get` and `hopper task notes`.

    Examples:
        hopper task note abc12345 "finding: exfil recompute left stale residuals"
        hopper task note abc12345 --from claude:cross-paper-sync "look here"
    """
    try:
        with ctx.get_client() as client:
            if not hasattr(client, "add_task_note"):
                print_error(
                    "Task notes require local (markdown) storage; the configured "
                    "backend does not support them yet."
                )
                raise click.Abort()
            result = client.add_task_note(task_id, body, author=from_)  # type: ignore[union-attr]

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Note added to {result.get('id', '')}")

    except ClientError as e:
        print_error(f"Failed to add note: {e.message}")
        raise click.Abort() from e


@task.command(name="notes")
@click.argument("task_id")
@click.pass_obj
def list_notes(ctx: Context, task_id: str) -> None:
    """List the append-only note stream for a task (oldest first)."""
    try:
        with ctx.get_client() as client:
            task = client.get_task(task_id)

        notes = task.get("notes") or []
        if ctx.json_output:
            print_json(notes)
            return
        if not notes:
            print_info("No notes on this task")
            return
        console.print(f"\n[bold cyan]Notes for {task.get('id', '')}[/bold cyan]\n")
        print_task_notes(notes)
        console.print()

    except ClientError as e:
        print_error(f"Failed to get notes: {e.message}")
        raise click.Abort() from e


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
@click.option("--parent", help="Set parent task ID")
@click.option("--unparent", is_flag=True, help="Remove from parent")
@click.option(
    "--note",
    help="Append an attributed, append-only note (does not overwrite the description)",
)
@click.option("--from", "note_from", help="Author for --note, e.g. 'claude:my-task'")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True, help="DID of the author")
@click.option("--author-location", envvar="HOPPER_LOCATION", hidden=True, help="Location context")
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
    parent: str | None,
    unparent: bool,
    note: str | None,
    note_from: str | None,
    interactive: bool,
    author_did: str | None,
    author_location: str | None,
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
            raise click.Abort() from e

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

    # Handle parent
    if parent:
        update_data["parent_id"] = parent
    elif unparent:
        update_data["parent_id"] = None

    if author_did:
        update_data["author_did"] = author_did
    if author_location:
        update_data["author_location"] = author_location

    if not update_data and not note:
        print_error("No updates specified")
        raise click.Abort()

    # Update task
    try:
        with ctx.get_client() as client:
            result = None
            if update_data:
                result = client.update_task(task_id, update_data)
            if note:
                if not hasattr(client, "add_task_note"):
                    print_error(
                        "Task notes require local (markdown) storage; the "
                        "configured backend does not support them yet."
                    )
                    raise click.Abort()
                result = client.add_task_note(task_id, note, author=note_from)  # type: ignore[union-attr]

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Updated task: {task_id}")
            print_task_detail(result)

    except ClientError as e:
        print_error(f"Failed to update task: {e.message}")
        raise click.Abort() from e


@task.command(name="status")
@click.argument("task_id")
@click.argument(
    "new_status", type=click.Choice(["open", "in_progress", "blocked", "completed", "cancelled"])
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.option("--assign", "-a", help="Assign to an agent or user while changing status")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True, help="DID of the author")
@click.option("--author-location", envvar="HOPPER_LOCATION", hidden=True, help="Location context")
@click.pass_obj
def change_status(
    ctx: Context,
    task_id: str,
    new_status: str,
    force: bool,
    assign: str | None,
    author_did: str | None,
    author_location: str | None,
) -> None:
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
    if author_did:
        update_data["author_did"] = author_did
    if author_location:
        update_data["author_location"] = author_location

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
        raise click.Abort() from e


@task.command(name="delete")
@click.argument("task_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True, help="DID of the author")
@click.pass_obj
def delete_task(ctx: Context, task_id: str, force: bool, author_did: str | None) -> None:
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
            console.print(
                f"\n[bold yellow]![/bold yellow] Could not fetch task details for {task_id}\n"
            )

        if not Confirm.ask("[bold red]Delete this task?[/bold red]", default=False):
            print_info("Cancelled")
            return

    # Delete task
    try:
        with ctx.get_client() as client:
            # Need to pass author_did directly if the client supports it
            client.delete_task(task_id, author_did=author_did)
        print_success(f"Deleted task {task_id}")
    except ClientError as e:
        print_error(f"Failed to delete task: {e.message}")
        raise click.Abort() from e


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
        raise click.Abort() from e


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
        raise click.Abort() from e


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
        raise click.Abort() from e


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


@task.command(name="children")
@click.argument("task_id")
@click.option("--compact", is_flag=True, help="Compact layout")
@click.pass_obj
def task_children(ctx: Context, task_id: str, compact: bool) -> None:
    """List child tasks of a parent task.

    Shows all tasks whose parent_id points to this task, with a
    status rollup summary.

    Examples:
        hopper task children abc12345
    """
    try:
        with ctx.get_client() as client:
            if not hasattr(client, "get_task_with_rollup"):
                print_error("Children requires local mode")
                raise click.Abort()

            parent = client.get_task_with_rollup(task_id)
            children = client.get_task_children(task_id)

        if ctx.json_output:
            print_json({"parent": parent, "children": children})
        else:
            rollup = parent.get("children")
            console.print(
                f"\n[bold cyan]Children of {parent['id'][:8]}[/bold cyan]: {parent.get('title', '')}"
            )
            if rollup:
                total = rollup["total"]
                done = rollup["done"]
                by_status = rollup["by_status"]
                parts = [f"[bold]{k}[/bold]: {v}" for k, v in sorted(by_status.items())]
                console.print(f"Progress: {done}/{total} done  ({', '.join(parts)})\n")
            else:
                console.print("[dim]No children[/dim]\n")

            if children:
                print_task_table(children, compact=compact)
                print_info(f"{len(children)} child task(s)")

    except ClientError as e:
        print_error(f"Failed to get children: {e.message}")
        raise click.Abort() from e


@task.command(name="heartbeat")
@click.argument("task_id")
@click.option(
    "--expect",
    "-e",
    help="When to expect the next heartbeat (e.g. '30m', '2h', '1h30m'). "
    "Use when starting a long-running process so stale detection won't fire early.",
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
        raise click.Abort() from e


@task.command(name="stale")
@click.option(
    "--minutes",
    "-m",
    type=int,
    default=30,
    help="Minutes without heartbeat to consider stale (default: 30)",
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
                    f"Found {len(tasks)} stale task(s) " f"(no heartbeat in {minutes}+ minutes)"
                )
            else:
                print_info(f"No stale tasks (threshold: {minutes} minutes)")

    except ClientError as e:
        print_error(f"Failed to check stale tasks: {e.message}")
        raise click.Abort() from e


@task.command(name="history")
@click.argument("task_id")
@click.option("--limit", type=int, default=50, help="Max revisions to show (default: 50)")
@click.pass_obj
def task_history(ctx: Context, task_id: str, limit: int) -> None:
    """Show revision history for a task.

    Displays each revision with its action, author DID, location context,
    and timestamp. Only available on the SQLite backend.

    Examples:
        hopper task history abc12345
        hopper task history abc12345 --limit 10
    """
    try:
        with ctx.get_client() as client:
            if not hasattr(client, "get_task_history"):
                print_error("History requires local mode")
                raise click.Abort()
            revisions = client.get_task_history(task_id, limit=limit)

        if ctx.json_output:
            print_json(revisions)
            return

        if not revisions:
            print_info(
                f"No revision history for {task_id} (SQLite backend required, or no writes yet)"
            )
            return

        from rich import box
        from rich.table import Table

        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("When", style="dim", min_width=12)
        table.add_column("Action", min_width=8)
        table.add_column("Location", min_width=14)
        table.add_column("Author DID", min_width=20)
        table.add_column("Rev ID", style="dim", min_width=10)

        from hopper.cli.output import format_datetime

        _ACTION_STYLE = {
            "create": "green",
            "update": "cyan",
            "tombstone": "red",
            "propose": "yellow",
            "apply": "green",
            "reject": "red",
        }

        for rev in revisions:
            action = rev.get("action", "?")
            style = _ACTION_STYLE.get(action, "white")
            did = rev.get("author_did") or "—"
            # Abbreviate long DIDs for readability
            if did and len(did) > 28:
                did = did[:12] + "…" + did[-8:]
            table.add_row(
                format_datetime(rev.get("created_at")),
                f"[{style}]{action}[/]",
                rev.get("author_location") or "—",
                did,
                (rev.get("id") or "")[:10],
            )

        console.print(f"\n[bold cyan]Revision history: {task_id}[/bold cyan]\n")
        console.print(table)
        console.print(f"\n[dim]{len(revisions)} revision(s)[/dim]\n")

    except ClientError as e:
        print_error(f"Failed to get history: {e.message}")
        raise click.Abort() from e


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
    ctx.invoke(list_tasks, sort_by="status", limit=50, **kwargs)
