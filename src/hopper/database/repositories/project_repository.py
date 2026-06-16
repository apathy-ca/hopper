"""
Project repository with project-specific queries and operations.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models.project import Project
from hopper.timeutils import utc_now_naive

from .base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    """Repository for Project model with custom queries."""

    def __init__(self, session: Session):
        """Initialize ProjectRepository."""
        super().__init__(Project, session)

    def get_by_slug(self, slug: str) -> Project | None:
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

    def get_by_name(self, name: str) -> Project | None:
        """
        Get a project by its name (primary key).

        Args:
            name: Project name

        Returns:
            Project instance or None if not found
        """
        return self.get(name)

    def get_projects_with_active_tasks(self) -> list[Project]:
        """Get all projects. Task table is dropped; returns all projects."""
        query = select(Project)
        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_projects_by_executor_type(self, executor_type: str) -> list[Project]:
        """
        Get all projects with a specific executor type.

        Args:
            executor_type: Executor type (e.g., "czarina", "human", "sage")

        Returns:
            List of projects with the executor type
        """
        return self.filter(filters={"executor_type": executor_type})

    def get_auto_claim_projects(self) -> list[Project]:
        """
        Get all projects with auto_claim enabled.

        Returns:
            List of projects that auto-claim tasks
        """
        return self.filter(filters={"auto_claim": True})

    def update_last_sync(self, name: str) -> Project | None:
        """
        Update the last_sync timestamp for a project.

        Args:
            name: Project name

        Returns:
            Updated project or None if not found
        """

        return self.update(name, last_sync=utc_now_naive())

    def get_project_task_count(self, name: str) -> int:
        """Task table is dropped; always returns 0."""
        return 0

    def get_project_statistics(self, name: str) -> dict:
        """Task table is dropped; returns zeroed statistics."""
        return {
            "total_tasks": 0,
            "status_counts": {},
            "pending": 0,
            "in_progress": 0,
            "completed": 0,
        }
