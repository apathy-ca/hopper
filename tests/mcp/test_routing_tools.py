"""Tests for MCP routing tools."""

import pytest

from hopper.mcp.tools.routing_tools import (
    get_routing_suggestions,
    get_routing_tools,
    route_task,
)


class TestRoutingToolDefinitions:
    """Test routing tool definitions."""

    def test_get_routing_tools_returns_correct_count(self):
        """Test that all routing tools are returned."""
        tools = get_routing_tools()
        assert len(tools) == 2

    def test_tool_names_are_correct(self):
        """Test that tool names match expected values."""
        tools = get_routing_tools()
        tool_names = [tool.name for tool in tools]
        assert "hopper_route_task" in tool_names
        assert "hopper_get_routing_suggestions" in tool_names


class TestRoutingFunctions:
    """Test routing functions."""

    @pytest.mark.asyncio
    async def test_route_task(self, mock_http_client, mock_http_response):
        """Test routing a task."""
        mock_http_client.post.return_value = mock_http_response(
            json_data={"project": "backend", "confidence": 0.95, "reason": "API-related task"}
        )
        result = await route_task(
            client=mock_http_client, args={"task_id": "task-123", "project_id": "backend"}
        )
        assert result["routed_to"] == "backend"
        assert result["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_get_routing_suggestions(self, mock_http_client, mock_http_response):
        """Test getting routing suggestions."""
        mock_http_client.post.return_value = mock_http_response(
            json_data={
                "suggestions": [
                    {"project": "backend", "confidence": 0.9, "reason": "API task"},
                    {"project": "frontend", "confidence": 0.6, "reason": "UI mentioned"},
                ]
            }
        )
        result = await get_routing_suggestions(
            client=mock_http_client, args={"task_description": "Add API endpoint"}
        )
        assert result["total_suggestions"] == 2
        assert result["suggestions"][0]["project"] == "backend"
