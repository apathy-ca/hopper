"""
Tests for database initialization.
"""
import os
import pytest
from sqlalchemy import inspect

from hopper.database.connection import create_sync_engine, reset_session_factories
from hopper.database.init import (
    check_database_health,
    drop_all_tables,
    get_database_info,
    init_database,
    reset_database,
)


@pytest.fixture
def test_engine():
    """Create a test database engine."""
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    engine = create_sync_engine()
    yield engine
    os.environ.pop("DATABASE_URL", None)
    reset_session_factories()


def test_init_database(test_engine):
    """Test database initialization."""
    init_database(test_engine, create_tables=True)

    # Verify tables were created
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()

    expected_tables = [
        "tasks",
        "projects",
        "hopper_instances",
        "routing_decisions",
        "task_feedback",
        "external_mappings",
    ]

    for table in expected_tables:
        assert table in tables, f"Table {table} was not created"


def test_check_database_health(test_engine):
    """Test database health check."""
    assert check_database_health(test_engine) is True


def test_drop_all_tables(test_engine):
    """Test dropping all tables."""
    # First create tables
    init_database(test_engine, create_tables=True)

    # Verify tables exist
    inspector = inspect(test_engine)
    assert len(inspector.get_table_names()) > 0

    # Drop all tables
    drop_all_tables(test_engine, confirm=True)

    # Verify tables were dropped
    inspector = inspect(test_engine)
    assert len(inspector.get_table_names()) == 0


def test_drop_all_tables_requires_confirmation(test_engine):
    """Test that drop_all_tables requires confirmation."""
    with pytest.raises(ValueError, match="Must set confirm=True"):
        drop_all_tables(test_engine, confirm=False)


def test_reset_database(test_engine):
    """Test database reset."""
    # Reset database
    reset_database(test_engine, confirm=True)

    # Verify tables were created
    inspector = inspect(test_engine)
    tables = inspector.get_table_names()
    assert len(tables) > 0


def test_reset_database_requires_confirmation(test_engine):
    """Test that reset_database requires confirmation."""
    with pytest.raises(ValueError, match="Must set confirm=True"):
        reset_database(test_engine, confirm=False)


def test_get_database_info():
    """Test getting database configuration info."""
    os.environ["DATABASE_URL"] = "sqlite:///./test.db"
    try:
        info = get_database_info()
        assert "url" in info
        assert "type" in info
        assert "async_url" in info
        assert info["type"] == "sqlite"
    finally:
        os.environ.pop("DATABASE_URL", None)
