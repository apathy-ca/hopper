"""Revision management commands (Phase 4d).

Surfaces the propose/apply/reject workflow for human review of agent writes.
"""

from __future__ import annotations

import click

from hopper.cli.client import APIError
from hopper.cli.local_client import LocalClientError
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    print_error,
    print_info,
    print_json,
    print_success,
)

ClientError = (APIError, LocalClientError)

_RULES_TEMPLATE = """\
# Hopper auto-apply rules
# Place this file at ~/.hopper/auto-apply-rules.yaml
#
# Rules are evaluated top-to-bottom; first match wins.
# author_did: exact DID string or "*" for any agent.
# record_type: task | idea | note | memory | log | reference | inbox | "*"
# action: apply (default) or reject.
#
# Example:
# rules:
#   - name: "Trust audit-agent tag normalization on tasks"
#     author_did: "did:key:z6Mk..."
#     record_type: "task"
#     action: apply
#   - name: "Reject any agent proposal on memory records"
#     author_did: "*"
#     record_type: "memory"
#     action: reject
#     reason: "Memory proposals require human review"
rules: []
"""


@click.group(name="revision")
def revision() -> None:
    """Manage record revisions.

    Revisions are the append-only history of every write. The proposal
    workflow (propose/apply/reject) lets agents submit changes for human
    review before they are applied to the live record.
    """
    pass


@revision.command(name="auto-apply")
@click.option("--dry-run", is_flag=True, help="Show what would be applied without doing it")
@click.pass_obj
def auto_apply(ctx: Context, dry_run: bool) -> None:
    """Run auto-apply rules against all pending proposals.

    Rules are read from auto-apply-rules.yaml in the active hopper directory.
    Use ``hopper revision auto-apply --dry-run`` to preview matches.

    Examples:
        hopper revision auto-apply
        hopper revision auto-apply --dry-run
    """
    try:
        with ctx.get_client() as client:
            if not hasattr(client, "list_pending_revisions"):
                print_error("auto-apply requires local mode")
                raise click.Abort()

            from pathlib import Path
            hopper_path = client.storage_path or Path.home() / ".hopper"

            if dry_run:
                from hopper.intelligence.auto_apply import _load_rules, _rule_matches
                from hopper.models import Record
                from hopper.storage.sqlite import SQLiteStorage

                rules = _load_rules(hopper_path)
                if not rules:
                    print_info("No auto-apply rules found — create auto-apply-rules.yaml")
                    return

                pending = client.list_pending_revisions(limit=500)
                console.print(f"\n[bold cyan]Dry run: {len(pending)} pending proposal(s), "
                               f"{len(rules)} rule(s)[/bold cyan]\n")
                for proposal in pending:
                    record_type = "task"
                    if isinstance(client.storage, SQLiteStorage):
                        with client.storage.session() as session:
                            r = session.get(Record, proposal["record_id"])
                            if r:
                                record_type = r.type
                    for rule in rules:
                        if _rule_matches(rule, proposal, record_type):
                            console.print(
                                f"  [yellow]MATCH[/yellow] proposal {proposal['id'][:12]} "
                                f"→ rule {rule.name!r} → {rule.action}"
                            )
                            break
                    else:
                        console.print(f"  [dim]skip[/dim] proposal {proposal['id'][:12]}")
                return

            from hopper.intelligence.auto_apply import run_auto_apply
            result = run_auto_apply(hopper_path, client)

        if ctx.json_output:
            print_json(result)
        else:
            if "error" in result:
                print_error(result["error"])
            elif "message" in result:
                print_info(result["message"])
            else:
                print_success(
                    f"Auto-apply complete: "
                    f"{result['applied']} applied, "
                    f"{result['rejected']} rejected, "
                    f"{result['skipped']} skipped"
                )

    except ClientError as e:
        print_error(f"auto-apply failed: {e.message}")
        raise click.Abort()


