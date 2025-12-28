"""
Hopper Instance model for multi-instance support.
"""
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from .base import Base, TimestampMixin


class HopperInstance(Base, TimestampMixin):
    """Hopper Instance model for hierarchical instance management."""

    __tablename__ = "hopper_instances"

    # Primary key
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Instance details
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    scope: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # GLOBAL, PROJECT, ORCHESTRATION

    # Hierarchy
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(100), ForeignKey("hopper_instances.id"), nullable=True
    )

    # Configuration
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(50), default="active", nullable=False
    )  # active, paused, terminated

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    parent: Mapped[Optional["HopperInstance"]] = relationship(
        "HopperInstance", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["HopperInstance"]] = relationship(
        "HopperInstance", back_populates="parent"
    )

    def __repr__(self) -> str:
        return f"<HopperInstance(id={self.id}, name={self.name}, scope={self.scope})>"
