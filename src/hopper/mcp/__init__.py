"""
Hopper MCP (Model Context Protocol) integration.

MCP tools and server implementation for Hopper.
"""

from .config import MCPServerConfig, get_mcp_config
from .context import ServerContext
from .server import HopperMCPServer, create_server

__all__ = [
    "MCPServerConfig",
    "get_mcp_config",
    "HopperMCPServer",
    "create_server",
    "ServerContext",
]

__version__ = "1.0.0"
