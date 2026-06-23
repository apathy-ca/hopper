"""Main CLI application entry point."""

import click
from rich.console import Console

from hopper import __version__
from hopper.cli.config import Config, get_storage_path, is_local_mode, load_config

console = Console()


class Context:
    """CLI context object to pass configuration between commands."""

    def __init__(
        self,
        config: Config,
        verbose: bool = False,
        json_output: bool = False,
        server: bool = False,
    ):
        self.config = config
        self.verbose = verbose
        self.json_output = json_output
        self._force_server = server
        self.console = console

    @property
    def is_local(self) -> bool:
        """Check if operating in local mode (default)."""
        if self._force_server:
            return False
        return is_local_mode(self.config)

    def get_client(self):
        """Get the appropriate client for the current mode.

        Returns:
            LocalClient for local mode, HopperClient for server mode.
        """
        if self.is_local:
            from hopper.cli.local_client import LocalClient

            storage_path = get_storage_path(self.config, self._force_server)
            return LocalClient(storage_path)
        else:
            from hopper.cli.client import HopperClient

            return HopperClient(self.config)

    def get_storage_path(self):
        """Get the storage path for local mode.

        Returns:
            Path to storage directory, or None for server mode.
        """
        return get_storage_path(self.config, self._force_server)


@click.group(invoke_without_command=True)
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
@click.option(
    "--server",
    "-s",
    is_flag=True,
    help="Use server mode instead of local storage",
)
@click.pass_context
def cli(
    ctx: click.Context, config: str | None, verbose: bool, json_output: bool, server: bool
) -> None:
    """Hopper - Cross-agent persistent memory for human-AI workflows.

    Hopper gives every agent — opencode, Claude, Kilo Code, or human — a
    shared, persistent memory layer. Tasks, learnings, decisions, and session
    state survive across conversations and tool boundaries.

    Examples:
        hopper context                          # Load session context
        hopper task add "Fix login bug"
        hopper task list --status open
        hopper task status <id> in_progress --assign "opencode:my-task" -f
        hopper task heartbeat <id>
        hopper knowledge update-agent-files     # Update global agent config
    """
    # Load configuration
    cfg = load_config(config)

    # Create context object (local is now default, server flag forces server mode)
    ctx.obj = Context(config=cfg, verbose=verbose, json_output=json_output, server=server)

    if verbose:
        console.print(f"[dim]Hopper v{__version__}[/dim]")
        console.print(f"[dim]Config: {cfg.config_path}[/dim]")
        if ctx.obj.is_local:
            storage_path = get_storage_path(cfg, server)
            console.print(f"[dim]Mode: local ({storage_path})[/dim]")
        else:
            console.print(f"[dim]Mode: server ({cfg.current_profile.api.endpoint})[/dim]")

    # Bare `hopper` with no subcommand → list tasks
    if ctx.invoked_subcommand is None:
        ctx.invoke(ls_shortcut)


# Import command groups
from hopper.cli.commands.config import auth, config_group, init
from hopper.cli.commands.context import context
from hopper.cli.commands.github import github
from hopper.cli.commands.instance import instance
from hopper.cli.commands.kinds import register as register_kinds
from hopper.cli.commands.knowledge import knowledge
from hopper.cli.commands.learning import learning
from hopper.cli.commands.maintenance import maintenance
from hopper.cli.commands.overseer import overseer
from hopper.cli.commands.project import project
from hopper.cli.commands.revision import revision
from hopper.cli.commands.server import server
from hopper.cli.commands.task import add_shortcut, ls_shortcut, task
from hopper.cli.commands.upstream import upstream
from hopper.cli.mcp_commands import mcp

# Register command groups
cli.add_command(task)
cli.add_command(project)
cli.add_command(instance)
cli.add_command(learning)
cli.add_command(knowledge)
cli.add_command(context)
cli.add_command(github)
cli.add_command(upstream)
cli.add_command(revision)
cli.add_command(mcp)
cli.add_command(maintenance)
cli.add_command(overseer)

# Shortcut: `hopper sync` → `hopper upstream sync` (with `hopper sync status`)
from hopper.cli.commands.upstream import sync_group  # noqa: E402

cli.add_command(sync_group, name="sync")
cli.add_command(config_group, name="config")
cli.add_command(init)
cli.add_command(auth)
cli.add_command(server)

# Register shortcuts
cli.add_command(add_shortcut)
cli.add_command(ls_shortcut)

# Register per-kind command groups (Phase 4c)
register_kinds(cli)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
