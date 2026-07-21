"""Tests for immutable creator attribution on records (markdown backend).

Every record kind (task/idea/note/memory/…) shares LocalTask, so creator
attribution stamped here covers all of them. created_by is a human-readable
identity; created_by_did is the did:key principal. Both are stamped once at
creation and must survive edits unchanged.
"""

import tempfile
from pathlib import Path

import pytest

from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore
from hopper.storage.tasks import LocalTask


@pytest.fixture
def temp_storage_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_store(temp_storage_path):
    config = StorageConfig.local(temp_storage_path)
    storage = MarkdownStorage(config)
    storage.initialize()
    return TaskMarkdownStore(storage)


def test_creator_round_trip(task_store):
    """created_by / created_by_did survive a save + reload."""
    task = LocalTask.create(
        title="Owned record",
        created_by="human:james",
        created_by_did="did:key:z6MkExample",
    )
    task_store.create(task)

    loaded = task_store.get(task.id)
    assert loaded is not None
    assert loaded.created_by == "human:james"
    assert loaded.created_by_did == "did:key:z6MkExample"


def test_creator_is_immutable_across_edits(task_store):
    """Editing a task (status, tags, notes) never changes its creator."""
    task = LocalTask.create(title="Immutable creator", created_by="claude:maker")
    task_store.create(task)

    task_store.update_status(task.id, "in_progress")
    task_store.add_tags(task.id, ["reviewed"])
    task_store.add_note(task.id, "a later note", author="claude:other")

    loaded = task_store.get(task.id)
    assert loaded.created_by == "claude:maker"


def test_creator_applies_to_all_kinds(task_store):
    """A memory record carries creator attribution just like a task."""
    mem = LocalTask.create(
        title="A durable fact",
        kind="memory",
        created_by="claude:consolidator",
    )
    task_store.create(mem)

    loaded = task_store.get(mem.id)
    assert loaded.kind == "memory"
    assert loaded.created_by == "claude:consolidator"


def test_ordinary_task_has_no_creator_frontmatter(task_store):
    """Records created without an identity don't get empty creator keys."""
    task = LocalTask.create(title="Anonymous task")
    fm = task.to_frontmatter()
    assert "created_by" not in fm
    assert "created_by_did" not in fm
