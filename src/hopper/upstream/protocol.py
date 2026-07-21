"""Protocol models for upstream sync.

Defines the wire format for sync requests and responses.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SyncTask(BaseModel):
    """Task representation for sync protocol."""

    id: str
    title: str
    status: str = "pending"
    priority: str | None = "medium"
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    project: str | None = None
    instance: str = "local"
    source: str = "cli"
    depends_on: list[str] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    external_id: str | None = None
    external_url: str | None = None
    external_platform: str | None = None
    context: str | None = None
    requester: str | None = None
    owner: str | None = None
    assigned_to: str | None = None
    last_heartbeat: datetime | None = None
    expected_heartbeat: datetime | None = None
    parent_id: str | None = None
    deleted: bool = False  # Tombstone marker
    # Append-only note stream and immutable creator attribution. Optional so
    # older clients/servers that omit them validate cleanly (Pydantic drops
    # unknown fields, so BOTH ends must carry these for them to survive sync).
    notes: list[dict] = Field(default_factory=list)
    created_by: str | None = None
    created_by_did: str | None = None
    # Record kind/type and structured memory fields. Optional for backward
    # compatibility: older clients/servers that omit them still validate.
    # `kind=None` is treated as "task" by the server's revision_writer
    # (RecordType(None) falls back to TASK), so the record type is preserved
    # for memories while plain tasks are unaffected.
    kind: str | None = None
    subject: str | None = None
    scope: str | None = None
    provenance: str | None = None
    # Consolidation fields — optional, only present on memory records post-consolidation.
    memory_class: str | None = None
    superseded_by: str | None = None
    source_record_ids: list[str] = Field(default_factory=list)
    consolidation_run_id: str | None = None
    consolidated_at: datetime | None = None
    drift_checked_at: datetime | None = None
    drift_score: float | None = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_local_task(cls, task: Any) -> SyncTask:
        """Convert a LocalTask to SyncTask."""
        return cls(
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
            deleted=False,
            notes=getattr(task, "notes", None) or [],
            created_by=getattr(task, "created_by", None),
            created_by_did=getattr(task, "created_by_did", None),
            kind=getattr(task, "kind", None),
            subject=getattr(task, "subject", None),
            scope=getattr(task, "scope", None),
            provenance=getattr(task, "provenance", None),
        )


class SyncRequest(BaseModel):
    """Sync request from client to server."""

    since: int = Field(
        default=0,
        description="Timestamp (ms since epoch) to get updates from",
    )
    tasks: list[SyncTask] = Field(
        default_factory=list,
        description="Tasks to push to server",
    )
    client_time: int = Field(
        description="Client's current time (ms since epoch)",
    )
    instance: str = Field(
        default="local",
        description="Hopper instance name — scopes the pull to this instance only",
    )


class SyncConflict(BaseModel):
    """Information about a sync conflict."""

    task_id: str
    local_updated_at: int
    server_updated_at: int
    resolution: str = "server_wins"  # server_wins | client_wins


class SyncResponse(BaseModel):
    """Sync response from server to client."""

    tasks: list[SyncTask] = Field(
        default_factory=list,
        description="Tasks updated on server since 'since' timestamp",
    )
    server_time: int = Field(
        description="Server's current time (ms since epoch)",
    )
    accepted: list[str] = Field(
        default_factory=list,
        description="Task IDs that were accepted from client",
    )
    rejected: list[SyncConflict] = Field(
        default_factory=list,
        description="Tasks that were rejected due to conflicts",
    )


def datetime_to_ms(dt: datetime | None) -> int:
    """Convert datetime to milliseconds since epoch."""
    if dt is None:
        return 0
    return int(dt.timestamp() * 1000)


def ms_to_datetime(ms: int) -> datetime | None:
    """Convert milliseconds since epoch to UTC-aware datetime."""
    if ms == 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=UTC)
