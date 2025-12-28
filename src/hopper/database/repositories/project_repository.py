"""
Project repository with project-specific queries and operations.
"""
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models.project import Project
from hopper.models.task import Task
from .base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project model with custom queries."""

    def __init__(self, session: Session):
        """Initialize ProjectRepository."""
        super().__init__(Project, session)

    def get_by_slug(self, slug: str) -> Optional[Project]:
        """
        Get a project by its slug.

        Args:
            slug: Project slug

        Returns:
            Project instance or None if not found
        """
        query = select(Project).where(Project.slug == slug)
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_by_name(self, name: str) -> Optional[Project]:
        """
        Get a project by its name (primary key).

        Args:
            name: Project name

        Returns:
            Project instance or None if not found
        """
        return self.get(name)

    def get_projects_with_active_tasks(self) -> List[Project]:
        """
        Get all projects that have active (non-completed) tasks.

        Returns:
            List of projects with active tasks
        """
        query = (
            select(Project)
            .join(Task, Project.name == Task.project)
            .where(Task.status != "completed")
            .distinct()
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_projects_by_executor_type(self, executor_type: str) -> List[Project]:
        """
        Get all projects with a specific executor type.

        Args:
            executor_type: Executor type (e.g., "czarina", "human", "sage")

        Returns:
            List of projects with the executor type
        """
        return self.filter(filters={"executor_type": executor_type})

    def get_auto_claim_projects(self) -> List[Project]:
        """
        Get all projects with auto_claim enabled.

        Returns:
            List of projects that auto-claim tasks
        """
        return self.filter(filters={"auto_claim": True})

    def update_last_sync(self, name: str) -> Optional[Project]:
        """
        Update the last_sync timestamp for a project.

        Args:
            name: Project name

        Returns:
            Updated project or None if not found
        """
        from datetime import datetime

        return self.update(name, last_sync=datetime.utcnow())

    def get_project_task_count(self, name: str) -> int:
        """
        Get the number of tasks for a project.

        Args:
            name: Project name

        Returns:
            Number of tasks
        """
        from sqlalchemy import func

        query = select(func.count(Task.id)).where(Task.project == name)
        result = self.session.execute(query)
        return result.scalar() or 0

    def get_project_statistics(self, name: str) -> dict:
        """
        Get statistics for a project.

        Args:
            name: Project name

        Returns:
            Dictionary with project statistics
        """
        from sqlalchemy import func

        # Count tasks by status
        query = (
            select(Task.status, func.count(Task.id))
            .where(Task.project == name)
            .group_by(Task.status)
        )
        result = self.session.execute(query)
        status_counts = dict(result.all())

        total_tasks = sum(status_counts.values())

        return {
            "total_tasks": total_tasks,
            "status_counts": status_counts,
            "pending": status_counts.get("pending", 0),
            "in_progress": status_counts.get("in_progress", 0),
            "completed": status_counts.get("completed", 0),
        }
