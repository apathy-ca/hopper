"""CLI configuration management."""

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIConfig(BaseModel):
    """API endpoint configuration."""

    endpoint: str = Field(default="http://localhost:8000", description="API endpoint URL")
    timeout: int = Field(default=30, description="Request timeout in seconds")


class LocalConfig(BaseModel):
    """Local storage configuration."""

    path: Path = Field(
        default_factory=lambda: Path.home() / ".hopper",
        description="Path to local storage directory",
    )
    auto_detect_embedded: bool = Field(
        default=True,
        description="Auto-detect embedded .hopper in current directory",
    )


class AuthConfig(BaseModel):
    """Authentication configuration."""

    token: str | None = Field(default=None, description="Authentication token")
    api_key: str | None = Field(default=None, description="API key")


class ProfileConfig(BaseModel):
    """Configuration profile."""

    mode: str = Field(default="server", description="Operation mode: local or server")
    api: APIConfig = Field(default_factory=APIConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)


class Config(BaseSettings):
    """Main Hopper CLI configuration."""

    model_config = SettingsConfigDict(
        env_prefix="HOPPER_",
        env_nested_delimiter="__",
    )

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
                    "mode": profile.mode,
                    "api": {
                        "endpoint": profile.api.endpoint,
                        "timeout": profile.api.timeout,
                    },
                    "auth": {
                        "token": profile.auth.token,
                        "api_key": profile.auth.api_key,
                    },
                    "local": {
                        "path": str(profile.local.path),
                        "auto_detect_embedded": profile.local.auto_detect_embedded,
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
            local_data = profile_data.get("local", {})
            if "path" in local_data:
                local_data["path"] = Path(local_data["path"])

            profiles[name] = ProfileConfig(
                mode=profile_data.get("mode", "server"),
                api=APIConfig(**profile_data.get("api", {})),
                auth=AuthConfig(**profile_data.get("auth", {})),
                local=LocalConfig(**local_data) if local_data else LocalConfig(),
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


def detect_embedded_hopper() -> Path | None:
    """Detect embedded .hopper directory in current or parent directories.

    Returns:
        Path to embedded .hopper directory if found, None otherwise.
    """
    current = Path.cwd()

    # Walk up to find .hopper directory (up to 10 levels)
    for _ in range(10):
        embedded = current / ".hopper"
        if embedded.is_dir():
            # Check if it has a config.yaml (indicates it's an initialized hopper)
            if (embedded / "config.yaml").exists() or (embedded / "tasks").is_dir():
                return embedded
        if current.parent == current:
            break
        current = current.parent

    return None


def get_storage_path(config: "Config", force_local: bool = False) -> Path | None:
    """Determine the storage path based on configuration and detection.

    Args:
        config: CLI configuration
        force_local: Force local mode regardless of config

    Returns:
        Path to storage directory, or None for server mode.
    """
    profile = config.current_profile

    # Force local mode
    if force_local:
        # Try embedded first
        if profile.local.auto_detect_embedded:
            embedded = detect_embedded_hopper()
            if embedded:
                return embedded
        return profile.local.path

    # Server mode
    if profile.mode == "server":
        return None

    # Local mode - check for embedded first
    if profile.local.auto_detect_embedded:
        embedded = detect_embedded_hopper()
        if embedded:
            return embedded

    return profile.local.path


def is_local_mode(config: "Config", force_local: bool = False) -> bool:
    """Check if operating in local mode.

    Args:
        config: CLI configuration
        force_local: Force local mode

    Returns:
        True if local mode, False for server mode.
    """
    if force_local:
        return True

    profile = config.current_profile

    # Explicit local mode
    if profile.mode == "local":
        return True

    # Auto-detect embedded
    if profile.local.auto_detect_embedded:
        if detect_embedded_hopper() is not None:
            return True

    return False
