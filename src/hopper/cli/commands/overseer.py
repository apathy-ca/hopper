"""Overseer commands — federation management across sub-instances."""

import click
from rich.table import Table

from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_json,
    print_success,
    print_warning,
)


@click.group(name="overseer")
def overseer() -> None:
    """Manage overseer federation — sub-instances, DAG, northbound consolidation."""
    pass


@overseer.command(name="register")
@click.option("--dry-run", is_flag=True, help="Show edges without creating them.")
@click.pass_obj
def register(ctx: Context, dry_run: bool) -> None:
    """Register sub-instance relationships from config.yaml to the server.

    Reads the sub_instances list from the local config.yaml and pushes
    each edge to the server's instance_relationships table with cycle
    detection.

    Examples:
        hopper overseer register
        hopper overseer register --dry-run
    """
    from hopper.cli.config import get_storage_path
    from hopper.instances.config import read_sub_instances

    storage_path = get_storage_path(ctx.config, False)
    subs = read_sub_instances(storage_path)

    if not subs:
        print_warning("No sub_instances declared in config.yaml")
        return

    # Read this instance's ID from config
    import yaml

    config_file = storage_path / "config.yaml"
    data = yaml.safe_load(config_file.read_text()) or {}
    parent_id = data.get("instance", {}).get("id")
    if not parent_id:
        print_error("No instance.id found in config.yaml")
        raise click.Abort()

    if dry_run:
        print_info(f"Would register {len(subs)} edges from {parent_id}:")
        for sub in subs:
            console.print(f"  {parent_id} → {sub['id']}")
        return

    from hopper.cli.client import HopperClient

    try:
        with HopperClient(ctx.config) as client:
            created = 0
            skipped = 0
            for sub in subs:
                child_id = sub["id"]
                try:
                    result = client.post(
                        f"/api/v1/instances/{parent_id}/children/{child_id}"
                    )
                    if result.get("status") == "created":
                        print_success(f"  {parent_id} → {child_id}")
                        created += 1
                    elif result.get("status") == "already_exists":
                        print_info(f"  {parent_id} → {child_id} (already registered)")
                        skipped += 1
                except Exception as exc:
                    print_error(f"  {parent_id} → {child_id}: {exc}")

            console.print(f"\n[bold]{created} created, {skipped} already existed[/bold]")
    except Exception as exc:
        print_error(f"Failed to connect to server: {exc}")
        raise click.Abort() from exc


@overseer.command(name="status")
@click.pass_obj
def status(ctx: Context) -> None:
    """Show overseer DAG and sub-instance status.

    Displays the instance hierarchy with task/memory counts and
    last consolidation timestamps.
    """
    from hopper.cli.config import get_storage_path
    from hopper.instances.config import read_sub_instances

    storage_path = get_storage_path(ctx.config, False)
    subs = read_sub_instances(storage_path)

    if not subs:
        print_warning("No sub_instances declared in config.yaml")
        return

    import yaml

    config_file = storage_path / "config.yaml"
    data = yaml.safe_load(config_file.read_text()) or {}
    parent_id = data.get("instance", {}).get("id", "unknown")

    table = Table(title=f"Overseer: {parent_id}")
    table.add_column("Sub-instance", style="bold")
    table.add_column("Scope")
    table.add_column("Description")

    for sub in subs:
        table.add_row(
            sub["id"],
            sub.get("scope", "—"),
            sub.get("description", "—"),
        )

    console.print(table)

    if ctx.json_output:
        print_json({"parent": parent_id, "sub_instances": subs})


