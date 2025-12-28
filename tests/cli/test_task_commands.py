"""Tests for task management commands."""

from unittest.mock import Mock

from click.testing import CliRunner

from hopper.cli.main import cli


def test_task_add_with_title(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test creating a task with a title."""
    result = runner.invoke(cli, ["task", "add", "Test task", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.create_task.assert_called_once()


def test_task_add_with_options(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test creating a task with various options."""
    result = runner.invoke(
        cli,
        [
            "task",
            "add",
            "Test task",
            "--priority",
            "high",
            "--tag",
            "bug",
            "--tag",
            "urgent",
            "--json",
        ],
        obj=mock_config,
    )

    assert result.exit_code == 0
    call_args = mock_client.create_task.call_args
    assert call_args[0][0]["priority"] == "high"
    assert "bug" in call_args[0][0]["tags"]
    assert "urgent" in call_args[0][0]["tags"]


def test_task_list(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test listing tasks."""
    result = runner.invoke(cli, ["task", "list", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.list_tasks.assert_called_once()


def test_task_list_with_filters(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test listing tasks with filters."""
    result = runner.invoke(
        cli, ["task", "list", "--status", "open", "--priority", "high", "--json"], obj=mock_config
    )

    assert result.exit_code == 0
    call_kwargs = mock_client.list_tasks.call_args[1]
    assert call_kwargs["status"] == "open"
    assert call_kwargs["priority"] == "high"


def test_task_get(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test getting a task."""
    result = runner.invoke(cli, ["task", "get", "task-123", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.get_task.assert_called_once_with("task-123")


def test_task_update(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test updating a task."""
    mock_client.update_task.return_value = {"id": "task-123", "title": "Updated"}

    result = runner.invoke(
        cli, ["task", "update", "task-123", "--title", "Updated title", "--json"], obj=mock_config
    )

    assert result.exit_code == 0
    mock_client.update_task.assert_called_once()


def test_task_status(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test changing task status."""
    mock_client.update_task.return_value = {"id": "task-123", "status": "completed"}

    result = runner.invoke(
        cli, ["task", "status", "task-123", "completed", "--force", "--json"], obj=mock_config
    )

    assert result.exit_code == 0
    call_args = mock_client.update_task.call_args
    assert call_args[0][1]["status"] == "completed"


def test_task_delete(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test deleting a task."""
    result = runner.invoke(cli, ["task", "delete", "task-123", "--force"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.delete_task.assert_called_once_with("task-123")


def test_task_search(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test searching tasks."""
    mock_client.search_tasks.return_value = [{"id": "task-123", "title": "Found task"}]

    result = runner.invoke(cli, ["task", "search", "bug", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.search_tasks.assert_called_once()


def test_add_shortcut(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test the 'add' shortcut command."""
    result = runner.invoke(cli, ["add", "Quick task", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.create_task.assert_called_once()


def test_ls_shortcut(runner: CliRunner, mock_client: Mock, mock_config) -> None:
    """Test the 'ls' shortcut command."""
    result = runner.invoke(cli, ["ls", "--json"], obj=mock_config)

    assert result.exit_code == 0
    mock_client.list_tasks.assert_called_once()
