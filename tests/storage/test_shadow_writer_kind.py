"""Regression tests for record `type` derivation in RevisionShadowWriter.

`record_write` previously hardcoded `Record.type = RecordType.TASK.value` for
every JSON upstream write, regardless of the payload's `kind` field. That made
the records/revisions backend (and any kind-segmented REST view) misreport
every memory/idea/note/job/etc as `type="task"`. The fix derives `type` from
`task_payload["kind"]`, mirroring `storage.revision_writer.write_revision`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import Record
from hopper.models.base import Base
from hopper.upstream.shadow import RevisionShadowWriter


def _writer(tmp_path) -> RevisionShadowWriter:
    writer = RevisionShadowWriter(f"sqlite:///{tmp_path / 'shadow.db'}")
    Base.metadata.create_all(bind=writer._engine)
    return writer


def test_record_write_uses_kind_for_record_type(tmp_path) -> None:
    writer = _writer(tmp_path)

    writer.record_write(
        {"id": "t0001", "title": "a memory", "kind": "memory", "instance": "local"},
        from_did="did:key:ztest",
        received_at_ms=1_000,
    )

    with Session(writer._engine) as session:
        rec = session.execute(select(Record).where(Record.id == "t0001")).scalar_one()
        assert rec.type == "memory"


def test_record_write_defaults_to_task_for_missing_or_unknown_kind(tmp_path) -> None:
    writer = _writer(tmp_path)

    writer.record_write(
        {"id": "t0002", "title": "no kind", "instance": "local"},
        from_did="did:key:ztest",
        received_at_ms=1_000,
    )
    writer.record_write(
        {"id": "t0003", "title": "bogus kind", "kind": "not-a-real-kind", "instance": "local"},
        from_did="did:key:ztest",
        received_at_ms=1_000,
    )

    with Session(writer._engine) as session:
        rec2 = session.execute(select(Record).where(Record.id == "t0002")).scalar_one()
        rec3 = session.execute(select(Record).where(Record.id == "t0003")).scalar_one()
        assert rec2.type == "task"
        assert rec3.type == "task"


def test_record_write_updates_type_when_kind_changes(tmp_path) -> None:
    """An inbox item later triaged to e.g. `idea` should update record.type."""
    writer = _writer(tmp_path)

    writer.record_write(
        {"id": "t0004", "title": "untriaged", "kind": "inbox", "instance": "local"},
        from_did="did:key:ztest",
        received_at_ms=1_000,
    )
    writer.record_write(
        {"id": "t0004", "title": "untriaged", "kind": "idea", "instance": "local"},
        from_did="did:key:ztest",
        received_at_ms=2_000,
    )

    with Session(writer._engine) as session:
        rec = session.execute(select(Record).where(Record.id == "t0004")).scalar_one()
        assert rec.type == "idea"
