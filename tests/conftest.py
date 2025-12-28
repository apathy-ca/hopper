"""
Pytest configuration and shared fixtures for Hopper tests.

This module provides comprehensive fixtures for:
- Database setup (PostgreSQL and SQLite)
- API client fixtures
- MCP client fixtures
- CLI runner fixtures
- Mock data factories
- Test configuration
"""

import os
from collections.abc import Generator
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Import models (will be available after integration)
try:
    from hopper.models.base import Base
    from hopper.models.external_mapping import ExternalMapping
    from hopper.models.hopper_instance import HopperInstance
    from hopper.models.project import Project
    from hopper.models.routing_decision import RoutingDecision
    from hopper.models.task import Task
    from hopper.models.task_feedback import TaskFeedback
except ImportError:
    # Models not yet integrated, create mock Base
    from sqlalchemy.orm import DeclarativeBase

    class Base(DeclarativeBase):
        pass


# ============================================================================
# Database Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def sqlite_engine() -> Generator[Engine, None, None]:
    """
    Create an in-memory SQLite engine for fast unit tests.

    Uses StaticPool to maintain connection across test functions.
    Enables foreign key constraints for SQLite.
    """
    # Create in-memory SQLite engine
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Enable foreign key constraints for SQLite
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Drop all tables after tests
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(sqlite_engine: Engine) -> Generator[Session, None, None]:
    """
    Create a new database session for each test.

    Automatically rolls back changes after each test to maintain isolation.
    """
    connection = sqlite_engine.connect()
    transaction = connection.begin()

    # Create session
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    # Rollback and cleanup
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def clean_db(db_session: Session) -> Session:
    """
    Alias for db_session fixture for backward compatibility.

    Some tests use 'clean_db' naming convention.
    This is a simple pass-through to the db_session fixture.
    """
    return db_session


@pytest.fixture(scope="session")
def postgres_engine() -> Generator[Engine, None, None]:
    """
    Create a PostgreSQL engine for integration tests.

    Requires PostgreSQL to be running (e.g., via Docker Compose).
    Falls back to SQLite if PostgreSQL is not available.
    """
    # Get PostgreSQL URL from environment or use default
    db_url = os.getenv("TEST_DATABASE_URL", "postgresql://hopper:hopper@localhost:5432/hopper_test")

    try:
        engine = create_engine(db_url, pool_pre_ping=True)

        # Test connection
        with engine.connect():
            pass

        # Create all tables
        Base.metadata.create_all(bind=engine)

        yield engine

        # Drop all tables after tests
        Base.metadata.drop_all(bind=engine)
        engine.dispose()

    except Exception:
        # Fall back to SQLite if PostgreSQL is not available
        pytest.skip("PostgreSQL not available, skipping PostgreSQL tests")


@pytest.fixture(scope="function")
def postgres_session(postgres_engine: Engine) -> Generator[Session, None, None]:
    """
    Create a new PostgreSQL database session for each test.

    Automatically rolls back changes after each test to maintain isolation.
    """
    connection = postgres_engine.connect()
    transaction = connection.begin()

    # Create session
    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    # Rollback and cleanup
    session.close()
    transaction.rollback()
    connection.close()


# ============================================================================
# API Client Fixtures
# ============================================================================


@pytest.fixture
def api_client(db_session: Session) -> TestClient:
    """
    Create a FastAPI test client with database session override.

    The database session is automatically injected into the API dependencies.
    """
    # Import API app (will be available after integration)
    try:
        from hopper.api.app import create_app
        from hopper.api.dependencies import get_db

        app = create_app()

        # Override database dependency
        def override_get_db():
            try:
                yield db_session
            finally:
                pass

        app.dependency_overrides[get_db] = override_get_db

        return TestClient(app)
    except ImportError:
        # API not yet integrated, return mock client
        return Mock(spec=TestClient)


@pytest.fixture
def authenticated_api_client(api_client: TestClient) -> TestClient:
    """
    Create an authenticated API client with JWT token.

    Adds Authorization header to all requests.
    """
    # Create test user and get JWT token
    try:
        from hopper.api.auth import create_access_token

        token = create_access_token({"sub": "test_user"})
        api_client.headers["Authorization"] = f"Bearer {token}"

        return api_client
    except ImportError:
        # Auth not yet integrated, return regular client
        return api_client


# ============================================================================
# MCP Client Fixtures
# ============================================================================


@pytest.fixture
def mcp_client() -> Mock:
    """
    Create a mock MCP client for testing MCP tools.

    Returns a mock client that can be used to simulate MCP tool calls.
    """
    # TODO: Replace with real MCP client once mcp-integration is complete
    return Mock()


