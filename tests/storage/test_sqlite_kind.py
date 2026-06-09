"""Tests for kind/type read-back on the SQLite task store.

The real record kind lives in records.type (written via the revision path),
not in the tasks table. These tests prove TaskSQLiteStore surfaces that real
type instead of the old hardcoded "task".
"""

import tempfile
from pathlib import Path

import pytest

from hopper.storage.base import StorageConfig
from hopper.storage.revision_writer import AuthorContext
from hopper.storage.sqlite import SQLiteStorage
from hopper.storage.sqlite_tasks import TaskSQLiteStore
from hopper.storage.tasks import LocalTask


@pytest.fixture
def sqlite_storage():
    """Create initialized SQLite storage in a temp dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config = StorageConfig.local(Path(tmpdir))
        storage = SQLiteStorage(config, db_path=Path(tmpdir) / "hopper.db")
        storage.initialize()
        yield storage
        storage.dispose()


@pytest.fixture
def sqlite_store(sqlite_storage):
    return TaskSQLiteStore(sqlite_storage)


@pytest.fixture
def author():
    return AuthorContext(did="did:key:test", location="cli")


class TestSQLiteKindReadBack:
    def test_kind_round_trips_from_records_type(self, sqlite_store, author):
        """A record created with kind="memory" reads back as kind="memory"."""
        memory = LocalTask.create(title="A memory", kind="memory")
        sqlite_store.create(memory, author=author)

        loaded = sqlite_store.get(memory.id)
        assert loaded is not None
        assert loaded.kind == "memory"

    def test_default_task_kind(self, sqlite_store, author):
        """A record created without a kind defaults to "task"."""
        task = LocalTask.create(title="A task")
        sqlite_store.create(task, author=author)

        loaded = sqlite_store.get(task.id)
        assert loaded is not None
        assert loaded.kind == "task"

    def test_list_surfaces_real_kind(self, sqlite_store, author):
        """list() returns the real kind for each row, not a hardcoded value."""
        sqlite_store.create(LocalTask.create(title="A task"), author=author)
        sqlite_store.create(LocalTask.create(title="A memory", kind="memory"), author=author)

        by_id = {t.title: t.kind for t in sqlite_store.list()}
        assert by_id["A task"] == "task"
        assert by_id["A memory"] == "memory"

    def test_filter_by_kind(self, sqlite_store, author):
        """list(kind="memory") returns only memory records."""
        sqlite_store.create(LocalTask.create(title="A task"), author=author)
        memory = LocalTask.create(title="A memory", kind="memory")
        sqlite_store.create(memory, author=author)

        memories = sqlite_store.list(kind="memory")
        assert [m.id for m in memories] == [memory.id]

        tasks = sqlite_store.list(kind="task")
        assert memory.id not in {t.id for t in tasks}
