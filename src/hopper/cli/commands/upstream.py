"""Upstream sync CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from hopper.cli.main import Context
from hopper.cli.output import print_error, print_info, print_json, print_success, print_warning


@click.group(name="upstream")
def upstream() -> None:
    """Upstream sync commands."""
    pass


@upstream.command(name="init")
@click.option(
    "--key-path",
    "-k",
    type=click.Path(),
    help="Path to save the DID key (default: ~/.hopper/did.key)",
)
@click.option("--force", "-f", is_flag=True, help="Overwrite existing key")
@click.pass_obj
def init_upstream(ctx: Context, key_path: str | None, force: bool) -> None:
    """Generate a DID key pair for upstream authentication."""
    from hopper.upstream.did import generate_did_key

    # Determine key path
    if key_path:
        path = Path(key_path).expanduser()
    else:
        path = Path.home() / ".hopper" / "did.key"

    # Check if key exists
    if path.exists() and not force:
        print_error(f"Key already exists at {path}. Use --force to overwrite.")
        raise click.Abort()

    # Generate key
    did_key = generate_did_key()
    did_key.save(path)

    # Update config
    config = ctx.config
    profile = config.current_profile
    profile.upstream.did_key_path = str(path)
    profile.upstream.enabled = True
    config.save()

    if ctx.json_output:
        print_json({
            "did": did_key.did,
            "key_path": str(path),
        })
    else:
        print_success(f"Generated DID key: {did_key.did}")
        print_info(f"Key saved to: {path}")
        print_info("Configure upstream.server in your config to enable sync.")


@upstream.command(name="sync")
@click.option("--server", "-s", help="Upstream server URL (overrides config)")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed sync info")
@click.pass_obj
def sync_upstream(ctx: Context, server: str | None, verbose: bool) -> None:
    """Sync tasks with upstream server."""
    from hopper.cli.local_client import LocalClient
    from hopper.upstream.client import UpstreamClient, UpstreamError
    from hopper.upstream.did import load_did_key
    from hopper.upstream.sync import sync_with_upstream

    profile = ctx.config.current_profile

    # Get server URL
    server_url = server or profile.upstream.server
    if not server_url:
        print_error("No upstream server configured. Set upstream.server in config.")
        raise click.Abort()

    # Get DID key
    key_path_str = profile.upstream.did_key_path
    if not key_path_str:
        print_error("No DID key configured. Run 'hopper upstream init' first.")
        raise click.Abort()

    key_path = Path(key_path_str).expanduser()
    if not key_path.exists():
        print_error(f"DID key not found at {key_path}. Run 'hopper upstream init'.")
        raise click.Abort()

    try:
        did_key = load_did_key(key_path)
    except Exception as e:
        print_error(f"Failed to load DID key: {e}")
        raise click.Abort()

    # Get storage path
    storage_path = ctx.get_storage_path()
    if not storage_path:
        print_error("Upstream sync requires local mode.")
        raise click.Abort()

    # Create client
    client = UpstreamClient(server_url=server_url, did_key=did_key)

    # Get task store
    local_client = LocalClient(storage_path)
    task_store = local_client.task_store

    # Sync state path
    state_path = storage_path / ".sync_state"

    if verbose:
        print_info(f"Syncing with {server_url}...")
        print_info(f"Using DID: {did_key.did}")

    try:
        result = sync_with_upstream(
            task_store=task_store,
            client=client,
            state_path=state_path,
        )
    except UpstreamError as e:
        print_error(f"Sync failed: {e}")
        raise click.Abort()

    if ctx.json_output:
        print_json({
            "pushed": result.pushed,
            "pulled": result.pulled,
            "conflicts": result.conflicts,
            "errors": result.errors,
        })
    else:
        if result.errors:
            for error in result.errors:
                print_error(error)
            raise click.Abort()

        pushed_count = len(result.pushed)
        pulled_count = len(result.pulled)
        conflict_count = len(result.conflicts)

        if pushed_count == 0 and pulled_count == 0:
            print_info("Already up to date.")
        else:
            if pushed_count > 0:
                print_success(f"Pushed {pushed_count} task(s)")
                if verbose:
                    for task_id in result.pushed:
                        print_info(f"  {task_id}")

            if pulled_count > 0:
                print_success(f"Pulled {pulled_count} task(s)")
                if verbose:
                    for task_id in result.pulled:
                        print_info(f"  {task_id}")

            if conflict_count > 0:
                print_warning(f"{conflict_count} conflict(s) (server wins)")
                if verbose:
                    for task_id in result.conflicts:
                        print_warning(f"  {task_id}")


@upstream.command(name="server")
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=9000, help="Port to listen on")
@click.option(
    "--storage",
    "-s",
    type=click.Path(),
    default="./upstream-data",
    help="Storage directory for server data",
)
def run_server(host: str, port: int, storage: str) -> None:
    """Start the upstream sync server."""
    from hopper.upstream.server import run_server as start_server

    storage_path = Path(storage).expanduser().resolve()
    storage_path.mkdir(parents=True, exist_ok=True)

    # Check if this is first run (no admin key yet)
    admin_key_path = storage_path / "admin.key"
    is_first_run = not admin_key_path.exists()

    if is_first_run:
        print_info("First run - initializing server admin...")

    start_server(storage_path=storage_path, host=host, port=port)

    # Note: start_server blocks, so we won't reach here until shutdown


@upstream.command(name="status")
@click.pass_obj
def status_upstream(ctx: Context) -> None:
    """Show upstream sync status."""
    import json

    profile = ctx.config.current_profile

    # Get config info
    server = profile.upstream.server
    key_path_str = profile.upstream.did_key_path
    enabled = profile.upstream.enabled

    # Get storage path and sync state
    storage_path = ctx.get_storage_path()
    last_sync = None
    did = None

    if key_path_str:
        key_path = Path(key_path_str).expanduser()
        if key_path.exists():
            try:
                from hopper.upstream.did import load_did_key

                did_key = load_did_key(key_path)
                did = did_key.did
            except Exception:
                pass

    if storage_path:
        state_path = storage_path / ".sync_state"
        if state_path.exists():
            try:
                with open(state_path) as f:
                    state = json.load(f)
                    last_sync = state.get("last_sync", 0)
            except Exception:
                pass

    if ctx.json_output:
        print_json({
            "enabled": enabled,
            "server": server,
            "did": did,
            "key_path": key_path_str,
            "last_sync": last_sync,
        })
    else:
        print_info(f"Enabled: {enabled}")
        print_info(f"Server: {server or '(not configured)'}")
        print_info(f"DID: {did or '(no key)'}")
        print_info(f"Key path: {key_path_str or '(not configured)'}")

        if last_sync:
            from datetime import datetime

            dt = datetime.fromtimestamp(last_sync / 1000)
            print_info(f"Last sync: {dt.isoformat()}")
        else:
            print_info("Last sync: never")


@upstream.command(name="whoami")
@click.pass_obj
def whoami(ctx: Context) -> None:
    """Show your DID identity."""
    profile = ctx.config.current_profile

    key_path_str = profile.upstream.did_key_path
    if not key_path_str:
        print_error("No DID key configured. Run 'hopper upstream init' first.")
        raise click.Abort()

    key_path = Path(key_path_str).expanduser()
    if not key_path.exists():
        print_error(f"DID key not found at {key_path}. Run 'hopper upstream init'.")
        raise click.Abort()

    try:
        from hopper.upstream.did import load_did_key

        did_key = load_did_key(key_path)
    except Exception as e:
        print_error(f"Failed to load DID key: {e}")
        raise click.Abort()

    if ctx.json_output:
        print_json({"did": did_key.did, "key_path": str(key_path)})
    else:
        click.echo(did_key.did)


# --- Admin commands ---


def _get_admin_client(ctx: Context, server: str | None = None):
    """Get an upstream client for admin operations."""
    from hopper.upstream.client import UpstreamClient
    from hopper.upstream.did import load_did_key

    profile = ctx.config.current_profile

    server_url = server or profile.upstream.server
    if not server_url:
        print_error("No upstream server configured.")
        raise click.Abort()

    key_path_str = profile.upstream.did_key_path
    if not key_path_str:
        print_error("No DID key configured. Run 'hopper upstream init' first.")
        raise click.Abort()

    key_path = Path(key_path_str).expanduser()
    if not key_path.exists():
        print_error(f"DID key not found at {key_path}.")
        raise click.Abort()

    try:
        did_key = load_did_key(key_path)
    except Exception as e:
        print_error(f"Failed to load DID key: {e}")
        raise click.Abort()

    return UpstreamClient(server_url=server_url, did_key=did_key), did_key


@upstream.group(name="admin")
def admin() -> None:
    """Admin commands for managing DID access."""
    pass


@admin.command(name="list")
@click.option("--server", "-s", help="Upstream server URL")
@click.pass_obj
def admin_list(ctx: Context, server: str | None) -> None:
    """List all registered DIDs."""
    from hopper.upstream.client import UpstreamError

    client, _ = _get_admin_client(ctx, server)

    try:
        result = client.list_dids()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        admin_did = result.get("admin_did")
        dids = result.get("dids", [])

        if not dids:
            print_info("No DIDs registered.")
            return

        print_info(f"Admin: {admin_did}")
        print_info("")

        for d in dids:
            status = d["status"]
            did = d["did"]
            marker = ""
            if status == "admin":
                marker = " (admin)"
            elif status == "pending":
                marker = " [PENDING]"

            click.echo(f"  {did}{marker}")


@admin.command(name="pending")
@click.option("--server", "-s", help="Upstream server URL")
@click.pass_obj
def admin_pending(ctx: Context, server: str | None) -> None:
    """List DIDs pending approval."""
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server)

    try:
        result = client.list_pending()
    except NotAdminError:
        print_error("Only admin can view pending DIDs.")
        raise click.Abort()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        dids = result.get("dids", [])

        if not dids:
            print_info("No pending DIDs.")
            return

        print_info(f"{len(dids)} pending approval:")
        for d in dids:
            from datetime import datetime

            created = datetime.fromtimestamp(d["created_at"] / 1000)
            click.echo(f"  {d['did']}")
            click.echo(f"    Requested: {created.isoformat()}")


@admin.command(name="approve")
@click.argument("did")
@click.option("--server", "-s", help="Upstream server URL")
@click.pass_obj
def admin_approve(ctx: Context, did: str, server: str | None) -> None:
    """Approve a pending DID."""
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server)

    try:
        result = client.approve_did(did)
    except NotAdminError as e:
        print_error(str(e))
        raise click.Abort()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        print_success(f"Approved: {did}")


@admin.command(name="revoke")
@click.argument("did")
@click.option("--server", "-s", help="Upstream server URL")
@click.pass_obj
def admin_revoke(ctx: Context, did: str, server: str | None) -> None:
    """Revoke a DID's access."""
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server)

    try:
        result = client.revoke_did(did)
    except NotAdminError as e:
        print_error(str(e))
        raise click.Abort()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        print_success(f"Revoked: {did}")
