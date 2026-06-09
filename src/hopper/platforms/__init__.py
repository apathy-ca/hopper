"""Platform integration module for external issue trackers."""

from .base import (
    GitHubIssue,
    PlatformAdapter,
    PlatformAuthError,
    PlatformError,
    PlatformNotFoundError,
    PlatformRateLimitError,
)
from .github import GitHubClient, GitHubMapper
from .sync import ExportResult, GitHubSyncService, ImportResult

__all__ = [
    "GitHubIssue",
    "PlatformAdapter",
    "PlatformError",
    "PlatformAuthError",
    "PlatformNotFoundError",
    "PlatformRateLimitError",
    "GitHubClient",
    "GitHubMapper",
    "GitHubSyncService",
    "ImportResult",
    "ExportResult",
]
