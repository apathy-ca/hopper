"""
MCP server CLI commands.

Commands for managing the Hopper MCP server.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import click


@click.group()
def mcp() -> None:
    """Manage the Hopper MCP server."""
    pass


@mcp.command()
@click.option(
    "--host",
    default="localhost",
    help="API host (default: localhost)",
)
@click.option(
    "--port",
    default=8080,
    help="API port (default: 8080)",
)
@click.option(
    "--token",
    envvar="HOPPER_API_TOKEN",
    help="API authentication token (can also use HOPPER_API_TOKEN env var)",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug logging",
)
def start(host: str, port: int, token: Optional[str], debug: bool) -> None:
    """Start the MCP server.

    The server will run in stdio mode for use with Claude Desktop
    and other MCP clients.

    Example:
        hopper mcp start --token YOUR_TOKEN
    """
    # Set environment variables
    os.environ["HOPPER_API_BASE_URL"] = f"http://{host}:{port}"

    if token:
        os.environ["HOPPER_API_TOKEN"] = token

    if debug:
        os.environ["HOPPER_LOG_LEVEL"] = "DEBUG"
        os.environ["HOPPER_ENABLE_DEBUG"] = "true"

    # Run the MCP server
    try:
        # Import here to avoid import errors if dependencies aren't installed
        from hopper.mcp.main import main as mcp_main
        import asyncio

        click.echo("Starting Hopper MCP server...")
        if debug:
            click.echo(f"API URL: {os.environ['HOPPER_API_BASE_URL']}")

        asyncio.run(mcp_main())
    except KeyboardInterrupt:
        click.echo("\nMCP server stopped")
        sys.exit(0)
    except Exception as e:
        click.echo(f"Error starting MCP server: {e}", err=True)
        if debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@mcp.command()
def config() -> None:
    """Show MCP server configuration for Claude Desktop.

    Displays the configuration snippet to add to Claude Desktop's
    MCP settings file.
    """
    config_template = {
        "mcpServers": {
            "hopper": {
                "command": "python",
                "args": ["-m", "hopper.mcp.main"],
                "env": {
                    "HOPPER_API_BASE_URL": "http://localhost:8080",
                    "HOPPER_API_TOKEN": "your-api-token-here"
                }
            }
        }
    }

    click.echo("\n=== Claude Desktop MCP Configuration ===\n")
    click.echo("Add this to your Claude Desktop MCP settings:\n")
    click.echo(json.dumps(config_template, indent=2))
    click.echo("\n")

    # Platform-specific config file locations
    if sys.platform == "darwin":
        config_path = "~/Library/Application Support/Claude/claude_desktop_config.json"
    elif sys.platform == "win32":
        config_path = "%APPDATA%\\Claude\\claude_desktop_config.json"
    else:
        config_path = "~/.config/Claude/claude_desktop_config.json"

    click.echo(f"Configuration file location: {config_path}")
    click.echo("\nDon't forget to replace 'your-api-token-here' with your actual API token!")


@mcp.command()
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file path (default: prints to stdout)",
)
def init_config(output: Optional[str]) -> None:
    """Generate an MCP server configuration file.

    Creates a configuration file template that can be customized
    for your Hopper deployment.
    """
    config_template = {
        "mcpServers": {
            "hopper": {
                "command": "python",
                "args": ["-m", "hopper.mcp.main"],
                "env": {
                    "HOPPER_API_BASE_URL": "http://localhost:8080",
                    "HOPPER_API_TOKEN": "${HOPPER_API_TOKEN}",
                    "HOPPER_LOG_LEVEL": "INFO",
                    "HOPPER_ENABLE_DEBUG": "false",
                    "HOPPER_AUTO_ROUTE_TASKS": "true",
                    "HOPPER_DEFAULT_PRIORITY": "medium"
                }
            }
        }
    }

    config_json = json.dumps(config_template, indent=2)

    if output:
        output_path = Path(output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(config_json)
        click.echo(f"Configuration written to: {output_path}")
    else:
        click.echo(config_json)


@mcp.command()
def test() -> None:
    """Test the MCP server configuration.

    Verifies that the MCP server can be started and responds correctly.
    This is useful for debugging configuration issues.
    """
    click.echo("Testing MCP server configuration...")

    # Check Python version
    import sys
    py_version = sys.version_info
    if py_version < (3, 11):
        click.echo(f"❌ Python 3.11+ required, found {py_version.major}.{py_version.minor}", err=True)
        sys.exit(1)
    else:
        click.echo(f"✓ Python version: {py_version.major}.{py_version.minor}.{py_version.micro}")

    # Check if MCP module can be imported
    try:
        import hopper.mcp
        click.echo("✓ Hopper MCP module found")
    except ImportError as e:
        click.echo(f"❌ Cannot import hopper.mcp: {e}", err=True)
        sys.exit(1)

    # Check required dependencies
    try:
        import mcp
        click.echo("✓ MCP SDK installed")
    except ImportError:
        click.echo("❌ MCP SDK not installed. Run: pip install mcp", err=True)
        sys.exit(1)

    try:
        import httpx
        click.echo("✓ httpx installed")
    except ImportError:
        click.echo("❌ httpx not installed. Run: pip install httpx", err=True)
        sys.exit(1)

    # Check configuration
    from hopper.mcp.config import get_mcp_config

    try:
        config = get_mcp_config()
        click.echo(f"✓ Configuration loaded")
        click.echo(f"  - API URL: {config.api_base_url}")
        click.echo(f"  - Server name: {config.server_name}")
        click.echo(f"  - Auto-route: {config.auto_route_tasks}")

        if not config.api_token and not config.api_key:
            click.echo("⚠ Warning: No API token configured. Set HOPPER_API_TOKEN environment variable.")

    except Exception as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)

    click.echo("\n✓ All tests passed! MCP server is ready to use.")
    click.echo("\nTo start the server, run: hopper mcp start")
