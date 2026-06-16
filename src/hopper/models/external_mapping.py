"""
External Mapping model for Hopper.
"""

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExternalMapping(Base):
    """External Mapping model for syncing with external platforms."""

    __tablename__ = "external_mappings"

    # Composite primary key (FK to records — the canonical server-side store)
    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("records.id"), primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), primary_key=True)

    # External identifiers
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Indexes for efficient lookups by external_id
    __table_args__ = (
        Index("idx_external_mappings_external_id", "external_id"),
        Index("idx_external_mappings_external_id_platform", "external_id", "platform"),
    )

    def __repr__(self) -> str:
        return f"<ExternalMapping(task_id={self.task_id}, platform={self.platform})>"
