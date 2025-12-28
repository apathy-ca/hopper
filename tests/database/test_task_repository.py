"""
Tests for TaskRepository.
"""
import os
import pytest
from datetime import datetime

from hopper.database.connection import create_sync_engine, get_sync_session, reset_session_factories
from hopper.database.init import init_database
from hopper.database.repositories import TaskRepository


@pytest.fixture
def test_session():
    """Create a test database session."""
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    engine = create_sync_engine()
    init_database(engine, create_tables=True)

    # Create session manually instead of using the factory
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        os.environ.pop("DATABASE_URL", None)
        reset_session_factories()


def test_create_task(test_session):
    """Test creating a task."""
    repo = TaskRepository(test_session)

    task = repo.create(
        id="task-1",
        title="Test Task",
        description="A test task",
        status="pending",
        priority="high",
    )

    assert task.id == "task-1"
    assert task.title == "Test Task"
    assert task.status == "pending"
    assert task.priority == "high"


def test_get_task(test_session):
    """Test getting a task by ID."""
    repo = TaskRepository(test_session)

    # Create a task
    repo.create(id="task-1", title="Test Task", status="pending", priority="medium")

    # Get the task
    task = repo.get("task-1")

    assert task is not None
    assert task.id == "task-1"
    assert task.title == "Test Task"


def test_get_task_not_found(test_session):
    """Test getting a non-existent task."""
    repo = TaskRepository(test_session)

    task = repo.get("nonexistent")
    assert task is None


def test_update_task(test_session):
    """Test updating a task."""
    repo = TaskRepository(test_session)

    # Create a task
    repo.create(id="task-1", title="Test Task", status="pending", priority="medium")

    # Update the task
    updated = repo.update("task-1", status="in_progress", priority="high")

    assert updated is not None
    assert updated.status == "in_progress"
    assert updated.priority == "high"


def test_delete_task(test_session):
    """Test deleting a task."""
    repo = TaskRepository(test_session)

    # Create a task
    repo.create(id="task-1", title="Test Task", status="pending", priority="medium")

    # Delete the task
    result = repo.delete("task-1")
    assert result is True

    # Verify it's gone
    task = repo.get("task-1")
    assert task is None


def test_get_tasks_by_status(test_session):
    """Test getting tasks by status."""
    repo = TaskRepository(test_session)

    # Create some tasks
    repo.create(id="task-1", title="Task 1", status="pending", priority="medium")
    repo.create(id="task-2", title="Task 2", status="pending", priority="high")
    repo.create(id="task-3", title="Task 3", status="completed", priority="low")

    # Get pending tasks
    pending = repo.get_tasks_by_status("pending")
    assert len(pending) == 2

    # Get completed tasks
    completed = repo.get_tasks_by_status("completed")
    assert len(completed) == 1


def test_get_tasks_by_project(test_session):
    """Test getting tasks by project."""
    repo = TaskRepository(test_session)

    # Create some tasks
    repo.create(id="task-1", title="Task 1", project="project-a", status="pending", priority="medium")
    repo.create(id="task-2", title="Task 2", project="project-a", status="pending", priority="high")
    repo.create(id="task-3", title="Task 3", project="project-b", status="pending", priority="low")

    # Get tasks for project-a
    tasks = repo.get_tasks_by_project("project-a")
    assert len(tasks) == 2
    assert all(t.project == "project-a" for t in tasks)


def test_search_tasks(test_session):
    """Test searching tasks."""
    repo = TaskRepository(test_session)

    # Create some tasks
    repo.create(id="task-1", title="Fix the bug", description="Bug in login", status="pending", priority="high")
    repo.create(id="task-2", title="Add feature", description="New dashboard", status="pending", priority="medium")
    repo.create(id="task-3", title="Bug report", description="Issue with API", status="pending", priority="low")

    # Search for "bug"
    results = repo.search_tasks("bug")
    assert len(results) == 2


def test_update_status(test_session):
    """Test updating task status."""
    repo = TaskRepository(test_session)

    # Create a task
    repo.create(id="task-1", title="Test Task", status="pending", priority="medium")

    # Update status
    updated = repo.update_status("task-1", "in_progress")
    assert updated is not None
    assert updated.status == "in_progress"


def test_get_unassigned_tasks(test_session):
    """Test getting unassigned tasks."""
    repo = TaskRepository(test_session)

    # Create some tasks
    repo.create(id="task-1", title="Task 1", project="project-a", status="pending", priority="medium")
    repo.create(id="task-2", title="Task 2", status="pending", priority="high")
    repo.create(id="task-3", title="Task 3", status="pending", priority="low")

    # Get unassigned tasks
    unassigned = repo.get_unassigned_tasks()
    assert len(unassigned) == 2


def test_assign_to_project(test_session):
    """Test assigning a task to a project."""
    repo = TaskRepository(test_session)

    # Create a task
    repo.create(id="task-1", title="Test Task", status="pending", priority="medium")

    # Assign to project
    updated = repo.assign_to_project("task-1", "project-a")
    assert updated is not None
    assert updated.project == "project-a"


def test_bulk_create(test_session):
    """Test bulk creating tasks."""
    repo = TaskRepository(test_session)

    tasks_data = [
        {"id": "task-1", "title": "Task 1", "status": "pending", "priority": "low"},
        {"id": "task-2", "title": "Task 2", "status": "pending", "priority": "medium"},
        {"id": "task-3", "title": "Task 3", "status": "pending", "priority": "high"},
    ]

    tasks = repo.bulk_create(tasks_data)
    assert len(tasks) == 3
    assert all(t.id.startswith("task-") for t in tasks)


def test_count(test_session):
    """Test counting tasks."""
    repo = TaskRepository(test_session)

    # Create some tasks
    repo.create(id="task-1", title="Task 1", status="pending", priority="medium")
    repo.create(id="task-2", title="Task 2", status="pending", priority="high")
    repo.create(id="task-3", title="Task 3", status="completed", priority="low")

    # Count all tasks
    assert repo.count() == 3

    # Count pending tasks
    assert repo.count(filters={"status": "pending"}) == 2
