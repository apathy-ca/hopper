"""
Project model for Hopper.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class Project(Base):
    """Project model representing a work destination."""

    __tablename__ = "projects"

    # Primary key
    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    repository: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Capabilities and tags
    capabilities: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    tags: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Executor configuration
    executor_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    executor_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Project settings
    auto_claim: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    priority_boost: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    velocity: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    sla: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Integration endpoints
    webhook_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Sync configuration
    sync_config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Metadata
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_sync: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<Project(name={self.name}, slug={self.slug})>"
