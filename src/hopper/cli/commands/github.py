"""GitHub integration CLI commands."""

from __future__ import annotations

import click

from hopper.cli.main import Context
from hopper.cli.output import print_error, print_info, print_json, print_success, print_warning
from hopper.platforms import (
    GitHubClient,
    GitHubSyncService,
    PlatformAuthError,
    PlatformError,
    PlatformNotFoundError,
)
from hopper.platforms.github.mapper import GitHubMapper


@click.group(name="github")
def github() -> None:
    """GitHub integration commands."""
    pass


@github.command(name="auth")
@click.option("--token", "-t", required=True, help="GitHub personal access token")
@click.option("--default-owner", "-o", help="Default repository owner (org or user)")
@click.pass_obj
def auth_github(ctx: Context, token: str, default_owner: str | None) -> None:
    """Authenticate with GitHub and save token to config."""
    # Test the token first
    try:
        client = GitHubClient(token)
        user_data = client.test_connection()
        username = user_data.get("login", "unknown")
        client.close()
    except PlatformAuthError as e:
        print_error("Invalid GitHub token. Please check your token and try again.")
        raise click.Abort() from e
    except PlatformError as e:
        print_error(f"Failed to connect to GitHub: {e.message}")
        raise click.Abort() from e

    # Save to config
    config = ctx.config
    profile = config.current_profile
    profile.github.token = token
    if default_owner:
        profile.github.default_owner = default_owner
    config.save()

    print_success(f"Authenticated as {username}")
    if default_owner:
        print_info(f"Default owner set to: {default_owner}")


@github.command(name="list")
@click.argument("repo")
@click.option("--state", "-s", default="open", type=click.Choice(["open", "closed", "all"]))
@click.option("--limit", "-n", default=20, help="Maximum issues to show")
@click.pass_obj
def list_issues(ctx: Context, repo: str, state: str, limit: int) -> None:
    """List issues from a GitHub repository.

    REPO should be in 'owner/repo' format.
    """
    token = _get_token(ctx)
    mapper = GitHubMapper()

    try:
        owner, repo_name = mapper.parse_repo(repo)
    except ValueError as e:
        print_error(str(e))
        raise click.Abort() from e

    try:
        client = GitHubClient(token)
        issues = client.list_issues(owner, repo_name, state=state, per_page=limit)
        client.close()
    except PlatformNotFoundError as e:
        print_error(f"Repository not found: {repo}")
        raise click.Abort() from e
    except PlatformError as e:
        print_error(f"GitHub error: {e.message}")
        raise click.Abort() from e

    if ctx.json_output:
        print_json(
            [
                {
                    "number": issue.number,
                    "title": issue.title,
                    "state": issue.state,
                    "labels": issue.labels,
                    "url": issue.html_url,
                }
                for issue in issues
            ]
        )
    else:
        if not issues:
            print_info(f"No {state} issues found in {repo}")
            return

        print_info(f"Issues in {repo} ({state}):\n")
        for issue in issues:
            labels = ", ".join(issue.labels) if issue.labels else ""
            label_str = f" [{labels}]" if labels else ""
            state_marker = "[green]●[/green]" if issue.state == "open" else "[red]●[/red]"
            click.echo(f"  {state_marker} #{issue.number}: {issue.title}{label_str}")


@github.command(name="import")
@click.argument("repo")
@click.option("--issue", "-i", type=int, help="Import a specific issue number")
@click.option("--all", "import_all", is_flag=True, help="Import all open issues")
@click.option("--state", "-s", default="open", type=click.Choice(["open", "closed", "all"]))
@click.option("--project", "-p", help="Hopper project ID to assign tasks to")
@click.option("--max", "max_issues", default=100, help="Maximum issues to import")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True, help="DID of the author")
@click.option("--author-location", envvar="HOPPER_LOCATION", hidden=True, help="Location context")
@click.pass_obj
def import_issues(
    ctx: Context,
    repo: str,
    issue: int | None,
    import_all: bool,
    state: str,
    project: str | None,
    max_issues: int,
    author_did: str | None,
    author_location: str | None,
) -> None:
    """Import GitHub issues as Hopper tasks.

    REPO should be in 'owner/repo' format.

    Examples:

        hopper github import owner/repo --issue 123

        hopper github import owner/repo --all
    """
    if not issue and not import_all:
        print_error("Specify --issue <number> or --all")
        raise click.Abort()

    token = _get_token(ctx)
    mapper = GitHubMapper()

    try:
        owner, repo_name = mapper.parse_repo(repo)
    except ValueError as e:
        print_error(str(e))
        raise click.Abort() from e

    # Get task store
    if not ctx.is_local:
        print_error("GitHub import currently only works in local mode (--local)")
        raise click.Abort()

    from hopper.cli.config import get_storage_path
    from hopper.cli.local_client import LocalClient

    storage_path = get_storage_path(ctx.config, force_local=True)
    local_client = LocalClient(storage_path)
    task_store = local_client.task_store
    author = local_client._author_context(author_did=author_did, author_location=author_location)

    # Create sync service
    client = GitHubClient(token)
    sync = GitHubSyncService(client, task_store, author=author)

    try:
        if issue:
            # Import single issue
            task_id = sync.import_issue(owner, repo_name, issue, project_id=project)
            if task_id:
                if ctx.json_output:
                    print_json({"task_id": task_id, "issue": issue, "status": "imported"})
                else:
                    print_success(f"Imported issue #{issue} as task {task_id}")
            else:
                if ctx.json_output:
                    print_json({"issue": issue, "status": "skipped", "reason": "already_imported"})
                else:
                    print_warning(f"Issue #{issue} already imported, skipping")
        else:
            # Import all issues
            result = sync.import_all_issues(
                owner,
                repo_name,
                state=state,
                project_id=project,
                max_issues=max_issues,
            )

            if ctx.json_output:
                print_json(
                    {
                        "imported": result.imported,
                        "skipped": result.skipped,
                        "errors": result.errors,
                        "total_imported": result.total_imported,
                        "total_skipped": result.total_skipped,
                        "total_errors": result.total_errors,
                    }
                )
            else:
                print_success(f"Imported {result.total_imported} issues from {repo}")
                if result.total_skipped:
                    print_info(f"Skipped {result.total_skipped} already imported")
                if result.total_errors:
                    print_warning(f"{result.total_errors} errors:")
                    for err in result.errors:
                        print_error(f"  {err}")
    except PlatformNotFoundError as e:
        print_error(f"Issue or repository not found: {repo}")
        raise click.Abort() from e
    except PlatformError as e:
        print_error(f"GitHub error: {e.message}")
        raise click.Abort() from e
    finally:
        client.close()


