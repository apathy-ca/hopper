"""Tests for append-only task notes on LocalTask (markdown backend).

Notes let one agent leave an attributed, timestamped finding on a task another
agent owns, without overwriting the description. These tests prove notes
round-trip through the markdown store, stay append-only, and that ordinary
tasks stay clean.
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


def test_add_note_round_trip(task_store):
    """A note survives a save + reload with author, timestamp, and body."""
    task = LocalTask.create(title="Owned by another agent")
    task_store.create(task)

    updated = task_store.add_note(
        task.id, "finding: stale residuals in recompute", author="claude:reviewer"
    )
    assert updated is not None

    loaded = task_store.get(task.id)
    assert loaded is not None
    assert len(loaded.notes) == 1
    note = loaded.notes[0]
    assert note["author"] == "claude:reviewer"
    assert note["body"] == "finding: stale residuals in recompute"
    assert note["ts"]  # timestamp present


def test_notes_are_append_only_and_ordered(task_store):
    """Multiple notes accumulate oldest-first; earlier notes are never lost."""
    task = LocalTask.create(title="Multi-note task")
    task_store.create(task)

    task_store.add_note(task.id, "first", author="human:james")
    task_store.add_note(task.id, "second", author="claude:worker")
    task_store.add_note(task.id, "third")  # default author

    loaded = task_store.get(task.id)
    assert [n["body"] for n in loaded.notes] == ["first", "second", "third"]
    assert loaded.notes[0]["author"] == "human:james"
    assert loaded.notes[2]["author"] == "unknown"


def test_note_does_not_touch_description(task_store):
    """Adding a note leaves the description untouched (non-destructive)."""
    task = LocalTask.create(title="Has a description", description="original body")
    task_store.create(task)

    task_store.add_note(task.id, "a finding", author="claude:reviewer")

    loaded = task_store.get(task.id)
    assert loaded.description == "original body"
    assert len(loaded.notes) == 1


def test_add_note_to_missing_task_returns_none(task_store):
    """Noting a nonexistent task is a no-op returning None (not a crash)."""
    assert task_store.add_note("tdeadbeef", "body", author="x") is None


def test_ordinary_task_has_no_notes_frontmatter(task_store):
    """Plain tasks don't get an empty notes key written to frontmatter."""
    task = LocalTask.create(title="Fix the bug")
    fm = task.to_frontmatter()
    assert "notes" not in fm
