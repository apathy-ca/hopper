"""
Hopper configuration settings.

Uses pydantic-settings to load configuration from environment variables
with validation and type safety.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Settings are loaded from:
    1. Environment variables
    2. .env file (if present)
    3. Default values defined here
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== Application Settings =====
    hopper_env: str = Field(default="development", description="Environment name")
    hopper_debug: bool = Field(default=False, description="Debug mode")
    hopper_log_level: str = Field(default="INFO", description="Logging level")

    # ===== Database Configuration =====
    database_url: str = Field(
        default="sqlite:///./hopper.db",
        description="Database connection URL",
    )

    # ===== Redis Configuration =====
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_enabled: bool = Field(
        default=False,
        description="Enable Redis for working memory",
    )

    # ===== API Configuration =====
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=1, description="Number of API workers")
    api_reload: bool = Field(
        default=False,
        description="Auto-reload on code changes",
    )

    # CORS settings
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins",
    )

    # ===== Authentication & Security =====
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for JWT tokens",
    )
    access_token_expire_minutes: int = Field(
        default=30,
        description="Access token expiration time",
    )

    # ===== MCP Server Configuration =====
    mcp_enabled: bool = Field(default=True, description="Enable MCP server")
    mcp_server_name: str = Field(default="hopper", description="MCP server name")

    # ===== Intelligence Configuration =====
    default_routing_strategy: str = Field(
        default="rules",
        description="Default routing strategy: rules, llm, sage",
    )
    anthropic_api_key: str = Field(
        default="",
        description="Anthropic API key for LLM routing",
    )

    # ===== Memory Configuration =====
    working_memory_ttl: int = Field(
        default=3600,
        description="Working memory TTL in seconds",
    )

    # Episodic Memory (OpenSearch) - Phase 3
    opensearch_url: str = Field(
        default="http://localhost:9200",
        description="OpenSearch URL",
    )
    opensearch_enabled: bool = Field(
        default=False,
        description="Enable OpenSearch for episodic memory",
    )

    # Consolidated Memory (GitLab) - Phase 3
    gitlab_url: str = Field(default="https://gitlab.com", description="GitLab URL")
    gitlab_token: str = Field(default="", description="GitLab API token")
    consolidated_memory_enabled: bool = Field(
        default=False,
        description="Enable consolidated memory",
    )

    # ===== Platform Integration =====
    # GitHub
    github_token: str = Field(default="", description="GitHub API token")
    github_sync_enabled: bool = Field(
        default=False,
        description="Enable GitHub sync",
    )

    # GitLab
    gitlab_sync_token: str = Field(default="", description="GitLab sync API token")
    gitlab_sync_enabled: bool = Field(
        default=False,
        description="Enable GitLab sync",
    )

    # ===== Federation =====
    federation_enabled: bool = Field(
        default=False,
        description="Enable federation",
    )
    hopper_instance_name: str = Field(
        default="hopper-local",
        description="Hopper instance name",
    )
    hopper_instance_scope: str = Field(
        default="GLOBAL",
        description="Hopper instance scope",
    )

    # ===== Development Settings =====
    auto_reload: bool = Field(
        default=False,
        description="Auto-reload on code changes",
    )
    auto_create_tables: bool = Field(
        default=True,
        description="Auto-create database tables",
    )
    testing: bool = Field(default=False, description="Test mode")

    @field_validator("hopper_log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v_upper

    @field_validator("default_routing_strategy")
    @classmethod
    def validate_routing_strategy(cls, v: str) -> str:
        """Validate routing strategy is valid."""
        valid_strategies = ["rules", "llm", "sage", "hybrid", "simple_priority"]
        if v not in valid_strategies:
            raise ValueError(f"Routing strategy must be one of {valid_strategies}")
        return v

    @field_validator("hopper_instance_scope")
    @classmethod
    def validate_instance_scope(cls, v: str) -> str:
        """Validate instance scope is valid."""
        valid_scopes = [
            "GLOBAL",
            "PROJECT",
            "ORCHESTRATION",
            "PERSONAL",
            "FAMILY",
            "EVENT",
            "FEDERATED",
        ]
        v_upper = v.upper()
        if v_upper not in valid_scopes:
            raise ValueError(f"Instance scope must be one of {valid_scopes}")
        return v_upper

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.hopper_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.hopper_env == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running in test mode."""
        return self.testing or self.hopper_env == "test"

    @property
    def database_is_sqlite(self) -> bool:
        """Check if using SQLite database."""
        return self.database_url.startswith("sqlite")

    @property
    def database_is_postgres(self) -> bool:
        """Check if using PostgreSQL database."""
        return self.database_url.startswith("postgresql")


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Settings are loaded once and cached for the application lifetime.
    Use this function to access settings throughout the application.
    """
    return Settings()
