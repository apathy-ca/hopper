"""Instance relationship model for DAG-based instance hierarchy."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from hopper.timeutils import utc_now_naive

from .base import Base


class InstanceRelationship(Base):
    """Edge in the instance DAG: parent oversees child."""

    __tablename__ = "instance_relationships"

    parent_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("hopper_instances.id", ondelete="CASCADE"),
        primary_key=True,
    )
    child_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("hopper_instances.id", ondelete="CASCADE"),
        primary_key=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, nullable=False)

    def __repr__(self) -> str:
        return f"<InstanceRelationship({self.parent_id} -> {self.child_id})>"
