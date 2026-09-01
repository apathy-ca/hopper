"""Regression test for the InviteStore race (auditor finding #A on the
second review pass of PR owner-identity-instance-discovery): redeem() had
no lock, so two concurrent redemptions of the same (often max_uses=1)
invite could both read uses=0, both pass validation, and both write —
second write wins, silently granting a single-use invite to two separate
identities with neither aware the other happened.

Real OS processes (multiprocessing), matching
test_owner_registry_concurrency.py's approach — the race is specifically
about separate processes with independent memory, not something threads
sharing the GIL would reproduce.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from hopper.upstream.storage import InviteStore

N_WORKERS = 8


def _redeem_one(storage_path: str, token: str, worker_index: int, results_path: str) -> None:
    store = InviteStore(Path(storage_path))
    invite, message = store.redeem(token, by_did=f"did:key:zWorker{worker_index}")
    with open(results_path, "a") as f:
        f.write(f"{worker_index}:{invite is not None}\n")


def test_concurrent_redeem_of_a_single_use_invite_grants_exactly_once(
    tmp_path: Path,
) -> None:
    store = InviteStore(tmp_path)
    token, invite = store.create(
        issued_by="did:key:zAdmin", expires_at=None, max_uses=1, namespace="eigan"
    )
    assert invite.uses == 0

    results_path = tmp_path / "results.txt"
    results_path.write_text("")

    processes = [
        multiprocessing.Process(
            target=_redeem_one, args=(str(tmp_path), token, i, str(results_path))
        )
        for i in range(N_WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = results_path.read_text().strip().splitlines()
    successes = [line for line in lines if line.endswith(":True")]
    assert len(successes) == 1, f"expected exactly 1 successful redemption, got: {lines}"

    final = store.get(token)
    assert final is not None
    assert final.uses == 1
    assert len(final.redeemed_by) == 1


def test_concurrent_redeem_of_a_five_use_invite_grants_exactly_five_times(
    tmp_path: Path,
) -> None:
    store = InviteStore(tmp_path)
    token, _ = store.create(
        issued_by="did:key:zAdmin", expires_at=None, max_uses=5, namespace="eigan"
    )

    results_path = tmp_path / "results.txt"
    results_path.write_text("")

    processes = [
        multiprocessing.Process(
            target=_redeem_one, args=(str(tmp_path), token, i, str(results_path))
        )
        for i in range(N_WORKERS)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = results_path.read_text().strip().splitlines()
    successes = [line for line in lines if line.endswith(":True")]
    assert len(successes) == 5

    final = store.get(token)
    assert final is not None
    assert final.uses == 5
    assert len(final.redeemed_by) == 5


class TestUnredeem:
    def test_unredeem_gives_the_slot_back(self, tmp_path: Path) -> None:
        store = InviteStore(tmp_path)
        token, _ = store.create(
            issued_by="did:key:zAdmin", expires_at=None, max_uses=1, namespace="eigan"
        )
        store.redeem(token, by_did="did:key:zAlice")
        assert store.get(token).uses == 1  # type: ignore[union-attr]

        store.unredeem(token, by_did="did:key:zAlice")

        after = store.get(token)
        assert after is not None
        assert after.uses == 0
        assert "did:key:zAlice" not in after.redeemed_by

    def test_after_unredeem_the_token_is_usable_again(self, tmp_path: Path) -> None:
        """The actual point: a failed downstream grant (link_did losing a
        race, an owner already existing) shouldn't permanently burn an
        often-single-use token."""
        store = InviteStore(tmp_path)
        token, _ = store.create(
            issued_by="did:key:zAdmin", expires_at=None, max_uses=1, namespace="eigan"
        )
        store.redeem(token, by_did="did:key:zAlice")
        store.unredeem(token, by_did="did:key:zAlice")

        invite, message = store.redeem(token, by_did="did:key:zBob")

        assert invite is not None
        assert message == "redeemed"

    def test_unredeem_on_a_did_that_never_redeemed_is_a_silent_no_op(self, tmp_path: Path) -> None:
        store = InviteStore(tmp_path)
        token, _ = store.create(
            issued_by="did:key:zAdmin", expires_at=None, max_uses=1, namespace="eigan"
        )
        store.redeem(token, by_did="did:key:zAlice")

        store.unredeem(token, by_did="did:key:zSomeoneWhoNeverRedeemed")

        # Alice's redemption is untouched.
        after = store.get(token)
        assert after.uses == 1  # type: ignore[union-attr]
        assert "did:key:zAlice" in after.redeemed_by  # type: ignore[union-attr]

    def test_unredeem_on_a_nonexistent_token_does_not_raise(self, tmp_path: Path) -> None:
        store = InviteStore(tmp_path)
        store.unredeem("hinv_does_not_exist", by_did="did:key:zAlice")  # must not raise


def _revoke_repeatedly(storage_path: str, token_hash_prefix: str, results_path: str) -> None:
    store = InviteStore(Path(storage_path))
    success, message = store.revoke(token_hash_prefix)
    with open(results_path, "a") as f:
        f.write(f"revoke:{success}\n")


def _redeem_repeatedly(storage_path: str, token: str, worker_index: int, results_path: str) -> None:
    store = InviteStore(Path(storage_path))
    invite, message = store.redeem(token, by_did=f"did:key:zRacer{worker_index}")
    with open(results_path, "a") as f:
        f.write(f"redeem:{invite is not None}\n")


def test_concurrent_revoke_and_redeem_never_leaves_a_grant_after_a_reported_revoke(
    tmp_path: Path,
) -> None:
    """The exact bad outcome the unlocked revoke() could produce: revoke()
    unlink()s the file while a concurrent redeem() has already read the
    old (pre-delete) state and then re-creates the file via _save() with
    the attacker's redemption recorded — both calls report success, and
    the 'revoked' invite is still redeemable. With both locked through the
    same InviteStore.invites_dir/.lock, whichever call actually wins the
    race, the end state must be self-consistent: either the file is gone
    (revoke fully won) or it exists holding exactly the redemptions that
    happened-before the revoke — never a resurrected file after a
    revoke() that reported success.
    """
    store = InviteStore(tmp_path)
    token, invite = store.create(
        issued_by="did:key:zAdmin", expires_at=None, max_uses=8, namespace="eigan"
    )
    token_hash_prefix = invite.token_hash[:16]

    results_path = tmp_path / "results.txt"
    results_path.write_text("")

    processes = [
        multiprocessing.Process(
            target=_redeem_repeatedly, args=(str(tmp_path), token, i, str(results_path))
        )
        for i in range(N_WORKERS)
    ]
    processes.append(
        multiprocessing.Process(
            target=_revoke_repeatedly, args=(str(tmp_path), token_hash_prefix, str(results_path))
        )
    )
    for p in processes:
        p.start()
    for p in processes:
        p.join(timeout=30)
        assert p.exitcode == 0

    lines = results_path.read_text().strip().splitlines()
    revoke_succeeded = any(line == "revoke:True" for line in lines)
    final = store.get(token)

    if revoke_succeeded:
        # A revoke that reports success must actually mean the invite is
        # gone — not silently resurrected by a racing redeem.
        assert final is None, "revoke() reported success but the invite still exists"
