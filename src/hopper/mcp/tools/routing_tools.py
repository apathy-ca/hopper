"""
Routing tools for MCP.

Provides MCP tools for task routing and getting routing suggestions.
"""

from typing import Any
import httpx
from mcp.types import Tool


def get_routing_tools() -> list[Tool]:
    """Get list of routing tools.

    Returns:
        List of MCP Tool definitions for routing operations
    """
    return [
        Tool(
            name="hopper_route_task",
            description=(
                "Manually route a task to an appropriate destination. This can override "
                "automatic routing or route tasks that weren't automatically assigned. "
                "The routing engine considers project capabilities and historical patterns."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to route",
                    },
                    "project_id": {
                        "type": "string",
                        "description": (
                            "Target project ID. If not provided, Hopper will suggest "
                            "the best destination."
                        ),
                    },
                    "context": {
                        "type": "object",
                        "description": (
                            "Additional context for routing decision (e.g., user preferences, "
                            "conversation context, urgency)"
                        ),
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="hopper_get_routing_suggestions",
            description=(
                "Get routing suggestions for a task description without creating the task. "
                "Useful for previewing where a task would be routed before actually creating it. "
                "Returns suggested destinations with confidence scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_description": {
                        "type": "string",
                        "description": "Task description or title to analyze",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags to help with routing",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of suggestions to return (default: 3)",
                        "default": 3,
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["task_description"],
            },
        ),
    ]


async def route_task(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Route a task to a destination via the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Routing arguments including task_id and optional project_id

    Returns:
        Routing decision with destination and confidence
    """
    task_id = args["task_id"]

    route_data: dict[str, Any] = {}

    if "project_id" in args:
        route_data["project_id"] = args["project_id"]

    if "context" in args:
        route_data["context"] = args["context"]

    response = await client.post(
        f"/api/v1/tasks/{task_id}/route",
        json=route_data
    )
    response.raise_for_status()

    result = response.json()

    return {
        "task_id": task_id,
        "routed_to": result.get("project"),
        "confidence": result.get("confidence"),
        "reason": result.get("reason"),
        "external_url": result.get("external_url"),
        "message": f"Task routed to {result.get('project')} with {result.get('confidence', 0):.0%} confidence",
    }


async def get_routing_suggestions(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Get routing suggestions for a task description.

    Args:
        client: HTTP client configured for the Hopper API
        args: Arguments containing task_description and optional tags

    Returns:
        List of suggested destinations with confidence scores
    """
    suggestion_data = {
        "description": args["task_description"],
        "tags": args.get("tags", []),
        "limit": args.get("limit", 3),
    }

    response = await client.post(
        "/api/v1/routing/suggestions",
        json=suggestion_data
    )
    response.raise_for_status()

    result = response.json()

    suggestions = result.get("suggestions", [])

    return {
        "task_description": args["task_description"],
        "suggestions": [
            {
                "project": s.get("project"),
                "confidence": s.get("confidence"),
                "reason": s.get("reason"),
                "capabilities_match": s.get("capabilities_match", []),
            }
            for s in suggestions
        ],
        "total_suggestions": len(suggestions),
    }
