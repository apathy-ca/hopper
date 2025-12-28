"""
Base models and mixins for Hopper.

Provides common functionality for all SQLAlchemy models.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TimestampMixin:
    """Mixin that adds created_at and updated_at timestamp fields."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Mixin that adds soft delete functionality."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        """Check if this record is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark this record as deleted."""
        self.deleted_at = datetime.now()

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None
