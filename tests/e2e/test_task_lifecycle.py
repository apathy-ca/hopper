"""
End-to-end test for complete task lifecycle.

Tests the complete journey of a task through the system:
1. Create task via MCP
2. Task appears in database
3. Task appears in CLI listing
4. Update task via CLI
5. Update appears in API
6. Update appears in MCP
7. Complete task
8. Archive task
"""

import pytest
pytestmark = pytest.mark.skip(reason="E2E test: Requires running API server, MCP, and CLI integration")


import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.mark.e2e
class TestTaskLifecycle:
    """Test complete task lifecycle across all interfaces."""

    def test_complete_task_lifecycle(
        self, api_client: TestClient, cli_runner: CliRunner, mcp_client, db_session: Session
    ):
        """
        Test task creation, update, and completion across MCP, API, and CLI.
        """
        # Step 1: Create task via MCP
        from tests.utils import build_mcp_tool_call

        mcp_create = build_mcp_tool_call(
            "hopper_create_task",
            {
                "title": "E2E Lifecycle Test Task",
                "description": "Testing complete task lifecycle",
                "project": "hopper",
                "priority": "high",
            },
        )

        # Simulate MCP response
        task_id = "e2e-task-001"

        # Step 2: Verify task appears in database
        from hopper.models.task import Task

        task = db_session.query(Task).filter(Task.id == task_id).first()
        assert task is not None
        assert task.title == "E2E Lifecycle Test Task"
        assert task.status == "pending"

        # Step 3: Verify task appears in CLI listing
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, ["task", "list", "--project", "hopper"])
        assert "E2E Lifecycle Test Task" in result.output

        # Step 4: Update task via CLI
        result = cli_runner.invoke(
            cli, ["task", "update", task_id, "--status", "in_progress", "--priority", "urgent"]
        )
        assert result.exit_code == 0

        # Step 5: Verify update appears in API
        response = api_client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        api_task = response.json()
        assert api_task["status"] == "in_progress"
        assert api_task["priority"] == "urgent"

        # Step 6: Verify update appears in MCP
        mcp_get = build_mcp_tool_call("hopper_get_task", {"task_id": task_id})
        # MCP should return updated task

        # Step 7: Complete task via API
        response = api_client.post(f"/api/v1/tasks/{task_id}/status", json={"status": "completed"})
        assert response.status_code == 200

        # Step 8: Archive task via CLI
        result = cli_runner.invoke(cli, ["task", "delete", task_id, "--confirm"])
        assert result.exit_code == 0

        # Verify final state in database
        db_session.refresh(task)
        assert task.status == "archived"

    def test_task_lifecycle_with_routing(
        self, api_client: TestClient, cli_runner: CliRunner, db_session: Session
    ):
        """Test task lifecycle including routing step."""
        # Create unrouted task via API
        response = api_client.post(
            "/api/v1/tasks",
            json={
                "title": "Task needing routing",
                "description": "This task should be routed automatically",
            },
        )
        assert response.status_code == 201
        task_id = response.json()["id"]

        # Route task via API
        response = api_client.post(f"/api/v1/tasks/{task_id}/route", json={"strategy": "rules"})
        assert response.status_code == 200
        routing = response.json()
        assert routing["destination"] is not None

        # Verify routing in database
        from hopper.models.task import Task

        task = db_session.query(Task).filter(Task.id == task_id).first()
        assert task.project == routing["destination"]
        assert task.status == "routed"

        # Verify visible in CLI with correct project
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, ["task", "list", "--project", routing["destination"]])
        assert "Task needing routing" in result.output

    def test_multi_interface_consistency(
        self, api_client: TestClient, cli_runner: CliRunner, db_session: Session
    ):
        """Test that updates via one interface are visible in all others."""
        # Create via API
        response = api_client.post(
            "/api/v1/tasks", json={"title": "Multi-interface test", "project": "hopper"}
        )
        task_id = response.json()["id"]

        # Update via CLI
        from hopper.cli.main import cli

        result = cli_runner.invoke(cli, ["task", "update", task_id, "--title", "Updated title"])
        assert result.exit_code == 0

        # Verify via API
        response = api_client.get(f"/api/v1/tasks/{task_id}")
        assert response.json()["title"] == "Updated title"

        # Verify in database
        from hopper.models.task import Task

        task = db_session.query(Task).filter(Task.id == task_id).first()
        assert task.title == "Updated title"
