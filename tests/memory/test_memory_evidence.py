"""Tests for the optional ``evidence`` field on memory records.

Covers classification/verification helpers, the markdown round-trip, every
sync hop, and ``hopper memory add --evidence``. The ``hopper doctor`` check
lives in tests/cli/test_doctor.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.main import cli
from hopper.memory.evidence import (
    COMMIT,
    FILE,
    TASK,
    UNKNOWN,
    URL,
    classify_evidence,
    find_missing_evidence,
)
from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore
from hopper.storage.tasks import LocalTask
from hopper.upstream.protocol import SyncTask
from hopper.upstream.storage import UpstreamStorage
from hopper.upstream.sync import _apply_sync_task_to_local, _local_task_to_sync_task

EVIDENCE = ["t1a2b3c4d", "src/hopper/upstream/sync.py:120", "commit:abc1234"]


@pytest.fixture
def task_store(tmp_path: Path) -> TaskMarkdownStore:
    storage = MarkdownStorage(StorageConfig.local(tmp_path))
    storage.initialize()
    return TaskMarkdownStore(storage)


class TestClassify:
    @pytest.mark.parametrize(
        ("raw", "kind", "value"),
        [
            ("t1a2b3c4d", TASK, "t1a2b3c4d"),
            ("task:t1a2", TASK, "t1a2"),
            ("abc1234", COMMIT, "abc1234"),
            ("commit:deadbeefcafe", COMMIT, "deadbeefcafe"),
            ("src/foo.py", FILE, "src/foo.py"),
            ("src/foo.py:42", FILE, "src/foo.py"),
            ("README.md:3-9", FILE, "README.md"),
            ("file:Makefile", FILE, "Makefile"),
            ("https://example.com/x.py", URL, "https://example.com/x.py"),
            ("observed in test run", UNKNOWN, "observed in test run"),
            ("", UNKNOWN, ""),
        ],
    )
    def test_classify(self, raw, kind, value):
        ref = classify_evidence(raw)
        assert (ref.kind, ref.value, ref.raw) == (kind, value, raw)


class TestFindMissing:
    def test_reports_only_demonstrably_missing(self, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "here.py").write_text("x")
        missing = find_missing_evidence(
            [
                "src/here.py:10",
                "src/gone.py",
                "t11111111",
                "t22222222",
                "task:t333",
                "abc1234",
                "https://example.com",
                "told by user",
            ],
            known_ids={"t11111111", "t33333333"},
            project_root=tmp_path,
            commit_exists=lambda sha: False,
        )
        assert missing == ["src/gone.py", "t22222222", "abc1234"]

    def test_unverifiable_things_are_skipped(self, tmp_path):
        # No project root -> relative paths skipped; no commit checker -> shas
        # skipped; checker that can't tell (None) -> skipped.
        assert (
            find_missing_evidence(["src/gone.py", "abc1234"], known_ids=[], project_root=None) == []
        )
        assert (
            find_missing_evidence(
                ["abc1234"], known_ids=[], project_root=tmp_path, commit_exists=lambda s: None
            )
            == []
        )

    def test_absolute_path_checked_without_project_root(self, tmp_path):
        gone = str(tmp_path / "nope.txt")
        assert find_missing_evidence([gone], known_ids=[], project_root=None) == [gone]


class TestStorage:
    def test_evidence_round_trips(self, task_store):
        mem = LocalTask.create(title="m", kind="memory", evidence=EVIDENCE)
        task_store.create(mem)
        loaded = task_store.get(mem.id)
        assert loaded is not None
        assert loaded.evidence == EVIDENCE

    def test_ordinary_task_has_no_evidence_frontmatter(self):
        assert "evidence" not in LocalTask.create(title="Fix the bug").to_frontmatter()


class TestSync:
    def test_evidence_survives_every_hop(self, tmp_path, task_store):
        local = LocalTask.create(title="m", status="open", kind="memory", evidence=EVIDENCE)
        local.instance = "test-instance"

        wire = _local_task_to_sync_task(local)
        assert wire.model_dump(mode="json")["evidence"] == EVIDENCE

        server = UpstreamStorage(tmp_path / "server")
        ok, _ = server.put(wire, from_did="did:key:test")
        assert ok
        stored = server.get("test-instance", local.id)
        assert stored is not None and stored.task.evidence == EVIDENCE

        _apply_sync_task_to_local(stored.task, task_store)
        assert task_store.get(local.id).evidence == EVIDENCE

        # Update path: a newer pulled version replaces the local list.
        stored.task.evidence = ["t1a2b3c4d"]
        stored.task.updated_at = stored.task.updated_at + timedelta(seconds=5)
        _apply_sync_task_to_local(stored.task, task_store)
        assert task_store.get(local.id).evidence == ["t1a2b3c4d"]

    def test_legacy_payload_defaults_to_empty(self):
        now = datetime.now(UTC)
        legacy = SyncTask.model_validate(
            {"id": "x", "title": "old", "status": "open", "created_at": now, "updated_at": now}
        )
        assert legacy.evidence == []


class TestCli:
    def test_memory_add_evidence_repeatable(self):
        runner = CliRunner()
        with runner.isolated_filesystem() as tmpdir:
            (Path(tmpdir) / ".hopper" / "tasks").mkdir(parents=True)
            result = runner.invoke(
                cli,
                [
                    "--json",
                    "memory",
                    "add",
                    "Sync batches at 512KB",
                    "--evidence",
                    "src/hopper/upstream/sync.py",
                    "-e",
                    "t1a2b3c4d",
                    "--non-interactive",
                ],
            )
            assert result.exit_code == 0, result.output
            mem_id = json.loads(result.output.strip())["id"]

            result = runner.invoke(cli, ["--json", "task", "get", mem_id])
            assert result.exit_code == 0, result.output
            rec = json.loads(result.output.strip())
            assert rec["evidence"] == ["src/hopper/upstream/sync.py", "t1a2b3c4d"]

            result = runner.invoke(cli, ["task", "get", mem_id])
            assert "Evidence:" in result.output
            assert "t1a2b3c4d" in result.output
