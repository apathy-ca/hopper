"""Tests for the optional ``how_known`` field on memory records.

Covers the markdown round-trip, every sync hop, ``hopper memory add
--how-known`` + ``hopper task get`` rendering, and the agent-file guidance.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.main import cli
from hopper.storage import MarkdownStorage, StorageConfig, TaskMarkdownStore
from hopper.storage.tasks import LocalTask
from hopper.upstream.protocol import SyncTask
from hopper.upstream.storage import UpstreamStorage
from hopper.upstream.sync import _apply_sync_task_to_local, _local_task_to_sync_task

HOW = "observed in test run"


@pytest.fixture
def task_store(tmp_path: Path) -> TaskMarkdownStore:
    storage = MarkdownStorage(StorageConfig.local(tmp_path))
    storage.initialize()
    return TaskMarkdownStore(storage)


def test_how_known_round_trips(task_store):
    mem = LocalTask.create(title="m", kind="memory", how_known=HOW)
    task_store.create(mem)
    assert task_store.get(mem.id).how_known == HOW


def test_ordinary_task_has_no_how_known_frontmatter():
    assert "how_known" not in LocalTask.create(title="Fix the bug").to_frontmatter()


def test_how_known_survives_every_sync_hop(tmp_path, task_store):
    local = LocalTask.create(title="m", status="open", kind="memory", how_known=HOW)
    local.instance = "test-instance"

    wire = _local_task_to_sync_task(local)
    assert wire.model_dump(mode="json")["how_known"] == HOW

    server = UpstreamStorage(tmp_path / "server")
    ok, _ = server.put(wire, from_did="did:key:test")
    assert ok
    stored = server.get("test-instance", local.id)
    assert stored is not None and stored.task.how_known == HOW

    _apply_sync_task_to_local(stored.task, task_store)
    assert task_store.get(local.id).how_known == HOW


def test_legacy_payload_has_no_how_known():
    now = datetime.now(UTC)
    legacy = SyncTask.model_validate(
        {"id": "x", "title": "old", "status": "open", "created_at": now, "updated_at": now}
    )
    assert legacy.how_known is None


def test_memory_add_how_known_and_get_renders_it():
    runner = CliRunner()
    with runner.isolated_filesystem() as tmpdir:
        (Path(tmpdir) / ".hopper" / "tasks").mkdir(parents=True)
        result = runner.invoke(
            cli,
            ["--json", "memory", "add", "A fact", "--how-known", HOW, "--non-interactive"],
        )
        assert result.exit_code == 0, result.output
        mem_id = json.loads(result.output.strip())["id"]

        rec = json.loads(runner.invoke(cli, ["--json", "task", "get", mem_id]).output.strip())
        assert rec["how_known"] == HOW

        result = runner.invoke(cli, ["task", "get", mem_id])
        assert result.exit_code == 0, result.output
        assert f"How known: {HOW}" in result.output


def test_agent_files_tell_agents_to_record_how_known_and_evidence():
    from hopper.storage.knowledge import (
        AGENTS_MD_SECTION,
        GLOBAL_AGENTS_MD_SECTION,
        HOPPER_SKILL_CONTENT,
    )

    for text in (AGENTS_MD_SECTION, GLOBAL_AGENTS_MD_SECTION, HOPPER_SKILL_CONTENT):
        assert "--how-known" in text
        assert "--evidence" in text
