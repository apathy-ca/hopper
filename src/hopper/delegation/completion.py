"""
Completion bubbling for task delegation.

Handles propagating completion status up the instance hierarchy.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from hopper.models import (
    DelegationStatus,
    HopperInstance,
    Task,
    TaskDelegation,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class CompletionBubbler:
    """
    Handles bubbling completion status up the delegation chain.

    When a task completes at a leaf instance, this class propagates
    the completion back through all parent delegations.
    """

    def __init__(self, session: Session):
        """
        Initialize the completion bubbler.

        Args:
            session: Database session
        """
        self.session = session

    def bubble_completion(
        self,
        task: Task,
        result: dict[str, Any] | None = None,
    ) -> list[TaskDelegation]:
        """
        Bubble task completion up through the delegation chain.

        Marks all active delegations as completed and notifies
        ancestor instances.

        Args:
            task: Completed task
            result: Completion result data

        Returns:
            List of completed delegations
        """
        completed_delegations = []

        # Get all delegations for this task
        delegations = sorted(task.delegations, key=lambda d: d.delegated_at, reverse=True)

        for delegation in delegations:
            if delegation.is_active:
                delegation.complete(result)
                completed_delegations.append(delegation)
                logger.info(
                    f"Bubbled completion for task {task.id} "
                    f"through delegation {delegation.id}"
                )

        self.session.flush()

        return completed_delegations

    def propagate_status_change(
        self,
        task: Task,
        new_status: str,
    ) -> None:
        """
        Propagate a task status change through the hierarchy.

        Useful for notifying parent instances of status changes
        like blocking or cancellation.

        Args:
            task: Task with status change
            new_status: New status value
        """
        # Get the active delegation chain
        delegations = [d for d in task.delegations if d.is_active]

        if not delegations:
            return

        # Log the propagation
        for delegation in delegations:
            logger.info(
                f"Propagating status {new_status} for task {task.id} "
                f"to delegation {delegation.id}"
            )

            # Update delegation notes with status change
            status_note = f"Task status changed to {new_status} at {datetime.utcnow()}"
            delegation.notes = (delegation.notes or "") + f"\n{status_note}"

        self.session.flush()

    def aggregate_child_completions(
        self,
        parent_task: Task,
        child_tasks: list[Task],
    ) -> bool:
        """
        Check if all child tasks are completed.

        Used for tasks that were decomposed into subtasks.

        Args:
            parent_task: Parent task
            child_tasks: Child tasks to check

        Returns:
            True if all children are completed
        """
        if not child_tasks:
            return True

        for child in child_tasks:
            if child.status not in (TaskStatus.DONE, TaskStatus.CANCELLED):
                return False

        return True

    def notify_parent_instance(
        self,
        task: Task,
        event_type: str,
        event_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Notify the parent instance about a task event.

        Args:
            task: Task that triggered the event
            event_type: Type of event (completed, blocked, failed, etc.)
            event_data: Additional event data
        """
        # Get the delegation that brought this task here
        delegations = sorted(task.delegations, key=lambda d: d.delegated_at, reverse=True)

        if not delegations:
            return

        latest_delegation = delegations[0]

        if not latest_delegation.source_instance_id:
            return

        # Log the notification (in a real system, this could trigger webhooks, etc.)
        logger.info(
            f"Notifying parent instance {latest_delegation.source_instance_id} "
            f"about {event_type} for task {task.id}"
        )

        # Store event in delegation metadata
        event = {
            "type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "data": event_data or {},
        }

        result = latest_delegation.result or {}
        events = result.get("events", [])
        events.append(event)
        result["events"] = events
        latest_delegation.result = result

        self.session.flush()

    def get_completion_status(self, task: Task) -> dict[str, Any]:
        """
        Get the completion status of a task's delegation chain.

        Args:
            task: Task to check

        Returns:
            Dict with completion status details
        """
        delegations = task.delegations

        total = len(delegations)
        completed = sum(1 for d in delegations if d.status == DelegationStatus.COMPLETED)
        pending = sum(1 for d in delegations if d.status == DelegationStatus.PENDING)
        accepted = sum(1 for d in delegations if d.status == DelegationStatus.ACCEPTED)
        rejected = sum(1 for d in delegations if d.status == DelegationStatus.REJECTED)

        # Determine overall status
        if total == 0:
            overall = "not_delegated"
        elif completed == total:
            overall = "fully_completed"
        elif rejected > 0:
            overall = "has_rejections"
        elif pending > 0:
            overall = "pending_acceptance"
        elif accepted > 0:
            overall = "in_progress"
        else:
            overall = "unknown"

        return {
            "task_id": task.id,
            "total_delegations": total,
            "completed": completed,
            "pending": pending,
            "accepted": accepted,
            "rejected": rejected,
            "overall_status": overall,
        }
