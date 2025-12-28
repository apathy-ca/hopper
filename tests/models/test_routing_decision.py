"""
Tests for RoutingDecision model.
"""

import pytest
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, Project, RoutingDecision, Task


def test_routing_decision_creation(clean_db: Session) -> None:
    """Test creating a routing decision."""
    # Create prerequisites
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    project = Project(name="czarina", slug="czarina")
    task = Task(id="TASK-001", instance_id="test-instance", title="Test task")
    clean_db.add_all([instance, project, task])
    clean_db.commit()

    # Create routing decision
    decision = RoutingDecision(
        task_id="TASK-001",
        project="czarina",
        confidence=0.85,
        reasoning="Task matches project capabilities",
        decided_by="llm",
        decision_time_ms=150.5,
    )
    clean_db.add(decision)
    clean_db.commit()

    retrieved = clean_db.query(RoutingDecision).filter_by(task_id="TASK-001").first()
    assert retrieved is not None
    assert retrieved.project == "czarina"
    assert retrieved.confidence == 0.85
    assert retrieved.reasoning == "Task matches project capabilities"
    assert retrieved.decided_by == "llm"
    assert retrieved.decision_time_ms == 150.5


def test_routing_decision_with_alternatives(clean_db: Session) -> None:
    """Test routing decision with alternative projects considered."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    project = Project(name="czarina", slug="czarina")
    task = Task(id="TASK-001", instance_id="test-instance", title="Test task")
    clean_db.add_all([instance, project, task])
    clean_db.commit()

    alternatives = [
        {"project": "sark", "confidence": 0.65, "reason": "Could handle it"},
        {"project": "manual", "confidence": 0.45, "reason": "Fallback option"},
    ]

    decision = RoutingDecision(
        task_id="TASK-001",
        project="czarina",
        confidence=0.85,
        alternatives=alternatives,
    )
    clean_db.add(decision)
    clean_db.commit()

    retrieved = clean_db.query(RoutingDecision).filter_by(task_id="TASK-001").first()
    assert retrieved is not None
    assert len(retrieved.alternatives) == 2
    assert retrieved.alternatives[0]["project"] == "sark"
    assert retrieved.alternatives[0]["confidence"] == 0.65


def test_routing_decision_with_context(clean_db: Session) -> None:
    """Test routing decision with workload and context snapshots."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    project = Project(name="czarina", slug="czarina")
    task = Task(id="TASK-001", instance_id="test-instance", title="Test task")
    clean_db.add_all([instance, project, task])
    clean_db.commit()

    workload_snapshot = {
        "czarina": {"pending": 5, "in_progress": 2},
        "sark": {"pending": 10, "in_progress": 3},
    }

    context = {
        "task_tags": ["backend", "python"],
        "time_of_day": "business_hours",
        "priority": "high",
    }

    decision = RoutingDecision(
        task_id="TASK-001",
        project="czarina",
        confidence=0.90,
        workload_snapshot=workload_snapshot,
        context=context,
    )
    clean_db.add(decision)
    clean_db.commit()

    retrieved = clean_db.query(RoutingDecision).filter_by(task_id="TASK-001").first()
    assert retrieved is not None
    assert retrieved.workload_snapshot is not None
    assert retrieved.workload_snapshot["czarina"]["pending"] == 5
    assert retrieved.context is not None
    assert retrieved.context["priority"] == "high"


def test_routing_decision_task_relationship(clean_db: Session) -> None:
    """Test relationship between routing decision and task."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    project = Project(name="czarina", slug="czarina")
    task = Task(id="TASK-001", instance_id="test-instance", title="Test task")
    clean_db.add_all([instance, project, task])
    clean_db.commit()

    decision = RoutingDecision(
        task_id="TASK-001",
        project="czarina",
        confidence=0.80,
    )
    clean_db.add(decision)
    clean_db.commit()

    # Access decision from task
    retrieved_task = clean_db.query(Task).filter_by(id="TASK-001").first()
    assert retrieved_task is not None
    assert retrieved_task.routing_decision is not None
    assert retrieved_task.routing_decision.project == "czarina"
    assert retrieved_task.routing_decision.confidence == 0.80

    # Access task from decision
    retrieved_decision = clean_db.query(RoutingDecision).filter_by(task_id="TASK-001").first()
    assert retrieved_decision is not None
    assert retrieved_decision.task.id == "TASK-001"
    assert retrieved_decision.task.title == "Test task"


@pytest.mark.skip(reason="Phase 2: project_obj relationship not implemented")
@pytest.mark.skip(reason="Phase 2: project_obj relationship not implemented")
def test_routing_decision_project_relationship(clean_db: Session) -> None:
    """Test relationship between routing decision and project."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    project = Project(name="czarina", slug="czarina")
    task = Task(id="TASK-001", instance_id="test-instance", title="Test task")
    clean_db.add_all([instance, project, task])
    clean_db.commit()

    decision = RoutingDecision(
        task_id="TASK-001",
        project="czarina",
        confidence=0.85,
    )
    clean_db.add(decision)
    clean_db.commit()

    # Access project from decision
    retrieved_decision = clean_db.query(RoutingDecision).filter_by(task_id="TASK-001").first()
    assert retrieved_decision is not None
    assert retrieved_decision.project_obj is not None
    assert retrieved_decision.project_obj.name == "czarina"

    # Access decisions from project
    retrieved_project = clean_db.query(Project).filter_by(name="czarina").first()
    assert retrieved_project is not None
    assert len(retrieved_project.routing_decisions) == 1
    assert retrieved_project.routing_decisions[0].task_id == "TASK-001"


def test_routing_decision_without_project(clean_db: Session) -> None:
    """Test routing decision when no project is selected."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    task = Task(id="TASK-001", instance_id="test-instance", title="Unroutable task")
    clean_db.add_all([instance, task])
    clean_db.commit()

    decision = RoutingDecision(
        task_id="TASK-001",
        project=None,
        confidence=0.0,
        reasoning="No suitable project found",
        decided_by="rules",
    )
    clean_db.add(decision)
    clean_db.commit()

    retrieved = clean_db.query(RoutingDecision).filter_by(task_id="TASK-001").first()
    assert retrieved is not None
    assert retrieved.project is None
    assert retrieved.confidence == 0.0
    assert "No suitable project" in retrieved.reasoning
