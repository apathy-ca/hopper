"""Sync orchestration between local storage and upstream server.

Handles:
- Tracking last sync timestamp
- Collecting local changes
- Pushing to server
- Applying remote changes locally
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from .client import PayloadTooLargeError, UpstreamClient, UpstreamError
from .protocol import SyncResponse, SyncTask

if TYPE_CHECKING:
    from hopper.storage.tasks import LocalTask, TaskMarkdownStore


@dataclass
class SyncState:
    """Tracks sync state between local and upstream."""

    last_sync: int = 0  # ms since epoch
    last_server_time: int = 0  # server's time at last sync

    @classmethod
    def load(cls, path: Path) -> SyncState:
        """Load sync state from file.

        If the stored ``last_sync`` is implausibly far in the future (local
        clock jumped forward, then jumped back), reset to 0 rather than
        silently filtering out every future local edit.
        """
        if not path.exists():
            return cls()
        try:
            with open(path) as f:
                data = json.load(f)
                last_sync = data.get("last_sync", 0)
                last_server_time = data.get("last_server_time", 0)
        except (json.JSONDecodeError, OSError):
            return cls()

        # Guard: allow up to 1h skew, otherwise treat as corrupt.
        now_ms = int(time.time() * 1000)
        skew_ms = 3600 * 1000
        if last_sync > now_ms + skew_ms:
            last_sync = 0
            last_server_time = 0

        return cls(last_sync=last_sync, last_server_time=last_server_time)

    def save(self, path: Path) -> None:
        """Save sync state to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(
                {
                    "last_sync": self.last_sync,
                    "last_server_time": self.last_server_time,
                },
                f,
            )


DEFAULT_BATCH_SIZE = 100
# Stay under nginx's default client_max_body_size (1 MiB), leaving headroom for
# the request envelope.
DEFAULT_BATCH_BYTES = 800_000


@dataclass
class SyncResult:
    """Result of a sync operation."""

    pushed: list[str] = field(default_factory=list)  # task IDs pushed
    pulled: list[str] = field(default_factory=list)  # task IDs pulled
    conflicts: list[str] = field(default_factory=list)  # task IDs with conflicts
    errors: list[str] = field(default_factory=list)  # error messages
    notes_added: list[str] = field(default_factory=list)  # losing edits saved as notes


def _datetime_to_ms(dt: datetime | None) -> int:
    """Convert datetime to milliseconds since epoch.

    Naive datetimes are assumed to be UTC, matching the storage convention.
    """
    if dt is None:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def _local_task_to_sync_task(task: LocalTask) -> SyncTask:
    """Convert a LocalTask to SyncTask for the wire."""
    return SyncTask(
        id=task.id,
        title=task.title,
        status=task.status,
        priority=task.priority,
        description=task.description,
        tags=task.tags,
        project=task.project,
        instance=task.instance,
        source=task.source,
        depends_on=task.depends_on,
        created_at=task.created_at,
        updated_at=task.updated_at,
        external_id=task.external_id,
        external_url=task.external_url,
        external_platform=task.external_platform,
        context=task.context,
        requester=task.requester,
        owner=task.owner,
        assigned_to=task.assigned_to,
        last_heartbeat=task.last_heartbeat,
        expected_heartbeat=task.expected_heartbeat,
        parent_id=task.parent_id,
        deleted=task.deleted,
        notes=getattr(task, "notes", None) or [],
        created_by=getattr(task, "created_by", None),
        created_by_did=getattr(task, "created_by_did", None),
        kind=getattr(task, "kind", None),
        subject=getattr(task, "subject", None),
        scope=getattr(task, "scope", None),
        provenance=getattr(task, "provenance", None),
        memory_class=getattr(task, "memory_class", None),
        superseded_by=getattr(task, "superseded_by", None),
        source_record_ids=getattr(task, "source_record_ids", None) or [],
        consolidation_run_id=getattr(task, "consolidation_run_id", None),
        consolidated_at=getattr(task, "consolidated_at", None),
        drift_checked_at=getattr(task, "drift_checked_at", None),
        drift_score=getattr(task, "drift_score", None),
    )


