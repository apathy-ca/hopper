"""Tests for GitHub CLI commands."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hopper.cli.main import Context, cli


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_config():
    """Create a mock configuration."""
    config = MagicMock()
    config.current_profile.github.token = "test-token"
    config.current_profile.github.default_owner = None
    config.current_profile.mode = "local"
    config.current_profile.local.auto_detect_embedded = False
    config.current_profile.local.path = "/tmp/hopper-test"
    config.current_profile.api.endpoint = "http://localhost:8000"
    config.config_path = "/tmp/config.yaml"
    return config


@pytest.fixture
def mock_context(mock_config):
    """Create a mock CLI context."""
    ctx = Context(config=mock_config, verbose=False, json_output=False, server=False)
    return ctx


@pytest.fixture
def sample_issue():
    """Create a sample GitHub issue."""
    from hopper.platforms.base import GitHubIssue

    return GitHubIssue(
        number=42,
        title="Fix login bug",
        body="Users can't login",
        state="open",
        labels=["bug", "priority:high"],
        html_url="https://github.com/owner/repo/issues/42",
        created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 1, 16, 14, 30, 0, tzinfo=UTC),
    )


class TestGitHubAuth:
    """Tests for github auth command."""

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_auth_success(self, mock_load_config, mock_client_class, runner, mock_config):
        """Test successful authentication."""
        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.test_connection.return_value = {"login": "testuser"}
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli, ["github", "auth", "--token", "new-token"])

        assert result.exit_code == 0
        assert "testuser" in result.output
        mock_config.save.assert_called_once()

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_auth_with_default_owner(
        self, mock_load_config, mock_client_class, runner, mock_config
    ):
        """Test authentication with default owner."""
        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.test_connection.return_value = {"login": "testuser"}
        mock_client_class.return_value = mock_client

        result = runner.invoke(
            cli, ["github", "auth", "--token", "new-token", "--default-owner", "myorg"]
        )

        assert result.exit_code == 0
        assert "myorg" in result.output
        assert mock_config.current_profile.github.default_owner == "myorg"

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_auth_invalid_token(self, mock_load_config, mock_client_class, runner, mock_config):
        """Test authentication with invalid token."""
        from hopper.platforms import PlatformAuthError

        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.test_connection.side_effect = PlatformAuthError("Invalid token")
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli, ["github", "auth", "--token", "bad-token"])

        assert result.exit_code == 1
        assert "Invalid" in result.output or "invalid" in result.output.lower()


class TestGitHubList:
    """Tests for github list command."""

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_list_issues(
        self, mock_load_config, mock_client_class, runner, mock_config, sample_issue
    ):
        """Test listing issues."""
        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.list_issues.return_value = [sample_issue]
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli, ["github", "list", "owner/repo"])

        assert result.exit_code == 0
        assert "#42" in result.output
        assert "Fix login bug" in result.output

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_list_issues_json(
        self, mock_load_config, mock_client_class, runner, mock_config, sample_issue
    ):
        """Test listing issues with JSON output."""
        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.list_issues.return_value = [sample_issue]
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli, ["--json", "github", "list", "owner/repo"])

        assert result.exit_code == 0
        assert "42" in result.output

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_list_issues_empty(self, mock_load_config, mock_client_class, runner, mock_config):
        """Test listing issues when none found."""
        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.list_issues.return_value = []
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli, ["github", "list", "owner/repo"])

        assert result.exit_code == 0
        assert "No" in result.output or "no" in result.output

    @patch("hopper.cli.main.load_config")
    def test_list_invalid_repo_format(self, mock_load_config, runner, mock_config):
        """Test listing issues with invalid repo format."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, ["github", "list", "invalid"])

        assert result.exit_code == 1
        assert "Invalid" in result.output or "invalid" in result.output.lower()


class TestGitHubImport:
    """Tests for github import command."""

    @patch("hopper.cli.local_client.LocalClient")
    @patch("hopper.cli.commands.github.GitHubSyncService")
    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.config.get_storage_path")
    @patch("hopper.cli.main.load_config")
    def test_import_single_issue(
        self,
        mock_load_config,
        mock_get_storage,
        mock_client_class,
        mock_sync_class,
        mock_local_client,
        runner,
        mock_config,
    ):
        """Test importing a single issue."""
        mock_load_config.return_value = mock_config
        mock_get_storage.return_value = "/tmp/hopper"
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_sync = MagicMock()
        mock_sync.import_issue.return_value = "task-123"
        mock_sync_class.return_value = mock_sync

        result = runner.invoke(cli, ["github", "import", "owner/repo", "--issue", "42"])

        assert result.exit_code == 0
        assert "task-123" in result.output or "42" in result.output

    @patch("hopper.cli.local_client.LocalClient")
    @patch("hopper.cli.commands.github.GitHubSyncService")
    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.config.get_storage_path")
    @patch("hopper.cli.main.load_config")
    def test_import_all_issues(
        self,
        mock_load_config,
        mock_get_storage,
        mock_client_class,
        mock_sync_class,
        mock_local_client,
        runner,
        mock_config,
    ):
        """Test importing all issues."""
        from hopper.platforms.sync import ImportResult

        mock_load_config.return_value = mock_config
        mock_get_storage.return_value = "/tmp/hopper"
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_sync = MagicMock()
        mock_sync.import_all_issues.return_value = ImportResult(
            imported=["task-1", "task-2"],
            skipped=["3"],
            errors=[],
        )
        mock_sync_class.return_value = mock_sync

        result = runner.invoke(cli, ["github", "import", "owner/repo", "--all"])

        assert result.exit_code == 0
        assert "2" in result.output  # 2 imported

    @patch("hopper.cli.main.load_config")
    def test_import_requires_option(self, mock_load_config, runner, mock_config):
        """Test import requires --issue or --all."""
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, ["github", "import", "owner/repo"])

        assert result.exit_code == 1
        assert "--issue" in result.output or "--all" in result.output


