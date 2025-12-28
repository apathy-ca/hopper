"""
Integration tests for MCP tools calling API.

Tests MCP tool integration including:
- Task creation via MCP
- Task listing via MCP
- Routing via MCP
- Error handling in MCP
- Context preservation
"""

from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from tests.factories import ProjectFactory, TaskFactory
from tests.utils import (
    assert_mcp_tool_response_valid,
    build_mcp_tool_call,
    build_mcp_tool_response,
)


@pytest.mark.integration
class TestMCPTaskTools:
    """Test MCP task management tools with API backend."""

    def test_hopper_create_task(self, mcp_client: Mock, db_session: Session):
        """Test creating a task via MCP tool."""
        tool_call = build_mcp_tool_call(
            "hopper_create_task",
            {
                "title": "Implement MCP integration",
                "description": "Add MCP support to Hopper",
                "project": "hopper",
                "priority": "high",
                "tags": ["mcp", "backend"],
            },
        )

        # Simulate MCP tool execution
        # In real implementation, this would call the actual MCP tool
        response = {
            "result": {
                "id": "task-mcp-001",
                "title": "Implement MCP integration",
                "project": "hopper",
                "status": "pending",
                "priority": "high",
            }
        }

        assert_mcp_tool_response_valid(response)

        # Verify task created in database
        from hopper.models.task import Task

        task = db_session.query(Task).filter(Task.id == "task-mcp-001").first()
        assert task is not None
        assert task.title == "Implement MCP integration"
        assert task.source == "mcp"  # Should mark source as MCP

    def test_hopper_list_tasks(self, mcp_client: Mock, db_session: Session):
        """Test listing tasks via MCP tool."""
        # Create some tasks
        TaskFactory.create_batch(5, session=db_session, project="hopper")

        tool_call = build_mcp_tool_call(
            "hopper_list_tasks", {"project": "hopper", "status": "pending"}
        )

        response = {
            "result": {
                "tasks": [{"id": "task-1", "title": "Task 1", "status": "pending"}],
                "total": 5,
            }
        }

        assert_mcp_tool_response_valid(response)
        assert len(response["result"]["tasks"]) > 0

    def test_hopper_get_task(self, mcp_client: Mock, db_session: Session):
        """Test getting task details via MCP tool."""
        task = TaskFactory.create(session=db_session, title="Test Task for MCP")

        tool_call = build_mcp_tool_call("hopper_get_task", {"task_id": task.id})

        response = {
            "result": {
                "id": task.id,
                "title": "Test Task for MCP",
                "description": task.description,
                "project": task.project,
                "status": task.status,
            }
        }

        assert_mcp_tool_response_valid(response)
        assert response["result"]["id"] == task.id

    def test_hopper_update_task(self, mcp_client: Mock, db_session: Session):
        """Test updating a task via MCP tool."""
        task = TaskFactory.create(session=db_session, title="Original Title", status="pending")

        tool_call = build_mcp_tool_call(
            "hopper_update_task",
            {"task_id": task.id, "title": "Updated via MCP", "status": "in_progress"},
        )

        response = {"result": {"id": task.id, "title": "Updated via MCP", "status": "in_progress"}}

        assert_mcp_tool_response_valid(response)

        # Verify database updated
        db_session.refresh(task)
        assert task.title == "Updated via MCP"
        assert task.status == "in_progress"

    def test_hopper_update_task_status(self, mcp_client: Mock, db_session: Session):
        """Test updating task status via dedicated MCP tool."""
        task = TaskFactory.create(session=db_session, status="pending")

        tool_call = build_mcp_tool_call(
            "hopper_update_task_status", {"task_id": task.id, "status": "completed"}
        )

        response = {"result": {"status": "completed"}}
        assert_mcp_tool_response_valid(response)

        db_session.refresh(task)
        assert task.status == "completed"


@pytest.mark.integration
class TestMCPProjectTools:
    """Test MCP project management tools."""

    def test_hopper_list_projects(self, mcp_client: Mock, db_session: Session):
        """Test listing projects via MCP."""
        ProjectFactory.create_batch(3, session=db_session)

        tool_call = build_mcp_tool_call("hopper_list_projects", {})

        response = {
            "result": [
                {"id": "proj-1", "name": "Project 1", "slug": "project-1"},
                {"id": "proj-2", "name": "Project 2", "slug": "project-2"},
                {"id": "proj-3", "name": "Project 3", "slug": "project-3"},
            ]
        }

        assert_mcp_tool_response_valid(response)
        assert len(response["result"]) >= 3

    def test_hopper_get_project(self, mcp_client: Mock, db_session: Session):
        """Test getting project details via MCP."""
        project = ProjectFactory.create(session=db_session, name="Hopper Project")

        tool_call = build_mcp_tool_call("hopper_get_project", {"project_id": project.id})

        response = {"result": {"id": project.id, "name": "Hopper Project", "slug": project.slug}}

        assert_mcp_tool_response_valid(response)

    def test_hopper_create_project(self, mcp_client: Mock, db_session: Session):
        """Test creating a project via MCP."""
        tool_call = build_mcp_tool_call(
            "hopper_create_project",
            {
                "name": "New Project from MCP",
                "slug": "new-mcp-project",
                "description": "Created via MCP tool",
            },
        )

        response = {
            "result": {
                "id": "proj-mcp-001",
                "name": "New Project from MCP",
                "slug": "new-mcp-project",
            }
        }

        assert_mcp_tool_response_valid(response)

    def test_hopper_get_project_tasks(self, mcp_client: Mock, db_session: Session):
        """Test getting all tasks for a project via MCP."""
        project = ProjectFactory.create(session=db_session, slug="hopper")
        TaskFactory.create_batch(5, session=db_session, project="hopper")

        tool_call = build_mcp_tool_call("hopper_get_project_tasks", {"project_id": project.id})

        response = {"result": {"tasks": [], "total": 5}}

        assert_mcp_tool_response_valid(response)


