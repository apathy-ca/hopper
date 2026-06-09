"""
Base SQLAlchemy models and utilities.
"""

from datetime import datetime

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from hopper.timeutils import utc_now_naive

# Explicit naming convention so Alembic batch-mode on SQLite can drop/recreate
# named constraints. Without this, anonymous FKs cannot be renamed in SQLite's
# table-rebuild path.
_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    metadata = MetaData(naming_convention=_NAMING_CONVENTION)


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False
    )
