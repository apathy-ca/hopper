"""Tests for the write-time ``salience`` flag + ``salient_until`` expiry.

Covers the window parser, ``is_salient`` expiry semantics, the markdown
round-trip, every sync hop, and ``hopper memory add --salient``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.main import cli
from hopper.memory.salience import (
    DEFAULT_SALIENCE_WINDOW,
    is_salient,
    parse_salience_window,
    reinforced_salient_until,
    salient_until_from,
)
from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore
from hopper.storage.tasks import LocalTask
from hopper.upstream.protocol import SyncTask
from hopper.upstream.storage import UpstreamStorage
from hopper.upstream.sync import _apply_sync_task_to_local, _local_task_to_sync_task

NOW = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def task_store(tmp_path: Path) -> TaskMarkdownStore:
    storage = MarkdownStorage(StorageConfig.local(tmp_path))
    storage.initialize()
    return TaskMarkdownStore(storage)


class TestWindow:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("3d", timedelta(days=3)),
            ("12h", timedelta(hours=12)),
            ("90m", timedelta(minutes=90)),
            ("1w", timedelta(weeks=1)),
            ("1d12h", timedelta(days=1, hours=12)),
            ("2", timedelta(days=2)),
        ],
    )
    def test_parse(self, raw, expected):
        assert parse_salience_window(raw) == expected

    @pytest.mark.parametrize("raw", ["", "soon", "3x", "0d", "3d junk"])
    def test_parse_rejects(self, raw):
        with pytest.raises(ValueError):
            parse_salience_window(raw)

    def test_default_window_is_three_days(self):
        assert DEFAULT_SALIENCE_WINDOW == timedelta(days=3)
        assert salient_until_from(NOW) == NOW + timedelta(days=3)


class TestIsSalient:
    def test_unflagged_is_never_salient(self):
        assert not is_salient(LocalTask.create(title="m"), NOW)

    def test_expires_at_salient_until(self):
        mem = LocalTask.create(title="m", salience=True, salient_until=NOW + timedelta(hours=1))
        assert is_salient(mem, NOW)
        assert not is_salient(mem, NOW + timedelta(hours=1))
        assert not is_salient(mem, NOW + timedelta(days=30))

    def test_accepts_task_dicts_with_iso_strings(self):
        rec = {"salience": True, "salient_until": (NOW + timedelta(hours=1)).isoformat()}
        assert is_salient(rec, NOW)
        assert not is_salient(rec, NOW + timedelta(hours=2))

    def test_missing_expiry_falls_back_to_created_plus_default(self):
        rec = {"salience": True, "created_at": NOW.isoformat()}
        assert is_salient(rec, NOW + timedelta(days=2))
        assert not is_salient(rec, NOW + timedelta(days=4))

    def test_naive_now_treated_as_utc(self):
        mem = LocalTask.create(title="m", salience=True, salient_until=NOW + timedelta(hours=1))
        assert is_salient(mem, NOW.replace(tzinfo=None))


class TestStorageAndSync:
    def test_round_trips(self, task_store):
        until = NOW + timedelta(days=3)
        mem = LocalTask.create(title="m", kind="memory", salience=True, salient_until=until)
        task_store.create(mem)
        loaded = task_store.get(mem.id)
        assert loaded.salience is True
        assert loaded.salient_until == until

    def test_ordinary_task_stays_clean(self):
        fm = LocalTask.create(title="Fix the bug").to_frontmatter()
        assert "salience" not in fm and "salient_until" not in fm

    def test_survives_every_sync_hop(self, tmp_path, task_store):
        until = NOW + timedelta(days=3)
        local = LocalTask.create(
            title="m", status="open", kind="memory", salience=True, salient_until=until
        )
        local.instance = "test-instance"

        wire = _local_task_to_sync_task(local)
        dumped = wire.model_dump(mode="json")
        assert dumped["salience"] is True and dumped["salient_until"]

        server = UpstreamStorage(tmp_path / "server")
        ok, _ = server.put(wire, from_did="did:key:test")
        assert ok
        stored = server.get("test-instance", local.id)
        assert stored is not None and stored.task.salience is True

        _apply_sync_task_to_local(stored.task, task_store)
        loaded = task_store.get(local.id)
        assert loaded.salience is True
        assert loaded.salient_until == until

    def test_legacy_payload_is_not_salient(self):
        legacy = SyncTask.model_validate(
            {"id": "x", "title": "old", "status": "open", "created_at": NOW, "updated_at": NOW}
        )
        assert legacy.salience is False and legacy.salient_until is None


class TestCli:
    def _add(self, runner, *extra):
        result = runner.invoke(
            cli, ["--json", "memory", "add", "A fact", "--non-interactive", *extra]
        )
        assert result.exit_code == 0, result.output
        mem_id = json.loads(result.output.strip())["id"]
        return json.loads(runner.invoke(cli, ["--json", "task", "get", mem_id]).output.strip())

    def test_salient_default_and_window(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as tmpdir:
            (Path(tmpdir) / ".hopper" / "tasks").mkdir(parents=True)
            before = datetime.now(UTC)

            rec = self._add(runner, "--salient")
            until = datetime.fromisoformat(rec["salient_until"])
            assert rec["salience"] is True
            assert before + timedelta(days=3) <= until <= datetime.now(UTC) + timedelta(days=3)

            rec = self._add(runner, "--salient-for", "12h")  # implies --salient
            until = datetime.fromisoformat(rec["salient_until"])
            assert rec["salience"] is True
            assert until <= datetime.now(UTC) + timedelta(hours=12)

            rec = self._add(runner)
            assert rec["salience"] is False and rec["salient_until"] is None

            result = runner.invoke(cli, ["task", "get", rec["id"]])
            assert "Salience:" not in result.output

    def test_get_renders_salience(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as tmpdir:
            (Path(tmpdir) / ".hopper" / "tasks").mkdir(parents=True)
            rec = self._add(runner, "--salient-for", "1d")
            result = runner.invoke(cli, ["task", "get", rec["id"]])
            assert "Salience: salient (until" in result.output

    def test_bad_window_rejected(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as tmpdir:
            (Path(tmpdir) / ".hopper" / "tasks").mkdir(parents=True)
            result = runner.invoke(
                cli, ["memory", "add", "A fact", "--salient-for", "soon", "--non-interactive"]
            )
            assert result.exit_code != 0
            assert "salience window" in result.output


class TestReinforcement:
    def test_extends_to_now_plus_default_window(self):
        rec = {"salience": True, "salient_until": (NOW + timedelta(hours=1)).isoformat()}
        assert reinforced_salient_until(rec, NOW) == NOW + DEFAULT_SALIENCE_WINDOW

    def test_never_shortens(self):
        rec = {"salience": True, "salient_until": (NOW + timedelta(weeks=2)).isoformat()}
        assert reinforced_salient_until(rec, NOW) is None

    def test_unflagged_and_lapsed_are_not_reinforced(self):
        assert reinforced_salient_until({"salience": False}, NOW) is None
        lapsed = {"salience": True, "salient_until": (NOW - timedelta(hours=1)).isoformat()}
        assert reinforced_salient_until(lapsed, NOW) is None

    def test_custom_window(self):
        rec = {"salience": True, "salient_until": (NOW + timedelta(hours=1)).isoformat()}
        got = reinforced_salient_until(rec, NOW, window=timedelta(hours=6))
        assert got == NOW + timedelta(hours=6)


class TestReinforcementWiring:
    @pytest.fixture
    def client(self, tmp_path):
        from hopper.cli.local_client import LocalClient

        return LocalClient(tmp_path)

    def _salient(self, client, hours=1, **extra):
        until = datetime.now(UTC) + timedelta(hours=hours)
        return client.create_task(
            {
                "title": "m",
                "kind": "memory",
                "salience": True,
                "salient_until": until.isoformat(),
                **extra,
            }
        )

    def _until(self, client, tid):
        return client.task_store.get(tid).salient_until

    def test_note_reinforces_salient_record(self, client):
        rec = self._salient(client)
        before = datetime.now(UTC)
        client.add_task_note(rec["id"], "still relevant", author="claude:x")
        assert self._until(client, rec["id"]) >= before + DEFAULT_SALIENCE_WINDOW

    def test_note_does_not_shorten_or_flag(self, client):
        long = self._salient(client, hours=24 * 14)
        original = self._until(client, long["id"])
        client.add_task_note(long["id"], "n")
        assert self._until(client, long["id"]) == original

        plain = client.create_task({"title": "m", "kind": "memory"})
        client.add_task_note(plain["id"], "n")
        loaded = client.task_store.get(plain["id"])
        assert loaded.salience is False and loaded.salient_until is None

    def test_citing_memory_reinforces_on_create(self, client):
        rec = self._salient(client)
        before = datetime.now(UTC)
        client.create_task(
            {"title": "cites", "kind": "memory", "evidence": [f"task:{rec['id'][:6]}"]}
        )
        assert self._until(client, rec["id"]) >= before + DEFAULT_SALIENCE_WINDOW

    def test_non_memory_citation_does_not_reinforce(self, client):
        rec = self._salient(client)
        original = self._until(client, rec["id"])
        client.create_task({"title": "task", "evidence": [rec["id"]]})
        assert self._until(client, rec["id"]) == original

    def test_update_adding_citation_reinforces(self, client):
        rec = self._salient(client)
        other = client.create_task({"title": "other", "kind": "memory"})
        original = self._until(client, rec["id"])
        client.update_task(other["id"], {"how_known": "x"})  # no evidence change
        assert self._until(client, rec["id"]) == original

        before = datetime.now(UTC)
        client.update_task(other["id"], {"evidence": [rec["id"]]})
        assert self._until(client, rec["id"]) >= before + DEFAULT_SALIENCE_WINDOW

    def test_unknown_citation_is_ignored(self, client):
        client.create_task({"title": "cites", "kind": "memory", "evidence": ["t00000000"]})


class TestUpdateAndBriefPaths:
    @pytest.fixture
    def client(self, tmp_path):
        from hopper.cli.local_client import LocalClient

        return LocalClient(tmp_path)

    def test_update_flag_without_expiry_uses_default_window(self, client):
        rec = client.create_task({"title": "m", "kind": "memory"})
        before = datetime.now(UTC)
        client.update_task(rec["id"], {"salience": True})
        loaded = client.task_store.get(rec["id"])
        assert loaded.salience is True
        assert loaded.salient_until >= before + DEFAULT_SALIENCE_WINDOW

        explicit = datetime(2030, 1, 1, tzinfo=UTC)
        client.update_task(rec["id"], {"salience": True, "salient_until": explicit.isoformat()})
        assert client.task_store.get(rec["id"]).salient_until == explicit

        # Re-flagging a live flag keeps its expiry; clearing works.
        client.update_task(rec["id"], {"salience": True})
        assert client.task_store.get(rec["id"]).salient_until == explicit
        client.update_task(rec["id"], {"salience": False, "salient_until": None})
        loaded = client.task_store.get(rec["id"])
        assert loaded.salience is False and loaded.salient_until is None

    def test_brief_path_preserves_memory_fields(self, client):
        parent = client.create_task({"title": "parent"})
        until = (NOW + timedelta(days=30)).isoformat()
        rec = client.create_task_with_brief(
            {
                "title": "m",
                "kind": "memory",
                "subject": "project:hopper",
                "scope": "repo",
                "provenance": "observation",
                "evidence": ["src/x.py", "abc1234"],
                "how_known": "read in code",
                "salience": True,
                "salient_until": until,
                "parent_id": parent["id"][:6],
            },
            "# Full brief\n\nBody.",
        )
        loaded = client.task_store.get(rec["id"])
        assert loaded.description == "# Full brief\n\nBody."
        assert loaded.status == "open"
        assert loaded.kind == "memory"
        assert (loaded.subject, loaded.scope, loaded.provenance) == (
            "project:hopper",
            "repo",
            "observation",
        )
        assert loaded.evidence == ["src/x.py", "abc1234"]
        assert loaded.how_known == "read in code"
        assert loaded.salience is True and loaded.salient_until.isoformat() == until
        assert loaded.parent_id == parent["id"]

    def test_cli_brief_file_keeps_memory_fields(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as tmpdir:
            (Path(tmpdir) / ".hopper" / "tasks").mkdir(parents=True)
            (Path(tmpdir) / "brief.md").write_text("# Brief\n")
            result = runner.invoke(
                cli,
                [
                    "--json",
                    "task",
                    "add",
                    "M",
                    "--brief-file",
                    "brief.md",
                    "--kind",
                    "memory",
                    "--evidence",
                    "src/x.py",
                    "--how-known",
                    "told by user",
                    "--provenance",
                    "conversation",
                    "--non-interactive",
                ],
            )
            assert result.exit_code == 0, result.output
            rec = json.loads(result.output.strip())
            assert rec["kind"] == "memory"
            assert rec["evidence"] == ["src/x.py"]
            assert rec["how_known"] == "told by user"
            assert rec["provenance"] == "conversation"
            assert rec["description"] == "# Brief\n"
