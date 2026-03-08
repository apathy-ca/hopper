"""Base classes and protocols for platform integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass
class GitHubIssue:
    """Represents a GitHub issue."""

    number: int
    title: str
    body: str | None
    state: str  # "open" or "closed"
    labels: list[str]
    html_url: str
    created_at: datetime
    updated_at: datetime
    user: str | None = None
    assignee: str | None = None
    milestone: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> GitHubIssue:
        """Create GitHubIssue from GitHub API response."""
        return cls(
            number=data["number"],
            title=data["title"],
            body=data.get("body"),
            state=data["state"],
            labels=[label["name"] for label in data.get("labels", [])],
            html_url=data["html_url"],
            created_at=datetime.fromisoformat(data["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00")),
            user=data.get("user", {}).get("login"),
            assignee=data.get("assignee", {}).get("login") if data.get("assignee") else None,
            milestone=data.get("milestone", {}).get("title") if data.get("milestone") else None,
        )


class PlatformAdapter(Protocol):
    """Protocol for platform adapters."""

    def get_issue(self, owner: str, repo: str, number: int) -> GitHubIssue:
        """Get a single issue by number."""
        ...

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str | None = None,
        labels: list[str] | None = None,
    ) -> GitHubIssue:
        """Create a new issue."""
        ...

    def update_issue(
        self,
        owner: str,
        repo: str,
        number: int,
        **updates: Any,
    ) -> GitHubIssue:
        """Update an existing issue."""
        ...

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: list[str] | None = None,
    ) -> list[GitHubIssue]:
        """List issues for a repository."""
        ...

    def close_issue(self, owner: str, repo: str, number: int) -> GitHubIssue:
        """Close an issue."""
        ...


class PlatformError(Exception):
    """Base exception for platform errors."""

    def __init__(self, message: str, platform: str = "unknown"):
        self.message = message
        self.platform = platform
        super().__init__(f"[{platform}] {message}")


class PlatformAuthError(PlatformError):
    """Authentication error for platform."""

    pass


class PlatformNotFoundError(PlatformError):
    """Resource not found on platform."""

    pass


class PlatformRateLimitError(PlatformError):
    """Rate limit exceeded on platform."""

    pass
