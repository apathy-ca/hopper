"""Tests for project management commands."""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock

from hopper.cli.main import cli


def test_project_create(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test creating a project."""
    result = runner.invoke(
        cli,
        ["project", "create", "Test Project", "--json"],
        obj=mock_config
    )

    assert result.exit_code == 0
    mock_client.create_project.assert_called_once()


def test_project_create_with_description(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test creating a project with description."""
    result = runner.invoke(
        cli,
        ["project", "create", "Test Project", "--description", "Test desc", "--json"],
        obj=mock_config
    )

    assert result.exit_code == 0
    call_args = mock_client.create_project.call_args[0][0]
    assert call_args["name"] == "Test Project"
    assert call_args["description"] == "Test desc"


def test_project_list(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test listing projects."""
    result = runner.invoke(cli, ["project", "list", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.list_projects.assert_called_once()


def test_project_get(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test getting a project."""
    mock_client.get_project.return_value = {
        "id": "proj-123",
        "name": "Test Project",
        "description": "Test description",
    }

    result = runner.invoke(cli, ["project", "get", "proj-123", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.get_project.assert_called_once_with("proj-123")


def test_project_update(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test updating a project."""
    mock_client.update_project.return_value = {"id": "proj-123", "name": "Updated"}

    result = runner.invoke(
        cli,
        ["project", "update", "proj-123", "--name", "Updated name", "--json"],
        obj=mock_config
    )

    assert result.exit_code == 0
    mock_client.update_project.assert_called_once()


def test_project_delete(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test deleting a project."""
    result = runner.invoke(
        cli,
        ["project", "delete", "proj-123", "--force"],
        obj=mock_config
    )

    assert result.exit_code == 0
    mock_client.delete_project.assert_called_once_with("proj-123")


def test_project_tasks(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test listing project tasks."""
    result = runner.invoke(
        cli,
        ["project", "tasks", "proj-123", "--json"],
        obj=mock_config
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.list_tasks.call_args[1]
    assert call_kwargs["project"] == "proj-123"
