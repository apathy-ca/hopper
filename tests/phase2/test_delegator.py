"""
Tests for the Delegator class.

Tests task delegation, acceptance, rejection, and completion.
"""

import pytest
from datetime import datetime

from hopper.delegation.delegator import Delegator, DelegationError
from hopper.models import (
    DelegationStatus,
    DelegationType,
    InstanceStatus,
    TaskDelegation,
)


class TestDelegator:
    """Tests for Delegator class."""

    def test_delegate_task_creates_delegation(
        self,
        db_session,
        sample_task,
        project_instance,
    ):
        """Test that delegate_task creates a delegation record."""
        delegator = Delegator(db_session)

        delegation = delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
            delegation_type=DelegationType.ROUTE,
            delegated_by="test-user",
            notes="Test delegation",
        )

        assert delegation is not None
        assert delegation.task_id == sample_task.id
        assert delegation.target_instance_id == project_instance.id
        assert delegation.delegation_type == DelegationType.ROUTE
        assert delegation.status == DelegationStatus.PENDING
        assert delegation.delegated_by == "test-user"
        assert "Test delegation" in delegation.notes

    def test_delegate_task_updates_task_instance(
        self,
        db_session,
        sample_task,
        global_instance,
        project_instance,
    ):
        """Test that delegation updates the task's instance_id."""
        delegator = Delegator(db_session)
        original_instance_id = sample_task.instance_id

        delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
        )

        assert sample_task.instance_id == project_instance.id
        assert sample_task.instance_id != original_instance_id

    def test_delegate_to_stopped_instance_fails(
        self,
        db_session,
        sample_task,
        stopped_instance,
    ):
        """Test that delegation to a stopped instance fails."""
        delegator = Delegator(db_session)

        with pytest.raises(DelegationError) as exc_info:
            delegator.delegate_task(
                task=sample_task,
                target_instance=stopped_instance,
            )

        assert "Cannot delegate to instance" in str(exc_info.value)
        assert "stopped" in str(exc_info.value).lower()

    def test_accept_delegation(
        self,
        db_session,
        task_with_delegation,
    ):
        """Test accepting a delegation."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        result = delegator.accept_delegation(
            delegation=delegation,
            notes="Accepted for processing",
        )

        assert result.status == DelegationStatus.ACCEPTED
        assert result.accepted_at is not None
        assert "Accepted for processing" in result.notes

    def test_accept_non_pending_delegation_fails(
        self,
        db_session,
        task_with_delegation,
    ):
        """Test that accepting an already accepted delegation fails."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        # First accept
        delegator.accept_delegation(delegation)

        # Second accept should fail
        with pytest.raises(DelegationError) as exc_info:
            delegator.accept_delegation(delegation)

        assert "Cannot accept delegation" in str(exc_info.value)

    def test_reject_delegation(
        self,
        db_session,
        task_with_delegation,
        global_instance,
    ):
        """Test rejecting a delegation."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        result = delegator.reject_delegation(
            delegation=delegation,
            reason="Insufficient resources",
        )

        assert result.status == DelegationStatus.REJECTED
        assert result.rejection_reason == "Insufficient resources"
        # Task should return to source instance
        assert task.instance_id == global_instance.id

    def test_complete_delegation(
        self,
        db_session,
        task_with_delegation,
    ):
        """Test completing a delegation."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        # First accept
        delegator.accept_delegation(delegation)

        # Then complete
        result = delegator.complete_delegation(
            delegation=delegation,
            result={"output": "Task completed successfully"},
        )

        assert result.status == DelegationStatus.COMPLETED
        assert result.completed_at is not None
        assert result.result == {"output": "Task completed successfully"}

    def test_cancel_delegation(
        self,
        db_session,
        task_with_delegation,
        global_instance,
    ):
        """Test cancelling a delegation."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        result = delegator.cancel_delegation(delegation)

        assert result.status == DelegationStatus.CANCELLED
        # Task should return to source instance
        assert task.instance_id == global_instance.id

    def test_cancel_completed_delegation_fails(
        self,
        db_session,
        task_with_delegation,
    ):
        """Test that cancelling a completed delegation fails."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        # Complete the delegation
        delegator.complete_delegation(delegation)

        # Cancel should fail
        with pytest.raises(DelegationError) as exc_info:
            delegator.cancel_delegation(delegation)

        assert "Cannot cancel delegation" in str(exc_info.value)

    def test_get_delegation_chain(
        self,
        db_session,
        global_instance,
        project_instance,
        orchestration_instance,
        sample_task,
    ):
        """Test getting the full delegation chain."""
        delegator = Delegator(db_session)

        # Create chain: global -> project -> orchestration
        del1 = delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
        )
        delegator.accept_delegation(del1)

        del2 = delegator.delegate_task(
            task=sample_task,
            target_instance=orchestration_instance,
        )

        chain = delegator.get_delegation_chain(sample_task)

        assert len(chain) == 2
        assert chain[0].target_instance_id == project_instance.id
        assert chain[1].target_instance_id == orchestration_instance.id

    def test_get_active_delegation(
        self,
        db_session,
        task_with_delegation,
    ):
        """Test getting the active delegation for a task."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        active = delegator.get_active_delegation(task)

        assert active is not None
        assert active.id == delegation.id

    def test_get_active_delegation_none_when_completed(
        self,
        db_session,
        task_with_delegation,
    ):
        """Test that completed delegations are not returned as active."""
        task, delegation = task_with_delegation
        delegator = Delegator(db_session)

        delegator.complete_delegation(delegation)
        active = delegator.get_active_delegation(task)

        assert active is None


class TestDelegationTypes:
    """Tests for different delegation types."""

    def test_route_delegation(
        self,
        db_session,
        sample_task,
        project_instance,
    ):
        """Test ROUTE delegation type."""
        delegator = Delegator(db_session)

        delegation = delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
            delegation_type=DelegationType.ROUTE,
        )

        assert delegation.delegation_type == DelegationType.ROUTE

    def test_decompose_delegation(
        self,
        db_session,
        sample_task,
        project_instance,
    ):
        """Test DECOMPOSE delegation type."""
        delegator = Delegator(db_session)

        delegation = delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
            delegation_type=DelegationType.DECOMPOSE,
        )

        assert delegation.delegation_type == DelegationType.DECOMPOSE

    def test_escalate_delegation(
        self,
        db_session,
        sample_task,
        project_instance,
        global_instance,
    ):
        """Test ESCALATE delegation type."""
        delegator = Delegator(db_session)

        # First delegate to project
        delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
        )

        # Then escalate back to global
        delegation = delegator.delegate_task(
            task=sample_task,
            target_instance=global_instance,
            delegation_type=DelegationType.ESCALATE,
        )

        assert delegation.delegation_type == DelegationType.ESCALATE

    def test_reassign_delegation(
        self,
        db_session,
        sample_task,
        project_instance,
        second_project_instance,
    ):
        """Test REASSIGN delegation type."""
        delegator = Delegator(db_session)

        # First delegate to project
        delegator.delegate_task(
            task=sample_task,
            target_instance=project_instance,
        )

        # Then reassign to another project
        delegation = delegator.delegate_task(
            task=sample_task,
            target_instance=second_project_instance,
            delegation_type=DelegationType.REASSIGN,
        )

        assert delegation.delegation_type == DelegationType.REASSIGN
        assert sample_task.instance_id == second_project_instance.id
