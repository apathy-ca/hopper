"""Local storage client for Hopper CLI.

Provides the same interface as HopperClient but uses local markdown storage.
"""

from pathlib import Path
from typing import Any

from hopper.storage import (
    StorageConfig,
    MarkdownStorage,
    TaskMarkdownStore,
    EpisodeMarkdownStore,
    PatternMarkdownStore,
    FeedbackMarkdownStore,
)
from hopper.storage.tasks import LocalTask
from hopper.storage.memory import LocalPattern, LocalFeedback


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

        # Initialize storage backend
        self.storage = MarkdownStorage(self.config)
        self.storage.initialize()

        # Initialize stores
        self.task_store = TaskMarkdownStore(self.storage)
        self.episode_store = EpisodeMarkdownStore(self.storage)
        self.pattern_store = PatternMarkdownStore(self.storage)
        self.feedback_store = FeedbackMarkdownStore(self.storage)

    def __enter__(self) -> "LocalClient":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        pass  # No cleanup needed for local storage

    def close(self) -> None:
        """Close the client (no-op for local)."""
        pass

    # =========================================================================
    # Task API methods
    # =========================================================================

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new task."""
        task = LocalTask.create(
            title=data.get("title", "Untitled"),
            description=data.get("description"),
            priority=data.get("priority", "medium"),
            tags=data.get("tags", []),
            project=data.get("project_id"),
            status=data.get("status", "pending"),
        )
        self.task_store.save(task)
        return self._task_to_dict(task)

    def list_tasks(self, **params: Any) -> list[dict[str, Any]]:
        """List tasks with optional filters."""
        filters = {}

        if "status" in params:
            filters["status"] = params["status"]
        if "priority" in params:
            filters["priority"] = params["priority"]
        if "project" in params:
            filters["project"] = params["project"]
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
        return [self._task_to_dict(t) for t in tasks]

    def get_task(self, task_id: str) -> dict[str, Any]:
        """Get task by ID."""
        task = self.task_store.get(task_id)
        if task is None:
            raise LocalClientError(f"Task not found: {task_id}")
        return self._task_to_dict(task)

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

        # Handle tags
        if "add_tags" in data:
            for tag in data["add_tags"]:
                if tag not in task.tags:
                    task.tags.append(tag)
        if "remove_tags" in data:
            task.tags = [t for t in task.tags if t not in data["remove_tags"]]
        if "tags" in data:
            task.tags = data["tags"]

        self.task_store.save(task)
        return self._task_to_dict(task)

    def delete_task(self, task_id: str) -> None:
        """Delete task."""
        if not self.task_store.delete(task_id):
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

    def _task_to_dict(self, task: LocalTask) -> dict[str, Any]:
        """Convert LocalTask to API-compatible dict."""
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "tags": task.tags,
            "project_id": task.project,
            "instance": task.instance,
            "source": task.source,
            "depends_on": task.depends_on,
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
            {**self._pattern_to_dict(pattern), "match_score": score}
            for pattern, score in matches
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
        return [{
            "id": "local",
            "name": "Local Hopper",
            "scope": "personal",
            "status": "running",
        }]

    def delegate_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Delegate task (not supported in local mode)."""
        raise LocalClientError("Task delegation not supported in local mode")

    def get_task_delegations(self, task_id: str) -> dict[str, Any]:
        """Get delegations (not supported in local mode)."""
        return {"delegations": [], "current_instance_id": "local"}
