"""Tests for MCP resources."""

import pytest

from hopper.mcp.resources import (
    get_all_resources,
)
from hopper.mcp.resources.project_resources import read_project_resource
from hopper.mcp.resources.task_resources import read_task_resource

# Mark tests requiring API integration
pytestmark = pytest.mark.skip(reason="MCP integration: Requires running API")



class TestResourceDefinitions:
    """Test resource definitions."""

    def test_get_all_resources(self):
        """Test getting all resource definitions."""
        resources = get_all_resources()
        assert len(resources) > 0

        uris = [r.uri for r in resources]
        assert "hopper://tasks" in uris
        assert "hopper://projects" in uris


class TestTaskResources:
    """Test task resource reading."""

    @pytest.mark.asyncio
    async def test_read_all_tasks(self, mock_http_client, mock_http_response, sample_task_list):
        """Test reading all tasks resource."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_task_list)

        contents = await read_task_resource("hopper://tasks", mock_http_client)
        assert len(contents) == 1
        assert "task_list" in contents[0].text

    @pytest.mark.asyncio
    async def test_read_pending_tasks(self, mock_http_client, mock_http_response):
        """Test reading pending tasks resource."""
        mock_http_client.get.return_value = mock_http_response(json_data={"tasks": [], "total": 0})

        contents = await read_task_resource("hopper://tasks/pending", mock_http_client)
        assert len(contents) == 1

    @pytest.mark.asyncio
    async def test_read_specific_task(self, mock_http_client, mock_http_response, sample_task):
        """Test reading a specific task resource."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_task)

        contents = await read_task_resource("hopper://tasks/task-123", mock_http_client)
        assert len(contents) == 1


class TestProjectResources:
    """Test project resource reading."""

    @pytest.mark.asyncio
    async def test_read_all_projects(
        self, mock_http_client, mock_http_response, sample_project_list
    ):
        """Test reading all projects resource."""
        mock_http_client.get.return_value = mock_http_response(json_data=sample_project_list)

        contents = await read_project_resource("hopper://projects", mock_http_client)
        assert len(contents) == 1
