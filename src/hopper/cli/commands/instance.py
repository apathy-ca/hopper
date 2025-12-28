"""Instance management commands."""


import click
from rich.prompt import Confirm, Prompt

from hopper.cli.client import APIError, HopperClient
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_instance_tree,
    print_json,
    print_success,
)


@click.group(name="instance")
def instance() -> None:
    """Manage Hopper instances.

    Hopper instances form a hierarchy:
    - Global: Strategic routing across all projects
    - Project: Project-specific task management
    - Orchestration: Execution-level task queues
    """
    pass


@instance.command(name="create")
@click.argument("name", required=False)
@click.option(
    "--scope",
    type=click.Choice(["global", "project", "orchestration"]),
    required=True,
    help="Instance scope",
)
@click.option("--parent", help="Parent instance ID")
@click.option("--config", help="Instance configuration (JSON)")
@click.pass_obj
def create_instance(
    ctx: Context,
    name: str | None,
    scope: str,
    parent: str | None,
    config: str | None,
) -> None:
    """Create a new Hopper instance.

    Examples:
        hopper instance create --scope global
        hopper instance create my-project --scope project --parent global-id
        hopper instance create run-123 --scope orchestration --parent project-id
    """
    # Interactive mode if no name
    if not name:
        name = Prompt.ask(f"[bold]{scope.capitalize()} instance name[/bold]")
        if not name:
            print_error("Name is required")
            raise click.Abort()

    # Build instance data
    instance_data = {
        "name": name,
        "scope": scope,
    }

    if parent:
        instance_data["parent_id"] = parent

    if config:
        import json

        try:
            instance_data["config"] = json.loads(config)
        except json.JSONDecodeError as e:
            print_error(f"Invalid JSON config: {e}")
            raise click.Abort()

    # Create instance
    try:
        with HopperClient(ctx.config) as client:
            result = client.create_instance(instance_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Created {scope} instance: {result.get('id', '')}")
            console.print(f"[bold]{result.get('name', '')}[/bold]")

    except APIError as e:
        print_error(f"Failed to create instance: {e.message}")
        raise click.Abort()


@instance.command(name="list")
@click.option(
    "--scope", type=click.Choice(["global", "project", "orchestration"]), help="Filter by scope"
)
@click.option("--parent", help="Filter by parent instance ID")
@click.option("--limit", type=int, default=50, help="Maximum instances")
@click.pass_obj
def list_instances(
    ctx: Context,
    scope: str | None,
    parent: str | None,
    limit: int,
) -> None:
    """List Hopper instances.

    Examples:
        hopper instance list
        hopper instance list --scope project
        hopper instance list --parent global-id
    """
    params = {"limit": limit}

    if scope:
        params["scope"] = scope
    if parent:
        params["parent_id"] = parent

    try:
        with HopperClient(ctx.config) as client:
            instances = client.list_instances(**params)

        if ctx.json_output:
            print_json(instances)
        else:
            if not instances:
                print_info("No instances found")
                return

            # Display as simple table
            from rich import box
            from rich.table import Table

            table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Name", style="bold")
            table.add_column("Scope")
            table.add_column("Status", justify="center")
            table.add_column("Parent", style="dim")

            for inst in instances:
                inst_id = str(inst.get("id", ""))[:8]
                name = inst.get("name", "")
                scope = inst.get("scope", "")
                status = inst.get("status", "inactive")
                parent_id = str(inst.get("parent_id", "—"))[:8] if inst.get("parent_id") else "—"

                from hopper.cli.output import get_status_style

                table.add_row(
                    inst_id,
                    name,
                    scope,
                    f"[{get_status_style(status)}]{status}[/]",
                    parent_id,
                )

            console.print(table)
            print_info(f"Showing {len(instances)} instance(s)")

    except APIError as e:
        print_error(f"Failed to list instances: {e.message}")
        raise click.Abort()


@instance.command(name="get")
@click.argument("instance_id")
@click.pass_obj
def get_instance(ctx: Context, instance_id: str) -> None:
    """Get detailed instance information.

    Examples:
        hopper instance get abc12345
    """
    try:
        with HopperClient(ctx.config) as client:
            inst = client.get_instance(instance_id)

        if ctx.json_output:
            print_json(inst)
        else:
            console.print(f"\n[bold cyan]Instance {inst.get('id', '')}[/bold cyan]")
            console.print(f"[bold]{inst.get('name', '')}[/bold]\n")

            scope = inst.get("scope", "")
            status = inst.get("status", "inactive")
            from hopper.cli.output import get_status_style

            console.print(f"[bold]Scope:[/bold] {scope}")
            console.print(f"[bold]Status:[/bold] [{get_status_style(status)}]{status}[/]")

            if parent_id := inst.get("parent_id"):
                console.print(f"[bold]Parent:[/bold] {parent_id}")

            if config := inst.get("config"):
                console.print("\n[bold]Configuration:[/bold]")
                print_json(config)

            if children := inst.get("children"):
                console.print(f"\n[bold]Child Instances:[/bold] {len(children)}")

            if queue_size := inst.get("queue_size"):
                console.print(f"\n[bold]Task Queue:[/bold] {queue_size} task(s)")

            from hopper.cli.output import format_datetime

            console.print(f"\n[dim]Created: {format_datetime(inst.get('created_at'))}[/dim]")

            console.print()

    except APIError as e:
        print_error(f"Failed to get instance: {e.message}")
        raise click.Abort()


@instance.command(name="tree")
@click.option("--root", help="Root instance ID (default: show all)")
@click.pass_obj
def show_tree(ctx: Context, root: str | None) -> None:
    """Show instance hierarchy as a tree.

    Examples:
        hopper instance tree
        hopper instance tree --root global-id
    """
    try:
        with HopperClient(ctx.config) as client:
            params = {}
            if root:
                params["root"] = root

            instances = client.list_instances(**params)

        if ctx.json_output:
            print_json(instances)
        else:
            print_instance_tree(instances)

    except APIError as e:
        print_error(f"Failed to get instance tree: {e.message}")
        raise click.Abort()


@instance.command(name="start")
@click.argument("instance_id")
@click.pass_obj
def start_instance(ctx: Context, instance_id: str) -> None:
    """Start a Hopper instance.

    Examples:
        hopper instance start abc12345
    """
    try:
        with HopperClient(ctx.config) as client:
            result = client.start_instance(instance_id)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Started instance: {instance_id}")

    except APIError as e:
        print_error(f"Failed to start instance: {e.message}")
        raise click.Abort()


@instance.command(name="stop")
@click.argument("instance_id")
@click.option("--force", "-f", is_flag=True, help="Force stop")
@click.pass_obj
def stop_instance(ctx: Context, instance_id: str, force: bool) -> None:
    """Stop a Hopper instance.

    Examples:
        hopper instance stop abc12345
        hopper instance stop abc12345 --force
    """
    if not force:
        if not Confirm.ask(f"Stop instance {instance_id}?", default=True):
            print_info("Cancelled")
            return

    try:
        with HopperClient(ctx.config) as client:
            result = client.stop_instance(instance_id)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Stopped instance: {instance_id}")

    except APIError as e:
        print_error(f"Failed to stop instance: {e.message}")
        raise click.Abort()


@instance.command(name="status")
@click.argument("instance_id")
@click.pass_obj
def get_status(ctx: Context, instance_id: str) -> None:
    """Get instance status and health.

    Examples:
        hopper instance status abc12345
    """
    try:
        with HopperClient(ctx.config) as client:
            status = client.get_instance_status(instance_id)

        if ctx.json_output:
            print_json(status)
        else:
            console.print("\n[bold cyan]Instance Status[/bold cyan]\n")

            state = status.get("status", "unknown")
            from hopper.cli.output import get_status_style

            console.print(f"[bold]Status:[/bold] [{get_status_style(state)}]{state}[/]")

            if uptime := status.get("uptime"):
                console.print(f"[bold]Uptime:[/bold] {uptime}")

            if queue_size := status.get("queue_size"):
                console.print(f"[bold]Queue Size:[/bold] {queue_size}")

            if health := status.get("health"):
                health_color = (
                    "green" if health == "healthy" else "yellow" if health == "degraded" else "red"
                )
                console.print(
                    f"[bold]Health:[/bold] [bold {health_color}]{health}[/bold {health_color}]"
                )

            console.print()

    except APIError as e:
        print_error(f"Failed to get instance status: {e.message}")
        raise click.Abort()
