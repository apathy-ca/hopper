"""
Orchestration scope behavior implementation.

Orchestration instances execute tasks and manage worker queues.
They don't delegate further - they're the execution level.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, Task, TaskStatus

from .base import BaseScopeBehavior, TaskAction

logger = logging.getLogger(__name__)


class OrchestrationScopeBehavior(BaseScopeBehavior):
    """
    Behavior for ORCHESTRATION scope instances.

    Orchestration instances are the execution level:
    - Manage worker task queues
    - Execute tasks (don't delegate further)
    - Track execution status
    - Report completion to parent PROJECT
    - Handle worker failures
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
        return "ORCHESTRATION"

    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> TaskAction:
        """
        Orchestration instances queue tasks for execution.

        They don't delegate - they execute.
        """
        # Check if we can accept more tasks
        max_concurrent = self.get_config_value(instance, "max_concurrent_tasks", 10)
        current_active = await self._count_active_tasks(instance)

        if current_active >= max_concurrent:
            return TaskAction.reject(
                reason=f"Instance at capacity ({current_active}/{max_concurrent} tasks)"
            )

        return TaskAction.queue(
            reason="Task added to orchestration queue for execution"
        )

    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """Orchestration never delegates - it executes."""
        return False

    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """Orchestration doesn't delegate."""
        return None

    async def on_task_completed(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> None:
        """
        Handle task completion at orchestration level.

        Updates metrics and notifies parent project.
        """
        logger.info(
            f"Task {task.id} completed at orchestration instance {instance.id}"
        )

        # Update metrics
        metadata = instance.runtime_metadata or {}
        completed_count = metadata.get("completed_tasks", 0) + 1
        metadata["completed_tasks"] = completed_count
        instance.runtime_metadata = metadata

        # The completion will bubble up through the delegation chain

    async def get_task_queue(
        self,
        instance: HopperInstance,
    ) -> list[Task]:
        """
        Get the execution queue for this orchestration instance.

        Returns tasks ordered by priority and creation time.
        """
        # Priority order mapping
        priority_order = {
            "urgent": 0,
            "high": 1,
            "medium": 2,
            "low": 3,
        }

        query = (
            select(Task)
            .where(Task.instance_id == instance.id)
            .where(
                Task.status.in_(
                    [TaskStatus.PENDING, TaskStatus.CLAIMED, TaskStatus.IN_PROGRESS]
                )
            )
        )
        result = self.session.execute(query)
        tasks = list(result.scalars().all())

        # Sort by priority then creation time
        tasks.sort(
            key=lambda t: (
                priority_order.get(t.priority, 2),
                t.created_at,
            )
        )

        return tasks

    async def _count_active_tasks(self, instance: HopperInstance) -> int:
        """Count currently active tasks."""
        query = (
            select(Task)
            .where(Task.instance_id == instance.id)
            .where(
                Task.status.in_(
                    [TaskStatus.CLAIMED, TaskStatus.IN_PROGRESS]
                )
            )
        )
        result = self.session.execute(query)
        return len(list(result.scalars().all()))

    async def get_next_task(
        self,
        instance: HopperInstance,
    ) -> Task | None:
        """
        Get the next task to execute from the queue.

        Returns:
            Next pending task or None if queue is empty
        """
        queue = await self.get_task_queue(instance)
        for task in queue:
            if task.status == TaskStatus.PENDING:
                return task
        return None

    async def claim_task(
        self,
        task: Task,
        worker_id: str,
    ) -> Task:
        """
        Claim a task for execution.

        Args:
            task: Task to claim
            worker_id: ID of the worker claiming the task

        Returns:
            Updated task
        """
        task.status = TaskStatus.CLAIMED
        task.owner = worker_id
        self.session.flush()
        return task

    async def get_queue_stats(
        self,
        instance: HopperInstance,
    ) -> dict:
        """
        Get queue statistics for this orchestration instance.

        Returns:
            Dict with queue statistics
        """
        tasks = instance.tasks or []

        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        claimed = sum(1 for t in tasks if t.status == TaskStatus.CLAIMED)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)

        max_concurrent = self.get_config_value(instance, "max_concurrent_tasks", 10)

        return {
            "pending": pending,
            "claimed": claimed,
            "in_progress": in_progress,
            "done": done,
            "total": len(tasks),
            "active": claimed + in_progress,
            "max_concurrent": max_concurrent,
            "capacity_used": (claimed + in_progress) / max_concurrent if max_concurrent > 0 else 0,
        }

    async def should_accept_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """
        Check if this orchestration can accept a new task.

        Args:
            task: Task to potentially accept
            instance: This instance

        Returns:
            True if task can be accepted
        """
        max_concurrent = self.get_config_value(instance, "max_concurrent_tasks", 10)
        current_active = await self._count_active_tasks(instance)
        return current_active < max_concurrent
