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
@click.option("--server", "-s", help="Upstream server URL (e.g. https://hopper.example.com)")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing key")
@click.pass_obj
def init_upstream(ctx: Context, key_path: str | None, server: str | None, force: bool) -> None:
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
    if server:
        profile.upstream.server = server.rstrip("/")
    config.save()

    if ctx.json_output:
        print_json({
            "did": did_key.did,
            "key_path": str(path),
            "server": profile.upstream.server,
        })
    else:
        print_success(f"Generated DID key: {did_key.did}")
        print_info(f"Key saved to: {path}")
        if profile.upstream.server:
            print_info(f"Upstream server: {profile.upstream.server}")
        else:
            print_info("Set a server with: hopper upstream set-server <url>")


@upstream.command(name="set-server")
@click.argument("url")
@click.pass_obj
def set_server(ctx: Context, url: str) -> None:
    """Set the upstream server URL in config.

    Example: hopper upstream set-server https://hopper.example.com
    """
    config = ctx.config
    profile = config.current_profile
    profile.upstream.server = url.rstrip("/")
    config.save()

    if ctx.json_output:
        print_json({"server": profile.upstream.server})
    else:
        print_success(f"Upstream server set to: {profile.upstream.server}")


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
            instance=local_client.config.instance_id,
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
@click.option("--port", "-p", default=8080, help="Port to listen on")
@click.option(
    "--storage",
    "-s",
    type=click.Path(),
    default="./upstream-data",
    help="Storage directory for server data",
)
def run_server(host: str, port: int, storage: str) -> None:
    """Start the upstream sync server (standalone).

    Note: The upstream server is now built into 'hopper server start' at /upstream.
    Use this only if you need a standalone sync server without the full API.
    """
    try:
        from hopper.upstream.server import run_server as start_server
    except ModuleNotFoundError as e:
        print_error(
            f"Missing server dependency: {e.name}. "
            "Install server extras with: pip install 'hopper-memory[server]'"
        )
        raise click.Abort()

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


@upstream.command(name="reset")
@click.option("--instance", "-i", help="Instance to reset (defaults to current)")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def reset_upstream(ctx: Context, instance: str | None, force: bool) -> None:
    """Clear sync state, forcing a full re-sync on next run.

    Use this when sync appears stuck (e.g. clock skew left the cursor in
    the future, or state got corrupted). Safe: sync resolves conflicts by
    comparing per-task updated_at timestamps.
    """
    import json

    from hopper.cli.local_client import LocalClient

    storage_path = ctx.get_storage_path()
    if not storage_path:
        print_error("Reset requires local mode.")
        raise click.Abort()

    instance_id = instance or LocalClient(storage_path).config.instance_id
    state_path = storage_path / f".sync_state_{instance_id}"

    if not state_path.exists():
        print_info(f"No sync state to reset for instance '{instance_id}'.")
        return

    old_cursor = None
    try:
        with open(state_path) as f:
            old_cursor = json.load(f)
    except (json.JSONDecodeError, OSError):
        pass

    if not force:
        click.confirm(
            f"Delete sync state for instance '{instance_id}'? "
            f"Next sync will re-push/pull all tasks.",
            abort=True,
        )

    state_path.unlink()

    if ctx.json_output:
        print_json({"instance": instance_id, "previous": old_cursor})
    else:
        print_success(f"Reset sync state for instance '{instance_id}'.")
        if old_cursor:
            print_info(f"Previous cursor: {old_cursor}")
        print_info("Run 'hopper upstream sync' to resync.")


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


def _get_admin_client(ctx: Context, server: str | None = None, admin_key: str | None = None):
    """Get an upstream client for admin operations."""
    from hopper.upstream.client import UpstreamClient
    from hopper.upstream.did import load_did_key

    profile = ctx.config.current_profile

    server_url = server or profile.upstream.server
    if not server_url:
        print_error("No upstream server configured.")
        raise click.Abort()

    if admin_key:
        key_path = Path(admin_key).expanduser()
    else:
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
@click.option("--admin-key", "-k", type=click.Path(), help="Path to admin DID key")
@click.option("--namespace", "-n", default=None, help="Filter to a specific namespace")
@click.pass_obj
def admin_list(ctx: Context, server: str | None, admin_key: str | None, namespace: str | None) -> None:
    """List all registered DIDs."""
    from hopper.upstream.client import UpstreamError

    client, _ = _get_admin_client(ctx, server, admin_key)

    try:
        result = client.list_dids(namespace=namespace)
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
            did = d["did"]
            namespaces = d.get("namespaces", {})
            if namespaces:
                for ns, info in namespaces.items():
                    status = info["status"]
                    marker = f" [{status.upper()}]" if status != "approved" else ""
                    click.echo(f"  {did}  {ns}{marker}")
            else:
                click.echo(f"  {did}  (admin)")


