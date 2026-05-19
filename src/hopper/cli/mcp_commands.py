"""
MCP server CLI commands.

Commands for managing the Hopper MCP server.
"""

import json
import os
import sys
from pathlib import Path

import click
import httpx

from hopper.cli.output import print_error, print_info, print_json, print_success, print_warning


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
def start(host: str, port: int, token: str | None, debug: bool) -> None:
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
        import asyncio

        from hopper.mcp.main import main as mcp_main

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
    api_base_url = _get_default_server()
    config_template = {
        "mcpServers": {
            "hopper": {
                "command": "python",
                "args": ["-m", "hopper.mcp.main"],
                "env": {
                    "HOPPER_API_BASE_URL": api_base_url,
                    "HOPPER_API_TOKEN": "your-api-token-here",
                },
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
def init_config(output: str | None) -> None:
    """Generate an MCP server configuration file.

    Creates a configuration file template that can be customized
    for your Hopper deployment.
    """
    api_base_url = _get_default_server()
    config_template = {
        "mcpServers": {
            "hopper": {
                "command": "python",
                "args": ["-m", "hopper.mcp.main"],
                "env": {
                    "HOPPER_API_BASE_URL": api_base_url,
                    "HOPPER_API_TOKEN": "${HOPPER_API_TOKEN}",
                    "HOPPER_LOG_LEVEL": "INFO",
                    "HOPPER_ENABLE_DEBUG": "false",
                    "HOPPER_AUTO_ROUTE_TASKS": "true",
                    "HOPPER_DEFAULT_PRIORITY": "medium",
                },
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
        click.echo(
            f"❌ Python 3.11+ required, found {py_version.major}.{py_version.minor}", err=True
        )
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
        click.echo("✓ Configuration loaded")
        click.echo(f"  - API URL: {config.api_base_url}")
        click.echo(f"  - Server name: {config.server_name}")
        click.echo(f"  - Auto-route: {config.auto_route_tasks}")

        if not config.api_token and not config.api_key:
            click.echo(
                "⚠ Warning: No API token configured. Set HOPPER_API_TOKEN environment variable."
            )

    except Exception as e:
        click.echo(f"❌ Configuration error: {e}", err=True)
        sys.exit(1)

    click.echo("\n✓ All tests passed! MCP server is ready to use.")
    click.echo("\nTo start the server, run: hopper mcp start")


# --- MCP Token Management Commands ---


def _get_did_key():
    """Load DID key for MCP authentication."""
    from hopper.upstream.did import DIDKey

    did_key_path = Path.home() / ".hopper" / "did.key"

    if did_key_path.exists():
        return DIDKey.load(did_key_path)

    raise click.ClickException(
        f"No DID key found at {did_key_path}.\n"
        "Run 'hopper upstream init' to generate one.\n"
        "If this host is ephemeral, store the key outside the home directory and\n"
        "set did_key_path in your Hopper config to point to it."
    )


def _get_default_server() -> str:
    """Get default server URL from config or fallback."""
    try:
        from hopper.cli.config import load_config

        config = load_config()
        if config.current_profile.upstream.server:
            return config.current_profile.upstream.server
    except Exception:
        pass
    return "http://localhost:8080"


@mcp.command(name="init-token")
@click.option(
    "--server",
    "-s",
    default=None,
    help="Hopper server URL (default from config or http://localhost:8080)",
)
@click.option(
    "--label",
    "-l",
    default="claude-web",
    help="Label for this token (default: claude-web)",
)
@click.option(
    "--instance",
    "-i",
    default=None,
    help="Instance name (default: read from local .hopper context)",
)
@click.option(
    "--instance-path",
    "-p",
    default=None,
    help="Path to instance storage directory",
)
def mcp_init_token(server: str | None, label: str, instance: str | None, instance_path: str | None) -> None:
    """Register for MCP access and get a Bearer token.

    Creates a token linked to your DID and a specific Hopper instance.
    The instance name is read from the nearest .hopper context automatically;
    use -i to override it explicitly.

    Examples:
        hopper mcp init-token --server https://hopper.example.com
        hopper mcp init-token -s https://hopper.example.com -i work
        hopper mcp init-token -s https://hopper.example.com -i project -p /path/to/project/.hopper
    """
    from hopper.upstream.did import sign_request
    from hopper.cli.config import detect_embedded_hopper
    from hopper.storage.base import StorageConfig

    # Get server URL
    server_url = server or _get_default_server()
    server_url = server_url.rstrip("/")

    # Load or generate DID key
    did_key = _get_did_key()

    # Auto-detect instance name and path from .hopper context when not provided
    if instance is None or instance_path is None:
        embedded = detect_embedded_hopper()
        if embedded:
            if instance is None:
                instance = StorageConfig._read_instance_name(embedded) or embedded.parent.name
            if instance_path is None:
                instance_path = str(embedded)
    if instance is None:
        instance = "default"

    # Sign request to server
    body = {
        "label": label,
        "instance": instance,
        "instance_path": instance_path,
    }
    path = "/mcp/register"

    # Serialize body consistently for signing
    body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    auth_header = sign_request(did_key, "POST", path, body_bytes)

    # Make request
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{server_url}{path}",
                content=body_bytes,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                },
            )

        if response.status_code == 200:
            data = response.json()
            click.echo("\n" + "=" * 60)
            click.echo("MCP TOKEN GENERATED")
            click.echo("=" * 60)
            click.echo(f"\nYour token: {data['token']}")
            click.echo(f"Your DID:   {data['did']}")
            click.echo(f"Instance:   {data.get('instance', 'default')}")
            if "expires_at" in data:
                click.echo(f"Expires:    {data['expires_at']}")
            click.echo("\nAdd to Claude Web config:")
            click.echo('  "authorization_token": "' + data["token"] + '"')
            click.echo("=" * 60 + "\n")
        elif response.status_code == 401:
            print_error("DID authentication failed")
            raise click.Abort()
        elif response.status_code == 403:
            detail = response.json().get("detail", "Not authorized")
            print_error(f"Access denied: {detail}")
            print_info("Your DID may be pending approval. Contact the server admin.")
            raise click.Abort()
        else:
            print_error(f"Server error ({response.status_code}): {response.text}")
            raise click.Abort()

    except httpx.ConnectError:
        print_error(f"Could not connect to server: {server_url}")
        print_info("Check that the server URL is correct and the server is running.")
        raise click.Abort()
    except httpx.RequestError as e:
        print_error(f"Request failed: {e}")
        raise click.Abort()


@mcp.command(name="tokens")
@click.option(
    "--server",
    "-s",
    default=None,
    help="Hopper server URL",
)
@click.option(
    "--json",
    "json_output",
    is_flag=True,
    help="Output as JSON",
)
def mcp_tokens(server: str | None, json_output: bool) -> None:
    """List your MCP tokens.

    Shows all tokens associated with your DID identity.

    Example:
        hopper mcp tokens --server https://hopper.example.com
    """
    from hopper.upstream.did import sign_request

    # Get server URL
    server_url = server or _get_default_server()
    server_url = server_url.rstrip("/")

    # Load DID key
    did_key_path = Path.home() / ".hopper" / "did.key"
    if not did_key_path.exists():
        print_error("No DID key found. Run 'hopper mcp init-token' first to generate one.")
        raise click.Abort()

    from hopper.upstream.did import DIDKey

    did_key = DIDKey.load(did_key_path)

    # Sign request
    path = "/mcp/tokens"
    auth_header = sign_request(did_key, "GET", path, None)

    # Make request
    try:
        with httpx.Client(timeout=30) as client:
            response = client.get(
                f"{server_url}{path}",
                headers={
                    "Authorization": auth_header,
                },
            )

        if response.status_code == 200:
            data = response.json()
            tokens = data.get("tokens", [])

            if json_output:
                print_json(data)
            elif not tokens:
                print_info("No tokens found.")
            else:
                click.echo(f"\nTokens for DID: {did_key.did[:50]}...\n")
                for token in tokens:
                    prefix = token.get("prefix", token.get("token", "")[:12])
                    label = token.get("label", "")
                    instance = token.get("instance", "default")
                    created = token.get("created_at", "")
                    last_used = token.get("last_used", "never")

                    click.echo(f"  {prefix}...")
                    click.echo(f"    Label:     {label}")
                    click.echo(f"    Instance:  {instance}")
                    click.echo(f"    Created:   {created}")
                    click.echo(f"    Last used: {last_used}")
                    click.echo()
        elif response.status_code == 401:
            print_error("DID authentication failed")
            raise click.Abort()
        else:
            print_error(f"Server error ({response.status_code}): {response.text}")
            raise click.Abort()

    except httpx.ConnectError:
        print_error(f"Could not connect to server: {server_url}")
        raise click.Abort()
    except httpx.RequestError as e:
        print_error(f"Request failed: {e}")
        raise click.Abort()


@mcp.command(name="revoke")
@click.argument("token_prefix")
@click.option(
    "--server",
    "-s",
    default=None,
    help="Hopper server URL",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def mcp_revoke(token_prefix: str, server: str | None, force: bool) -> None:
    """Revoke an MCP token.

    Revokes a token matching the given prefix. The prefix should be the
    first characters of the token (at least 8 characters recommended).

    Example:
        hopper mcp revoke abc123xy --server https://hopper.example.com
    """
    from hopper.upstream.did import sign_request

    # Get server URL
    server_url = server or _get_default_server()
    server_url = server_url.rstrip("/")

    # Load DID key
    did_key_path = Path.home() / ".hopper" / "did.key"
    if not did_key_path.exists():
        print_error("No DID key found. Run 'hopper mcp init-token' first.")
        raise click.Abort()

    from hopper.upstream.did import DIDKey

    did_key = DIDKey.load(did_key_path)

    # Confirm
    if not force:
        click.confirm(
            f"Revoke token starting with '{token_prefix}'?",
            abort=True,
        )

    # Sign request
    body = {"prefix": token_prefix}
    path = "/mcp/revoke"
    body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
    auth_header = sign_request(did_key, "POST", path, body_bytes)

    # Make request
    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{server_url}{path}",
                content=body_bytes,
                headers={
                    "Authorization": auth_header,
                    "Content-Type": "application/json",
                },
            )

        if response.status_code == 200:
            data = response.json()
            revoked_count = data.get("revoked", 1)
            print_success(f"Revoked {revoked_count} token(s)")
        elif response.status_code == 401:
            print_error("DID authentication failed")
            raise click.Abort()
        elif response.status_code == 404:
            print_error(f"No token found matching prefix '{token_prefix}'")
            raise click.Abort()
        else:
            print_error(f"Server error ({response.status_code}): {response.text}")
            raise click.Abort()

    except httpx.ConnectError:
        print_error(f"Could not connect to server: {server_url}")
        raise click.Abort()
    except httpx.RequestError as e:
        print_error(f"Request failed: {e}")
        raise click.Abort()
