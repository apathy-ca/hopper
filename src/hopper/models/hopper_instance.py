"""
HopperInstance model - Multi-instance hierarchy support.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .task import Task


class HopperInstance(Base, TimestampMixin):
    """
    HopperInstance represents a node in the Hopper hierarchy.

    Hopper supports multiple scopes (GLOBAL, PROJECT, ORCHESTRATION, etc.)
    in a parent-child hierarchy for sophisticated task delegation.
    """

    __tablename__ = "hopper_instances"

    # Primary identification
    instance_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    scope: Mapped[str] = mapped_column(String(50), nullable=False)

    # Hierarchy
    parent_instance_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("hopper_instances.instance_id"), nullable=True
    )

    # Configuration
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships - parent/children
    parent: Mapped["HopperInstance | None"] = relationship(
        "HopperInstance",
        remote_side=[instance_id],
        back_populates="children",
        foreign_keys=[parent_instance_id],
    )
    children: Mapped[list["HopperInstance"]] = relationship(
        "HopperInstance",
        back_populates="parent",
        foreign_keys=[parent_instance_id],
    )

    # Relationship to tasks
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="hopper_instance")

    # Relationship to delegations
    parent_delegations: Mapped[list["TaskDelegation"]] = relationship(
        "TaskDelegation",
        foreign_keys="TaskDelegation.parent_instance_id",
        back_populates="parent_instance",
    )
    child_delegations: Mapped[list["TaskDelegation"]] = relationship(
        "TaskDelegation",
        foreign_keys="TaskDelegation.child_instance_id",
        back_populates="child_instance",
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_instances_parent", "parent_instance_id"),
        Index("idx_instances_scope", "scope"),
    )

    def __repr__(self) -> str:
        return f"<HopperInstance(id={self.instance_id}, scope={self.scope})>"


class TaskDelegation(Base, TimestampMixin):
    """
    TaskDelegation tracks parent→child task delegation in the instance hierarchy.

    When a parent instance delegates a task to a child instance, this record
    tracks the relationship for completion notification.
    """

    __tablename__ = "task_delegations"

    # Composite primary key
    parent_instance_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("hopper_instances.instance_id"), primary_key=True
    )
    parent_task_id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Child information
    child_instance_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("hopper_instances.instance_id"), nullable=False
    )
    child_task_id: Mapped[str] = mapped_column(String(50), nullable=False)

    # Relationships
    parent_instance: Mapped["HopperInstance"] = relationship(
        "HopperInstance",
        foreign_keys=[parent_instance_id],
        back_populates="parent_delegations",
    )
    child_instance: Mapped["HopperInstance"] = relationship(
        "HopperInstance",
        foreign_keys=[child_instance_id],
        back_populates="child_delegations",
    )

    def __repr__(self) -> str:
        return f"<TaskDelegation(parent={self.parent_task_id}, " f"child={self.child_task_id})>"
