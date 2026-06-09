"""
Task model for Hopper.
"""

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .external_mapping import ExternalMapping
    from .hopper_instance import HopperInstance
    from .routing_decision import RoutingDecision
    from .task_delegation import TaskDelegation
    from .task_feedback import TaskFeedback


class Task(Base, TimestampMixin):
    """Task model representing a unit of work."""

    __tablename__ = "tasks"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Instance association
    instance_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("hopper_instances.id"), nullable=True
    )

    # Basic info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)

    # Metadata
    requester: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # External links
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Context
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Arrays/JSON - use JSONB for PostgreSQL, JSON for SQLite
    tags: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    required_capabilities: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    depends_on: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    blocks: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Agent/heartbeat tracking
    assigned_to: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_heartbeat: Mapped[Any | None] = mapped_column(DateTime, nullable=True)
    expected_heartbeat: Mapped[Any | None] = mapped_column(DateTime, nullable=True)

    # Task hierarchy
    parent_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Soft delete
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Routing
    routing_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    instance: Mapped[Optional["HopperInstance"]] = relationship(
        "HopperInstance", back_populates="tasks"
    )
    routing_decision: Mapped[Optional["RoutingDecision"]] = relationship(
        "RoutingDecision", back_populates="task", uselist=False
    )
    feedback: Mapped[Optional["TaskFeedback"]] = relationship(
        "TaskFeedback", back_populates="task", uselist=False
    )
    external_mappings: Mapped[list["ExternalMapping"]] = relationship(
        "ExternalMapping", back_populates="task"
    )
    delegations: Mapped[list["TaskDelegation"]] = relationship(
        "TaskDelegation", back_populates="task", foreign_keys="TaskDelegation.task_id"
    )

    # Indexes
    __table_args__ = (
        Index("idx_tasks_project", "project"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_created_at", "created_at"),
        Index("idx_tasks_updated_at", "updated_at"),
        Index("idx_tasks_parent_id", "parent_id"),
        Index("idx_tasks_assigned_to", "assigned_to"),
        Index("idx_tasks_instance_id", "instance_id"),
        Index("idx_tasks_requester", "requester"),
        Index("idx_tasks_owner", "owner"),
        Index("idx_tasks_deleted", "deleted"),
        Index("idx_tasks_external", "external_id", "external_platform"),
        # GIN index for JSONB tags (PostgreSQL only)
        # Index("idx_tasks_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title={self.title}, status={self.status})>"
