#!/usr/bin/env python3
"""Backfill tasks from markdown files into the SQLite tasks table.

Reads every task markdown file from the hopper directory and upserts them
into the tasks table.  Safe to re-run — existing rows are updated in place
(merge/upsert semantics).

Usage:
    python scripts/backfill_tasks_to_sqlite.py [--hopper-path ~/.hopper] [--dry-run]

Options:
    --hopper-path PATH   Path to the .hopper directory (default: ~/.hopper)
    --dry-run            Print what would be written without touching the DB
    --verbose            Log each task ID as it is processed
"""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hopper-path",
        type=Path,
        default=Path.home() / ".hopper",
        help="Path to the .hopper directory (default: ~/.hopper)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    hopper_path: Path = args.hopper_path.expanduser().resolve()
    if not hopper_path.exists():
        print(f"ERROR: hopper path not found: {hopper_path}", file=sys.stderr)
        sys.exit(1)

    # Add src to path so we can import hopper without installing
    repo_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / "src"))

    from hopper.storage.base import StorageConfig
    from hopper.storage.markdown import MarkdownStorage
    from hopper.storage.tasks import TaskMarkdownStore
    from hopper.storage.sqlite import SQLiteStorage
    from hopper.storage.sqlite_tasks import TaskSQLiteStore

    # Source: markdown
    md_config = StorageConfig.local(hopper_path)
    md_storage = MarkdownStorage(md_config)
    md_storage.initialize()
    md_tasks = TaskMarkdownStore(md_storage)

    # Destination: SQLite
    sqlite_storage = SQLiteStorage(md_config)
    if not args.dry_run:
        sqlite_storage.initialize()
    sql_tasks = TaskSQLiteStore(sqlite_storage)

    # Load all tasks (including soft-deleted so we preserve tombstones)
    all_tasks = md_tasks.list(include_deleted=True)

    print(f"Found {len(all_tasks)} task(s) in markdown at {hopper_path}")

    inserted = 0
    updated = 0
    errors = 0

    for task in all_tasks:
        try:
            if args.dry_run:
                print(f"  [dry-run] would upsert {task.id}: {task.title!r}")
                continue

            existing = sql_tasks.get(task.id, include_deleted=True)
            if existing is None:
                sql_tasks.save(task)  # save handles upsert via session.merge
                inserted += 1
                if args.verbose:
                    print(f"  INSERT {task.id}: {task.title!r}")
            else:
                sql_tasks.save(task)
                updated += 1
                if args.verbose:
                    print(f"  UPDATE {task.id}: {task.title!r}")

        except Exception as exc:
            errors += 1
            print(f"  ERROR {task.id}: {exc}", file=sys.stderr)

    if not args.dry_run:
        print(f"\nDone: {inserted} inserted, {updated} updated, {errors} errors")
    else:
        print(f"\nDry run complete — no changes written.")


if __name__ == "__main__":
    main()
