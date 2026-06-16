"""Local storage client for Hopper CLI.

Provides the same interface as HopperClient but uses local markdown storage.
"""

from pathlib import Path
from typing import Any

from hopper.storage import (
    EpisodeMarkdownStore,
    EpisodeSQLiteStore,
    FeedbackMarkdownStore,
    FeedbackSQLiteStore,
    MarkdownStorage,
    PatternMarkdownStore,
    PatternSQLiteStore,
    SQLiteStorage,
    StorageConfig,
    TaskMarkdownStore,
    TaskSQLiteStore,
)
from hopper.storage.memory import LocalFeedback, LocalPattern
from hopper.storage.revision_writer import AuthorContext
from hopper.storage.tasks import LocalTask


def _read_storage_type(storage_path: Path) -> str:
    """Read storage.type from config.yaml in the hopper directory.

    Returns 'sqlite' or 'markdown' (default).
    """
    config_file = storage_path / "config.yaml"
    if not config_file.exists():
        return "markdown"
    try:
        import yaml

        with open(config_file) as f:
            data = yaml.safe_load(f) or {}
        return data.get("storage", {}).get("type", "markdown")
    except Exception:
        return "markdown"


class LocalClientError(Exception):
    """Local client error."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class LocalClient:
    """Local storage client for Hopper.

    Provides the same API as HopperClient but uses local markdown files.
    """

    def __init__(self, storage_path: Path | None = None):
        """Initialize the local client.

        Args:
            storage_path: Path to storage directory. Defaults to ~/.hopper
        """
        if storage_path is None:
            storage_path = Path.home() / ".hopper"

        self.storage_path = storage_path
        self.config = StorageConfig.local(storage_path)

        storage_type = _read_storage_type(storage_path)

        if storage_type == "sqlite":
            # SQLite backend — task store is SQL; episode/pattern delegate to
            # markdown files until their SQL tables are built (Phase 4c+).
            sqlite_storage = SQLiteStorage(self.config)
            sqlite_storage.initialize()
            self.storage = sqlite_storage  # type: ignore[assignment]
            self.task_store = TaskSQLiteStore(sqlite_storage)
            # Episode and pattern stores still need a MarkdownStorage for now
            _md_storage = MarkdownStorage(self.config)
            _md_storage.initialize()
            self.episode_store = EpisodeSQLiteStore(_md_storage)
            self.pattern_store = PatternSQLiteStore(_md_storage)
            self.feedback_store = FeedbackSQLiteStore(sqlite_storage)
        else:
            # Default: markdown backend
            self.storage = MarkdownStorage(self.config)
            self.storage.initialize()
            self.task_store = TaskMarkdownStore(self.storage)
            self.episode_store = EpisodeMarkdownStore(self.storage)
            self.pattern_store = PatternMarkdownStore(self.storage)
            self.feedback_store = FeedbackMarkdownStore(self.storage)

    def __enter__(self) -> "LocalClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close the client, releasing any DB connections."""
        if isinstance(self.storage, SQLiteStorage):
            self.storage.dispose()

    def _author_context(
        self,
        author_did: str | None = None,
        author_location: str | None = None,
    ) -> AuthorContext | None:
        """Build an AuthorContext for revision tracking.

        Returns None when not on the SQLite backend (markdown doesn't record
        revisions) or when identity cannot be resolved.

        Identity resolution order for DID:
          1. Explicit author_did arg (from CLI --author-did / MCP field)
          2. HOPPER_DID env var
          3. Local did.key file at config.path/did.key (or ~/.hopper/did.key)

        Location resolution: delegates to resolve_location().
        """
        if not isinstance(self.storage, SQLiteStorage):
            return None  # markdown backend — no revisions

        import os

        from hopper.location import resolve_location

        # --- DID resolution ---
        did = author_did or os.getenv("HOPPER_DID")
        if not did and self.storage_path:
            key_path = self.storage_path / "did.key"
            if key_path.exists():
                try:
                    from hopper.upstream.did import DIDKey

                    did = DIDKey.load(key_path).did
                except Exception:
                    pass
        if not did:
            raise LocalClientError(
                "No DID available. Agents must supply --author-did or HOPPER_DID. Humans should 'hopper init'."
            )

        # --- Location resolution ---
        location = resolve_location(override=author_location)

        return AuthorContext(did=did, location=location)

    # =========================================================================
    # Task API methods
    # =========================================================================

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new task."""
        # Resolve parent prefix if provided
        parent_id = data.get("parent_id")
        if parent_id:
            resolved = self.task_store.resolve_id(parent_id)
            if resolved is None:
                raise LocalClientError(f"Parent task not found: {parent_id}")
            parent_id = resolved

        from hopper.location import resolve_location

        location = data.get("source") or resolve_location(transport="cli")
        task = LocalTask.create(
            title=data.get("title", "Untitled"),
            description=data.get("description"),
            priority=data.get("priority", "medium"),
            tags=data.get("tags", []),
            project=data.get("project_id"),
            status=data.get("status", "pending"),
            assigned_to=data.get("assigned_to"),
            parent_id=parent_id,
            source=location,
            kind=data.get("kind", "task"),
            subject=data.get("subject"),
            scope=data.get("scope"),
            provenance=data.get("provenance"),
            memory_class=data.get("memory_class"),
            superseded_by=data.get("superseded_by"),
            source_record_ids=data.get("source_record_ids") or [],
            consolidation_run_id=data.get("consolidation_run_id"),
            consolidated_at=data.get("consolidated_at"),
            drift_checked_at=data.get("drift_checked_at"),
            drift_score=data.get("drift_score"),
        )
        task.instance = self.config.instance_id
        author = self._author_context(
            author_did=data.get("author_did"),
            author_location=location,
        )
        self.task_store.create(task, author=author)
        return self._task_to_dict(task)

    # Sort ranks: lower number = higher in the list
    _STATUS_RANK = {
        "in_progress": 0,
        "blocked": 1,
        "open": 2,
        "completed": 3,
        "done": 3,
        "cancelled": 4,
    }
    _PRIORITY_RANK = {
        "urgent": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
    }

    def list_tasks(self, **params: Any) -> list[dict[str, Any]]:
        """List tasks with optional filters."""
        filters = {}

        if "status" in params:
            filters["status"] = params["status"]
        if "priority" in params:
            filters["priority"] = params["priority"]
        if "project" in params:
            filters["project"] = params["project"]
        if "kind" in params and params["kind"]:
            filters["kind"] = params["kind"]
        if "memory_class" in params and params["memory_class"]:
            filters["memory_class"] = params["memory_class"]
        if "tags" in params:
            # Handle comma-separated tags
            tags = params["tags"]
            if isinstance(tags, str):
                filters["tags"] = [t.strip() for t in tags.split(",")]
            else:
                filters["tags"] = tags
        if "limit" in params:
            filters["limit"] = params["limit"]

        tasks = self.task_store.list(**filters)
        result = [self._task_to_dict(t) for t in tasks]

        # Compute staleness ratio for in_progress tasks
        # 0.0 = just heartbeated, 1.0 = stale threshold reached, >1.0 = overdue
        from datetime import datetime as dt
        from datetime import timedelta

        from hopper.storage.tasks import _utc_now

        now = _utc_now()
        default_window = timedelta(minutes=30)
        for t in result:
            if t.get("status") == "in_progress" and t.get("assigned_to"):
                expected = t.get("expected_heartbeat")
                heartbeat = t.get("last_heartbeat")
                hb_dt = (
                    (dt.fromisoformat(heartbeat) if isinstance(heartbeat, str) else heartbeat)
                    if heartbeat
                    else None
                )

                if expected:
                    exp_dt = dt.fromisoformat(expected) if isinstance(expected, str) else expected
                    if hb_dt and exp_dt:
                        window = exp_dt - hb_dt
                        elapsed = now - hb_dt
                        t["stale_ratio"] = (elapsed / window) if window.total_seconds() > 0 else 1.0
                    else:
                        t["stale_ratio"] = 1.0
                elif hb_dt:
                    elapsed = now - hb_dt
                    t["stale_ratio"] = elapsed / default_window
                else:
                    t["stale_ratio"] = 1.0

                t["stale"] = t["stale_ratio"] >= 1.0

        # Compute rollup for parent tasks
        child_map: dict[str, list[dict[str, Any]]] = {}
        for t in result:
            pid = t.get("parent_id")
            if pid:
                child_map.setdefault(pid, []).append(t)

        for t in result:
            tid = t["id"]
            if tid in child_map:
                children = child_map[tid]
                status_counts: dict[str, int] = {}
                for c in children:
                    status_counts[c["status"]] = status_counts.get(c["status"], 0) + 1
                done = status_counts.get("completed", 0) + status_counts.get("done", 0)
                t["children"] = {
                    "total": len(children),
                    "done": done,
                    "by_status": status_counts,
                }

        # Default sort: status rank, then priority rank
        sort_by = params.get("sort_by", "status")
        if sort_by == "status":
            result.sort(
                key=lambda t: (
                    self._STATUS_RANK.get(t.get("status", ""), 99),
                    self._PRIORITY_RANK.get(t.get("priority", ""), 99),
                )
            )

        # Group children directly after their parent
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for t in result:
            if t["id"] in seen:
                continue
            if t.get("parent_id") and t.get("parent_id") not in seen:
                # Skip children for now — they'll be placed after their parent
                continue
            ordered.append(t)
            seen.add(t["id"])
            # Insert children immediately after parent
            if t["id"] in child_map:
                for child in child_map[t["id"]]:
                    if child["id"] not in seen:
                        ordered.append(child)
                        seen.add(child["id"])

        # Append any orphaned children (parent filtered out or missing)
        for t in result:
            if t["id"] not in seen:
                ordered.append(t)

        return ordered

    def create_task_with_brief(self, data: dict[str, Any], brief: str) -> dict[str, Any]:
        """Create a task whose body is a full markdown brief.

        Identical to create_task but stores the brief as the task description
        (which maps to the markdown body in local storage). Use this when the
        worker's full instruction document needs to live in hopper rather than
        just a one-liner description.

        Args:
            data: Task metadata (title, priority, tags, etc.)
            brief: Full markdown content to store as the task body

        Returns:
            Created task as dict
        """
        from hopper.location import resolve_location

        location = data.get("source") or resolve_location(transport="cli")
        task = LocalTask.create(
            title=data.get("title", "Untitled"),
            description=brief,
            priority=data.get("priority", "medium"),
            tags=data.get("tags", []),
            project=data.get("project_id"),
            status=data.get("status", "open"),
            source=location,
        )
        task.instance = self.config.instance_id
        author = self._author_context(
            author_did=data.get("author_did"),
            author_location=location,
        )
        self.task_store.create(task, author=author)
        return self._task_to_dict(task)

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Get task by ID."""
        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")
        return self._task_to_dict(task)

    def get_task_with_lessons(
        self, task_id: str, project_slug: str | None = None
    ) -> dict[str, Any]:
        """Get a task with relevant lessons appended to its description.

        Queries the lesson store for lessons matching the task's project and
        tags, and appends a '## Relevant Lessons' section to the description
        if any high-confidence lessons are found.

        Args:
            task_id: Task ID to retrieve
            project_slug: Project slug to filter lessons by (uses task tags if not provided)

        Returns:
            Task dict with description augmented by relevant lessons
        """
        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")

        result = self._task_to_dict(task)

        # Query lesson store for relevant lessons (lesson_store wired up by lessons plan)
        lesson_store = getattr(self, "lesson_store", None)
        lessons: list[dict[str, Any]] = []

        if lesson_store is not None:
            lessons = lesson_store.list(project_slug=project_slug, confidence="high")

            # Fallback: match by role tag domain if no project_slug provided
            if not lessons and not project_slug and task.tags:
                domain_tags = [t for t in task.tags if t.startswith("role-")]
                if domain_tags:
                    domain = domain_tags[0].removeprefix("role-")
                    lessons = lesson_store.list(domain=domain, confidence="high")

        if lessons:
            lesson_section = "\n\n---\n## Relevant Lessons\n\n"
            lesson_section += "_These lessons were filed by previous workers on this project._\n\n"
            for lesson in lessons:
                lesson_section += f"### {lesson.get('title', 'Lesson')}"
                if lesson.get("domain"):
                    lesson_section += f" `{lesson['domain']}`"
                lesson_section += "\n"
                if lesson.get("body"):
                    lesson_section += lesson["body"] + "\n\n"
            result["description"] = (result.get("description") or "") + lesson_section

        return result

    def update_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update task."""
        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")

        # Update fields
        if "title" in data:
            task.title = data["title"]
        if "description" in data:
            task.description = data["description"]
        if "priority" in data:
            task.priority = data["priority"]
        if "status" in data:
            task.status = data["status"]
        if "project_id" in data:
            task.project = data["project_id"]
        if "kind" in data:
            task.kind = data["kind"]
        if "subject" in data:
            task.subject = data["subject"]
        if "scope" in data:
            task.scope = data["scope"]
        if "provenance" in data:
            task.provenance = data["provenance"]
        if "memory_class" in data:
            task.memory_class = data["memory_class"]
        if "superseded_by" in data:
            task.superseded_by = data["superseded_by"]
        if "source_record_ids" in data:
            task.source_record_ids = data["source_record_ids"] or []
        if "consolidation_run_id" in data:
            task.consolidation_run_id = data["consolidation_run_id"]
        if "consolidated_at" in data:
            task.consolidated_at = data["consolidated_at"]
        if "drift_checked_at" in data:
            task.drift_checked_at = data["drift_checked_at"]
        if "drift_score" in data:
            task.drift_score = data["drift_score"]

        # Handle tags
        if "add_tags" in data:
            for tag in data["add_tags"]:
                if tag not in task.tags:
                    task.tags.append(tag)
        if "remove_tags" in data:
            task.tags = [t for t in task.tags if t not in data["remove_tags"]]
        if "tags" in data:
            task.tags = data["tags"]

        # Handle assignment
        if "assigned_to" in data:
            task.assigned_to = data["assigned_to"]
            if task.assigned_to:
                from hopper.storage.tasks import _utc_now

                task.last_heartbeat = _utc_now()
            else:
                task.last_heartbeat = None

        # Handle parent
        if "parent_id" in data:
            parent_id = data["parent_id"]
            if parent_id:
                resolved = self.task_store.resolve_id(parent_id)
                if resolved is None:
                    raise LocalClientError(f"Parent task not found: {parent_id}")
                task.parent_id = resolved
            else:
                task.parent_id = None

        author = self._author_context(
            author_did=data.get("author_did"),
            author_location=data.get("author_location"),
        )
        self.task_store.save(task, author=author)
        return self._task_to_dict(task)

    def delete_task(self, task_id: str, author_did: str | None = None) -> None:
        """Soft-delete task so the deletion propagates via sync."""
        author = self._author_context(author_did=author_did)
        if not self.task_store.mark_deleted(task_id, author=author):
            raise LocalClientError(f"Task not found: {task_id}")

    def search_tasks(self, query: str, **params: Any) -> list[dict[str, Any]]:
        """Search tasks."""
        filters = {}
        if "status" in params:
            filters["status"] = params["status"]
        if "priority" in params:
            filters["priority"] = params["priority"]
        if "project" in params:
            filters["project"] = params["project"]
        if "limit" in params:
            filters["limit"] = params["limit"]

        tasks = self.task_store.search(query, **filters)
        return [self._task_to_dict(t) for t in tasks]

    def heartbeat_task(self, task_id: str, expect_minutes: int | None = None) -> dict[str, Any]:
        """Update the heartbeat timestamp for a task.

        Called by agents to signal they are still alive and working on a task.

        Args:
            task_id: Task to heartbeat
            expect_minutes: If set, the next heartbeat is expected in this many
                minutes. Use for long-running processes (GPU jobs, data generation)
                so the stale detector doesn't flag the task prematurely.
        """
        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")

        from datetime import timedelta

        from hopper.storage.tasks import _utc_now

        now = _utc_now()
        task.last_heartbeat = now
        if expect_minutes:
            task.expected_heartbeat = now + timedelta(minutes=expect_minutes)
        else:
            task.expected_heartbeat = None
        author = self._author_context()
        self.task_store.save(task, author=author)
        return self._task_to_dict(task)

    def list_stale_tasks(self, minutes: int = 30) -> list[dict[str, Any]]:
        """List in_progress tasks whose agent has gone silent.

        A task is stale when:
        - It has an assigned agent, AND
        - If expected_heartbeat is set: now > expected_heartbeat
        - If no expected_heartbeat: last_heartbeat is older than `minutes` threshold

        This means an agent that says "back in 4 hours" won't be flagged at 30 min.

        Args:
            minutes: Default minutes without heartbeat to consider stale
                (only used when no expected_heartbeat is set).
        """
        from datetime import timedelta

        from hopper.storage.tasks import _utc_now

        now = _utc_now()
        default_cutoff = now - timedelta(minutes=minutes)
        in_progress = self.task_store.list(status="in_progress")
        stale = []
        for task in in_progress:
            if not task.assigned_to:
                continue
            if task.expected_heartbeat:
                # Agent said when to expect them — use that
                if now > task.expected_heartbeat:
                    stale.append(task)
            elif task.last_heartbeat is None or task.last_heartbeat < default_cutoff:
                # No expectation set — use default threshold
                stale.append(task)
        return [self._task_to_dict(t) for t in stale]

    def propose_task_update(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Submit a proposed update to a task without applying it immediately.

        The task's current state is unchanged.  The proposal appears in
        ``list_pending_revisions()`` and must be applied or rejected
        explicitly (or matched by an auto-apply rule).

        Only available on the SQLite backend.
        """
        if not isinstance(self.storage, SQLiteStorage):
            raise LocalClientError("Proposals require SQLite backend (storage.type: sqlite)")

        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")

        # Build the proposed payload (apply proposed fields to a copy)
        import copy

        proposed = copy.copy(task)
        if "title" in data:
            proposed.title = data["title"]
        if "description" in data:
            proposed.description = data["description"]
        if "priority" in data:
            proposed.priority = data["priority"]
        if "status" in data:
            proposed.status = data["status"]
        if "tags" in data:
            proposed.tags = data["tags"]
        if "add_tags" in data:
            for t in data["add_tags"]:
                if t not in proposed.tags:
                    proposed.tags.append(t)
        if "remove_tags" in data:
            proposed.tags = [t for t in proposed.tags if t not in data["remove_tags"]]

        author = self._author_context(
            author_did=data.get("author_did"),
            author_location=data.get("author_location"),
        )
        if author is None:
            raise LocalClientError("Proposals require author identity (SQLite backend)")

        from hopper.storage.revision_writer import propose_revision

        with self.storage.session() as session:
            rev_id = propose_revision(
                session, proposed.to_frontmatter(), author, instance_id=task.instance or "local"
            )
            session.commit()

        return {"revision_id": rev_id, "task_id": task_id, "status": "proposed"}

    def list_pending_revisions(
        self, record_id: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List all pending (propose) revisions awaiting apply/reject.

        Only available on the SQLite backend.
        """
        if not isinstance(self.storage, SQLiteStorage):
            return []

        from sqlalchemy import exists, not_, select
        from sqlalchemy.orm import aliased

        from hopper.models import Revision

        with self.storage.session() as session:
            # A proposal is "pending" only when no subsequent apply/reject
            # revision exists that references it via parent_revision_id.
            Followup = aliased(Revision)
            pending_filter = not_(
                exists(
                    select(Followup.id).where(
                        Followup.parent_revision_id == Revision.id,
                        Followup.action.in_(["apply", "reject"]),
                    )
                )
            )

            stmt = (
                select(Revision)
                .where(Revision.action == "propose")
                .where(pending_filter)
                .order_by(Revision.created_at.desc())
                .limit(limit)
            )
            if record_id:
                resolved = self.task_store.resolve_id(record_id)
                stmt = stmt.where(Revision.record_id == (resolved or record_id))
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "record_id": r.record_id,
                    "action": r.action,
                    "author_did": r.author_did,
                    "author_location": r.author_location,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    def apply_revision(self, revision_id: str, author_did: str | None = None) -> dict[str, Any]:
        """Apply a pending proposal revision.

        Only available on the SQLite backend.
        """
        if not isinstance(self.storage, SQLiteStorage):
            raise LocalClientError("apply_revision requires SQLite backend")

        author = self._author_context(author_did=author_did)
        if author is None:
            raise LocalClientError("apply_revision requires author identity")

        from hopper.storage.revision_writer import apply_revision as _apply

        with self.storage.session() as session:
            apply_rev_id = _apply(session, revision_id, author)
            session.commit()
        return {"applied_revision_id": apply_rev_id, "proposal_id": revision_id}

    def reject_revision(
        self, revision_id: str, reason: str | None = None, author_did: str | None = None
    ) -> dict[str, Any]:
        """Reject a pending proposal revision.

        Only available on the SQLite backend.
        """
        if not isinstance(self.storage, SQLiteStorage):
            raise LocalClientError("reject_revision requires SQLite backend")

        author = self._author_context(author_did=author_did)
        if author is None:
            raise LocalClientError("reject_revision requires author identity")

        from hopper.storage.revision_writer import reject_revision as _reject

        with self.storage.session() as session:
            reject_rev_id = _reject(session, revision_id, author, reason=reason)
            session.commit()
        return {"rejected_revision_id": reject_rev_id, "proposal_id": revision_id}

    def get_task_history(self, task_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Return revision history for a task, oldest-first.

        Only meaningful on the SQLite backend — returns empty list on markdown.
        """
        if not isinstance(self.storage, SQLiteStorage):
            return []

        resolved = self.task_store.resolve_id(task_id)
        if resolved is None:
            raise LocalClientError(f"Task not found: {task_id}")

        from sqlalchemy import select

        from hopper.models import Revision

        with self.storage.session() as session:
            stmt = (
                select(Revision)
                .where(Revision.record_id == resolved)
                .order_by(Revision.created_at.asc())
                .limit(limit)
            )
            rows = session.execute(stmt).scalars().all()
            return [
                {
                    "id": r.id,
                    "action": r.action,
                    "author_did": r.author_did,
                    "author_location": r.author_location,
                    "schema_version": r.schema_version,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    def get_task_children(self, task_id: str) -> list[dict[str, Any]]:
        """Get children of a task with rollup summary."""
        children = self.task_store.get_children(task_id)
        return [self._task_to_dict(t) for t in children]

    def get_task_with_rollup(self, task_id: str) -> dict[str, Any]:
        """Get a task with child status rollup."""
        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")

        result = self._task_to_dict(task)
        children = self.task_store.get_children(task_id)

        if children:
            status_counts: dict[str, int] = {}
            for child in children:
                status_counts[child.status] = status_counts.get(child.status, 0) + 1
            done = status_counts.get("completed", 0) + status_counts.get("done", 0)
            result["children"] = {
                "total": len(children),
                "done": done,
                "by_status": status_counts,
            }
        return result

    def _task_to_dict(self, task: LocalTask) -> dict[str, Any]:
        """Convert LocalTask to API-compatible dict."""
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "tags": task.tags,
            "kind": task.kind,
            "subject": task.subject,
            "scope": task.scope,
            "provenance": task.provenance,
            "memory_class": task.memory_class,
            "superseded_by": task.superseded_by,
            "source_record_ids": task.source_record_ids,
            "consolidation_run_id": task.consolidation_run_id,
            "consolidated_at": task.consolidated_at.isoformat() if task.consolidated_at else None,
            "drift_checked_at": (
                task.drift_checked_at.isoformat() if task.drift_checked_at else None
            ),
            "drift_score": task.drift_score,
            "project_id": task.project,
            "instance": task.instance,
            "source": task.source,
            "depends_on": task.depends_on,
            "parent_id": task.parent_id,
            "assigned_to": task.assigned_to,
            "last_heartbeat": task.last_heartbeat.isoformat() if task.last_heartbeat else None,
            "expected_heartbeat": (
                task.expected_heartbeat.isoformat() if task.expected_heartbeat else None
            ),
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }

    # =========================================================================
    # Learning API methods
    # =========================================================================

    def submit_feedback(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Submit feedback for a task's routing decision."""
        feedback = self.feedback_store.save(
            task_id=task_id,
            was_good_match=data.get("was_good_match", True),
            routing_feedback=data.get("routing_feedback"),
            should_have_routed_to=data.get("should_have_routed_to"),
            quality_score=data.get("quality_score"),
            complexity_rating=data.get("complexity_rating"),
            required_rework=data.get("required_rework"),
            notes=data.get("notes"),
        )
        return self._feedback_to_dict(feedback)

    def get_task_feedback(self, task_id: str) -> dict[str, Any]:
        """Get feedback for a specific task."""
        feedback = self.feedback_store.get(task_id)
        if feedback is None:
            raise LocalClientError(f"No feedback found for task: {task_id}")
        return self._feedback_to_dict(feedback)

    def list_feedback(self, **params: Any) -> dict[str, Any]:
        """List feedback records."""
        good_only = params.get("good_only")
        limit = params.get("limit", 100)

        records = self.feedback_store.list(good_only=good_only, limit=limit)
        return {
            "feedback": [self._feedback_to_dict(f) for f in records],
            "total": len(records),
        }

    def get_routing_accuracy(self, days: int = 30) -> dict[str, Any]:
        """Get routing accuracy statistics."""
        return self.feedback_store.get_accuracy_stats(days=days)

    def _feedback_to_dict(self, feedback: LocalFeedback) -> dict[str, Any]:
        """Convert LocalFeedback to API-compatible dict."""
        return {
            "id": feedback.id,
            "task_id": feedback.task_id,
            "was_good_match": feedback.was_good_match,
            "routing_feedback": feedback.routing_feedback,
            "should_have_routed_to": feedback.should_have_routed_to,
            "quality_score": feedback.quality_score,
            "complexity_rating": feedback.complexity_rating,
            "required_rework": feedback.required_rework,
            "notes": feedback.notes,
            "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        }

    # =========================================================================
    # Pattern API methods
    # =========================================================================

    def create_pattern(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a routing pattern."""
        # Build tag and text criteria from various input formats
        tag_criteria = data.get("tag_criteria", {})
        text_criteria = data.get("text_criteria", {})

        # Handle match_tags format (from local client API)
        if "match_tags" in data:
            tag_criteria["required"] = data["match_tags"]
        if "match_keywords" in data:
            text_criteria["keywords"] = data["match_keywords"]

        pattern = LocalPattern.create(
            name=data.get("name", ""),
            description=data.get("description"),
            pattern_type=data.get("pattern_type", "tag"),
            tag_criteria=tag_criteria if tag_criteria else None,
            text_criteria=text_criteria if text_criteria else None,
            priority_criteria=data.get("priority_criteria") or data.get("match_priority"),
            target_instance=data.get("target_instance", "local"),
            confidence=data.get("confidence", 0.8),
        )
        self.pattern_store.save(pattern)
        return self._pattern_to_dict(pattern)

    def list_patterns(self, **params: Any) -> dict[str, Any]:
        """List routing patterns."""
        active_only = params.get("active_only", True)
        patterns = self.pattern_store.list(active_only=active_only)
        return {
            "patterns": [self._pattern_to_dict(p) for p in patterns],
            "total": len(patterns),
        }

    def get_pattern(self, pattern_id: str) -> dict[str, Any]:
        """Get pattern by ID."""
        pattern = self.pattern_store.get(pattern_id)
        if pattern is None:
            raise LocalClientError(f"Pattern not found: {pattern_id}")
        return self._pattern_to_dict(pattern)

    def update_pattern(self, pattern_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update pattern."""
        pattern = self.pattern_store.get(pattern_id)
        if pattern is None:
            raise LocalClientError(f"Pattern not found: {pattern_id}")

        # Update fields
        if "name" in data:
            pattern.name = data["name"]
        if "description" in data:
            pattern.description = data["description"]
        if "pattern_type" in data:
            pattern.pattern_type = data["pattern_type"]
        if "tag_criteria" in data:
            pattern.tag_criteria = data["tag_criteria"]
        if "text_criteria" in data:
            pattern.text_criteria = data["text_criteria"]
        if "priority_criteria" in data:
            pattern.priority_criteria = data["priority_criteria"]
        if "target_instance" in data:
            pattern.target_instance = data["target_instance"]
        if "confidence" in data:
            pattern.confidence = data["confidence"]
        if "is_active" in data:
            pattern.is_active = data["is_active"]

        self.pattern_store.save(pattern)
        return self._pattern_to_dict(pattern)

    def delete_pattern(self, pattern_id: str) -> None:
        """Delete pattern."""
        if not self.pattern_store.delete(pattern_id):
            raise LocalClientError(f"Pattern not found: {pattern_id}")

    def match_patterns(self, **params: Any) -> list[dict[str, Any]]:
        """Find patterns matching criteria."""
        matches = self.pattern_store.find_matching(
            tags=params.get("tags"),
            text=params.get("text"),
            priority=params.get("priority"),
        )
        return [
            {**self._pattern_to_dict(pattern), "match_score": score} for pattern, score in matches
        ]

    def _pattern_to_dict(self, pattern: LocalPattern) -> dict[str, Any]:
        """Convert LocalPattern to API-compatible dict."""
        return {
            "id": pattern.id,
            "name": pattern.name,
            "description": pattern.description,
            "pattern_type": pattern.pattern_type,
            "tag_criteria": pattern.tag_criteria,
            "text_criteria": pattern.text_criteria,
            "priority_criteria": pattern.priority_criteria,
            "target_instance": pattern.target_instance,
            "confidence": pattern.confidence,
            "is_active": pattern.is_active,
            "usage_count": pattern.usage_count,
            "success_count": pattern.success_count,
            "failure_count": pattern.failure_count,
            "success_rate": pattern.success_rate,
            "created_at": pattern.created_at.isoformat() if pattern.created_at else None,
            "last_used_at": pattern.last_used_at.isoformat() if pattern.last_used_at else None,
        }

    # =========================================================================
    # Statistics and consolidation
    # =========================================================================

    def get_learning_statistics(self) -> dict[str, Any]:
        """Get overall learning statistics."""
        episode_stats = self.episode_store.get_statistics()
        pattern_stats = {
            "total_patterns": len(self.pattern_store.list(active_only=False)),
            "active_patterns": len(self.pattern_store.list(active_only=True)),
        }
        feedback_stats = self.feedback_store.get_accuracy_stats(days=30)

        return {
            "episodes": episode_stats,
            "patterns": pattern_stats,
            "feedback": feedback_stats,
        }

    def run_consolidation(self, days: int = 7) -> dict[str, Any]:
        """Run pattern consolidation (placeholder for local mode)."""
        # In local mode, consolidation is simpler - just report stats
        # Real consolidation would analyze episodes and suggest patterns
        return {
            "patterns_created": 0,
            "patterns_updated": 0,
            "patterns_deactivated": 0,
            "message": "Local consolidation complete",
        }

    # =========================================================================
    # Project and Instance stubs (limited in local mode)
    # =========================================================================

    def list_projects(self, **params: Any) -> list[dict[str, Any]]:
        """List projects (returns empty in local mode)."""
        return []

    def list_instances(self, **params: Any) -> list[dict[str, Any]]:
        """List instances (returns local instance only)."""
        return [
            {
                "id": "local",
                "name": "Local Hopper",
                "scope": "personal",
                "status": "running",
            }
        ]

    def delegate_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Delegate task (not supported in local mode)."""
        raise LocalClientError("Task delegation not supported in local mode")

    def get_task_delegations(self, task_id: str) -> dict[str, Any]:
        """Get delegations (not supported in local mode)."""
        return {"delegations": [], "current_instance_id": "local"}
