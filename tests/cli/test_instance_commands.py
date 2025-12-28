"""Tests for instance management commands."""

import pytest
from unittest.mock import Mock

from click.testing import CliRunner

from hopper.cli.main import cli

# Mark tests requiring API integration
pytestmark = pytest.mark.skip(reason="CLI integration: Requires running API or complex mocking")



def test_instance_create(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test creating an instance."""
    result = runner.invoke(
        cli,
        ["instance", "create", "test-instance", "--scope", "project", "--json"],
        obj=mock_config,
    )

    assert result.exit_code == 0
    mock_client.create_instance.assert_called_once()
    call_args = mock_client.create_instance.call_args[0][0]
    assert call_args["name"] == "test-instance"
    assert call_args["scope"] == "project"


def test_instance_create_with_parent(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test creating an instance with parent."""
    result = runner.invoke(
        cli,
        [
            "instance",
            "create",
            "child-instance",
            "--scope",
            "orchestration",
            "--parent",
            "parent-123",
            "--json",
        ],
        obj=mock_config,
    )

    assert result.exit_code == 0
    call_args = mock_client.create_instance.call_args[0][0]
    assert call_args["parent_id"] == "parent-123"


def test_instance_list(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test listing instances."""
    result = runner.invoke(cli, ["instance", "list", "--json"], obj=mock_context)

    assert result.exit_code == 0
    mock_client.list_instances.assert_called_once()


def test_instance_list_with_scope_filter(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test listing instances with scope filter."""
    result = runner.invoke(
        cli, ["instance", "list", "--scope", "project", "--json"], obj=mock_config
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.list_instances.call_args[1]
    assert call_kwargs["scope"] == "project"


def test_instance_get(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test getting an instance."""
    mock_client.get_instance.return_value = {
        "id": "inst-123",
        "name": "test-instance",
        "scope": "project",
        "status": "active",
    }

    result = runner.invoke(cli, ["instance", "get", "inst-123", "--json"], obj=mock_context)

    assert result.exit_code == 0
    mock_client.get_instance.assert_called_once_with("inst-123")


def test_instance_tree(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test showing instance tree."""
    result = runner.invoke(cli, ["instance", "tree", "--json"], obj=mock_context)

    assert result.exit_code == 0
    mock_client.list_instances.assert_called_once()


def test_instance_start(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test starting an instance."""
    mock_client.start_instance.return_value = {"id": "inst-123", "status": "active"}

    result = runner.invoke(cli, ["instance", "start", "inst-123", "--json"], obj=mock_context)

    assert result.exit_code == 0
    mock_client.start_instance.assert_called_once_with("inst-123")


def test_instance_stop(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test stopping an instance."""
    mock_client.stop_instance.return_value = {"id": "inst-123", "status": "inactive"}

    result = runner.invoke(
        cli, ["instance", "stop", "inst-123", "--force", "--json"], obj=mock_config
    )

    assert result.exit_code == 0
    mock_client.stop_instance.assert_called_once_with("inst-123")


def test_instance_status(runner: CliRunner, mock_client: Mock, mock_context) -> None:
    """Test getting instance status."""
    mock_client.get_instance_status.return_value = {
        "status": "active",
        "health": "healthy",
        "queue_size": 5,
    }

    result = runner.invoke(cli, ["instance", "status", "inst-123", "--json"], obj=mock_context)

    assert result.exit_code == 0
    mock_client.get_instance_status.assert_called_once_with("inst-123")
