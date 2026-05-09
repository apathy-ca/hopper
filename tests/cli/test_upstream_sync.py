"""Unit tests for upstream sync cursor logic.

Regression tests for the pull-cursor fix: the server indexes tasks on
received_at (server wall time), not on client-reported updated_at.  This
makes the pull cursor immune to client clock skew — including GPU boxes
running UTC while the dev machine runs a different timezone.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from hopper.upstream.protocol import SyncResponse, SyncTask
from hopper.upstream.storage import UpstreamStorage
from hopper.upstream.sync import SyncState, sync_with_upstream


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_task(task_id: str, updated_ms: int, instance: str = "test-instance") -> SyncTask:
    updated_at = datetime.fromtimestamp(updated_ms / 1000, tz=timezone.utc)
    return SyncTask(
        id=task_id,
        title=f"Task {task_id}",
        status="open",
        instance=instance,
        created_at=updated_at,
        updated_at=updated_at,
    )


def _make_task_store(tasks: list[SyncTask] | None = None) -> Any:
    """Return a minimal mock local task store with no pre-existing tasks."""
    from hopper.storage.tasks import LocalTask

    local_tasks = []
    for t in (tasks or []):
        lt = MagicMock(spec=LocalTask)
        lt.id = t.id
        lt.title = t.title
        lt.status = t.status
        lt.updated_at = t.updated_at
        lt.created_at = t.created_at
        lt.priority = "medium"
        lt.description = None
        lt.tags = []
        lt.project = None
        lt.instance = t.instance
        lt.source = "cli"
        lt.depends_on = []
        lt.external_id = None
        lt.external_url = None
        lt.external_platform = None
        lt.context = None
        lt.requester = None
        lt.owner = None
        lt.assigned_to = None
        lt.last_heartbeat = None
        lt.expected_heartbeat = None
        lt.parent_id = None
        lt.deleted = False
        local_tasks.append(lt)

    store = MagicMock()
    store.list.return_value = local_tasks
    store.get.return_value = None
    store.save.return_value = None
    store.delete.return_value = None
    return store


def _make_client(server_time: int, tasks: list[SyncTask] | None = None) -> Any:
    client = MagicMock()
    client.sync.return_value = SyncResponse(
        tasks=tasks or [],
        server_time=server_time,
        accepted=[],
        rejected=[],
    )
    return client


# ---------------------------------------------------------------------------
# Tests: client-side cursor storage
# ---------------------------------------------------------------------------


class TestPullCursor:
    """The pull cursor stored in SyncState must equal the server_time exactly.

    The server now controls its own clock (indexing on received_at), so the
    client can trust server_time as an exact cursor — no overlap needed.
    """

    def test_last_server_time_stored_exactly(self, tmp_path: Path) -> None:
        server_time = int(time.time() * 1000)
        store = _make_task_store()
        client = _make_client(server_time=server_time)
        state_path = tmp_path / ".hopper" / ".sync_state"

        sync_with_upstream(store, client, state_path, instance="test-instance")

        state = SyncState.load(state_path.parent / ".sync_state_test-instance")
        assert state.last_server_time == server_time

    def test_since_sent_on_second_sync_equals_previous_server_time(
        self, tmp_path: Path
    ) -> None:
        """Second sync must send since == server_time from previous response."""
        T = int(time.time() * 1000)
        state_path = tmp_path / ".hopper" / ".sync_state"

        # Sync 1
        sync_with_upstream(
            _make_task_store(), _make_client(server_time=T),
            state_path, instance="test-instance",
        )

        # Sync 2
        client2 = _make_client(server_time=T + 5000)
        sync_with_upstream(
            _make_task_store(), client2, state_path, instance="test-instance",
        )

        call_args = client2.sync.call_args
        since_sent = call_args.kwargs.get("since") or call_args.args[1]
        assert since_sent == T, (
            f"sync 2 should send since={T} (previous server_time), got {since_sent}"
        )


# ---------------------------------------------------------------------------
# Tests: server-side index uses received_at
# ---------------------------------------------------------------------------


class TestServerIndexOnReceivedAt:
    """UpstreamStorage.put() must index on server received_at, not client updated_at."""

    def test_index_uses_server_time_not_client_time(self, tmp_path: Path) -> None:
        storage = UpstreamStorage(tmp_path)

        # Client claims the task was updated 10 minutes in the future.
        future_ms = int(time.time() * 1000) + 10 * 60 * 1000
        task = _make_sync_task("task-future", updated_ms=future_ms)

        before = int(time.time() * 1000)
        ok, _ = storage.put(task, from_did="did:key:test")
        after = int(time.time() * 1000)

        assert ok
        index_ts = storage._index[storage._index_key("test-instance", "task-future")]
        # Index must be server wall time, not the client's future timestamp.
        assert before <= index_ts <= after, (
            f"index entry {index_ts} should be within [{before}, {after}], "
            f"not the client's future timestamp {future_ms}"
        )

    def test_list_since_uses_server_received_time(self, tmp_path: Path) -> None:
        """Tasks with skewed client clocks are still returned at the right time."""
        storage = UpstreamStorage(tmp_path)

        # Two tasks: one with a far-future client timestamp, one normal.
        now_ms = int(time.time() * 1000)
        future_task = _make_sync_task("task-future", updated_ms=now_ms + 60_000)
        normal_task = _make_sync_task("task-normal", updated_ms=now_ms - 1000)

        storage.put(future_task, from_did="did:key:test")
        storage.put(normal_task, from_did="did:key:test")

        # Both tasks were received now, so they should appear in list_since(0).
        results = storage.list_since(0, instance="test-instance")
        ids = {t.id for t in results}
        assert "task-future" in ids
        assert "task-normal" in ids

    def test_conflict_still_uses_client_updated_at(self, tmp_path: Path) -> None:
        """Conflict resolution must still use client updated_at, not received_at.

        A newer client edit (higher updated_at) must win even if it arrives
        after the first write's received_at.
        """
        storage = UpstreamStorage(tmp_path)

        now_ms = int(time.time() * 1000)
        old_task = _make_sync_task("task-conflict", updated_ms=now_ms - 5000)
        new_task = _make_sync_task("task-conflict", updated_ms=now_ms)

        ok1, _ = storage.put(old_task, from_did="did:key:test")
        assert ok1

        # New task has higher updated_at — should be accepted.
        ok2, reason = storage.put(new_task, from_did="did:key:test")
        assert ok2, f"newer client edit should be accepted, got: {reason}"

        # Old re-send should be rejected.
        ok3, reason3 = storage.put(old_task, from_did="did:key:test")
        assert not ok3, f"stale re-send should be rejected, got: {reason3}"

    def test_rebuild_index_prefers_received_at(self, tmp_path: Path) -> None:
        """After a server restart, _rebuild_index must recover received_at."""
        storage = UpstreamStorage(tmp_path)

        now_ms = int(time.time() * 1000)
        task = _make_sync_task("task-rebuild", updated_ms=now_ms - 30_000)

        before = int(time.time() * 1000)
        storage.put(task, from_did="did:key:test")
        after = int(time.time() * 1000)

        # Simulate server restart by creating a fresh UpstreamStorage (drops
        # in-memory index and calls _rebuild_index from disk).
        storage2 = UpstreamStorage(tmp_path)
        index_ts = storage2._index.get(
            storage2._index_key("test-instance", "task-rebuild")
        )
        assert index_ts is not None
        # Should recover server received_at, not the client's old timestamp.
        assert before <= index_ts <= after, (
            f"rebuilt index entry {index_ts} should be server time [{before}, {after}], "
            f"not client's updated_at {now_ms - 30_000}"
        )
