"""Regression tests for hopper_instances auto-creation on the records write path.

`write_revision` (and thus every records-backend write, including the now-default
REST task backend and the local SQLite store) calls
`RevisionShadowWriter._ensure_instance`, which raw-INSERTs a hopper_instances row
when one does not yet exist. That INSERT previously omitted the NOT-NULL
`instance_type` column (crashing the first write on a fresh DB) and stored enum
*values* rather than the *names* SQLAlchemy reads back for native_enum=False
columns (so the row could not be loaded via the ORM). These tests pin both fixes.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, Record
from hopper.storage.revision_writer import AuthorContext, write_revision


def _author() -> AuthorContext:
    return AuthorContext(did="did:key:ztest", location="test")


def test_write_revision_on_fresh_db_creates_readable_instance(db_session: Session) -> None:
    """First records write on a fresh DB must succeed AND leave an ORM-readable instance row."""
    instance_id = "BrandNewInstance"
    # No hopper_instances row exists yet — this is the path that used to crash.
    assert (
        db_session.execute(
            select(HopperInstance).where(HopperInstance.id == instance_id)
        ).scalar_one_or_none()
        is None
    )

    write_revision(
        db_session,
        task_payload={"id": "t0001", "title": "first", "kind": "task"},
        author=_author(),
        instance_id=instance_id,
    )
    db_session.flush()

    # The record was written...
    rec = db_session.execute(select(Record).where(Record.id == "t0001")).scalar_one()
    assert rec.type == "task"

    # ...and the auto-created instance round-trips through the ORM (enum names valid).
    inst = db_session.execute(
        select(HopperInstance).where(HopperInstance.id == instance_id)
    ).scalar_one()
    assert inst.instance_type is not None  # NOT NULL satisfied
    assert inst.status is not None
    assert inst.scope is not None


def test_ensure_instance_is_idempotent(db_session: Session) -> None:
    """A second write to the same instance must not duplicate or crash."""
    instance_id = "RepeatInstance"
    write_revision(
        db_session,
        task_payload={"id": "t0002", "title": "a", "kind": "task"},
        author=_author(),
        instance_id=instance_id,
    )
    write_revision(
        db_session,
        task_payload={"id": "t0003", "title": "b", "kind": "memory"},
        author=_author(),
        instance_id=instance_id,
    )
    db_session.flush()

    rows = (
        db_session.execute(select(HopperInstance).where(HopperInstance.id == instance_id))
        .scalars()
        .all()
    )
    assert len(rows) == 1
