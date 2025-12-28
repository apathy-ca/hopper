"""
MCP server implementation for Hopper.

Provides MCP (Model Context Protocol) server that allows Claude and other AI
assistants to interact with Hopper for task management and routing.
"""

import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import EmbeddedResource, ImageContent, Resource, TextContent, Tool

from .config import MCPServerConfig, get_mcp_config
from .context import ServerContext
from .resources import get_all_resources, read_resource
from .tools import call_tool as call_tool_handler
from .tools import get_all_tools

logger = logging.getLogger(__name__)


class HopperMCPServer:
    """MCP server for Hopper task management."""

    def __init__(self, config: MCPServerConfig | None = None):
        """Initialize the Hopper MCP server.

        Args:
            config: Server configuration. If None, loads from environment.
        """
        self.config = config or get_mcp_config()
        self.server = Server(self.config.server_name)
        self.context = ServerContext(self.config)
        self.http_client: httpx.AsyncClient | None = None

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
            return get_all_tools()

        @self.server.call_tool()
        async def call_tool(
            name: str, arguments: Any
        ) -> Sequence[TextContent | ImageContent | EmbeddedResource]:
            """Handle tool calls."""
            try:
                client = await self._get_http_client()
                context = self.context.get_context()

                result = await call_tool_handler(
                    name=name,
                    arguments=arguments,
                    client=client,
                    context=context,
                    config=self.config,
                )

                # Update context for task creation
                if name == "hopper_create_task" and "task_id" in result:
                    self.context.add_recent_task(result["task_id"], result.get("title", ""))

                # Format result as JSON for better readability
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error executing tool {name}: {e.response.status_code} - {e.response.text}"
                )
                return [
                    TextContent(
                        type="text", text=f"API Error ({e.response.status_code}): {e.response.text}"
                    )
                ]
            except Exception as e:
                logger.error(f"Error executing tool {name}: {e}", exc_info=True)
                return [TextContent(type="text", text=f"Error: {str(e)}")]

        @self.server.list_resources()
        async def list_resources() -> list[Resource]:
            """List available resources."""
            return get_all_resources()

        @self.server.read_resource()
        async def read_resource_handler(uri: str) -> str:
            """Handle resource read requests."""
            try:
                client = await self._get_http_client()
                contents = await read_resource(uri, client, self.config)

                # Combine all text contents into a single string
                return "\n".join(content.text for content in contents)
            except httpx.HTTPStatusError as e:
                logger.error(
                    f"HTTP error reading resource {uri}: {e.response.status_code} - {e.response.text}"
                )
                return f"API Error ({e.response.status_code}): {e.response.text}"
            except Exception as e:
                logger.error(f"Error reading resource {uri}: {e}", exc_info=True)
                return f"Error: {str(e)}"

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
                    read_stream, write_stream, self.server.create_initialization_options()
                )
            finally:
                await self.cleanup()


async def create_server(config: MCPServerConfig | None = None) -> HopperMCPServer:
    """Create and initialize a Hopper MCP server.

    Args:
        config: Server configuration. If None, loads from environment.

    Returns:
        Initialized MCP server instance
    """
    return HopperMCPServer(config)
