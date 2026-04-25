"""RevisionWriter — append-only revision persistence for Phase 4b.

Every mutating SQLite task write must produce a Record + Revision row with
non-null author_did and author_location.  This module is the single place that
logic lives; TaskSQLiteStore, LocalClient, and any future write path all go
through here.

Unlike the upstream shadow writer (which is fail-soft by design), this writer
is *fail-hard*: if a revision cannot be written the whole write is rolled back.
The JSON markdown path is no longer the source of truth once SQLite is the
primary backend.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from hopper.models import Record, RecordType, Revision, RevisionAction, new_ulid
from hopper.models.revision import SCHEMA_VERSION
from hopper.upstream.shadow import RevisionShadowWriter  # for _ensure_instance

logger = logging.getLogger(__name__)

# Sentinel used when the DID key file doesn't exist yet (fresh install).
_UNKNOWN_DID = "did:key:unknown"


@dataclass(frozen=True)
class AuthorContext:
    """Identity and location of a write."""

    did: str
    location: str

    def __post_init__(self) -> None:
        if not self.did:
            raise ValueError("AuthorContext.did must not be empty")
        if not self.location:
            raise ValueError("AuthorContext.location must not be empty")


def write_revision(
    session: Session,
    task_payload: dict[str, Any],
    author: AuthorContext,
    action: str | None = None,
    *,
    instance_id: str = "local",
) -> str:
    """Upsert a Record and insert a Revision row within an existing session.

    The caller is responsible for committing the session.  This function does
    NOT commit — it only flushes so that FK constraints are satisfied before
    the caller's own flush/commit.

    Args:
        session: An active SQLAlchemy session (not yet committed for this write).
        task_payload: Full task dict snapshot (stored verbatim in revision.payload).
        author: Non-null identity for this write.
        action: Override the RevisionAction string.  Auto-detected (create vs
            update) when None.
        instance_id: The hopper instance name for the Record row.

    Returns:
        The new revision ID (ULID string).
    """
    task_id = task_payload.get("id")
    if not task_id:
        raise ValueError("task_payload must contain 'id'")

    # Ensure hopper_instances row exists (raw SQL, same approach as shadow writer)
    RevisionShadowWriter._ensure_instance(session, instance_id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    existing = session.get(Record, task_id)
    revision_id = new_ulid()

    # Derive record type from payload kind field; fall back to TASK
    raw_kind = task_payload.get("kind", "task")
    try:
        record_type = RecordType(raw_kind).value
    except ValueError:
        record_type = RecordType.TASK.value

    if existing is None:
        resolved_action = action or RevisionAction.CREATE.value
        parent_revision_id = None
        record = Record(
            id=task_id,
            type=record_type,
            instance_id=instance_id if not instance_id.startswith(".") else None,
            current_revision_id=None,
            created_at=now,
            updated_at=now,
        )
        session.add(record)
        session.flush()
    else:
        resolved_action = action or RevisionAction.UPDATE.value
        parent_revision_id = existing.current_revision_id
        existing.updated_at = now

    revision = Revision(
        id=revision_id,
        record_id=task_id,
        parent_revision_id=parent_revision_id,
        action=resolved_action,
        author_did=author.did,
        author_location=author.location,
        payload=task_payload,
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )
    session.add(revision)
    session.flush()

    # Advance current_revision pointer
    if existing is None:
        record.current_revision_id = revision_id
    else:
        existing.current_revision_id = revision_id

    return revision_id


def propose_revision(
    session: Session,
    task_payload: dict[str, Any],
    author: AuthorContext,
    *,
    instance_id: str = "local",
) -> str:
    """Insert a 'propose' revision WITHOUT advancing current_revision_id.

    The record's current state is unchanged until an 'apply' revision follows.
    This is the safe path for agent writes that require human review.

    Returns:
        The new revision ID (proposal that can be applied or rejected).
    """
    task_id = task_payload.get("id")
    if not task_id:
        raise ValueError("task_payload must contain 'id'")

    RevisionShadowWriter._ensure_instance(session, instance_id)

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    existing = session.get(Record, task_id)
    if existing is None:
        raise ValueError(f"Record {task_id!r} does not exist — cannot propose on unknown record")

    revision_id = new_ulid()
    revision = Revision(
        id=revision_id,
        record_id=task_id,
        parent_revision_id=existing.current_revision_id,
        action=RevisionAction.PROPOSE.value,
        author_did=author.did,
        author_location=author.location,
        payload=task_payload,
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )
    session.add(revision)
    session.flush()
    # NOTE: current_revision_id is intentionally NOT updated for proposals
    return revision_id


def apply_revision(
    session: Session,
    revision_id: str,
    author: AuthorContext,
) -> str:
    """Apply a pending proposal: insert an 'apply' revision and advance the record pointer.

    Returns:
        The new 'apply' revision ID.
    """
    from hopper.models import Revision as RevisionModel

    proposal = session.get(RevisionModel, revision_id)
    if proposal is None:
        raise ValueError(f"Revision {revision_id!r} not found")
    if proposal.action != RevisionAction.PROPOSE.value:
        raise ValueError(f"Revision {revision_id!r} has action={proposal.action!r}, not 'propose'")

    record = session.get(Record, proposal.record_id)
    if record is None:
        raise ValueError(f"Record {proposal.record_id!r} not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    apply_rev_id = new_ulid()

    apply_rev = Revision(
        id=apply_rev_id,
        record_id=proposal.record_id,
        parent_revision_id=revision_id,
        action=RevisionAction.APPLY.value,
        author_did=author.did,
        author_location=author.location,
        payload=proposal.payload,  # same payload as the proposal
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )
    session.add(apply_rev)
    session.flush()

    record.current_revision_id = apply_rev_id
    record.updated_at = now
    return apply_rev_id


def reject_revision(
    session: Session,
    revision_id: str,
    author: AuthorContext,
    reason: str | None = None,
) -> str:
    """Reject a pending proposal: insert a 'reject' revision. Does not touch the record pointer.

    Returns:
        The new 'reject' revision ID.
    """
    from hopper.models import Revision as RevisionModel

    proposal = session.get(RevisionModel, revision_id)
    if proposal is None:
        raise ValueError(f"Revision {revision_id!r} not found")
    if proposal.action != RevisionAction.PROPOSE.value:
        raise ValueError(f"Revision {revision_id!r} has action={proposal.action!r}, not 'propose'")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    reject_rev_id = new_ulid()
    payload = dict(proposal.payload or {})
    if reason:
        payload["_rejection_reason"] = reason

    reject_rev = Revision(
        id=reject_rev_id,
        record_id=proposal.record_id,
        parent_revision_id=revision_id,
        action=RevisionAction.REJECT.value,
        author_did=author.did,
        author_location=author.location,
        payload=payload,
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )
    session.add(reject_rev)
    session.flush()
    return reject_rev_id


def tombstone_revision(
    session: Session,
    task_id: str,
    author: AuthorContext,
    task_payload: dict[str, Any],
    *,
    instance_id: str = "local",
) -> str:
    """Insert a tombstone revision and mark the Record as tombstoned.

    Used by mark_deleted / delete to record soft-delete in revision history.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    existing = session.get(Record, task_id)

    revision_id = new_ulid()
    parent_revision_id = existing.current_revision_id if existing else None

    if existing is not None:
        existing.tombstoned_at = now
        existing.updated_at = now

    revision = Revision(
        id=revision_id,
        record_id=task_id,
        parent_revision_id=parent_revision_id,
        action=RevisionAction.TOMBSTONE.value,
        author_did=author.did,
        author_location=author.location,
        payload=task_payload,
        schema_version=SCHEMA_VERSION,
        created_at=now,
    )
    session.add(revision)
    session.flush()

    if existing is not None:
        existing.current_revision_id = revision_id

    return revision_id
