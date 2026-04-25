"""Configuration and authentication commands."""

from pathlib import Path
from typing import Any

import click
from rich import box
from rich.prompt import Confirm, Prompt
from rich.table import Table

from hopper.cli.client import APIError, HopperClient
from hopper.cli.config import APIConfig, AuthConfig, Config, ProfileConfig, get_config_dir
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_json,
    print_success,
    print_warning,
)


# Default agent-knowledge source
DEFAULT_KNOWLEDGE_SOURCE = "https://github.com/apathy-ca/agent-knowledge.git"


@click.command(name="init")
@click.option(
    "--embedded", "-e", is_flag=True, help="Initialize embedded .hopper in current directory"
)
@click.option("--knowledge-source", "-k", help="Path to agent-knowledge repo")
@click.option(
    "--no-knowledge", is_flag=True, help="Skip agent-knowledge sync (only hopper-usage.md)"
)
@click.option(
    "--auto-detect",
    is_flag=True,
    default=True,
    help="Auto-detect project type for relevant knowledge",
)
@click.option("--name", "-n", default=None, help="Instance name (defaults to current directory name)")
@click.option("--profile", default="default", help="Profile name (for server mode)")
@click.option("--endpoint", help="API endpoint URL (for server mode)")
@click.option("--server", "-s", is_flag=True, help="Initialize for server mode instead of local")
@click.option("--non-interactive", is_flag=True, help="Non-interactive mode")
@click.option("--allow-git", is_flag=True, help="Do not add .hopper/ to .gitignore")
@click.pass_obj
def init(
    ctx: Context,
    embedded: bool,
    knowledge_source: str | None,
    no_knowledge: bool,
    auto_detect: bool,
    name: str | None,
    profile: str,
    endpoint: str | None,
    server: bool,
    non_interactive: bool,
    allow_git: bool,
) -> None:
    """Initialize Hopper for a project or globally.

    By default, creates an embedded .hopper directory in the current project
    with hopper-usage.md and relevant agent-knowledge synced from the
    exe.dev standard location.

    Examples:
        hopper init                     # Initialize in current directory (default)
        hopper init --no-knowledge      # Skip agent-knowledge, just hopper-usage.md
        hopper init -k /path/to/knowledge  # Use custom knowledge source
        hopper init --allow-git         # Don't gitignore .hopper/
        hopper init --server            # Initialize server mode config
        hopper init --server --endpoint https://api.hopper.io
    """
    # Server mode initialization (original behavior)
    if server:
        _init_server_mode(ctx, profile, endpoint, non_interactive)
        return

    # Local/embedded mode initialization (new default)
    _init_local_mode(
        ctx,
        embedded=True,  # Always embedded for local init
        knowledge_source=knowledge_source,
        no_knowledge=no_knowledge,
        auto_detect=auto_detect,
        non_interactive=non_interactive,
        instance_name=name,
        allow_git=allow_git,
    )


