"""
Tests for Working Memory implementation.
"""

import time
import pytest
from datetime import datetime

from hopper.memory.working import RoutingContext, WorkingMemory
from hopper.memory.working.backends import LocalBackend
from hopper.memory.working.context import InstanceInfo, RecentDecision, SimilarTask


class TestLocalBackend:
    """Tests for LocalBackend."""

    def test_set_and_get(self, local_backend: LocalBackend):
        """Test basic set and get operations."""
        data = {"key": "value", "number": 42}
        local_backend.set("test-key", data)

        result = local_backend.get("test-key")

        assert result == data

    def test_get_nonexistent_key(self, local_backend: LocalBackend):
        """Test getting a nonexistent key."""
        result = local_backend.get("nonexistent")

        assert result is None

    def test_delete(self, local_backend: LocalBackend):
        """Test deleting a key."""
        local_backend.set("to-delete", {"data": True})

        deleted = local_backend.delete("to-delete")

        assert deleted is True
        assert local_backend.get("to-delete") is None

    def test_delete_nonexistent(self, local_backend: LocalBackend):
        """Test deleting nonexistent key."""
        deleted = local_backend.delete("nonexistent")

        assert deleted is False

    def test_exists(self, local_backend: LocalBackend):
        """Test key existence check."""
        local_backend.set("exists-key", {"data": True})

        assert local_backend.exists("exists-key") is True
        assert local_backend.exists("not-exists") is False

    def test_ttl_expiration(self, local_backend: LocalBackend):
        """Test that keys expire after TTL."""
        local_backend.set("expiring", {"data": True}, ttl=1)

        assert local_backend.get("expiring") is not None

        time.sleep(1.1)

        assert local_backend.get("expiring") is None

    def test_clear(self, local_backend: LocalBackend):
        """Test clearing all entries."""
        local_backend.set("key1", {"a": 1})
        local_backend.set("key2", {"b": 2})

        cleared = local_backend.clear()

        assert cleared == 2
        assert local_backend.size() == 0

    def test_clear_expired(self, local_backend: LocalBackend):
        """Test clearing expired entries."""
        local_backend.set("permanent", {"data": True})
        local_backend.set("expiring", {"data": True}, ttl=1)

        time.sleep(1.1)

        cleared = local_backend.clear_expired()

        assert cleared == 1
        assert local_backend.exists("permanent")
        assert not local_backend.exists("expiring")

    def test_keys_pattern(self, local_backend: LocalBackend):
        """Test getting keys by pattern."""
        local_backend.set("context:task-1", {"a": 1})
        local_backend.set("context:task-2", {"b": 2})
        local_backend.set("session:sess-1", {"c": 3})

        context_keys = local_backend.keys("context:*")
        session_keys = local_backend.keys("session:*")
        all_keys = local_backend.keys("*")

        assert len(context_keys) == 2
        assert len(session_keys) == 1
        assert len(all_keys) == 3

    def test_max_entries_eviction(self):
        """Test that entries are evicted when max is reached."""
        backend = LocalBackend(max_entries=3)

        backend.set("key1", {"a": 1})
        backend.set("key2", {"b": 2})
        backend.set("key3", {"c": 3})
        backend.set("key4", {"d": 4})  # Should evict key1

        assert backend.size() == 3
        assert backend.get("key1") is None  # Evicted
        assert backend.get("key4") is not None

    def test_get_stats(self, local_backend: LocalBackend):
        """Test getting backend statistics."""
        local_backend.set("key1", {"a": 1})
        local_backend.set("key2", {"b": 2})

        stats = local_backend.get_stats()

        assert stats["total_entries"] == 2
        assert stats["max_entries"] == 100
        assert "utilization" in stats


class TestRoutingContext:
    """Tests for RoutingContext."""

    def test_to_dict_and_from_dict(self, sample_routing_context: RoutingContext):
        """Test serialization roundtrip."""
        data = sample_routing_context.to_dict()
        restored = RoutingContext.from_dict(data)

        assert restored.task_id == sample_routing_context.task_id
        assert restored.task_title == sample_routing_context.task_title
        assert restored.task_tags == sample_routing_context.task_tags
        assert len(restored.similar_tasks) == len(sample_routing_context.similar_tasks)
        assert len(restored.available_instances) == len(
            sample_routing_context.available_instances
        )

    def test_get_successful_routings(self, sample_routing_context: RoutingContext):
        """Test getting successful routing references."""
        successful = sample_routing_context.get_successful_routings()

        assert len(successful) == 2
        assert all(st.outcome_success is True for st in successful)

    def test_get_instance_by_id(self, sample_routing_context: RoutingContext):
        """Test getting instance by ID."""
        instance = sample_routing_context.get_instance_by_id("inst-1")

        assert instance is not None
        assert instance.name == "api-project"

        missing = sample_routing_context.get_instance_by_id("nonexistent")
        assert missing is None

    def test_get_instances_with_capacity(self, sample_routing_context: RoutingContext):
        """Test getting instances with remaining capacity."""
        with_capacity = sample_routing_context.get_instances_with_capacity()

        assert len(with_capacity) == 2  # Both have capacity
        for inst in with_capacity:
            assert inst.current_load < inst.max_capacity


