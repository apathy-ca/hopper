"""Unit tests for upstream sync cursor logic.

Regression tests for the pull-cursor fix: the server indexes tasks on
received_at (server wall time), not on client-reported updated_at.  This
makes the pull cursor immune to client clock skew — including GPU boxes
running UTC while the dev machine runs a different timezone.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from hopper.upstream.protocol import SyncResponse, SyncTask
from hopper.upstream.storage import UpstreamStorage
from hopper.upstream.sync import (
    SyncState,
    _apply_sync_task_to_local,
    _local_task_to_sync_task,
    sync_with_upstream,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sync_task(task_id: str, updated_ms: int, instance: str = "test-instance") -> SyncTask:
    updated_at = datetime.fromtimestamp(updated_ms / 1000, tz=UTC)
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
    for t in tasks or []:
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

    def test_since_sent_on_second_sync_equals_previous_server_time(self, tmp_path: Path) -> None:
        """Second sync must send since == server_time from previous response."""
        T = int(time.time() * 1000)
        state_path = tmp_path / ".hopper" / ".sync_state"

        # Sync 1
        sync_with_upstream(
            _make_task_store(),
            _make_client(server_time=T),
            state_path,
            instance="test-instance",
        )

        # Sync 2
        client2 = _make_client(server_time=T + 5000)
        sync_with_upstream(
            _make_task_store(),
            client2,
            state_path,
            instance="test-instance",
        )

        call_args = client2.sync.call_args
        since_sent = call_args.kwargs.get("since") or call_args.args[1]
        assert (
            since_sent == T
        ), f"sync 2 should send since={T} (previous server_time), got {since_sent}"


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
        index_ts = storage2._index.get(storage2._index_key("test-instance", "task-rebuild"))
        assert index_ts is not None
        # Should recover server received_at, not the client's old timestamp.
        assert before <= index_ts <= after, (
            f"rebuilt index entry {index_ts} should be server time [{before}, {after}], "
            f"not client's updated_at {now_ms - 30_000}"
        )


# ---------------------------------------------------------------------------
# Tests: kind/type + structured memory fields survive every sync hop
# ---------------------------------------------------------------------------


class TestKindAndMemoryFieldRoundTrip:
    """kind/type + structured memory fields (subject/scope/provenance) must
    survive every sync hop: client serialize -> wire model -> server store
    (revision.payload) -> server read -> pull back -> client apply.

    Regression for the dropped-field bug: SyncTask did not declare these
    fields, so Pydantic silently dropped them on validation/dump and the
    server's revision_writer always derived record_type="task".
    """

    MEMORY_FIELDS = {
        "kind": "memory",
        "subject": "auth flow",
        "scope": "project:hopper",
        "provenance": "claude:acm-rewrite",
    }

    @staticmethod
    def _markdown_store(tmp_path: Path) -> Any:
        from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore

        config = StorageConfig.local(tmp_path)
        storage = MarkdownStorage(config)
        storage.initialize()
        return TaskMarkdownStore(storage)

    def test_protocol_serialize_deserialize_preserves_fields(self) -> None:
        """model_dump -> model_validate round-trips all four fields (the wire)."""
        now = datetime.now(UTC)
        task = SyncTask(
            id="mem-1",
            title="A memory",
            status="open",
            instance="test-instance",
            created_at=now,
            updated_at=now,
            **self.MEMORY_FIELDS,
        )

        wire = task.model_dump(mode="json")
        # Fields must be present on the wire payload, not silently dropped.
        assert wire["kind"] == "memory"
        assert wire["subject"] == "auth flow"
        assert wire["scope"] == "project:hopper"
        assert wire["provenance"] == "claude:acm-rewrite"

        restored = SyncTask.model_validate(wire)
        assert restored.kind == "memory"
        assert restored.subject == "auth flow"
        assert restored.scope == "project:hopper"
        assert restored.provenance == "claude:acm-rewrite"

    def test_server_store_payload_preserves_fields(self, tmp_path: Path) -> None:
        """UpstreamStorage.put -> get keeps the fields in revision.payload.

        revision_writer derives records.type from payload['kind'], so the
        stored payload must carry kind="memory".
        """
        storage = UpstreamStorage(tmp_path)
        now = datetime.now(UTC)
        task = SyncTask(
            id="mem-store",
            title="A memory",
            status="open",
            instance="test-instance",
            created_at=now,
            updated_at=now,
            **self.MEMORY_FIELDS,
        )

        ok, _ = storage.put(task, from_did="did:key:test")
        assert ok

        # The same dict shape revision_writer consumes (payload.get("kind")).
        stored = storage.get("test-instance", "mem-store")
        assert stored is not None
        payload = stored.task.model_dump(mode="json")
        assert payload["kind"] == "memory"
        assert payload["subject"] == "auth flow"
        assert payload["scope"] == "project:hopper"
        assert payload["provenance"] == "claude:acm-rewrite"

    def test_client_serialize_and_apply_round_trip(self, tmp_path: Path) -> None:
        """LocalTask -> SyncTask -> (pull) -> LocalTask preserves the fields."""
        from hopper.storage.tasks import LocalTask

        local = LocalTask.create(
            title="A memory",
            status="open",
            **self.MEMORY_FIELDS,
        )

        # Client serialize hop.
        sync_task = _local_task_to_sync_task(local)
        assert sync_task.kind == "memory"
        assert sync_task.subject == "auth flow"
        assert sync_task.scope == "project:hopper"
        assert sync_task.provenance == "claude:acm-rewrite"

        # Pull-back / apply hop into a real markdown store.
        store = self._markdown_store(tmp_path)
        applied_id = _apply_sync_task_to_local(sync_task, store)
        assert applied_id == sync_task.id

        reloaded = store.get(sync_task.id)
        assert reloaded is not None
        assert reloaded.kind == "memory"
        assert reloaded.subject == "auth flow"
        assert reloaded.scope == "project:hopper"
        assert reloaded.provenance == "claude:acm-rewrite"

    def test_legacy_task_without_fields_still_syncs(self, tmp_path: Path) -> None:
        """Older payloads omitting the fields validate and default to a task."""
        # Simulate an old client/server that never sends the new keys.
        legacy_wire = {
            "id": "legacy-1",
            "title": "Old task",
            "status": "open",
            "instance": "test-instance",
        }
        restored = SyncTask.model_validate(legacy_wire)
        assert restored.kind is None  # treated as "task" downstream
        assert restored.subject is None
        assert restored.scope is None
        assert restored.provenance is None

        store = self._markdown_store(tmp_path)
        applied_id = _apply_sync_task_to_local(restored, store)
        assert applied_id == "legacy-1"
        reloaded = store.get("legacy-1")
        assert reloaded is not None
        assert reloaded.kind == "task"
