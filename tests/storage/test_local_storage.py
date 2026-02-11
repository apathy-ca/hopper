"""Tests for local markdown storage."""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from hopper.storage import (
    StorageConfig,
    MarkdownStorage,
    TaskMarkdownStore,
    EpisodeMarkdownStore,
    PatternMarkdownStore,
    FeedbackMarkdownStore,
)
from hopper.storage.tasks import LocalTask
from hopper.storage.memory import LocalPattern, LocalEpisode, LocalFeedback


@pytest.fixture
def temp_storage_path():
    """Create a temporary directory for storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def storage(temp_storage_path):
    """Create initialized markdown storage."""
    config = StorageConfig.local(temp_storage_path)
    storage = MarkdownStorage(config)
    storage.initialize()
    return storage


@pytest.fixture
def task_store(storage):
    """Create task store."""
    return TaskMarkdownStore(storage)


@pytest.fixture
def episode_store(storage):
    """Create episode store."""
    return EpisodeMarkdownStore(storage)


@pytest.fixture
def pattern_store(storage):
    """Create pattern store."""
    return PatternMarkdownStore(storage)


@pytest.fixture
def feedback_store(storage):
    """Create feedback store."""
    return FeedbackMarkdownStore(storage)


class TestStorageConfig:
    """Test storage configuration."""

    def test_local_config(self):
        """Test local storage configuration."""
        config = StorageConfig.local()
        assert config.mode == "local"
        assert config.path == Path.home() / ".hopper"

    def test_local_config_with_path(self, temp_storage_path):
        """Test local config with custom path."""
        config = StorageConfig.local(temp_storage_path)
        assert config.mode == "local"
        assert config.path == temp_storage_path

    def test_embedded_config(self, temp_storage_path):
        """Test embedded storage configuration."""
        config = StorageConfig.embedded(temp_storage_path)
        assert config.mode == "embedded"
        assert config.path == temp_storage_path

    def test_server_config(self):
        """Test server storage configuration."""
        config = StorageConfig.server("http://localhost:8000", "api-key")
        assert config.mode == "server"
        assert config.server_url == "http://localhost:8000"
        assert config.api_key == "api-key"


class TestMarkdownStorage:
    """Test markdown storage backend."""

    def test_initialize_creates_directories(self, temp_storage_path):
        """Test storage initialization creates directories."""
        config = StorageConfig.local(temp_storage_path)
        storage = MarkdownStorage(config)
        storage.initialize()

        assert (temp_storage_path / "tasks").is_dir()
        assert (temp_storage_path / "memory" / "episodes").is_dir()
        assert (temp_storage_path / "memory" / "patterns").is_dir()
        assert (temp_storage_path / "feedback").is_dir()
        assert (temp_storage_path / ".index").is_dir()

    def test_is_local(self, storage):
        """Test is_local property."""
        assert storage.is_local is True

    def test_reindex(self, storage):
        """Test reindex rebuilds task index."""
        count = storage.reindex()
        assert count == 0  # No tasks yet


class TestTaskMarkdownStore:
    """Test task markdown storage."""

    def test_create_task(self, task_store):
        """Test creating a task."""
        task = LocalTask.create(
            title="Test Task",
            description="A test task",
            priority="high",
            tags=["test", "unit"],
        )
        task_store.save(task)

        # Verify task was saved
        loaded = task_store.get(task.id)
        assert loaded is not None
        assert loaded.title == "Test Task"
        assert loaded.description == "A test task"
        assert loaded.priority == "high"
        assert loaded.tags == ["test", "unit"]

    def test_list_tasks(self, task_store):
        """Test listing tasks."""
        # Create multiple tasks
        for i in range(3):
            task = LocalTask.create(title=f"Task {i}")
            task_store.save(task)

        tasks = task_store.list()
        assert len(tasks) == 3

    def test_filter_by_status(self, task_store):
        """Test filtering tasks by status."""
        task1 = LocalTask.create(title="Pending Task", status="pending")
        task2 = LocalTask.create(title="Done Task", status="completed")
        task_store.save(task1)
        task_store.save(task2)

        pending = task_store.list(status="pending")
        assert len(pending) == 1
        assert pending[0].title == "Pending Task"

    def test_filter_by_tags(self, task_store):
        """Test filtering tasks by tags."""
        task1 = LocalTask.create(title="Tagged Task", tags=["important"])
        task2 = LocalTask.create(title="Other Task", tags=["other"])
        task_store.save(task1)
        task_store.save(task2)

        important = task_store.list(tags=["important"])
        assert len(important) == 1
        assert important[0].title == "Tagged Task"

    def test_search_tasks(self, task_store):
        """Test searching tasks."""
        task1 = LocalTask.create(title="Fix login bug")
        task2 = LocalTask.create(title="Add feature")
        task_store.save(task1)
        task_store.save(task2)

        results = task_store.search("login")
        assert len(results) == 1
        assert results[0].title == "Fix login bug"

    def test_update_task(self, task_store):
        """Test updating a task."""
        task = LocalTask.create(title="Original")
        task_store.save(task)

        task.title = "Updated"
        task_store.save(task)

        loaded = task_store.get(task.id)
        assert loaded.title == "Updated"

    def test_delete_task(self, task_store):
        """Test deleting a task."""
        task = LocalTask.create(title="To Delete")
        task_store.save(task)

        assert task_store.delete(task.id) is True
        assert task_store.get(task.id) is None

    def test_delete_nonexistent_task(self, task_store):
        """Test deleting a nonexistent task."""
        assert task_store.delete("nonexistent-id") is False

    def test_update_status(self, task_store):
        """Test updating task status."""
        task = LocalTask.create(title="Status Test")
        task_store.save(task)

        updated = task_store.update_status(task.id, "in_progress")
        assert updated.status == "in_progress"

    def test_add_tags(self, task_store):
        """Test adding tags to task."""
        task = LocalTask.create(title="Tag Test", tags=["original"])
        task_store.save(task)

        updated = task_store.add_tags(task.id, ["new", "tags"])
        assert "original" in updated.tags
        assert "new" in updated.tags
        assert "tags" in updated.tags

    def test_remove_tags(self, task_store):
        """Test removing tags from task."""
        task = LocalTask.create(title="Tag Test", tags=["keep", "remove"])
        task_store.save(task)

        updated = task_store.remove_tags(task.id, ["remove"])
        assert updated.tags == ["keep"]


class TestEpisodeMarkdownStore:
    """Test episode markdown storage."""

    def test_record_episode(self, episode_store):
        """Test recording an episode."""
        episode = episode_store.record(
            task_id="task-001",
            chosen_instance="local",
            confidence=0.85,
            strategy="rules",
        )

        assert episode is not None
        assert episode.task_id == "task-001"
        assert episode.chosen_instance == "local"
        assert episode.confidence == 0.85

    def test_get_for_task(self, episode_store):
        """Test getting episode for a task."""
        episode_store.record(
            task_id="task-002",
            chosen_instance="project-1",
            confidence=0.9,
        )

        episode = episode_store.get_for_task("task-002")
        assert episode is not None
        assert episode.task_id == "task-002"

    def test_mark_outcome(self, episode_store):
        """Test marking episode outcome."""
        episode_store.record(
            task_id="task-003",
            chosen_instance="local",
            confidence=0.8,
        )

        updated = episode_store.mark_outcome("task-003", success=True)
        assert updated is not None
        assert updated.outcome_success is True

    def test_list_recent(self, episode_store):
        """Test listing recent episodes."""
        for i in range(5):
            episode_store.record(
                task_id=f"task-{i}",
                chosen_instance="local",
                confidence=0.8,
            )

        recent = episode_store.list_recent(days=7, limit=10)
        assert len(recent) == 5

    def test_get_statistics(self, episode_store):
        """Test getting episode statistics."""
        # Record some episodes
        episode_store.record("task-1", "local", 0.8)
        episode_store.record("task-2", "local", 0.9)
        episode_store.mark_outcome("task-1", success=True)
        episode_store.mark_outcome("task-2", success=False)

        stats = episode_store.get_statistics()
        assert "total_episodes" in stats
        assert stats["total_episodes"] == 2


class TestPatternMarkdownStore:
    """Test pattern markdown storage."""

    def test_create_pattern(self, pattern_store):
        """Test creating a pattern."""
        pattern = LocalPattern.create(
            name="Test Pattern",
            tag_criteria={"required": ["api", "python"]},
            target_instance="api-instance",
        )
        pattern_store.save(pattern)

        loaded = pattern_store.get(pattern.id)
        assert loaded is not None
        assert loaded.name == "Test Pattern"
        assert loaded.tag_criteria == {"required": ["api", "python"]}

    def test_list_patterns(self, pattern_store):
        """Test listing patterns."""
        pattern1 = LocalPattern.create(name="Active", target_instance="local")
        pattern2 = LocalPattern.create(name="Inactive", target_instance="local")
        pattern2.is_active = False
        pattern_store.save(pattern1)
        pattern_store.save(pattern2)

        active = pattern_store.list(active_only=True)
        assert len(active) == 1
        assert active[0].name == "Active"

        all_patterns = pattern_store.list(active_only=False)
        assert len(all_patterns) == 2

    def test_find_matching_by_tags(self, pattern_store):
        """Test finding patterns matching tags."""
        pattern = LocalPattern.create(
            name="API Pattern",
            tag_criteria={"required": ["api"]},
            target_instance="api-instance",
        )
        pattern_store.save(pattern)

        matches = pattern_store.find_matching(tags=["api", "python"])
        assert len(matches) == 1
        assert matches[0][0].name == "API Pattern"

    def test_record_usage(self, pattern_store):
        """Test recording pattern usage."""
        pattern = LocalPattern.create(name="Usage Test", target_instance="local")
        pattern_store.save(pattern)

        pattern_store.record_usage(pattern.id, success=True)
        pattern_store.record_usage(pattern.id, success=True)
        pattern_store.record_usage(pattern.id, success=False)

        updated = pattern_store.get(pattern.id)
        assert updated.usage_count == 3
        assert updated.success_count == 2

    def test_delete_pattern(self, pattern_store):
        """Test deleting a pattern."""
        pattern = LocalPattern.create(name="To Delete", target_instance="local")
        pattern_store.save(pattern)

        assert pattern_store.delete(pattern.id) is True
        assert pattern_store.get(pattern.id) is None


class TestFeedbackMarkdownStore:
    """Test feedback markdown storage."""

    def test_save_feedback(self, feedback_store):
        """Test saving feedback."""
        feedback = feedback_store.save(
            task_id="task-001",
            was_good_match=True,
            routing_feedback="Good routing decision",
            quality_score=4.5,
        )

        assert feedback is not None
        assert feedback.task_id == "task-001"
        assert feedback.was_good_match is True

    def test_get_feedback(self, feedback_store):
        """Test getting feedback for task."""
        feedback_store.save(
            task_id="task-002",
            was_good_match=False,
            should_have_routed_to="other-instance",
        )

        feedback = feedback_store.get("task-002")
        assert feedback is not None
        assert feedback.was_good_match is False
        assert feedback.should_have_routed_to == "other-instance"

    def test_list_feedback(self, feedback_store):
        """Test listing feedback."""
        feedback_store.save(task_id="task-1", was_good_match=True)
        feedback_store.save(task_id="task-2", was_good_match=False)
        feedback_store.save(task_id="task-3", was_good_match=True)

        all_feedback = feedback_store.list()
        assert len(all_feedback) == 3

        good_only = feedback_store.list(good_only=True)
        assert len(good_only) == 2

        bad_only = feedback_store.list(good_only=False)
        assert len(bad_only) == 1

    def test_get_accuracy_stats(self, feedback_store):
        """Test getting accuracy statistics."""
        feedback_store.save(task_id="task-1", was_good_match=True)
        feedback_store.save(task_id="task-2", was_good_match=True)
        feedback_store.save(task_id="task-3", was_good_match=False)

        stats = feedback_store.get_accuracy_stats(days=30)
        assert "total_feedback" in stats
        assert stats["total_feedback"] == 3
        assert stats["good_matches"] == 2
        assert stats["bad_matches"] == 1
