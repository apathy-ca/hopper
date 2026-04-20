"""Tests for configuration commands."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.config import Config, ProfileConfig
from hopper.cli.main import cli, Context


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def config_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Create an isolated config and point HOPPER_CONFIG at it.

    The root `cli` callback reloads config from disk on every invocation
    (ignoring `obj=ctx` passed to CliRunner). Redirecting HOPPER_CONFIG
    is what actually isolates tests from the user's real ~/.hopper config.
    """
    config_path = tmp_path / "config.yaml"
    config = Config(
        active_profile="default",
        profiles={"default": ProfileConfig()},
        config_path=config_path,
    )
    config.save()
    monkeypatch.setenv("HOPPER_CONFIG", str(config_path))
    return config


@pytest.fixture
def ctx(config_with_file: Config) -> Context:
    return Context(config=config_with_file, verbose=False, json_output=False)


class TestConfigGet:
    """Test config get command."""

    def test_get_api_endpoint(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(cli, ["config", "get", "api.endpoint"], obj=ctx)
        assert result.exit_code == 0
        assert "localhost:8000" in result.output

    def test_get_upstream_server(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(cli, ["config", "get", "upstream.server"], obj=ctx)
        assert result.exit_code == 0
        assert "not set" in result.output

    def test_get_github_token(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(cli, ["config", "get", "github.token"], obj=ctx)
        assert result.exit_code == 0
        assert "not set" in result.output

    def test_get_unknown_key(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(cli, ["config", "get", "nonexistent.key"], obj=ctx)
        assert result.exit_code != 0

    def test_get_active_profile(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(cli, ["config", "get", "active_profile"], obj=ctx)
        assert result.exit_code == 0
        assert "default" in result.output


class TestConfigSet:
    """Test config set command.

    These tests reload from disk after each invocation because the root CLI
    callback always loads a fresh Config — the test's `ctx.config` is never
    the one actually mutated.
    """

    def test_set_api_endpoint(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "api.endpoint", "http://newhost:9000"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.api.endpoint == "http://newhost:9000"

    def test_set_upstream_server(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "upstream.server", "https://upstream.example.com"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.upstream.server == "https://upstream.example.com"

    def test_set_upstream_enabled(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "upstream.enabled", "true"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.upstream.enabled is True

    def test_set_github_token(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "github.token", "ghp_test123"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.github.token == "ghp_test123"

    def test_set_api_timeout(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "api.timeout", "60"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.api.timeout == 60

    def test_set_knowledge_enabled(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "knowledge.enabled", "false"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.knowledge.enabled is False

    def test_set_unknown_key(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(
            cli, ["config", "set", "nonexistent.key", "value"], obj=ctx
        )
        assert result.exit_code != 0

    def test_set_null_value(self, runner: CliRunner, ctx: Context) -> None:
        # First set a value, then null it out
        runner.invoke(
            cli, ["config", "set", "upstream.server", "https://example.com"], obj=ctx
        )
        result = runner.invoke(
            cli, ["config", "set", "upstream.server", "null"], obj=ctx
        )
        assert result.exit_code == 0
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.upstream.server is None

    def test_set_persists_to_file(self, runner: CliRunner, ctx: Context) -> None:
        runner.invoke(
            cli, ["config", "set", "upstream.server", "https://saved.example.com"], obj=ctx
        )
        # Reload from disk
        reloaded = Config.load_from_file(ctx.config.config_path)
        assert reloaded.current_profile.upstream.server == "https://saved.example.com"


class TestConfigList:
    """Test config list command."""

    def test_list_shows_all_sections(self, runner: CliRunner, ctx: Context) -> None:
        result = runner.invoke(cli, ["config", "list"], obj=ctx)
        assert result.exit_code == 0
        assert "api.endpoint" in result.output
        assert "upstream.server" in result.output
        assert "github.token" in result.output
        assert "knowledge.enabled" in result.output
        assert "local.path" in result.output
