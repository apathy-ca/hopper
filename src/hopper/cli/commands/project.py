"""Project management commands."""


import click
from rich.prompt import Confirm, Prompt

from hopper.cli.client import APIError, HopperClient
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_json,
    print_project_table,
    print_success,
    print_task_table,
)


@click.group(name="project")
def project() -> None:
    """Manage Hopper projects.

    Projects organize tasks and provide configuration for routing and
    intelligence.
    """
    pass


@project.command(name="create")
@click.argument("name", required=False)
@click.option("--description", "-d", help="Project description")
@click.option("--config", "-c", help="Project configuration (JSON)")
@click.pass_obj
def create_project(
    ctx: Context,
    name: str | None,
    description: str | None,
    config: str | None,
) -> None:
    """Create a new project.

    Examples:
        hopper project create my-project
        hopper project create my-project -d "My awesome project"
    """
    # Interactive mode if no name provided
    if not name:
        name = Prompt.ask("[bold]Project name[/bold]")
        if not name:
            print_error("Name is required")
            raise click.Abort()

    if not description:
        description = Prompt.ask("[bold]Description[/bold]", default="")

    # Build project data
    project_data = {
        "name": name,
    }

    if description:
        project_data["description"] = description

    if config:
        import json

        try:
            project_data["config"] = json.loads(config)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON config: {e}")
            raise click.Abort()

    # Create project
    try:
        with HopperClient(ctx.config) as client:
            result = client.create_project(project_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Created project: {result.get('id', '')}")
            console.print(f"[bold]{result.get('name', '')}[/bold]")
            if desc := result.get("description"):
                console.print(f"[dim]{desc}[/dim]")

    except APIError as e:
        print_error(f"Failed to create project: {e.message}")
        raise click.Abort()


@project.command(name="list")
@click.option("--limit", type=int, default=50, help="Maximum number of projects")
@click.pass_obj
def list_projects(ctx: Context, limit: int) -> None:
    """List all projects.

    Examples:
        hopper project list
        hopper project list --limit 20
    """
    try:
        with HopperClient(ctx.config) as client:
            projects = client.list_projects(limit=limit)

        if ctx.json_output:
            print_json(projects)
        else:
            print_project_table(projects)
            if projects:
                print_info(f"Showing {len(projects)} project(s)")

    except APIError as e:
        print_error(f"Failed to list projects: {e.message}")
        raise click.Abort()


@project.command(name="get")
@click.argument("project_id")
@click.pass_obj
def get_project(ctx: Context, project_id: str) -> None:
    """Get detailed project information.

    Examples:
        hopper project get abc12345
    """
    try:
        with HopperClient(ctx.config) as client:
            proj = client.get_project(project_id)

        if ctx.json_output:
            print_json(proj)
        else:
            console.print(f"\n[bold cyan]Project {proj.get('id', '')}[/bold cyan]")
            console.print(f"[bold]{proj.get('name', '')}[/bold]\n")

            if desc := proj.get("description"):
                console.print(f"[bold]Description:[/bold]\n{desc}\n")

            if config := proj.get("config"):
                console.print("[bold]Configuration:[/bold]")
                print_json(config)

            task_count = proj.get("task_count", 0)
            console.print(f"\n[bold]Tasks:[/bold] {task_count}")

            from hopper.cli.output import format_datetime

            console.print(f"\n[dim]Created: {format_datetime(proj.get('created_at'))}[/dim]")
            if updated := proj.get("updated_at"):
                console.print(f"[dim]Updated: {format_datetime(updated)}[/dim]")

            console.print()

    except APIError as e:
        print_error(f"Failed to get project: {e.message}")
        raise click.Abort()


@project.command(name="update")
@click.argument("project_id")
@click.option("--name", help="New name")
@click.option("--description", help="New description")
@click.option("--config", help="New configuration (JSON)")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.pass_obj
def update_project(
    ctx: Context,
    project_id: str,
    name: str | None,
    description: str | None,
    config: str | None,
    interactive: bool,
) -> None:
    """Update a project.

    Examples:
        hopper project update abc12345 --name "New name"
        hopper project update abc12345 --interactive
    """
    # Interactive mode
    if interactive:
        try:
            with HopperClient(ctx.config) as client:
                current = client.get_project(project_id)

            console.print(f"\n[bold]Current:[/bold] {current.get('name', '')}\n")
            console.print("[bold]Update project (press Enter to keep current value):[/bold]\n")

            name = Prompt.ask("Name", default=current.get("name", ""))
            description = Prompt.ask("Description", default=current.get("description", ""))

        except APIError as e:
            print_error(f"Failed to get project: {e.message}")
            raise click.Abort()

    # Build update data
    update_data = {}

    if name:
        update_data["name"] = name
    if description:
        update_data["description"] = description
    if config:
        import json

        try:
            update_data["config"] = json.loads(config)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON config: {e}")
            raise click.Abort()

    if not update_data:
        print_error("No updates specified")
        raise click.Abort()

    # Update project
    try:
        with HopperClient(ctx.config) as client:
            result = client.update_project(project_id, update_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Updated project: {project_id}")
            console.print(f"[bold]{result.get('name', '')}[/bold]")

    except APIError as e:
        print_error(f"Failed to update project: {e.message}")
        raise click.Abort()


@project.command(name="delete")
@click.argument("project_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def delete_project(ctx: Context, project_id: str, force: bool) -> None:
    """Delete a project.

    WARNING: This may affect associated tasks.

    Examples:
        hopper project delete abc12345
        hopper project delete abc12345 --force
    """
    # Get project info for confirmation
    if not force:
        try:
            with HopperClient(ctx.config) as client:
                proj = client.get_project(project_id)

            console.print(f"\n[bold]Project to delete:[/bold] {proj.get('name', '')}")
            task_count = proj.get("task_count", 0)
            if task_count > 0:
                console.print(
                    f"[bold yellow]Warning:[/bold yellow] This project has {task_count} task(s)"
                )
            console.print()

        except APIError:
            pass

        if not Confirm.ask("[bold red]Delete this project?[/bold red]", default=False):
            print_info("Cancelled")
            return

    # Delete project
    try:
        with HopperClient(ctx.config) as client:
            client.delete_project(project_id)

        print_success(f"Deleted project: {project_id}")

    except APIError as e:
        print_error(f"Failed to delete project: {e.message}")
        raise click.Abort()


@project.command(name="tasks")
@click.argument("project_id")
@click.option("--status", help="Filter by status")
@click.option("--priority", help="Filter by priority")
@click.option("--limit", type=int, default=50, help="Maximum tasks")
@click.option("--compact", is_flag=True, help="Compact layout")
@click.pass_obj
def list_project_tasks(
    ctx: Context,
    project_id: str,
    status: str | None,
    priority: str | None,
    limit: int,
    compact: bool,
) -> None:
    """List tasks for a project.

    Examples:
        hopper project tasks abc12345
        hopper project tasks abc12345 --status open
    """
    params = {
        "project": project_id,
        "limit": limit,
    }

    if status:
        params["status"] = status
    if priority:
        params["priority"] = priority

    try:
        with HopperClient(ctx.config) as client:
            tasks = client.list_tasks(**params)

        if ctx.json_output:
            print_json(tasks)
        else:
            # Show project header
            try:
                proj = client.get_project(project_id)
                console.print(
                    f"\n[bold cyan]Tasks for project: {proj.get('name', '')}[/bold cyan]\n"
                )
            except APIError:
                pass

            print_task_table(tasks, compact=compact)
            if tasks:
                print_info(f"Showing {len(tasks)} task(s)")

    except APIError as e:
        print_error(f"Failed to list project tasks: {e.message}")
        raise click.Abort()
