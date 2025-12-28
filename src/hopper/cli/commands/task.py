"""Task management commands."""


import click
from rich.prompt import Confirm, Prompt

from hopper.cli.client import APIError, HopperClient
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


@click.group(name="task")
def task() -> None:
    """Manage Hopper tasks.

    Tasks are the core units of work in Hopper. You can create, list, update,
    and manage tasks through this command group.
    """
    pass


@task.command(name="add")
@click.argument("title", required=False)
@click.option("--description", "-d", help="Task description")
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
@click.pass_obj
def add_task(
    ctx: Context,
    title: str | None,
    description: str | None,
    priority: str,
    tag: tuple[str, ...],
    project: str | None,
    status: str,
) -> None:
    """Create a new task.

    If TITLE is not provided, you'll be prompted to enter it interactively.

    Examples:
        hopper task add "Fix login bug"
        hopper task add "Add dark mode" -p high -t feature -t ui
        hopper task add --project my-project
    """
    # Interactive mode if no title provided
    if not title:
        title = Prompt.ask("[bold]Task title[/bold]")
        if not title:
            print_error("Title is required")
            raise click.Abort()

    # Interactive prompts for additional fields if not in quick mode
    if not description and not tag:
        if Confirm.ask("Add description?", default=False):
            description = Prompt.ask("[bold]Description[/bold]", default="")

        if Confirm.ask("Add tags?", default=False):
            tags_input = Prompt.ask("[bold]Tags (comma-separated)[/bold]", default="")
            tag = tuple(t.strip() for t in tags_input.split(",") if t.strip())

    # Build task data
    task_data = {
        "title": title,
        "status": status,
        "priority": priority,
    }

    if description:
        task_data["description"] = description

    if tag:
        task_data["tags"] = list(tag)

    if project:
        task_data["project_id"] = project

    # Create task via API
    try:
        with HopperClient(ctx.config) as client:
            result = client.create_task(task_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Created task: {result.get('id', '')}")
            print_task_detail(result)

    except APIError as e:
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
        with HopperClient(ctx.config) as client:
            tasks = client.list_tasks(**params)

        if ctx.json_output:
            print_json(tasks)
        else:
            print_task_table(tasks, compact=compact)
            if tasks:
                print_info(f"Showing {len(tasks)} task(s)")

    except APIError as e:
        print_error(f"Failed to list tasks: {e.message}")
        raise click.Abort()


@task.command(name="get")
@click.argument("task_id")
@click.pass_obj
def get_task(ctx: Context, task_id: str) -> None:
    """Get detailed information about a task.

    Examples:
        hopper task get abc12345
    """
    try:
        with HopperClient(ctx.config) as client:
            task = client.get_task(task_id)

        if ctx.json_output:
            print_json(task)
        else:
            print_task_detail(task)

    except APIError as e:
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
            with HopperClient(ctx.config) as client:
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

        except APIError as e:
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

    if not update_data:
        print_error("No updates specified")
        raise click.Abort()

    # Update task
    try:
        with HopperClient(ctx.config) as client:
            result = client.update_task(task_id, update_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Updated task: {task_id}")
            print_task_detail(result)

    except APIError as e:
        print_error(f"Failed to update task: {e.message}")
        raise click.Abort()


@task.command(name="status")
@click.argument("task_id")
@click.argument(
    "new_status", type=click.Choice(["open", "in_progress", "blocked", "completed", "cancelled"])
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def change_status(ctx: Context, task_id: str, new_status: str, force: bool) -> None:
    """Change task status.

    Examples:
        hopper task status abc12345 in_progress
        hopper task status abc12345 completed
    """
    # Confirmation
    if not force:
        if not Confirm.ask(f"Change status to '{new_status}'?", default=True):
            print_info("Cancelled")
            return

    # Update status
    try:
        with HopperClient(ctx.config) as client:
            result = client.update_task(task_id, {"status": new_status})

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Changed status to: {new_status}")

    except APIError as e:
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
            with HopperClient(ctx.config) as client:
                task = client.get_task(task_id)
            console.print(f"\n[bold]Task to delete:[/bold] {task.get('title', '')}\n")
        except APIError:
            pass

        if not Confirm.ask("[bold red]Delete this task?[/bold red]", default=False):
            print_info("Cancelled")
            return

    # Delete task
    try:
        with HopperClient(ctx.config) as client:
            client.delete_task(task_id)

        print_success(f"Deleted task: {task_id}")

    except APIError as e:
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
        with HopperClient(ctx.config) as client:
            results = client.search_tasks(query, **params)

        if ctx.json_output:
            print_json(results)
        else:
            print_task_table(results, compact=compact)
            if results:
                print_info(f"Found {len(results)} task(s) matching '{query}'")
            else:
                print_info(f"No tasks found matching '{query}'")

    except APIError as e:
        print_error(f"Search failed: {e.message}")
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
