"""Tests for kind/type read-back on the records+revisions backend.

The real record kind lives in records.type (written via the revision path).
These tests prove RecordTaskRepository surfaces that real type correctly.
The legacy tasks table was dropped in Phase 5; these tests use the
records-backed repository which is the current canonical path.
"""

from hopper.api.repositories.record_tasks import RecordTaskRepository

_AUTHOR_DID = "did:key:testauthor"
_AUTHOR_LOC = "cli:test"


class TestSQLiteKindReadBack:
    def test_kind_round_trips_from_records_type(self, db_session):
        """A record created with kind="memory" reads back as kind="memory"."""
        repo = RecordTaskRepository(db_session)
        created = repo.create(
            {"title": "A memory", "kind": "memory"},
            author_did=_AUTHOR_DID,
            author_location=_AUTHOR_LOC,
        )
        db_session.flush()

        loaded = repo.get(created["id"])
        assert loaded is not None
        assert loaded["kind"] == "memory"

    def test_default_task_kind(self, db_session):
        """A record created without an explicit kind defaults to "task"."""
        repo = RecordTaskRepository(db_session)
        created = repo.create(
            {"title": "A task"},
            author_did=_AUTHOR_DID,
            author_location=_AUTHOR_LOC,
        )
        db_session.flush()

        loaded = repo.get(created["id"])
        assert loaded is not None
        assert loaded["kind"] == "task"

    def test_list_surfaces_real_kind(self, db_session):
        """list() returns the real kind for each record, not a hardcoded value."""
        repo = RecordTaskRepository(db_session)
        repo.create(
            {"title": "A task"},
            author_did=_AUTHOR_DID,
            author_location=_AUTHOR_LOC,
        )
        repo.create(
            {"title": "A memory", "kind": "memory"},
            author_did=_AUTHOR_DID,
            author_location=_AUTHOR_LOC,
        )
        db_session.flush()

        tasks, _ = repo.list(kind="task")
        memories, _ = repo.list(kind="memory")

        task_titles = {t["title"] for t in tasks}
        memory_titles = {m["title"] for m in memories}

        assert "A task" in task_titles
        assert "A memory" in memory_titles
        assert "A memory" not in task_titles
        assert "A task" not in memory_titles

    def test_filter_by_kind(self, db_session):
        """list(kind="memory") returns only memory records."""
        repo = RecordTaskRepository(db_session)
        repo.create(
            {"title": "A task"},
            author_did=_AUTHOR_DID,
            author_location=_AUTHOR_LOC,
        )
        mem = repo.create(
            {"title": "A memory", "kind": "memory"},
            author_did=_AUTHOR_DID,
            author_location=_AUTHOR_LOC,
        )
        db_session.flush()

        memories, _ = repo.list(kind="memory")
        assert len(memories) == 1
        assert memories[0]["id"] == mem["id"]

        tasks, _ = repo.list(kind="task")
        assert all(t["id"] != mem["id"] for t in tasks)
