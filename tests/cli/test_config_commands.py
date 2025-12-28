"""Tests for configuration and authentication commands."""

import pytest
from click.testing import CliRunner
from unittest.mock import Mock
from pathlib import Path

from hopper.cli.main import cli
from hopper.cli.config import Config


def test_init_command(runner: CliRunner, temp_config_dir: Path, monkeypatch) -> None:
    """Test initialization command."""
    config_path = temp_config_dir / "config.yaml"
    monkeypatch.setenv("HOME", str(temp_config_dir))

    result = runner.invoke(
        cli,
        [
            "init",
            "--endpoint", "http://localhost:8000",
            "--non-interactive"
        ]
    )

    assert result.exit_code == 0


def test_config_get(runner: CliRunner, mock_config) -> None:
    """Test getting configuration value."""
    result = runner.invoke(
        cli,
        ["config", "get", "api.endpoint"],
        obj=mock_config
    )

    assert result.exit_code == 0
    assert "http://localhost:8000" in result.output


def test_config_set(runner: CliRunner, mock_config, temp_config_dir: Path) -> None:
    """Test setting configuration value."""
    mock_config.config_path = temp_config_dir / "config.yaml"

    result = runner.invoke(
        cli,
        ["config", "set", "api.endpoint", "http://newhost:9000"],
        obj=mock_config
    )

    assert result.exit_code == 0
    assert mock_config.current_profile.api.endpoint == "http://newhost:9000"


def test_config_list(runner: CliRunner, mock_config) -> None:
    """Test listing configuration."""
    result = runner.invoke(
        cli,
        ["config", "list"],
        obj=mock_config
    )

    assert result.exit_code == 0
    assert "api.endpoint" in result.output


def test_auth_login_with_token(runner: CliRunner, mock_config, temp_config_dir: Path, mock_client: Mock) -> None:
    """Test login with token."""
    mock_config.config_path = temp_config_dir / "config.yaml"
    mock_client.get.return_value = {"status": "ok"}

    result = runner.invoke(
        cli,
        ["auth", "login", "--token", "new-token", "--profile", "test"],
        obj=mock_config,
        input="n\n"  # Don't test connection
    )

    assert result.exit_code == 0
    assert mock_config.profiles["test"].auth.token == "new-token"


def test_auth_logout(runner: CliRunner, mock_config, temp_config_dir: Path) -> None:
    """Test logout command."""
    mock_config.config_path = temp_config_dir / "config.yaml"

    result = runner.invoke(
        cli,
        ["auth", "logout"],
        obj=mock_config
    )

    assert result.exit_code == 0
    assert mock_config.current_profile.auth.token is None


def test_auth_status_authenticated(runner: CliRunner, mock_config, mock_client: Mock) -> None:
    """Test auth status when authenticated."""
    mock_client.get.return_value = {"status": "ok"}

    result = runner.invoke(
        cli,
        ["auth", "status"],
        obj=mock_config
    )

    assert result.exit_code == 0
    assert "Authenticated" in result.output
