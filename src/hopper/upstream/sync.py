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
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .client import UpstreamClient
from .did import DIDKey
from .protocol import SyncTask

if TYPE_CHECKING:
    from hopper.storage.tasks import LocalTask, TaskMarkdownStore


@dataclass
class SyncState:
    """Tracks sync state between local and upstream."""

    last_sync: int = 0  # ms since epoch
    last_server_time: int = 0  # server's time at last sync

    @classmethod
    def load(cls, path: Path) -> SyncState:
        """Load sync state from file."""
        if not path.exists():
            return cls()
        try:
            with open(path) as f:
                data = json.load(f)
                return cls(
                    last_sync=data.get("last_sync", 0),
                    last_server_time=data.get("last_server_time", 0),
                )
        except (json.JSONDecodeError, OSError):
            return cls()

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


@dataclass
class SyncResult:
    """Result of a sync operation."""

    pushed: list[str] = field(default_factory=list)  # task IDs pushed
    pulled: list[str] = field(default_factory=list)  # task IDs pulled
    conflicts: list[str] = field(default_factory=list)  # task IDs with conflicts
    errors: list[str] = field(default_factory=list)  # error messages


def _datetime_to_ms(dt: datetime | None) -> int:
    """Convert datetime to milliseconds since epoch."""
    if dt is None:
        return 0
    return int(dt.timestamp() * 1000)


def _local_task_to_sync_task(task: "LocalTask") -> SyncTask:
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
    )


def _apply_sync_task_to_local(
    sync_task: SyncTask,
    task_store: "TaskMarkdownStore",
) -> str | None:
    """Apply a SyncTask to local storage.

    Returns the task ID if applied, None if skipped.
    """
    from hopper.storage.tasks import LocalTask

    # Check if we have this task locally
    existing = task_store.get(sync_task.id)

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
        task_store.save(existing)
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
        )
        task_store.save(new_task)

    return sync_task.id


def sync_with_upstream(
    task_store: "TaskMarkdownStore",
    client: UpstreamClient,
    state_path: Path,
    instance: str = "local",
) -> SyncResult:
    # Per-instance state file so switching instances doesn't skip tasks
    state_path = state_path.parent / f"{state_path.name}_{instance}"
    """Perform a full sync with upstream server.

    1. Load sync state (last sync timestamp)
    2. Collect local tasks modified since last sync
    3. Push to server
    4. Apply server's updates locally
    5. Save new sync state

    Args:
        task_store: Local task storage
        client: Upstream client
        state_path: Path to sync state file

    Returns:
        SyncResult with pushed/pulled/conflict counts
    """
    result = SyncResult()

    # Load sync state
    state = SyncState.load(state_path)

    # Collect local tasks modified since last sync (including soft-deleted)
    all_tasks = task_store.list(include_deleted=True)
    local_changes = []

    for task in all_tasks:
        task_ts = _datetime_to_ms(task.updated_at)
        if task_ts > state.last_sync:
            local_changes.append(_local_task_to_sync_task(task))

    # Sync with server
    try:
        response = client.sync(
            tasks=local_changes,
            since=state.last_server_time,
            instance=instance,
        )
    except Exception as e:
        result.errors.append(str(e))
        return result

    # Record pushed tasks
    result.pushed = response.accepted

    # Record conflicts
    for conflict in response.rejected:
        result.conflicts.append(conflict.task_id)

    # Apply remote changes
    for sync_task in response.tasks:
        task_id = _apply_sync_task_to_local(sync_task, task_store)
        if task_id:
            result.pulled.append(task_id)

    # Update sync state
    state.last_sync = int(time.time() * 1000)
    state.last_server_time = response.server_time
    state.save(state_path)

    return result