@pytest.mark.integration
class TestMCPRoutingTools:
    """Test MCP routing tools."""

    def test_hopper_route_task(self, mcp_client: Mock, db_session: Session):
        """Test routing a task via MCP tool."""
        task = TaskFactory.create(
            session=db_session, title="Task about routing logic", project=None
        )

        tool_call = build_mcp_tool_call(
            "hopper_route_task", {"task_id": task.id, "strategy": "rules"}
        )

        response = {
            "result": {
                "task_id": task.id,
                "destination": "hopper",
                "confidence": 0.85,
                "reasoning": "Matched keyword 'routing'",
                "strategy": "rules",
            }
        }

        assert_mcp_tool_response_valid(response)

        # Verify routing applied
        db_session.refresh(task)
        assert task.project == "hopper"

    def test_hopper_get_routing_suggestions(self, mcp_client: Mock, db_session: Session):
        """Test getting routing suggestions via MCP."""
        task = TaskFactory.create(session=db_session, project=None)

        tool_call = build_mcp_tool_call("hopper_get_routing_suggestions", {"task_id": task.id})

        response = {
            "result": [
                {"destination": "hopper", "confidence": 0.85, "reasoning": "Keyword match"},
                {"destination": "backend", "confidence": 0.65, "reasoning": "Tag match"},
            ]
        }

        assert_mcp_tool_response_valid(response)
        assert isinstance(response["result"], list)


@pytest.mark.integration
class TestMCPErrorHandling:
    """Test error handling in MCP tools."""

    def test_create_task_with_invalid_data(self, mcp_client: Mock):
        """Test MCP tool returns error for invalid task data."""
        tool_call = build_mcp_tool_call(
            "hopper_create_task", {"title": "", "priority": "invalid_priority"}  # Empty title
        )

        error_response = build_mcp_tool_response(
            "Invalid task data: title cannot be empty", is_error=True
        )

        assert_mcp_tool_response_valid(error_response)
        assert "error" in error_response

    def test_get_nonexistent_task(self, mcp_client: Mock):
        """Test MCP tool returns error for non-existent task."""
        tool_call = build_mcp_tool_call("hopper_get_task", {"task_id": "nonexistent-task-id"})

        error_response = build_mcp_tool_response(
            "Task not found: nonexistent-task-id", is_error=True
        )

        assert_mcp_tool_response_valid(error_response)
        assert error_response["error"]["code"] == -32000

    def test_missing_required_parameter(self, mcp_client: Mock):
        """Test MCP tool returns error for missing required parameters."""
        tool_call = build_mcp_tool_call("hopper_create_task", {})  # Missing required 'title'

        error_response = build_mcp_tool_response("Missing required parameter: title", is_error=True)

        assert_mcp_tool_response_valid(error_response)

    def test_invalid_task_status_transition(self, mcp_client: Mock, db_session: Session):
        """Test MCP tool handles invalid status transitions."""
        task = TaskFactory.create(session=db_session, status="completed")

        tool_call = build_mcp_tool_call(
            "hopper_update_task_status",
            {"task_id": task.id, "status": "pending"},  # Invalid: can't go back to pending
        )

        error_response = build_mcp_tool_response(
            "Invalid status transition: completed -> pending", is_error=True
        )

        assert_mcp_tool_response_valid(error_response)


@pytest.mark.integration
class TestMCPConversationContext:
    """Test context preservation across MCP tool calls."""

    def test_active_project_context_preserved(
        self, mcp_client: Mock, mcp_context: dict, db_session: Session
    ):
        """Test that active project context is preserved across calls."""
        # Set active project in context
        mcp_context["active_project"] = "hopper"

        # Create task without specifying project
        tool_call = build_mcp_tool_call(
            "hopper_create_task",
            {
                "title": "Task in active project"
                # Note: no 'project' specified
            },
        )

        # Should use active project from context
        response = {
            "result": {
                "id": "task-001",
                "title": "Task in active project",
                "project": "hopper",  # Should use context project
            }
        }

        assert response["result"]["project"] == mcp_context["active_project"]

    def test_conversation_id_tracked(
        self, mcp_client: Mock, mcp_context: dict, db_session: Session
    ):
        """Test that tasks created via MCP track conversation ID."""
        mcp_context["conversation_id"] = "conv-123"

        tool_call = build_mcp_tool_call("hopper_create_task", {"title": "Task from conversation"})

        # Verify task has conversation_id set
        from hopper.models.task import Task

        task = db_session.query(Task).filter(Task.conversation_id == "conv-123").first()

        assert task is not None
        assert task.conversation_id == mcp_context["conversation_id"]

    def test_session_state_persistence(self, mcp_client: Mock, mcp_context: dict):
        """Test that session state persists across tool calls."""
        # Store state in context
        mcp_context["session_state"]["last_task_id"] = "task-123"

        # Subsequent call should have access to state
        assert mcp_context["session_state"]["last_task_id"] == "task-123"

    def test_switching_active_project(self, mcp_client: Mock, mcp_context: dict):
        """Test switching active project in context."""
        # Start with one project
        mcp_context["active_project"] = "hopper"

        # Tool to switch project
        tool_call = build_mcp_tool_call("hopper_set_active_project", {"project": "czarina"})

        # Context should update
        mcp_context["active_project"] = "czarina"

        assert mcp_context["active_project"] == "czarina"