def _merge_notes(local: list[dict] | None, remote: list[dict] | None) -> list[dict]:
    """Union two append-only note streams, deduped and time-ordered.

    Notes are append-only (never edited or deleted), so a set-union by
    (author, ts, body) loses nothing and resolves concurrent note-adds on
    different instances without last-write-wins dropping either side.
    """
    merged: dict[tuple, dict] = {}
    for note in (local or []) + (remote or []):
        key = (note.get("author"), note.get("ts"), note.get("body"))
        merged.setdefault(key, note)
    return sorted(merged.values(), key=lambda n: n.get("ts") or "")


def _apply_sync_task_to_local(
    sync_task: SyncTask,
    task_store: TaskMarkdownStore,
) -> str | None:
    """Apply a SyncTask to local storage.

    Returns the task ID if applied, None if skipped.
    """
    from hopper.storage.tasks import LocalTask

    # Check if we have this task locally (include tombstones — we need to
    # compare timestamps against soft-deleted tasks too)
    existing = task_store.get(sync_task.id, include_deleted=True)

    if existing:
        # Compare timestamps - only update if remote is newer
        local_ts = _datetime_to_ms(existing.updated_at)
        remote_ts = _datetime_to_ms(sync_task.updated_at)

        if remote_ts <= local_ts:
            return None  # Local is newer or same, skip

    # Handle deletion
    if sync_task.deleted:
        if existing:
            task_store.delete(sync_task.id)
            return sync_task.id
        return None

    # Create or update task
    if existing:
        # Update existing task
        existing.title = sync_task.title
        existing.status = sync_task.status
        existing.priority = sync_task.priority
        existing.description = sync_task.description
        existing.tags = sync_task.tags
        existing.project = sync_task.project
        existing.instance = sync_task.instance
        existing.source = sync_task.source
        existing.depends_on = sync_task.depends_on
        existing.created_at = sync_task.created_at
        existing.updated_at = sync_task.updated_at
        existing.external_id = sync_task.external_id
        existing.external_url = sync_task.external_url
        existing.external_platform = sync_task.external_platform
        existing.context = sync_task.context
        existing.requester = sync_task.requester
        existing.owner = sync_task.owner
        existing.assigned_to = sync_task.assigned_to
        existing.last_heartbeat = sync_task.last_heartbeat
        existing.expected_heartbeat = sync_task.expected_heartbeat
        existing.parent_id = sync_task.parent_id
        # Notes are append-only: union both sides so a concurrent add on another
        # instance is never dropped by last-write-wins.
        existing.notes = _merge_notes(existing.notes, sync_task.notes)
        # Creator attribution is immutable: keep whatever was stamped first, so a
        # later edit (or an older client that omits the field) can't wipe it.
        existing.created_by = existing.created_by or sync_task.created_by
        existing.created_by_did = existing.created_by_did or sync_task.created_by_did
        existing.kind = sync_task.kind or "task"
        existing.subject = sync_task.subject
        existing.scope = sync_task.scope
        existing.provenance = sync_task.provenance
        existing.memory_class = sync_task.memory_class
        existing.superseded_by = sync_task.superseded_by
        existing.source_record_ids = sync_task.source_record_ids or []
        existing.consolidation_run_id = sync_task.consolidation_run_id
        existing.consolidated_at = sync_task.consolidated_at
        existing.drift_checked_at = sync_task.drift_checked_at
        existing.drift_score = sync_task.drift_score
        task_store.save(existing, preserve_timestamp=True)
    else:
        # Create new task with the remote ID
        new_task = LocalTask(
            id=sync_task.id,
            title=sync_task.title,
            status=sync_task.status,
            priority=sync_task.priority,
            description=sync_task.description,
            tags=sync_task.tags,
            project=sync_task.project,
            instance=sync_task.instance,
            source=sync_task.source,
            depends_on=sync_task.depends_on,
            created_at=sync_task.created_at,
            updated_at=sync_task.updated_at,
            external_id=sync_task.external_id,
            external_url=sync_task.external_url,
            external_platform=sync_task.external_platform,
            context=sync_task.context,
            requester=sync_task.requester,
            owner=sync_task.owner,
            assigned_to=sync_task.assigned_to,
            last_heartbeat=sync_task.last_heartbeat,
            expected_heartbeat=sync_task.expected_heartbeat,
            parent_id=sync_task.parent_id,
            notes=sync_task.notes or [],
            created_by=sync_task.created_by,
            created_by_did=sync_task.created_by_did,
            kind=sync_task.kind or "task",
            subject=sync_task.subject,
            scope=sync_task.scope,
            provenance=sync_task.provenance,
            memory_class=sync_task.memory_class,
            superseded_by=sync_task.superseded_by,
            source_record_ids=sync_task.source_record_ids or [],
            consolidation_run_id=sync_task.consolidation_run_id,
            consolidated_at=sync_task.consolidated_at,
            drift_checked_at=sync_task.drift_checked_at,
            drift_score=sync_task.drift_score,
        )
        task_store.save(new_task, preserve_timestamp=True)

    return sync_task.id


