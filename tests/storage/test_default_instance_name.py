"""New project stores are named after the project, not ".hopper"."""

from pathlib import Path

from hopper.cli.local_client import LocalClient
from hopper.storage.base import StorageConfig


def test_project_store_named_after_project(tmp_path: Path) -> None:
    store = tmp_path / "my-project" / ".hopper"
    store.mkdir(parents=True)
    cfg = StorageConfig.local(store)
    assert cfg.instance_id == cfg.instance_name == "my-project"


def test_initialised_config_persists_project_name(tmp_path: Path) -> None:
    store = tmp_path / "my-project" / ".hopper"
    store.mkdir(parents=True)
    LocalClient(store).close()
    assert "id: my-project" in (store / "config.yaml").read_text()


def test_explicit_and_existing_names_win(tmp_path: Path) -> None:
    store = tmp_path / "proj" / ".hopper"
    store.mkdir(parents=True)
    assert StorageConfig.local(store, instance_name="custom").instance_id == "custom"
    (store / "config.yaml").write_text("instance:\n  id: saved\n")
    assert StorageConfig.local(store).instance_id == "saved"


def test_global_store_name_unchanged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    store = Path.home() / ".hopper"
    store.mkdir()
    assert StorageConfig.local(store).instance_id == ".hopper"


def test_non_dot_hopper_dir_uses_its_own_name(tmp_path: Path) -> None:
    store = tmp_path / "somewhere"
    store.mkdir()
    assert StorageConfig.local(store).instance_id == "somewhere"
