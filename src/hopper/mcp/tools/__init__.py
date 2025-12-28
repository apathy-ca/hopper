"""
MCP tools for Hopper.

Exports all MCP tool definitions and handlers for task management,
project management, and routing.
"""

from typing import Any, Callable, Awaitable
import httpx
from mcp.types import Tool

from .task_tools import (
    get_task_tools,
    create_task,
    list_tasks,
    get_task,
    update_task,
    update_task_status,
)
from .project_tools import (
    get_project_tools,
    list_projects,
    get_project,
    create_project,
    get_project_tasks,
)
from .routing_tools import (
    get_routing_tools,
    route_task,
    get_routing_suggestions,
)


# Tool registry mapping tool names to their handler functions
ToolHandler = Callable[[httpx.AsyncClient, dict[str, Any]], Awaitable[dict[str, Any]]]

TOOL_HANDLERS: dict[str, ToolHandler] = {
    # Task tools
    "hopper_create_task": create_task,
    "hopper_list_tasks": list_tasks,
    "hopper_get_task": get_task,
    "hopper_update_task": update_task,
    "hopper_update_task_status": update_task_status,
    # Project tools
    "hopper_list_projects": list_projects,
    "hopper_get_project": get_project,
    "hopper_create_project": create_project,
    "hopper_get_project_tasks": get_project_tasks,
    # Routing tools
    "hopper_route_task": route_task,
    "hopper_get_routing_suggestions": get_routing_suggestions,
}


def get_all_tools() -> list[Tool]:
    """Get all MCP tool definitions.

    Returns:
        List of all Tool definitions for task, project, and routing operations
    """
    return [
        *get_task_tools(),
        *get_project_tools(),
        *get_routing_tools(),
    ]


async def call_tool(
    name: str,
    arguments: dict[str, Any],
    client: httpx.AsyncClient,
    context: dict[str, Any],
    config: Any = None,
) -> dict[str, Any]:
    """Call a tool by name with the provided arguments.

    Args:
        name: Tool name to invoke
        arguments: Tool arguments
        client: HTTP client configured for the Hopper API
        context: Server context to pass to tools
        config: Optional server configuration for defaults

    Returns:
        Tool execution result

    Raises:
        ValueError: If tool name is not recognized
    """
    handler = TOOL_HANDLERS.get(name)

    if handler is None:
        raise ValueError(f"Unknown tool: {name}")

    # Special handling for create_task which needs context and config
    if name == "hopper_create_task" and config:
        return await handler(client, arguments, context, config.default_priority)
    elif name == "hopper_list_tasks" and config:
        return await handler(client, arguments, config.default_task_limit)
    else:
        return await handler(client, arguments)


__all__ = [
    # Tool definitions
    "get_all_tools",
    "get_task_tools",
    "get_project_tools",
    "get_routing_tools",
    # Tool handlers
    "call_tool",
    "TOOL_HANDLERS",
    # Individual handlers (for direct use if needed)
    "create_task",
    "list_tasks",
    "get_task",
    "update_task",
    "update_task_status",
    "list_projects",
    "get_project",
    "create_project",
    "get_project_tasks",
    "route_task",
    "get_routing_suggestions",
]
