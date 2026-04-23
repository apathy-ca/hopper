"""Knowledge management commands."""

from pathlib import Path

import click

from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_json,
    print_success,
    print_warning,
)
from hopper.cli.config import detect_embedded_hopper


@click.group(name="knowledge")
def knowledge() -> None:
    """Manage agent knowledge.

    Sync and manage knowledge from agent-knowledge repositories.
    Knowledge is stored in .hopper/knowledge/ and includes both
    built-in hopper-usage.md and synced agent-knowledge.
    """
    pass


@knowledge.command(name="sync")
@click.option("--source", "-s", help="Path to agent-knowledge repo")
@click.option("--full", is_flag=True, help="Sync full repo instead of auto-detecting")
@click.option("--patterns", "-p", multiple=True, help="Specific patterns to sync")
@click.pass_obj
def sync(ctx: Context, source: str | None, full: bool, patterns: tuple[str, ...]) -> None:
    """Sync agent-knowledge to local storage.

    By default, auto-detects project type and syncs only relevant sections.
    Use --full to sync the entire agent-knowledge repository.

    Examples:
        hopper knowledge sync                    # Auto-detect and sync
        hopper knowledge sync --full             # Sync everything
        hopper knowledge sync -p core-rules/testing
        hopper knowledge sync -s /path/to/knowledge
    """
    from hopper.storage.knowledge import (
        sync_agent_knowledge,
        detect_project_type,
        DEFAULT_KNOWLEDGE_SOURCE,
    )

    # Find storage path
    embedded = detect_embedded_hopper()
    if embedded:
        knowledge_path = embedded / "knowledge"
    else:
        knowledge_path = Path.home() / ".hopper" / "knowledge"

    if not knowledge_path.parent.exists():
        print_error("Hopper not initialized. Run 'hopper init' first.")
        raise click.Abort()

    # Determine source
    src = source or ctx.config.current_profile.knowledge.source or DEFAULT_KNOWLEDGE_SOURCE
    console.print(f"[bold]Source:[/bold] {src}")
    console.print(f"[bold]Destination:[/bold] {knowledge_path}")

    # Determine patterns
    if patterns:
        pattern_list = list(patterns)
    elif full:
        pattern_list = None  # Full sync
    else:
        pattern_list = detect_project_type(Path.cwd())
        if pattern_list:
            console.print(f"[bold]Detected patterns:[/bold] {', '.join(pattern_list)}")
        else:
            console.print("[dim]No project type detected, syncing full repo[/dim]")
            pattern_list = None

    # Sync
    result = sync_agent_knowledge(knowledge_path, src, pattern_list)

    if ctx.json_output:
        print_json(result)
        return

    # Report results
    if result.get("synced"):
        synced = result["synced"]
        if synced == ["(full repo)"]:
            print_success("Synced full agent-knowledge repo")
        else:
            print_success(f"Synced {len(synced)} sections:")
            for s in synced:
                console.print(f"  [green]+[/green] {s}")

    if result.get("skipped"):
        for s in result["skipped"]:
            console.print(f"  [dim]- {s}[/dim]")

    if result.get("errors"):
        for err in result["errors"]:
            print_warning(f"Error: {err}")


@knowledge.command(name="list")
@click.pass_obj
def list_knowledge(ctx: Context) -> None:
    """List available knowledge files.

    Shows all knowledge files in .hopper/knowledge/.
    """
    # Find storage path
    embedded = detect_embedded_hopper()
    if embedded:
        knowledge_path = embedded / "knowledge"
    else:
        knowledge_path = Path.home() / ".hopper" / "knowledge"

    if not knowledge_path.exists():
        print_info("No knowledge directory found. Run 'hopper init' or 'hopper knowledge sync'.")
        return

    # List files
    console.print(f"\n[bold cyan]Knowledge files in {knowledge_path}[/bold cyan]\n")

    # Built-in
    hopper_usage = knowledge_path / "hopper-usage.md"
    if hopper_usage.exists():
        console.print("  [green]hopper-usage.md[/green] [dim](built-in)[/dim]")

    # Agent knowledge
    agent_knowledge = knowledge_path / "agent-knowledge"
    if agent_knowledge.exists():
        console.print(f"\n  [bold]agent-knowledge/[/bold]")
        for item in sorted(agent_knowledge.iterdir()):
            if item.is_dir():
                file_count = len(list(item.rglob("*.md")))
                console.print(f"    {item.name}/ [dim]({file_count} files)[/dim]")
            else:
                console.print(f"    {item.name}")

    console.print()