@revision.command(name="list")
@click.option("--pending", is_flag=True, help="Show only pending proposals (action=propose)")
@click.option("--record", "record_id", default=None, help="Filter by record ID")
@click.option("--limit", type=int, default=50, help="Max revisions to show")
@click.pass_obj
def list_revisions(ctx: Context, pending: bool, record_id: str | None, limit: int) -> None:
    """List revisions (or pending proposals).

    Examples:
        hopper revision list --pending
        hopper revision list --record abc12345
    """
    try:
        with ctx.get_client() as client:
            if not hasattr(client, "list_pending_revisions"):
                print_error("Revision management requires local mode")
                raise click.Abort()
            if pending:
                revisions = client.list_pending_revisions(record_id=record_id, limit=limit)
            else:
                # General history — if record_id given use task history, else pending only
                if record_id:
                    revisions = client.get_task_history(record_id, limit=limit)
                else:
                    revisions = client.list_pending_revisions(limit=limit)

        if ctx.json_output:
            print_json(revisions)
            return

        if not revisions:
            print_info("No revisions found")
            return

        from rich import box
        from rich.table import Table
        from hopper.cli.output import format_datetime

        _ACTION_STYLE = {
            "create": "green",
            "update": "cyan",
            "tombstone": "red",
            "propose": "yellow",
            "apply": "green",
            "reject": "red",
        }

        label = "Pending proposals" if pending else "Revisions"
        console.print(f"\n[bold cyan]{label}[/bold cyan]\n")

        table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
        table.add_column("Rev ID", style="dim", min_width=12)
        table.add_column("Record", min_width=10)
        table.add_column("Action", min_width=8)
        table.add_column("Location", min_width=14)
        table.add_column("Author DID", min_width=20)
        table.add_column("When", style="dim", min_width=12)

        for rev in revisions:
            action = rev.get("action", "?")
            style = _ACTION_STYLE.get(action, "white")
            did = rev.get("author_did") or "—"
            if did and len(did) > 28:
                did = did[:12] + "…" + did[-8:]
            table.add_row(
                (rev.get("id") or "")[:12],
                (rev.get("record_id") or "")[:10],
                f"[{style}]{action}[/]",
                rev.get("author_location") or "—",
                did,
                format_datetime(rev.get("created_at")),
            )

        console.print(table)
        console.print(f"\n[dim]{len(revisions)} revision(s)[/dim]\n")

    except ClientError as e:
        print_error(f"Failed to list revisions: {e.message}")
        raise click.Abort()


@revision.command(name="apply")
@click.argument("revision_id")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def apply_revision(ctx: Context, revision_id: str, author_did: str | None, force: bool) -> None:
    """Apply a pending proposal revision to the live record.

    This makes the proposed change active by inserting an 'apply' revision
    and advancing the record's current_revision pointer.

    Examples:
        hopper revision apply 01KQABCDEF1234567890123456
        hopper revision apply 01KQ... --force
    """
    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Apply revision [bold]{revision_id[:12]}[/bold]?", default=True):
            print_info("Cancelled")
            return

    try:
        with ctx.get_client() as client:
            if not hasattr(client, "apply_revision"):
                print_error("Revision management requires local mode")
                raise click.Abort()
            result = client.apply_revision(revision_id, author_did=author_did)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Applied: proposal {revision_id[:12]} → apply revision {result.get('applied_revision_id', '')[:12]}")

    except ClientError as e:
        print_error(f"Failed to apply revision: {e.message}")
        raise click.Abort()
    except ValueError as e:
        print_error(str(e))
        raise click.Abort()


@revision.command(name="reject")
@click.argument("revision_id")
@click.option("--reason", "-r", help="Optional rejection reason")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def reject_revision(ctx: Context, revision_id: str, reason: str | None,
                    author_did: str | None, force: bool) -> None:
    """Reject a pending proposal (the live record is unchanged).

    A 'reject' revision is inserted to close the proposal. The record's
    current state is unaffected.

    Examples:
        hopper revision reject 01KQABCDEF1234567890123456
        hopper revision reject 01KQ... --reason "Normalisation incorrect"
    """
    if not force:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Reject revision [bold]{revision_id[:12]}[/bold]?", default=False):
            print_info("Cancelled")
            return

    try:
        with ctx.get_client() as client:
            if not hasattr(client, "reject_revision"):
                print_error("Revision management requires local mode")
                raise click.Abort()
            result = client.reject_revision(revision_id, reason=reason, author_did=author_did)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Rejected: proposal {revision_id[:12]}")

    except ClientError as e:
        print_error(f"Failed to reject revision: {e.message}")
        raise click.Abort()
    except ValueError as e:
        print_error(str(e))
        raise click.Abort()