@overseer.command(name="consolidate")
@click.option("--overseer-id", "only", help="Scope to this overseer and its subtree.")
@click.option("--dry-run", is_flag=True, help="Show what would happen without writing.")
@click.option("--model", help="Anthropic model override.")
@click.pass_obj
def consolidate(ctx: Context, only: str | None, dry_run: bool, model: str | None) -> None:
    """Run bottom-up consolidation across the instance DAG.

    Consolidates leaf instances first, then overseers, with a northbound
    pass generating cross-cutting summaries. Each instance consolidates
    exactly once.

    Examples:
        hopper overseer consolidate
        hopper overseer consolidate --overseer-id Overseer --dry-run
    """
    from hopper.cli.config import get_storage_path

    storage_path = get_storage_path(ctx.config, False)
    shadow_db = storage_path / "shadow.db"

    if not shadow_db.exists():
        print_error("shadow.db not found — consolidation requires the SQLite backend")
        raise click.Abort()

    from hopper.audit_agent.agent import _get_or_create_agent_did, run_bottom_up

    agent_did = _get_or_create_agent_did(storage_path)

    print_info(f"Running bottom-up consolidation{f' (scoped to {only})' if only else ''}...")

    result = run_bottom_up(
        shadow_db,
        agent_did,
        storage_path,
        run_northbound_pass=True,
        only=only,
        model=model,
        dry_run=dry_run,
    )

    if ctx.json_output:
        print_json(result)
    elif result.get("skipped"):
        print_warning(f"Skipped: {result.get('reason', 'unknown')}")
    else:
        instances = result.get("instances", {})
        for iid, detail in instances.items():
            parts = []
            if c := detail.get("consolidation"):
                if not c.get("skipped"):
                    if dry_run:
                        parts.append(f"would consolidate {c.get('eligible', 0)} records")
                    else:
                        parts.append(f"consolidated {c.get('eligible', 0)} records")
            if n := detail.get("northbound"):
                if not n.get("skipped"):
                    if dry_run:
                        parts.append(f"northbound: would create {len(n.get('summaries', []))} summaries")
                    else:
                        parts.append(f"northbound: {n.get('northbound_records_created', 0)} summaries")
            if parts:
                print_success(f"  {iid}: {', '.join(parts)}")
            else:
                print_info(f"  {iid}: skipped")


@overseer.command(name="northbound")
@click.option("--overseer-id", "overseer_id", required=True, help="Overseer instance ID.")
@click.option("--dry-run", is_flag=True, help="Show summaries without writing.")
@click.option("--model", help="Anthropic model override.")
@click.pass_obj
def northbound(ctx: Context, overseer_id: str, dry_run: bool, model: str | None) -> None:
    """Run only the northbound pass for one overseer.

    Reads sub-instances' consolidated memories and generates cross-cutting
    summaries, without re-consolidating the children.

    Examples:
        hopper overseer northbound --overseer-id Overseer
        hopper overseer northbound --overseer-id Overseer --dry-run
    """
    from hopper.cli.config import get_storage_path

    storage_path = get_storage_path(ctx.config, False)
    shadow_db = storage_path / "shadow.db"

    if not shadow_db.exists():
        print_error("shadow.db not found")
        raise click.Abort()

    from hopper.audit_agent.agent import (
        _get_instance_edges,
        _get_or_create_agent_did,
        _ShadowConsolidationClient,
    )
    from hopper.instances.dag import build_adjacency
    from hopper.memory.consolidation import run_northbound as _run_northbound

    edges = _get_instance_edges(storage_path)
    children_of, _ = build_adjacency(edges)
    child_ids = list(children_of.get(overseer_id, set()))

    if not child_ids:
        print_warning(f"No registered children for {overseer_id}")
        return

    agent_did = _get_or_create_agent_did(storage_path)
    print_info(f"Northbound pass for {overseer_id} (children: {', '.join(child_ids)})")

    with _ShadowConsolidationClient(
        shadow_db,
        agent_did,
        overseer_id,
        read_instance_ids=set(child_ids),
        write_instance_id=overseer_id,
    ) as nb_client:
        result = _run_northbound(
            nb_client,
            parent_instance_id=overseer_id,
            child_instance_ids=child_ids,
            model=model,
            dry_run=dry_run,
        )

    if ctx.json_output:
        print_json(result)
    elif result.get("skipped"):
        print_warning(f"Skipped: {result.get('reason', 'unknown')}")
    elif result.get("error"):
        print_error(result["error"])
    elif dry_run:
        console.print(f"[bold]Would create {len(result.get('summaries', []))} northbound summaries:[/bold]")
        for s in result.get("summaries", []):
            console.print(f"  • {s.get('title', '?')}")
    else:
        print_success(
            f"Created {result.get('northbound_records_created', 0)} northbound summaries "
            f"(run: {result.get('run_id', '?')})"
        )