@admin.command(name="pending")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--admin-key", "-k", type=click.Path(), help="Path to admin DID key")
@click.option("--namespace", "-n", default=None, help="Filter to a specific namespace")
@click.pass_obj
def admin_pending(ctx: Context, server: str | None, admin_key: str | None, namespace: str | None) -> None:
    """List DIDs pending approval."""
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server, admin_key)

    try:
        result = client.list_pending(namespace=namespace)
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
            namespaces = d.get("namespaces", {})
            pending_ns = [ns for ns, info in namespaces.items() if info["status"] == "pending"]
            click.echo(f"  {d['did']}")
            click.echo(f"    Requested: {created.isoformat()}")
            if pending_ns:
                click.echo(f"    Namespaces: {', '.join(pending_ns)}")


@admin.command(name="approve")
@click.argument("did")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--admin-key", "-k", type=click.Path(), help="Path to admin DID key")
@click.option("--namespace", "-n", default=None, help="Approve for a specific namespace")
@click.option("--all", "all_namespaces", is_flag=True, help="Approve for all namespaces")
@click.option(
    "--role",
    "-r",
    type=click.Choice(["approved", "approver"]),
    default="approved",
    help="'approved' (default) or 'approver' (can approve/invite others)",
)
@click.pass_obj
def admin_approve(
    ctx: Context,
    did: str,
    server: str | None,
    admin_key: str | None,
    namespace: str | None,
    all_namespaces: bool,
    role: str,
) -> None:
    """Approve a pending DID for a namespace (or all with --all).

    Use --role approver to grant approve/invite authority for that namespace.
    Only admin can grant the approver role.
    """
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server, admin_key)

    ns = "*" if all_namespaces else (namespace or "*")

    try:
        result = client.approve_did(did, namespace=ns, role=role)
    except NotAdminError as e:
        print_error(str(e))
        raise click.Abort()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        scope = "all namespaces" if ns == "*" else f"namespace '{ns}'"
        label = "granted approver on" if role == "approver" else "approved for"
        print_success(f"{did}: {label} {scope}")


@admin.command(name="revoke")
@click.argument("did")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--admin-key", "-k", type=click.Path(), help="Path to admin DID key")
@click.option("--namespace", "-n", default=None, help="Revoke for a specific namespace")
@click.option("--all", "all_namespaces", is_flag=True, help="Revoke for all namespaces")
@click.pass_obj
def admin_revoke(
    ctx: Context,
    did: str,
    server: str | None,
    admin_key: str | None,
    namespace: str | None,
    all_namespaces: bool,
) -> None:
    """Revoke a DID's access to a namespace (or all with --all)."""
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server, admin_key)

    ns = "*" if all_namespaces else (namespace or "*")

    try:
        result = client.revoke_did(did, namespace=ns)
    except NotAdminError as e:
        print_error(str(e))
        raise click.Abort()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        scope = "all namespaces" if ns == "*" else f"namespace '{ns}'"
        print_success(f"Revoked {did} from {scope}")


# --- Invite commands (peer approval) ---


_DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _parse_duration(s: str) -> int:
    """Parse '7d', '24h', '30m', '1w' → seconds. Raise ValueError on bad input."""
    s = s.strip().lower()
    if not s:
        raise ValueError("empty duration")
    unit = s[-1]
    if unit not in _DURATION_UNITS:
        # Treat bare integers as seconds.
        return int(s)
    return int(s[:-1]) * _DURATION_UNITS[unit]


@upstream.group(name="invite")
def invite() -> None:
    """Manage peer-approval invite tokens.

    Invites let admins or approvers grant access to a namespace without
    round-tripping through the server admin for each new DID.
    """


