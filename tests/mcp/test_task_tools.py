"""
Tests for MCP task management tools.

Tests the task creation, listing, updating, and status management tools.
"""

import pytest

from hopper.mcp.tools.task_tools import (
    create_task,
    get_task,
    get_task_tools,
    list_tasks,
    update_task,
    update_task_status,
)


class TestTaskToolDefinitions:
    """Test task tool definitions."""

    def test_get_task_tools_returns_correct_count(self):
        """Test that all task tools are returned."""
        tools = get_task_tools()
        assert len(tools) == 5

    def test_tool_names_are_correct(self):
        """Test that tool names match expected values."""
        tools = get_task_tools()
        tool_names = [tool.name for tool in tools]

        assert "hopper_create_task" in tool_names
        assert "hopper_list_tasks" in tool_names
        assert "hopper_get_task" in tool_names
        assert "hopper_update_task" in tool_names
        assert "hopper_update_task_status" in tool_names

    def test_create_task_schema_has_required_fields(self):
        """Test create_task tool schema."""
        tools = get_task_tools()
        create_tool = next(t for t in tools if t.name == "hopper_create_task")

        assert "title" in create_tool.inputSchema["required"]
        assert "title" in create_tool.inputSchema["properties"]


class TestCreateTask:
    """Test create_task function."""

    @pytest.mark.asyncio
    async def test_create_task_success(self, mock_http_client, mock_http_response):
        """Test successful task creation."""
        mock_http_client.post.return_value = mock_http_response(
            json_data={
                "id": "task-123",
                "title": "New task",
                "project": "test-project",
                "external_url": "https://github.com/test/repo/issues/1",
            }
        )

        result = await create_task(
            client=mock_http_client,
            args={"title": "New task", "description": "Test description"},
            context={"user": "test-user"},
            default_priority="medium",
        )

        assert result["task_id"] == "task-123"
        assert result["title"] == "New task"
        assert result["routed_to"] == "test-project"
        assert "url" in result

        # Verify API call
        mock_http_client.post.assert_called_once()
        call_args = mock_http_client.post.call_args
        assert call_args[0][0] == "/api/v1/tasks"

    @pytest.mark.asyncio
    async def test_create_task_with_all_fields(self, mock_http_client, mock_http_response):
        """Test task creation with all optional fields."""
        mock_http_client.post.return_value = mock_http_response(
            json_data={"id": "task-456", "title": "Full task"}
        )

        result = await create_task(
            client=mock_http_client,
            args={
                "title": "Full task",
                "description": "Full description",
                "priority": "high",
                "tags": ["bug", "urgent"],
                "project": "specific-project",
            },
            context={},
            default_priority="medium",
        )

        assert result["task_id"] == "task-456"

        # Verify request data
        call_args = mock_http_client.post.call_args
        request_data = call_args[1]["json"]
        assert request_data["priority"] == "high"
        assert "bug" in request_data["tags"]


class TestListTasks:
    """Test list_tasks function."""

    @pytest.mark.asyncio
    async def test_list_tasks_default(self, mock_http_client, mock_http_response, sample_task_list):
        """Test listing tasks with default parameters."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_task_list)

        result = await list_tasks(
            client=mock_http_client,
            args={},
            default_limit=10,
        )

        assert result["total"] == 2
        assert len(result["tasks"]) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_with_filters(self, mock_http_client, mock_http_response):
        """Test listing tasks with filters."""
        mock_http_client.get.return_value = mock_http_response(json_data={"tasks": [], "total": 0})

        await list_tasks(
            client=mock_http_client,
            args={
                "status": "pending",
                "priority": "high",
                "project": "my-project",
                "tags": ["bug"],
                "limit": 5,
            },
            default_limit=10,
        )

        # Verify filters were passed
        call_args = mock_http_client.get.call_args
        params = call_args[1]["params"]
        assert params["status"] == "pending"
        assert params["priority"] == "high"
        assert params["project"] == "my-project"
        assert params["limit"] == 5


class TestGetTask:
    """Test get_task function."""

    @pytest.mark.asyncio
    async def test_get_task_success(self, mock_http_client, mock_http_response, sample_task):
        """Test getting a specific task."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_task)

        result = await get_task(
            client=mock_http_client,
            args={"task_id": "task-123"},
        )

        assert result["id"] == "task-123"
        assert result["title"] == "Test task"

        # Verify API call
        mock_http_client.get.assert_called_once_with("/api/v1/tasks/task-123")


class TestUpdateTask:
    """Test update_task function."""

    @pytest.mark.asyncio
    async def test_update_task_success(self, mock_http_client, mock_http_response):
        """Test updating a task."""
        mock_http_client.patch.return_value = mock_http_response(
            json_data={"id": "task-123", "title": "Updated"}
        )

        result = await update_task(
            client=mock_http_client,
            args={
                "task_id": "task-123",
                "title": "Updated",
            },
        )

        assert result["title"] == "Updated"

        # Verify API call
        call_args = mock_http_client.patch.call_args
        assert "task-123" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_update_task_no_fields_raises_error(self, mock_http_client):
        """Test that updating with no fields raises an error."""
        with pytest.raises(ValueError, match="No fields provided"):
            await update_task(
                client=mock_http_client,
                args={"task_id": "task-123"},
            )


class TestUpdateTaskStatus:
    """Test update_task_status function."""

    @pytest.mark.asyncio
    async def test_update_status_success(self, mock_http_client, mock_http_response):
        """Test updating task status."""
        mock_http_client.patch.return_value = mock_http_response(
            json_data={"id": "task-123", "status": "completed"}
        )

        result = await update_task_status(
            client=mock_http_client,
            args={
                "task_id": "task-123",
                "status": "completed",
            },
        )

        assert result["status"] == "completed"

        # Verify API call
        call_args = mock_http_client.patch.call_args
        assert "/status" in call_args[0][0]
        assert call_args[1]["json"]["status"] == "completed"
