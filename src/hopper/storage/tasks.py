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

    @classmethod
    def create(
        cls,
        title: str,
        description: str | None = None,
        priority: str = "medium",
        tags: list[str] | None = None,
        project: str | None = None,
        status: str = "pending",
    ) -> "LocalTask":
        """Create a new task with generated ID."""
        return cls(
            id=f"task-{uuid4().hex[:8]}",
            title=title,
            description=description,
            priority=priority,
            tags=tags or [],
            project=project,
            status=status,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

    def to_frontmatter(self) -> dict[str, Any]:
        """Convert to frontmatter dict."""
        return {
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
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else created,
            updated_at=datetime.fromisoformat(updated) if isinstance(updated, str) else updated,
        )


class TaskMarkdownStore:
    """Task storage using markdown files."""

    def __init__(self, storage: MarkdownStorage):
        """Initialize task store."""
        self.storage = storage

    def _task_path(self, task_id: str) -> Path:
        """Get path for a task file."""
        return self.storage.tasks_path / f"{task_id}.md"

    def get(self, task_id: str) -> LocalTask | None:
        """Get task by ID."""
        doc = self.storage.read_document(self._task_path(task_id))
        if doc is None:
            return None
        return LocalTask.from_frontmatter(doc.frontmatter, doc.content)

    def save(self, task: LocalTask) -> None:
        """Save task to markdown file."""
        task.updated_at = _utc_now()

        doc = MarkdownDocument(
            frontmatter=task.to_frontmatter(),
            content=task.description or "",
        )

        file_path = self._task_path(task.id)
        self.storage.write_document(file_path, doc)
        self.storage.update_index(task.id, doc.frontmatter, file_path)

    def delete(self, task_id: str) -> bool:
        """Delete task. Returns True if deleted."""
        file_path = self._task_path(task_id)
        if self.storage.delete_file(file_path):
            self.storage._remove_from_index(task_id)
            self.storage._save_index()
            return True
        return False

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

        # Load matching tasks
        tasks = []
        for task_id in task_ids:
            task = self.get(task_id)
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
