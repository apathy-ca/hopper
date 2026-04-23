"""Revision model.

Revisions are append-only. Every write to a Record produces one Revision.
Revisions are never updated in place — reject/tombstone are themselves
revisions layered on top. The full history of a record is reconstructible
by walking revisions.record_id in created_at order.

Each revision carries:
- author_did: the principal who performed the write (did:key:...).
- author_location: the context of the write ('ember-cli', 'phone-claude',
  'waypoint-skill', 'audit-agent@ember', etc.). A per-write signal surface,
  not just a per-record one.
- action: one of RevisionAction values. 'propose' does not advance the
  record's current_revision_id; 'apply' does.
- payload: full snapshot of the record's state at this revision (JSON).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .base import Base

SCHEMA_VERSION = 1


class Revision(Base):
    __tablename__ = "revisions"

    # ULID — 26 char Crockford base32, sorts by creation time
    id: Mapped[str] = mapped_column(String(26), primary_key=True)

    record_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("records.id"), nullable=False
    )
    parent_revision_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("revisions.id"), nullable=True
    )

    action: Mapped[str] = mapped_column(String(20), nullable=False)

    # did:key:... identifying the principal (human DID or agent DID).
    # Nullable only for backfilled rows where the historical from_did is
    # unknown; new writes must carry a DID.
    author_did: Mapped[str | None] = mapped_column(String(200), nullable=True)
    author_location: Mapped[str | None] = mapped_column(String(100), nullable=True)

    payload: Mapped[dict | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    schema_version: Mapped[int] = mapped_column(
        Integer, default=SCHEMA_VERSION, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, nullable=False
    )

    __table_args__ = (
        Index("idx_revisions_record_created", "record_id", "created_at"),
        Index("idx_revisions_author_did", "author_did"),
        Index("idx_revisions_action", "action"),
    )

    def __repr__(self) -> str:
        return (
            f"<Revision(id={self.id}, record_id={self.record_id}, "
            f"action={self.action})>"
        )
