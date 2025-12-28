"""
Task model for Hopper.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class Task(Base, TimestampMixin):
    """Task model representing a unit of work."""

    __tablename__ = "tasks"

    # Primary key
    id: Mapped[str] = mapped_column(String(50), primary_key=True)

    # Instance association
    instance_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("hopper_instances.id"), nullable=True
    )

    # Basic info
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)

    # Metadata
    requester: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    owner: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # External links
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    external_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    external_platform: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Context
    source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Arrays/JSON - use JSONB for PostgreSQL, JSON for SQLite
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    required_capabilities: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    depends_on: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    blocks: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Routing
    routing_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    routing_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
    external_mappings: Mapped[List["ExternalMapping"]] = relationship(
        "ExternalMapping", back_populates="task"
    )

    # Indexes
    __table_args__ = (
        Index("idx_tasks_project", "project"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_created_at", "created_at"),
        # GIN index for JSONB tags (PostgreSQL only)
        # Index("idx_tasks_tags", "tags", postgresql_using="gin"),
    )

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, title={self.title}, status={self.status})>"