def _init_local_mode(
    ctx: Context,
    embedded: bool,
    knowledge_source: str | None,
    no_knowledge: bool,
    auto_detect: bool,
    non_interactive: bool,
    instance_name: str | None = None,
    allow_git: bool = False,
) -> None:
    """Initialize local/embedded Hopper storage with knowledge."""
    from hopper.storage import StorageConfig, MarkdownStorage
    from hopper.storage.knowledge import (
        initialize_knowledge,
        write_agent_files,
        write_global_agent_files,
        DEFAULT_KNOWLEDGE_SOURCE,
    )

    # Determine storage path
    if embedded:
        storage_path = Path.cwd() / ".hopper"
    else:
        storage_path = Path.home() / ".hopper"

    console.print("\n[bold cyan]Initializing Hopper[/bold cyan]\n")
    console.print(f"[bold]Location:[/bold] {storage_path}")

    # Check if already initialized
    if storage_path.exists() and (storage_path / "tasks").exists():
        if not non_interactive:
            if not Confirm.ask("Hopper already initialized here. Reinitialize?", default=False):
                print_info("Aborted")
                return
        console.print("[dim]Reinitializing...[/dim]")

    # Initialize storage structure
    config = StorageConfig.local(storage_path, instance_name=instance_name or Path.cwd().name)
    storage = MarkdownStorage(config)
    storage.initialize()

    print_success("Storage initialized")
    console.print(f"  [dim]tasks/[/dim]")
    console.print(f"  [dim]memory/[/dim]")
    console.print(f"  [dim]knowledge/[/dim]")

    # Initialize knowledge
    knowledge_path = storage_path / "knowledge"
    source = knowledge_source or DEFAULT_KNOWLEDGE_SOURCE

    console.print(f"\n[bold]Knowledge source:[/bold] {source}")

    result = initialize_knowledge(
        knowledge_path=knowledge_path,
        source=source,
        auto_detect=auto_detect,
        project_path=Path.cwd(),
        skip_agent_knowledge=no_knowledge,
    )

    # Report results
    if result.get("hopper_usage"):
        print_success("Created hopper-usage.md (built-in)")

    ak_result = result.get("agent_knowledge")
    if ak_result:
        if ak_result.get("synced"):
            synced = ak_result["synced"]
            if synced == ["(full repo)"]:
                print_success("Synced full agent-knowledge repo")
            else:
                print_success(f"Synced {len(synced)} knowledge sections:")
                for s in synced:
                    console.print(f"  [dim]{s}[/dim]")
        if ak_result.get("errors"):
            for err in ak_result["errors"]:
                print_warning(f"Error: {err}")
    elif no_knowledge:
        print_info("Skipped agent-knowledge (--no-knowledge)")

    # Add .hopper/ to .gitignore unless caller explicitly opted out
    if not allow_git:
        gitignore = Path.cwd() / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# Hopper data directory\n.hopper/\n")
            print_info("Created .gitignore with .hopper/")
        else:
            content = gitignore.read_text()
            if ".hopper/" not in content and ".hopper" not in content:
                with open(gitignore, "a") as f:
                    f.write("\n# Hopper data directory\n.hopper/\n")
                print_info("Added .hopper/ to .gitignore")

    # Write AGENTS.md and CLAUDE.md so AI agents discover Hopper automatically
    agent_file_results = write_agent_files(Path.cwd())
    for filename, info in agent_file_results.items():
        action = info["action"]
        if action == "created":
            print_success(f"Created {filename}")
        elif action == "appended":
            print_success(f"Added Hopper section to {filename}")
        # "skipped" means it was already there — no output needed

    # Install global skill + session protocol into ~/.config/opencode/ and ~/.claude/
    global_results = write_global_agent_files()
    global_changes = [r for r in global_results.values() if r.get("action") not in ("skipped",)]
    if global_changes:
        print_success("Installed Hopper skill and session protocol globally")
        for path, info in global_results.items():
            action = info.get("action")
            if action != "skipped":
                console.print(f"  [dim]{action}[/dim]  {path}")

    console.print("\n[bold green]Hopper initialized![/bold green]")
    console.print("[dim]Try: hopper task add 'My first task'[/dim]")
    console.print("[dim]Run: hopper knowledge update-agent-files  # sync AGENTS.md/CLAUDE.md[/dim]\n")


def _init_server_mode(
    ctx: Context,
    profile: str,
    endpoint: str | None,
    non_interactive: bool,
) -> None:
    """Initialize server mode configuration (original behavior)."""
    config_dir = get_config_dir()
    config_path = config_dir / "config.yaml"

    console.print("\n[bold cyan]Initializing Hopper CLI (Server Mode)[/bold cyan]\n")

    # Interactive prompts
    if not non_interactive:
        if not endpoint:
            endpoint = Prompt.ask("[bold]API endpoint URL[/bold]", default="http://localhost:8000")

        # Ask about authentication
        if Confirm.ask("Configure authentication now?", default=True):
            auth_method = Prompt.ask(
                "[bold]Authentication method[/bold]",
                choices=["token", "api_key", "none"],
                default="none",
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
                mode="server",
                api=APIConfig(endpoint=endpoint or "http://localhost:8000"),
                auth=AuthConfig(token=token, api_key=api_key),
            )
        },
        config_path=config_path,
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

    console.print("\n[dim]You can now use Hopper CLI commands.[/dim]")
    console.print("[dim]Try: hopper task list[/dim]\n")


@click.group(name="config")
def config_group() -> None:
    """Manage Hopper configuration.

    Configuration is stored in ~/.hopper/config.yaml and supports
    multiple profiles for different environments.
    """
    pass


def _resolve_profile_attr(prof: "ProfileConfig", key: str) -> tuple[Any, bool]:
    """Resolve a dotted key path against a ProfileConfig.

    Returns (value, found). Traverses nested config objects like
    api.endpoint, upstream.server, etc.
    """
    parts = key.split(".")
    if len(parts) < 2:
        return None, False

    # Map top-level names to config objects
    sections = {
        "api": prof.api,
        "auth": prof.auth,
        "local": prof.local,
        "github": prof.github,
        "knowledge": prof.knowledge,
        "upstream": prof.upstream,
    }

    section = sections.get(parts[0])
    if section is None:
        return None, False

    if not hasattr(section, parts[1]):
        return None, False

    return getattr(section, parts[1]), True


