"""Record model.

A Record is the unit of identity in Hopper. Tasks, ideas, notes, and logs
are all records differentiated by the `type` column. The record row itself
is a thin pointer; the authoritative state at any point in time lives in
the Revision history. `current_revision_id` names the most recent applied
revision.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Record(Base, TimestampMixin):
    __tablename__ = "records"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)

    instance_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("hopper_instances.id"), nullable=True
    )

    # Nullable during the initial insert transaction; application logic
    # sets it to the id of the first 'create' revision within the same
    # transaction. Never null for a record that has been successfully saved.
    current_revision_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("revisions.id", use_alter=True), nullable=True
    )

    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_records_type", "type"),
        Index("idx_records_instance_id", "instance_id"),
        Index("idx_records_tombstoned_at", "tombstoned_at"),
    )

    def __repr__(self) -> str:
        return f"<Record(id={self.id}, type={self.type})>"
