"""
RoutingDecision model - Records how and why tasks were routed.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .project import Project
    from .task import Task


class RoutingDecision(Base, TimestampMixin):
    """
    RoutingDecision records the routing decision for a task.

    This is crucial for the memory system - we track confidence, reasoning,
    alternatives considered, and context to learn from outcomes.
    """

    __tablename__ = "routing_decisions"

    # Primary key - one decision per task
    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("tasks.id"), primary_key=True)

    # Routing result
    project: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("projects.name"), nullable=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Decision metadata
    alternatives: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(50), nullable=True)
    decision_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Context snapshot
    workload_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="routing_decision")
    project_obj: Mapped["Project | None"] = relationship(
        "Project", back_populates="routing_decisions"
    )

    def __repr__(self) -> str:
        return (
            f"<RoutingDecision(task_id={self.task_id}, project={self.project}, "
            f"confidence={self.confidence})>"
        )
