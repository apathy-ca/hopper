"""reclassify must not rewrite records that belong to another instance's shard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from hopper.cli.commands.doctor import legacy_records
from hopper.cli.local_client import LocalClient
from hopper.cli.main import cli
from hopper.storage.tasks import LocalTask


@pytest.fixture
def board():
    runner = CliRunner()
    with runner.isolated_filesystem() as tmp:
        store = Path(tmp) / ".hopper"
        (store / "tasks").mkdir(parents=True)
        (store / "config.yaml").write_text(
            yaml.safe_dump({"instance": {"id": "mine", "name": "mine"}})
        )
        client = LocalClient(store)
        ids = {}
        for label, instance in (("own", "mine"), ("foreign", ".other")):
            t = LocalTask.create(title=label, tags=["gpu-job"])
            t.instance = instance
            client.task_store.save(t)
            ids[label] = t.id
        client.close()
        yield runner, store, ids


def _kinds(store: Path) -> dict[str, str]:
    c = LocalClient(store)
    try:
        return {t.id: t.kind for t in c.task_store.list()}
    finally:
        c.close()


def test_dry_run_reports_and_skips_foreign(board):
    runner, _, ids = board
    r = runner.invoke(cli, ["--json", "maintenance", "reclassify"])
    out = json.loads(r.output[r.output.index("{") :])
    assert out["would_change"] == 1
    assert out["skipped_foreign"] == [ids["foreign"]]


def test_apply_only_touches_own_records(board):
    runner, store, ids = board
    assert runner.invoke(cli, ["maintenance", "reclassify", "--apply"]).exit_code == 0
    kinds = _kinds(store)
    assert kinds[ids["own"]] == "job"
    assert kinds[ids["foreign"]] == "task"


def test_include_foreign_opts_back_in(board):
    runner, store, ids = board
    runner.invoke(cli, ["maintenance", "reclassify", "--apply", "--include-foreign"])
    assert set(_kinds(store).values()) == {"job"}


def test_doctor_ignores_foreign_legacy_records(board):
    _, store, ids = board
    c = LocalClient(store)
    records = c.task_store.list()
    c.close()
    assert [r.id for r, _ in legacy_records(records, "mine")] == [ids["own"]]
    assert len(legacy_records(records, None)) == 2  # no own instance known: no filtering
