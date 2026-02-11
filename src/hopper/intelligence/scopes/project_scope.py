"""
Project scope behavior implementation.

Project instances make tactical decisions about whether to handle tasks
directly or delegate to orchestration instances.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, InstanceStatus, Task, TaskStatus

from .base import BaseScopeBehavior, TaskAction

logger = logging.getLogger(__name__)


class ProjectScopeBehavior(BaseScopeBehavior):
    """
    Behavior for PROJECT scope instances.

    Project instances make tactical decisions:
    - Handle simple tasks directly
    - Delegate complex tasks to ORCHESTRATION instances
    - Create orchestration instances for worker runs
    - Track project-level metrics
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
        return "PROJECT"

    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> TaskAction:
        """
        Projects decide between direct handling and orchestration.

        Decision factors:
        - Task complexity
        - Task type (routine vs complex)
        - Available orchestration instances
        - Configuration thresholds
        """
        if await self.should_delegate(task, instance):
            target = await self.find_delegation_target(task, instance)
            if target:
                return TaskAction.delegate(
                    target_instance_id=target.id,
                    reason=f"Task complexity ({self.estimate_task_complexity(task)}) "
                           f"exceeds threshold, delegating to orchestration",
                )
            else:
                # No orchestration available, check if we can create one
                auto_create = self.get_config_value(
                    instance, "auto_create_orchestrations", True
                )
                if auto_create:
                    return TaskAction.reject(
                        reason="No orchestration instance available and auto-create not implemented"
                    )
                else:
                    # Handle directly even though complex
                    return TaskAction.handle(
                        reason="No orchestration available, handling directly"
                    )

        # Handle directly - task is simple enough
        return TaskAction.handle(
            reason="Task complexity within threshold, handling directly"
        )

    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """
        Determine if task should be delegated to orchestration.

        Based on:
        - auto_delegate config setting
        - Task complexity vs threshold
        """
        # Check if auto-delegation is enabled
        auto_delegate = self.get_config_value(instance, "auto_delegate", True)
        if not auto_delegate:
            return False

        # Compare complexity to threshold
        threshold = self.get_config_value(instance, "orchestration_threshold", 3)
        complexity = self.estimate_task_complexity(task)

        return complexity >= threshold

    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Find an orchestration instance to delegate to.

        Prefers running instances, can create new ones if configured.
        """
        # Find existing orchestration instances
        query = (
            select(HopperInstance)
            .where(HopperInstance.parent_id == instance.id)
            .where(HopperInstance.scope == HopperScope.ORCHESTRATION)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        orchestrations = list(result.scalars().all())

        if orchestrations:
            # Return the one with fewest tasks (simple load balance)
            return min(
                orchestrations,
                key=lambda o: len(o.tasks) if o.tasks else 0,
            )

        return None

    async def on_task_completed(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> None:
        """
        Handle task completion at project level.

        Updates metrics and may bubble up to global.
        """
        logger.info(
            f"Task {task.id} completed at project instance {instance.id}"
        )

        # Update metrics
        metadata = instance.runtime_metadata or {}
        completed_count = metadata.get("completed_tasks", 0) + 1
        metadata["completed_tasks"] = completed_count
        instance.runtime_metadata = metadata

    async def get_task_queue(
        self,
        instance: HopperInstance,
    ) -> list[Task]:
        """
        Get tasks at this project instance.

        Includes tasks being handled directly (not delegated to orchestration).
        """
        query = (
            select(Task)
            .where(Task.instance_id == instance.id)
            .where(
                Task.status.in_(
                    [TaskStatus.PENDING, TaskStatus.CLAIMED, TaskStatus.IN_PROGRESS]
                )
            )
            .order_by(Task.created_at.asc())
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    async def get_project_stats(
        self,
        instance: HopperInstance,
    ) -> dict:
        """
        Get statistics for this project.

        Returns:
            Dict with project statistics
        """
        # Count tasks by status
        tasks = instance.tasks or []
        status_counts = {}
        for task in tasks:
            status = task.status.value if hasattr(task.status, 'value') else str(task.status)
            status_counts[status] = status_counts.get(status, 0) + 1

        # Count orchestration instances
        orch_count = 0
        for child in instance.children:
            if child.scope == HopperScope.ORCHESTRATION:
                orch_count += 1

        return {
            "total_tasks": len(tasks),
            "tasks_by_status": status_counts,
            "orchestration_instances": orch_count,
            "completed_tasks": (instance.runtime_metadata or {}).get("completed_tasks", 0),
        }
