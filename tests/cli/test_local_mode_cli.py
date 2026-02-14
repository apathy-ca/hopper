"""Integration tests for CLI in local mode.

These tests exercise the full CLI stack using local markdown storage,
providing true end-to-end testing without mocking.
"""

import json
import tempfile
from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.main import cli


@pytest.fixture
def isolated_runner():
    """Create a CLI runner with isolated environment."""
    runner = CliRunner()
    with runner.isolated_filesystem() as tmpdir:
        # Create .hopper directory for auto-detection
        # Include tasks/ subdirectory so detect_embedded_hopper() finds it
        hopper_dir = Path(tmpdir) / ".hopper"
        hopper_dir.mkdir()
        (hopper_dir / "tasks").mkdir()
        yield runner, hopper_dir


class TestLocalTaskCommands:
    """Test task commands in local mode."""

    def test_task_add_and_list(self, isolated_runner):
        """Test adding and listing tasks."""
        runner, _ = isolated_runner

        # Add a task (--json is a global option, must come before subcommand)
        # Use --tag to skip interactive prompts
        result = runner.invoke(cli, ["--local", "--json", "task", "add", "Test task", "--tag", "test"])
        assert result.exit_code == 0, f"Failed: {result.output}"

        # Parse the JSON output (may span multiple lines)
        output = json.loads(result.output.strip())
        assert output["title"] == "Test task"

        # List tasks
        result = runner.invoke(cli, ["--local", "--json", "task", "list"])
        assert result.exit_code == 0

    def test_task_add_with_options(self, isolated_runner):
        """Test adding a task with options."""
        runner, _ = isolated_runner

        result = runner.invoke(
            cli,
            [
                "--local",
                "--json",
                "task",
                "add",
                "High priority bug",
                "--priority",
                "high",
                "--tag",
                "bug",
                "--tag",
                "urgent",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"

        output = json.loads(result.output.strip())
        assert output["priority"] == "high"
        assert "bug" in output["tags"]
        assert "urgent" in output["tags"]

    def test_task_get(self, isolated_runner):
        """Test getting a task by ID."""
        runner, _ = isolated_runner

        # Add a task first (--tag to skip prompts)
        result = runner.invoke(cli, ["--local", "--json", "task", "add", "Get test", "--tag", "test"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        output = json.loads(result.output.strip())
        task_id = output["id"]

        # Get the task
        result = runner.invoke(cli, ["--local", "--json", "task", "get", task_id])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_task_update(self, isolated_runner):
        """Test updating a task."""
        runner, _ = isolated_runner

        # Add a task (--tag to skip prompts)
        result = runner.invoke(cli, ["--local", "--json", "task", "add", "Original title", "--tag", "test"])
        assert result.exit_code == 0, f"Failed to add: {result.output}"
        output = json.loads(result.output.strip())
        task_id = output["id"]

        # Update the task
        result = runner.invoke(
            cli,
            ["--local", "--json", "task", "update", task_id, "--title", "Updated title"],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_task_status_change(self, isolated_runner):
        """Test changing task status."""
        runner, _ = isolated_runner

        # Add a task (--tag to skip prompts)
        result = runner.invoke(cli, ["--local", "--json", "task", "add", "Status test", "--tag", "test"])
        assert result.exit_code == 0, f"Failed to add: {result.output}"
        output = json.loads(result.output.strip())
        task_id = output["id"]

        # Change status
        result = runner.invoke(
            cli,
            ["--local", "--json", "task", "status", task_id, "in_progress", "--force"],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_task_delete(self, isolated_runner):
        """Test deleting a task."""
        runner, _ = isolated_runner

        # Add a task (--tag to skip prompts)
        result = runner.invoke(cli, ["--local", "--json", "task", "add", "Delete me", "--tag", "test"])
        assert result.exit_code == 0, f"Failed to add: {result.output}"
        output = json.loads(result.output.strip())
        task_id = output["id"]

        # Delete the task
        result = runner.invoke(cli, ["--local", "task", "delete", task_id, "--force"])
        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify it's gone
        result = runner.invoke(cli, ["--local", "--json", "task", "get", task_id])
        assert result.exit_code != 0  # Should fail

    def test_task_search(self, isolated_runner):
        """Test searching tasks."""
        runner, _ = isolated_runner

        # Add tasks (--tag to skip prompts)
        runner.invoke(cli, ["--local", "task", "add", "Login bug fix", "--tag", "test"])
        runner.invoke(cli, ["--local", "task", "add", "Add dark mode", "--tag", "test"])
        runner.invoke(cli, ["--local", "task", "add", "Fix login validation", "--tag", "test"])

        # Search
        result = runner.invoke(cli, ["--local", "--json", "task", "search", "login"])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_add_shortcut(self, isolated_runner):
        """Test the 'add' shortcut command."""
        runner, _ = isolated_runner

        # Use --tag to skip prompts
        result = runner.invoke(cli, ["--local", "--json", "add", "Quick task", "--tag", "test"])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_ls_shortcut(self, isolated_runner):
        """Test the 'ls' shortcut command."""
        runner, _ = isolated_runner

        # Add some tasks first (--tag to skip prompts)
        runner.invoke(cli, ["--local", "task", "add", "Task 1", "--tag", "test"])
        runner.invoke(cli, ["--local", "task", "add", "Task 2", "--tag", "test"])

        result = runner.invoke(cli, ["--local", "--json", "ls"])
        assert result.exit_code == 0, f"Failed: {result.output}"


class TestLocalLearningCommands:
    """Test learning commands in local mode."""

    def test_learning_stats(self, isolated_runner):
        """Test getting learning statistics."""
        runner, _ = isolated_runner

        result = runner.invoke(cli, ["--local", "--json", "learning", "stats"])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_feedback_submit_and_list(self, isolated_runner):
        """Test submitting and listing feedback."""
        runner, _ = isolated_runner

        # Add a task first (--tag to skip prompts)
        result = runner.invoke(cli, ["--local", "--json", "task", "add", "Feedback test", "--tag", "test"])
        assert result.exit_code == 0, f"Failed to add: {result.output}"
        output = json.loads(result.output.strip())
        task_id = output["id"]

        # Submit feedback
        result = runner.invoke(
            cli,
            ["--local", "--json", "learning", "feedback", "submit", task_id, "--good"],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"

        # List feedback
        result = runner.invoke(cli, ["--local", "--json", "learning", "feedback", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_pattern_create_and_list(self, isolated_runner):
        """Test creating and listing patterns."""
        runner, _ = isolated_runner

        # Create a pattern
        result = runner.invoke(
            cli,
            [
                "--local",
                "--json",
                "learning",
                "pattern",
                "create",
                "--name",
                "API Tasks",
                "--target",
                "api-worker",
                "--required-tag",
                "api",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"

        # List patterns
        result = runner.invoke(cli, ["--local", "--json", "learning", "pattern", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"

    def test_routing_accuracy(self, isolated_runner):
        """Test getting routing accuracy."""
        runner, _ = isolated_runner

        result = runner.invoke(cli, ["--local", "--json", "learning", "feedback", "accuracy"])
        assert result.exit_code == 0, f"Failed: {result.output}"


class TestVerboseMode:
    """Test verbose output mode."""

    def test_verbose_shows_mode(self, isolated_runner):
        """Test that verbose mode shows the storage mode."""
        runner, hopper_dir = isolated_runner

        result = runner.invoke(cli, ["--local", "-v", "task", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        assert "local" in result.output.lower()


class TestEmbeddedDetection:
    """Test embedded .hopper directory detection."""

    def test_auto_detect_embedded(self, isolated_runner):
        """Test that embedded .hopper is auto-detected."""
        runner, hopper_dir = isolated_runner

        # Initialize storage by adding a task (--tag to skip prompts)
        result = runner.invoke(cli, ["--local", "task", "add", "Embedded task", "--tag", "test"])
        assert result.exit_code == 0, f"Failed: {result.output}"

        # Verify the task file was created in the embedded directory
        tasks_dir = hopper_dir / "tasks"
        assert tasks_dir.exists()
        assert len(list(tasks_dir.glob("*.md"))) == 1
