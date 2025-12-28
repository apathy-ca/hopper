"""
Tests for database utilities.
"""

import os

import pytest

from hopper.database.connection import create_sync_engine, reset_session_factories
from hopper.database.init import init_database
from hopper.database.utils import (
    analyze_database_statistics,
    build_database_url,
    dump_schema,
    get_table_row_counts,
    reset_database_dev_only,
)


@pytest.fixture
def test_engine():
    """Create a test database engine."""
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    engine = create_sync_engine()
    init_database(engine, create_tables=True)
    yield engine
    os.environ.pop("DATABASE_URL", None)
    reset_session_factories()


def test_build_database_url_sqlite():
    """Test building SQLite database URL."""
    url = build_database_url("sqlite", database="test.db")
    assert url == "sqlite:///./test.db"


def test_build_database_url_postgresql():
    """Test building PostgreSQL database URL."""
    url = build_database_url(
        "postgresql",
        host="localhost",
        database="testdb",
        username="user",
        password="pass",
    )
    assert url == "postgresql://user:pass@localhost:5432/testdb"


def test_build_database_url_postgresql_no_auth():
    """Test building PostgreSQL URL without authentication."""
    url = build_database_url(
        "postgresql",
        host="localhost",
        database="testdb",
    )
    assert url == "postgresql://localhost:5432/testdb"


def test_dump_schema(test_engine):
    """Test dumping database schema."""
    schema = dump_schema(test_engine)

    assert "tables" in schema
    assert "database_url" in schema

    # Check for expected tables
    expected_tables = ["tasks", "projects", "hopper_instances", "routing_decisions"]
    for table in expected_tables:
        assert table in schema["tables"]

    # Check task table structure
    tasks_table = schema["tables"]["tasks"]
    assert "columns" in tasks_table
    assert "indexes" in tasks_table
    assert "foreign_keys" in tasks_table

    # Verify some columns exist
    column_names = [col["name"] for col in tasks_table["columns"]]
    assert "id" in column_names
    assert "title" in column_names
    assert "status" in column_names


def test_get_table_row_counts(test_engine):
    """Test getting row counts for all tables."""
    from sqlalchemy.orm import sessionmaker

    from hopper.database.repositories import ProjectRepository, TaskRepository

    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()

    try:
        # Add some data
        task_repo = TaskRepository(session)
        project_repo = ProjectRepository(session)

        project_repo.create(name="test-project", slug="test-proj")
        task_repo.create(id="task-1", title="Task 1", status="pending", priority="medium")
        task_repo.create(id="task-2", title="Task 2", status="pending", priority="medium")

        session.commit()

        # Get counts
        counts = get_table_row_counts(test_engine)

        assert counts["tasks"] == 2
        assert counts["projects"] == 1

    finally:
        session.close()


def test_analyze_database_statistics(test_engine):
    """Test analyzing database statistics."""
    stats = analyze_database_statistics(test_engine)

    assert "database_type" in stats
    assert "table_count" in stats
    assert "tables" in stats
    assert "row_counts" in stats
    assert "total_rows" in stats

    assert stats["database_type"] == "sqlite"
    assert stats["table_count"] > 0
    assert isinstance(stats["tables"], list)


def test_reset_database_dev_only(test_engine):
    """Test resetting database in development mode."""
    from sqlalchemy.orm import sessionmaker

    from hopper.database.repositories import TaskRepository

    SessionLocal = sessionmaker(bind=test_engine)
    session = SessionLocal()

    try:
        # Add some data
        task_repo = TaskRepository(session)
        task_repo.create(id="task-1", title="Task 1", status="pending", priority="medium")
        session.commit()

        # Verify data exists
        counts_before = get_table_row_counts(test_engine)
        assert counts_before["tasks"] == 1

        # Reset database
        reset_database_dev_only(test_engine)

        # Verify tables exist but are empty
        counts_after = get_table_row_counts(test_engine)
        assert counts_after["tasks"] == 0

    finally:
        session.close()


def test_reset_database_production_safety():
    """Test that reset fails on non-local databases."""
    # Create an engine with a production-like URL
    reset_session_factories()
    os.environ["DATABASE_URL"] = "postgresql://user:pass@prod.example.com/hopper"

    try:
        engine = create_sync_engine()

        with pytest.raises(RuntimeError, match="Cannot reset database"):
            reset_database_dev_only(engine)

    finally:
        os.environ.pop("DATABASE_URL", None)
        reset_session_factories()
