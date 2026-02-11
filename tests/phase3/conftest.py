"""
Phase 3 specific fixtures for memory system testing.
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
    RoutingDecision,
    Task,
    TaskStatus,
)
from hopper.memory.working import RoutingContext, WorkingMemory
from hopper.memory.working.backends import LocalBackend
from hopper.memory.working.context import InstanceInfo, RecentDecision, SimilarTask


@pytest.fixture
def local_backend() -> LocalBackend:
    """Create a local backend for testing."""
    return LocalBackend(max_entries=100)


@pytest.fixture
def working_memory(local_backend: LocalBackend) -> WorkingMemory:
    """Create a working memory instance for testing."""
    return WorkingMemory(
        backend=local_backend,
        default_ttl=300,  # 5 minutes
        max_similar_tasks=5,
        max_recent_decisions=10,
    )


@pytest.fixture
def sample_routing_context() -> RoutingContext:
    """Create a sample routing context."""
    return RoutingContext(
        task_id=f"task-{uuid4().hex[:8]}",
        task_title="Implement authentication",
        task_tags=["python", "security", "api"],
        task_priority="high",
        similar_tasks=[
            SimilarTask(
                task_id="task-old-1",
                title="Add login endpoint",
                similarity_score=0.85,
                routed_to="api-project",
                outcome_success=True,
            ),
            SimilarTask(
                task_id="task-old-2",
                title="Implement OAuth",
                similarity_score=0.72,
                routed_to="api-project",
                outcome_success=True,
            ),
        ],
        available_instances=[
            InstanceInfo(
                instance_id="inst-1",
                name="api-project",
                scope="PROJECT",
                status="running",
                capabilities=["python", "fastapi", "security"],
                current_load=3,
                max_capacity=10,
            ),
            InstanceInfo(
                instance_id="inst-2",
                name="frontend-project",
                scope="PROJECT",
                status="running",
                capabilities=["typescript", "react"],
                current_load=5,
                max_capacity=8,
            ),
        ],
        recent_decisions=[
            RecentDecision(
                task_id="task-recent-1",
                task_title="Fix API bug",
                routed_to="api-project",
                routed_at=datetime.utcnow(),
                confidence=0.9,
                outcome="success",
            ),
        ],
        session_id="session-123",
        created_at=datetime.utcnow(),
    )


@pytest.fixture
def sample_task_for_memory(db_session: Session) -> Task:
    """Create a sample task for memory testing."""
    task = Task(
        id=f"task-{uuid4().hex[:8]}",
        title="Build dashboard",
        description="Create a new admin dashboard",
        project="webapp",
        status=TaskStatus.PENDING,
        priority="medium",
        tags={"python": True, "dashboard": True},
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def instances_for_memory(db_session: Session) -> list[HopperInstance]:
    """Create instances for memory testing."""
    instances = [
        HopperInstance(
            id=f"mem-inst-{uuid4().hex[:8]}",
            name="webapp-project",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.RUNNING,
            config={
                "capabilities": ["python", "fastapi", "dashboard"],
                "max_concurrent_tasks": 10,
            },
            runtime_metadata={"active_tasks": 2},
            created_at=datetime.utcnow(),
        ),
        HopperInstance(
            id=f"mem-inst-{uuid4().hex[:8]}",
            name="api-project",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.RUNNING,
            config={
                "capabilities": ["python", "api", "database"],
                "max_concurrent_tasks": 8,
            },
            runtime_metadata={"active_tasks": 5},
            created_at=datetime.utcnow(),
        ),
    ]
    for inst in instances:
        db_session.add(inst)
    db_session.flush()
    return instances


@pytest.fixture
def routing_decisions_for_memory(
    db_session: Session, sample_task_for_memory: Task
) -> list[RoutingDecision]:
    """Create routing decisions for memory testing."""
    decisions = []
    for i in range(3):
        decision = RoutingDecision(
            id=f"dec-{uuid4().hex[:8]}",
            task_id=sample_task_for_memory.id,
            strategy_used="rules",
            target_project="webapp-project",
            confidence_score=0.8 + (i * 0.05),
            decided_at=datetime.utcnow(),
        )
        db_session.add(decision)
        decisions.append(decision)
    db_session.flush()
    return decisions
