"""Tests for upstream CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.config import Config, LocalConfig, ProfileConfig, UpstreamConfig
from hopper.cli.main import cli, Context


@pytest.fixture
def upstream_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    """Create an isolated local-mode config for upstream CLI tests."""
    config_path = tmp_path / "config.yaml"
    storage_path = tmp_path / ".hopper"
    config = Config(
        active_profile="default",
        profiles={
            "default": ProfileConfig(
                mode="local",
                local=LocalConfig(path=storage_path, auto_detect_embedded=False),
                upstream=UpstreamConfig(
                    enabled=True,
                    server="https://upstream.example.com",
                ),
            )
        },
        config_path=config_path,
    )
    config.save()
    monkeypatch.setenv("HOPPER_CONFIG", str(config_path))
    return config


@pytest.fixture
def upstream_ctx(upstream_config: Config) -> Context:
    """Create a CLI context for upstream CLI tests."""
    return Context(config=upstream_config, verbose=False, json_output=False)


class TestUpstreamStatus:
    def test_status_reads_instance_scoped_state_and_formats_utc(
        self,
        runner: CliRunner,
        upstream_ctx: Context,
    ) -> None:
        storage_path = upstream_ctx.config.current_profile.local.path
        assert storage_path is not None
        storage_path.mkdir(parents=True, exist_ok=True)
        (storage_path / "tasks").mkdir(exist_ok=True)

        instance_id = "test-instance"
        (storage_path / "config.yaml").write_text(
            f"instance:\n  id: {instance_id}\n  name: {instance_id}\n",
            encoding="utf-8",
        )

        last_sync = 1_700_000_000_000
        with (storage_path / f".sync_state_{instance_id}").open("w", encoding="utf-8") as f:
            json.dump({"last_sync": last_sync, "last_server_time": last_sync}, f)

        result = runner.invoke(cli, ["upstream", "status"], obj=upstream_ctx)

        assert result.exit_code == 0
        assert "Server: https://upstream.example.com" in result.output
        assert "Last sync: 2023-11-14T22:13:20+00:00" in result.output

    def test_status_ignores_unscoped_sync_state_file(
        self,
        runner: CliRunner,
        upstream_ctx: Context,
    ) -> None:
        storage_path = upstream_ctx.config.current_profile.local.path
        assert storage_path is not None
        storage_path.mkdir(parents=True, exist_ok=True)
        (storage_path / "tasks").mkdir(exist_ok=True)

        instance_id = "test-instance"
        (storage_path / "config.yaml").write_text(
            f"instance:\n  id: {instance_id}\n  name: {instance_id}\n",
            encoding="utf-8",
        )

        with (storage_path / ".sync_state").open("w", encoding="utf-8") as f:
            json.dump({"last_sync": 1_700_000_000_000}, f)

        result = runner.invoke(cli, ["upstream", "status"], obj=upstream_ctx)

        assert result.exit_code == 0
        assert "Last sync: never" in result.output
