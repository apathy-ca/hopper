"""
Tests for Task model.
"""

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from hopper.models import (
    HopperInstance,
    HopperScope,
    Task,
    TaskFeedback,
    TaskPriority,
    TaskStatus,
)


def test_task_creation(clean_db: Session) -> None:
    """Test creating a basic task."""
    # Create a hopper instance first
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    # Create a task
    task = Task(
        id="HOP-001",
        instance_id="test-instance",
        title="Test task",
        description="Test description",
        status=TaskStatus.PENDING.value,
        priority=TaskPriority.MEDIUM.value,
    )
    clean_db.add(task)
    clean_db.commit()

    # Verify task was created
    retrieved_task = clean_db.query(Task).filter_by(id="HOP-001").first()
    assert retrieved_task is not None
    assert retrieved_task.title == "Test task"
    assert retrieved_task.description == "Test description"
    assert retrieved_task.status == TaskStatus.PENDING.value
    assert retrieved_task.priority == TaskPriority.MEDIUM.value
    assert isinstance(retrieved_task.created_at, datetime)
    assert isinstance(retrieved_task.updated_at, datetime)


def test_task_with_tags_and_capabilities(clean_db: Session) -> None:
    """Test task with JSON fields (tags, capabilities, dependencies)."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    task = Task(
        id="HOP-002",
        instance_id="test-instance",
        title="Task with metadata",
        tags=["backend", "database"],
        required_capabilities=["python", "postgresql"],
        depends_on=["HOP-001"],
        blocks=["HOP-003"],
    )
    clean_db.add(task)
    clean_db.commit()

    retrieved_task = clean_db.query(Task).filter_by(id="HOP-002").first()
    assert retrieved_task is not None
    assert retrieved_task.tags == ["backend", "database"]
    assert retrieved_task.required_capabilities == ["python", "postgresql"]
    assert retrieved_task.depends_on == ["HOP-001"]
    assert retrieved_task.blocks == ["HOP-003"]


def test_task_relationships(clean_db: Session) -> None:
    """Test task relationships with hopper instance."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.PROJECT.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    task1 = Task(id="HOP-001", instance_id="test-instance", title="Task 1")
    task2 = Task(id="HOP-002", instance_id="test-instance", title="Task 2")
    clean_db.add_all([task1, task2])
    clean_db.commit()

    # Verify relationship works
    retrieved_instance = (
        clean_db.query(HopperInstance).filter_by(instance_id="test-instance").first()
    )
    assert retrieved_instance is not None
    assert len(retrieved_instance.tasks) == 2
    assert {t.id for t in retrieved_instance.tasks} == {"HOP-001", "HOP-002"}


def test_task_feedback_creation(clean_db: Session) -> None:
    """Test creating task feedback."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)

    task = Task(id="HOP-001", instance_id="test-instance", title="Task with feedback")
    clean_db.add(task)
    clean_db.commit()

    feedback = TaskFeedback(
        task_id="HOP-001",
        was_good_match=True,
        quality_score=4.5,
        complexity_rating=3,
        notes="Well executed",
    )
    clean_db.add(feedback)
    clean_db.commit()

    retrieved_feedback = clean_db.query(TaskFeedback).filter_by(task_id="HOP-001").first()
    assert retrieved_feedback is not None
    assert retrieved_feedback.was_good_match is True
    assert retrieved_feedback.quality_score == 4.5
    assert retrieved_feedback.complexity_rating == 3
    assert retrieved_feedback.notes == "Well executed"


def test_task_feedback_relationship(clean_db: Session) -> None:
    """Test task-feedback relationship."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)

    task = Task(id="HOP-001", instance_id="test-instance", title="Task")
    clean_db.add(task)
    clean_db.commit()

    feedback = TaskFeedback(
        task_id="HOP-001",
        was_good_match=False,
        should_have_routed_to="other-project",
    )
    clean_db.add(feedback)
    clean_db.commit()

    # Access feedback through task
    retrieved_task = clean_db.query(Task).filter_by(id="HOP-001").first()
    assert retrieved_task is not None
    assert retrieved_task.feedback is not None
    assert retrieved_task.feedback.was_good_match is False
    assert retrieved_task.feedback.should_have_routed_to == "other-project"

    # Access task through feedback
    retrieved_feedback = clean_db.query(TaskFeedback).filter_by(task_id="HOP-001").first()
    assert retrieved_feedback is not None
    assert retrieved_feedback.task.id == "HOP-001"
    assert retrieved_feedback.task.title == "Task"


def test_task_external_integration(clean_db: Session) -> None:
    """Test task with external platform integration fields."""
    instance = HopperInstance(
        instance_id="test-instance",
        scope=HopperScope.GLOBAL.value,
    )
    clean_db.add(instance)
    clean_db.commit()

    task = Task(
        id="HOP-001",
        instance_id="test-instance",
        title="GitHub issue task",
        external_id="123",
        external_url="https://github.com/org/repo/issues/123",
        external_platform="github",
    )
    clean_db.add(task)
    clean_db.commit()

    retrieved_task = clean_db.query(Task).filter_by(id="HOP-001").first()
    assert retrieved_task is not None
    assert retrieved_task.external_id == "123"
    assert retrieved_task.external_url == "https://github.com/org/repo/issues/123"
    assert retrieved_task.external_platform == "github"
