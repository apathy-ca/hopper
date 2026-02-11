"""
Global scope behavior implementation.

Global instances are strategic routers that delegate all tasks to appropriate
Project instances. They never execute tasks directly.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, InstanceStatus, Task, TaskStatus

from .base import BaseScopeBehavior, TaskAction

logger = logging.getLogger(__name__)


class GlobalScopeBehavior(BaseScopeBehavior):
    """
    Behavior for GLOBAL scope instances.

    Global instances act as strategic routers:
    - Route tasks to appropriate PROJECT instances
    - Never execute tasks directly
    - Can create new PROJECT instances if configured
    - Balance load across projects
    """

    def __init__(self, session: Session):
        """
        Initialize the behavior.

        Args:
            session: Database session for queries
        """
        self.session = session

    @property
    def scope_name(self) -> str:
        return "GLOBAL"

    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> TaskAction:
        """
        Global instances always delegate - they route, don't execute.

        Routing strategy:
        1. Check explicit project assignment
        2. Match task tags to project capabilities
        3. Match task content to project domains
        4. Fall back to load balancing
        """
        # Find best project for this task
        target = await self.find_delegation_target(task, instance)

        if target:
            return TaskAction.delegate(
                target_instance_id=target.id,
                reason=f"Routed to project {target.name} based on task attributes",
            )

        # No suitable project found
        auto_create = self.get_config_value(instance, "auto_create_projects", False)
        if auto_create:
            # In a real implementation, we'd create a new project here
            return TaskAction.reject(
                reason="No suitable project found and auto-create not implemented"
            )

        return TaskAction.reject(
            reason="No suitable project found for task routing"
        )

    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """Global always delegates."""
        return True

    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Find the best PROJECT instance for this task.

        Routing priority:
        1. Explicit project assignment in task
        2. Project matching task tags/capabilities
        3. Project matching task content keywords
        4. Round-robin among available projects
        """
        # 1. Check explicit project assignment
        if task.project:
            target = await self._find_project_by_name(task.project, instance.id)
            if target:
                return target

        # 2. Find project by tag matching
        if task.tags:
            target = await self._find_project_by_tags(task.tags, instance.id)
            if target:
                return target

        # 3. Find any available project (load balance)
        strategy = self.get_config_value(instance, "fallback_strategy", "round_robin")
        return await self._find_available_project(instance.id, strategy)

    async def on_task_completed(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> None:
        """
        Handle task completion notification.

        Global instances track completion metrics and can trigger
        follow-up actions.
        """
        logger.info(
            f"Task {task.id} completed, bubbled up to global instance {instance.id}"
        )

        # Update metrics in runtime_metadata
        metadata = instance.runtime_metadata or {}
        completed_count = metadata.get("completed_tasks", 0) + 1
        metadata["completed_tasks"] = completed_count
        instance.runtime_metadata = metadata

    async def get_task_queue(
        self,
        instance: HopperInstance,
    ) -> list[Task]:
        """
        Global instances don't maintain an execution queue.

        Returns only tasks that haven't been routed yet.
        """
        # Get tasks at this instance that are pending routing
        query = (
            select(Task)
            .where(Task.instance_id == instance.id)
            .where(Task.status == TaskStatus.PENDING)
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    async def _find_project_by_name(
        self,
        project_name: str,
        parent_id: str,
    ) -> HopperInstance | None:
        """Find a project instance by name."""
        query = (
            select(HopperInstance)
            .where(HopperInstance.parent_id == parent_id)
            .where(HopperInstance.scope == HopperScope.PROJECT)
            .where(HopperInstance.name == project_name)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    async def _find_project_by_tags(
        self,
        task_tags: list[str],
        parent_id: str,
    ) -> HopperInstance | None:
        """Find a project that matches task tags."""
        query = (
            select(HopperInstance)
            .where(HopperInstance.parent_id == parent_id)
            .where(HopperInstance.scope == HopperScope.PROJECT)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        projects = result.scalars().all()

        # Check each project for matching capabilities
        for project in projects:
            config = project.config or {}
            capabilities = config.get("capabilities", [])
            tags = config.get("tags", [])

            if set(task_tags) & set(capabilities + tags):
                return project

        return None

    async def _find_available_project(
        self,
        parent_id: str,
        strategy: str = "round_robin",
    ) -> HopperInstance | None:
        """Find any available project using the specified strategy."""
        query = (
            select(HopperInstance)
            .where(HopperInstance.parent_id == parent_id)
            .where(HopperInstance.scope == HopperScope.PROJECT)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        projects = list(result.scalars().all())

        if not projects:
            return None

        if strategy == "round_robin":
            # Simple: return the first one
            # Could be enhanced with actual round-robin tracking
            return projects[0]
        elif strategy == "least_loaded":
            # Return project with fewest active tasks
            return min(projects, key=lambda p: len(p.tasks) if p.tasks else 0)
        else:
            return projects[0]