def _set_profile_attr(prof: "ProfileConfig", key: str, value: str) -> bool:
    """Set a dotted key path on a ProfileConfig.

    Handles type coercion for bool, int, and Path fields.
    Returns True if set successfully, False if key not found.
    """
    parts = key.split(".")
    if len(parts) < 2:
        return False

    sections = {
        "api": prof.api,
        "auth": prof.auth,
        "local": prof.local,
        "github": prof.github,
        "knowledge": prof.knowledge,
        "upstream": prof.upstream,
    }

    section = sections.get(parts[0])
    if section is None:
        return False

    attr_name = parts[1]
    if not hasattr(section, attr_name):
        return False

    # Coerce value to the field's type
    current = getattr(section, attr_name)
    if isinstance(current, bool) or (current is None and attr_name in ("enabled", "auto_detect", "auto_detect_embedded")):
        coerced: Any = value.lower() in ("true", "1", "yes")
    elif isinstance(current, int):
        coerced = int(value)
    elif isinstance(current, Path):
        coerced = Path(value)
    else:
        # str or None — treat "null"/"none" as None for nullable fields
        coerced = None if value.lower() in ("null", "none") else value

    setattr(section, attr_name, coerced)
    return True


# Sensitive key names that should be masked in output
_SENSITIVE_KEYS = {"token", "api_key", "did_key_path"}


@config_group.command(name="get")
@click.argument("key")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def get_config(ctx: Context, key: str, profile: str | None) -> None:
    """Get a configuration value.

    Examples:
        hopper config get api.endpoint
        hopper config get auth.token
        hopper config get upstream.server
        hopper config get active_profile
    """
    profile_name = profile or ctx.config.active_profile
    prof = ctx.config.profiles.get(profile_name)

    if not prof and profile:
        print_error(f"Profile '{profile}' not found")
        raise click.Abort()

    if key == "active_profile":
        value = ctx.config.active_profile
    else:
        value, found = _resolve_profile_attr(prof, key)
        if not found:
            print_error(f"Unknown key: {key}")
            raise click.Abort()

    if ctx.json_output:
        print_json({key: value})
    else:
        display = value
        # Mask sensitive values
        if key.split(".")[-1] in _SENSITIVE_KEYS:
            if display:
                display = f"{str(display)[:8]}..." if len(str(display)) > 8 else "***"
        console.print(f"[bold]{key}:[/bold] {display or '(not set)'}")


@config_group.command(name="set")
@click.argument("key")
@click.argument("value")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def set_config(ctx: Context, key: str, value: str, profile: str | None) -> None:
    """Set a configuration value.

    Examples:
        hopper config set api.endpoint http://localhost:8000
        hopper config set api.timeout 60
        hopper config set upstream.server https://hopper.example.com
        hopper config set github.token ghp_xxxx
        hopper config set active_profile production
    """
    profile_name = profile or ctx.config.active_profile

    if profile_name not in ctx.config.profiles:
        # Create new profile
        ctx.config.profiles[profile_name] = ProfileConfig()

    prof = ctx.config.profiles[profile_name]

    if key == "active_profile":
        if value not in ctx.config.profiles:
            print_error(f"Profile '{value}' does not exist")
            raise click.Abort()
        ctx.config.active_profile = value
    else:
        if not _set_profile_attr(prof, key, value):
            print_error(f"Unknown key: {key}")
            raise click.Abort()

    # Save configuration
    ctx.config.save()
    print_success(f"Set {key} = {value}")


@config_group.command(name="list")
@click.option("--profile", help="Profile name (default: active profile)")
@click.pass_obj
def list_config(ctx: Context, profile: str | None) -> None:
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
                    },
                }
                for name, p in ctx.config.profiles.items()
            },
        }
        print_json(data)
        return

    console.print("\n[bold cyan]Hopper Configuration[/bold cyan]\n")
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

    # Iterate all config sections dynamically
    sections = [
        ("api", prof.api),
        ("auth", prof.auth),
        ("local", prof.local),
        ("github", prof.github),
        ("knowledge", prof.knowledge),
        ("upstream", prof.upstream),
    ]

    for section_name, section_obj in sections:
        for field_name in section_obj.model_fields:
            key = f"{section_name}.{field_name}"
            value = getattr(section_obj, field_name)

            # Mask sensitive values
            if field_name in _SENSITIVE_KEYS and value:
                display = f"{str(value)[:8]}..." if len(str(value)) > 8 else "***"
            elif value is None:
                display = "[dim](not set)[/dim]"
            else:
                display = str(value)

            table.add_row(key, display)

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
    token: str | None,
    api_key: str | None,
    profile: str | None,
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
            "[bold]Authentication method[/bold]", choices=["token", "api_key"], default="token"
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
def logout(ctx: Context, profile: str | None) -> None:
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
def auth_status(ctx: Context, profile: str | None) -> None:
    """Check authentication status.

    Examples:
        hopper auth status
    """
    profile_name = profile or ctx.config.active_profile
    prof = ctx.config.profiles.get(profile_name)

    if not prof:
        print_error(f"Profile '{profile_name}' not found")
        raise click.Abort()

    console.print("\n[bold cyan]Authentication Status[/bold cyan]\n")
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
