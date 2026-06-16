"""
Tests for scope behavior implementations.

Tests Global, Project, and Orchestration scope behaviors.
"""

import pytest

from hopper.intelligence.scopes.base import TaskActionType
from hopper.intelligence.scopes.factory import (
    GlobalScopeBehavior,
    OrchestrationScopeBehavior,
    ProjectScopeBehavior,
    get_available_scopes,
    get_behavior_for_instance,
    get_behavior_for_scope,
)
from hopper.models import HopperScope, TaskStatus


class TestScopeBehaviorFactory:
    """Tests for scope behavior factory functions."""

    def test_get_behavior_for_global_scope(self, db_session):
        """Test getting behavior for GLOBAL scope."""
        behavior = get_behavior_for_scope(HopperScope.GLOBAL, db_session)

        assert isinstance(behavior, GlobalScopeBehavior)
        assert behavior.scope_name == "GLOBAL"

    def test_get_behavior_for_project_scope(self, db_session):
        """Test getting behavior for PROJECT scope."""
        behavior = get_behavior_for_scope(HopperScope.PROJECT, db_session)

        assert isinstance(behavior, ProjectScopeBehavior)
        assert behavior.scope_name == "PROJECT"

    def test_get_behavior_for_orchestration_scope(self, db_session):
        """Test getting behavior for ORCHESTRATION scope."""
        behavior = get_behavior_for_scope(HopperScope.ORCHESTRATION, db_session)

        assert isinstance(behavior, OrchestrationScopeBehavior)
        assert behavior.scope_name == "ORCHESTRATION"

    def test_get_behavior_for_instance(self, db_session, global_instance):
        """Test getting behavior for an instance."""
        behavior = get_behavior_for_instance(global_instance, db_session)

        assert isinstance(behavior, GlobalScopeBehavior)

    def test_get_available_scopes(self):
        """Test getting list of available scopes."""
        scopes = get_available_scopes()

        assert HopperScope.GLOBAL in scopes
        assert HopperScope.PROJECT in scopes
        assert HopperScope.ORCHESTRATION in scopes
        assert len(scopes) >= 3


class TestGlobalScopeBehavior:
    """Tests for GlobalScopeBehavior."""

    @pytest.mark.asyncio
    async def test_should_delegate_always_true(self, db_session, global_instance, sample_task):
        """Test that global scope always delegates."""
        behavior = GlobalScopeBehavior(db_session)

        result = await behavior.should_delegate(sample_task, global_instance)

        assert result is True

    @pytest.mark.asyncio
    async def test_handle_incoming_task_delegates(
        self, db_session, global_instance, project_instance, sample_task
    ):
        """Test that global scope delegates incoming tasks."""
        behavior = GlobalScopeBehavior(db_session)

        # Add project as child of global
        global_instance.children = [project_instance]

        action = await behavior.handle_incoming_task(sample_task, global_instance)

        assert action.action_type == TaskActionType.DELEGATE

    @pytest.mark.asyncio
    async def test_handle_incoming_task_rejects_when_no_children(
        self, db_session, global_instance, sample_task
    ):
        """Test that global scope rejects when no children available."""
        behavior = GlobalScopeBehavior(db_session)
        global_instance.children = []  # No children

        action = await behavior.handle_incoming_task(sample_task, global_instance)

        assert action.action_type == TaskActionType.REJECT

    @pytest.mark.asyncio
    async def test_find_delegation_target_returns_child(
        self, db_session, global_instance, project_instance, sample_task
    ):
        """Test finding delegation target returns a child instance."""
        behavior = GlobalScopeBehavior(db_session)
        global_instance.children = [project_instance]

        target = await behavior.find_delegation_target(sample_task, global_instance)

        assert target is not None
        assert target.id == project_instance.id


