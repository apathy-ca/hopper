"""Tests for ``hopper doctor``. All state lives in tmp dirs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from hopper.cli.commands import doctor as doctor_mod
from hopper.cli.config import Config, LocalConfig, ProfileConfig, UpstreamConfig
from hopper.cli.local_client import LocalClient
from hopper.cli.main import Context, cli


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(tmp_path)
    # Never touch the network or the real checkout.
    monkeypatch.setattr(doctor_mod, "_tcp_reachable", lambda *a, **k: False)
    monkeypatch.setattr("hopper.utils.install.editable_install_status", lambda *a, **k: None)


@pytest.fixture
def storage(tmp_path: Path) -> Path:
    path = tmp_path / "proj" / ".hopper"
    path.mkdir(parents=True)
    LocalClient(path).close()  # initialise layout
    cfg = path / "config.yaml"
    data = yaml.safe_load(cfg.read_text()) or {}
    data["instance"] = {"id": "proj", "name": "proj", "scope": "personal"}  # matches the dir
    cfg.write_text(yaml.safe_dump(data))
    from hopper.storage.knowledge import write_agent_files

    write_agent_files(path.parent)  # current agent files, so a fresh project is clean
    return path


def make_ctx(storage: Path, tmp_path: Path, upstream: UpstreamConfig | None = None) -> Context:
    profile = ProfileConfig(
        mode="local",
        local=LocalConfig(path=storage, auto_detect_embedded=False),
        upstream=upstream or UpstreamConfig(),
    )
    cfg = Config(
        active_profile="p", profiles={"p": profile}, config_path=tmp_path / "home" / "config.yaml"
    )
    return Context(config=cfg)


def add_task(storage: Path, title="t", status="open", age_days=0.0, **kw) -> str:
    from hopper.storage.tasks import LocalTask

    client = LocalClient(storage)
    t = LocalTask.create(title=title)
    t.instance = client.config.instance_id  # as LocalClient.create_task does
    t.status = status
    for k, v in kw.items():
        setattr(t, k, v)
    client.task_store.save(t)
    if age_days:
        # Backdate updated_at in the file and rebuild the index.
        f = storage / "tasks" / f"{t.id}.md"
        text = f.read_text()
        old = t.updated_at
        assert old.isoformat() in text
        f.write_text(text.replace(old.isoformat(), (old - timedelta(days=age_days)).isoformat()))
        client.storage._rebuild_index()
    client.close()
    return t.id


def run(storage, tmp_path, *args, upstream=None):
    ctx = make_ctx(storage, tmp_path, upstream)
    return CliRunner().invoke(doctor_mod.doctor, list(args), obj=ctx)


def by_id(result) -> dict:
    return {c["id"]: c for c in json.loads(result.stdout)}


def test_registered_in_cli():
    assert "doctor" in cli.commands


def test_clean_board_exit_0_and_json_shape(storage, tmp_path):
    r = run(storage, tmp_path, "--json")
    assert r.exit_code == 0, r.output
    checks = json.loads(r.stdout)
    assert all(set(c) == {"id", "status", "message", "remedy"} for c in checks)
    assert by_id(r)["tasks.summary"]["message"].startswith("0 tasks")


def test_text_output_grouped(storage, tmp_path):
    add_task(storage)
    r = run(storage, tmp_path)
    for header in ("Config", "Sync", "Tasks", "Environment"):
        assert header in r.stdout
    assert "tasks: open=1" in r.stdout


def test_ownerless_stale_in_progress_warns(storage, tmp_path):
    tid = add_task(storage, status="in_progress", age_days=4)
    r = run(storage, tmp_path, "--json")
    assert r.exit_code == 1
    c = by_id(r)["tasks.in_progress"]
    assert c["status"] == "warn" and tid in c["message"]


def test_stale_days_threshold(storage, tmp_path):
    add_task(storage, status="in_progress", age_days=1, assigned_to="claude:x")
    assert by_id(run(storage, tmp_path, "--json"))["tasks.in_progress"]["status"] == "ok"
    r = run(storage, tmp_path, "--json", "--stale-days", "0.5")
    assert by_id(r)["tasks.in_progress"]["status"] == "warn"


def test_blocked_open_rot_generic_and_dangling(storage, tmp_path):
    add_task(storage, status="blocked", age_days=114, tags=["retired"])
    add_task(storage, status="open", age_days=160)
    add_task(storage, status="open", assigned_to="main")
    add_task(storage, status="open", depends_on=["tmissing0"])
    got = by_id(run(storage, tmp_path, "--json"))
    assert "114d" in got["tasks.blocked"]["message"]
    assert "retired" in got["tasks.blocked"]["message"]
    assert got["tasks.open_rot"]["status"] == "warn"
    assert got["tasks.generic_assignee"]["status"] == "warn"
    assert "tmissing0" in got["tasks.dangling_depends"]["message"]


def test_split_brain_detected_and_effective_target_reported(storage, tmp_path):
    cfg = storage / "config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["sync"] = {"enabled": False, "server_url": None}
    cfg.write_text(yaml.dump(data))
    key = tmp_path / "did.key"
    key.write_text("x")
    up = UpstreamConfig(server="https://hopper.example", enabled=True, did_key_path=str(key))
    c = by_id(run(storage, tmp_path, "--json", upstream=up))["config.sync_target"]
    assert c["status"] == "warn"
    assert "https://hopper.example" in c["message"]
    assert str(tmp_path / "home" / "config.yaml") in c["message"]


def test_missing_did_key_path_is_error_and_offline_is_warn(storage, tmp_path):
    up = UpstreamConfig(
        server="https://hopper.example", enabled=True, did_key_path=str(tmp_path / "nope.key")
    )
    r = run(storage, tmp_path, "--json", upstream=up)
    got = by_id(r)
    assert r.exit_code == 2
    assert got["config.paths"]["status"] == "error"
    assert got["sync.did_key"]["status"] == "error"
    assert got["sync.reachable"]["status"] == "warn"  # offline degrades to warn


def test_pending_changes_and_last_sync(storage, tmp_path):
    from hopper.upstream.did import generate_did_key

    key = tmp_path / "did.key"
    generate_did_key().save(key)
    add_task(storage)
    up = UpstreamConfig(server="https://hopper.example", enabled=True, did_key_path=str(key))
    got = by_id(run(storage, tmp_path, "--json", upstream=up))
    assert got["sync.did_key"]["status"] == "ok"
    assert got["sync.last_sync"]["status"] == "warn"  # never synced
    assert got["sync.pending"]["status"] == "warn"
    assert "1 local change" in got["sync.pending"]["message"]


def test_pending_changes_helper(storage):
    from hopper.upstream.sync import pending_changes

    add_task(storage)
    client = LocalClient(storage)
    count, size = pending_changes(client.task_store, storage / ".sync_state", "i")
    assert count == 1 and size > 0
    state = storage / ".sync_state_i"
    state.write_text(json.dumps({"last_sync": int(datetime.now(UTC).timestamp() * 1000) + 1000}))
    assert pending_changes(client.task_store, storage / ".sync_state", "i") == (0, 0)


def test_agent_files_drift_and_up_to_date(storage, tmp_path):
    proj = storage.parent
    (proj / "AGENTS.md").write_text("## Hopper - Persistent Memory\nold\n")
    got = by_id(run(storage, tmp_path, "--json"))
    assert got["environment.agent_files"]["status"] == "warn"

    from hopper.storage.knowledge import write_agent_files

    (proj / "AGENTS.md").unlink()
    write_agent_files(proj)
    got = by_id(run(storage, tmp_path, "--json"))
    assert got["environment.agent_files"]["status"] == "ok"


def test_legacy_records_counted(storage, tmp_path):
    add_task(storage, tags=["gpu-job"])
    c = by_id(run(storage, tmp_path, "--json"))["environment.legacy_records"]
    assert c["status"] == "warn" and "1 legacy" in c["message"]


def test_fix_releases_stale_annotates_and_reclassifies(storage, tmp_path):
    stale = add_task(storage, status="in_progress", age_days=4)
    owned = add_task(storage, status="in_progress", assigned_to="claude:live")
    blocked = add_task(storage, status="blocked", age_days=100)
    legacy = add_task(storage, tags=["gpu-job"])
    cfg = storage / "config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["sync"] = {"enabled": False, "server_url": None}
    cfg.write_text(yaml.dump(data))
    key = tmp_path / "did.key"
    key.write_text("x")
    up = UpstreamConfig(server="https://hopper.example", enabled=True, did_key_path=str(key))

    r = run(storage, tmp_path, "--fix", upstream=up)
    assert "FIX: releasing " + stale in r.stdout
    assert "FIX: annotating legacy sync" in r.stdout
    assert "FIX: reclassifying" in r.stdout

    client = LocalClient(storage)
    t = client.task_store.get(stale)
    assert t.status == "open" and t.assigned_to is None
    assert t.notes and t.notes[-1]["author"] == "hopper:doctor"
    assert client.task_store.get(owned).status == "in_progress"
    assert client.task_store.get(blocked).status == "blocked"  # never touched
    assert client.task_store.get(legacy).kind == "job"
    assert doctor_mod.LEGACY_SYNC_MARKER in yaml.safe_load(cfg.read_text())["sync"]


def test_fix_json_keeps_stdout_pure(storage, tmp_path):
    add_task(storage, status="in_progress", age_days=4)
    try:
        runner = CliRunner(mix_stderr=False)  # click < 8.2
    except TypeError:
        runner = CliRunner()  # click >= 8.2 always separates stderr
    r = runner.invoke(doctor_mod.doctor, ["--fix", "--json"], obj=make_ctx(storage, tmp_path))
    assert "FIX: releasing" in r.stderr
    json.loads(r.stdout)  # parses; FIX lines went to stderr


def test_missing_storage_degrades_to_error_not_crash(tmp_path):
    ctx = make_ctx(tmp_path / "missing", tmp_path)
    r = CliRunner().invoke(doctor_mod.doctor, ["--json"], obj=ctx)
    assert r.exit_code == 2
    assert by_id(r)["tasks.load"]["status"] == "error"


def _checks(storage, tmp_path, **kw):
    ctx = make_ctx(storage, tmp_path, **kw)
    r = CliRunner().invoke(doctor_mod.doctor, ["--json"], obj=ctx)
    return {c["id"]: c for c in json.loads(r.stdout)}


def test_instance_id_mismatch_warns(storage, tmp_path):
    cfg = storage / "config.yaml"
    data = yaml.safe_load(cfg.read_text()) if cfg.exists() else {}
    data["instance"] = {"id": "other-name", "name": "other-name"}
    cfg.write_text(yaml.safe_dump(data))
    assert _checks(storage, tmp_path)["config.instance"]["status"] == "warn"

    data["instance"] = {"id": storage.parent.name, "name": "x"}
    cfg.write_text(yaml.safe_dump(data))
    assert _checks(storage, tmp_path)["config.instance"]["status"] == "ok"


@pytest.mark.parametrize(
    ("remote", "status"),
    [("__CLI__", "ok"), ("0.0.9", "warn"), (None, "warn"), ("0.1.0", "warn")],
)
def test_server_version_check(remote, status):
    from unittest.mock import MagicMock, patch

    from hopper import __version__

    body = (
        {"status": "ok"}
        if remote is None
        else {"version": __version__ if remote == "__CLI__" else remote}
    )
    with patch("httpx.get", return_value=MagicMock(json=lambda: body)):
        assert doctor_mod._check_server_version("https://x").status == status


def test_server_version_unreachable_is_not_a_failure():
    from unittest.mock import patch

    with patch("httpx.get", side_effect=OSError("down")):
        assert doctor_mod._check_server_version("https://x").status == "ok"


def test_install_behind_warns(storage, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "hopper.utils.install.editable_install_status",
        lambda *a, **k: {
            "repo": "/r",
            "branch": "feat/x",
            "default_ref": "origin/master",
            "behind": 29,
        },
    )
    assert _checks(storage, tmp_path)["environment.install"]["status"] == "warn"
