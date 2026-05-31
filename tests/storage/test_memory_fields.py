"""Tests for memory structured fields on LocalTask (markdown backend).

Memory records carry subject/scope/provenance as real frontmatter fields
(not a text preamble). These tests prove those fields round-trip through
the markdown store and that ordinary tasks stay clean.
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


def test_memory_fields_round_trip(task_store):
    """subject/scope/provenance survive a save + reload."""
    mem = LocalTask.create(
        title="User prefers terse responses",
        kind="memory",
        subject="user:preferences",
        scope="shared-with-user",
        provenance="conversation 2026-05-30",
    )
    task_store.create(mem)

    loaded = task_store.get(mem.id)
    assert loaded is not None
    assert loaded.kind == "memory"
    assert loaded.subject == "user:preferences"
    assert loaded.scope == "shared-with-user"
    assert loaded.provenance == "conversation 2026-05-30"


def test_ordinary_task_has_no_memory_frontmatter(task_store):
    """Plain tasks don't get empty subject/scope/provenance keys written."""
    task = LocalTask.create(title="Fix the bug")
    fm = task.to_frontmatter()
    assert "subject" not in fm
    assert "scope" not in fm
    assert "provenance" not in fm


def test_legacy_preamble_memory_still_loads(task_store):
    """Old-shape memory (preamble in body, no fields) loads without error."""
    legacy = LocalTask.create(
        title="Legacy memory",
        description="Subject: user:preferences\nScope: shared-with-user\n\nThe content.",
        kind="memory",
    )
    task_store.create(legacy)

    loaded = task_store.get(legacy.id)
    assert loaded is not None
    assert loaded.kind == "memory"
    # No structured fields on the legacy record — they live in the body.
    assert loaded.subject is None
    assert "Subject: user:preferences" in (loaded.description or "")
