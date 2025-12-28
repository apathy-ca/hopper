"""
Hopper MCP (Model Context Protocol) integration.

MCP tools and server implementation for Hopper.
"""

from .config import MCPServerConfig, get_mcp_config
from .server import HopperMCPServer, create_server
from .context import ServerContext

__all__ = [
    "MCPServerConfig",
    "get_mcp_config",
    "HopperMCPServer",
    "create_server",
    "ServerContext",
]

__version__ = "1.0.0"
