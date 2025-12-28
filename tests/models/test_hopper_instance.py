"""
Tests for HopperInstance and TaskDelegation models.
"""

from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, Task, TaskDelegation


def test_hopper_instance_creation(clean_db: Session) -> None:
    """Test creating a hopper instance."""
    instance = HopperInstance(
        instance_id="hopper-global",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    retrieved = (
        clean_db.query(HopperInstance).filter_by(instance_id="hopper-global").first()
    )
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
    retrieved_global = (
        clean_db.query(HopperInstance).filter_by(instance_id="hopper-global").first()
    )
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

    retrieved = (
        clean_db.query(HopperInstance).filter_by(instance_id="hopper-project").first()
    )
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
    retrieved = (
        clean_db.query(HopperInstance).filter_by(instance_id="test-instance").first()
    )
    assert retrieved is not None
    assert len(retrieved.tasks) == 2
    assert {t.id for t in retrieved.tasks} == {"TASK-001", "TASK-002"}


def test_task_delegation_creation(clean_db: Session) -> None:
    """Test creating a task delegation."""
    parent_instance = HopperInstance(
        instance_id="parent-instance",
        scope=HopperScope.PROJECT.value,
    )
    child_instance = HopperInstance(
        instance_id="child-instance",
        scope=HopperScope.ORCHESTRATION.value,
        parent_instance_id="parent-instance",
    )
    clean_db.add_all([parent_instance, child_instance])
    clean_db.commit()

    delegation = TaskDelegation(
        parent_instance_id="parent-instance",
        parent_task_id="TASK-001",
        child_instance_id="child-instance",
        child_task_id="TASK-001-CHILD",
    )
    clean_db.add(delegation)
    clean_db.commit()

    retrieved = (
        clean_db.query(TaskDelegation)
        .filter_by(parent_instance_id="parent-instance", parent_task_id="TASK-001")
        .first()
    )
    assert retrieved is not None
    assert retrieved.child_instance_id == "child-instance"
    assert retrieved.child_task_id == "TASK-001-CHILD"


def test_task_delegation_relationships(clean_db: Session) -> None:
    """Test task delegation relationships with instances."""
    parent = HopperInstance(
        instance_id="parent",
        scope=HopperScope.GLOBAL.value,
    )
    child = HopperInstance(
        instance_id="child",
        scope=HopperScope.PROJECT.value,
        parent_instance_id="parent",
    )
    clean_db.add_all([parent, child])
    clean_db.commit()

    delegation = TaskDelegation(
        parent_instance_id="parent",
        parent_task_id="TASK-001",
        child_instance_id="child",
        child_task_id="TASK-001-CHILD",
    )
    clean_db.add(delegation)
    clean_db.commit()

    # Access delegation through parent instance
    retrieved_parent = (
        clean_db.query(HopperInstance).filter_by(instance_id="parent").first()
    )
    assert retrieved_parent is not None
    assert len(retrieved_parent.parent_delegations) == 1
    assert retrieved_parent.parent_delegations[0].child_task_id == "TASK-001-CHILD"

    # Access delegation through child instance
    retrieved_child = clean_db.query(HopperInstance).filter_by(instance_id="child").first()
    assert retrieved_child is not None
    assert len(retrieved_child.child_delegations) == 1
    assert retrieved_child.child_delegations[0].parent_task_id == "TASK-001"


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
