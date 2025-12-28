"""
Project management tools for MCP.

Provides MCP tools for listing, getting, creating projects, and retrieving project tasks.
"""

from typing import Any
import httpx
from mcp.types import Tool


def get_project_tools() -> list[Tool]:
    """Get list of project management tools.

    Returns:
        List of MCP Tool definitions for project management
    """
    return [
        Tool(
            name="hopper_list_projects",
            description=(
                "List all projects registered in Hopper. Projects represent different "
                "destinations where tasks can be routed (e.g., GitHub repos, GitLab projects)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of projects to return (default: 50)",
                        "default": 50,
                        "minimum": 1,
                        "maximum": 200,
                    },
                    "active_only": {
                        "type": "boolean",
                        "description": "Only return active projects (default: true)",
                        "default": True,
                    },
                },
            },
        ),
        Tool(
            name="hopper_get_project",
            description=(
                "Get detailed information about a specific project including its "
                "configuration, routing rules, and statistics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier or slug",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="hopper_create_project",
            description=(
                "Register a new project in Hopper. This allows tasks to be routed to "
                "this project. Typically used to add GitHub repos or GitLab projects."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Project name (e.g., 'hopper')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Project description",
                    },
                    "platform": {
                        "type": "string",
                        "enum": ["github", "gitlab", "jira", "linear"],
                        "description": "Platform where the project is hosted",
                    },
                    "external_id": {
                        "type": "string",
                        "description": (
                            "External identifier (e.g., 'owner/repo' for GitHub, "
                            "project ID for GitLab)"
                        ),
                    },
                    "capabilities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "List of project capabilities (e.g., ['python', 'api', 'mcp']). "
                            "Used for intelligent routing."
                        ),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization",
                    },
                },
                "required": ["name", "platform", "external_id"],
            },
        ),
        Tool(
            name="hopper_get_project_tasks",
            description=(
                "Get all tasks for a specific project. Useful for seeing what work "
                "is queued or in progress for a project."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Filter tasks by status",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return (default: 20)",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["project_id"],
            },
        ),
    ]


async def list_projects(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """List projects from the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Filter arguments from MCP tool call

    Returns:
        List of projects
    """
    params = {
        "limit": args.get("limit", 50),
    }

    if "active_only" in args:
        params["active_only"] = args["active_only"]

    response = await client.get("/api/v1/projects", params=params)
    response.raise_for_status()

    data = response.json()
    return {
        "projects": data.get("projects", []),
        "total": data.get("total", 0),
    }


async def get_project(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Get a specific project from the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Arguments containing project_id

    Returns:
        Full project details
    """
    project_id = args["project_id"]

    response = await client.get(f"/api/v1/projects/{project_id}")
    response.raise_for_status()

    return response.json()


async def create_project(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Create a new project via the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Project creation arguments

    Returns:
        Created project details
    """
    project_data = {
        "name": args["name"],
        "description": args.get("description", ""),
        "platform": args["platform"],
        "external_id": args["external_id"],
        "capabilities": args.get("capabilities", []),
        "tags": args.get("tags", []),
    }

    response = await client.post("/api/v1/projects", json=project_data)
    response.raise_for_status()

    project = response.json()

    return {
        "project_id": project["id"],
        "name": project["name"],
        "platform": project["platform"],
        "external_id": project["external_id"],
        "status": "created",
        "message": f"Project '{project['name']}' registered successfully",
    }


async def get_project_tasks(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Get tasks for a specific project from the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Arguments containing project_id and optional filters

    Returns:
        List of tasks for the project
    """
    project_id = args["project_id"]

    params = {
        "limit": args.get("limit", 20),
        "project": project_id,
    }

    if "status" in args:
        params["status"] = args["status"]

    response = await client.get("/api/v1/tasks", params=params)
    response.raise_for_status()

    data = response.json()
    return {
        "project_id": project_id,
        "tasks": data.get("tasks", []),
        "total": data.get("total", 0),
    }
