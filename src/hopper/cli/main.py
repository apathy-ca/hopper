"""
Main CLI entry point for Hopper.

Provides command-line interface for Hopper operations including
MCP server management.
"""

import sys
import click

from .mcp_commands import mcp


@click.group()
@click.version_option(version="0.1.0", prog_name="hopper")
def cli() -> None:
    """Hopper - Intelligent Task Routing and Orchestration System."""
    pass


# Register command groups
cli.add_command(mcp)


def main() -> None:
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
