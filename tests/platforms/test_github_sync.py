"""Tests for GitHub sync service."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from hopper.platforms.base import GitHubIssue
from hopper.platforms.sync import GitHubSyncService, ImportResult, ExportResult


@pytest.fixture
def mock_client():
    """Create a mock GitHub client."""
    return MagicMock()


@pytest.fixture
def mock_task_store():
    """Create a mock task store."""
    store = MagicMock()
    store.list.return_value = []
    return store


@pytest.fixture
def sync_service(mock_client, mock_task_store):
    """Create a GitHubSyncService instance."""
    return GitHubSyncService(mock_client, mock_task_store)


@pytest.fixture
def sample_issue():
    """Create a sample GitHub issue."""
    return GitHubIssue(
        number=42,
        title="Fix login bug",
        body="Users can't login with special characters",
        state="open",
        labels=["bug", "priority:high"],
        html_url="https://github.com/owner/repo/issues/42",
        created_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        updated_at=datetime(2024, 1, 16, 14, 30, 0, tzinfo=timezone.utc),
    )


class TestImportResult:
    """Tests for ImportResult dataclass."""

    def test_empty_result(self):
        """Test empty import result."""
        result = ImportResult()
        assert result.total_imported == 0
        assert result.total_skipped == 0
        assert result.total_errors == 0

    def test_with_data(self):
        """Test import result with data."""
        result = ImportResult(
            imported=["task-1", "task-2"],
            skipped=["3", "4", "5"],
            errors=["Error 1"],
        )
        assert result.total_imported == 2
        assert result.total_skipped == 3
        assert result.total_errors == 1


class TestExportResult:
    """Tests for ExportResult dataclass."""

    def test_success_result(self):
        """Test successful export result."""
        result = ExportResult(
            issue_number=42,
            issue_url="https://github.com/owner/repo/issues/42",
            success=True,
        )
        assert result.success is True
        assert result.error is None

    def test_failure_result(self):
        """Test failed export result."""
        result = ExportResult(
            issue_number=0,
            issue_url="",
            success=False,
            error="Task not found",
        )
        assert result.success is False
        assert result.error == "Task not found"


class TestGitHubSyncService:
    """Tests for GitHubSyncService."""

    def test_import_issue_new(self, sync_service, mock_client, mock_task_store, sample_issue):
        """Test importing a new issue."""
        mock_client.get_issue.return_value = sample_issue

        with patch("hopper.storage.tasks.LocalTask") as MockLocalTask:
            mock_task = MagicMock()
            mock_task.id = "task-123"
            MockLocalTask.create.return_value = mock_task

            task_id = sync_service.import_issue("owner", "repo", 42)

            assert task_id == "task-123"
            mock_client.get_issue.assert_called_once_with("owner", "repo", 42)
            mock_task_store.save.assert_called_once_with(mock_task)

    def test_import_issue_skip_existing(self, sync_service, mock_client, mock_task_store, sample_issue):
        """Test skipping already imported issue."""
        # Create an existing task that matches the issue
        existing_task = MagicMock()
        existing_task.external_id = "42"
        existing_task.external_platform = "github"
        existing_task.context = "Imported from owner/repo"
        mock_task_store.list.return_value = [existing_task]

        task_id = sync_service.import_issue("owner", "repo", 42, skip_existing=True)

        assert task_id is None
        mock_client.get_issue.assert_not_called()

    def test_import_issue_force_reimport(self, sync_service, mock_client, mock_task_store, sample_issue):
        """Test force reimporting an issue."""
        mock_client.get_issue.return_value = sample_issue

        with patch("hopper.storage.tasks.LocalTask") as MockLocalTask:
            mock_task = MagicMock()
            mock_task.id = "task-new"
            MockLocalTask.create.return_value = mock_task

            task_id = sync_service.import_issue("owner", "repo", 42, skip_existing=False)

            assert task_id == "task-new"

    def test_import_all_issues(self, sync_service, mock_client, mock_task_store, sample_issue):
        """Test importing multiple issues."""
        issue2 = GitHubIssue(
            number=43,
            title="Another issue",
            body="Description",
            state="open",
            labels=[],
            html_url="https://github.com/owner/repo/issues/43",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_client.list_all_issues.return_value = [sample_issue, issue2]
        mock_client.get_issue.side_effect = [sample_issue, issue2]

        with patch("hopper.storage.tasks.LocalTask") as MockLocalTask:
            task1 = MagicMock()
            task1.id = "task-1"
            task2 = MagicMock()
            task2.id = "task-2"
            MockLocalTask.create.side_effect = [task1, task2]

            result = sync_service.import_all_issues("owner", "repo")

            assert result.total_imported == 2
            assert "task-1" in result.imported
            assert "task-2" in result.imported

    def test_import_all_issues_with_errors(self, sync_service, mock_client, mock_task_store, sample_issue):
        """Test importing issues with some errors."""
        mock_client.list_all_issues.return_value = [sample_issue]
        mock_client.get_issue.side_effect = Exception("API error")

        result = sync_service.import_all_issues("owner", "repo")

        assert result.total_imported == 0
        assert result.total_errors == 1
        assert "API error" in result.errors[0]

    def test_export_task_success(self, sync_service, mock_client, mock_task_store):
        """Test exporting a task successfully."""
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.title = "New feature"
        mock_task.description = "Add dark mode"
        mock_task.status = "pending"
        mock_task.priority = "high"
        mock_task.tags = ["feature"]
        mock_task.external_id = None
        mock_task.external_url = None
        mock_task.external_platform = None
        mock_task_store.get.return_value = mock_task

        created_issue = GitHubIssue(
            number=99,
            title="New feature",
            body="Add dark mode",
            state="open",
            labels=["feature", "priority:high"],
            html_url="https://github.com/owner/repo/issues/99",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_client.create_issue.return_value = created_issue

        result = sync_service.export_task("task-123", "owner", "repo")

        assert result.success is True
        assert result.issue_number == 99
        assert result.issue_url == "https://github.com/owner/repo/issues/99"
        mock_task_store.save.assert_called_once()

    def test_export_task_not_found(self, sync_service, mock_task_store):
        """Test exporting a non-existent task."""
        mock_task_store.get.return_value = None

        result = sync_service.export_task("nonexistent", "owner", "repo")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_export_task_already_exported(self, sync_service, mock_task_store):
        """Test exporting an already exported task."""
        mock_task = MagicMock()
        mock_task.external_id = "42"
        mock_task.external_platform = "github"
        mock_task.external_url = "https://github.com/owner/repo/issues/42"
        mock_task_store.get.return_value = mock_task

        result = sync_service.export_task("task-123", "owner", "repo")

        assert result.success is False
        assert "already exported" in result.error.lower()

    def test_export_task_api_error(self, sync_service, mock_client, mock_task_store):
        """Test export when GitHub API fails."""
        mock_task = MagicMock()
        mock_task.id = "task-123"
        mock_task.title = "New feature"
        mock_task.description = "Add dark mode"
        mock_task.status = "pending"
        mock_task.priority = "high"
        mock_task.tags = []
        mock_task.external_id = None
        mock_task.external_url = None
        mock_task.external_platform = None
        mock_task_store.get.return_value = mock_task

        mock_client.create_issue.side_effect = Exception("API error")

        result = sync_service.export_task("task-123", "owner", "repo")

        assert result.success is False
        assert "API error" in result.error

    def test_sync_status_to_github(self, sync_service, mock_client, mock_task_store, sample_issue):
        """Test syncing task status to GitHub."""
        mock_task = MagicMock()
        mock_task.status = "done"
        mock_task.external_id = "42"
        mock_task_store.get.return_value = mock_task

        # Issue is currently open
        mock_client.get_issue.return_value = sample_issue

        result = sync_service.sync_status_to_github("task-123", "owner", "repo")

        assert result is True
        mock_client.update_issue.assert_called_once_with("owner", "repo", 42, state="closed")

    def test_sync_status_no_change_needed(self, sync_service, mock_client, mock_task_store):
        """Test sync when no status change needed."""
        mock_task = MagicMock()
        mock_task.status = "pending"
        mock_task.external_id = "42"
        mock_task_store.get.return_value = mock_task

        # Issue is also open
        open_issue = GitHubIssue(
            number=42,
            title="Issue",
            body=None,
            state="open",
            labels=[],
            html_url="https://github.com/owner/repo/issues/42",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        mock_client.get_issue.return_value = open_issue

        result = sync_service.sync_status_to_github("task-123", "owner", "repo")

        assert result is False
        mock_client.update_issue.assert_not_called()

    def test_sync_status_no_external_id(self, sync_service, mock_task_store):
        """Test sync when task has no external ID."""
        mock_task = MagicMock()
        mock_task.external_id = None
        mock_task_store.get.return_value = mock_task

        result = sync_service.sync_status_to_github("task-123", "owner", "repo")

        assert result is False

    def test_list_issues(self, sync_service, mock_client, sample_issue):
        """Test listing issues."""
        mock_client.list_issues.return_value = [sample_issue]

        issues = sync_service.list_issues("owner", "repo", state="open")

        assert len(issues) == 1
        assert issues[0].number == 42
        mock_client.list_issues.assert_called_once_with("owner", "repo", state="open")