def _updated_ms(task: LocalTask) -> int:
    return _datetime_to_ms(task.updated_at)


def _next_batch(
    tasks: list[LocalTask], max_records: int, max_bytes: int
) -> tuple[list[SyncTask], int]:
    """Take a leading slice of ``tasks`` (sorted by updated_at) as one request body.

    Bounded by record count and approximate serialized size (a single oversized
    task still goes alone).

    Returns the wire tasks and how many local tasks were consumed.
    """
    batch: list[SyncTask] = []
    size = 0
    n = 0
    while n < len(tasks) and n < max_records:
        wire = _local_task_to_sync_task(tasks[n])
        wire_size = len(wire.model_dump_json())
        if batch and size + wire_size > max_bytes:
            break
        batch.append(wire)
        size += wire_size
        n += 1
    return batch, n


SYNC_NOTE_AUTHOR = "hopper:sync"
_LOST_FIELDS = (
    "title",
    "status",
    "priority",
    "description",
    "tags",
    "assigned_to",
    "project",
    "depends_on",
)
_LOST_VALUE_MAX = 2000


def _record_lost_edit(task_store: TaskMarkdownStore, pushed: SyncTask) -> bool:
    """Keep a rejected local edit as a note on the task that replaced it.

    When the server rejects a push (server wins), the pull overwrites the local
    task and the losing values would vanish. Append them as an attributed note,
    listing only the fields that differ from the version that won. The note is
    saved with the winner's timestamp so it stays local until the task next
    changes; bumping updated_at here would let this host's copy overwrite a
    newer edit made elsewhere in the meantime.

    Returns True if a note was added.
    """
    current = task_store.get(pushed.id, include_deleted=True)
    if current is None:
        return False
    lines = []
    for name in _LOST_FIELDS:
        mine, winner = getattr(pushed, name, None), getattr(current, name, None)
        if mine == winner:
            continue
        text = str(mine)
        if len(text) > _LOST_VALUE_MAX:
            text = text[:_LOST_VALUE_MAX] + "... [truncated]"
        lines.append(f"- {name}: {text}")
    if not lines:
        return False
    when = pushed.updated_at.isoformat() if pushed.updated_at else "unknown time"
    current.notes = _merge_notes(
        current.notes,
        [
            {
                "author": SYNC_NOTE_AUTHOR,
                "ts": datetime.now(UTC).isoformat(),
                "body": f"Sync conflict: the server version won. Your local edit from {when} "
                "was replaced; its values for the fields that differ:\n" + "\n".join(lines),
            }
        ],
    )
    task_store.save(current, preserve_timestamp=True)
    return True


def _apply_pulled(
    response: SyncResponse, task_store: TaskMarkdownStore, result: SyncResult
) -> None:
    for sync_task in response.tasks:
        task_id = _apply_sync_task_to_local(sync_task, task_store)
        if task_id:
            result.pulled.append(task_id)


def pending_changes(
    task_store: TaskMarkdownStore, state_path: Path, instance: str = "local"
) -> tuple[int, int]:
    """Count (records, approximate bytes) that the next sync would push."""
    state_path = state_path.parent / f"{state_path.name}_{instance}"
    state = SyncState.load(state_path)
    changed = task_store.list_since(state.last_sync, include_deleted=True)
    size = sum(len(_local_task_to_sync_task(t).model_dump_json()) for t in changed)
    return len(changed), size


