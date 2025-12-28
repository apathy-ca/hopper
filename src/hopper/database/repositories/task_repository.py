"""
Task repository with task-specific queries and operations.
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from hopper.models.task import Task
from .base import BaseRepository


class TaskRepository(BaseRepository[Task]):
    """Repository for Task model with custom queries."""

    def __init__(self, session: Session):
        """Initialize TaskRepository."""
        super().__init__(Task, session)

    def get_tasks_by_project(
        self, project_id: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all tasks for a specific project.

        Args:
            project_id: Project identifier
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of tasks for the project
        """
        return self.filter(filters={"project": project_id}, skip=skip, limit=limit)

    def get_tasks_by_status(
        self, status: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all tasks with a specific status.

        Args:
            status: Task status (e.g., "pending", "in_progress", "completed")
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of tasks with the given status
        """
        return self.filter(filters={"status": status}, skip=skip, limit=limit)

    def get_tasks_by_tag(
        self, tag: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all tasks with a specific tag.

        Args:
            tag: Tag to search for
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of tasks with the tag
        """
        # This is a simplified version - actual implementation would need
        # to query the JSONB/JSON tags field properly
        query = select(Task)

        # For SQLite, we'd need different logic than PostgreSQL
        # This is a basic implementation that works with both
        query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        result = self.session.execute(query)
        tasks = list(result.scalars().all())

        # Filter in Python (not ideal for large datasets)
        # In production, use database-specific JSON queries
        return [
            task
            for task in tasks
            if task.tags and tag in (task.tags if isinstance(task.tags, list) else [])
        ]

    def search_tasks(
        self, query: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Search tasks by title or description.

        Args:
            query: Search query string
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of tasks matching the query
        """
        stmt = select(Task).where(
            or_(
                Task.title.ilike(f"%{query}%"),
                Task.description.ilike(f"%{query}%") if Task.description else False,
            )
        )

        stmt = stmt.offset(skip)
        if limit:
            stmt = stmt.limit(limit)

        result = self.session.execute(stmt)
        return list(result.scalars().all())

    def update_status(self, task_id: str, status: str) -> Optional[Task]:
        """
        Update task status.

        Args:
            task_id: Task identifier
            status: New status

        Returns:
            Updated task or None if not found
        """
        return self.update(task_id, status=status)

    def get_tasks_by_requester(
        self, requester: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all tasks created by a specific requester.

        Args:
            requester: Requester identifier
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of tasks from the requester
        """
        return self.filter(filters={"requester": requester}, skip=skip, limit=limit)

    def get_tasks_by_owner(
        self, owner: str, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all tasks assigned to a specific owner.

        Args:
            owner: Owner identifier
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of tasks assigned to the owner
        """
        return self.filter(filters={"owner": owner}, skip=skip, limit=limit)

    def get_pending_tasks(
        self, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all pending tasks.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of pending tasks
        """
        return self.get_tasks_by_status("pending", skip=skip, limit=limit)

    def get_unassigned_tasks(
        self, skip: int = 0, limit: Optional[int] = None
    ) -> List[Task]:
        """
        Get all tasks without an assigned project.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of unassigned tasks
        """
        query = select(Task).where(Task.project.is_(None))

        query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def assign_to_project(self, task_id: str, project: str) -> Optional[Task]:
        """
        Assign a task to a project.

        Args:
            task_id: Task identifier
            project: Project name

        Returns:
            Updated task or None if not found
        """
        return self.update(task_id, project=project)
