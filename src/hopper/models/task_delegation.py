"""
TaskDelegation model for tracking task movement between instances.

Tracks the full delegation chain as tasks flow through the instance hierarchy.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin
from .enums import TaskStatus


class DelegationType(str):
    """Types of task delegation."""

    ROUTE = "route"          # Routing to appropriate instance
    DECOMPOSE = "decompose"  # Breaking task into subtasks
    ESCALATE = "escalate"    # Escalating to parent instance
    REASSIGN = "reassign"    # Reassigning to different instance


class DelegationStatus(str):
    """Status of a delegation."""

    PENDING = "pending"      # Delegation created, not yet accepted
    ACCEPTED = "accepted"    # Target instance accepted the delegation
    REJECTED = "rejected"    # Target instance rejected the delegation
    COMPLETED = "completed"  # Task completed at target instance
    CANCELLED = "cancelled"  # Delegation was cancelled


class TaskDelegation(Base, TimestampMixin):
    """
    Model for tracking task delegation between Hopper instances.

    Records the movement of tasks through the instance hierarchy,
    enabling full traceability of delegation chains.
    """

    __tablename__ = "task_delegations"

    # Primary key
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Task being delegated
    task_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Source and target instances
    source_instance_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("hopper_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_instance_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("hopper_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Delegation details
    delegation_type: Mapped[str] = mapped_column(
        String(20),
        default=DelegationType.ROUTE,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default=DelegationStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Timestamps
    delegated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Result and metadata
    result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit
    delegated_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship(
        "Task",
        back_populates="delegations",
        foreign_keys=[task_id],
    )
    source_instance: Mapped["HopperInstance"] = relationship(
        "HopperInstance",
        foreign_keys=[source_instance_id],
    )
    target_instance: Mapped["HopperInstance"] = relationship(
        "HopperInstance",
        foreign_keys=[target_instance_id],
    )

    def __repr__(self) -> str:
        return (
            f"<TaskDelegation(id={self.id}, task_id={self.task_id}, "
            f"source={self.source_instance_id}, target={self.target_instance_id}, "
            f"status={self.status})>"
        )

    def accept(self) -> None:
        """Accept this delegation."""
        self.status = DelegationStatus.ACCEPTED
        self.accepted_at = datetime.utcnow()

    def reject(self, reason: str | None = None) -> None:
        """Reject this delegation."""
        self.status = DelegationStatus.REJECTED
        self.rejection_reason = reason

    def complete(self, result: dict[str, Any] | None = None) -> None:
        """Mark this delegation as completed."""
        self.status = DelegationStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        if result:
            self.result = result

    def cancel(self) -> None:
        """Cancel this delegation."""
        self.status = DelegationStatus.CANCELLED

    @property
    def is_pending(self) -> bool:
        """Check if delegation is pending."""
        return self.status == DelegationStatus.PENDING

    @property
    def is_active(self) -> bool:
        """Check if delegation is active (pending or accepted)."""
        return self.status in (DelegationStatus.PENDING, DelegationStatus.ACCEPTED)

    @property
    def is_terminal(self) -> bool:
        """Check if delegation is in a terminal state."""
        return self.status in (
            DelegationStatus.COMPLETED,
            DelegationStatus.REJECTED,
            DelegationStatus.CANCELLED,
        )