class TestGitHubExport:
    """Tests for github export command."""

    @patch("hopper.cli.local_client.LocalClient")
    @patch("hopper.cli.commands.github.GitHubSyncService")
    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.config.get_storage_path")
    @patch("hopper.cli.main.load_config")
    def test_export_task(
        self,
        mock_load_config,
        mock_get_storage,
        mock_client_class,
        mock_sync_class,
        mock_local_client,
        runner,
        mock_config,
    ):
        """Test exporting a task."""
        from hopper.platforms.sync import ExportResult

        mock_load_config.return_value = mock_config
        mock_get_storage.return_value = "/tmp/hopper"
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_sync = MagicMock()
        mock_sync.export_task.return_value = ExportResult(
            issue_number=99,
            issue_url="https://github.com/owner/repo/issues/99",
            success=True,
        )
        mock_sync_class.return_value = mock_sync

        result = runner.invoke(cli, ["github", "export", "task-123", "--repo", "owner/repo"])

        assert result.exit_code == 0
        assert "#99" in result.output or "99" in result.output

    @patch("hopper.cli.local_client.LocalClient")
    @patch("hopper.cli.commands.github.GitHubSyncService")
    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.config.get_storage_path")
    @patch("hopper.cli.main.load_config")
    def test_export_task_failure(
        self,
        mock_load_config,
        mock_get_storage,
        mock_client_class,
        mock_sync_class,
        mock_local_client,
        runner,
        mock_config,
    ):
        """Test export failure."""
        from hopper.platforms.sync import ExportResult

        mock_load_config.return_value = mock_config
        mock_get_storage.return_value = "/tmp/hopper"
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_sync = MagicMock()
        mock_sync.export_task.return_value = ExportResult(
            issue_number=0,
            issue_url="",
            success=False,
            error="Task not found",
        )
        mock_sync_class.return_value = mock_sync

        result = runner.invoke(cli, ["github", "export", "nonexistent", "--repo", "owner/repo"])

        assert result.exit_code == 1


class TestGitHubStatus:
    """Tests for github status command."""

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_status_authenticated(self, mock_load_config, mock_client_class, runner, mock_config):
        """Test status when authenticated."""
        mock_load_config.return_value = mock_config
        mock_client = MagicMock()
        mock_client.test_connection.return_value = {"login": "testuser"}
        mock_client_class.return_value = mock_client

        result = runner.invoke(cli, ["github", "status"])

        assert result.exit_code == 0
        assert "testuser" in result.output

    @patch("hopper.cli.main.load_config")
    def test_status_not_authenticated(self, mock_load_config, runner):
        """Test status when not authenticated."""
        mock_config = MagicMock()
        mock_config.current_profile.github.token = None
        mock_config.current_profile.mode = "server"
        mock_config.current_profile.local.auto_detect_embedded = False
        mock_config.current_profile.api.endpoint = "http://localhost:8000"
        mock_config.config_path = "/tmp/config.yaml"
        mock_load_config.return_value = mock_config

        result = runner.invoke(cli, ["github", "status"])

        assert result.exit_code == 0
        assert "Not authenticated" in result.output or "not" in result.output.lower()


class TestGitHubTokenRetrieval:
    """Tests for token retrieval from config and environment."""

    @patch("hopper.cli.commands.github.GitHubClient")
    @patch("hopper.cli.main.load_config")
    def test_uses_env_token_as_fallback(
        self, mock_load_config, mock_client_class, runner, sample_issue
    ):
        """Test using GITHUB_TOKEN from environment."""
        import os

        mock_config = MagicMock()
        mock_config.current_profile.github.token = None  # No config token
        mock_config.current_profile.github.default_owner = None
        mock_config.current_profile.mode = "server"
        mock_config.current_profile.local.auto_detect_embedded = False
        mock_config.current_profile.api.endpoint = "http://localhost:8000"
        mock_config.config_path = "/tmp/config.yaml"
        mock_load_config.return_value = mock_config

        mock_client = MagicMock()
        mock_client.list_issues.return_value = [sample_issue]
        mock_client_class.return_value = mock_client

        # Set the environment variable for this test
        with patch.dict(os.environ, {"GITHUB_TOKEN": "env-token"}):
            result = runner.invoke(cli, ["github", "list", "owner/repo"])

        assert result.exit_code == 0
        mock_client_class.assert_called_with("env-token")

    @patch("hopper.cli.main.load_config")
    def test_error_when_no_token(self, mock_load_config, runner):
        """Test error when no token available."""
        import os

        mock_config = MagicMock()
        mock_config.current_profile.github.token = None
        mock_config.current_profile.mode = "server"
        mock_config.current_profile.local.auto_detect_embedded = False
        mock_config.current_profile.api.endpoint = "http://localhost:8000"
        mock_config.config_path = "/tmp/config.yaml"
        mock_load_config.return_value = mock_config

        # Ensure GITHUB_TOKEN is not set
        env = os.environ.copy()
        env.pop("GITHUB_TOKEN", None)

        with patch.dict(os.environ, env, clear=True):
            result = runner.invoke(cli, ["github", "list", "owner/repo"])

        assert result.exit_code == 1
        assert "token" in result.output.lower()
