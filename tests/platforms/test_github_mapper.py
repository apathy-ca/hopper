"""Tests for GitHub mapper."""

from datetime import datetime, timezone

import pytest

from hopper.platforms.base import GitHubIssue
from hopper.platforms.github.mapper import GitHubMapper


@pytest.fixture
def mapper():
    """Create a GitHubMapper instance."""
    return GitHubMapper()


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


class TestGitHubMapper:
    """Tests for GitHubMapper."""

    def test_issue_to_task_data_basic(self, mapper, sample_issue):
        """Test converting issue to task data."""
        result = mapper.issue_to_task_data(sample_issue, "owner", "repo")

        assert result["title"] == "Fix login bug"
        assert result["description"] == "Users can't login with special characters"
        assert result["status"] == "pending"
        assert result["external_id"] == "42"
        assert result["external_url"] == "https://github.com/owner/repo/issues/42"
        assert result["external_platform"] == "github"
        assert "bug" in result["tags"]
        assert result["priority"] == "high"
        assert "owner/repo" in result["context"]

    def test_issue_to_task_data_with_project(self, mapper, sample_issue):
        """Test converting issue with project ID."""
        result = mapper.issue_to_task_data(sample_issue, "owner", "repo", project_id="proj-123")

        assert result["project_id"] == "proj-123"

    def test_issue_to_task_data_closed_issue(self, mapper):
        """Test converting closed issue."""
        issue = GitHubIssue(
            number=1,
            title="Done task",
            body=None,
            state="closed",
            labels=[],
            html_url="https://github.com/owner/repo/issues/1",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        result = mapper.issue_to_task_data(issue, "owner", "repo")

        assert result["status"] == "done"

    def test_task_to_issue_data_basic(self, mapper):
        """Test converting task to issue data."""
        task = {
            "id": "task-123",
            "title": "New feature",
            "description": "Add dark mode",
            "priority": "high",
            "tags": ["feature", "ui"],
        }

        result = mapper.task_to_issue_data(task)

        assert result["title"] == "New feature"
        assert "Add dark mode" in result["body"]
        assert "Exported from Hopper" in result["body"]
        assert "priority:high" in result["labels"]
        assert "feature" in result["labels"]
        assert "ui" in result["labels"]

    def test_task_to_issue_data_minimal(self, mapper):
        """Test converting task with minimal data."""
        task = {"title": "Simple task"}

        result = mapper.task_to_issue_data(task)

        assert result["title"] == "Simple task"
        assert "body" not in result  # No description means no body
        assert "labels" not in result or result.get("labels") == []

    def test_labels_to_tags(self, mapper):
        """Test converting GitHub labels to tags."""
        labels = ["bug", "priority:high", "wontfix", "priority:low"]

        tags = mapper.labels_to_tags(labels)

        assert "bug" in tags
        assert "wontfix" in tags
        # Priority labels should be excluded
        assert "priority:high" not in tags
        assert "priority:low" not in tags

    def test_tags_to_labels(self, mapper):
        """Test converting tags to GitHub labels."""
        tags = ["bug", "feature", "ui"]

        labels = mapper.tags_to_labels(tags)

        assert labels == ["bug", "feature", "ui"]

    def test_state_to_status(self, mapper):
        """Test converting GitHub state to Hopper status."""
        assert mapper.state_to_status("open") == "pending"
        assert mapper.state_to_status("closed") == "done"
        assert mapper.state_to_status("unknown") == "pending"

    def test_status_to_state(self, mapper):
        """Test converting Hopper status to GitHub state."""
        assert mapper.status_to_state("pending") == "open"
        assert mapper.status_to_state("claimed") == "open"
        assert mapper.status_to_state("in_progress") == "open"
        assert mapper.status_to_state("blocked") == "open"
        assert mapper.status_to_state("done") == "closed"
        assert mapper.status_to_state("cancelled") == "closed"
        assert mapper.status_to_state("unknown") == "open"

    def test_extract_priority_from_labels(self, mapper):
        """Test extracting priority from labels."""
        # Test through the private method
        assert mapper._extract_priority(["bug", "priority:urgent"]) == "urgent"
        assert mapper._extract_priority(["priority:high", "feature"]) == "high"
        assert mapper._extract_priority(["priority:low"]) == "low"
        # No priority label defaults to "medium"
        assert mapper._extract_priority(["bug", "feature"]) == "medium"
        assert mapper._extract_priority([]) == "medium"

    def test_parse_repo_valid(self, mapper):
        """Test parsing valid repo string."""
        owner, repo = mapper.parse_repo("owner/repo")
        assert owner == "owner"
        assert repo == "repo"

    def test_parse_repo_with_org(self, mapper):
        """Test parsing repo with organization."""
        owner, repo = mapper.parse_repo("my-org/my-repo")
        assert owner == "my-org"
        assert repo == "my-repo"

    def test_parse_repo_invalid(self, mapper):
        """Test parsing invalid repo string."""
        with pytest.raises(ValueError, match="Invalid repository format"):
            mapper.parse_repo("invalid")

        with pytest.raises(ValueError, match="Invalid repository format"):
            mapper.parse_repo("too/many/slashes")

    def test_should_sync_status(self, mapper):
        """Test checking if status should sync."""
        # Done task with open issue should sync
        assert mapper.should_sync_status("done", "open") is True

        # Pending task with closed issue should sync
        assert mapper.should_sync_status("pending", "closed") is True

        # Already in sync
        assert mapper.should_sync_status("done", "closed") is False
        assert mapper.should_sync_status("pending", "open") is False
        assert mapper.should_sync_status("in_progress", "open") is False
