"""Tests for consolidation structured fields on LocalTask (markdown backend).

memory_class, superseded_by, source_record_ids, consolidation_run_id,
consolidated_at, drift_checked_at, and drift_score should round-trip through
the markdown store and only appear in frontmatter when set.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore
from hopper.storage.tasks import LocalTask


@pytest.fixture
def tempstorage_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def task_store(tempstorage_path):
    config = StorageConfig.local(tempstorage_path)
    storage = MarkdownStorage(config)
    storage.initialize()
    return TaskMarkdownStore(storage)


def test_consolidation_fields_round_trip(task_store):
    """All seven consolidation fields survive save + reload."""
    now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=UTC)
    mem = LocalTask.create(
        title="Consolidated: agent routing preferences",
        kind="memory",
        subject="project:waypoint",
        memory_class="consolidated",
        source_record_ids=["rec-001", "rec-002", "rec-003"],
        consolidation_run_id="consolidate-abc12345",
        consolidated_at=now,
        drift_checked_at=now,
        drift_score=0.05,
        superseded_by=None,
    )
    task_store.create(mem)
    loaded = task_store.get(mem.id)

    assert loaded is not None
    assert loaded.memory_class == "consolidated"
    assert loaded.source_record_ids == ["rec-001", "rec-002", "rec-003"]
    assert loaded.consolidation_run_id == "consolidate-abc12345"
    assert loaded.consolidated_at is not None
    assert loaded.drift_checked_at is not None
    assert loaded.drift_score == pytest.approx(0.05)
    assert loaded.superseded_by is None


def test_superseded_by_round_trip(task_store):
    """superseded_by is written and loaded correctly."""
    source = LocalTask.create(
        title="Old observation about agent timing",
        kind="memory",
        subject="project:waypoint",
        memory_class="episodic",
    )
    task_store.create(source)

    source.superseded_by = "consolidated-record-xyz"
    task_store.save(source)

    loaded = task_store.get(source.id)
    assert loaded is not None
    assert loaded.superseded_by == "consolidated-record-xyz"
    assert loaded.memory_class == "episodic"


def test_ordinary_task_stays_clean(task_store):
    """Non-memory tasks have no consolidation frontmatter fields."""
    task = LocalTask.create(title="Fix the login bug")
    task_store.create(task)

    task_file = None
    for f in (task_store.storage.base_path / "tasks").rglob("*.md"):
        if task.id in f.name or task.id in f.read_text():
            task_file = f
            break

    assert task_file is not None, "task file not found"
    content = task_file.read_text()
    for field in (
        "memory_class", "superseded_by", "source_record_ids",
        "consolidation_run_id", "consolidated_at", "drift_checked_at", "drift_score",
    ):
        assert field not in content, f"field {field!r} leaked into ordinary task frontmatter"


def test_empty_source_record_ids_not_written(task_store):
    """Empty source_record_ids list does not appear in frontmatter."""
    mem = LocalTask.create(
        title="Raw episodic memory",
        kind="memory",
        memory_class="episodic",
    )
    task_store.create(mem)

    task_file = None
    for f in (task_store.storage.base_path / "tasks").rglob("*.md"):
        if mem.id in f.name or mem.id in f.read_text():
            task_file = f
            break

    assert task_file is not None, "task file not found"
    content = task_file.read_text()
    assert "source_record_ids" not in content


def test_memory_class_index_filter(task_store):
    """list(memory_class=...) returns only matching records."""
    ep = LocalTask.create(title="Episodic memory", kind="memory", memory_class="episodic")
    con = LocalTask.create(title="Consolidated memory", kind="memory", memory_class="consolidated")
    plain = LocalTask.create(title="Plain task")
    for t in (ep, con, plain):
        task_store.create(t)

    episodics = task_store.list(kind="memory", memory_class="episodic")
    assert any(t.id == ep.id for t in episodics)
    assert not any(t.id == con.id for t in episodics)
    assert not any(t.id == plain.id for t in episodics)

    consolidated = task_store.list(kind="memory", memory_class="consolidated")
    assert any(t.id == con.id for t in consolidated)
    assert not any(t.id == ep.id for t in consolidated)