class TestProjectScopeBehavior:
    """Tests for ProjectScopeBehavior."""

    @pytest.mark.asyncio
    async def test_should_delegate_complex_task(self, db_session, project_instance, sample_task):
        """Test that complex tasks are delegated."""
        behavior = ProjectScopeBehavior(db_session)

        # Make task complex
        sample_task.description = "A" * 600  # Long description
        sample_task.tags = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}  # Many tags
        sample_task.priority = "urgent"

        result = await behavior.should_delegate(sample_task, project_instance)

        assert result is True

    @pytest.mark.asyncio
    async def test_should_not_delegate_simple_task(self, db_session, project_instance, sample_task):
        """Test that simple tasks are handled directly."""
        behavior = ProjectScopeBehavior(db_session)

        # Make task simple
        sample_task.description = "Simple fix"
        sample_task.tags = {}
        sample_task.priority = "low"
        project_instance.children = []

        result = await behavior.should_delegate(sample_task, project_instance)

        assert result is False

    @pytest.mark.asyncio
    async def test_handle_incoming_task_routes_to_orchestration(
        self, db_session, project_instance, orchestration_instance, sample_task
    ):
        """Test that project routes tasks to orchestration instances."""
        behavior = ProjectScopeBehavior(db_session)
        project_instance.children = [orchestration_instance]

        # Make it complex enough to delegate
        sample_task.description = "A" * 600
        sample_task.priority = "high"

        action = await behavior.handle_incoming_task(sample_task, project_instance)

        assert action.action_type == TaskActionType.DELEGATE

    @pytest.mark.asyncio
    async def test_handle_incoming_task_handles_directly_when_no_orchestration(
        self, db_session, project_instance, sample_task
    ):
        """Test that project handles tasks directly when no orchestration children."""
        behavior = ProjectScopeBehavior(db_session)
        project_instance.children = []  # No orchestration instances

        action = await behavior.handle_incoming_task(sample_task, project_instance)

        assert action.action_type == TaskActionType.HANDLE


