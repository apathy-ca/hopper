"""
Tests for ProjectRepository.
"""

import os

import pytest

from hopper.database.connection import create_sync_engine, reset_session_factories
from hopper.database.init import init_database
from hopper.database.repositories import ProjectRepository


@pytest.fixture
def test_session():
    """Create a test database session."""
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    engine = create_sync_engine()
    init_database(engine, create_tables=True)

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


def test_create_project(test_session):
    """Test creating a project."""
    repo = ProjectRepository(test_session)

    project = repo.create(
        name="test-project",
        slug="test-proj",
        repository="https://github.com/user/test",
        executor_type="agent",
    )

    assert project.name == "test-project"
    assert project.slug == "test-proj"


def test_get_by_name(test_session):
    """Test getting a project by name."""
    repo = ProjectRepository(test_session)

    repo.create(name="test-project", slug="test-proj")

    project = repo.get_by_name("test-project")
    assert project is not None
    assert project.name == "test-project"


def test_get_by_slug(test_session):
    """Test getting a project by slug."""
    repo = ProjectRepository(test_session)

    repo.create(name="test-project", slug="test-proj")

    project = repo.get_by_slug("test-proj")
    assert project is not None
    assert project.slug == "test-proj"


def test_get_projects_with_active_tasks(test_session):
    """Test getting projects; tasks table dropped so returns all projects."""
    project_repo = ProjectRepository(test_session)

    project_repo.create(name="project-a", slug="proj-a")
    project_repo.create(name="project-b", slug="proj-b")
    project_repo.create(name="project-c", slug="proj-c")

    projects = project_repo.get_projects_with_active_tasks()

    # Stubbed: returns all projects since Task table is gone
    assert len(projects) == 3


def test_get_auto_claim_projects(test_session):
    """Test getting projects with auto_claim enabled."""
    repo = ProjectRepository(test_session)

    repo.create(name="project-a", slug="proj-a", auto_claim=True)
    repo.create(name="project-b", slug="proj-b", auto_claim=False)
    repo.create(name="project-c", slug="proj-c", auto_claim=True)

    projects = repo.get_auto_claim_projects()
    assert len(projects) == 2
    assert all(p.auto_claim for p in projects)


def test_get_project_task_count(test_session):
    """Test task count; tasks table dropped so always returns 0."""
    project_repo = ProjectRepository(test_session)

    project_repo.create(name="test-project", slug="test-proj")

    count = project_repo.get_project_task_count("test-project")
    assert count == 0


def test_get_project_statistics(test_session):
    """Test project statistics; tasks table dropped so all counts are 0."""
    project_repo = ProjectRepository(test_session)

    project_repo.create(name="test-project", slug="test-proj")

    stats = project_repo.get_project_statistics("test-project")

    assert stats["total_tasks"] == 0
    assert stats["pending"] == 0
    assert stats["in_progress"] == 0
    assert stats["completed"] == 0
