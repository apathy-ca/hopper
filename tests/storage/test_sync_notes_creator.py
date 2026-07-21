"""Sync-wire coverage for notes + creator attribution.

These fields live in markdown frontmatter but must also survive the SyncTask
wire round-trip, or they'd be dropped the moment a task crosses the server.
Also covers the append-only note union-merge and the immutable-creator guard in
the pull-apply path.
"""

import tempfile
from pathlib import Path

import pytest

from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore
from hopper.storage.tasks import LocalTask
from hopper.upstream.sync import (
    _apply_sync_task_to_local,
    _local_task_to_sync_task,
    _merge_notes,
)


@pytest.fixture
def task_store():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = StorageConfig.local(Path(tmpdir))
        storage = MarkdownStorage(config)
        storage.initialize()
        yield TaskMarkdownStore(storage)


def test_wire_round_trip_preserves_notes_and_creator():
    """LocalTask -> SyncTask carries notes + creator (not silently dropped)."""
    task = LocalTask.create(
        title="Crosses the wire",
        created_by="human:james",
        created_by_did="did:key:z6MkJames",
    )
    task.notes = [{"author": "claude:x", "ts": "2026-07-21T00:00:00+00:00", "body": "hi"}]

    sync_task = _local_task_to_sync_task(task)
    assert sync_task.created_by == "human:james"
    assert sync_task.created_by_did == "did:key:z6MkJames"
    assert sync_task.notes == task.notes


def test_merge_notes_unions_without_loss():
    """Concurrent note streams union, dedupe, and stay time-ordered."""
    a = [
        {"author": "u1", "ts": "2026-07-21T01:00:00+00:00", "body": "first"},
        {"author": "u2", "ts": "2026-07-21T03:00:00+00:00", "body": "shared"},
    ]
    b = [
        {"author": "u2", "ts": "2026-07-21T03:00:00+00:00", "body": "shared"},  # dup
        {"author": "u3", "ts": "2026-07-21T02:00:00+00:00", "body": "second"},
    ]
    merged = _merge_notes(a, b)
    assert [n["body"] for n in merged] == ["first", "second", "shared"]


def test_apply_merges_notes_and_protects_creator(task_store):
    """A remote update unions notes and never overwrites an existing creator."""
    local = LocalTask.create(title="Owned", created_by="human:james")
    local.notes = [{"author": "human:james", "ts": "2026-07-21T01:00:00+00:00", "body": "local"}]
    task_store.create(local)

    # Remote version: newer, different (wrong) creator, a different note.
    remote = _local_task_to_sync_task(local)
    remote.updated_at = local.updated_at.replace(year=local.updated_at.year + 1)
    remote.created_by = "claude:impostor"
    remote.notes = [{"author": "claude:x", "ts": "2026-07-21T02:00:00+00:00", "body": "remote"}]

    _apply_sync_task_to_local(remote, task_store)

    reloaded = task_store.get(local.id)
    assert reloaded.created_by == "human:james"  # immutable — impostor rejected
    assert [n["body"] for n in reloaded.notes] == ["local", "remote"]  # unioned


def test_apply_backfills_creator_when_absent(task_store):
    """If local had no creator, a remote one fills it (best-effort backfill)."""
    local = LocalTask.create(title="No creator yet")
    task_store.create(local)

    remote = _local_task_to_sync_task(local)
    remote.updated_at = local.updated_at.replace(year=local.updated_at.year + 1)
    remote.created_by = "human:george"

    _apply_sync_task_to_local(remote, task_store)
    assert task_store.get(local.id).created_by == "human:george"
