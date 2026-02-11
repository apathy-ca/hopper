"""
Episodic memory models.

Defines the RoutingEpisode model for recording routing decisions.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from hopper.models.base import Base, TimestampMixin


class RoutingEpisode(Base, TimestampMixin):
    """
    Model for recording routing episodes.

    Captures the complete context and outcome of a routing decision
    for learning and analysis.
    """

    __tablename__ = "routing_episodes"

    # Primary key
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Link to task and routing decision
    task_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision_task_id: Mapped[str | None] = mapped_column(
        String(50),
        ForeignKey("routing_decisions.task_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Snapshot of task at routing time
    task_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
    )

    # Routing context at decision time
    available_instances: Mapped[list[str]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    similar_tasks_used: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # Decision details
    chosen_instance: Mapped[str | None] = mapped_column(String(100), nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    strategy_used: Mapped[str] = mapped_column(
        String(50), default="rules", nullable=False
    )

    # Factors that influenced the decision
    decision_factors: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # Outcome (filled after task completion)
    outcome_success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome_duration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    outcome_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Link to feedback
    feedback_id: Mapped[str | None] = mapped_column(
        String(50),
        ForeignKey("task_feedback.task_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Timestamps
    routed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Instance context at routing time
    instance_context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", foreign_keys=[task_id])
    decision: Mapped["RoutingDecision"] = relationship(
        "RoutingDecision", foreign_keys=[decision_task_id]
    )
    feedback: Mapped["TaskFeedback"] = relationship(
        "TaskFeedback", foreign_keys=[feedback_id]
    )

    def __repr__(self) -> str:
        return (
            f"<RoutingEpisode(id={self.id}, task_id={self.task_id}, "
            f"chosen={self.chosen_instance}, outcome={self.outcome_success})>"
        )

    def mark_success(
        self,
        duration: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Mark episode as successful."""
        self.outcome_success = True
        self.completed_at = datetime.utcnow()
        if duration:
            self.outcome_duration = duration
        if notes:
            self.outcome_notes = notes

    def mark_failure(
        self,
        notes: str | None = None,
    ) -> None:
        """Mark episode as failed."""
        self.outcome_success = False
        self.completed_at = datetime.utcnow()
        if notes:
            self.outcome_notes = notes

    @property
    def is_completed(self) -> bool:
        """Check if episode has outcome recorded."""
        return self.outcome_success is not None

    @property
    def duration_seconds(self) -> float | None:
        """Get episode duration in seconds."""
        if self.completed_at is None:
            return None
        delta = self.completed_at - self.routed_at
        return delta.total_seconds()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "decision_task_id": self.decision_task_id,
            "task_snapshot": self.task_snapshot,
            "available_instances": self.available_instances,
            "similar_tasks_used": self.similar_tasks_used,
            "chosen_instance": self.chosen_instance,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "strategy_used": self.strategy_used,
            "decision_factors": self.decision_factors,
            "outcome_success": self.outcome_success,
            "outcome_duration": self.outcome_duration,
            "outcome_notes": self.outcome_notes,
            "feedback_id": self.feedback_id,
            "routed_at": self.routed_at.isoformat() if self.routed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "instance_context": self.instance_context,
        }