@invite.command(name="create")
@click.option("--namespace", "-n", required=True, help="Instance namespace (e.g. Rosetta_Program)")
@click.option(
    "--role",
    "-r",
    type=click.Choice(["approved", "approver"]),
    default="approved",
    help="Role to grant on redeem (default: approved). 'approver' is admin-only.",
)
@click.option("--expires", "-e", default="7d", help="Expiry window, e.g. 7d, 24h, 30m. Use 'never' to disable.")
@click.option("--uses", "-u", default=1, type=int, help="Max redemptions (default: 1)")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--key", "-k", type=click.Path(), help="Path to issuer DID key")
@click.pass_obj
def invite_create(
    ctx: Context,
    namespace: str,
    role: str,
    expires: str,
    uses: int,
    server: str | None,
    key: str | None,
) -> None:
    """Create an invite token.

    The token is printed ONCE and is not recoverable — pass it to the
    recipient via a secure channel. They redeem with 'hopper upstream redeem'.
    """
    from hopper.upstream.client import NotAdminError, UpstreamError

    if expires.lower() == "never":
        expires_in_ms: int | None = None
    else:
        try:
            expires_in_ms = _parse_duration(expires) * 1000
        except ValueError:
            print_error(f"Invalid --expires value: {expires!r}")
            raise click.Abort()

    client, _ = _get_admin_client(ctx, server, key)

    try:
        result = client.create_invite(
            namespace=namespace, role=role, expires_in_ms=expires_in_ms, max_uses=uses
        )
    except (NotAdminError, UpstreamError) as e:
        print_error(str(e))
        raise click.Abort()

    token = result["token"]
    inv = result["invite"]

    if ctx.json_output:
        print_json(result)
        return

    print_success(f"Invite created for namespace '{namespace}' (role: {role})")
    click.echo("")
    click.echo(f"  Token:     {token}")
    click.echo(f"  Uses:      {inv['uses']}/{inv['max_uses']}")
    exp = inv.get("expires_at")
    if exp:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(exp / 1000, tz=timezone.utc)
        click.echo(f"  Expires:   {dt.isoformat()}")
    else:
        click.echo(f"  Expires:   never")
    click.echo("")
    print_warning("This token is shown only once. Share it over a secure channel.")
    click.echo("")
    click.echo(f"Recipient runs:  hopper upstream redeem {token}")


@invite.command(name="list")
@click.option("--namespace", "-n", default=None, help="Filter to a specific namespace")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--key", "-k", type=click.Path(), help="Path to DID key")
@click.pass_obj
def invite_list(
    ctx: Context,
    namespace: str | None,
    server: str | None,
    key: str | None,
) -> None:
    """List invites you can see (admin: all, approver: your namespaces)."""
    from hopper.upstream.client import UpstreamError

    client, _ = _get_admin_client(ctx, server, key)

    try:
        result = client.list_invites(namespace=namespace)
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    invites = result.get("invites", [])

    if ctx.json_output:
        print_json(result)
        return

    if not invites:
        print_info("No invites.")
        return

    from datetime import datetime, timezone
    now_ms = int(__import__("time").time() * 1000)
    for inv in invites:
        exp = inv.get("expires_at")
        status_bits = []
        if inv["uses"] >= inv["max_uses"]:
            status_bits.append("exhausted")
        if exp and now_ms >= exp:
            status_bits.append("expired")
        status = ", ".join(status_bits) if status_bits else "active"

        click.echo(f"  {inv['token_hash'][:12]}…  ns={inv['namespace']}  role={inv['role']}  uses={inv['uses']}/{inv['max_uses']}  [{status}]")
        if exp:
            dt = datetime.fromtimestamp(exp / 1000, tz=timezone.utc)
            click.echo(f"    expires: {dt.isoformat()}")
        click.echo(f"    issued_by: {inv['issued_by']}")


@invite.command(name="revoke")
@click.argument("token_hash_prefix")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--key", "-k", type=click.Path(), help="Path to DID key")
@click.pass_obj
def invite_revoke_cmd(
    ctx: Context,
    token_hash_prefix: str,
    server: str | None,
    key: str | None,
) -> None:
    """Revoke an invite by token hash (or unique prefix from 'invite list')."""
    from hopper.upstream.client import NotAdminError, UpstreamError

    client, _ = _get_admin_client(ctx, server, key)

    try:
        result = client.revoke_invite(token_hash_prefix)
    except (NotAdminError, UpstreamError) as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        print_success(f"Revoked invite {token_hash_prefix}")


@upstream.command(name="redeem")
@click.argument("token")
@click.option("--server", "-s", help="Upstream server URL")
@click.option("--key", "-k", type=click.Path(), help="Path to DID key (default: ~/.hopper/did.key)")
@click.pass_obj
def redeem_cmd(ctx: Context, token: str, server: str | None, key: str | None) -> None:
    """Redeem an invite token for this machine's DID.

    Run this on the new machine after 'hopper upstream init'. Afterwards,
    'hopper sync' will succeed for the invited namespace.
    """
    from hopper.upstream.client import NotAuthorizedError, UpstreamError

    client, _ = _get_admin_client(ctx, server, key)

    try:
        result = client.redeem_invite(token)
    except NotAuthorizedError as e:
        print_error(str(e))
        raise click.Abort()
    except UpstreamError as e:
        print_error(str(e))
        raise click.Abort()

    if ctx.json_output:
        print_json(result)
    else:
        print_success(result.get("message", "redeemed"))
        print_info("Run 'hopper sync' to pull tasks.")
