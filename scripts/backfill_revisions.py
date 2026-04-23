"""Backfill records + revisions from an upstream-data tree.

Reads ``<root>/tasks/<instance>/*.json`` produced by the Hopper server and
populates the new records + revisions tables. One ``create`` revision per
task. Idempotent: skips records that already exist.

Usage::

    python scripts/backfill_revisions.py \\
        --root ~/.hopper/upstream-data \\
        --database-url sqlite:////tmp/hopper-test.db \\
        [--dry-run]

By design this does not touch the existing ``tasks`` table and does not
modify the source tree. Phase 4a is observational: the new tables exist
and are populated; the live write path is unchanged.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Allow running as a script without packaging install
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from hopper.models import (  # noqa: E402
    Record,
    RecordType,
    Revision,
    RevisionAction,
    new_ulid,
)
from hopper.models.revision import SCHEMA_VERSION  # noqa: E402


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    # Accept both Z-suffix and offset forms
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    # Drop tz for sqlite DateTime columns (naive UTC)
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def ensure_instance(session: Session, instance_id: str) -> None:
    """Create a placeholder hopper_instances row if one doesn't exist.

    Uses raw SQL rather than the HopperInstance ORM model because the model
    has columns (instance_type, runtime_metadata, started_at, stopped_at)
    that the initial schema migration did not create. Reconciling that drift
    is out of scope for Phase 4a. We touch only the columns the DB actually
    has.
    """
    found = session.execute(
        text("SELECT 1 FROM hopper_instances WHERE id = :id"),
        {"id": instance_id},
    ).first()
    if found is not None:
        return
    now = datetime.utcnow()
    session.execute(
        text(
            "INSERT INTO hopper_instances "
            "(id, name, scope, status, created_at, updated_at) "
            "VALUES (:id, :name, :scope, :status, :now, :now)"
        ),
        {
            "id": instance_id,
            "name": instance_id,
            "scope": "PERSONAL",
            "status": "running",
            "now": now,
        },
    )


def backfill_one(
    session: Session,
    task_json: dict[str, Any],
    instance_id: str,
    dry_run: bool,
) -> str:
    """Backfill a single task JSON file. Returns one of: created, skipped, error."""
    task = task_json.get("task") or {}
    task_id = task.get("id")
    if not task_id:
        return "error"

    if session.get(Record, task_id) is not None:
        return "skipped"

    created_at = parse_iso(task.get("created_at")) or datetime.utcnow()
    updated_at = parse_iso(task.get("updated_at")) or created_at

    if dry_run:
        return "created"

    revision_id = new_ulid()
    revision = Revision(
        id=revision_id,
        record_id=task_id,
        parent_revision_id=None,
        action=RevisionAction.CREATE.value,
        author_did=task_json.get("from_did"),
        # task.source captures the original write context. Current values
        # are typically "cli" — honest proto-location. Phase 4b richens
        # this on new writes; backfilled rows keep their historical value.
        author_location=task.get("source"),
        payload=task,
        schema_version=SCHEMA_VERSION,
        created_at=created_at,
    )
    record = Record(
        id=task_id,
        type=RecordType.TASK.value,
        instance_id=instance_id,
        current_revision_id=None,  # filled after flush
        tombstoned_at=None,
        created_at=created_at,
        updated_at=updated_at,
    )
    session.add(record)
    session.flush()
    session.add(revision)
    session.flush()
    record.current_revision_id = revision_id
    session.flush()
    return "created"


def run_backfill(root: Path, database_url: str, dry_run: bool) -> dict[str, int]:
    tasks_root = root / "tasks"
    if not tasks_root.is_dir():
        raise SystemExit(f"No tasks directory at {tasks_root}")

    engine = create_engine(database_url)
    counts = {"created": 0, "skipped": 0, "error": 0}

    # Process named project instances before 'local'. 'local' is the
    # personal aggregator that mirrors tasks from named projects; if it
    # runs first it wins dedup and the named project gets empty shelves.
    def _order(p: Path) -> tuple[int, str]:
        return (1 if p.name == "local" else 0, p.name)

    with Session(engine) as session:
        for instance_dir in sorted(
            (d for d in tasks_root.iterdir() if d.is_dir()),
            key=_order,
        ):
            instance_id = instance_dir.name
            if not dry_run:
                ensure_instance(session, instance_id)
                session.flush()

            for task_file in sorted(instance_dir.glob("*.json")):
                try:
                    data = json.loads(task_file.read_text())
                except (OSError, json.JSONDecodeError) as e:
                    print(f"  ERROR reading {task_file.name}: {e}", file=sys.stderr)
                    counts["error"] += 1
                    continue
                result = backfill_one(session, data, instance_id, dry_run)
                counts[result] += 1

        if dry_run:
            session.rollback()
        else:
            session.commit()

    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(os.path.expanduser("~/.hopper/upstream-data")),
        help="Path to upstream-data tree (default: ~/.hopper/upstream-data)",
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", "sqlite:///./hopper.db"),
        help="SQLAlchemy URL (default: $DATABASE_URL or sqlite:///./hopper.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be written without committing",
    )
    args = parser.parse_args()

    print(f"Root:         {args.root}")
    print(f"Database:     {args.database_url}")
    print(f"Mode:         {'dry-run' if args.dry_run else 'commit'}")

    counts = run_backfill(args.root, args.database_url, args.dry_run)
    print()
    print(f"Records created: {counts['created']}")
    print(f"Records skipped: {counts['skipped']} (already present)")
    print(f"Errors:          {counts['error']}")


if __name__ == "__main__":
    main()