def sync_with_upstream(
    task_store: TaskMarkdownStore,
    client: UpstreamClient,
    state_path: Path,
    instance: str = "local",
    batch_size: int = DEFAULT_BATCH_SIZE,
    batch_bytes: int = DEFAULT_BATCH_BYTES,
) -> SyncResult:
    """Perform a full sync with upstream server.

    1. Load sync state (last sync timestamp)
    2. Collect local tasks modified since last sync
    3. Push to server
    4. Apply server's updates locally
    5. Save new sync state

    Args:
        task_store: Local task storage
        client: Upstream client
        state_path: Path to sync state file (base path; instance suffix appended)
        instance: Instance ID used to qualify the sync state file name
        batch_size: Max records per push request. Halved automatically on HTTP 413.
        batch_bytes: Approximate max serialized bytes per push request

    Returns:
        SyncResult with pushed/pulled/conflict counts
    """
    # Per-instance state file so switching instances doesn't skip tasks
    state_path = state_path.parent / f"{state_path.name}_{instance}"
    result = SyncResult()

    # Load sync state
    state = SyncState.load(state_path)

    # Snapshot the cursor BEFORE reading local tasks. If we captured it after
    # the network round-trip, any local edit that happened during the sync
    # window would have updated_at < cursor and be dropped on the next run.
    sync_start_ms = int(time.time() * 1000)

    # Collect local tasks modified since last sync (including soft-deleted)
    # Uses index-based filtering to avoid loading all tasks
    pending = sorted(task_store.list_since(state.last_sync, include_deleted=True), key=_updated_ms)

    # Push in bounded batches so a large backlog can't exceed a proxy body
    # limit. The cursor advances after each accepted batch, so a mid-run
    # failure resumes where it stopped instead of redoing earlier batches.
    # The pull cursor advances likewise: later batches only ask for what the
    # previous response didn't already cover.
    batch_size = max(1, batch_size)
    since = state.last_server_time
    while True:
        batch, consumed = _next_batch(pending, batch_size, batch_bytes)
        try:
            response = client.sync(
                tasks=batch, since=since, instance=instance, pull_limit=batch_size
            )
        except PayloadTooLargeError as e:
            if len(batch) > 1:
                batch_size = max(1, len(batch) // 2)
                batch_bytes = max(1, batch_bytes // 2)
                continue
            result.errors.append(str(e))
            return result
        except UpstreamError as e:
            result.errors.append(str(e))
            return result

        result.pushed.extend(response.accepted)
        result.conflicts.extend(c.task_id for c in response.rejected)
        rejected_ids = {c.task_id for c in response.rejected}
        losers = [t for t in batch if t.id in rejected_ids]
        _apply_pulled(response, task_store, result)

        # Drain remaining pull pages. Until the last page, the cursor is the
        # page boundary (not server_time) so a failure resumes mid-pull.
        while response.has_more and response.next_since is not None:
            state.last_server_time = response.next_since
            state.save(state_path)
            try:
                response = client.sync(
                    tasks=[],
                    since=response.next_since,
                    instance=instance,
                    pull_limit=batch_size,
                )
            except UpstreamError as e:
                result.errors.append(str(e))
                return result
            _apply_pulled(response, task_store, result)

        # The winning versions are in place; preserve what the losers had.
        for pushed in losers:
            if _record_lost_edit(task_store, pushed):
                result.notes_added.append(pushed.id)

        since = response.server_time
        state.last_server_time = response.server_time
        rest = pending[consumed:]
        # Final batch: use the pre-sync snapshot, not "now". Intermediate
        # batches: resume at the last task sent. list_since is a strict ">", so
        # step back 1 ms to keep tasks tied on that millisecond; re-sending
        # them is idempotent.
        state.last_sync = _updated_ms(pending[consumed - 1]) - 1 if rest else sync_start_ms
        state.save(state_path)
        pending = rest
        if not pending:
            break

    return result
