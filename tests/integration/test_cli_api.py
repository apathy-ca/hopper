"""
Integration tests for CLI commands calling API.

Tests CLI integration including:
- Task commands end-to-end
- Project commands end-to-end
- Instance commands end-to-end
- Configuration commands
- Authentication flow
"""
import pytest
from click.testing import CliRunner
from sqlalchemy.orm import Session

from tests.factories import TaskFactory, ProjectFactory
from tests.utils import assert_cli_success, assert_cli_error


@pytest.mark.integration
class TestCLITaskCommands:
    """Test CLI task commands with API backend."""

    def test_task_add_command(self, cli_runner: CliRunner, db_session: Session):
        """Test 'hopper task add' command."""
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, [
            'task', 'add',
            '--title', 'Test Task from CLI',
            '--project', 'hopper',
            '--priority', 'high'
        ])

        assert_cli_success(result, "Task created successfully")

        # Verify task in database
        from hopper.models.task import Task
        task = db_session.query(Task).filter(
            Task.title == "Test Task from CLI"
        ).first()
        assert task is not None
        assert task.source == "cli"

    def test_task_list_command(self, cli_runner: CliRunner, db_session: Session):
        """Test 'hopper task list' command."""
        # Create tasks
        TaskFactory.create_batch(5, session=db_session, project="hopper")

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, ['task', 'list'])

        assert_cli_success(result)
        assert "Test Task" in result.output

    def test_task_get_command(self, cli_runner: CliRunner, db_session: Session):
        """Test 'hopper task get' command."""
        task = TaskFactory.create(session=db_session, title="CLI Test Task")

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, ['task', 'get', task.id])

        assert_cli_success(result)
        assert "CLI Test Task" in result.output

    def test_task_update_command(self, cli_runner: CliRunner, db_session: Session):
        """Test 'hopper task update' command."""
        task = TaskFactory.create(session=db_session, title="Original")

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, [
            'task', 'update', task.id,
            '--title', 'Updated from CLI'
        ])

        assert_cli_success(result)

        db_session.refresh(task)
        assert task.title == "Updated from CLI"

    def test_task_delete_command(self, cli_runner: CliRunner, db_session: Session):
        """Test 'hopper task delete' command."""
        task = TaskFactory.create(session=db_session)

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, [
            'task', 'delete', task.id, '--confirm'
        ])

        assert_cli_success(result)


@pytest.mark.integration
class TestCLIProjectCommands:
    """Test CLI project commands."""

    def test_project_create_command(self, cli_runner: CliRunner):
        """Test 'hopper project create' command."""
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, [
            'project', 'create',
            '--name', 'CLI Test Project',
            '--slug', 'cli-test'
        ])

        assert_cli_success(result)

    def test_project_list_command(self, cli_runner: CliRunner, db_session: Session):
        """Test 'hopper project list' command."""
        ProjectFactory.create_batch(3, session=db_session)

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, ['project', 'list'])

        assert_cli_success(result)


@pytest.mark.integration
class TestCLIOutputFormatting:
    """Test CLI output formatting."""

    def test_table_output(self, cli_runner: CliRunner, db_session: Session):
        """Test CLI table output format."""
        TaskFactory.create_batch(3, session=db_session)

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, ['task', 'list', '--format', 'table'])

        assert_cli_success(result)
        assert "|" in result.output  # Table format uses pipes

    def test_json_output(self, cli_runner: CliRunner, db_session: Session):
        """Test CLI JSON output format."""
        TaskFactory.create_batch(3, session=db_session)

        from hopper.cli.main import cli
        result = cli_runner.invoke(cli, ['task', 'list', '--format', 'json'])

        assert_cli_success(result)

        import json
        data = json.loads(result.output)
        assert isinstance(data, list)


@pytest.mark.integration
class TestCLIAuthFlow:
    """Test CLI authentication flow."""

    def test_cli_login(self, cli_runner: CliRunner):
        """Test CLI login command."""
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, [
            'login',
            '--username', 'testuser',
            '--password', 'testpassword'
        ])

        assert_cli_success(result, "Logged in successfully")

    def test_cli_logout(self, cli_runner: CliRunner):
        """Test CLI logout command."""
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, ['logout'])
        assert_cli_success(result)
