"""
Project resources for MCP.

Exposes projects as MCP resources accessible via hopper://projects/* URIs.
"""

import json
from typing import Any
import httpx
from mcp.types import Resource, TextContent


def get_project_resources() -> list[Resource]:
    """Get list of project resource definitions.

    Returns:
        List of MCP Resource definitions for projects
    """
    return [
        Resource(
            uri="hopper://projects",
            name="All Projects",
            description="List of all projects registered in Hopper",
            mimeType="application/json",
        ),
    ]


async def read_project_resource(
    uri: str,
    client: httpx.AsyncClient,
    default_limit: int = 50,
) -> list[TextContent]:
    """Read a project resource by URI.

    Args:
        uri: Resource URI (e.g., hopper://projects, hopper://projects/{project_id})
        client: HTTP client configured for the Hopper API
        default_limit: Default limit for project lists

    Returns:
        Resource content as TextContent

    Raises:
        ValueError: If URI is not recognized
    """
    # Parse the URI
    if not uri.startswith("hopper://projects"):
        raise ValueError(f"Invalid project resource URI: {uri}")

    # Extract path after hopper://projects
    path = uri.replace("hopper://projects", "").lstrip("/")

    # Handle different resource types
    if not path or path == "":
        # List all projects
        response = await client.get("/api/v1/projects", params={"limit": default_limit})
        response.raise_for_status()
        data = response.json()

        content = {
            "uri": uri,
            "type": "project_list",
            "projects": data.get("projects", []),
            "total": data.get("total", 0),
        }

        return [TextContent(
            type="text",
            text=json.dumps(content, indent=2)
        )]

    else:
        # Assume it's a project ID
        project_id = path

        response = await client.get(f"/api/v1/projects/{project_id}")
        response.raise_for_status()
        project = response.json()

        # Also get tasks for this project
        tasks_response = await client.get(
            "/api/v1/tasks",
            params={"project": project_id, "limit": 10}
        )
        tasks_response.raise_for_status()
        tasks_data = tasks_response.json()

        content = {
            "uri": uri,
            "type": "project",
            "project": project,
            "recent_tasks": tasks_data.get("tasks", []),
        }

        return [TextContent(
            type="text",
            text=json.dumps(content, indent=2)
        )]