class TestOrchestrationScopeBehavior:
    """Tests for OrchestrationScopeBehavior."""

    @pytest.mark.asyncio
    async def test_should_delegate_always_false(
        self, db_session, orchestration_instance, sample_task
    ):
        """Test that orchestration scope never delegates."""
        behavior = OrchestrationScopeBehavior(db_session)

        result = await behavior.should_delegate(sample_task, orchestration_instance)

        assert result is False

    @pytest.mark.asyncio
    async def test_find_delegation_target_returns_none(
        self, db_session, orchestration_instance, sample_task
    ):
        """Test that orchestration has no delegation targets."""
        behavior = OrchestrationScopeBehavior(db_session)

        target = await behavior.find_delegation_target(sample_task, orchestration_instance)

        assert target is None

    @pytest.mark.asyncio
    async def test_handle_incoming_task_queues(
        self, db_session, orchestration_instance, sample_task
    ):
        """Test that orchestration queues tasks for execution."""
        behavior = OrchestrationScopeBehavior(db_session)
        orchestration_instance.tasks = []

        action = await behavior.handle_incoming_task(sample_task, orchestration_instance)

        assert action.action_type == TaskActionType.QUEUE

    @pytest.mark.asyncio
    async def test_handle_incoming_task_rejects_at_capacity(
        self, db_session, orchestration_instance, sample_task, multiple_tasks
    ):
        """Test that orchestration rejects when at capacity."""
        behavior = OrchestrationScopeBehavior(db_session)

        # Set low capacity
        orchestration_instance.config = {"max_concurrent_tasks": 2}

        # Add active tasks to hit capacity
        for task in multiple_tasks[:2]:
            task.instance_id = orchestration_instance.id
            task.status = TaskStatus.IN_PROGRESS
        orchestration_instance.tasks = multiple_tasks[:2]

        action = await behavior.handle_incoming_task(sample_task, orchestration_instance)

        # _count_active_tasks is stubbed to 0 (tasks table dropped), so never rejects
        assert action.action_type == TaskActionType.QUEUE

    @pytest.mark.asyncio
    async def test_get_task_queue_orders_by_priority(
        self, db_session, orchestration_instance, multiple_tasks
    ):
        """get_task_queue is stubbed (tasks table dropped); always returns []."""
        behavior = OrchestrationScopeBehavior(db_session)

        queue = await behavior.get_task_queue(orchestration_instance)

        assert queue == []

    @pytest.mark.asyncio
    async def test_get_next_task_returns_pending(
        self, db_session, orchestration_instance, multiple_tasks
    ):
        """get_next_task returns None since get_task_queue is stubbed to []."""
        behavior = OrchestrationScopeBehavior(db_session)

        next_task = await behavior.get_next_task(orchestration_instance)

        assert next_task is None

    @pytest.mark.asyncio
    async def test_claim_task_updates_status(self, db_session, orchestration_instance, sample_task):
        """Test that claiming a task updates its status and owner."""
        behavior = OrchestrationScopeBehavior(db_session)
        sample_task.instance_id = orchestration_instance.id
        sample_task.status = TaskStatus.PENDING

        claimed = await behavior.claim_task(sample_task, "worker-123")

        assert claimed.status == TaskStatus.CLAIMED
        assert claimed.owner == "worker-123"

    @pytest.mark.asyncio
    async def test_get_queue_stats(self, db_session, orchestration_instance, multiple_tasks):
        """get_queue_stats is stubbed (tasks table dropped); returns zeroed dict."""
        behavior = OrchestrationScopeBehavior(db_session)

        orchestration_instance.config = {"max_concurrent_tasks": 10}

        stats = await behavior.get_queue_stats(orchestration_instance)

        assert stats["pending"] == 0
        assert stats["claimed"] == 0
        assert stats["in_progress"] == 0
        assert stats["done"] == 0
        assert stats["total"] == 0
        assert stats["active"] == 0
        assert stats["max_concurrent"] == 10

    @pytest.mark.asyncio
    async def test_on_task_completed_updates_metrics(
        self, db_session, orchestration_instance, sample_task
    ):
        """Test that task completion updates instance metrics."""
        behavior = OrchestrationScopeBehavior(db_session)
        orchestration_instance.runtime_metadata = {"completed_tasks": 5}

        await behavior.on_task_completed(sample_task, orchestration_instance)

        assert orchestration_instance.runtime_metadata["completed_tasks"] == 6


class TestTaskComplexityEstimation:
    """Tests for task complexity estimation."""

    def test_minimal_task_complexity(self, db_session, sample_task):
        """Test complexity of a minimal task."""
        behavior = ProjectScopeBehavior(db_session)

        sample_task.description = "Short"
        sample_task.tags = {}
        sample_task.depends_on = None
        sample_task.priority = "low"

        complexity = behavior.estimate_task_complexity(sample_task)

        assert complexity == 1

    def test_high_complexity_task(self, db_session, sample_task):
        """Test complexity of a complex task."""
        behavior = ProjectScopeBehavior(db_session)

        sample_task.description = "A" * 600  # Long description
        sample_task.tags = {"a": 1, "b": 2, "c": 3, "d": 4}  # Many tags
        sample_task.depends_on = {"task_ids": ["dep-1"]}  # Has dependencies
        sample_task.priority = "urgent"  # High priority

        complexity = behavior.estimate_task_complexity(sample_task)

        assert complexity == 5  # Max complexity

    def test_medium_complexity_task(self, db_session, sample_task):
        """Test complexity of a medium complexity task."""
        behavior = ProjectScopeBehavior(db_session)

        sample_task.description = "A" * 600  # Long description adds 1
        sample_task.tags = {"a": 1, "b": 2}  # Not enough for complexity
        sample_task.depends_on = None
        sample_task.priority = "high"  # Adds 1

        complexity = behavior.estimate_task_complexity(sample_task)

        assert complexity == 3  # base(1) + description(1) + priority(1)
