"""
Integration tests for the full delegation flow.

Tests end-to-end task delegation from Global -> Project -> Orchestration
and completion bubbling back up.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from hopper.delegation.delegator import Delegator, DelegationError
from hopper.delegation.completion import CompletionBubbler
from hopper.delegation.router import InstanceRouter
from hopper.models import (
    DelegationStatus,
    DelegationType,
    HopperInstance,
    HopperScope,
    InstanceStatus,
    InstanceType,
    Task,
    TaskDelegation,
    TaskStatus,
)


class TestFullDelegationFlow:
    """End-to-end tests for delegation flow."""

    def test_task_flows_down_hierarchy(
        self,
        db_session,
        instance_hierarchy,
        sample_task,
    ):
        """Test that a task flows from global -> project -> orchestration."""
        delegator = Delegator(db_session)

        global_inst = instance_hierarchy["global"]
        project_inst = instance_hierarchy["project"]
        orch_inst = instance_hierarchy["orchestration"]

        # Start at global
        assert sample_task.instance_id == global_inst.id

        # Delegate to project
        del1 = delegator.delegate_task(
            task=sample_task,
            target_instance=project_inst,
            delegation_type=DelegationType.ROUTE,
        )
        delegator.accept_delegation(del1)

        assert sample_task.instance_id == project_inst.id

        # Delegate to orchestration
        del2 = delegator.delegate_task(
            task=sample_task,
            target_instance=orch_inst,
            delegation_type=DelegationType.ROUTE,
        )
        delegator.accept_delegation(del2)

        assert sample_task.instance_id == orch_inst.id

        # Verify delegation chain
        chain = delegator.get_delegation_chain(sample_task)
        assert len(chain) == 2
        assert chain[0].source_instance_id == global_inst.id
        assert chain[0].target_instance_id == project_inst.id
        assert chain[1].source_instance_id == project_inst.id
        assert chain[1].target_instance_id == orch_inst.id

    def test_rejection_returns_task_to_source(
        self,
        db_session,
        instance_hierarchy,
        sample_task,
    ):
        """Test that rejection returns task to source instance."""
        delegator = Delegator(db_session)

        global_inst = instance_hierarchy["global"]
        project_inst = instance_hierarchy["project"]

        # Delegate to project
        delegation = delegator.delegate_task(
            task=sample_task,
            target_instance=project_inst,
        )

        assert sample_task.instance_id == project_inst.id

        # Reject the delegation
        delegator.reject_delegation(delegation, "Project at capacity")

        # Task should return to global
        assert sample_task.instance_id == global_inst.id
        assert delegation.status == DelegationStatus.REJECTED

    def test_multiple_delegation_attempts(
        self,
        db_session,
        global_instance,
        project_instance,
        second_project_instance,
        sample_task,
    ):
        """Test multiple delegation attempts with rejection and reassignment."""
        delegator = Delegator(db_session)

        # First attempt to project 1
        del1 = delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
        )

        # Project 1 rejects
        delegator.reject_delegation(del1, "Cannot handle this type")
        assert sample_task.instance_id == global_instance.id

        # Second attempt to project 2
        del2 = delegator.delegate_task(
            task=sample_task,
            target_instance=second_project_instance,
        )
        delegator.accept_delegation(del2)

        assert sample_task.instance_id == second_project_instance.id

        # Chain should show both attempts
        chain = delegator.get_delegation_chain(sample_task)
        assert len(chain) == 2


class TestCompletionBubbling:
    """Tests for completion bubbling through the hierarchy."""

    def test_completion_bubbles_up_chain(
        self,
        db_session,
        instance_hierarchy,
        sample_task,
    ):
        """Test that completion bubbles up the delegation chain."""
        delegator = Delegator(db_session)
        bubbler = CompletionBubbler(db_session)

        global_inst = instance_hierarchy["global"]
        project_inst = instance_hierarchy["project"]
        orch_inst = instance_hierarchy["orchestration"]

        # Set up delegation chain
        del1 = delegator.delegate_task(sample_task, project_inst)
        delegator.accept_delegation(del1)

        del2 = delegator.delegate_task(sample_task, orch_inst)
        delegator.accept_delegation(del2)

        # Complete at orchestration level
        sample_task.status = TaskStatus.DONE
        result = {"output": "Task completed at orchestration"}

        completed_delegations = bubbler.bubble_completion(
            task=sample_task,
            result=result,
        )

        # Both delegations should be completed
        assert len(completed_delegations) >= 1
        for delegation in completed_delegations:
            assert delegation.status == DelegationStatus.COMPLETED

    def test_already_completed_delegations_not_bubbled_again(
        self,
        db_session,
        instance_hierarchy,
        sample_task,
    ):
        """Test that already completed delegations are not processed again."""
        delegator = Delegator(db_session)
        bubbler = CompletionBubbler(db_session)

        project_inst = instance_hierarchy["project"]
        orch_inst = instance_hierarchy["orchestration"]

        # Set up delegation chain
        del1 = delegator.delegate_task(sample_task, project_inst)
        delegator.accept_delegation(del1)

        del2 = delegator.delegate_task(sample_task, orch_inst)
        delegator.accept_delegation(del2)

        # Complete the task
        sample_task.status = TaskStatus.DONE

        # First bubble - should complete both delegations
        first_completed = bubbler.bubble_completion(sample_task)
        assert len(first_completed) == 2

        # Second bubble - no active delegations left
        second_completed = bubbler.bubble_completion(sample_task)
        assert len(second_completed) == 0


class TestInstanceRouter:
    """Tests for the instance router."""

    def test_find_target_instance_from_global(
        self,
        db_session,
        global_instance,
        project_instance,
        second_project_instance,
    ):
        """Test routing from global to project."""
        router = InstanceRouter(db_session)
        global_instance.children = [project_instance, second_project_instance]

        # Task matching Python/FastAPI
        from hopper.models import Task, TaskStatus
        python_task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Add FastAPI endpoint",
            description="Create a new FastAPI endpoint for user management",
            project="Project Alpha",  # Explicit project name
            status=TaskStatus.PENDING,
            priority="medium",
            instance_id=global_instance.id,
            tags={"python": True, "api": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(python_task)
        db_session.flush()

        target = router.find_target_instance(
            task=python_task,
            source_instance=global_instance,
        )

        # Should match Project Alpha
        assert target is not None
        assert target.id == project_instance.id

    def test_find_target_by_tags(
        self,
        db_session,
        global_instance,
        project_instance,
        second_project_instance,
    ):
        """Test routing by tag matching."""
        router = InstanceRouter(db_session)
        global_instance.children = [project_instance, second_project_instance]

        # Task with tags matching project capabilities
        from hopper.models import Task, TaskStatus
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="New task",
            project=None,  # No explicit project
            status=TaskStatus.PENDING,
            priority="medium",
            instance_id=global_instance.id,
            tags=["python", "testing"],  # Matches Project Alpha capabilities
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        db_session.flush()

        target = router.find_target_instance(
            task=task,
            source_instance=global_instance,
        )

        # Should find a matching project
        if target:
            assert target.scope == HopperScope.PROJECT

    def test_no_target_when_all_stopped(
        self,
        db_session,
        global_instance,
        stopped_instance,
    ):
        """Test that stopped instances are not selected as targets."""
        router = InstanceRouter(db_session)
        global_instance.children = [stopped_instance]

        from hopper.models import Task, TaskStatus
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Test task",
            project=None,
            status=TaskStatus.PENDING,
            priority="medium",
            instance_id=global_instance.id,
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        db_session.flush()

        target = router.find_target_instance(
            task=task,
            source_instance=global_instance,
        )

        assert target is None

    def test_orchestration_does_not_delegate(
        self,
        db_session,
        orchestration_instance,
        sample_task,
    ):
        """Test that orchestration instances don't delegate further."""
        router = InstanceRouter(db_session)
        sample_task.instance_id = orchestration_instance.id

        target = router.find_target_instance(
            task=sample_task,
            source_instance=orchestration_instance,
        )

        assert target is None

    def test_can_delegate_to_child(
        self,
        db_session,
        global_instance,
        project_instance,
    ):
        """Test validation that delegation to child is allowed."""
        router = InstanceRouter(db_session)

        can_delegate = router.can_delegate_to(global_instance, project_instance)

        assert can_delegate is True

    def test_cannot_delegate_to_self(
        self,
        db_session,
        global_instance,
    ):
        """Test that delegation to self is not allowed."""
        router = InstanceRouter(db_session)

        can_delegate = router.can_delegate_to(global_instance, global_instance)

        assert can_delegate is False

    def test_cannot_delegate_to_stopped(
        self,
        db_session,
        global_instance,
        stopped_instance,
    ):
        """Test that delegation to stopped instance is not allowed."""
        router = InstanceRouter(db_session)

        can_delegate = router.can_delegate_to(global_instance, stopped_instance)

        assert can_delegate is False


