"""A saved profile without a ``mode`` key must load as local, not server (t10ee10fb)."""

from pathlib import Path

from hopper.cli.config import load_config


def test_profile_without_mode_loads_as_local(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "active_profile: default\n"
        "profiles:\n"
        "  default:\n"
        "    upstream:\n"
        "      server: https://example.invalid\n"
        "      enabled: true\n"
    )
    assert load_config(cfg).current_profile.mode == "local"


def test_explicit_server_mode_is_respected(tmp_path: Path) -> None:
    cfg = tmp_path / "config.yaml"
    cfg.write_text("active_profile: default\nprofiles:\n  default:\n    mode: server\n")
    assert load_config(cfg).current_profile.mode == "server"
