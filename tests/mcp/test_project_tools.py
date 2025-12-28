"""Tests for MCP project management tools."""

import pytest

from hopper.mcp.tools.project_tools import (
    create_project,
    get_project,
    get_project_tools,
    list_projects,
)


class TestProjectToolDefinitions:
    """Test project tool definitions."""

    def test_get_project_tools_returns_correct_count(self):
        """Test that all project tools are returned."""
        tools = get_project_tools()
        assert len(tools) == 4

    def test_tool_names_are_correct(self):
        """Test that tool names match expected values."""
        tools = get_project_tools()
        tool_names = [tool.name for tool in tools]
        assert "hopper_list_projects" in tool_names
        assert "hopper_get_project" in tool_names
        assert "hopper_create_project" in tool_names
        assert "hopper_get_project_tasks" in tool_names


class TestProjectFunctions:
    """Test project functions."""

    @pytest.mark.asyncio
    async def test_list_projects(self, mock_http_client, mock_http_response, sample_project_list):
        """Test listing projects."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_project_list)
        result = await list_projects(client=mock_http_client, args={})
        assert result["total"] == 2
        assert len(result["projects"]) == 2

    @pytest.mark.asyncio
    async def test_get_project(self, mock_http_client, mock_http_response, sample_project):
        """Test getting a project."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_project)
        result = await get_project(client=mock_http_client, args={"project_id": "project-abc"})
        assert result["id"] == "project-abc"

    @pytest.mark.asyncio
    async def test_create_project(self, mock_http_client, mock_http_response):
        """Test creating a project."""
        mock_http_client.post.return_value = mock_http_response(
            json_data={
                "id": "project-new",
                "name": "new-project",
                "platform": "github",
                "external_id": "owner/repo",
            }
        )
        result = await create_project(
            client=mock_http_client,
            args={"name": "new-project", "platform": "github", "external_id": "owner/repo"},
        )
        assert result["project_id"] == "project-new"
        assert "message" in result
