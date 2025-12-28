"""
Tests for database connection management.
"""
import os
import pytest
from sqlalchemy import text

from hopper.database.connection import (
    create_sync_engine,
    get_database_url,
    get_sync_session,
    reset_session_factories,
)


def test_get_database_url_default():
    """Test default database URL."""
    # Clear env var if set
    old_url = os.environ.pop("DATABASE_URL", None)
    try:
        url = get_database_url(async_mode=False)
        assert url.startswith("sqlite:///")
    finally:
        if old_url:
            os.environ["DATABASE_URL"] = old_url


def test_get_database_url_from_env():
    """Test database URL from environment variable."""
    test_url = "postgresql://test:test@localhost/test"
    old_url = os.environ.get("DATABASE_URL")
    try:
        os.environ["DATABASE_URL"] = test_url
        url = get_database_url(async_mode=False)
        assert url == test_url
    finally:
        if old_url:
            os.environ["DATABASE_URL"] = old_url
        else:
            os.environ.pop("DATABASE_URL", None)


def test_get_database_url_async_mode():
    """Test async URL conversion."""
    # Test PostgreSQL async URL
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"
    url = get_database_url(async_mode=True)
    assert url.startswith("postgresql+asyncpg://")

    # Test SQLite async URL
    os.environ["DATABASE_URL"] = "sqlite:///./test.db"
    url = get_database_url(async_mode=True)
    assert url.startswith("sqlite+aiosqlite:///" )

    os.environ.pop("DATABASE_URL", None)


def test_create_sync_engine_sqlite():
    """Test creating a SQLite engine."""
    engine = create_sync_engine("sqlite:///:memory:")
    assert engine is not None

    # Test connection
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_sync_session_context_manager():
    """Test synchronous session context manager."""
    # Use in-memory SQLite for testing
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    try:
        with get_sync_session() as session:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        os.environ.pop("DATABASE_URL", None)
        reset_session_factories()


def test_sync_session_rollback_on_error():
    """Test that sessions rollback on error."""
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    try:
        with pytest.raises(Exception):
            with get_sync_session() as session:
                # This will raise an error
                session.execute(text("SELECT * FROM nonexistent_table"))
    finally:
        os.environ.pop("DATABASE_URL", None)
        reset_session_factories()
