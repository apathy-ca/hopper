"""Tests for GitHub client."""

from unittest.mock import MagicMock, patch

import pytest

from hopper.platforms.base import (
    GitHubIssue,
    PlatformAuthError,
    PlatformNotFoundError,
    PlatformRateLimitError,
)
from hopper.platforms.github.client import GitHubClient


@pytest.fixture
def mock_response():
    """Create a mock httpx response."""
    response = MagicMock()
    response.status_code = 200
    response.headers = {}
    return response


@pytest.fixture
def sample_issue_data():
    """Sample GitHub API issue response."""
    return {
        "number": 42,
        "title": "Fix login bug",
        "body": "Users can't login",
        "state": "open",
        "labels": [{"name": "bug"}, {"name": "priority:high"}],
        "html_url": "https://github.com/owner/repo/issues/42",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-16T14:30:00Z",
    }


class TestGitHubClient:
    """Tests for GitHubClient."""

    def test_init(self):
        """Test client initialization."""
        client = GitHubClient("test-token")
        assert client.token == "test-token"
        assert client.base_url == "https://api.github.com"
        client.close()

    def test_custom_base_url(self):
        """Test client with custom base URL."""
        client = GitHubClient("token", base_url="https://github.example.com/api/v3")
        assert client.base_url == "https://github.example.com/api/v3"
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_get_issue(self, mock_client_class, sample_issue_data):
        """Test getting a single issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = sample_issue_data
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        issue = client.get_issue("owner", "repo", 42)

        assert issue.number == 42
        assert issue.title == "Fix login bug"
        assert issue.state == "open"
        assert "bug" in issue.labels
        mock_client.get.assert_called_once()
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_get_issue_not_found(self, mock_client_class):
        """Test getting a non-existent issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"message": "Not Found"}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        with pytest.raises(PlatformNotFoundError):
            client.get_issue("owner", "repo", 9999)
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_get_issue_auth_error(self, mock_client_class):
        """Test getting issue with invalid token."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Bad credentials"}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("bad-token")
        with pytest.raises(PlatformAuthError):
            client.get_issue("owner", "repo", 1)
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_create_issue(self, mock_client_class, sample_issue_data):
        """Test creating an issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = sample_issue_data
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        issue = client.create_issue(
            "owner",
            "repo",
            title="Fix login bug",
            body="Users can't login",
            labels=["bug"],
        )

        assert issue.number == 42
        assert issue.title == "Fix login bug"
        mock_client.post.assert_called_once()
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_update_issue(self, mock_client_class, sample_issue_data):
        """Test updating an issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        updated_data = {**sample_issue_data, "state": "closed"}
        mock_response.json.return_value = updated_data
        mock_client.patch.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        issue = client.update_issue("owner", "repo", 42, state="closed")

        assert issue.state == "closed"
        mock_client.patch.assert_called_once()
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_close_issue(self, mock_client_class, sample_issue_data):
        """Test closing an issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        closed_data = {**sample_issue_data, "state": "closed"}
        mock_response.json.return_value = closed_data
        mock_client.patch.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        issue = client.close_issue("owner", "repo", 42)

        assert issue.state == "closed"
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_list_issues(self, mock_client_class, sample_issue_data):
        """Test listing issues."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [sample_issue_data]
        mock_response.headers = {}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        issues = client.list_issues("owner", "repo", state="open")

        assert len(issues) == 1
        assert issues[0].number == 42
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_list_issues_pagination(self, mock_client_class, sample_issue_data):
        """Test listing issues with pagination."""
        mock_client = MagicMock()

        # First page - return full page (100 issues would be full, but we use 1 for simplicity)
        # Implementation checks if len(issues) < per_page to determine if there's more
        first_response = MagicMock()
        first_response.status_code = 200
        # Return 100 issues to simulate a full page
        first_page_issues = [sample_issue_data] * 100
        first_response.json.return_value = first_page_issues

        # Second page - return less than per_page to signal end
        second_issue = {**sample_issue_data, "number": 43, "title": "Another issue"}
        second_response = MagicMock()
        second_response.status_code = 200
        second_response.json.return_value = [second_issue]  # Less than 100, signals end

        mock_client.get.side_effect = [first_response, second_response]
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        issues = client.list_all_issues("owner", "repo", max_issues=150)

        # Should get 101 issues (100 from first page + 1 from second)
        assert len(issues) == 101
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_rate_limit_error(self, mock_client_class):
        """Test rate limit handling."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.headers = {"X-RateLimit-Remaining": "0"}
        mock_response.text = "API rate limit exceeded"  # Used by _handle_response
        mock_response.json.return_value = {"message": "API rate limit exceeded"}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        with pytest.raises(PlatformRateLimitError):
            client.get_issue("owner", "repo", 1)
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_test_connection(self, mock_client_class):
        """Test connection verification."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"login": "testuser", "id": 123}
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        user_data = client.test_connection()

        assert user_data["login"] == "testuser"
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_context_manager(self, mock_client_class):
        """Test using client as context manager."""
        mock_httpx_client = MagicMock()
        mock_client_class.return_value = mock_httpx_client

        with GitHubClient("test-token") as client:
            assert client.token == "test-token"
            # Access the client property to trigger lazy initialization
            _ = client.client

        mock_httpx_client.close.assert_called_once()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_add_labels(self, mock_client_class, sample_issue_data):
        """Test adding labels to an issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"name": "bug"}, {"name": "new-label"}]
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        labels = client.add_labels("owner", "repo", 42, ["new-label"])

        assert "new-label" in labels
        client.close()

    @patch("hopper.platforms.github.client.httpx.Client")
    def test_remove_label(self, mock_client_class):
        """Test removing a label from an issue."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_client.delete.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = GitHubClient("test-token")
        # remove_label returns None
        result = client.remove_label("owner", "repo", 42, "old-label")

        assert result is None
        mock_client.delete.assert_called_once()
        client.close()


class TestGitHubIssueFromApiResponse:
    """Tests for GitHubIssue.from_api_response."""

    def test_basic_response(self, sample_issue_data):
        """Test parsing basic API response."""
        issue = GitHubIssue.from_api_response(sample_issue_data)

        assert issue.number == 42
        assert issue.title == "Fix login bug"
        assert issue.body == "Users can't login"
        assert issue.state == "open"
        assert issue.labels == ["bug", "priority:high"]
        assert issue.html_url == "https://github.com/owner/repo/issues/42"

    def test_null_body(self, sample_issue_data):
        """Test parsing response with null body."""
        data = {**sample_issue_data, "body": None}
        issue = GitHubIssue.from_api_response(data)

        assert issue.body is None

    def test_empty_labels(self, sample_issue_data):
        """Test parsing response with no labels."""
        data = {**sample_issue_data, "labels": []}
        issue = GitHubIssue.from_api_response(data)

        assert issue.labels == []

    def test_datetime_parsing(self, sample_issue_data):
        """Test datetime parsing from API response."""
        issue = GitHubIssue.from_api_response(sample_issue_data)

        assert issue.created_at.year == 2024
        assert issue.created_at.month == 1
        assert issue.created_at.day == 15
