"""
Task resources for MCP.

Exposes tasks as MCP resources accessible via hopper://tasks/* URIs.
"""

import json
from typing import Any
import httpx
from mcp.types import Resource, TextContent


def get_task_resources() -> list[Resource]:
    """Get list of task resource definitions.

    Returns:
        List of MCP Resource definitions for tasks
    """
    return [
        Resource(
            uri="hopper://tasks",
            name="All Tasks",
            description="List of all tasks in Hopper",
            mimeType="application/json",
        ),
        Resource(
            uri="hopper://tasks/pending",
            name="Pending Tasks",
            description="List of pending tasks",
            mimeType="application/json",
        ),
        Resource(
            uri="hopper://tasks/in_progress",
            name="In Progress Tasks",
            description="List of tasks currently in progress",
            mimeType="application/json",
        ),
        Resource(
            uri="hopper://tasks/completed",
            name="Completed Tasks",
            description="List of completed tasks",
            mimeType="application/json",
        ),
    ]


async def read_task_resource(
    uri: str,
    client: httpx.AsyncClient,
    default_limit: int = 20,
) -> list[TextContent]:
    """Read a task resource by URI.

    Args:
        uri: Resource URI (e.g., hopper://tasks, hopper://tasks/{task_id})
        client: HTTP client configured for the Hopper API
        default_limit: Default limit for task lists

    Returns:
        Resource content as TextContent

    Raises:
        ValueError: If URI is not recognized
    """
    # Parse the URI
    if not uri.startswith("hopper://tasks"):
        raise ValueError(f"Invalid task resource URI: {uri}")

    # Extract path after hopper://tasks
    path = uri.replace("hopper://tasks", "").lstrip("/")

    # Handle different resource types
    if not path or path == "":
        # List all tasks
        response = await client.get("/api/v1/tasks", params={"limit": default_limit})
        response.raise_for_status()
        data = response.json()

        content = {
            "uri": uri,
            "type": "task_list",
            "tasks": data.get("tasks", []),
            "total": data.get("total", 0),
        }

        return [TextContent(
            type="text",
            text=json.dumps(content, indent=2)
        )]

    elif path in ["pending", "in_progress", "completed", "cancelled"]:
        # List tasks by status
        response = await client.get(
            "/api/v1/tasks",
            params={"status": path, "limit": default_limit}
        )
        response.raise_for_status()
        data = response.json()

        content = {
            "uri": uri,
            "type": "task_list",
            "status": path,
            "tasks": data.get("tasks", []),
            "total": data.get("total", 0),
        }

        return [TextContent(
            type="text",
            text=json.dumps(content, indent=2)
        )]

    else:
        # Assume it's a task ID
        task_id = path

        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()
        task = response.json()

        content = {
            "uri": uri,
            "type": "task",
            "task": task,
        }

        return [TextContent(
            type="text",
            text=json.dumps(content, indent=2)
        )]
