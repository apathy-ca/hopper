"""Pytest fixtures for CLI tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from click.testing import CliRunner

from hopper.cli.config import APIConfig, AuthConfig, Config, LocalConfig, ProfileConfig


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def local_storage_path() -> Generator[Path, None, None]:
    """Create a temporary directory for local storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def local_config(local_storage_path: Path) -> Config:
    """Create a configuration for local mode testing."""
    config_path = local_storage_path / "config.yaml"

    return Config(
        active_profile="local",
        profiles={
            "local": ProfileConfig(
                mode="local",
                api=APIConfig(
                    endpoint="http://localhost:8000",
                    timeout=30,
                ),
                auth=AuthConfig(),
                local=LocalConfig(
                    path=local_storage_path,
                    auto_detect_embedded=False,
                ),
            )
        },
        config_path=config_path,
    )


@pytest.fixture
def local_context(local_config: Config) -> "Context":
    """Create a CLI context for local mode testing."""
    from hopper.cli.main import Context

    return Context(config=local_config, verbose=False, json_output=True, local=True)


@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    """Create a temporary configuration directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_config(temp_config_dir: Path) -> Config:
    """Create a mock configuration."""
    config_path = temp_config_dir / "config.yaml"

    return Config(
        active_profile="test",
        profiles={
            "test": ProfileConfig(
                api=APIConfig(
                    endpoint="http://localhost:8000",
                    timeout=30,
                ),
                auth=AuthConfig(
                    token="test-token-12345",
                    api_key=None,
                ),
            )
        },
        config_path=config_path,
    )


@pytest.fixture
def mock_context(mock_config: Config) -> "Context":
    """Create a mock CLI context."""
    from hopper.cli.main import Context

    return Context(config=mock_config, verbose=False, json_output=True)


@pytest.fixture
def mock_client(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Create a mock Hopper client."""
    mock = MagicMock()

    # Mock common responses
    mock.create_task.return_value = {
        "id": "task-123",
        "title": "Test task",
        "status": "open",
        "priority": "medium",
        "created_at": "2025-12-28T00:00:00Z",
    }

    mock.list_tasks.return_value = [
        {
            "id": "task-123",
            "title": "Test task 1",
            "status": "open",
            "priority": "high",
            "created_at": "2025-12-28T00:00:00Z",
        },
        {
            "id": "task-456",
            "title": "Test task 2",
            "status": "in_progress",
            "priority": "medium",
            "created_at": "2025-12-28T01:00:00Z",
        },
    ]

    mock.get_task.return_value = {
        "id": "task-123",
        "title": "Test task",
        "description": "Test description",
        "status": "open",
        "priority": "high",
        "tags": ["bug", "urgent"],
        "created_at": "2025-12-28T00:00:00Z",
    }

    mock.create_project.return_value = {
        "id": "proj-123",
        "name": "Test Project",
        "description": "Test description",
        "created_at": "2025-12-28T00:00:00Z",
    }

    mock.list_projects.return_value = [
        {
            "id": "proj-123",
            "name": "Test Project",
            "description": "Test description",
            "task_count": 5,
            "created_at": "2025-12-28T00:00:00Z",
        }
    ]

    mock.create_instance.return_value = {
        "id": "inst-123",
        "name": "test-instance",
        "scope": "project",
        "status": "active",
        "created_at": "2025-12-28T00:00:00Z",
    }

    mock.list_instances.return_value = [
        {
            "id": "inst-global",
            "name": "global-hopper",
            "scope": "global",
            "status": "active",
            "parent_id": None,
        },
        {
            "id": "inst-project",
            "name": "project-hopper",
            "scope": "project",
            "status": "active",
            "parent_id": "inst-global",
        },
    ]

    # Mock context manager
    mock.__enter__ = Mock(return_value=mock)
    mock.__exit__ = Mock(return_value=None)

    # Patch HopperClient - patch it in the client module itself
    monkeypatch.setattr("hopper.cli.client.HopperClient", lambda config: mock)

    # Also patch in all command modules that import it
    monkeypatch.setattr("hopper.cli.commands.task.HopperClient", lambda config: mock)
    monkeypatch.setattr("hopper.cli.commands.project.HopperClient", lambda config: mock)
    monkeypatch.setattr("hopper.cli.commands.instance.HopperClient", lambda config: mock)
    monkeypatch.setattr("hopper.cli.commands.config.HopperClient", lambda config: mock)

    return mock
