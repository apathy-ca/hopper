"""
TaskDelegation repository for delegation tracking and queries.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models.task_delegation import (
    DelegationStatus,
    DelegationType,
    TaskDelegation,
)

from .base import BaseRepository


class TaskDelegationRepository(BaseRepository[TaskDelegation]):
    """Repository for TaskDelegation model with custom queries."""

    def __init__(self, session: Session):
        """Initialize TaskDelegationRepository."""
        super().__init__(TaskDelegation, session)

    def create_delegation(
        self,
        delegation_id: str,
        task_id: str,
        source_instance_id: str | None,
        target_instance_id: str,
        delegation_type: str = DelegationType.ROUTE,
        delegated_by: str | None = None,
        notes: str | None = None,
    ) -> TaskDelegation:
        """
        Create a new task delegation.

        Args:
            delegation_id: Unique delegation ID
            task_id: ID of the task being delegated
            source_instance_id: ID of the source instance
            target_instance_id: ID of the target instance
            delegation_type: Type of delegation (route, decompose, escalate)
            delegated_by: Who initiated the delegation
            notes: Optional notes about the delegation

        Returns:
            Created TaskDelegation
        """
        delegation = TaskDelegation(
            id=delegation_id,
            task_id=task_id,
            source_instance_id=source_instance_id,
            target_instance_id=target_instance_id,
            delegation_type=delegation_type,
            status=DelegationStatus.PENDING,
            delegated_at=datetime.utcnow(),
            delegated_by=delegated_by,
            notes=notes,
        )
        return self.create(delegation)

    def get_delegations_for_task(self, task_id: str) -> list[TaskDelegation]:
        """
        Get all delegations for a task.

        Args:
            task_id: Task ID

        Returns:
            List of delegations for the task, ordered by delegation time
        """
        query = (
            select(TaskDelegation)
            .where(TaskDelegation.task_id == task_id)
            .order_by(TaskDelegation.delegated_at.asc())
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_delegation_chain(self, task_id: str) -> list[TaskDelegation]:
        """
        Get the full delegation chain for a task.

        Returns delegations in order from origin to current location.

        Args:
            task_id: Task ID

        Returns:
            Ordered list of delegations showing task's journey
        """
        return self.get_delegations_for_task(task_id)

    def get_pending_delegations(self, instance_id: str) -> list[TaskDelegation]:
        """
        Get pending delegations for an instance (incoming).

        Args:
            instance_id: Target instance ID

        Returns:
            List of pending delegations
        """
        return self.filter(
            filters={
                "target_instance_id": instance_id,
                "status": DelegationStatus.PENDING,
            }
        )

    def get_active_delegations(self, instance_id: str) -> list[TaskDelegation]:
        """
        Get active delegations for an instance (pending or accepted).

        Args:
            instance_id: Target instance ID

        Returns:
            List of active delegations
        """
        query = (
            select(TaskDelegation)
            .where(TaskDelegation.target_instance_id == instance_id)
            .where(
                TaskDelegation.status.in_(
                    [DelegationStatus.PENDING, DelegationStatus.ACCEPTED]
                )
            )
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_outgoing_delegations(self, instance_id: str) -> list[TaskDelegation]:
        """
        Get delegations sent from an instance.

        Args:
            instance_id: Source instance ID

        Returns:
            List of delegations from the instance
        """
        return self.filter(filters={"source_instance_id": instance_id})

    def mark_accepted(self, delegation_id: str) -> TaskDelegation | None:
        """
        Mark a delegation as accepted.

        Args:
            delegation_id: Delegation ID

        Returns:
            Updated delegation or None if not found
        """
        delegation = self.get(delegation_id)
        if delegation:
            delegation.accept()
            self.session.flush()
        return delegation

    def mark_rejected(
        self, delegation_id: str, reason: str | None = None
    ) -> TaskDelegation | None:
        """
        Mark a delegation as rejected.

        Args:
            delegation_id: Delegation ID
            reason: Rejection reason

        Returns:
            Updated delegation or None if not found
        """
        delegation = self.get(delegation_id)
        if delegation:
            delegation.reject(reason)
            self.session.flush()
        return delegation

    def mark_completed(
        self, delegation_id: str, result: dict | None = None
    ) -> TaskDelegation | None:
        """
        Mark a delegation as completed.

        Args:
            delegation_id: Delegation ID
            result: Optional result data

        Returns:
            Updated delegation or None if not found
        """
        delegation = self.get(delegation_id)
        if delegation:
            delegation.complete(result)
            self.session.flush()
        return delegation

    def mark_cancelled(self, delegation_id: str) -> TaskDelegation | None:
        """
        Mark a delegation as cancelled.

        Args:
            delegation_id: Delegation ID

        Returns:
            Updated delegation or None if not found
        """
        delegation = self.get(delegation_id)
        if delegation:
            delegation.cancel()
            self.session.flush()
        return delegation

    def get_latest_delegation(self, task_id: str) -> TaskDelegation | None:
        """
        Get the most recent delegation for a task.

        Args:
            task_id: Task ID

        Returns:
            Most recent delegation or None
        """
        query = (
            select(TaskDelegation)
            .where(TaskDelegation.task_id == task_id)
            .order_by(TaskDelegation.delegated_at.desc())
            .limit(1)
        )
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_current_location(self, task_id: str) -> str | None:
        """
        Get the current instance location of a task based on delegations.

        Args:
            task_id: Task ID

        Returns:
            Instance ID where the task currently resides, or None
        """
        latest = self.get_latest_delegation(task_id)
        if latest and latest.status in (
            DelegationStatus.PENDING,
            DelegationStatus.ACCEPTED,
        ):
            return latest.target_instance_id
        return None

    def count_delegations_by_status(self, instance_id: str) -> dict[str, int]:
        """
        Count delegations by status for an instance.

        Args:
            instance_id: Instance ID

        Returns:
            Dict mapping status to count
        """
        counts = {}
        for status in [
            DelegationStatus.PENDING,
            DelegationStatus.ACCEPTED,
            DelegationStatus.COMPLETED,
            DelegationStatus.REJECTED,
            DelegationStatus.CANCELLED,
        ]:
            counts[status] = self.count(
                filters={"target_instance_id": instance_id, "status": status}
            )
        return counts
