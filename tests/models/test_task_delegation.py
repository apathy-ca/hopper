"""
Tests for TaskDelegation model.
"""

import pytest
from sqlalchemy.orm import Session

from hopper.models import (
    HopperInstance,
    HopperScope,
    InstanceStatus,
    Task,
    TaskDelegation,
    DelegationType,
    DelegationStatus,
)


class TestTaskDelegationModel:
    """Test TaskDelegation model operations."""

    def test_create_delegation(self, clean_db: Session):
        """Test creating a TaskDelegation."""
        # Create instances
        source = HopperInstance(
            id="source-inst",
            name="Source",
            scope=HopperScope.GLOBAL,
            status=InstanceStatus.RUNNING,
        )
        target = HopperInstance(
            id="target-inst",
            name="Target",
            scope=HopperScope.PROJECT,
            status=InstanceStatus.RUNNING,
        )
        clean_db.add_all([source, target])
        clean_db.commit()

        # Create task
        task = Task(id="TASK-001", title="Test Task", instance_id="source-inst")
        clean_db.add(task)
        clean_db.commit()

        # Create delegation
        delegation = TaskDelegation(
            id="DEL-001",
            task_id="TASK-001",
            source_instance_id="source-inst",
            target_instance_id="target-inst",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        # Verify
        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-001").first()
        assert retrieved is not None
        assert retrieved.task_id == "TASK-001"
        assert retrieved.source_instance_id == "source-inst"
        assert retrieved.target_instance_id == "target-inst"
        assert retrieved.delegation_type == DelegationType.ROUTE
        assert retrieved.status == DelegationStatus.PENDING

    def test_delegation_accept(self, clean_db: Session):
        """Test accepting a delegation."""
        # Setup
        instance = HopperInstance(
            id="inst-1", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        task = Task(id="TASK-002", title="Test Task")
        clean_db.add(task)
        clean_db.commit()

        delegation = TaskDelegation(
            id="DEL-002",
            task_id="TASK-002",
            target_instance_id="inst-1",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        # Accept
        delegation.accept()
        clean_db.commit()

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-002").first()
        assert retrieved.status == DelegationStatus.ACCEPTED
        assert retrieved.accepted_at is not None

    def test_delegation_reject(self, clean_db: Session):
        """Test rejecting a delegation."""
        instance = HopperInstance(
            id="inst-2", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        task = Task(id="TASK-003", title="Test Task")
        clean_db.add(task)
        clean_db.commit()

        delegation = TaskDelegation(
            id="DEL-003",
            task_id="TASK-003",
            target_instance_id="inst-2",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        # Reject
        delegation.reject("Instance is busy")
        clean_db.commit()

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-003").first()
        assert retrieved.status == DelegationStatus.REJECTED
        assert retrieved.rejection_reason == "Instance is busy"

    def test_delegation_complete(self, clean_db: Session):
        """Test completing a delegation."""
        instance = HopperInstance(
            id="inst-3", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        task = Task(id="TASK-004", title="Test Task")
        clean_db.add(task)
        clean_db.commit()

        delegation = TaskDelegation(
            id="DEL-004",
            task_id="TASK-004",
            target_instance_id="inst-3",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.ACCEPTED,
        )
        clean_db.add(delegation)
        clean_db.commit()

        # Complete with result
        result = {"output": "Success", "artifacts": ["file.txt"]}
        delegation.complete(result)
        clean_db.commit()

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-004").first()
        assert retrieved.status == DelegationStatus.COMPLETED
        assert retrieved.completed_at is not None
        assert retrieved.result == result

    def test_delegation_status_properties(self, clean_db: Session):
        """Test delegation status property methods."""
        instance = HopperInstance(
            id="inst-4", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        task = Task(id="TASK-005", title="Test Task")
        clean_db.add(task)
        clean_db.commit()

        delegation = TaskDelegation(
            id="DEL-005",
            task_id="TASK-005",
            target_instance_id="inst-4",
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        # Pending state
        assert delegation.is_pending is True
        assert delegation.is_active is True
        assert delegation.is_terminal is False

        # Accepted state
        delegation.accept()
        assert delegation.is_pending is False
        assert delegation.is_active is True
        assert delegation.is_terminal is False

        # Completed state
        delegation.complete()
        assert delegation.is_pending is False
        assert delegation.is_active is False
        assert delegation.is_terminal is True

    def test_task_delegations_relationship(self, clean_db: Session):
        """Test relationship between task and its delegations."""
        # Create hierarchy
        global_inst = HopperInstance(
            id="global-del",
            name="Global",
            scope=HopperScope.GLOBAL,
            status=InstanceStatus.RUNNING,
        )
        project_inst = HopperInstance(
            id="project-del",
            name="Project",
            scope=HopperScope.PROJECT,
            parent_id="global-del",
            status=InstanceStatus.RUNNING,
        )
        orch_inst = HopperInstance(
            id="orch-del",
            name="Orchestration",
            scope=HopperScope.ORCHESTRATION,
            parent_id="project-del",
            status=InstanceStatus.RUNNING,
        )
        clean_db.add_all([global_inst, project_inst, orch_inst])
        clean_db.commit()

        # Create task with delegations
        task = Task(id="TASK-CHAIN", title="Chained Task", instance_id="global-del")
        clean_db.add(task)
        clean_db.commit()

        # Delegation chain: Global -> Project -> Orchestration
        del1 = TaskDelegation(
            id="DEL-CHAIN-1",
            task_id="TASK-CHAIN",
            source_instance_id="global-del",
            target_instance_id="project-del",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.COMPLETED,
        )
        del2 = TaskDelegation(
            id="DEL-CHAIN-2",
            task_id="TASK-CHAIN",
            source_instance_id="project-del",
            target_instance_id="orch-del",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.ACCEPTED,
        )
        clean_db.add_all([del1, del2])
        clean_db.commit()

        # Verify relationship
        retrieved_task = clean_db.query(Task).filter_by(id="TASK-CHAIN").first()
        assert len(retrieved_task.delegations) == 2

        # Verify delegation chain order
        delegations = sorted(retrieved_task.delegations, key=lambda d: d.id)
        assert delegations[0].source_instance_id == "global-del"
        assert delegations[0].target_instance_id == "project-del"
        assert delegations[1].source_instance_id == "project-del"
        assert delegations[1].target_instance_id == "orch-del"