class TestWorkingMemory:
    """Tests for WorkingMemory."""

    def test_set_and_get_context(
        self,
        working_memory: WorkingMemory,
        sample_routing_context: RoutingContext,
    ):
        """Test storing and retrieving context."""
        working_memory.set_context(sample_routing_context)

        retrieved = working_memory.get_context(sample_routing_context.task_id)

        assert retrieved is not None
        assert retrieved.task_id == sample_routing_context.task_id
        assert retrieved.task_title == sample_routing_context.task_title

    def test_get_nonexistent_context(self, working_memory: WorkingMemory):
        """Test getting nonexistent context."""
        result = working_memory.get_context("nonexistent-task")

        assert result is None

    def test_delete_context(
        self,
        working_memory: WorkingMemory,
        sample_routing_context: RoutingContext,
    ):
        """Test deleting context."""
        working_memory.set_context(sample_routing_context)

        deleted = working_memory.delete_context(sample_routing_context.task_id)

        assert deleted is True
        assert working_memory.get_context(sample_routing_context.task_id) is None

    def test_build_routing_context(
        self,
        working_memory: WorkingMemory,
        db_session,
        sample_task_for_memory,
        instances_for_memory,
    ):
        """Test building routing context from database."""
        context = working_memory.build_routing_context(
            task=sample_task_for_memory,
            session=db_session,
            session_id="test-session",
        )

        assert context.task_id == sample_task_for_memory.id
        assert context.task_title == sample_task_for_memory.title
        assert context.session_id == "test-session"
        assert len(context.available_instances) >= 2

        # Verify context was stored
        retrieved = working_memory.get_context(sample_task_for_memory.id)
        assert retrieved is not None

    def test_add_similar_tasks(
        self,
        working_memory: WorkingMemory,
        sample_routing_context: RoutingContext,
    ):
        """Test adding similar tasks to context."""
        # Store context without similar tasks
        sample_routing_context.similar_tasks = []
        working_memory.set_context(sample_routing_context)

        # Add similar tasks
        similar = [
            SimilarTask(
                task_id="similar-1",
                title="Similar task",
                similarity_score=0.9,
                routed_to="project-a",
                outcome_success=True,
            )
        ]
        result = working_memory.add_similar_tasks(
            sample_routing_context.task_id, similar
        )

        assert result is True
        retrieved = working_memory.get_context(sample_routing_context.task_id)
        assert len(retrieved.similar_tasks) == 1
        assert retrieved.similar_tasks[0].task_id == "similar-1"

    def test_get_stats(
        self,
        working_memory: WorkingMemory,
        sample_routing_context: RoutingContext,
    ):
        """Test getting memory statistics."""
        working_memory.set_context(sample_routing_context)

        stats = working_memory.get_stats()

        assert stats["backend"] == "LocalBackend"
        assert stats["total_contexts"] >= 1
        assert "default_ttl" in stats

    def test_clear_all(
        self,
        working_memory: WorkingMemory,
        sample_routing_context: RoutingContext,
    ):
        """Test clearing all contexts."""
        working_memory.set_context(sample_routing_context)

        cleared = working_memory.clear_all()

        assert cleared >= 1
        assert working_memory.get_context(sample_routing_context.task_id) is None

    def test_from_config_local(self):
        """Test creating from config with local backend."""
        config = {
            "backend": "local",
            "default_ttl": 600,
            "max_entries": 500,
        }

        memory = WorkingMemory.from_config(config)

        assert memory is not None
        stats = memory.get_stats()
        assert stats["backend"] == "LocalBackend"
        assert stats["default_ttl"] == 600


class TestContextIntegration:
    """Integration tests for working memory with database."""

    def test_context_includes_instance_capabilities(
        self,
        working_memory: WorkingMemory,
        db_session,
        sample_task_for_memory,
        instances_for_memory,
    ):
        """Test that context includes instance capabilities."""
        context = working_memory.build_routing_context(
            task=sample_task_for_memory,
            session=db_session,
        )

        # Find webapp-project instance
        webapp_inst = None
        for inst in context.available_instances:
            if inst.name == "webapp-project":
                webapp_inst = inst
                break

        assert webapp_inst is not None
        assert "python" in webapp_inst.capabilities
        assert "dashboard" in webapp_inst.capabilities

    def test_context_reflects_instance_load(
        self,
        working_memory: WorkingMemory,
        db_session,
        sample_task_for_memory,
        instances_for_memory,
    ):
        """Test that context reflects current instance load."""
        context = working_memory.build_routing_context(
            task=sample_task_for_memory,
            session=db_session,
        )

        # webapp-project was set up with active_tasks: 2
        webapp_inst = None
        for inst in context.available_instances:
            if inst.name == "webapp-project":
                webapp_inst = inst
                break

        assert webapp_inst is not None
        assert webapp_inst.current_load == 2
        assert webapp_inst.max_capacity == 10
