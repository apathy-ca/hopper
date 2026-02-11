"""
Phase 2 specific fixtures for multi-instance testing.

Provides fixtures for:
- Instance hierarchies (Global -> Project -> Orchestration)
- Task delegation scenarios
- Scope behavior testing
"""

import pytest
from datetime import datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from hopper.models import (
    HopperInstance,
    HopperScope,
    InstanceStatus,
    InstanceType,
    Task,
    TaskStatus,
    TaskDelegation,
    DelegationType,
    DelegationStatus,
)


@pytest.fixture
def global_instance(db_session: Session) -> HopperInstance:
    """Create a global scope instance."""
    instance = HopperInstance(
        id=f"global-{uuid4().hex[:8]}",
        name="Global Hopper",
        scope=HopperScope.GLOBAL,
        instance_type=InstanceType.PERSISTENT,
        status=InstanceStatus.RUNNING,
        config={
            "routing_engine": "rules",
            "llm_fallback": True,
            "auto_routing": True,
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(instance)
    db_session.flush()
    return instance


@pytest.fixture
def project_instance(db_session: Session, global_instance: HopperInstance) -> HopperInstance:
    """Create a project scope instance under global."""
    instance = HopperInstance(
        id=f"project-{uuid4().hex[:8]}",
        name="Project Alpha",
        scope=HopperScope.PROJECT,
        instance_type=InstanceType.PERSISTENT,
        status=InstanceStatus.RUNNING,
        parent_id=global_instance.id,
        config={
            "capabilities": ["python", "fastapi", "testing"],
            "max_concurrent_tasks": 5,
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(instance)
    db_session.flush()
    return instance


@pytest.fixture
def orchestration_instance(db_session: Session, project_instance: HopperInstance) -> HopperInstance:
    """Create an orchestration scope instance under project."""
    instance = HopperInstance(
        id=f"orch-{uuid4().hex[:8]}",
        name="Orchestration Worker",
        scope=HopperScope.ORCHESTRATION,
        instance_type=InstanceType.EPHEMERAL,
        status=InstanceStatus.RUNNING,
        parent_id=project_instance.id,
        config={
            "max_concurrent_tasks": 10,
            "worker_type": "execution",
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(instance)
    db_session.flush()
    return instance


@pytest.fixture
def instance_hierarchy(
    global_instance: HopperInstance,
    project_instance: HopperInstance,
    orchestration_instance: HopperInstance,
) -> dict:
    """Full instance hierarchy for testing."""
    return {
        "global": global_instance,
        "project": project_instance,
        "orchestration": orchestration_instance,
    }


@pytest.fixture
def sample_task(db_session: Session, global_instance: HopperInstance) -> Task:
    """Create a sample task at global level."""
    task = Task(
        id=f"task-{uuid4().hex[:8]}",
        title="Implement feature",
        description="Implement the new feature as described",
        project="test-project",
        status=TaskStatus.PENDING,
        priority="medium",
        instance_id=global_instance.id,
        tags={"feature": True, "backend": True},
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def high_priority_task(db_session: Session, global_instance: HopperInstance) -> Task:
    """Create a high priority task."""
    task = Task(
        id=f"task-{uuid4().hex[:8]}",
        title="Urgent fix needed",
        description="Critical bug that needs immediate attention",
        project="test-project",
        status=TaskStatus.PENDING,
        priority="urgent",
        instance_id=global_instance.id,
        tags={"bug": True, "critical": True},
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def task_with_delegation(
    db_session: Session,
    global_instance: HopperInstance,
    project_instance: HopperInstance,
    sample_task: Task,
) -> tuple[Task, TaskDelegation]:
    """Create a task with an existing delegation."""
    delegation = TaskDelegation(
        id=f"del-{uuid4().hex[:8]}",
        task_id=sample_task.id,
        source_instance_id=global_instance.id,
        target_instance_id=project_instance.id,
        delegation_type=DelegationType.ROUTE,
        status=DelegationStatus.PENDING,
        delegated_at=datetime.utcnow(),
    )
    db_session.add(delegation)
    db_session.flush()
    return sample_task, delegation


@pytest.fixture
def multiple_tasks(db_session: Session, global_instance: HopperInstance) -> list[Task]:
    """Create multiple tasks for batch testing."""
    tasks = []
    priorities = ["low", "medium", "high", "urgent"]
    for i in range(4):
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title=f"Task {i+1}",
            description=f"Description for task {i+1}",
            project="test-project",
            status=TaskStatus.PENDING,
            priority=priorities[i],
            instance_id=global_instance.id,
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        tasks.append(task)
    db_session.flush()
    return tasks


@pytest.fixture
def second_project_instance(db_session: Session, global_instance: HopperInstance) -> HopperInstance:
    """Create a second project instance for routing tests."""
    instance = HopperInstance(
        id=f"project-{uuid4().hex[:8]}",
        name="Project Beta",
        scope=HopperScope.PROJECT,
        instance_type=InstanceType.PERSISTENT,
        status=InstanceStatus.RUNNING,
        parent_id=global_instance.id,
        config={
            "capabilities": ["rust", "systems", "performance"],
            "max_concurrent_tasks": 3,
        },
        created_at=datetime.utcnow(),
    )
    db_session.add(instance)
    db_session.flush()
    return instance


@pytest.fixture
def stopped_instance(db_session: Session, global_instance: HopperInstance) -> HopperInstance:
    """Create a stopped instance for testing delegation validation."""
    instance = HopperInstance(
        id=f"stopped-{uuid4().hex[:8]}",
        name="Stopped Instance",
        scope=HopperScope.PROJECT,
        instance_type=InstanceType.PERSISTENT,
        status=InstanceStatus.STOPPED,
        parent_id=global_instance.id,
        config={},
        created_at=datetime.utcnow(),
    )
    db_session.add(instance)
    db_session.flush()
    return instance
