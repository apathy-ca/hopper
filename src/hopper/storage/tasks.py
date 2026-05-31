"""
Task storage implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse a datetime value, ensuring it is UTC-aware.

    Naive ISO strings (no timezone suffix) are assumed to be UTC, matching
    the storage convention used by _utc_now().
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

from .base import TaskStore
from .markdown import MarkdownDocument, MarkdownStorage


@dataclass
class LocalTask:
    """Task representation for local storage."""

    id: str
    title: str
    status: str = "pending"
    priority: str | None = "medium"
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    project: str | None = None
    instance: str = "local"
    source: str = "cli"
    depends_on: list[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # External platform integration
    external_id: str | None = None
    external_url: str | None = None
    external_platform: str | None = None
    context: str | None = None
    requester: str | None = None
    owner: str | None = None
    # Agent/user identity tracking
    assigned_to: str | None = None
    last_heartbeat: datetime | None = None
    expected_heartbeat: datetime | None = None
    # Parent-child hierarchy
    parent_id: str | None = None
    # Soft delete — propagated via sync
    deleted: bool = False
    # Record kind (Phase 4c): task | idea | note | memory | log | reference | inbox | job
    kind: str = "task"
    # Memory structured fields (Phase 2): first-class on memory records,
    # serialized to frontmatter only when present so ordinary tasks stay clean.
    subject: str | None = None
    scope: str | None = None
    provenance: str | None = None

    @classmethod
    def _generate_id(cls) -> str:
        """Generate a unique task ID, retrying on collision."""
        return f"t{uuid4().hex[:8]}"

    @classmethod
    def create(
        cls,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        tags: list[str] | None = None,
        project: str | None = None,
        status: str = "pending",
        source: str = "cli",
        external_id: str | None = None,
        external_url: str | None = None,
        external_platform: str | None = None,
        context: str | None = None,
        requester: str | None = None,
        owner: str | None = None,
        assigned_to: str | None = None,
        expected_heartbeat: datetime | None = None,
        parent_id: str | None = None,
        kind: str = "task",
        subject: str | None = None,
        scope: str | None = None,
        provenance: str | None = None,
        **kwargs: Any,  # Accept and ignore unknown fields
    ) -> "LocalTask":
        """Create a new task with generated ID."""
        now = _utc_now()
        return cls(
            id=cls._generate_id(),
            title=title,
            description=description,
            priority=priority,
            tags=tags or [],
            project=project,
            status=status,
            source=source,
            external_id=external_id,
            external_url=external_url,
            external_platform=external_platform,
            context=context,
            requester=requester,
            owner=owner,
            assigned_to=assigned_to,
            last_heartbeat=now if assigned_to else None,
            expected_heartbeat=expected_heartbeat,
            parent_id=parent_id,
            created_at=now,
            updated_at=now,
            kind=kind,
            subject=subject,
            scope=scope,
            provenance=provenance,
        )

    def to_frontmatter(self) -> dict[str, Any]:
        """Convert to frontmatter dict."""
        data = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "priority": self.priority,
            "tags": self.tags,
            "project": self.project,
            "instance": self.instance,
            "source": self.source,
            "depends_on": self.depends_on if self.depends_on else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        # Add external fields if present
        if self.external_id:
            data["external_id"] = self.external_id
        if self.external_url:
            data["external_url"] = self.external_url
        if self.external_platform:
            data["external_platform"] = self.external_platform
        if self.context:
            data["context"] = self.context
        if self.requester:
            data["requester"] = self.requester
        if self.owner:
            data["owner"] = self.owner
        if self.assigned_to:
            data["assigned_to"] = self.assigned_to
        if self.last_heartbeat:
            data["last_heartbeat"] = self.last_heartbeat.isoformat()
        if self.expected_heartbeat:
            data["expected_heartbeat"] = self.expected_heartbeat.isoformat()
        if self.parent_id:
            data["parent_id"] = self.parent_id
        if self.deleted:
            data["deleted"] = True
        if self.kind and self.kind != "task":
            data["kind"] = self.kind
        # Memory structured fields — only written when present, so ordinary
        # task files stay clean.
        if self.subject:
            data["subject"] = self.subject
        if self.scope:
            data["scope"] = self.scope
        if self.provenance:
            data["provenance"] = self.provenance
        return data

    @classmethod
    def from_frontmatter(cls, fm: dict[str, Any], content: str = "") -> "LocalTask":
        """Create from frontmatter dict."""
        created = fm.get("created_at")
        updated = fm.get("updated_at")

        return cls(
            id=fm["id"],
            title=fm.get("title", "Untitled"),
            status=fm.get("status", "pending"),
            priority=fm.get("priority"),
            description=content if content else None,
            tags=fm.get("tags", []),
            project=fm.get("project"),
            instance=fm.get("instance", "local"),
            source=fm.get("source", "cli"),
            depends_on=fm.get("depends_on", []),
            created_at=_parse_datetime(created),
            updated_at=_parse_datetime(updated),
            external_id=fm.get("external_id"),
            external_url=fm.get("external_url"),
            external_platform=fm.get("external_platform"),
            context=fm.get("context"),
            requester=fm.get("requester"),
            owner=fm.get("owner"),
            assigned_to=fm.get("assigned_to"),
            last_heartbeat=_parse_datetime(fm.get("last_heartbeat")),
            expected_heartbeat=_parse_datetime(fm.get("expected_heartbeat")),
            parent_id=fm.get("parent_id"),
            deleted=bool(fm.get("deleted", False)),
            kind=fm.get("kind", "task"),
            subject=fm.get("subject"),
            scope=fm.get("scope"),
            provenance=fm.get("provenance"),
        )


class TaskMarkdownStore:
    """Task storage using markdown files."""

    def __init__(self, storage: MarkdownStorage):
        """Initialize task store."""
        self.storage = storage

    def _task_path(self, task_id: str) -> Path:
        """Get path for a task file."""
        return self.storage.tasks_path / f"{task_id}.md"

    def resolve_id(self, task_id: str) -> str | None:
        """Resolve a possibly-truncated task ID to a full ID.

        Tries exact match first, then prefix match. Returns None if no match
        or if the prefix is ambiguous (matches multiple tasks).
        """
        # Exact match
        if self._task_path(task_id).exists():
            return task_id

        # Prefix match against index
        index = self.storage.get_index()
        all_ids = list(index.get("tasks", {}).keys())
        matches = [tid for tid in all_ids if tid.startswith(task_id)]

        # Also check filesystem for tasks not yet indexed
        if not matches:
            matches = [
                f.stem for f in self.storage.tasks_path.glob(f"{task_id}*.md")
            ]

        if len(matches) == 1:
            return matches[0]
        return None  # 0 or ambiguous

    def get(self, task_id: str, include_deleted: bool = False) -> LocalTask | None:
        """Get task by ID (accepts prefix matches).

        Soft-deleted tasks are hidden by default. Pass include_deleted=True to
        see tombstones (used by sync and by mark_deleted for idempotency).
        """
        resolved = self.resolve_id(task_id)
        if resolved is None:
            return None
        doc = self.storage.read_document(self._task_path(resolved))
        if doc is None:
            return None
        task = LocalTask.from_frontmatter(doc.frontmatter, doc.content)
        if task.deleted and not include_deleted:
            return None
        return task

    def create(self, task: LocalTask, **kwargs: Any) -> None:
        """Save a new task, regenerating ID on collision.

        kwargs are accepted and ignored for interface compatibility with
        TaskSQLiteStore (which accepts author= for revision tracking).
        """
        file_path = self._task_path(task.id)
        attempts = 0
        while file_path.exists() and attempts < 5:
            task.id = LocalTask._generate_id()
            file_path = self._task_path(task.id)
            attempts += 1
        self.save(task)

    def save(self, task: LocalTask, preserve_timestamp: bool = False, **kwargs: Any) -> None:
        """Save task to markdown file (create or update).

        Args:
            task: Task to save.
            preserve_timestamp: If True, keep the task's existing updated_at instead of
                stamping now. Used by sync when applying remote tasks so pulled tasks
                don't appear locally-modified on the next sync round.
        """
        if not preserve_timestamp:
            task.updated_at = _utc_now()

        doc = MarkdownDocument(
            frontmatter=task.to_frontmatter(),
            content=task.description or "",
        )

        file_path = self._task_path(task.id)
        self.storage.write_document(file_path, doc)
        self.storage.update_index(task.id, doc.frontmatter, file_path)

    def delete(self, task_id: str, **kwargs: Any) -> bool:
        """Hard-delete task file. Used when applying a remote deletion. Returns True if deleted."""
        resolved = self.resolve_id(task_id)
        if resolved is None:
            return False
        file_path = self._task_path(resolved)
        if self.storage.delete_file(file_path):
            self.storage._remove_from_index(resolved)
            self.storage._save_index()
            return True
        return False

    def mark_deleted(self, task_id: str, **kwargs: Any) -> bool:
        """Soft-delete task (sets deleted=True, saves). Syncs the deletion to other instances.

        Idempotent — re-marking an already-deleted task is a no-op and still returns True.
        """
        task = self.get(task_id, include_deleted=True)
        if task is None:
            return False
        if task.deleted:
            return True
        task.deleted = True
        self.save(task)
        return True

    def list(self, **filters: Any) -> list[LocalTask]:
        """List tasks with optional filters."""
        index = self.storage.get_index()
        task_ids = set(index.get("tasks", {}).keys())

        # Filter by status
        if "status" in filters and filters["status"]:
            status_tasks = set(index.get("by_status", {}).get(filters["status"], []))
            task_ids &= status_tasks

        # Filter by priority
        if "priority" in filters and filters["priority"]:
            task_ids = {
                tid
                for tid in task_ids
                if index["tasks"].get(tid, {}).get("priority") == filters["priority"]
            }

        # Filter by tags (all must match)
        if "tags" in filters and filters["tags"]:
            for tag in filters["tags"]:
                tag_tasks = set(index.get("by_tag", {}).get(tag, []))
                task_ids &= tag_tasks

        # Filter by project
        if "project" in filters and filters["project"]:
            project_tasks = set(index.get("by_project", {}).get(filters["project"], []))
            task_ids &= project_tasks

        # Filter by kind. Intersect on the by_kind bucket when present; tolerate
        # older on-disk indexes that predate it by deriving kind per task (the
        # main index stores kind; missing => "task").
        if "kind" in filters and filters["kind"]:
            wanted = filters["kind"]
            by_kind = index.get("by_kind")
            if by_kind is not None:
                kind_tasks = set(by_kind.get(wanted, []))
                task_ids &= kind_tasks
            else:
                tasks_meta = index.get("tasks", {})
                task_ids = {
                    tid for tid in task_ids
                    if tasks_meta.get(tid, {}).get("kind", "task") == wanted
                }

        include_deleted = filters.pop("include_deleted", False)

        # Load matching tasks (exclude soft-deleted unless include_deleted)
        tasks = []
        for task_id in task_ids:
            task = self.get(task_id, include_deleted=include_deleted)
            if task:
                tasks.append(task)

        # Sort by updated_at descending
        tasks.sort(key=lambda t: t.updated_at or datetime.min, reverse=True)

        # Apply limit
        if "limit" in filters and filters["limit"]:
            tasks = tasks[: filters["limit"]]

        return tasks

    def search(self, query: str, **filters: Any) -> list[LocalTask]:
        """Search tasks by text query."""
        query_lower = query.lower()
        results = []

        # First filter by index
        candidates = self.list(**filters) if filters else None

        if candidates is not None:
            # Search within filtered set
            for task in candidates:
                if self._matches_query(task, query_lower):
                    results.append(task)
        else:
            # Full scan
            for task_file in self.storage.list_files(self.storage.tasks_path):
                doc = self.storage.read_document(task_file)
                if doc is None:
                    continue

                # Check title and content
                title = doc.frontmatter.get("title", "").lower()
                content = doc.content.lower()

                if query_lower in title or query_lower in content:
                    task = LocalTask.from_frontmatter(doc.frontmatter, doc.content)
                    results.append(task)

        return results

    def _matches_query(self, task: LocalTask, query_lower: str) -> bool:
        """Check if task matches search query."""
        if query_lower in task.title.lower():
            return True
        if task.description and query_lower in task.description.lower():
            return True
        if any(query_lower in tag.lower() for tag in task.tags):
            return True
        return False

    def count(self, **filters: Any) -> int:
        """Count tasks matching filters."""
        return len(self.list(**filters))

    def list_since(self, since_ms: int, include_deleted: bool = False) -> list[LocalTask]:
        """List tasks updated since a timestamp (ms since epoch).

        Uses the index to filter by timestamp before loading from disk,
        avoiding full table scans for incremental sync operations.
        """
        index = self.storage.get_index()
        tasks_index = index.get("tasks", {})

        # Filter task IDs by updated_at in index
        matching_ids = []
        for task_id, task_meta in tasks_index.items():
            updated_at_str = task_meta.get("updated_at")
            if not updated_at_str:
                # No timestamp in index, include it to be safe
                matching_ids.append(task_id)
                continue

            # Parse ISO timestamp to ms
            updated_dt = _parse_datetime(updated_at_str)
            if updated_dt is None:
                matching_ids.append(task_id)
                continue

            updated_ms = int(updated_dt.timestamp() * 1000)
            if updated_ms > since_ms:
                matching_ids.append(task_id)

        # Load only matching tasks
        tasks = []
        for task_id in matching_ids:
            task = self.get(task_id, include_deleted=include_deleted)
            if task:
                tasks.append(task)

        return tasks

    def get_children(self, parent_id: str) -> list[LocalTask]:
        """Get all direct children of a task."""
        # Resolve prefix
        resolved = self.resolve_id(parent_id)
        if resolved is None:
            return []
        all_tasks = self.list()
        return [t for t in all_tasks if t.parent_id == resolved]

    def get_by_status(self, status: str) -> list[LocalTask]:
        """Get tasks by status."""
        return self.list(status=status)

    def get_by_tag(self, tag: str) -> list[LocalTask]:
        """Get tasks by tag."""
        return self.list(tags=[tag])

    def get_by_project(self, project: str) -> list[LocalTask]:
        """Get tasks by project."""
        return self.list(project=project)

    def update_status(self, task_id: str, status: str) -> LocalTask | None:
        """Update task status."""
        task = self.get(task_id)
        if task is None:
            return None

        task.status = status
        self.save(task)
        return task

    def add_tags(self, task_id: str, tags: list[str]) -> LocalTask | None:
        """Add tags to task."""
        task = self.get(task_id)
        if task is None:
            return None

        for tag in tags:
            if tag not in task.tags:
                task.tags.append(tag)

        self.save(task)
        return task

    def remove_tags(self, task_id: str, tags: list[str]) -> LocalTask | None:
        """Remove tags from task."""
        task = self.get(task_id)
        if task is None:
            return None

        task.tags = [t for t in task.tags if t not in tags]
        self.save(task)
        return task


# Type alias for protocol compliance
TaskStore = TaskMarkdownStore
