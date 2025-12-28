"""
Pytest configuration and fixtures for MCP tests.

Provides shared fixtures for testing MCP server, tools, and resources.
"""

import pytest
from typing import AsyncGenerator, Dict, Any
from unittest.mock import AsyncMock, Mock
import httpx


@pytest.fixture
def mock_config():
    """Mock MCP server configuration."""
    from hopper.mcp.config import MCPServerConfig

    return MCPServerConfig(
        server_name="hopper-test",
        api_base_url="http://localhost:8080",
        api_token="test-token",
        default_priority="medium",
        default_task_limit=10,
        enable_context_persistence=False,  # Disable for tests
    )


@pytest.fixture
def mock_http_response():
    """Factory for creating mock HTTP responses."""

    def _create_response(
        status_code: int = 200,
        json_data: Dict[str, Any] = None,
        text: str = "",
    ) -> Mock:
        response = Mock(spec=httpx.Response)
        response.status_code = status_code
        response.json = Mock(return_value=json_data or {})
        response.text = text
        response.raise_for_status = Mock()

        if status_code >= 400:
            response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Error", request=Mock(), response=response
            )

        return response

    return _create_response


@pytest.fixture
async def mock_http_client(mock_http_response):
    """Mock HTTP client for API calls."""
    client = AsyncMock(spec=httpx.AsyncClient)

    # Default successful responses
    client.get = AsyncMock(
        return_value=mock_http_response(
            json_data={"tasks": [], "total": 0}
        )
    )
    client.post = AsyncMock(
        return_value=mock_http_response(
            json_data={
                "id": "task-123",
                "title": "Test task",
                "project": "test-project",
            }
        )
    )
    client.patch = AsyncMock(
        return_value=mock_http_response(
            json_data={
                "id": "task-123",
                "title": "Updated task",
            }
        )
    )
    client.aclose = AsyncMock()

    return client


@pytest.fixture
def mock_context():
    """Mock server context."""
    from hopper.mcp.context import ServerContext
    from unittest.mock import Mock

    context = Mock(spec=ServerContext)
    context.get_context = Mock(return_value={
        "user": "test-user",
        "active_project": "test-project",
    })
    context.add_recent_task = Mock()
    context.cleanup = AsyncMock()

    return context


@pytest.fixture
def sample_task():
    """Sample task data for tests."""
    return {
        "id": "task-123",
        "title": "Test task",
        "description": "This is a test task",
        "status": "pending",
        "priority": "medium",
        "project": "test-project",
        "tags": ["test", "sample"],
        "metadata": {
            "source": "mcp",
        },
        "created_at": "2025-01-01T00:00:00Z",
        "updated_at": "2025-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_project():
    """Sample project data for tests."""
    return {
        "id": "project-abc",
        "name": "test-project",
        "description": "Test project",
        "platform": "github",
        "external_id": "owner/repo",
        "capabilities": ["python", "api", "testing"],
        "tags": ["backend"],
        "active": True,
        "created_at": "2025-01-01T00:00:00Z",
    }


@pytest.fixture
def sample_task_list(sample_task):
    """Sample list of tasks for tests."""
    return {
        "tasks": [
            sample_task,
            {
                **sample_task,
                "id": "task-456",
                "title": "Another task",
                "status": "in_progress",
            },
        ],
        "total": 2,
    }


@pytest.fixture
def sample_project_list(sample_project):
    """Sample list of projects for tests."""
    return {
        "projects": [
            sample_project,
            {
                **sample_project,
                "id": "project-def",
                "name": "another-project",
                "platform": "gitlab",
            },
        ],
        "total": 2,
    }


@pytest.fixture
async def mcp_server(mock_config, monkeypatch):
    """Create a test MCP server instance."""
    from hopper.mcp.server import HopperMCPServer

    # Mock the HTTP client creation
    async def mock_get_client(self):
        return AsyncMock(spec=httpx.AsyncClient)

    monkeypatch.setattr(
        HopperMCPServer,
        "_get_http_client",
        mock_get_client
    )

    server = HopperMCPServer(config=mock_config)
    yield server

    # Cleanup
    await server.cleanup()
