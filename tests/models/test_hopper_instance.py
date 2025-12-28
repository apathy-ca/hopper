"""
Tests for HopperInstance model.
"""

import pytest
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, Task


def test_hopper_instance_creation(clean_db: Session) -> None:
    """Test creating a hopper instance."""
    instance = HopperInstance(
        instance_id="hopper-global",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    retrieved = clean_db.query(HopperInstance).filter_by(instance_id="hopper-global").first()
    assert retrieved is not None
    assert retrieved.instance_id == "hopper-global"
    assert retrieved.scope == HopperScope.GLOBAL.value


def test_hopper_instance_hierarchy(clean_db: Session) -> None:
    """Test parent-child hierarchy between instances."""
    # Create parent (Global)
    global_instance = HopperInstance(
        instance_id="hopper-global",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(global_instance)
    clean_db.commit()

    # Create child (Project)
    project_instance = HopperInstance(
        instance_id="hopper-czarina",
        scope=HopperScope.PROJECT.value,
        parent_instance_id="hopper-global",
    )
    clean_db.add(project_instance)
    clean_db.commit()

    # Create grandchild (Orchestration)
    orch_instance = HopperInstance(
        instance_id="hopper-czarina-run-123",
        scope=HopperScope.ORCHESTRATION.value,
        parent_instance_id="hopper-czarina",
    )
    clean_db.add(orch_instance)
    clean_db.commit()

    # Verify parent relationship
    retrieved_project = (
        clean_db.query(HopperInstance).filter_by(instance_id="hopper-czarina").first()
    )
    assert retrieved_project is not None
    assert retrieved_project.parent is not None
    assert retrieved_project.parent.instance_id == "hopper-global"

    # Verify children relationship
    retrieved_global = clean_db.query(HopperInstance).filter_by(instance_id="hopper-global").first()
    assert retrieved_global is not None
    assert len(retrieved_global.children) == 1
    assert retrieved_global.children[0].instance_id == "hopper-czarina"

    # Verify grandchild
    assert len(retrieved_project.children) == 1
    assert retrieved_project.children[0].instance_id == "hopper-czarina-run-123"
    assert retrieved_project.children[0].parent.instance_id == "hopper-czarina"


def test_hopper_instance_configuration(clean_db: Session) -> None:
    """Test instance with custom configuration."""
    config = {
        "max_concurrent_tasks": 10,
        "routing_strategy": "llm",
        "project_name": "czarina",
    }

    instance = HopperInstance(
        instance_id="hopper-project",
        scope=HopperScope.PROJECT.value,
        config=config,
        status="active",
    )
    clean_db.add(instance)
    clean_db.commit()

    retrieved = clean_db.query(HopperInstance).filter_by(instance_id="hopper-project").first()
    assert retrieved is not None
    assert retrieved.config == config
    assert retrieved.config["max_concurrent_tasks"] == 10
    assert retrieved.status == "active"


def test_hopper_instance_tasks_relationship(clean_db: Session) -> None:
    """Test relationship between instance and its tasks."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.PROJECT.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    # Add tasks to instance
    task1 = Task(id="TASK-001", instance_id="test-instance", title="Task 1")
    task2 = Task(id="TASK-002", instance_id="test-instance", title="Task 2")
    clean_db.add_all([task1, task2])
    clean_db.commit()

    # Verify instance can access its tasks
    retrieved = clean_db.query(HopperInstance).filter_by(instance_id="test-instance").first()
    assert retrieved is not None
    assert len(retrieved.tasks) == 2
    assert {t.id for t in retrieved.tasks} == {"TASK-001", "TASK-002"}


@pytest.mark.skip(reason="TaskDelegation model not implemented in Phase 1")
def test_task_delegation_creation(clean_db: Session) -> None:
    """Test creating a task delegation."""
    # NOTE: TaskDelegation model planned for Phase 2
    pass


@pytest.mark.skip(reason="TaskDelegation model not implemented in Phase 1")
def test_task_delegation_relationships(clean_db: Session) -> None:
    """Test task delegation relationships with instances."""
    # NOTE: TaskDelegation model planned for Phase 2
    pass


def test_instance_scopes(clean_db: Session) -> None:
    """Test all valid instance scopes."""
    scopes = [
        HopperScope.GLOBAL,
        HopperScope.PROJECT,
        HopperScope.ORCHESTRATION,
        HopperScope.PERSONAL,
        HopperScope.FAMILY,
        HopperScope.EVENT,
        HopperScope.FEDERATED,
    ]

    for scope in scopes:
        instance = HopperInstance(
            instance_id=f"instance-{scope.value.lower()}",
            scope=scope.value,
        )
        clean_db.add(instance)

    clean_db.commit()

    # Verify all were created
    count = clean_db.query(HopperInstance).count()
    assert count == len(scopes)
