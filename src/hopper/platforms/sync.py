"""Sync service for platform integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .base import GitHubIssue
from .github.client import GitHubClient
from .github.mapper import GitHubMapper

if TYPE_CHECKING:
    from hopper.storage.tasks import TaskMarkdownStore


@dataclass
class ImportResult:
    """Result of an import operation."""

    imported: list[str] = field(default_factory=list)  # Task IDs
    skipped: list[str] = field(default_factory=list)  # Issue numbers (already imported)
    errors: list[str] = field(default_factory=list)  # Error messages

    @property
    def total_imported(self) -> int:
        """Number of tasks imported."""
        return len(self.imported)

    @property
    def total_skipped(self) -> int:
        """Number of issues skipped."""
        return len(self.skipped)

    @property
    def total_errors(self) -> int:
        """Number of errors."""
        return len(self.errors)


@dataclass
class ExportResult:
    """Result of an export operation."""

    issue_number: int
    issue_url: str
    success: bool
    error: str | None = None


class GitHubSyncService:
    """Service for syncing between GitHub and Hopper."""

    def __init__(self, client: GitHubClient, task_store: "TaskMarkdownStore"):
        """Initialize sync service.

        Args:
            client: GitHub API client
            task_store: Hopper task store
        """
        self.client = client
        self.task_store = task_store
        self.mapper = GitHubMapper()

    def import_issue(
        self,
        owner: str,
        repo: str,
        number: int,
        project_id: str | None = None,
        skip_existing: bool = True,
    ) -> str | None:
        """Import a single GitHub issue as a Hopper task.

        Args:
            owner: Repository owner
            repo: Repository name
            number: Issue number
            project_id: Optional Hopper project ID
            skip_existing: Skip if already imported

        Returns:
            Task ID if imported, None if skipped
        """
        # Check if already imported
        if skip_existing:
            existing = self._find_task_by_external_id(str(number), owner, repo)
            if existing:
                return None

        # Fetch issue from GitHub
        issue = self.client.get_issue(owner, repo, number)

        # Convert to task data
        task_data = self.mapper.issue_to_task_data(issue, owner, repo, project_id)

        # Create task
        from hopper.storage.tasks import LocalTask

        task = LocalTask.create(**task_data)
        self.task_store.create(task)

        return task.id

    def import_all_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        project_id: str | None = None,
        skip_existing: bool = True,
        max_issues: int = 100,
    ) -> ImportResult:
        """Import all issues from a repository.

        Args:
            owner: Repository owner
            repo: Repository name
            state: Issue state filter ("open", "closed", "all")
            project_id: Optional Hopper project ID
            skip_existing: Skip already imported issues
            max_issues: Maximum issues to import

        Returns:
            ImportResult with details
        """
        result = ImportResult()

        # Fetch issues from GitHub
        issues = self.client.list_all_issues(owner, repo, state=state, max_issues=max_issues)

        for issue in issues:
            try:
                task_id = self.import_issue(
                    owner,
                    repo,
                    issue.number,
                    project_id=project_id,
                    skip_existing=skip_existing,
                )
                if task_id:
                    result.imported.append(task_id)
                else:
                    result.skipped.append(str(issue.number))
            except Exception as e:
                result.errors.append(f"Issue #{issue.number}: {e}")

        return result

    def export_task(
        self,
        task_id: str,
        owner: str,
        repo: str,
        update_task: bool = True,
    ) -> ExportResult:
        """Export a Hopper task as a GitHub issue.

        Args:
            task_id: Hopper task ID
            owner: Repository owner
            repo: Repository name
            update_task: Update task with external_id after export

        Returns:
            ExportResult with issue details
        """
        # Get task
        task = self.task_store.get(task_id)
        if not task:
            return ExportResult(
                issue_number=0,
                issue_url="",
                success=False,
                error=f"Task not found: {task_id}",
            )

        # Check if already exported
        if task.external_id and task.external_platform == "github":
            return ExportResult(
                issue_number=int(task.external_id),
                issue_url=task.external_url or "",
                success=False,
                error=f"Task already exported as issue #{task.external_id}",
            )

        # Convert to issue data
        task_dict = self._task_to_dict(task)
        issue_data = self.mapper.task_to_issue_data(task_dict)

        # Create issue on GitHub
        try:
            issue = self.client.create_issue(
                owner,
                repo,
                title=issue_data["title"],
                body=issue_data.get("body"),
                labels=issue_data.get("labels"),
            )
        except Exception as e:
            return ExportResult(
                issue_number=0,
                issue_url="",
                success=False,
                error=str(e),
            )

        # Update task with external reference
        if update_task:
            task.external_id = str(issue.number)
            task.external_url = issue.html_url
            task.external_platform = "github"
            self.task_store.save(task)

        return ExportResult(
            issue_number=issue.number,
            issue_url=issue.html_url,
            success=True,
        )

    def sync_status_to_github(
        self,
        task_id: str,
        owner: str,
        repo: str,
    ) -> bool:
        """Sync task status to GitHub issue.

        Args:
            task_id: Hopper task ID
            owner: Repository owner
            repo: Repository name

        Returns:
            True if sync was performed
        """
        task = self.task_store.get(task_id)
        if not task or not task.external_id:
            return False

        issue_number = int(task.external_id)
        issue = self.client.get_issue(owner, repo, issue_number)

        if self.mapper.should_sync_status(task.status, issue.state):
            new_state = self.mapper.status_to_state(task.status)
            self.client.update_issue(owner, repo, issue_number, state=new_state)
            return True

        return False

    def _find_task_by_external_id(
        self,
        external_id: str,
        owner: str,
        repo: str,
    ) -> Any | None:
        """Find a task by external ID.

        Args:
            external_id: External ID (issue number)
            owner: Repository owner
            repo: Repository name

        Returns:
            Task if found, None otherwise
        """
        # Search through tasks
        tasks = self.task_store.list(limit=1000)
        for task in tasks:
            if (
                task.external_id == external_id
                and task.external_platform == "github"
                and f"{owner}/{repo}" in (task.context or "")
            ):
                return task
        return None

    def _task_to_dict(self, task: Any) -> dict[str, Any]:
        """Convert task to dictionary.

        Args:
            task: LocalTask object

        Returns:
            Dictionary representation
        """
        return {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "status": task.status,
            "priority": task.priority,
            "tags": task.tags or [],
            "external_id": task.external_id,
            "external_url": task.external_url,
            "external_platform": task.external_platform,
        }

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
    ) -> list[GitHubIssue]:
        """List issues from GitHub (preview before import).

        Args:
            owner: Repository owner
            repo: Repository name
            state: Issue state filter

        Returns:
            List of GitHub issues
        """
        return self.client.list_issues(owner, repo, state=state)