@pytest.fixture
def mcp_context() -> dict:
    """
    Create a mock MCP context for testing context management.

    Returns a dictionary simulating MCP conversation context.
    """
    return {
        "conversation_id": "test-conv-123",
        "user_id": "test-user",
        "active_project": None,
        "session_state": {},
    }


# ============================================================================
# CLI Runner Fixtures
# ============================================================================


@pytest.fixture
def cli_runner():
    """
    Create a Click CLI test runner.

    Allows testing CLI commands in isolation.
    """
    from click.testing import CliRunner

    return CliRunner()


@pytest.fixture
def cli_config_dir(tmp_path: Path) -> Path:
    """
    Create a temporary configuration directory for CLI tests.

    Returns the path to the temp config directory.
    """
    config_dir = tmp_path / ".hopper"
    config_dir.mkdir(exist_ok=True)
    return config_dir


@pytest.fixture
def cli_runner_with_config(cli_runner, cli_config_dir: Path):
    """
    Create a CLI runner with isolated configuration.

    Sets environment variables to use temp config directory.
    """
    import os

    original_home = os.environ.get("HOME")
    os.environ["HOME"] = str(cli_config_dir.parent)

    yield cli_runner

    # Restore original HOME
    if original_home:
        os.environ["HOME"] = original_home
    else:
        del os.environ["HOME"]


# ============================================================================
# Mock Data Fixtures
# ============================================================================


@pytest.fixture
def sample_task_data() -> dict:
    """
    Sample task data for testing.
    """
    return {
        "id": "task-123",
        "title": "Implement authentication",
        "description": "Add JWT-based authentication to the API",
        "project": "hopper",
        "status": "pending",
        "priority": "high",
        "tags": {"feature": "auth", "backend": True},
        "requester": "test-user",
    }


@pytest.fixture
def sample_project_data() -> dict:
    """
    Sample project data for testing.
    """
    return {
        "id": "proj-123",
        "name": "Hopper",
        "slug": "hopper",
        "description": "Intelligent task routing system",
        "configuration": {
            "routing_rules": ["keyword_match", "tag_match"],
            "default_priority": "medium",
        },
    }


@pytest.fixture
def sample_instance_data() -> dict:
    """
    Sample Hopper instance data for testing.
    """
    return {
        "id": "inst-123",
        "name": "Global Hopper",
        "scope": "global",
        "configuration": {
            "routing_engine": "rules",
            "llm_fallback": True,
        },
    }


@pytest.fixture
def sample_routing_decision_data() -> dict:
    """
    Sample routing decision data for testing.
    """
    return {
        "id": "decision-123",
        "task_id": "task-123",
        "destination": "hopper",
        "strategy": "rules",
        "confidence": 0.85,
        "reasoning": "Matched keyword 'authentication' to hopper project",
    }


# ============================================================================
# Test Configuration
# ============================================================================


@pytest.fixture(scope="session")
def test_config() -> dict:
    """
    Test configuration dictionary.
    """
    return {
        "database_url": "sqlite:///:memory:",
        "api_base_url": "http://testserver",
        "mcp_server_url": "http://localhost:8001",
        "jwt_secret": "test-secret-key",
        "jwt_algorithm": "HS256",
        "jwt_expiration": 3600,
    }


@pytest.fixture
def temp_config_file(tmp_path: Path) -> Path:
    """
    Create a temporary configuration file for testing.
    """
    config_file = tmp_path / "hopper.yaml"
    config_content = """
database:
  url: sqlite:///:memory:

api:
  host: 0.0.0.0
  port: 8000

routing:
  default_strategy: rules
  llm_fallback: true
"""
    config_file.write_text(config_content)
    return config_file


# ============================================================================
# Cleanup Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_environment():
    """
    Reset environment variables after each test.

    Ensures test isolation by cleaning up environment variables.
    """
    original_env = os.environ.copy()
    yield

    # Restore original environment
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def cleanup_temp_files():
    """
    Clean up temporary files created during tests.
    """
    temp_files = []

    def _register_file(filepath: Path):
        temp_files.append(filepath)

    yield _register_file

    # Clean up all registered temp files
    for filepath in temp_files:
        try:
            if filepath.exists():
                if filepath.is_dir():
                    import shutil

                    shutil.rmtree(filepath)
                else:
                    filepath.unlink()
        except Exception:
            pass


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """
    Configure pytest with custom markers.
    """
    config.addinivalue_line("markers", "unit: Unit tests (fast, isolated)")
    config.addinivalue_line(
        "markers", "integration: Integration tests (slower, multiple components)"
    )
    config.addinivalue_line("markers", "e2e: End-to-end tests (slowest, full workflows)")
    config.addinivalue_line("markers", "postgres: Tests requiring PostgreSQL")
    config.addinivalue_line("markers", "slow: Slow tests (skip with -m 'not slow')")
