"""GitHub API client."""

from __future__ import annotations

from typing import Any

import httpx

from ..base import (
    GitHubIssue,
    PlatformAuthError,
    PlatformError,
    PlatformNotFoundError,
    PlatformRateLimitError,
)


class GitHubClient:
    """Client for GitHub API interactions."""

    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        """Initialize GitHub client.

        Args:
            token: GitHub personal access token or fine-grained token
            base_url: Base URL for GitHub API (for GitHub Enterprise)
        """
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    def __enter__(self) -> GitHubClient:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def _handle_response(self, response: httpx.Response) -> dict[str, Any]:
        """Handle API response and raise appropriate errors."""
        if response.status_code == 401:
            raise PlatformAuthError("Invalid or expired token", platform="github")
        if response.status_code == 403:
            if "rate limit" in response.text.lower():
                raise PlatformRateLimitError("Rate limit exceeded", platform="github")
            raise PlatformAuthError("Access forbidden", platform="github")
        if response.status_code == 404:
            raise PlatformNotFoundError("Resource not found", platform="github")
        if response.status_code >= 400:
            raise PlatformError(
                f"API error: {response.status_code} - {response.text}",
                platform="github",
            )
        return response.json()

    def get_issue(self, owner: str, repo: str, number: int) -> GitHubIssue:
        """Get a single issue by number.

        Args:
            owner: Repository owner (user or org)
            repo: Repository name
            number: Issue number

        Returns:
            GitHubIssue object
        """
        response = self.client.get(f"/repos/{owner}/{repo}/issues/{number}")
        data = self._handle_response(response)
        return GitHubIssue.from_api_response(data)

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssue:
        """Create a new issue.

        Args:
            owner: Repository owner
            repo: Repository name
            title: Issue title
            body: Issue body (optional)
            labels: List of label names (optional)

        Returns:
            Created GitHubIssue object
        """
        payload: dict[str, Any] = {"title": title}
        if body:
            payload["body"] = body
        if labels:
            payload["labels"] = labels

        response = self.client.post(f"/repos/{owner}/{repo}/issues", json=payload)
        data = self._handle_response(response)
        return GitHubIssue.from_api_response(data)

    def update_issue(
        self,
        owner: str,
        repo: str,
        number: int,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssue:
        """Update an existing issue.

        Args:
            owner: Repository owner
            repo: Repository name
            number: Issue number
            title: New title (optional)
            body: New body (optional)
            state: New state - "open" or "closed" (optional)
            labels: New labels (optional, replaces existing)

        Returns:
            Updated GitHubIssue object
        """
        payload: dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if body is not None:
            payload["body"] = body
        if state is not None:
            payload["state"] = state
        if labels is not None:
            payload["labels"] = labels

        response = self.client.patch(f"/repos/{owner}/{repo}/issues/{number}", json=payload)
        data = self._handle_response(response)
        return GitHubIssue.from_api_response(data)

    def close_issue(self, owner: str, repo: str, number: int) -> GitHubIssue:
        """Close an issue.

        Args:
            owner: Repository owner
            repo: Repository name
            number: Issue number

        Returns:
            Updated GitHubIssue object
        """
        return self.update_issue(owner, repo, number, state="closed")

    def reopen_issue(self, owner: str, repo: str, number: int) -> GitHubIssue:
        """Reopen a closed issue.

        Args:
            owner: Repository owner
            repo: Repository name
            number: Issue number

        Returns:
            Updated GitHubIssue object
        """
        return self.update_issue(owner, repo, number, state="open")

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: list[str] | None = None,
        per_page: int = 30,
        page: int = 1,
    ) -> list[GitHubIssue]:
        """List issues for a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: Filter by state - "open", "closed", or "all"
            labels: Filter by labels (comma-separated in API)
            per_page: Number of results per page (max 100)
            page: Page number

        Returns:
            List of GitHubIssue objects
        """
        params: dict[str, Any] = {
            "state": state,
            "per_page": min(per_page, 100),
            "page": page,
        }
        if labels:
            params["labels"] = ",".join(labels)

        response = self.client.get(f"/repos/{owner}/{repo}/issues", params=params)
        data = self._handle_response(response)

        # Filter out pull requests (GitHub API returns PRs in issues endpoint)
        issues = [item for item in data if "pull_request" not in item]
        return [GitHubIssue.from_api_response(item) for item in issues]

    def list_all_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: list[str] | None = None,
        max_issues: int = 1000,
    ) -> list[GitHubIssue]:
        """List all issues with pagination.

        Args:
            owner: Repository owner
            repo: Repository name
            state: Filter by state
            labels: Filter by labels
            max_issues: Maximum number of issues to fetch

        Returns:
            List of all GitHubIssue objects
        """
        all_issues: list[GitHubIssue] = []
        page = 1
        per_page = 100

        while len(all_issues) < max_issues:
            issues = self.list_issues(
                owner, repo, state=state, labels=labels, per_page=per_page, page=page
            )
            if not issues:
                break
            all_issues.extend(issues)
            if len(issues) < per_page:
                break
            page += 1

        return all_issues[:max_issues]

    def add_labels(self, owner: str, repo: str, number: int, labels: list[str]) -> list[str]:
        """Add labels to an issue.

        Args:
            owner: Repository owner
            repo: Repository name
            number: Issue number
            labels: Labels to add

        Returns:
            List of all labels on the issue
        """
        response = self.client.post(
            f"/repos/{owner}/{repo}/issues/{number}/labels",
            json={"labels": labels},
        )
        data = self._handle_response(response)
        return [label["name"] for label in data]

    def remove_label(self, owner: str, repo: str, number: int, label: str) -> None:
        """Remove a label from an issue.

        Args:
            owner: Repository owner
            repo: Repository name
            number: Issue number
            label: Label to remove
        """
        response = self.client.delete(f"/repos/{owner}/{repo}/issues/{number}/labels/{label}")
        if response.status_code != 200 and response.status_code != 404:
            self._handle_response(response)

    def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """Get repository information.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Repository data
        """
        response = self.client.get(f"/repos/{owner}/{repo}")
        return self._handle_response(response)

    def test_connection(self) -> dict[str, Any]:
        """Test the API connection and token validity.

        Returns:
            User data if successful
        """
        response = self.client.get("/user")
        return self._handle_response(response)
