"""
SQLite-backed task store for Hopper.

Implements the same interface as TaskMarkdownStore so it can drop in as a
replacement when storage.type == 'sqlite' in config.yaml.

The store reads/writes the ``tasks`` table via SQLAlchemy ORM.  It does NOT
touch the ``records``/``revisions`` tables — that layer (Phase 4a shadow
writer, Phase 4b DID attribution) is orthogonal and can be composed on top.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from hopper.models.task import Task
from hopper.storage.tasks import LocalTask, _utc_now
from hopper.storage.revision_writer import AuthorContext, write_revision, tombstone_revision

logger = logging.getLogger(__name__)


def _orm_to_local(row: Task) -> LocalTask:
    """Convert a Task ORM row to a LocalTask dataclass."""

    def _dt(v: Any) -> datetime | None:
        if v is None:
            return None
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        # Stored as string (shouldn't happen with ORM, but guard anyway)
        dt = datetime.fromisoformat(str(v))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    tags = row.tags
    if isinstance(tags, str):
        try:
            tags = json.loads(tags)
        except Exception:
            tags = []
    if not isinstance(tags, list):
        tags = []

    depends_on = row.depends_on
    if isinstance(depends_on, str):
        try:
            depends_on = json.loads(depends_on)
        except Exception:
            depends_on = []
    if not isinstance(depends_on, list):
        depends_on = []

    # kind is stored in records.type, not in the tasks table directly.
    # Default to "task"; full kind round-trip happens via the revision payload.
    kind = "task"

    return LocalTask(
        id=row.id,
        title=row.title,
        status=row.status,
        priority=row.priority,
        description=row.description,
        tags=tags,
        project=row.project,
        instance=row.instance_id or "local",
        source=row.source or "cli",
        depends_on=depends_on,
        created_at=_dt(row.created_at),
        updated_at=_dt(row.updated_at),
        external_id=row.external_id,
        external_url=row.external_url,
        external_platform=row.external_platform,
        context=row.context,
        requester=row.requester,
        owner=row.owner,
        assigned_to=row.assigned_to,
        last_heartbeat=_dt(row.last_heartbeat),
        expected_heartbeat=_dt(row.expected_heartbeat),
        parent_id=row.parent_id,
        deleted=bool(row.deleted),
        kind=kind,
    )


def _local_to_orm(task: LocalTask, existing: Task | None = None) -> Task:
    """Convert a LocalTask to a Task ORM object (create or update existing)."""
    row = existing or Task()
    row.id = task.id
    row.title = task.title
    row.status = task.status
    row.priority = task.priority or "medium"
    row.description = task.description
    row.tags = task.tags or []
    row.project = task.project
    # instance_id is a FK to hopper_instances; only set it when the value
    # looks like an actual DB row ID (not the bare hopper dir name like '.hopper').
    # Treat 'local' and bare dot-prefixed names as unmapped — leave NULL.
    inst = task.instance
    row.instance_id = inst if (inst and inst not in ("local",) and not inst.startswith(".")) else None
    row.source = task.source
    row.depends_on = task.depends_on or []
    row.created_at = task.created_at
    row.updated_at = task.updated_at
    row.external_id = task.external_id
    row.external_url = task.external_url
    row.external_platform = task.external_platform
    row.context = task.context
    row.requester = task.requester
    row.owner = task.owner
    row.assigned_to = task.assigned_to
    row.last_heartbeat = task.last_heartbeat
    row.expected_heartbeat = task.expected_heartbeat
    row.parent_id = task.parent_id
    row.deleted = task.deleted
    return row


class TaskSQLiteStore:
    """Task storage backed by SQLite via SQLAlchemy ORM.

    Mirrors the public API of TaskMarkdownStore so LocalClient can swap
    backends transparently.
    """

    def __init__(self, storage: "SQLiteStorage"):  # noqa: F821
        """Initialise with a SQLiteStorage backend (owns the engine)."""
        self._storage = storage

    # ------------------------------------------------------------------
    # ID resolution
    # ------------------------------------------------------------------

    def resolve_id(self, task_id: str) -> str | None:
        """Resolve a possibly-truncated task ID.

        Tries exact match first, then prefix LIKE match.  Returns None when
        the result is ambiguous (multiple matches).
        """
        with self._storage.session() as session:
            # Exact match
            row = session.get(Task, task_id)
            if row is not None:
                return row.id

            # Prefix match
            stmt = (
                select(Task.id)
                .where(Task.id.like(f"{task_id}%"))
                .where(Task.deleted.is_(False))
                .limit(2)
            )
            results = session.execute(stmt).scalars().all()
            if len(results) == 1:
                return results[0]
            return None  # 0 = not found, 2+ = ambiguous

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def get(self, task_id: str, include_deleted: bool = False) -> LocalTask | None:
        """Fetch a task by ID (prefix match supported)."""
        resolved = self.resolve_id(task_id)
        if resolved is None:
            return None
        with self._storage.session() as session:
            row = session.get(Task, resolved)
            if row is None:
                return None
            if row.deleted and not include_deleted:
                return None
            return _orm_to_local(row)

    def create(self, task: LocalTask, author: AuthorContext | None = None) -> None:
        """Insert a new task, retrying with fresh ID on collision.

        If author is provided (and the backend is SQLite with revisions), a
        Record + Revision row is written in the same transaction.
        """
        with self._storage.session() as session:
            attempts = 0
            while attempts < 5:
                existing = session.get(Task, task.id)
                if existing is None:
                    break
                task.id = LocalTask._generate_id()
                attempts += 1
            row = _local_to_orm(task)
            session.add(row)
            if author is not None:
                session.flush()  # flush so FK on Record.id is satisfiable
                write_revision(session, task.to_frontmatter(), author,
                               instance_id=task.instance or "local")
            session.commit()

    def save(self, task: LocalTask, author: AuthorContext | None = None) -> None:
        """Upsert a task (create or update).

        If author is provided, a Revision row is appended in the same transaction.
        """
        task.updated_at = _utc_now()
        with self._storage.session() as session:
            existing = session.get(Task, task.id)
            row = _local_to_orm(task, existing)
            session.merge(row)
            if author is not None:
                session.flush()
                write_revision(session, task.to_frontmatter(), author,
                               instance_id=task.instance or "local")
            session.commit()

    def delete(self, task_id: str, author: AuthorContext | None = None) -> bool:
        """Hard-delete a task row. Returns True if deleted."""
        resolved = self.resolve_id(task_id)
        if resolved is None:
            return False
        with self._storage.session() as session:
            row = session.get(Task, resolved)
            if row is None:
                return False
            if author is not None:
                task = _orm_to_local(row)
                tombstone_revision(session, resolved, author, task.to_frontmatter(),
                                   instance_id=task.instance or "local")
            session.delete(row)
            session.commit()
            return True

    def mark_deleted(self, task_id: str, author: AuthorContext | None = None) -> bool:
        """Soft-delete (sets deleted=True). Idempotent."""
        task = self.get(task_id, include_deleted=True)
        if task is None:
            return False
        if task.deleted:
            return True
        task.deleted = True
        self.save(task, author=author)
        return True

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def list(self, **filters: Any) -> list[LocalTask]:
        """List tasks with optional keyword filters.

        Supported filters: status, priority, tags (list), project,
        limit (int), include_deleted (bool).
        """
        include_deleted = filters.pop("include_deleted", False)
        limit = filters.pop("limit", None)

        with self._storage.session() as session:
            stmt = select(Task)

            if not include_deleted:
                stmt = stmt.where(Task.deleted.is_(False))

            if "status" in filters and filters["status"]:
                stmt = stmt.where(Task.status == filters["status"])

            if "priority" in filters and filters["priority"]:
                stmt = stmt.where(Task.priority == filters["priority"])

            if "project" in filters and filters["project"]:
                stmt = stmt.where(Task.project == filters["project"])

            stmt = stmt.order_by(Task.updated_at.desc())

            rows = session.execute(stmt).scalars().all()
            tasks = [_orm_to_local(r) for r in rows]

        # Tag filtering — SQLite JSON is stored as text; do it in Python
        if "tags" in filters and filters["tags"]:
            required = set(filters["tags"])
            tasks = [t for t in tasks if required.issubset(set(t.tags))]

        if limit:
            tasks = tasks[:limit]

        return tasks

    def search(self, query: str, **filters: Any) -> list[LocalTask]:
        """Full-text search across title, description, and tags."""
        q = query.lower()
        include_deleted = filters.pop("include_deleted", False)
        limit = filters.pop("limit", None)

        with self._storage.session() as session:
            stmt = select(Task)
            if not include_deleted:
                stmt = stmt.where(Task.deleted.is_(False))

            # DB-level filter on title / description for speed
            stmt = stmt.where(
                or_(
                    Task.title.ilike(f"%{q}%"),
                    Task.description.ilike(f"%{q}%"),
                )
            )

            # Apply column-level filters
            if "status" in filters and filters["status"]:
                stmt = stmt.where(Task.status == filters["status"])
            if "priority" in filters and filters["priority"]:
                stmt = stmt.where(Task.priority == filters["priority"])
            if "project" in filters and filters["project"]:
                stmt = stmt.where(Task.project == filters["project"])

            rows = session.execute(stmt).scalars().all()
            tasks = [_orm_to_local(r) for r in rows]

        # Python-side: also match tags, catch any title/desc misses
        results = []
        for task in tasks:
            if self._matches_query(task, q):
                results.append(task)

        if limit:
            results = results[:limit]

        return results

    def _matches_query(self, task: LocalTask, query_lower: str) -> bool:
        if query_lower in task.title.lower():
            return True
        if task.description and query_lower in task.description.lower():
            return True
        if any(query_lower in tag.lower() for tag in task.tags):
            return True
        return False

    def count(self, **filters: Any) -> int:
        return len(self.list(**filters))

    # ------------------------------------------------------------------
    # Convenience helpers (mirrors TaskMarkdownStore)
    # ------------------------------------------------------------------

    def get_children(self, parent_id: str) -> list[LocalTask]:
        """Return all direct children of a task."""
        resolved = self.resolve_id(parent_id)
        if resolved is None:
            return []
        with self._storage.session() as session:
            stmt = (
                select(Task)
                .where(Task.parent_id == resolved)
                .where(Task.deleted.is_(False))
            )
            rows = session.execute(stmt).scalars().all()
            return [_orm_to_local(r) for r in rows]

    def get_by_status(self, status: str) -> list[LocalTask]:
        return self.list(status=status)

    def get_by_tag(self, tag: str) -> list[LocalTask]:
        return self.list(tags=[tag])

    def get_by_project(self, project: str) -> list[LocalTask]:
        return self.list(project=project)

    def update_status(self, task_id: str, status: str,
                      author: AuthorContext | None = None) -> LocalTask | None:
        task = self.get(task_id)
        if task is None:
            return None
        task.status = status
        self.save(task, author=author)
        return task

    def add_tags(self, task_id: str, tags: list[str],
                 author: AuthorContext | None = None) -> LocalTask | None:
        task = self.get(task_id)
        if task is None:
            return None
        for tag in tags:
            if tag not in task.tags:
                task.tags.append(tag)
        self.save(task, author=author)
        return task

    def remove_tags(self, task_id: str, tags: list[str],
                    author: AuthorContext | None = None) -> LocalTask | None:
        task = self.get(task_id)
        if task is None:
            return None
        task.tags = [t for t in task.tags if t not in tags]
        self.save(task, author=author)
        return task
