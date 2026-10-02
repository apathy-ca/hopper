"""Maintenance commands for data hygiene.

Currently provides ``hopper maintenance reclassify`` — a migration that
folds legacy tag-encoded records into first-class record kinds:

  - records tagged ``gpu-job``                      -> kind=job
  - records tagged any of {memory, claude-import,
    claude-memory-project, claude-memory-feedback}  -> kind=memory

The command is **dry-run by default**: without ``--apply`` it inspects the
data and prints a per-rule summary of what *would* change, mutating nothing.
Only with ``--apply`` does it write the new kinds back.
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
    print_warning,
)

ClientError = (APIError, LocalClientError)

# Rule order matters: the first matching rule wins for a given record, so a
# record carrying both a job tag and a memory tag is classified as a job.
_RECLASSIFY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("job", ("gpu-job",)),
    (
        "memory",
        ("memory", "claude-import", "claude-memory-project", "claude-memory-feedback"),
    ),
)


def is_foreign_record(record_instance: str | None, own_instance: str | None) -> bool:
    """True if a record belongs to another instance's shard than this store's.

    Sync stores a record under its own ``instance`` field, so rewriting a
    foreign record re-stamps it and pushes it into the other shard, where it
    can overwrite newer remote state this store has never pulled.
    """
    return bool(own_instance and record_instance and record_instance != own_instance)


def _target_kind(tags: list[str], current_kind: str) -> str | None:
    """Return the kind a record should be reclassified to, or None.

    Returns None when no rule matches or the record is already that kind.
    """
    tagset = set(tags or [])
    for target, triggers in _RECLASSIFY_RULES:
        if tagset & set(triggers):
            if current_kind == target:
                return None  # already classified — nothing to do
            return target
    return None


@click.group(name="maintenance")
def maintenance() -> None:
    """Data hygiene and migration commands."""
    pass


@maintenance.command(name="reclassify")
@click.option(
    "--apply",
    "apply_changes",
    is_flag=True,
    help="Actually write the new kinds. Without this flag, runs as a dry-run and mutates nothing.",
)
@click.option("--limit", type=int, default=100000, help="Max records to scan")
@click.option(
    "--include-foreign",
    is_flag=True,
    help="Also rewrite records that belong to a different instance than this "
    "store. Skipped by default: they may be stale copies, and rewriting them "
    "overwrites newer remote state on the next sync.",
)
@click.pass_obj
def reclassify(ctx: Context, apply_changes: bool, limit: int, include_foreign: bool) -> None:
    """Reclassify legacy tag-encoded records to first-class kinds.

    DRY-RUN BY DEFAULT. Records tagged ``gpu-job`` become kind=job; records
    tagged ``memory``/``claude-import``/``claude-memory-project``/
    ``claude-memory-feedback`` become kind=memory. Pass ``--apply`` to write.

    Examples:
        hopper maintenance reclassify           # preview only
        hopper maintenance reclassify --apply   # perform the migration
    """
    try:
        with ctx.get_client() as client:
            # Scan every kind so already-tagged records (regardless of current
            # kind) are considered.
            records = client.list_tasks(all_kinds=True, limit=limit)

            counts: dict[str, int] = {target: 0 for target, _ in _RECLASSIFY_RULES}
            planned: list[tuple[str, str]] = []  # (record_id, target_kind)
            skipped_foreign: list[str] = []
            own_instance = getattr(getattr(client, "config", None), "instance_id", None)

            for rec in records:
                target = _target_kind(rec.get("tags", []), rec.get("kind", "task"))
                if target is None:
                    continue
                if not include_foreign and is_foreign_record(rec.get("instance"), own_instance):
                    skipped_foreign.append(rec["id"])
                    continue
                counts[target] += 1
                planned.append((rec["id"], target))

            total = len(planned)
            if skipped_foreign and not ctx.json_output:
                print_warning(
                    f"Skipped {len(skipped_foreign)} record(s) belonging to another instance "
                    f"(not '{own_instance}'): sync them first, or pass --include-foreign."
                )

            if apply_changes:
                applied = 0
                for record_id, target in planned:
                    client.update_task(record_id, {"kind": target})
                    applied += 1

                if ctx.json_output:
                    print_json(
                        {
                            "applied": applied,
                            "by_kind": counts,
                            "dry_run": False,
                            "skipped_foreign": skipped_foreign,
                        }
                    )
                else:
                    print_success(f"Reclassified {applied} record(s).")
                    for target, n in counts.items():
                        if n:
                            console.print(f"  -> kind={target}: {n}")
                return

            # Dry-run: report only, mutate nothing.
            if ctx.json_output:
                print_json(
                    {
                        "would_change": total,
                        "by_kind": counts,
                        "dry_run": True,
                        "skipped_foreign": skipped_foreign,
                    }
                )
            else:
                if total == 0:
                    print_info("Nothing to reclassify.")
                else:
                    print_info(
                        f"DRY-RUN: {total} record(s) would be reclassified "
                        "(no changes written). Re-run with --apply to perform it."
                    )
                    for target, n in counts.items():
                        if n:
                            console.print(f"  -> kind={target}: {n}")

    except ClientError as e:
        print_error(f"Reclassify failed: {e.message}")
        raise click.Abort() from e
