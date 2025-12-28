"""Configuration and authentication commands."""

from typing import Optional
from pathlib import Path

import click
from rich.prompt import Prompt, Confirm
from rich.table import Table
from rich import box

from hopper.cli.main import Context
from hopper.cli.config import Config, get_config_dir, ProfileConfig, APIConfig, AuthConfig
from hopper.cli.client import HopperClient, APIError
from hopper.cli.output import (
    print_json,
    print_success,
    print_error,
    print_info,
    print_warning,
    console,
)


@click.command(name="init")
@click.option("--profile", default="default", help="Profile name to initialize")
@click.option("--endpoint", help="API endpoint URL")
@click.option("--non-interactive", is_flag=True, help="Non-interactive mode")
@click.pass_obj
def init(
    ctx: Context,
    profile: str,
    endpoint: Optional[str],
    non_interactive: bool,
) -> None:
    """Initialize Hopper configuration.

    This creates the configuration directory and sets up the initial
    configuration file.

    Examples:
        hopper init
        hopper init --endpoint http://localhost:8000
        hopper init --profile production --endpoint https://api.hopper.io
    """
    config_dir = get_config_dir()
    config_path = config_dir / "config.yaml"

    console.print(f"\n[bold cyan]Initializing Hopper CLI[/bold cyan]\n")

    # Interactive prompts
    if not non_interactive:
        if not endpoint:
            endpoint = Prompt.ask(
                "[bold]API endpoint URL[/bold]",
                default="http://localhost:8000"
            )

        # Ask about authentication
        if Confirm.ask("Configure authentication now?", default=True):
            auth_method = Prompt.ask(
                "[bold]Authentication method[/bold]",
                choices=["token", "api_key", "none"],
                default="none"
            )

            if auth_method == "token":
                token = Prompt.ask("[bold]JWT token[/bold]", password=True)
            elif auth_method == "api_key":
                api_key = Prompt.ask("[bold]API key[/bold]", password=True)
            else:
                token = None
                api_key = None
        else:
            token = None
            api_key = None
    else:
        token = None
        api_key = None

    # Create configuration
    config = Config(
        active_profile=profile,
        profiles={
            profile: ProfileConfig(
                api=APIConfig(endpoint=endpoint or "http://localhost:8000"),
                auth=AuthConfig(token=token, api_key=api_key)
            )
        },
        config_path=config_path
    )

    # Save configuration
    config.save()

    print_success(f"Configuration created at {config_path}")
    console.print(f"[bold]Profile:[/bold] {profile}")
    console.print(f"[bold]Endpoint:[/bold] {endpoint or 'http://localhost:8000'}")

    # Test connection
    if not non_interactive:
        if Confirm.ask("\nTest connection?", default=True):
            try:
                with HopperClient(config) as client:
                    # Try a simple API call
                    client.get("/api/v1/health")
                print_success("Connection successful!")
            except Exception as e:
                print_warning(f"Connection test failed: {e}")
                print_info("You can configure authentication later with 'hopper auth login'")

    console.print(f"\n[dim]You can now use Hopper CLI commands.[/dim]")
    console.print(f"[dim]Try: hopper task list[/dim]\n")


@click.group(name="config")
def config_group() -> None:
    """Manage Hopper configuration.

    Configuration is stored in ~/.hopper/config.yaml and supports
    multiple profiles for different environments.
    """
    pass


