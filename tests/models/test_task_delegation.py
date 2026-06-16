"""
Tests for TaskDelegation model.
"""

from sqlalchemy.orm import Session

from hopper.models import (
    DelegationStatus,
    DelegationType,
    HopperInstance,
    HopperScope,
    InstanceStatus,
    TaskDelegation,
)


class TestTaskDelegationModel:
    """Test TaskDelegation model operations."""

    def test_create_delegation(self, clean_db: Session, make_record):
        """Test creating a TaskDelegation."""
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

        make_record("TASK-001", instance_id="source-inst")

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

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-001").first()
        assert retrieved is not None
        assert retrieved.task_id == "TASK-001"
        assert retrieved.source_instance_id == "source-inst"
        assert retrieved.target_instance_id == "target-inst"
        assert retrieved.delegation_type == DelegationType.ROUTE
        assert retrieved.status == DelegationStatus.PENDING

    def test_delegation_accept(self, clean_db: Session, make_record):
        """Test accepting a delegation."""
        instance = HopperInstance(
            id="inst-1", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        make_record("TASK-002")

        delegation = TaskDelegation(
            id="DEL-002",
            task_id="TASK-002",
            target_instance_id="inst-1",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        delegation.accept()
        clean_db.commit()

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-002").first()
        assert retrieved.status == DelegationStatus.ACCEPTED
        assert retrieved.accepted_at is not None

    def test_delegation_reject(self, clean_db: Session, make_record):
        """Test rejecting a delegation."""
        instance = HopperInstance(
            id="inst-2", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        make_record("TASK-003")

        delegation = TaskDelegation(
            id="DEL-003",
            task_id="TASK-003",
            target_instance_id="inst-2",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        delegation.reject("Instance is busy")
        clean_db.commit()

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-003").first()
        assert retrieved.status == DelegationStatus.REJECTED
        assert retrieved.rejection_reason == "Instance is busy"

    def test_delegation_complete(self, clean_db: Session, make_record):
        """Test completing a delegation."""
        instance = HopperInstance(
            id="inst-3", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        make_record("TASK-004")

        delegation = TaskDelegation(
            id="DEL-004",
            task_id="TASK-004",
            target_instance_id="inst-3",
            delegation_type=DelegationType.ROUTE,
            status=DelegationStatus.ACCEPTED,
        )
        clean_db.add(delegation)
        clean_db.commit()

        result = {"output": "Success", "artifacts": ["file.txt"]}
        delegation.complete(result)
        clean_db.commit()

        retrieved = clean_db.query(TaskDelegation).filter_by(id="DEL-004").first()
        assert retrieved.status == DelegationStatus.COMPLETED
        assert retrieved.completed_at is not None
        assert retrieved.result == result

    def test_delegation_status_properties(self, clean_db: Session, make_record):
        """Test delegation status property methods."""
        instance = HopperInstance(
            id="inst-4", name="Inst", scope=HopperScope.PROJECT, status=InstanceStatus.RUNNING
        )
        clean_db.add(instance)
        clean_db.commit()

        make_record("TASK-005")

        delegation = TaskDelegation(
            id="DEL-005",
            task_id="TASK-005",
            target_instance_id="inst-4",
            status=DelegationStatus.PENDING,
        )
        clean_db.add(delegation)
        clean_db.commit()

        assert delegation.is_pending is True
        assert delegation.is_active is True
        assert delegation.is_terminal is False

        delegation.accept()
        assert delegation.is_pending is False
        assert delegation.is_active is True
        assert delegation.is_terminal is False

        delegation.complete()
        assert delegation.is_pending is False
        assert delegation.is_active is False
        assert delegation.is_terminal is True

    def test_task_delegations_query(self, clean_db: Session, make_record):
        """Multiple TaskDelegations for the same record can be queried by task_id."""
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

        make_record("TASK-CHAIN", instance_id="global-del")

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

        delegations = sorted(
            clean_db.query(TaskDelegation).filter_by(task_id="TASK-CHAIN").all(),
            key=lambda d: d.id,
        )
        assert len(delegations) == 2
        assert delegations[0].source_instance_id == "global-del"
        assert delegations[0].target_instance_id == "project-del"
        assert delegations[1].source_instance_id == "project-del"
        assert delegations[1].target_instance_id == "orch-del"
