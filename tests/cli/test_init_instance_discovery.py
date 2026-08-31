"""Tests for 'hopper init' instance discovery (Phase D of
Owner-Identity-and-Instance-Discovery-Plan.md).

Covers: plain local-only init is completely unaffected (no upstream
configured, the common case); discovery is mocked at the
_discover_reachable_instances seam rather than run against a live
server/DID — that full chain (real server, real signing, real redeem) is
covered by a manual end-to-end smoke test, not unit tests, matching how
the rest of this plan's phases were verified. --no-knowledge on every
invocation avoids any network call to the agent-knowledge source.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml
from click.testing import CliRunner

from hopper.cli.config import Config, ProfileConfig
from hopper.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated config file + isolated cwd named 'myproject', so the
    directory-name default is a known, assertable value."""
    config_path = tmp_path / "config.yaml"
    config = Config(
        active_profile="default", profiles={"default": ProfileConfig()}, config_path=config_path
    )
    config.save()
    monkeypatch.setenv("HOPPER_CONFIG", str(config_path))

    project = tmp_path / "myproject"
    project.mkdir()
    monkeypatch.chdir(project)
    return project


def _instance_name(project_dir: Path) -> str:
    data = yaml.safe_load((project_dir / ".hopper" / "config.yaml").read_text())
    return data["instance"]["name"]


class TestNoUpstreamConfigured:
    """The common case — no upstream server configured at all. Must
    behave exactly as before this plan existed."""

    def test_defaults_to_directory_name(self, runner: CliRunner, project_dir: Path) -> None:
        result = runner.invoke(
            cli, ["init", "--no-knowledge", "--non-interactive"], catch_exceptions=False
        )

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "myproject"

    def test_explicit_name_still_wins(self, runner: CliRunner, project_dir: Path) -> None:
        result = runner.invoke(
            cli,
            ["init", "--no-knowledge", "--non-interactive", "--name", "explicit-name"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "explicit-name"


class TestDiscoveryMocked:
    """_discover_reachable_instances mocked at the seam config.py calls —
    covers the picker/refusal logic in isolation from real DID/server
    plumbing."""

    def _patch_discovery(self, monkeypatch: pytest.MonkeyPatch, return_value) -> MagicMock:
        mock = MagicMock(return_value=return_value)
        monkeypatch.setattr("hopper.cli.commands.config._discover_reachable_instances", mock)
        return mock

    def test_discovery_none_falls_back_to_directory_name(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """None means 'not applicable' (no upstream, or DID unlinked) —
        must fall back exactly like the no-upstream case."""
        self._patch_discovery(monkeypatch, None)

        result = runner.invoke(
            cli, ["init", "--no-knowledge", "--non-interactive"], catch_exceptions=False
        )

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "myproject"

    def test_no_candidates_and_no_global_falls_back_to_directory_name(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Owner is linked but has zero grants anywhere — nothing to
        discover, same as the no-upstream case."""
        self._patch_discovery(monkeypatch, ([], False, False))

        result = runner.invoke(
            cli, ["init", "--no-knowledge", "--non-interactive"], catch_exceptions=False
        )

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "myproject"

    def test_explicit_name_skips_discovery_without_even_calling_it(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock = self._patch_discovery(monkeypatch, ([], False, False))
        # Make it obvious if it's ever called despite --name being given.
        mock.side_effect = AssertionError("_discover_reachable_instances should not be called")

        result = runner.invoke(
            cli,
            ["init", "--no-knowledge", "--non-interactive", "--name", "explicit-name"],
            catch_exceptions=False,
        )

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "explicit-name"
        mock.assert_not_called()

    def test_non_interactive_with_candidates_refuses_and_lists_them(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_discovery(monkeypatch, (["eigan", "waypoint"], False, False))

        result = runner.invoke(cli, ["init", "--no-knowledge", "--non-interactive"])

        assert result.exit_code != 0
        assert "eigan" in result.output
        assert "waypoint" in result.output
        assert not (project_dir / ".hopper" / "config.yaml").exists()

    def test_non_interactive_with_global_access_only_still_refuses(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No explicit namespace list, but a global ('*') grant — still a
        real reason to refuse the silent default."""
        self._patch_discovery(monkeypatch, ([], True, False))

        result = runner.invoke(cli, ["init", "--no-knowledge", "--non-interactive"])

        assert result.exit_code != 0
        assert not (project_dir / ".hopper" / "config.yaml").exists()

    def test_interactive_picker_selects_existing_instance_by_number(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_discovery(monkeypatch, (["eigan", "waypoint"], False, False))

        result = runner.invoke(cli, ["init", "--no-knowledge"], input="1\n", catch_exceptions=False)

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "eigan"

    def test_interactive_picker_create_new_option_uses_directory_name(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_discovery(monkeypatch, (["eigan"], False, False))

        # Candidate 1 is "eigan"; option 2 is "create new: myproject".
        result = runner.invoke(cli, ["init", "--no-knowledge"], input="2\n", catch_exceptions=False)

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "myproject"

    def test_interactive_picker_default_choice_is_create_new(
        self, runner: CliRunner, project_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Just pressing enter (empty input) should take the prompt's
        default, which is 'create new', not silently pick an existing
        instance — an empty answer must never look like a deliberate
        choice of someone else's data."""
        self._patch_discovery(monkeypatch, (["eigan"], False, False))

        result = runner.invoke(cli, ["init", "--no-knowledge"], input="\n", catch_exceptions=False)

        assert result.exit_code == 0
        assert _instance_name(project_dir) == "myproject"
