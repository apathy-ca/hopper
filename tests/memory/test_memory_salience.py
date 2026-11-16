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