@config_group.command(name="get")
@click.argument("key")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def get_config(ctx: Context, key: str, profile: Optional[str]) -> None:
    """Get a configuration value.

    Examples:
        hopper config get api.endpoint
        hopper config get auth.token
        hopper config get active_profile
    """
    profile_name = profile or ctx.config.active_profile
    prof = ctx.config.profiles.get(profile_name)

    if not prof and profile:
        print_error(f"Profile '{profile}' not found")
        raise click.Abort()

    # Parse key path
    parts = key.split(".")

    if key == "active_profile":
        value = ctx.config.active_profile
    elif parts[0] == "api":
        if len(parts) < 2:
            print_error("Invalid key. Use 'api.endpoint' or 'api.timeout'")
            raise click.Abort()
        value = getattr(prof.api, parts[1], None)
    elif parts[0] == "auth":
        if len(parts) < 2:
            print_error("Invalid key. Use 'auth.token' or 'auth.api_key'")
            raise click.Abort()
        value = getattr(prof.auth, parts[1], None)
    else:
        print_error(f"Unknown key: {key}")
        raise click.Abort()

    if ctx.json_output:
        print_json({key: value})
    else:
        # Mask sensitive values
        if "token" in key or "key" in key:
            if value:
                value = f"{value[:8]}..." if len(value) > 8 else "***"
        console.print(f"[bold]{key}:[/bold] {value or '(not set)'}")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def set_config(ctx: Context, key: str, value: str, profile: Optional[str]) -> None:
    """Set a configuration value.

    Examples:
        hopper config set api.endpoint http://localhost:8000
        hopper config set api.timeout 60
        hopper config set active_profile production
    """
    profile_name = profile or ctx.config.active_profile

    if profile_name not in ctx.config.profiles:
        # Create new profile
        ctx.config.profiles[profile_name] = ProfileConfig()

    prof = ctx.config.profiles[profile_name]

    # Parse key path
    parts = key.split(".")

    if key == "active_profile":
        if value not in ctx.config.profiles:
            print_error(f"Profile '{value}' does not exist")
            raise click.Abort()
        ctx.config.active_profile = value
    elif parts[0] == "api":
        if len(parts) < 2:
            print_error("Invalid key. Use 'api.endpoint' or 'api.timeout'")
            raise click.Abort()
        if parts[1] == "endpoint":
            prof.api.endpoint = value
        elif parts[1] == "timeout":
            prof.api.timeout = int(value)
        else:
            print_error(f"Unknown api key: {parts[1]}")
            raise click.Abort()
    elif parts[0] == "auth":
        if len(parts) < 2:
            print_error("Invalid key. Use 'auth.token' or 'auth.api_key'")
            raise click.Abort()
        if parts[1] == "token":
            prof.auth.token = value
        elif parts[1] == "api_key":
            prof.auth.api_key = value
        else:
            print_error(f"Unknown auth key: {parts[1]}")
            raise click.Abort()
    else:
        print_error(f"Unknown key: {key}")
        raise click.Abort()

    # Save configuration
    ctx.config.save()
    print_success(f"Set {key} = {value}")


@config_group.command(name="list")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def list_config(ctx: Context, profile: Optional[str]) -> None:
    """List all configuration values.

    Examples:
        hopper config list
        hopper config list --profile production
    """
    if ctx.json_output:
        data = {
            "active_profile": ctx.config.active_profile,
            "profiles": {
                name: {
                    "api": {
                        "endpoint": p.api.endpoint,
                        "timeout": p.api.timeout,
                    },
                    "auth": {
                        "token": bool(p.auth.token),
                        "api_key": bool(p.auth.api_key),
                    }
                }
                for name, p in ctx.config.profiles.items()
            }
        }
        print_json(data)
        return

    console.print(f"\n[bold cyan]Hopper Configuration[/bold cyan]\n")
    console.print(f"[bold]Active Profile:[/bold] {ctx.config.active_profile}")
    console.print(f"[bold]Config File:[/bold] {ctx.config.config_path}\n")

    profile_name = profile or ctx.config.active_profile
    prof = ctx.config.profiles.get(profile_name)

    if not prof:
        print_error(f"Profile '{profile_name}' not found")
        return

    console.print(f"[bold]Profile: {profile_name}[/bold]\n")

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("api.endpoint", prof.api.endpoint)
    table.add_row("api.timeout", str(prof.api.timeout))

    # Show masked auth info
    if prof.auth.token:
        token_preview = f"{prof.auth.token[:8]}..." if len(prof.auth.token) > 8 else "***"
        table.add_row("auth.token", token_preview)
    else:
        table.add_row("auth.token", "[dim](not set)[/dim]")

    if prof.auth.api_key:
        key_preview = f"{prof.auth.api_key[:8]}..." if len(prof.auth.api_key) > 8 else "***"
        table.add_row("auth.api_key", key_preview)
    else:
        table.add_row("auth.api_key", "[dim](not set)[/dim]")

    console.print(table)
    console.print()


