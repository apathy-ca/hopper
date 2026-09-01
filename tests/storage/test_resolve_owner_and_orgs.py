"""Tests for server._resolve_owner_and_orgs — the single choke point
every server.py endpoint resolves a caller's (or invite issuer's) owner
through (Owner-Identity-and-Instance-Discovery-Plan.md, round 5 on PR
owner-identity-instance-discovery).

Round 4 gated OwnerRegistry's negative-cache writes on cache_negative,
but wired it as an opt-in parameter at exactly one call site (sync()) —
every other endpoint (/me, /admin/approve, /admin/revoke, the org
endpoints, the invite endpoints) still defaulted to caching negatives
before its own authorization check succeeded, reopening the same
pre-auth disk-exhaustion vector through seven other doors. Round 5 moved
the decision inside this one function instead, so every caller gets it
automatically. That round also found the gate itself (has any DIDRegistry
record) was satisfiable for free — PENDING costs an attacker nothing — so
it's now DIDRegistry.is_established (APPROVED/APPROVER only, not
self-grantable) instead.

These tests exercise the function directly against a real UpstreamStorage
on disk — no HTTP/FastAPI needed, since it's a plain function taking
storage and a DID.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hopper.upstream.server import _resolve_owner_and_orgs
from hopper.upstream.storage import UpstreamStorage

ADMIN = "did:key:zAdmin"


@pytest.fixture
def storage(tmp_path: Path) -> UpstreamStorage:
    s = UpstreamStorage(tmp_path)
    s.did_registry.register_or_get(ADMIN, "bootstrap")  # first DID becomes admin
    return s


def _did_index_files(storage: UpstreamStorage) -> list[Path]:
    return list(storage.owner_registry.did_index_dir.glob("*.json"))


class TestCentralGating:
    def test_never_established_did_plants_no_file_even_across_repeated_calls(
        self, storage: UpstreamStorage
    ) -> None:
        """The exact round-5 finding: a synthetic DID that only ever lands
        PENDING (free, one signed request per attempt, no approval)
        must not earn a permanent negative-cache file no matter how many
        times it's resolved — not even on a *second* call, once
        PENDING alone stopped counting as 'established'."""
        attacker_did = "did:key:zAttacker"

        for _ in range(5):
            # Each call mirrors what a real endpoint does: resolve, then
            # (elsewhere) register_or_get, which is what actually creates
            # the PENDING record an attacker gets for free.
            _resolve_owner_and_orgs(storage, attacker_did)
            storage.did_registry.register_or_get(attacker_did, "eigan")

        assert _did_index_files(storage) == []

    def test_spamming_many_synthetic_dids_plants_no_files(self, storage: UpstreamStorage) -> None:
        for i in range(20):
            did = f"did:key:zSpam{i}"
            _resolve_owner_and_orgs(storage, did)
            storage.did_registry.register_or_get(did, "eigan")
            _resolve_owner_and_orgs(storage, did)  # a returning call too

        assert _did_index_files(storage) == []

    def test_a_genuinely_approved_did_does_earn_the_cache_speedup(
        self, storage: UpstreamStorage
    ) -> None:
        """The negative-caching optimization this all sits on top of
        still works for the case it was built for — a real, approved
        device."""
        real_did = "did:key:zRealDevice"
        storage.did_registry.approve(real_did, "eigan", by_did=ADMIN)

        _resolve_owner_and_orgs(storage, real_did)

        assert len(_did_index_files(storage)) == 1

    def test_owner_linked_did_resolves_correctly_regardless_of_established_status(
        self, storage: UpstreamStorage
    ) -> None:
        """A DID linked to a real owner always resolves to that owner —
        cache_negative only governs the *negative*-result case; this is
        a positive one and must never be affected by it."""
        storage.owner_registry.create("james", "james@eigan.ai")
        storage.owner_registry.link_did("james", "did:key:zDevice")

        owner_id, org_ids = _resolve_owner_and_orgs(storage, "did:key:zDevice")

        assert owner_id == "james"

    def test_admin_resolves_with_no_owner_and_plants_nothing_unexpected(
        self, storage: UpstreamStorage
    ) -> None:
        owner_id, org_ids = _resolve_owner_and_orgs(storage, ADMIN)

        assert owner_id is None
        assert org_ids == []
        # Admin is_established, so this *does* cache — matches "no new
        # attack surface for the one real admin identity" reasoning.
        assert len(_did_index_files(storage)) == 1


class TestOrgIdsIncluded:
    def test_resolves_orgs_the_owner_belongs_to(self, storage: UpstreamStorage) -> None:
        storage.owner_registry.create("james", "james@eigan.ai")
        storage.owner_registry.link_did("james", "did:key:zDevice")
        storage.org_registry.create("eigan-corp", "Eigan Corp")
        storage.org_registry.add_member("eigan-corp", "james")

        owner_id, org_ids = _resolve_owner_and_orgs(storage, "did:key:zDevice")

        assert owner_id == "james"
        assert org_ids == ["eigan-corp"]
