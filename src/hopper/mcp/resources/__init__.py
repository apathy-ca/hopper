"""
MCP resources for Hopper.

Exports all MCP resource definitions and handlers for tasks and projects.
"""

from collections.abc import Awaitable, Callable

import httpx
from mcp.types import Resource, TextContent

from .project_resources import (
    get_project_resources,
    read_project_resource,
)
from .task_resources import (
    get_task_resources,
    read_task_resource,
)

# Resource handler type
ResourceHandler = Callable[[str, httpx.AsyncClient], Awaitable[list[TextContent]]]


def get_all_resources() -> list[Resource]:
    """Get all MCP resource definitions.

    Returns:
        List of all Resource definitions for tasks and projects
    """
    return [
        *get_task_resources(),
        *get_project_resources(),
    ]


async def read_resource(
    uri: str,
    client: httpx.AsyncClient,
    config: any = None,
) -> list[TextContent]:
    """Read a resource by URI.

    Args:
        uri: Resource URI (e.g., hopper://tasks, hopper://projects/foo)
        client: HTTP client configured for the Hopper API
        config: Optional server configuration for defaults

    Returns:
        Resource content as TextContent list

    Raises:
        ValueError: If URI is not recognized
    """
    if uri.startswith("hopper://tasks"):
        default_limit = config.default_task_limit if config else 20
        return await read_task_resource(uri, client, default_limit)
    elif uri.startswith("hopper://projects"):
        return await read_project_resource(uri, client)
    else:
        raise ValueError(f"Unknown resource URI: {uri}")


__all__ = [
    # Resource definitions
    "get_all_resources",
    "get_task_resources",
    "get_project_resources",
    # Resource handlers
    "read_resource",
    # Individual handlers (for direct use if needed)
    "read_task_resource",
    "read_project_resource",
]
