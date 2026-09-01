"""Regression coverage for a round-9 CLI finding on PR
owner-identity-instance-discovery: `invite list`'s human-readable output
never rendered the device/new-owner invite kinds introduced by this PR --
it always printed `ns={inv['namespace']} role={inv['role']}`, which for
those kinds is empty/meaningless (they carry owner_id/new_owner_email
instead), rendering as an indistinguishable-looking blank namespace
invite. Only correct via --json.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.config import Config, LocalConfig, ProfileConfig, UpstreamConfig
from hopper.cli.main import Context, cli


@pytest.fixture
def upstream_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Config:
    config_path = tmp_path / "config.yaml"
    storage_path = tmp_path / ".hopper"
    config = Config(
        active_profile="default",
        profiles={
            "default": ProfileConfig(
                mode="local",
                local=LocalConfig(path=storage_path, auto_detect_embedded=False),
                upstream=UpstreamConfig(enabled=True, server="https://upstream.example.com"),
            )
        },
        config_path=config_path,
    )
    config.save()
    monkeypatch.setenv("HOPPER_CONFIG", str(config_path))
    return config


@pytest.fixture
def upstream_ctx(upstream_config: Config) -> Context:
    return Context(config=upstream_config, verbose=False, json_output=False)


def _invite(**overrides) -> dict:
    base = {
        "token_hash": "abc123def456",
        "kind": "namespace",
        "namespace": "eigan",
        "role": "approved",
        "owner_id": "",
        "new_owner_email": "",
        "issued_by": "did:key:zAdmin",
        "created_at": 0,
        "expires_at": None,
        "max_uses": 1,
        "uses": 0,
    }
    base.update(overrides)
    return base


class _FakeClient:
    server_url = "https://upstream.example.com"

    def __init__(self, invites: list[dict]) -> None:
        self._invites = invites

    def list_invites(self, namespace: str | None = None) -> dict:
        return {"invites": self._invites}


class TestInviteListRendersKindAppropriately:
    def _invoke(self, runner: CliRunner, upstream_ctx: Context, monkeypatch, invites: list[dict]):
        from hopper.cli.commands import upstream as upstream_cmds

        monkeypatch.setattr(
            upstream_cmds,
            "_get_admin_client",
            lambda ctx, server=None, admin_key=None: (_FakeClient(invites), None),
        )
        return runner.invoke(cli, ["upstream", "invite", "list"], obj=upstream_ctx)

    def test_device_invite_shows_kind_and_owner_not_a_blank_namespace(
        self, runner: CliRunner, upstream_ctx: Context, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self._invoke(
            runner,
            upstream_ctx,
            monkeypatch,
            [_invite(kind="device", namespace="", owner_id="james")],
        )

        assert result.exit_code == 0, result.output
        assert "kind=device" in result.output
        assert "owner=james" in result.output
        assert "ns=" not in result.output

    def test_new_owner_invite_shows_kind_owner_and_email(
        self, runner: CliRunner, upstream_ctx: Context, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self._invoke(
            runner,
            upstream_ctx,
            monkeypatch,
            [
                _invite(
                    kind="new_owner",
                    namespace="",
                    owner_id="james",
                    new_owner_email="james@eigan.ai",
                )
            ],
        )

        assert result.exit_code == 0, result.output
        assert "kind=new_owner" in result.output
        assert "owner=james" in result.output
        assert "email=james@eigan.ai" in result.output

    def test_namespace_invite_still_shows_ns_and_role_as_before(
        self, runner: CliRunner, upstream_ctx: Context, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self._invoke(
            runner,
            upstream_ctx,
            monkeypatch,
            [_invite(kind="namespace", namespace="eigan", role="approver")],
        )

        assert result.exit_code == 0, result.output
        assert "ns=eigan" in result.output
        assert "role=approver" in result.output

    def test_device_and_namespace_invites_look_visibly_different(
        self, runner: CliRunner, upstream_ctx: Context, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        result = self._invoke(
            runner,
            upstream_ctx,
            monkeypatch,
            [
                _invite(kind="namespace", namespace="eigan", token_hash="nsinvitehash01"),
                _invite(
                    kind="device", namespace="", owner_id="james", token_hash="devinvitehash01"
                ),
            ],
        )

        lines = [line for line in result.output.splitlines() if "…" in line]
        assert len(lines) == 2
        assert lines[0] != lines[1]