@click.group(name="auth")
def auth() -> None:
    """Manage authentication credentials."""
    pass


@auth.command(name="login")
@click.option("--token", help="JWT token")
@click.option("--api-key", help="API key")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def login(
    ctx: Context,
    token: Optional[str],
    api_key: Optional[str],
    profile: Optional[str],
) -> None:
    """Authenticate with Hopper API.

    Examples:
        hopper auth login --token YOUR_TOKEN
        hopper auth login --api-key YOUR_KEY
        hopper auth login  # Interactive mode
    """
    profile_name = profile or ctx.config.active_profile

    if profile_name not in ctx.config.profiles:
        ctx.config.profiles[profile_name] = ProfileConfig()

    prof = ctx.config.profiles[profile_name]

    # Interactive mode
    if not token and not api_key:
        auth_method = Prompt.ask(
            "[bold]Authentication method[/bold]",
            choices=["token", "api_key"],
            default="token"
        )

        if auth_method == "token":
            token = Prompt.ask("[bold]JWT token[/bold]", password=True)
        else:
            api_key = Prompt.ask("[bold]API key[/bold]", password=True)

    # Update auth config
    if token:
        prof.auth.token = token
        prof.auth.api_key = None  # Clear other method
    elif api_key:
        prof.auth.api_key = api_key
        prof.auth.token = None  # Clear other method
    else:
        print_error("No credentials provided")
        raise click.Abort()

    # Save configuration
    ctx.config.save()
    print_success("Authentication configured")

    # Test connection
    if Confirm.ask("Test connection?", default=True):
        try:
            with HopperClient(ctx.config) as client:
                client.get("/api/v1/health")
            print_success("Authentication successful!")
        except APIError as e:
            print_error(f"Authentication failed: {e.message}")
            raise click.Abort()


@auth.command(name="logout")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def logout(ctx: Context, profile: Optional[str]) -> None:
    """Clear authentication credentials.

    Examples:
        hopper auth logout
        hopper auth logout --profile production
    """
    profile_name = profile or ctx.config.active_profile

    if profile_name not in ctx.config.profiles:
        print_error(f"Profile '{profile_name}' not found")
        raise click.Abort()

    prof = ctx.config.profiles[profile_name]
    prof.auth.token = None
    prof.auth.api_key = None

    ctx.config.save()
    print_success("Credentials cleared")


@auth.command(name="status")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def auth_status(ctx: Context, profile: Optional[str]) -> None:
    """Check authentication status.

    Examples:
        hopper auth status
    """
    profile_name = profile or ctx.config.active_profile
    prof = ctx.config.profiles.get(profile_name)

    if not prof:
        print_error(f"Profile '{profile_name}' not found")
        raise click.Abort()

    console.print(f"\n[bold cyan]Authentication Status[/bold cyan]\n")
    console.print(f"[bold]Profile:[/bold] {profile_name}")
    console.print(f"[bold]Endpoint:[/bold] {prof.api.endpoint}\n")

    if prof.auth.token:
        console.print("[bold green]✓[/bold green] Authenticated with JWT token")
    elif prof.auth.api_key:
        console.print("[bold green]✓[/bold green] Authenticated with API key")
    else:
        console.print("[bold yellow]![/bold yellow] Not authenticated")
        console.print("[dim]Use 'hopper auth login' to authenticate[/dim]")

    console.print()

    # Test connection
    if prof.auth.token or prof.auth.api_key:
        try:
            with HopperClient(ctx.config) as client:
                client.get("/api/v1/health")
            print_success("Connection OK")
        except APIError as e:
            print_error(f"Connection failed: {e.message}")
