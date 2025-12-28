"""
Project model - Project registry and configuration.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .routing_decision import RoutingDecision


class Project(Base, TimestampMixin):
    """
    Project represents a registered project that can receive tasks.

    Projects define capabilities, executor configuration, and sync settings
    for integration with external platforms.
    """

    __tablename__ = "projects"

    # Primary identification
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    repository: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Project capabilities
    capabilities: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    # Executor configuration
    executor_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    executor_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Routing preferences
    auto_claim: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority_boost: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    velocity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sla: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Integration endpoints
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    api_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Sync configuration
    sync_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Metadata
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    routing_decisions: Mapped[list["RoutingDecision"]] = relationship(
        "RoutingDecision", back_populates="project_obj"
    )

    def __repr__(self) -> str:
        return f"<Project(name={self.name}, executor_type={self.executor_type})>"
