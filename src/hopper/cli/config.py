"""CLI configuration management."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class APIConfig(BaseModel):
    """API endpoint configuration."""

    endpoint: str = Field(default="http://localhost:8000", description="API endpoint URL")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class AuthConfig(BaseModel):
    """Authentication configuration."""

    token: str | None = Field(default=None, description="Authentication token")
    api_key: str | None = Field(default=None, description="API key")


class ProfileConfig(BaseModel):
    """Configuration profile."""

    api: APIConfig = Field(default_factory=APIConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)


class Config(BaseSettings):
    """Main Hopper CLI configuration."""

    # Current active profile
    active_profile: str = Field(default="default", description="Active configuration profile")

    # Configuration profiles
    profiles: dict[str, ProfileConfig] = Field(
        default_factory=lambda: {"default": ProfileConfig()}, description="Configuration profiles"
    )

    # Configuration file path
    config_path: Path = Field(
        default_factory=lambda: Path.home() / ".hopper" / "config.yaml",
        description="Path to configuration file",
    )

    class Config:
        env_prefix = "HOPPER_"
        env_nested_delimiter = "__"

    @property
    def current_profile(self) -> ProfileConfig:
        """Get the current active profile."""
        return self.profiles.get(self.active_profile, ProfileConfig())

    def save(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "active_profile": self.active_profile,
            "profiles": {
                name: {
                    "api": {
                        "endpoint": profile.api.endpoint,
                        "timeout": profile.api.timeout,
                    },
                    "auth": {
                        "token": profile.auth.token,
                        "api_key": profile.auth.api_key,
                    },
                }
                for name, profile in self.profiles.items()
            },
        }

        with open(self.config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load_from_file(cls, config_path: Path) -> "Config":
        """Load configuration from file."""
        if not config_path.exists():
            return cls(config_path=config_path)

        with open(config_path) as f:
            data = yaml.safe_load(f) or {}

        profiles = {}
        for name, profile_data in data.get("profiles", {}).items():
            profiles[name] = ProfileConfig(
                api=APIConfig(**profile_data.get("api", {})),
                auth=AuthConfig(**profile_data.get("auth", {})),
            )

        return cls(
            active_profile=data.get("active_profile", "default"),
            profiles=profiles or {"default": ProfileConfig()},
            config_path=config_path,
        )


def load_config(config_path: str | None = None) -> Config:
    """Load Hopper configuration.

    Args:
        config_path: Optional path to configuration file. If not provided,
                    uses default location (~/.hopper/config.yaml) or
                    HOPPER_CONFIG environment variable.

    Returns:
        Loaded configuration object.
    """
    if config_path:
        path = Path(config_path)
    elif env_config := os.getenv("HOPPER_CONFIG"):
        path = Path(env_config)
    else:
        path = Path.home() / ".hopper" / "config.yaml"

    return Config.load_from_file(path)


def get_config_dir() -> Path:
    """Get Hopper configuration directory."""
    config_dir = Path.home() / ".hopper"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir
