"""Regression coverage for two round-7 CLI findings on PR
owner-identity-instance-discovery:

1. org_create/org_add_member/org_remove_member/org_approve/org_revoke
   never checked ctx.json_output the way every structurally identical
   owner_* command does -- --json silently fell back to human-readable
   text, breaking automation parsing stdout as JSON.
2. `invite create --owner X --role approver` silently accepted and
   dropped --role -- create_device_invite() takes no role argument at
   all, with no warning that the flag had no effect.

Uses a fake admin client (monkeypatching _get_admin_client) rather than a
real UpstreamClient/server round-trip, since the bug is entirely in how
the CLI layer decides whether to print JSON or plain text, and whether it
validates flag combinations -- not in the HTTP/storage layers underneath,
which already have their own coverage.
"""

from __future__ import annotations

import json
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


class _FakeClient:
    """Stands in for UpstreamClient -- each method just echoes a small,
    JSON-serializable dict shaped like the real server response, enough
    to prove the CLI layer prints it as JSON when asked."""

    server_url = "https://upstream.example.com"

    def create_org(self, org_id: str, name: str = "") -> dict:
        return {"success": True, "message": "created", "org": {"id": org_id, "name": name}}

    def add_org_member(self, org_id: str, owner_id: str) -> dict:
        return {"success": True, "message": "added", "org": {"id": org_id}}

    def remove_org_member(self, org_id: str, owner_id: str) -> dict:
        return {"success": True, "message": "removed", "org": {"id": org_id}}

    def approve_org(self, org_id: str, namespace: str = "*", role: str = "approved") -> dict:
        return {"success": True, "message": f"approved for {namespace}"}

    def revoke_org(self, org_id: str, namespace: str = "*") -> dict:
        return {"success": True, "message": f"revoked from {namespace}"}


@pytest.fixture(autouse=True)
def fake_admin_client(monkeypatch: pytest.MonkeyPatch) -> None:
    from hopper.cli.commands import upstream as upstream_cmds

    monkeypatch.setattr(
        upstream_cmds,
        "_get_admin_client",
        lambda ctx, server=None, admin_key=None: (
            _FakeClient(),
            None,
        ),
    )


class TestOrgCommandsSupportJson:
    def test_org_create_json(self, runner: CliRunner, upstream_ctx: Context) -> None:
        result = runner.invoke(
            cli, ["--json", "upstream", "admin", "org", "create", "eigan-corp"], obj=upstream_ctx
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["org"]["id"] == "eigan-corp"

    def test_org_add_member_json(self, runner: CliRunner, upstream_ctx: Context) -> None:
        result = runner.invoke(
            cli,
            ["--json", "upstream", "admin", "org", "add-member", "eigan-corp", "--owner", "james"],
            obj=upstream_ctx,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["success"] is True

    def test_org_remove_member_json(self, runner: CliRunner, upstream_ctx: Context) -> None:
        result = runner.invoke(
            cli,
            [
                "--json",
                "upstream",
                "admin",
                "org",
                "remove-member",
                "eigan-corp",
                "--owner",
                "james",
            ],
            obj=upstream_ctx,
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["success"] is True

    def test_org_approve_json(self, runner: CliRunner, upstream_ctx: Context) -> None:
        result = runner.invoke(
            cli, ["--json", "upstream", "admin", "org", "approve", "eigan-corp"], obj=upstream_ctx
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["success"] is True

    def test_org_revoke_json(self, runner: CliRunner, upstream_ctx: Context) -> None:
        result = runner.invoke(
            cli, ["--json", "upstream", "admin", "org", "revoke", "eigan-corp"], obj=upstream_ctx
        )
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["success"] is True

    def test_org_create_without_json_still_prints_human_text(
        self, runner: CliRunner, upstream_ctx: Context
    ) -> None:
        """--json is opt-in -- must not regress the default output."""
        result = runner.invoke(
            cli, ["upstream", "admin", "org", "create", "eigan-corp"], obj=upstream_ctx
        )
        assert result.exit_code == 0, result.output
        assert "eigan-corp" in result.output
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)


class TestInviteCreateRoleValidation:
    def test_role_with_owner_is_rejected(self, runner: CliRunner, upstream_ctx: Context) -> None:
        result = runner.invoke(
            cli,
            ["upstream", "invite", "create", "--owner", "james", "--role", "approver"],
            obj=upstream_ctx,
        )
        assert result.exit_code != 0
        assert "--role only applies to --namespace" in result.output

    def test_role_with_new_owner_is_rejected(
        self, runner: CliRunner, upstream_ctx: Context
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "upstream",
                "invite",
                "create",
                "--new-owner",
                "james",
                "--email",
                "james@eigan.ai",
                "--role",
                "approver",
            ],
            obj=upstream_ctx,
        )
        assert result.exit_code != 0
        assert "--role only applies to --namespace" in result.output

    def test_default_role_with_owner_is_still_fine(
        self, runner: CliRunner, upstream_ctx: Context, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Not passing --role at all must not trip the new check --
        create_device_invite() is still called with no role arg."""
        from hopper.cli.commands import upstream as upstream_cmds

        class _InviteClient(_FakeClient):
            server_url = "https://upstream.example.com"

            def create_device_invite(self, owner_id, expires_in_ms=None, max_uses=1) -> dict:
                return {
                    "token": "tok_abc",
                    "invite": {"uses": 0, "max_uses": max_uses, "expires_at": None},
                }

        monkeypatch.setattr(
            upstream_cmds,
            "_get_admin_client",
            lambda ctx, server=None, admin_key=None: (_InviteClient(), None),
        )

        result = runner.invoke(
            cli, ["upstream", "invite", "create", "--owner", "james"], obj=upstream_ctx
        )

        assert result.exit_code == 0, result.output
