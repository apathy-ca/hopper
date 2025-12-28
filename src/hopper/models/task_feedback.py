"""
Task Feedback model for Hopper.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base


class TaskFeedback(Base):
    """Task Feedback model for capturing task outcomes and learning."""

    __tablename__ = "task_feedback"

    # Primary key (also foreign key to tasks)
    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("tasks.id"), primary_key=True)

    # Duration estimates
    estimated_duration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    actual_duration: Mapped[str | None] = mapped_column(String(50), nullable=True)
    complexity_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Quality metrics
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    required_rework: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    rework_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Routing feedback
    was_good_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    should_have_routed_to: Mapped[str | None] = mapped_column(String(100), nullable=True)
    routing_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Unexpected issues
    unexpected_blockers: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    required_skills_not_tagged: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Additional notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="feedback")

    def __repr__(self) -> str:
        return f"<TaskFeedback(task_id={self.task_id}, was_good_match={self.was_good_match})>"
