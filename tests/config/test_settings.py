"""
Tests for configuration settings.
"""

import pytest
from pydantic import ValidationError

from hopper.config import Settings, get_settings


def test_default_settings() -> None:
    """Test that default settings are valid."""
    settings = Settings()
    assert settings.hopper_env == "development"
    assert settings.api_port == 8000
    assert settings.database_url.startswith("sqlite")


def test_settings_validation_log_level() -> None:
    """Test that invalid log level raises validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(hopper_log_level="INVALID")
    assert "Log level must be one of" in str(exc_info.value)


def test_settings_validation_routing_strategy() -> None:
    """Test that invalid routing strategy raises validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(default_routing_strategy="invalid")
    assert "Routing strategy must be one of" in str(exc_info.value)


def test_settings_validation_instance_scope() -> None:
    """Test that invalid instance scope raises validation error."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(hopper_instance_scope="INVALID")
    assert "Instance scope must be one of" in str(exc_info.value)


def test_settings_properties() -> None:
    """Test settings helper properties."""
    settings = Settings(hopper_env="development")
    assert settings.is_development
    assert not settings.is_production
    assert not settings.is_testing

    settings = Settings(hopper_env="production")
    assert not settings.is_development
    assert settings.is_production
    assert not settings.is_testing

    settings = Settings(testing=True)
    assert settings.is_testing


def test_database_type_detection() -> None:
    """Test database type detection properties."""
    settings = Settings(database_url="sqlite:///./test.db")
    assert settings.database_is_sqlite
    assert not settings.database_is_postgres

    settings = Settings(database_url="postgresql://user:pass@localhost/db")
    assert not settings.database_is_sqlite
    assert settings.database_is_postgres


def test_get_settings_singleton() -> None:
    """Test that get_settings returns cached instance."""
    settings1 = get_settings()
    settings2 = get_settings()
    assert settings1 is settings2


def test_cors_origins_default() -> None:
    """Test that CORS origins has sensible defaults."""
    settings = Settings()
    assert isinstance(settings.cors_origins, list)
    assert len(settings.cors_origins) > 0


def test_custom_environment_values() -> None:
    """Test that custom environment values are respected."""
    settings = Settings(
        api_port=9000,
        database_url="postgresql://localhost/hopper",
        hopper_debug=True,
    )
    assert settings.api_port == 9000
    assert settings.database_url == "postgresql://localhost/hopper"
    assert settings.hopper_debug is True
