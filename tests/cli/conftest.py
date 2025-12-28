"""Pytest fixtures for CLI tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
from click.testing import CliRunner

from hopper.cli.config import APIConfig, AuthConfig, Config, ProfileConfig


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


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

    # Patch HopperClient
    from hopper.cli import client

    monkeypatch.setattr(client, "HopperClient", lambda config: mock)

    return mock
