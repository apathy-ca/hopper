"""Mapper for converting between GitHub issues and Hopper tasks."""

from __future__ import annotations

from typing import Any

from ..base import GitHubIssue


# Priority label prefixes that map to Hopper priorities
PRIORITY_LABELS = {
    "priority:urgent": "urgent",
    "priority:high": "high",
    "priority:medium": "medium",
    "priority:low": "low",
    # Alternative formats
    "urgent": "urgent",
    "high-priority": "high",
    "low-priority": "low",
    "P0": "urgent",
    "P1": "high",
    "P2": "medium",
    "P3": "low",
}

# Hopper status to GitHub state mapping
STATUS_TO_STATE = {
    "pending": "open",
    "claimed": "open",
    "in_progress": "open",
    "blocked": "open",
    "open": "open",
    "done": "closed",
    "completed": "closed",
    "cancelled": "closed",
}

# GitHub state to Hopper status mapping
STATE_TO_STATUS = {
    "open": "pending",
    "closed": "done",
}


class GitHubMapper:
    """Maps between GitHub issues and Hopper tasks."""

    def issue_to_task_data(
        self,
        issue: GitHubIssue,
        owner: str,
        repo: str,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Convert a GitHub issue to task creation data.

        Args:
            issue: GitHub issue object
            owner: Repository owner
            repo: Repository name
            project_id: Optional Hopper project ID

        Returns:
            Dictionary suitable for creating a task
        """
        # Extract priority from labels
        priority = self._extract_priority(issue.labels)

        # Convert labels to tags, excluding priority labels
        tags = self.labels_to_tags(issue.labels)

        # Build task data
        task_data: dict[str, Any] = {
            "title": issue.title,
            "description": issue.body or "",
            "status": self.state_to_status(issue.state),
            "priority": priority,
            "tags": tags,
            "source": "github",
            "external_id": str(issue.number),
            "external_url": issue.html_url,
            "external_platform": "github",
            "context": f"Imported from {owner}/{repo}#{issue.number}",
        }

        if project_id:
            task_data["project_id"] = project_id

        if issue.user:
            task_data["requester"] = issue.user

        if issue.assignee:
            task_data["owner"] = issue.assignee

        return task_data

    def task_to_issue_data(self, task: dict[str, Any]) -> dict[str, Any]:
        """Convert a Hopper task to GitHub issue creation data.

        Args:
            task: Task dictionary (from task.to_dict() or similar)

        Returns:
            Dictionary suitable for GitHub API issue creation
        """
        # Build labels from tags and priority
        labels = self.tags_to_labels(task.get("tags", []))

        # Add priority label if not medium
        priority = task.get("priority", "medium")
        if priority and priority != "medium":
            labels.append(f"priority:{priority}")

        # Build issue data
        issue_data: dict[str, Any] = {
            "title": task["title"],
        }

        if task.get("description"):
            # Add Hopper reference to body
            body = task["description"]
            body += f"\n\n---\n*Exported from Hopper task `{task.get('id', 'unknown')}`*"
            issue_data["body"] = body

        if labels:
            issue_data["labels"] = labels

        return issue_data

    def labels_to_tags(self, labels: list[str]) -> list[str]:
        """Convert GitHub labels to Hopper tags.

        Filters out priority-related labels.

        Args:
            labels: List of GitHub label names

        Returns:
            List of Hopper tags
        """
        tags = []
        for label in labels:
            # Skip priority labels
            label_lower = label.lower()
            if any(p in label_lower for p in ["priority", "p0", "p1", "p2", "p3"]):
                continue
            # Normalize label to tag (lowercase, replace spaces)
            tag = label.lower().replace(" ", "-")
            tags.append(tag)
        return tags

    def tags_to_labels(self, tags: list[str]) -> list[str]:
        """Convert Hopper tags to GitHub labels.

        Args:
            tags: List of Hopper tags

        Returns:
            List of GitHub label names
        """
        # For now, just return tags as-is
        # Could add mapping logic for common tags
        return list(tags)

    def state_to_status(self, state: str) -> str:
        """Convert GitHub issue state to Hopper task status.

        Args:
            state: GitHub state ("open" or "closed")

        Returns:
            Hopper status string
        """
        return STATE_TO_STATUS.get(state.lower(), "pending")

    def status_to_state(self, status: str) -> str:
        """Convert Hopper task status to GitHub issue state.

        Args:
            status: Hopper status

        Returns:
            GitHub state ("open" or "closed")
        """
        return STATUS_TO_STATE.get(status.lower(), "open")

    def _extract_priority(self, labels: list[str]) -> str:
        """Extract priority from GitHub labels.

        Args:
            labels: List of GitHub label names

        Returns:
            Hopper priority string (defaults to "medium")
        """
        for label in labels:
            label_lower = label.lower()
            if label_lower in PRIORITY_LABELS:
                return PRIORITY_LABELS[label_lower]
        return "medium"

    def should_sync_status(self, task_status: str, issue_state: str) -> bool:
        """Check if task status and issue state are out of sync.

        Args:
            task_status: Current Hopper task status
            issue_state: Current GitHub issue state

        Returns:
            True if sync is needed
        """
        expected_state = self.status_to_state(task_status)
        return expected_state != issue_state.lower()

    def format_repo(self, owner: str, repo: str) -> str:
        """Format owner/repo string.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Formatted "owner/repo" string
        """
        return f"{owner}/{repo}"

    def parse_repo(self, repo_string: str) -> tuple[str, str]:
        """Parse owner/repo string.

        Args:
            repo_string: String in "owner/repo" format

        Returns:
            Tuple of (owner, repo)

        Raises:
            ValueError: If format is invalid
        """
        parts = repo_string.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid repository format: {repo_string}. Expected 'owner/repo'")
        return parts[0], parts[1]
