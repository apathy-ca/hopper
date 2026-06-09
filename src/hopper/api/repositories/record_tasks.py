"""Records-backed task repository for the REST API (Phase 1, additive).

This repository backs task-shaped CRUD with the ``records`` + ``revisions``
model where ``Record.type`` IS the kind. It mirrors the client-side
``TaskSQLiteStore`` patterns (see ``hopper/storage/sqlite_tasks.py``):

  * the authoritative state of a record lives in its current revision's JSON
    ``payload`` — there are no status/priority/tags/project/owner/parent
    columns, so those filters and any sorting happen in Python after reading
    the payload;
  * the kind is read from ``records.type`` (NOT a tag), so kind segmentation
    is a DB-level filter on ``Record.type``.

All methods are SYNC and take an active SQLAlchemy ``Session``. Async routes
bridge to them via ``await db.run_sync(...)``. The repository flushes through
the revision writer but does NOT commit — the caller owns the transaction
boundary (matching ``write_revision``'s contract).

This module is purely additive: no routes or existing behavior depend on it
yet. Later migration phases wire it into ``routes/tasks.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import Record, RecordType, Revision
from hopper.storage.revision_writer import (
    AuthorContext,
    tombstone_revision,
    write_revision,
)

# Fields hydrated onto every task-shaped dict, mirroring LocalTask.to_frontmatter.
_PASSTHROUGH_OPTIONAL = ("subject", "scope", "provenance")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_kind(raw: str | None) -> str:
    """Coerce a raw kind string to a valid RecordType value, defaulting to task."""
    try:
        return RecordType(raw or "task").value
    except ValueError:
        return RecordType.TASK.value


class RecordTaskRepository:
    """Task-shaped CRUD backed by the records+revisions model.

    Methods are SYNC and operate on the ``Session`` passed at construction.
    """

    def __init__(self, session: Session, *, instance_id: str = "local") -> None:
        self._session = session
        self._instance_id = instance_id

    # ------------------------------------------------------------------
    # Hydration
    # ------------------------------------------------------------------

    @staticmethod
    def _hydrate(record: Record, payload: dict[str, Any]) -> dict[str, Any]:
        """Build a task-shaped dict from a Record + its current revision payload.

        ``kind`` always comes from ``records.type`` (the authoritative source),
        never from a tag. Remaining fields come from the JSON payload, with the
        same defaults TaskSQLiteStore applies.
        """
        payload = payload or {}
        tags = payload.get("tags")
        if not isinstance(tags, list):
            tags = []

        hydrated: dict[str, Any] = {
            "id": record.id,
            "kind": record.type,
            "title": payload.get("title"),
            "description": payload.get("description"),
            "status": payload.get("status", "pending"),
            "priority": payload.get("priority", "medium"),
            "tags": tags,
            "project": payload.get("project"),
            "parent_id": payload.get("parent_id"),
            "assigned_to": payload.get("assigned_to"),
            "created_at": payload.get("created_at"),
            "updated_at": payload.get("updated_at"),
        }
        # Pass through memory/structured fields only when present so ordinary
        # tasks stay clean (mirrors to_frontmatter).
        for key in _PASSTHROUGH_OPTIONAL:
            if payload.get(key) is not None:
                hydrated[key] = payload[key]
        return hydrated

    def _current_payload(self, record: Record) -> dict[str, Any] | None:
        """Return the payload of the record's current revision, or None."""
        if record.current_revision_id is None:
            return None
        revision = self._session.get(Revision, record.current_revision_id)
        if revision is None:
            return None
        return dict(revision.payload or {})

    def _author(self, author_did: str, author_location: str) -> AuthorContext:
        return AuthorContext(did=author_did, location=author_location)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    def create(
        self,
        payload: dict[str, Any],
        *,
        author_did: str,
        author_location: str,
    ) -> dict[str, Any]:
        """Create a record via the revision writer, returning a task-shaped dict.

        ``kind`` is taken from ``payload["kind"]`` (default "task") and becomes
        ``records.type``. An ``id`` and ``created_at``/``updated_at`` are
        generated when absent.
        """
        data = dict(payload)
        data["kind"] = _normalize_kind(data.get("kind"))
        if not data.get("id"):
            # Match LocalTask._generate_id — a ULID prefix is the millisecond
            # timestamp and collides for same-tick creates, so use uuid4.
            data["id"] = f"t{uuid4().hex[:8]}"
        now = _utc_now_iso()
        data.setdefault("created_at", now)
        data.setdefault("updated_at", now)
        data.setdefault("status", "pending")
        data.setdefault("priority", "medium")
        if not isinstance(data.get("tags"), list):
            data["tags"] = []

        write_revision(
            self._session,
            data,
            self._author(author_did, author_location),
            instance_id=self._instance_id,
        )
        record = self._session.get(Record, data["id"])
        return self._hydrate(record, data)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, record_id: str) -> dict[str, Any] | None:
        """Hydrate a single record by ID. Returns None if missing or tombstoned."""
        record = self._session.get(Record, record_id)
        if record is None or record.tombstoned_at is not None:
            return None
        payload = self._current_payload(record)
        if payload is None:
            return None
        if payload.get("deleted"):
            return None
        return self._hydrate(record, payload)

    def _hydrated_records(
        self, *, kind: str, all_kinds: bool, include_deleted: bool
    ) -> list[dict[str, Any]]:
        """Load and hydrate all non-tombstoned records for a kind (or all kinds)."""
        stmt = select(Record).where(Record.tombstoned_at.is_(None))
        if not all_kinds:
            stmt = stmt.where(Record.type == kind)
        records = self._session.execute(stmt).scalars().all()

        items: list[dict[str, Any]] = []
        for record in records:
            payload = self._current_payload(record)
            if payload is None:
                continue
            if payload.get("deleted") and not include_deleted:
                continue
            items.append(self._hydrate(record, payload))
        return items

    @staticmethod
    def _apply_filters(
        items: list[dict[str, Any]],
        *,
        status: str | None,
        priority: str | None,
        project: str | None,
        owner: str | None,
        tags: list[str] | None,
        parent_id: str | None,
    ) -> list[dict[str, Any]]:
        """Apply payload-derived filters in Python (mirrors sqlite_tasks.list)."""
        if status:
            items = [t for t in items if t.get("status") == status]
        if priority:
            items = [t for t in items if t.get("priority") == priority]
        if project:
            items = [t for t in items if t.get("project") == project]
        if owner:
            items = [t for t in items if t.get("assigned_to") == owner]
        if parent_id:
            items = [t for t in items if t.get("parent_id") == parent_id]
        if tags:
            required = set(tags)
            items = [t for t in items if required.issubset(set(t.get("tags") or []))]
        return items

    @staticmethod
    def _sort(
        items: list[dict[str, Any]], *, sort_by: str, sort_order: str
    ) -> list[dict[str, Any]]:
        reverse = sort_order.lower() != "asc"
        return sorted(
            items,
            key=lambda t: (t.get(sort_by) is None, t.get(sort_by)),
            reverse=reverse,
        )

    def list(
        self,
        *,
        kind: str = "task",
        all_kinds: bool = False,
        status: str | None = None,
        priority: str | None = None,
        project: str | None = None,
        owner: str | None = None,
        tags: list[str] | None = None,
        parent_id: str | None = None,
        include_deleted: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[dict[str, Any]], int]:
        """List task-shaped records.

        Segments by ``Record.type == kind`` (the kind lives in records.type)
        unless ``all_kinds`` is set. Remaining filters/sort run in Python over
        the hydrated revision payloads. Returns ``(items, total)`` where total
        is the count after filtering but before pagination.
        """
        items = self._hydrated_records(
            kind=kind, all_kinds=all_kinds, include_deleted=include_deleted
        )
        items = self._apply_filters(
            items,
            status=status,
            priority=priority,
            project=project,
            owner=owner,
            tags=tags,
            parent_id=parent_id,
        )
        total = len(items)
        items = self._sort(items, sort_by=sort_by, sort_order=sort_order)
        if skip:
            items = items[skip:]
        if limit is not None:
            items = items[:limit]
        return items, total

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(
        self,
        record_id: str,
        changes: dict[str, Any],
        *,
        author_did: str,
        author_location: str,
    ) -> dict[str, Any] | None:
        """Merge ``changes`` onto the current payload and write a new revision.

        Returns the hydrated result, or None if the record is missing/tombstoned.
        ``id`` and ``kind`` cannot be changed through this path.
        """
        record = self._session.get(Record, record_id)
        if record is None or record.tombstoned_at is not None:
            return None
        payload = self._current_payload(record)
        if payload is None:
            return None

        merged = dict(payload)
        for key, value in changes.items():
            if key in ("id", "kind"):
                continue
            merged[key] = value
        merged["id"] = record_id
        # Preserve the authoritative kind from records.type.
        merged["kind"] = record.type
        merged["updated_at"] = _utc_now_iso()

        write_revision(
            self._session,
            merged,
            self._author(author_did, author_location),
            instance_id=self._instance_id,
        )
        record = self._session.get(Record, record_id)
        return self._hydrate(record, merged)

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def soft_delete(
        self,
        record_id: str,
        *,
        author_did: str,
        author_location: str,
    ) -> bool:
        """Tombstone a record via the revision writer. Idempotent-ish: returns
        False only when the record does not exist or is already tombstoned."""
        record = self._session.get(Record, record_id)
        if record is None or record.tombstoned_at is not None:
            return False
        payload = self._current_payload(record) or {"id": record_id, "kind": record.type}
        payload = dict(payload)
        payload["id"] = record_id
        payload["kind"] = record.type
        payload["deleted"] = True
        tombstone_revision(
            self._session,
            record_id,
            self._author(author_did, author_location),
            payload,
            instance_id=self._instance_id,
        )
        return True

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        """Substring search over title/description/tags (mirrors sqlite_tasks).

        Accepts the same keyword filters as ``list`` (kind, all_kinds, status,
        priority, project, owner, tags, parent_id, include_deleted, sort_by,
        sort_order, skip, limit).
        """
        q = (query or "").lower()
        skip = filters.pop("skip", 0)
        limit = filters.pop("limit", 50)
        sort_by = filters.pop("sort_by", "created_at")
        sort_order = filters.pop("sort_order", "desc")

        kind = filters.pop("kind", "task")
        all_kinds = filters.pop("all_kinds", False)
        include_deleted = filters.pop("include_deleted", False)

        items = self._hydrated_records(
            kind=kind, all_kinds=all_kinds, include_deleted=include_deleted
        )
        items = self._apply_filters(
            items,
            status=filters.pop("status", None),
            priority=filters.pop("priority", None),
            project=filters.pop("project", None),
            owner=filters.pop("owner", None),
            tags=filters.pop("tags", None),
            parent_id=filters.pop("parent_id", None),
        )

        def _matches(t: dict[str, Any]) -> bool:
            title = (t.get("title") or "").lower()
            if q in title:
                return True
            desc = (t.get("description") or "").lower()
            if desc and q in desc:
                return True
            return any(q in (tag or "").lower() for tag in (t.get("tags") or []))

        matched = [t for t in items if _matches(t)]
        total = len(matched)
        matched = self._sort(matched, sort_by=sort_by, sort_order=sort_order)
        if skip:
            matched = matched[skip:]
        if limit is not None:
            matched = matched[:limit]
        return matched, total
