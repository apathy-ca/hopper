"""
Task model - Core entity for task management in Hopper.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .enums import TaskPriority, TaskStatus

if TYPE_CHECKING:
    from .hopper_instance import HopperInstance
    from .routing_decision import RoutingDecision


class Task(Base, TimestampMixin):
    """
    Task represents a unit of work to be routed and executed.

    Tasks are the primary entity in Hopper, containing all information needed
    for intelligent routing decisions.
    """

    __tablename__ = "tasks"

    # Primary identification
    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    instance_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("hopper_instances.instance_id"), nullable=False
    )
    parent_task_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Core task information
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=TaskStatus.PENDING.value, nullable=False
    )
    priority: Mapped[str] = mapped_column(
        String(20), default=TaskPriority.MEDIUM.value, nullable=False
    )

    # Ownership and tracking
    requester: Mapped[str | None] = mapped_column(String(100), nullable=True)
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # External integration
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_platform: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Source and context
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Task metadata (JSONB/JSON fields)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    required_capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocks: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Routing information
    routing_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    routing_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    hopper_instance: Mapped["HopperInstance"] = relationship(
        "HopperInstance", back_populates="tasks"
    )
    routing_decision: Mapped["RoutingDecision | None"] = relationship(
        "RoutingDecision", back_populates="task", uselist=False
    )
    feedback: Mapped["TaskFeedback | None"] = relationship(
        "TaskFeedback", back_populates="task", uselist=False
    )

    # Indexes for performance
    __table_args__ = (
        Index("idx_tasks_instance", "instance_id"),
        Index("idx_tasks_project", "project"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title={self.title[:30]}, status={self.status})>"


class TaskFeedback(Base, TimestampMixin):
    """
    Feedback on task execution for learning and improvement.

    Captures information about how well a task was routed and executed,
    feeding into the memory system for continuous improvement.
    """

    __tablename__ = "task_feedback"

    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("tasks.id"), primary_key=True)

    # Duration tracking
    estimated_duration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actual_duration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    complexity_rating: Mapped[int | None] = mapped_column(nullable=True)

    # Quality metrics
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_rework: Mapped[bool | None] = mapped_column(nullable=True)
    rework_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Routing feedback
    was_good_match: Mapped[bool | None] = mapped_column(nullable=True)
    should_have_routed_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    routing_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Learning data
    unexpected_blockers: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    required_skills_not_tagged: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )

    # Additional notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="feedback")

    # Index for querying good/bad matches
    __table_args__ = (Index("idx_feedback_was_good_match", "was_good_match"),)

    def __repr__(self) -> str:
        return f"<TaskFeedback(task_id={self.task_id}, was_good_match={self.was_good_match})>"