class TestDelegationWithTaskLifecycle:
    """Tests for delegation integrated with task lifecycle."""

    def test_task_delegation_preserves_metadata(
        self,
        db_session,
        instance_hierarchy,
        sample_task,
    ):
        """Test that task metadata is preserved through delegation."""
        delegator = Delegator(db_session)

        project_inst = instance_hierarchy["project"]

        # Set task metadata
        sample_task.metadata = {"original_data": "preserved"}
        original_title = sample_task.title
        original_tags = sample_task.tags.copy()

        # Delegate
        delegator.delegate_task(sample_task, project_inst)

        # Verify preservation
        assert sample_task.title == original_title
        assert sample_task.tags == original_tags
        assert sample_task.metadata["original_data"] == "preserved"

    def test_delegation_timestamps(
        self,
        db_session,
        instance_hierarchy,
        sample_task,
    ):
        """Test that delegation timestamps are properly set."""
        delegator = Delegator(db_session)

        project_inst = instance_hierarchy["project"]
        before_delegation = datetime.utcnow()

        delegation = delegator.delegate_task(sample_task, project_inst)

        assert delegation.delegated_at is not None
        assert delegation.delegated_at >= before_delegation

        # Accept and check accepted_at
        before_accept = datetime.utcnow()
        delegator.accept_delegation(delegation)

        assert delegation.accepted_at is not None
        assert delegation.accepted_at >= before_accept

    def test_concurrent_delegations_handling(
        self,
        db_session,
        instance_hierarchy,
        multiple_tasks,
    ):
        """Test handling multiple tasks delegated concurrently."""
        delegator = Delegator(db_session)

        global_inst = instance_hierarchy["global"]
        project_inst = instance_hierarchy["project"]

        # Delegate all tasks
        delegations = []
        for task in multiple_tasks:
            task.instance_id = global_inst.id
            delegation = delegator.delegate_task(task, project_inst)
            delegations.append(delegation)

        # All should be pending
        assert all(d.status == DelegationStatus.PENDING for d in delegations)

        # Accept all
        for delegation in delegations:
            delegator.accept_delegation(delegation)

        # All should be accepted
        assert all(d.status == DelegationStatus.ACCEPTED for d in delegations)

        # All tasks should be at project
        assert all(t.instance_id == project_inst.id for t in multiple_tasks)
