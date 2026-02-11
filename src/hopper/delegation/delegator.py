"""
Main delegation logic for task routing between instances.
"""

import logging
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from hopper.models import (
    DelegationStatus,
    DelegationType,
    HopperInstance,
    InstanceStatus,
    Task,
    TaskDelegation,
)

logger = logging.getLogger(__name__)


class DelegationError(Exception):
    """Raised when delegation fails."""

    pass


class Delegator:
    """
    Handles task delegation between Hopper instances.

    Manages the process of moving tasks down the hierarchy
    and tracking delegation status.
    """

    def __init__(self, session: Session):
        """
        Initialize the delegator.

        Args:
            session: Database session
        """
        self.session = session

    def delegate_task(
        self,
        task: Task,
        target_instance: HopperInstance,
        delegation_type: str = DelegationType.ROUTE,
        delegated_by: str | None = None,
        notes: str | None = None,
    ) -> TaskDelegation:
        """
        Delegate a task to a target instance.

        Args:
            task: Task to delegate
            target_instance: Instance to delegate to
            delegation_type: Type of delegation
            delegated_by: Who initiated the delegation
            notes: Optional notes

        Returns:
            Created TaskDelegation

        Raises:
            DelegationError: If delegation fails
        """
        # Validate target instance is running
        if target_instance.status not in (InstanceStatus.RUNNING, InstanceStatus.CREATED):
            raise DelegationError(
                f"Cannot delegate to instance {target_instance.id} "
                f"with status {target_instance.status}"
            )

        # Get source instance
        source_instance_id = task.instance_id

        # Create delegation record
        delegation = TaskDelegation(
            id=f"del-{uuid4().hex[:12]}",
            task_id=task.id,
            source_instance_id=source_instance_id,
            target_instance_id=target_instance.id,
            delegation_type=delegation_type,
            status=DelegationStatus.PENDING,
            delegated_at=datetime.utcnow(),
            delegated_by=delegated_by,
            notes=notes,
        )

        self.session.add(delegation)

        # Update task's instance assignment
        task.instance_id = target_instance.id
        task.updated_at = datetime.utcnow()

        self.session.flush()

        logger.info(
            f"Delegated task {task.id} from {source_instance_id} "
            f"to {target_instance.id} (type={delegation_type})"
        )

        return delegation

    def accept_delegation(
        self,
        delegation: TaskDelegation,
        notes: str | None = None,
    ) -> TaskDelegation:
        """
        Accept an incoming delegation.

        Args:
            delegation: Delegation to accept
            notes: Optional acceptance notes

        Returns:
            Updated delegation

        Raises:
            DelegationError: If delegation cannot be accepted
        """
        if delegation.status != DelegationStatus.PENDING:
            raise DelegationError(
                f"Cannot accept delegation {delegation.id} "
                f"with status {delegation.status}"
            )

        delegation.accept()
        if notes:
            delegation.notes = (delegation.notes or "") + f"\nAccepted: {notes}"

        self.session.flush()

        logger.info(f"Accepted delegation {delegation.id}")

        return delegation

    def reject_delegation(
        self,
        delegation: TaskDelegation,
        reason: str,
    ) -> TaskDelegation:
        """
        Reject an incoming delegation.

        Args:
            delegation: Delegation to reject
            reason: Rejection reason

        Returns:
            Updated delegation

        Raises:
            DelegationError: If delegation cannot be rejected
        """
        if delegation.status != DelegationStatus.PENDING:
            raise DelegationError(
                f"Cannot reject delegation {delegation.id} "
                f"with status {delegation.status}"
            )

        delegation.reject(reason)
        self.session.flush()

        logger.info(f"Rejected delegation {delegation.id}: {reason}")

        # Return task to source instance
        task = delegation.task
        if delegation.source_instance_id:
            task.instance_id = delegation.source_instance_id
            task.updated_at = datetime.utcnow()
            self.session.flush()

        return delegation

    def complete_delegation(
        self,
        delegation: TaskDelegation,
        result: dict | None = None,
    ) -> TaskDelegation:
        """
        Mark a delegation as completed.

        Args:
            delegation: Delegation to complete
            result: Optional result data

        Returns:
            Updated delegation

        Raises:
            DelegationError: If delegation cannot be completed
        """
        if delegation.status not in (DelegationStatus.PENDING, DelegationStatus.ACCEPTED):
            raise DelegationError(
                f"Cannot complete delegation {delegation.id} "
                f"with status {delegation.status}"
            )

        delegation.complete(result)
        self.session.flush()

        logger.info(f"Completed delegation {delegation.id}")

        return delegation

    def cancel_delegation(
        self,
        delegation: TaskDelegation,
    ) -> TaskDelegation:
        """
        Cancel a delegation.

        Args:
            delegation: Delegation to cancel

        Returns:
            Updated delegation
        """
        if delegation.is_terminal:
            raise DelegationError(
                f"Cannot cancel delegation {delegation.id} "
                f"with terminal status {delegation.status}"
            )

        delegation.cancel()
        self.session.flush()

        logger.info(f"Cancelled delegation {delegation.id}")

        # Return task to source instance
        task = delegation.task
        if delegation.source_instance_id:
            task.instance_id = delegation.source_instance_id
            task.updated_at = datetime.utcnow()
            self.session.flush()

        return delegation

    def get_delegation_chain(self, task: Task) -> list[TaskDelegation]:
        """
        Get the full delegation chain for a task.

        Args:
            task: Task to get chain for

        Returns:
            List of delegations in order from origin to current
        """
        delegations = sorted(task.delegations, key=lambda d: d.delegated_at)
        return delegations

    def get_active_delegation(self, task: Task) -> TaskDelegation | None:
        """
        Get the active (non-terminal) delegation for a task.

        Args:
            task: Task to check

        Returns:
            Active delegation or None
        """
        for delegation in task.delegations:
            if delegation.is_active:
                return delegation
        return None
