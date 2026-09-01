"""Regression test for the OwnerRegistry multi-process race (auditor
finding #5 on PR owner-identity-instance-discovery): 'hopper server start
--workers N>1' spawns separate OS processes sharing one storage_path with
no other coordination. Before the flock fix, two concurrent link_did calls
for the same owner could race — both read the same linked_dids, both
append their own DID in memory, second write wins, the first DID silently
fails to link even though its own redemption reported success.

Uses real OS processes (multiprocessing), not threads, since the race is
specifically about separate processes with independent memory — threads
sharing the GIL wouldn't reproduce it.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from hopper.upstream.storage import OwnerRegistry

N_WORKERS = 8


def _link_one_did(storage_path: str, worker_index: int) -> None:
    registry = OwnerRegistry(Path(storage_path))
    registry.link_did("james", f"did:key:zWorker{worker_index}")


def test_concurrent_link_did_from_separate_processes_loses_no_writes(
    tmp_path: Path,
) -> None:
    registry = OwnerRegistry(tmp_path)
    registry.create("james", "james@eigan.ai")

    processes = [
        multiprocessing.Process(target=_link_one_did, args=(str(tmp_path), i))
        for i in range(N_WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    owner = registry.get("james")
    assert owner is not None
    assert sorted(owner.linked_dids) == sorted(f"did:key:zWorker{i}" for i in range(N_WORKERS))


def _create_owner(storage_path: str, index: int, results_path: str) -> None:
    registry = OwnerRegistry(Path(storage_path))
    owner, message = registry.create(f"owner{index}", f"owner{index}@eigan.ai")
    with open(results_path, "a") as f:
        f.write(f"{index}:{owner is not None}\n")


def test_concurrent_create_from_separate_processes_all_succeed(tmp_path: Path) -> None:
    """Distinct owners, no conflict — just proves the lock doesn't cause
    false failures or corrupt unrelated files under concurrent access."""
    results_path = tmp_path / "results.txt"
    results_path.write_text("")

    processes = [
        multiprocessing.Process(target=_create_owner, args=(str(tmp_path), i, str(results_path)))
        for i in range(N_WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = results_path.read_text().strip().splitlines()
    assert len(lines) == N_WORKERS
    assert all(line.endswith(":True") for line in lines)

    registry = OwnerRegistry(tmp_path)
    assert len(registry.list_all()) == N_WORKERS
