"""
Routing Decision model for Hopper.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base


class RoutingDecision(Base):
    """Routing Decision model for tracking routing outcomes."""

    __tablename__ = "routing_decisions"

    # Primary key (also foreign key to tasks)
    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("tasks.id"), primary_key=True)

    # Decision details
    project: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("projects.name"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternatives: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Decision metadata
    decided_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decision_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Context snapshot
    workload_snapshot: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    context: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="routing_decision")

    def __repr__(self) -> str:
        return f"<RoutingDecision(task_id={self.task_id}, project={self.project})>"
