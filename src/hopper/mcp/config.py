"""
MCP server configuration.

Handles configuration for the Hopper MCP server including API client setup,
authentication, and server metadata.
"""


from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseSettings):
    """Configuration for the Hopper MCP server."""

    model_config = SettingsConfigDict(
        env_prefix="HOPPER_",
        case_sensitive=False,
        env_file=".env",
    )

    # Server metadata
    server_name: str = "hopper"
    server_version: str = "1.0.0"
    server_description: str = "Intelligent Task Routing and Orchestration System"

    # API configuration
    api_base_url: str = "http://localhost:8080"
    api_timeout: int = 30

    # Authentication
    api_token: str | None = None
    api_key: str | None = None

    # Server behavior
    auto_route_tasks: bool = True
    default_priority: str = "medium"
    default_task_limit: int = 10

    # Context management
    enable_context_persistence: bool = True
    context_cache_ttl: int = 3600  # seconds

    # Logging
    log_level: str = "INFO"
    enable_debug: bool = False


def get_mcp_config() -> MCPServerConfig:
    """Get MCP server configuration."""
    return MCPServerConfig()
