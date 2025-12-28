"""Main CLI application entry point."""


import click
from rich.console import Console

from hopper import __version__
from hopper.cli.config import Config, load_config

console = Console()


class Context:
    """CLI context object to pass configuration between commands."""

    def __init__(self, config: Config, verbose: bool = False, json_output: bool = False):
        self.config = config
        self.verbose = verbose
        self.json_output = json_output
        self.console = console


@click.group()
@click.version_option(version=__version__, prog_name="hopper")
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True),
    help="Path to configuration file",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output in JSON format",
)
@click.pass_context
def cli(ctx: click.Context, config: str | None, verbose: bool, json_output: bool) -> None:
    """Hopper - Universal task queue for human-AI collaborative workflows.

    Hopper provides a powerful CLI for managing tasks, projects, and instances
    across your development workflow.

    Examples:
        hopper task add "Fix login bug"
        hopper task list --status open
        hopper project create my-project
        hopper instance tree
    """
    # Load configuration
    cfg = load_config(config)

    # Create context object
    ctx.obj = Context(config=cfg, verbose=verbose, json_output=json_output)

    if verbose:
        console.print(f"[dim]Hopper v{__version__}[/dim]")
        console.print(f"[dim]Config: {cfg.config_path}[/dim]")


# Import command groups
from hopper.cli.commands.config import auth, config_group, init
from hopper.cli.commands.instance import instance
from hopper.cli.commands.project import project
from hopper.cli.commands.server import server
from hopper.cli.commands.task import add_shortcut, ls_shortcut, task

# Register command groups
cli.add_command(task)
cli.add_command(project)
cli.add_command(instance)
cli.add_command(config_group, name="config")
cli.add_command(init)
cli.add_command(auth)
cli.add_command(server)

# Register shortcuts
cli.add_command(add_shortcut)
cli.add_command(ls_shortcut)


if __name__ == "__main__":
    cli()
