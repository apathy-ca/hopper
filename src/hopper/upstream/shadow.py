"""Revision shadow writer.

Phase 4a (second half). When enabled, server-side task writes additionally
persist a record + revision pair into SQLite. The JSON upstream-data tree
remains authoritative; the SQL store is a shadow that the audit agent,
cross-instance synthesis, and future SQL-first features can read from.

The shadow is strictly **fail-soft**: any exception during a shadow write
is logged and swallowed so the JSON write path — which is the real
source of truth for connected clients today — is never broken by the
new code. A bad shadow write leaves JSON correct and SQL missing a row;
the next write to that record reconciles.

Enabled by setting ``HOPPER_SHADOW_SQLITE_URL`` (SQLAlchemy URL, e.g.
``sqlite:////home/jhenry/.hopper/shadow.db``). When unset, shadow
writing is off and zero code runs in the hot path.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from hopper.models import (
    Record,
    RecordType,
    Revision,
    RevisionAction,
    new_ulid,
)
from hopper.models.revision import SCHEMA_VERSION

logger = logging.getLogger(__name__)


class RevisionShadowWriter:
    """Writes records + revisions to SQLite as a shadow of JSON upstream writes."""

    def __init__(self, database_url: str) -> None:
        self._engine: Engine = create_engine(database_url, future=True)
        self._database_url = database_url
        logger.info("Revision shadow writer active: %s", database_url)

    def record_write(
        self,
        task_payload: dict[str, Any],
        from_did: str | None,
        received_at_ms: int,
    ) -> None:
        """Record a JSON write as a SQL record + revision pair.

        Fail-soft: any exception is logged and swallowed.
        """
        try:
            self._record_write_inner(task_payload, from_did, received_at_ms)
        except Exception as exc:  # noqa: BLE001 — deliberate broad catch
            logger.warning(
                "shadow write failed for task_id=%s: %s",
                task_payload.get("id"),
                exc,
            )

    def _record_write_inner(
        self,
        task_payload: dict[str, Any],
        from_did: str | None,
        received_at_ms: int,
    ) -> None:
        task_id = task_payload.get("id")
        if not task_id:
            logger.warning("shadow write skipped: task payload has no id")
            return

        # Phase 4b: Ensure non-null DID and location
        from_did = from_did or "unknown"
        instance_id = task_payload.get("instance") or "local"
        author_location = task_payload.get("source") or "unknown"
        received_at = datetime.fromtimestamp(received_at_ms / 1000, tz=timezone.utc)
        received_at_naive = received_at.replace(tzinfo=None)

        with Session(self._engine) as session:
            self._ensure_instance(session, instance_id)

            existing = session.get(Record, task_id)
            revision_id = new_ulid()

            if existing is None:
                record = Record(
                    id=task_id,
                    type=RecordType.TASK.value,
                    instance_id=instance_id,
                    current_revision_id=None,
                    created_at=received_at_naive,
                    updated_at=received_at_naive,
                )
                session.add(record)
                session.flush()
                action = RevisionAction.CREATE.value
                parent_revision_id = None
            else:
                action = RevisionAction.UPDATE.value
                parent_revision_id = existing.current_revision_id
                existing.updated_at = received_at_naive

            revision = Revision(
                id=revision_id,
                record_id=task_id,
                parent_revision_id=parent_revision_id,
                action=action,
                author_did=from_did,
                author_location=author_location,
                payload=task_payload,
                schema_version=SCHEMA_VERSION,
                created_at=received_at_naive,
            )
            session.add(revision)
            session.flush()

            # Point current_revision_id at the new revision
            if existing is None:
                record.current_revision_id = revision_id
            else:
                existing.current_revision_id = revision_id

            session.commit()

    @staticmethod
    def _ensure_instance(session: Session, instance_id: str) -> None:
        """Create a hopper_instances row if one doesn't exist.

        Raw SQL because the HopperInstance ORM model may still drift from
        the live schema depending on which migrations have been applied.
        We touch only columns we are confident exist post-initial-migration.
        """
        found = session.execute(
            text("SELECT 1 FROM hopper_instances WHERE id = :id"),
            {"id": instance_id},
        ).first()
        if found is not None:
            return
        now = datetime.utcnow()
        session.execute(
            text(
                "INSERT INTO hopper_instances "
                "(id, name, scope, status, created_at, updated_at) "
                "VALUES (:id, :name, :scope, :status, :now, :now)"
            ),
            {
                "id": instance_id,
                "name": instance_id,
                "scope": "PERSONAL",
                "status": "running",
                "now": now,
            },
        )