@knowledge.command(name="show")
@click.argument("path", required=False)
@click.pass_obj
def show(ctx: Context, path: str | None) -> None:
    """Show knowledge file content.

    Without arguments, shows hopper-usage.md.

    Examples:
        hopper knowledge show
        hopper knowledge show core-rules/testing/README.md
    """
    # Find storage path
    embedded = detect_embedded_hopper()
    if embedded:
        knowledge_path = embedded / "knowledge"
    else:
        knowledge_path = Path.home() / ".hopper" / "knowledge"

    if not knowledge_path.exists():
        print_error("No knowledge directory found. Run 'hopper init' first.")
        raise click.Abort()

    # Determine file to show
    if path:
        file_path = knowledge_path / "agent-knowledge" / path
        if not file_path.exists():
            file_path = knowledge_path / path
    else:
        file_path = knowledge_path / "hopper-usage.md"

    if not file_path.exists():
        print_error(f"File not found: {path or 'hopper-usage.md'}")
        raise click.Abort()

    # Show content
    content = file_path.read_text()
    console.print(content)


@knowledge.command(name="refresh")
@click.pass_obj
def refresh(ctx: Context) -> None:
    """Refresh hopper-usage.md to latest built-in version.

    Useful if the built-in documentation has been updated.
    """
    from hopper.storage.knowledge import write_hopper_usage

    # Find storage path
    embedded = detect_embedded_hopper()
    if embedded:
        knowledge_path = embedded / "knowledge"
    else:
        knowledge_path = Path.home() / ".hopper" / "knowledge"

    if not knowledge_path.parent.exists():
        print_error("Hopper not initialized. Run 'hopper init' first.")
        raise click.Abort()

    usage_file = write_hopper_usage(knowledge_path)
    print_success(f"Refreshed {usage_file}")


@knowledge.command(name="update-agent-files")
@click.option("--force", "-f", is_flag=True, help="Replace existing Hopper section with latest version.")
@click.pass_obj
def update_agent_files(ctx: Context, force: bool) -> None:
    """Update AGENTS.md and CLAUDE.md with the latest Hopper section.

    Run this inside a project that has a .hopper/ directory to bring its
    agent files up to date after a Hopper upgrade. Without --force, skips
    files that already have a Hopper section. With --force, replaces the
    existing section with the current version.

    Examples:
        hopper knowledge update-agent-files           # Append if missing
        hopper knowledge update-agent-files --force   # Update in place
    """
    from hopper.storage.knowledge import write_agent_files

    embedded = detect_embedded_hopper()
    target = embedded.parent if embedded else Path.cwd()

    if not target.exists():
        print_error(f"Path not found: {target}")
        raise click.Abort()

    result = write_agent_files(target, force=force)

    if ctx.json_output:
        print_json(result)
        return

    for filename, info in result.items():
        action = info.get("action", "unknown")
        if action in ("created", "appended"):
            label = f"[green]{action}[/green]"
            detail = f" [dim]→ v{info.get('to_version')}[/dim]"
        elif action == "updated":
            fv = info.get("from_version")
            tv = info.get("to_version")
            label = "[green]updated[/green]"
            detail = f" [dim]v{fv} → v{tv}[/dim]" if fv else f" [dim]→ v{tv}[/dim]"
        else:
            label = "[dim]skipped[/dim]"
            detail = f" [dim]— {info.get('reason', '')}[/dim]"
        console.print(f"  {label}  {filename}{detail}")

    changed = sum(1 for info in result.values() if info.get("action") != "skipped")
    if changed:
        print_success(f"Updated {changed} file(s) in {target}")
    else:
        print_info(f"Already up to date (v{info.get('version', '?')})")
