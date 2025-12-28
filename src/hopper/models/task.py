"""
SQLAlchemy models for Task entities.
"""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, DateTime, Enum as SQLEnum, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
import enum
import uuid

from hopper.models.base import Base


class PriorityEnum(str, enum.Enum):
    """Task priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class StatusEnum(str, enum.Enum):
    """Task status values."""
    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class VelocityEnum(str, enum.Enum):
    """Task velocity requirements."""
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    GLACIAL = "glacial"


class TaskSourceEnum(str, enum.Enum):
    """Task source/origin."""
    MCP = "mcp"
    CLI = "cli"
    API = "api"
    WEBHOOK = "webhook"
    EMAIL = "email"
    GITHUB = "github"
    GITLAB = "gitlab"


class Task(Base):
    """Task model for universal task queue."""

    __tablename__ = "tasks"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=lambda: f"HOP-{uuid.uuid4().hex[:8].upper()}")

    # Identity
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # Categorization
    project: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    priority: Mapped[PriorityEnum] = mapped_column(
        SQLEnum(PriorityEnum, values_callable=lambda x: [e.value for e in x]),
        default=PriorityEnum.MEDIUM,
        nullable=False
    )

    # Routing
    executor_preference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    required_capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    estimated_effort: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    velocity_requirement: Mapped[VelocityEnum] = mapped_column(
        SQLEnum(VelocityEnum, values_callable=lambda x: [e.value for e in x]),
        default=VelocityEnum.MEDIUM,
        nullable=False
    )

    # Metadata
    requester: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )
    status: Mapped[StatusEnum] = mapped_column(
        SQLEnum(StatusEnum, values_callable=lambda x: [e.value for e in x]),
        default=StatusEnum.PENDING,
        nullable=False
    )
    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # External links
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Source
    source: Mapped[TaskSourceEnum] = mapped_column(
        SQLEnum(TaskSourceEnum, values_callable=lambda x: [e.value for e in x]),
        default=TaskSourceEnum.API,
        nullable=False
    )
    conversation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Dependencies (stored as JSON arrays of task IDs)
    depends_on: Mapped[List[str]] = mapped_column(JSON, default=list)
    blocks: Mapped[List[str]] = mapped_column(JSON, default=list)

    # Relationship to feedback (one-to-one)
    feedback: Mapped[Optional["TaskFeedback"]] = relationship(
        "TaskFeedback",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Task(id='{self.id}', title='{self.title}', status='{self.status}')>"


class TaskFeedback(Base):
    """Feedback on completed tasks."""

    __tablename__ = "task_feedback"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True, default=lambda: f"FB-{uuid.uuid4().hex[:8].upper()}")

    # Foreign key to task
    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("tasks.id"), nullable=False, unique=True)

    # Effort accuracy
    estimated_duration: Mapped[str] = mapped_column(String(50), nullable=False)
    actual_duration: Mapped[str] = mapped_column(String(50), nullable=False)
    complexity_rating: Mapped[int] = mapped_column(nullable=False)

    # Routing accuracy
    was_good_match: Mapped[bool] = mapped_column(nullable=False)
    should_have_routed_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    routing_feedback: Mapped[str] = mapped_column(Text, nullable=False)

    # Quality
    quality_score: Mapped[float] = mapped_column(nullable=False)
    required_rework: Mapped[bool] = mapped_column(nullable=False)
    rework_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Learning
    unexpected_blockers: Mapped[List[str]] = mapped_column(JSON, default=list)
    required_skills_not_tagged: Mapped[List[str]] = mapped_column(JSON, default=list)

    # General
    notes: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationship back to task
    task: Mapped["Task"] = relationship("Task", back_populates="feedback")

    def __repr__(self) -> str:
        return f"<TaskFeedback(id='{self.id}', task_id='{self.task_id}')>"
