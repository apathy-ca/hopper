"""
MCP server implementation for Hopper.

Provides MCP (Model Context Protocol) server that allows Claude and other AI
assistants to interact with Hopper for task management and routing.
"""

import logging
from typing import Any, Optional, Sequence
from contextlib import asynccontextmanager

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, Resource, TextContent, ImageContent, EmbeddedResource

from .config import MCPServerConfig, get_mcp_config
from .context import ServerContext


logger = logging.getLogger(__name__)


class HopperMCPServer:
    """MCP server for Hopper task management."""

    def __init__(self, config: Optional[MCPServerConfig] = None):
        """Initialize the Hopper MCP server.

        Args:
            config: Server configuration. If None, loads from environment.
        """
        self.config = config or get_mcp_config()
        self.server = Server(self.config.server_name)
        self.context = ServerContext(self.config)
        self.http_client: Optional[httpx.AsyncClient] = None

        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Register handlers
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register MCP protocol handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List available MCP tools."""
            return [
                Tool(
                    name="hopper_create_task",
                    description="Create a new task in Hopper. Tasks can be routed to appropriate projects based on content.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Task title (required)",
                            },
                            "description": {
                                "type": "string",
                                "description": "Detailed task description",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "urgent"],
                                "description": "Task priority (default: medium)",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of tags for categorization",
                            },
                            "project": {
                                "type": "string",
                                "description": "Target project (if not provided, will be auto-routed)",
                            },
                        },
                        "required": ["title"],
                    },
                ),
                Tool(
                    name="hopper_list_tasks",
                    description="List tasks from Hopper with optional filtering.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                "description": "Filter by task status",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "urgent"],
                                "description": "Filter by priority",
                            },
                            "project": {
                                "type": "string",
                                "description": "Filter by project",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Filter by tags",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of tasks to return (default: 10)",
                            },
                        },
                    },
                ),
                Tool(
                    name="hopper_get_task",
                    description="Get detailed information about a specific task.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "Task ID to retrieve",
                            },
                        },
                        "required": ["task_id"],
                    },
                ),
                Tool(
                    name="hopper_update_task",
                    description="Update an existing task.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "Task ID to update",
                            },
                            "title": {
                                "type": "string",
                                "description": "Updated title",
                            },
                            "description": {
                                "type": "string",
                                "description": "Updated description",
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "urgent"],
                                "description": "Updated priority",
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Updated tags",
                            },
                        },
                        "required": ["task_id"],
                    },
                ),
                Tool(
                    name="hopper_update_task_status",
                    description="Change the status of a task.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "task_id": {
                                "type": "string",
                                "description": "Task ID to update",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed", "cancelled"],
                                "description": "New status",
                            },
                        },
                        "required": ["task_id", "status"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Any) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
            """Handle tool calls."""
            try:
                if name == "hopper_create_task":
                    result = await self._create_task(arguments)
                elif name == "hopper_list_tasks":
                    result = await self._list_tasks(arguments)
                elif name == "hopper_get_task":
                    result = await self._get_task(arguments)
                elif name == "hopper_update_task":
                    result = await self._update_task(arguments)
                elif name == "hopper_update_task_status":
                    result = await self._update_task_status(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")

                return [TextContent(type="text", text=str(result))]
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]

        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available resources."""
            return [
                Resource(
                    uri="hopper://tasks",
                    name="All Tasks",
                    description="List of all tasks in Hopper",
                    mimeType="application/json",
                ),
            ]

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self.http_client is None:
            headers = {}
            if self.config.api_token:
                headers["Authorization"] = f"Bearer {self.config.api_token}"
            elif self.config.api_key:
                headers["X-API-Key"] = self.config.api_key

            self.http_client = httpx.AsyncClient(
                base_url=self.config.api_base_url,
                headers=headers,
                timeout=self.config.api_timeout,
            )
        return self.http_client

    async def _create_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Create a new task via the Hopper API.

        Args:
            args: Task creation arguments

        Returns:
            Created task information
        """
        client = await self._get_http_client()

        task_data = {
            "title": args["title"],
            "description": args.get("description", ""),
            "priority": args.get("priority", self.config.default_priority),
            "tags": args.get("tags", []),
            "metadata": {
                "source": "mcp",
                "context": self.context.get_context(),
            },
        }

        if "project" in args:
            task_data["project"] = args["project"]

        response = await client.post("/api/v1/tasks", json=task_data)
        response.raise_for_status()

        task = response.json()

        # Update context with the created task
        self.context.add_recent_task(task["id"], task["title"])

        return {
            "task_id": task["id"],
            "title": task["title"],
            "routed_to": task.get("project"),
            "url": task.get("external_url"),
            "status": "created",
        }

    async def _list_tasks(self, args: dict[str, Any]) -> dict[str, Any]:
        """List tasks from the Hopper API.

        Args:
            args: Filter arguments

        Returns:
            List of tasks
        """
        client = await self._get_http_client()

        params = {
            "limit": args.get("limit", self.config.default_task_limit),
        }

        if "status" in args:
            params["status"] = args["status"]
        if "priority" in args:
            params["priority"] = args["priority"]
        if "project" in args:
            params["project"] = args["project"]
        if "tags" in args:
            params["tags"] = ",".join(args["tags"])

        response = await client.get("/api/v1/tasks", params=params)
        response.raise_for_status()

        data = response.json()
        return {
            "tasks": data.get("tasks", []),
            "total": data.get("total", 0),
        }

    async def _get_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get a specific task from the Hopper API.

        Args:
            args: Task ID argument

        Returns:
            Task details
        """
        client = await self._get_http_client()
        task_id = args["task_id"]

        response = await client.get(f"/api/v1/tasks/{task_id}")
        response.raise_for_status()

        return response.json()

    async def _update_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Update a task via the Hopper API.

        Args:
            args: Update arguments

        Returns:
            Updated task
        """
        client = await self._get_http_client()
        task_id = args.pop("task_id")

        # Only include fields that were provided
        update_data = {k: v for k, v in args.items() if v is not None}

        response = await client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
        response.raise_for_status()

        return response.json()

    async def _update_task_status(self, args: dict[str, Any]) -> dict[str, Any]:
        """Update task status via the Hopper API.

        Args:
            args: Task ID and new status

        Returns:
            Updated task
        """
        client = await self._get_http_client()
        task_id = args["task_id"]
        new_status = args["status"]

        response = await client.patch(
            f"/api/v1/tasks/{task_id}/status",
            json={"status": new_status}
        )
        response.raise_for_status()

        return response.json()

    async def cleanup(self) -> None:
        """Clean up resources."""
        if self.http_client:
            await self.http_client.aclose()
        await self.context.cleanup()

    async def run(self) -> None:
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            try:
                await self.server.run(
                    read_stream,
                    write_stream,
                    self.server.create_initialization_options()
                )
            finally:
                await self.cleanup()


async def create_server(config: Optional[MCPServerConfig] = None) -> HopperMCPServer:
    """Create and initialize a Hopper MCP server.

    Args:
        config: Server configuration. If None, loads from environment.

    Returns:
        Initialized MCP server instance
    """
    return HopperMCPServer(config)
