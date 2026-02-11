"""
Task searcher for finding similar tasks in the database.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import Task, TaskStatus

from .similarity import TaskSimilarity, SimilarityResult

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Result from task search."""

    task_id: str
    title: str
    project: str | None
    tags: dict[str, Any]
    similarity_score: float
    text_score: float
    tag_score: float
    instance_id: str | None = None
    status: str | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "title": self.title,
            "project": self.project,
            "tags": self.tags,
            "similarity_score": self.similarity_score,
            "text_score": self.text_score,
            "tag_score": self.tag_score,
            "instance_id": self.instance_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class TaskSearcher:
    """
    Search for similar tasks using TF-IDF similarity.

    Loads tasks from database and indexes them for similarity search.
    """

    def __init__(
        self,
        session: Session,
        text_weight: float = 0.6,
        tag_weight: float = 0.4,
        max_corpus_size: int = 10000,
        corpus_max_age_days: int = 90,
    ):
        """
        Initialize task searcher.

        Args:
            session: Database session
            text_weight: Weight for text similarity
            tag_weight: Weight for tag similarity
            max_corpus_size: Maximum corpus size
            corpus_max_age_days: Only index tasks from this many days ago
        """
        self.session = session
        self.max_corpus_size = max_corpus_size
        self.corpus_max_age_days = corpus_max_age_days

        self._similarity = TaskSimilarity(
            text_weight=text_weight,
            tag_weight=tag_weight,
        )

        # Cache for task metadata
        self._task_cache: dict[str, dict[str, Any]] = {}
        self._indexed = False

    def index_tasks(
        self,
        force: bool = False,
        status_filter: list[TaskStatus] | None = None,
    ) -> int:
        """
        Index tasks from database.

        Args:
            force: Force re-indexing
            status_filter: Only index tasks with these statuses

        Returns:
            Number of tasks indexed
        """
        if self._indexed and not force:
            return self._similarity.get_corpus_size()

        # Clear existing index
        self._similarity.clear()
        self._task_cache.clear()

        # Build query
        query = select(Task).order_by(Task.created_at.desc())

        # Apply status filter
        if status_filter:
            query = query.where(Task.status.in_(status_filter))

        # Apply age filter
        if self.corpus_max_age_days > 0:
            cutoff = datetime.utcnow() - timedelta(days=self.corpus_max_age_days)
            query = query.where(Task.created_at >= cutoff)

        # Limit size
        query = query.limit(self.max_corpus_size)

        result = self.session.execute(query)
        tasks = result.scalars().all()

        # Index each task
        for task in tasks:
            text = f"{task.title or ''} {task.description or ''}"
            tags = task.tags or {}

            self._similarity.add_document(
                task_id=task.id,
                text=text,
                tags=tags,
            )

            # Cache metadata
            self._task_cache[task.id] = {
                "title": task.title,
                "project": task.project,
                "tags": tags,
                "instance_id": task.instance_id,
                "status": task.status.value if hasattr(task.status, "value") else str(task.status),
                "created_at": task.created_at,
            }

        self._indexed = True
        count = self._similarity.get_corpus_size()

        logger.info(f"Indexed {count} tasks for similarity search")

        return count

    def search(
        self,
        text: str,
        tags: list[str] | dict[str, Any] | None = None,
        limit: int = 10,
        min_score: float = 0.1,
        exclude_ids: set[str] | None = None,
        status_filter: list[TaskStatus] | None = None,
    ) -> list[SearchResult]:
        """
        Search for similar tasks.

        Args:
            text: Query text (title/description)
            tags: Query tags
            limit: Maximum results
            min_score: Minimum similarity score
            exclude_ids: Task IDs to exclude
            status_filter: Only return tasks with these statuses

        Returns:
            List of search results
        """
        # Ensure indexed
        if not self._indexed:
            self.index_tasks()

        # Find similar
        similar = self._similarity.find_similar(
            text=text,
            tags=tags,
            limit=limit * 2,  # Get extra for filtering
            min_score=min_score,
            exclude_ids=exclude_ids,
        )

        # Convert to SearchResults with metadata
        results = []
        for sim in similar:
            meta = self._task_cache.get(sim.task_id)
            if not meta:
                continue

            # Apply status filter
            if status_filter:
                task_status = meta.get("status")
                status_values = [s.value if hasattr(s, "value") else str(s) for s in status_filter]
                if task_status not in status_values:
                    continue

            results.append(
                SearchResult(
                    task_id=sim.task_id,
                    title=meta.get("title", ""),
                    project=meta.get("project"),
                    tags=meta.get("tags", {}),
                    similarity_score=sim.score,
                    text_score=sim.text_score,
                    tag_score=sim.tag_score,
                    instance_id=meta.get("instance_id"),
                    status=meta.get("status"),
                    created_at=meta.get("created_at"),
                )
            )

            if len(results) >= limit:
                break

        return results

    def search_by_task(
        self,
        task: Task,
        limit: int = 10,
        min_score: float = 0.1,
        exclude_self: bool = True,
    ) -> list[SearchResult]:
        """
        Search for tasks similar to a given task.

        Args:
            task: Task to find similar to
            limit: Maximum results
            min_score: Minimum similarity score
            exclude_self: Exclude the task itself

        Returns:
            List of search results
        """
        text = f"{task.title or ''} {task.description or ''}"
        tags = task.tags or {}

        exclude_ids = {task.id} if exclude_self else None

        return self.search(
            text=text,
            tags=tags,
            limit=limit,
            min_score=min_score,
            exclude_ids=exclude_ids,
        )

    def add_task(self, task: Task) -> None:
        """
        Add a single task to the index.

        Args:
            task: Task to add
        """
        text = f"{task.title or ''} {task.description or ''}"
        tags = task.tags or {}

        self._similarity.add_document(
            task_id=task.id,
            text=text,
            tags=tags,
        )

        self._task_cache[task.id] = {
            "title": task.title,
            "project": task.project,
            "tags": tags,
            "instance_id": task.instance_id,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "created_at": task.created_at,
        }

    def remove_task(self, task_id: str) -> bool:
        """
        Remove a task from the index.

        Args:
            task_id: Task ID to remove

        Returns:
            True if removed
        """
        self._task_cache.pop(task_id, None)
        return self._similarity.remove_document(task_id)

    def get_index_size(self) -> int:
        """Get number of indexed tasks."""
        return self._similarity.get_corpus_size()

    def clear_index(self) -> None:
        """Clear the index."""
        self._similarity.clear()
        self._task_cache.clear()
        self._indexed = False

    def get_statistics(self) -> dict[str, Any]:
        """Get searcher statistics."""
        return {
            "indexed": self._indexed,
            "corpus_size": self._similarity.get_corpus_size(),
            "max_corpus_size": self.max_corpus_size,
            "corpus_max_age_days": self.corpus_max_age_days,
            "text_weight": self._similarity.text_weight,
            "tag_weight": self._similarity.tag_weight,
            "unique_terms": len(self._similarity._doc_freq),
        }
