"""Regression test for the DIDRegistry race (auditor finding on the
second review pass of PR owner-identity-instance-discovery, "New in this
round"): OwnerRegistry/OrgRegistry got flock-guarded critical sections,
but DIDRegistry itself — mutated on nearly every /sync call via
register_or_get — didn't. Worse than the Owner/Org case: DIDRegistry
loads its whole namespace->did->status map into memory once at process
start and mutates that in-memory copy incrementally, so even a lock
around the final write wouldn't be enough without also reloading fresh
from disk immediately before mutating — two workers each holding a stale
in-memory snapshot would still silently clobber each other's writes one
at a time, lock or no lock, unless each write starts from a fresh read.

Real OS processes (multiprocessing), matching the Owner/Org/Invite
concurrency tests' approach.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from hopper.upstream.storage import DIDRegistry, DIDStatus

N_WORKERS = 8


def _bootstrap_admin(storage_path: str) -> None:
    DIDRegistry(Path(storage_path)).register_or_get("did:key:zAdmin", "some-namespace")


def _register_one(storage_path: str, worker_index: int) -> None:
    registry = DIDRegistry(Path(storage_path))
    registry.register_or_get(f"did:key:zWorker{worker_index}", "eigan")


def test_concurrent_register_from_separate_processes_loses_no_registration(
    tmp_path: Path,
) -> None:
    _bootstrap_admin(str(tmp_path))

    processes = [
        multiprocessing.Process(target=_register_one, args=(str(tmp_path), i))
        for i in range(N_WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    registry = DIDRegistry(tmp_path)
    for i in range(N_WORKERS):
        did = f"did:key:zWorker{i}"
        assert registry.get_status(did, "eigan") == DIDStatus.PENDING, (
            f"{did}'s PENDING registration was lost — a concurrent worker's write "
            "silently clobbered it"
        )


def _approve_one(storage_path: str, worker_index: int) -> None:
    registry = DIDRegistry(Path(storage_path))
    registry.approve(f"did:key:zWorker{worker_index}", "eigan", by_did="did:key:zAdmin")


def test_concurrent_approve_from_separate_processes_loses_no_grant(tmp_path: Path) -> None:
    _bootstrap_admin(str(tmp_path))
    # Pre-register every worker DID so approve() only has to update status,
    # isolating this test to the set_status() write path specifically.
    registry = DIDRegistry(tmp_path)
    for i in range(N_WORKERS):
        registry.register_or_get(f"did:key:zWorker{i}", "eigan", owner_id="nobody")

    processes = [
        multiprocessing.Process(target=_approve_one, args=(str(tmp_path), i))
        for i in range(N_WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    registry = DIDRegistry(tmp_path)
    for i in range(N_WORKERS):
        did = f"did:key:zWorker{i}"
        assert registry.is_authorized(did, "eigan") is True, (
            f"{did}'s approval was lost — a concurrent worker's write silently " "clobbered it"
        )