@github.command(name="export")
@click.argument("task_id")
@click.option("--repo", "-r", required=True, help="Target repository (owner/repo)")
@click.option("--author-did", envvar="HOPPER_DID", hidden=True, help="DID of the author")
@click.option("--author-location", envvar="HOPPER_LOCATION", hidden=True, help="Location context")
@click.pass_obj
def export_task(
    ctx: Context, task_id: str, repo: str, author_did: str | None, author_location: str | None
) -> None:
    """Export a Hopper task as a GitHub issue.

    TASK_ID is the Hopper task ID to export.
    """
    token = _get_token(ctx)
    mapper = GitHubMapper()

    try:
        owner, repo_name = mapper.parse_repo(repo)
    except ValueError as e:
        print_error(str(e))
        raise click.Abort() from e

    # Get task store
    if not ctx.is_local:
        print_error("GitHub export currently only works in local mode (--local)")
        raise click.Abort()

    from hopper.cli.config import get_storage_path
    from hopper.cli.local_client import LocalClient

    storage_path = get_storage_path(ctx.config, force_local=True)
    local_client = LocalClient(storage_path)
    task_store = local_client.task_store
    author = local_client._author_context(author_did=author_did, author_location=author_location)

    # Create sync service
    client = GitHubClient(token)
    sync = GitHubSyncService(client, task_store, author=author)

    try:
        result = sync.export_task(task_id, owner, repo_name)

        if ctx.json_output:
            print_json(
                {
                    "success": result.success,
                    "issue_number": result.issue_number,
                    "issue_url": result.issue_url,
                    "error": result.error,
                }
            )
        else:
            if result.success:
                print_success(f"Created issue #{result.issue_number}")
                print_info(f"URL: {result.issue_url}")
            else:
                print_error(f"Export failed: {result.error}")
                raise click.Abort()
    except PlatformError as e:
        print_error(f"GitHub error: {e.message}")
        raise click.Abort() from e
    finally:
        client.close()


@github.command(name="status")
@click.pass_obj
def github_status(ctx: Context) -> None:
    """Show GitHub authentication status."""
    profile = ctx.config.current_profile

    if not profile.github.token:
        print_warning("Not authenticated with GitHub")
        print_info("Run: hopper github auth --token <your-token>")
        return

    try:
        client = GitHubClient(profile.github.token)
        user_data = client.test_connection()
        client.close()

        if ctx.json_output:
            print_json(
                {
                    "authenticated": True,
                    "username": user_data.get("login"),
                    "default_owner": profile.github.default_owner,
                }
            )
        else:
            print_success(f"Authenticated as: {user_data.get('login')}")
            if profile.github.default_owner:
                print_info(f"Default owner: {profile.github.default_owner}")
    except PlatformAuthError:
        if ctx.json_output:
            print_json({"authenticated": False, "error": "invalid_token"})
        else:
            print_error("Token is invalid or expired")
            print_info("Run: hopper github auth --token <new-token>")
    except PlatformError as e:
        if ctx.json_output:
            print_json({"authenticated": False, "error": str(e)})
        else:
            print_error(f"Connection error: {e.message}")


def _get_token(ctx: Context) -> str:
    """Get GitHub token from config or environment."""
    import os

    # Try config first
    token = ctx.config.current_profile.github.token

    # Fall back to environment
    if not token:
        token = os.environ.get("GITHUB_TOKEN")

    if not token:
        print_error("GitHub token not configured")
        print_info("Run: hopper github auth --token <your-token>")
        print_info("Or set GITHUB_TOKEN environment variable")
        raise click.Abort()

    return token
