"""
External Mapping model for Hopper.
"""


from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ExternalMapping(Base):
    """External Mapping model for syncing with external platforms."""

    __tablename__ = "external_mappings"

    # Composite primary key
    task_id: Mapped[str] = mapped_column(String(50), ForeignKey("tasks.id"), primary_key=True)
    platform: Mapped[str] = mapped_column(String(50), primary_key=True)

    # External identifiers
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    external_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    task: Mapped["Task"] = relationship("Task", back_populates="external_mappings")

    def __repr__(self) -> str:
        return f"<ExternalMapping(task_id={self.task_id}, platform={self.platform})>"
