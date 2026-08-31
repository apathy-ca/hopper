"""Tests for OwnerRegistry (Phase A of Owner-Identity-and-Instance-Discovery-Plan.md).

Phase A is pure CRUD — no authorization behavior. These tests cover the
registry in isolation: create/list/get, email aliasing (the multi-email
requirement — one owner, several addresses), DID linking, and the
conflicting-claim rejection the design doc leans toward for v1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hopper.upstream.storage import Owner, OwnerRegistry


@pytest.fixture
def registry(tmp_path: Path) -> OwnerRegistry:
    return OwnerRegistry(tmp_path)


class TestCreate:
    def test_create_returns_owner_with_primary_email(self, registry: OwnerRegistry) -> None:
        owner, message = registry.create("james", "james@eigan.ai")

        assert owner is not None
        assert owner.id == "james"
        assert owner.primary_email == "james@eigan.ai"
        assert owner.emails == ["james@eigan.ai"]
        assert owner.linked_dids == []
        assert message == "created"

    def test_create_persists_across_registry_instances(
        self, registry: OwnerRegistry, tmp_path: Path
    ) -> None:
        registry.create("james", "james@eigan.ai")

        reloaded = OwnerRegistry(tmp_path)
        found = reloaded.get("james")

        assert found is not None
        assert found.primary_email == "james@eigan.ai"

    def test_create_rejects_duplicate_id(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")

        owner, message = registry.create("james", "someone-else@example.com")

        assert owner is None
        assert "already exists" in message

    def test_create_rejects_email_already_claimed_by_another_owner(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")

        owner, message = registry.create("someone-else", "james@eigan.ai")

        assert owner is None
        assert "already linked to owner 'james'" in message


class TestEmailAliasing:
    """The concrete requirement from the design conversation: one owner
    (hopper.henrynet.ca's bootstrap identity) needs to resolve from *both*
    an @eigan.ai and an @henrynet.ca address."""

    def test_add_email_extends_the_alias_list(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@henrynet.ca")

        ok, message = registry.add_email("james", "james@eigan.ai")

        assert ok is True
        owner = registry.get("james")
        assert owner is not None
        assert owner.emails == ["james@henrynet.ca", "james@eigan.ai"]
        assert owner.primary_email == "james@henrynet.ca"  # unchanged — first stays default

    def test_get_by_email_resolves_either_alias_to_the_same_owner(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@henrynet.ca")
        registry.add_email("james", "james@eigan.ai")

        by_old = registry.get_by_email("james@henrynet.ca")
        by_new = registry.get_by_email("james@eigan.ai")

        assert by_old is not None
        assert by_new is not None
        assert by_old.id == by_new.id == "james"

    def test_add_email_rejects_email_already_on_this_owner(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")

        ok, message = registry.add_email("james", "james@eigan.ai")

        assert ok is False
        assert "already linked to 'james'" in message

    def test_add_email_rejects_email_claimed_by_a_different_owner(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.create("sarah", "sarah@eigan.ai")

        ok, message = registry.add_email("sarah", "james@eigan.ai")

        assert ok is False
        assert "different owner 'james'" in message

    def test_add_email_for_unknown_owner_fails(self, registry: OwnerRegistry) -> None:
        ok, message = registry.add_email("nobody", "x@example.com")

        assert ok is False
        assert "not found" in message

    def test_get_by_email_unknown_returns_none(self, registry: OwnerRegistry) -> None:
        assert registry.get_by_email("nobody@example.com") is None


class TestDidLinking:
    def test_link_did_adds_to_linked_dids(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")

        ok, message = registry.link_did("james", "did:key:zAbc123")

        assert ok is True
        owner = registry.get("james")
        assert owner is not None
        assert owner.linked_dids == ["did:key:zAbc123"]

    def test_get_by_did_finds_the_owning_owner(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")

        found = registry.get_by_did("did:key:zAbc123", cache_negative=True)

        assert found is not None
        assert found.id == "james"

    def test_get_by_did_unlinked_returns_none(self, registry: OwnerRegistry) -> None:
        assert registry.get_by_did("did:key:znotlinked", cache_negative=True) is None

    def test_link_did_rejects_conflicting_owner(self, registry: OwnerRegistry) -> None:
        """Design-doc leaning for the 'conflicting owner claims' open
        question: reject rather than silently reassign."""
        registry.create("james", "james@eigan.ai")
        registry.create("sarah", "sarah@eigan.ai")
        registry.link_did("james", "did:key:zShared")

        ok, message = registry.link_did("sarah", "did:key:zShared")

        assert ok is False
        assert "different owner 'james'" in message
        # James still holds it — the attempted reassignment had no effect.
        assert registry.get_by_did("did:key:zShared", cache_negative=True).id == "james"  # type: ignore[union-attr]

    def test_link_did_is_idempotent_error_not_duplicate(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")

        ok, message = registry.link_did("james", "did:key:zAbc123")

        assert ok is False
        assert "already linked" in message
        assert registry.get("james").linked_dids == ["did:key:zAbc123"]  # type: ignore[union-attr]

    def test_unlink_did_removes_it(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")

        ok, _ = registry.unlink_did("james", "did:key:zAbc123")

        assert ok is True
        assert registry.get("james").linked_dids == []  # type: ignore[union-attr]
        assert registry.get_by_did("did:key:zAbc123", cache_negative=True) is None

    def test_unlink_did_not_linked_fails(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")

        ok, message = registry.unlink_did("james", "did:key:znever-linked")

        assert ok is False
        assert "not linked" in message

    def test_after_unlink_did_can_be_relinked_to_a_different_owner(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.create("sarah", "sarah@eigan.ai")
        registry.link_did("james", "did:key:zShared")
        registry.unlink_did("james", "did:key:zShared")

        ok, _ = registry.link_did("sarah", "did:key:zShared")

        assert ok is True
        assert registry.get_by_did("did:key:zShared", cache_negative=True).id == "sarah"  # type: ignore[union-attr]


class TestListAll:
    def test_list_all_empty(self, registry: OwnerRegistry) -> None:
        assert registry.list_all() == []

    def test_list_all_returns_every_owner(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.create("sarah", "sarah@eigan.ai")

        owners = registry.list_all()

        assert {o.id for o in owners} == {"james", "sarah"}

    def test_list_all_order_is_deterministic_even_when_created_at_ties(
        self, registry: OwnerRegistry
    ) -> None:
        """created_at is millisecond resolution — two owners created in the
        same request burst can land on the same millisecond. Order must not
        depend on directory-iteration happenstance in that case."""
        registry.create("zed", "zed@eigan.ai")
        registry.create("amy", "amy@eigan.ai")

        first_call = [o.id for o in registry.list_all()]
        second_call = [o.id for o in registry.list_all()]

        assert first_call == second_call

    def test_list_all_does_not_pick_up_the_did_index_directory(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")  # writes a did_index/*.json file too

        owners = registry.list_all()

        assert len(owners) == 1
        assert owners[0].id == "james"


class TestGet:
    def test_get_unknown_owner_returns_none(self, registry: OwnerRegistry) -> None:
        assert registry.get("nobody") is None


class TestGetByDidSelfHealing:
    """get_by_did's fast path is a cache (did_index/{hash}.json), not the
    source of truth. These lock down that a stale or missing pointer never
    produces a wrong answer — only, at worst, one slower lookup."""

    def test_missing_pointer_falls_back_to_scan_and_heals(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")
        # Simulate data written before the did_index cache existed.
        registry._did_index_path("did:key:zAbc123").unlink()

        found = registry.get_by_did("did:key:zAbc123", cache_negative=True)

        assert found is not None
        assert found.id == "james"
        # Healed — the next lookup should hit the fast path.
        assert registry._did_index_path("did:key:zAbc123").exists()

    def test_stale_pointer_pointing_at_wrong_owner_falls_back_and_heals(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.create("sarah", "sarah@eigan.ai")
        registry.link_did("sarah", "did:key:zAbc123")
        # Corrupt the pointer to claim it belongs to james instead.
        import json

        registry._did_index_path("did:key:zAbc123").write_text(json.dumps({"owner_id": "james"}))

        found = registry.get_by_did("did:key:zAbc123", cache_negative=True)

        assert found is not None
        assert found.id == "sarah"  # the real owner, not the stale pointer's claim

    def test_unlink_leaves_a_negative_cache_entry_not_no_pointer_at_all(
        self, registry: OwnerRegistry
    ) -> None:
        """unlink_did writes owner_id=None rather than deleting the
        pointer file, so the *next* lookup for this DID is still the fast
        path (a confirmed-negative cache hit) instead of falling through
        to a scan just because nothing exists at that path."""
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")
        pointer_path = registry._did_index_path("did:key:zAbc123")
        assert pointer_path.exists()

        registry.unlink_did("james", "did:key:zAbc123")

        assert pointer_path.exists()  # still there — now a negative marker
        cache_hit, owner = registry._get_by_did_fast("did:key:zAbc123")
        assert cache_hit is True
        assert owner is None
        assert registry.get_by_did("did:key:zAbc123", cache_negative=True) is None

    def test_corrupt_pointer_file_falls_back_to_scan(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")
        registry._did_index_path("did:key:zAbc123").write_text("not valid json{{{")

        found = registry.get_by_did("did:key:zAbc123", cache_negative=True)

        assert found is not None
        assert found.id == "james"


class TestNegativeCaching:
    """Regression coverage for auditor finding #5 (round 2/3): get_by_did
    for a DID that's never been linked to anyone used to fall through to a
    full owner scan on *every single call* — the common case for /sync
    traffic from a device that's never been linked. Now the first lookup
    scans and caches a negative result; every subsequent lookup for that
    same DID is a fast-path hit, no scan."""

    def test_first_lookup_of_a_never_linked_did_scans_and_caches_negative(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")

        cache_hit_before, _ = registry._get_by_did_fast("did:key:zNeverLinked")
        assert cache_hit_before is False  # nothing cached yet — must scan

        found = registry.get_by_did("did:key:zNeverLinked", cache_negative=True)

        assert found is None
        cache_hit_after, owner_after = registry._get_by_did_fast("did:key:zNeverLinked")
        assert cache_hit_after is True  # now cached — no scan needed next time
        assert owner_after is None

    def test_repeat_lookups_of_a_never_linked_did_never_scan_again(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.get_by_did(
            "did:key:zNeverLinked", cache_negative=True
        )  # first call: scans, caches negative

        # Delete every owner file to prove a second scan would find
        # nothing meaningfully different anyway, then confirm the fast
        # path alone (no scan) still correctly returns None.
        for owner_file in registry.owners_dir.glob("*.json"):
            owner_file.unlink()

        cache_hit, owner = registry._get_by_did_fast("did:key:zNeverLinked")
        assert cache_hit is True
        assert owner is None
        assert registry.get_by_did("did:key:zNeverLinked", cache_negative=True) is None

    def test_linking_a_previously_negative_cached_did_overwrites_the_cache(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zAbc123", cache_negative=True)  # caches negative
        assert registry.get_by_did("did:key:zAbc123", cache_negative=True) is None

        registry.link_did("james", "did:key:zAbc123")

        found = registry.get_by_did("did:key:zAbc123", cache_negative=True)
        assert found is not None
        assert found.id == "james"


class TestNegativeCacheStalenessGuard:
    """Regression coverage for a round-4/round-5 finding on PR
    owner-identity-instance-discovery: a positive pointer hit re-verifies
    against its specific owner record every read, but the original
    negative-cache entries trusted 'owner_id: null' unconditionally, with
    no equivalent check — reproducibly stale in the gap between link_did's
    two writes (owner file, then pointer file), since the fast path is
    deliberately unlocked.

    An earlier fix used a shared generation counter bumped before every
    mutation, but that invalidated *every* DID's negative cache on *any*
    owner-registry change, not just the affected one — round 5 flagged
    this as unnecessary shared-state churn. This version instead has
    link_did delete the specific DID's stale pointer before touching the
    owner file: a reader hitting a *missing* pointer during that window
    correctly falls through to the locked scan and waits, while every
    other DID's cache entry is untouched.
    """

    def test_fresh_negative_entry_is_trusted(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zAbc123", cache_negative=True)  # scans, caches negative

        cache_hit, owner = registry._get_by_did_fast("did:key:zAbc123")

        assert cache_hit is True
        assert owner is None

    def test_link_did_leaves_no_pointer_file_during_the_owner_file_write(
        self, registry: OwnerRegistry
    ) -> None:
        """The actual mechanism, observed directly: by the time the owner
        file is written, any prior pointer for this DID is already gone —
        never still sitting there stale next to data that's moved on."""
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zAbc123", cache_negative=True)  # caches negative
        pointer_path = registry._did_index_path("did:key:zAbc123")
        assert pointer_path.exists()

        observed: dict[str, bool] = {}
        original_save_owner = registry._save_owner

        def spying_save_owner(owner: Owner) -> None:
            observed["pointer_existed_during_owner_write"] = pointer_path.exists()
            original_save_owner(owner)

        registry._save_owner = spying_save_owner  # type: ignore[method-assign]
        registry.link_did("james", "did:key:zAbc123")

        assert observed["pointer_existed_during_owner_write"] is False

    def test_after_link_did_the_pointer_reflects_the_final_state_not_stale(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zAbc123", cache_negative=True)  # caches negative

        registry.link_did("james", "did:key:zAbc123")

        cache_hit, owner = registry._get_by_did_fast("did:key:zAbc123")
        assert cache_hit is True
        assert owner is not None
        assert owner.id == "james"

    def test_link_did_does_not_invalidate_a_different_dids_negative_cache(
        self, registry: OwnerRegistry
    ) -> None:
        """The property this per-pointer approach was chosen for over a
        shared generation counter: linking one DID must not force every
        *other* DID's already-cached negative result to be re-scanned."""
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zUnrelated", cache_negative=True)  # caches negative
        unrelated_pointer = registry._did_index_path("did:key:zUnrelated")
        assert unrelated_pointer.exists()

        registry.link_did("james", "did:key:zAbc123")  # a different DID entirely

        cache_hit, owner = registry._get_by_did_fast("did:key:zUnrelated")
        assert cache_hit is True  # untouched — not invalidated by an unrelated mutation
        assert owner is None

    def test_create_and_add_email_do_not_touch_any_negative_pointer(
        self, registry: OwnerRegistry
    ) -> None:
        """create/add_email never mutate linked_dids, so they can't make
        any DID's negative cache stale — no reason for them to touch
        did_index/ at all."""
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zAbc123", cache_negative=True)  # caches negative

        registry.create("sarah", "sarah@eigan.ai")
        registry.add_email("sarah", "sarah2@eigan.ai")

        cache_hit, owner = registry._get_by_did_fast("did:key:zAbc123")
        assert cache_hit is True
        assert owner is None


class TestNegativeCacheGating:
    """Regression coverage for the other round-4 finding: get_by_did used
    to write a permanent negative-cache file for *any* DID on a scan miss,
    with no cap — server.py's sync() calls this before any admission
    check, so a caller could mint a fresh did:key, sign one /sync call,
    and plant one file, forever, for free. cache_negative=False finds the
    same correct answer without writing anything."""

    def test_cache_negative_false_writes_no_pointer_file(self, registry: OwnerRegistry) -> None:
        registry.create("james", "james@eigan.ai")

        found = registry.get_by_did("did:key:zNeverSeen", cache_negative=False)

        assert found is None
        assert not registry._did_index_path("did:key:zNeverSeen").exists()

    def test_cache_negative_false_still_returns_the_correct_answer(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.link_did("james", "did:key:zAbc123")

        found = registry.get_by_did("did:key:zAbc123", cache_negative=False)

        assert found is not None
        assert found.id == "james"

    def test_cache_negative_false_does_not_prevent_a_later_true_call_from_caching(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")
        registry.get_by_did("did:key:zNeverSeen", cache_negative=False)
        assert not registry._did_index_path("did:key:zNeverSeen").exists()

        registry.get_by_did(
            "did:key:zNeverSeen", cache_negative=True
        )  # now DID is "known" to the caller

        assert registry._did_index_path("did:key:zNeverSeen").exists()

    def test_repeated_cache_negative_false_calls_never_accumulate_files(
        self, registry: OwnerRegistry
    ) -> None:
        """The actual attack this closes: spamming fresh, never-approved
        DIDs must not grow did_index/ at all."""
        registry.create("james", "james@eigan.ai")

        for i in range(20):
            registry.get_by_did(f"did:key:zSpam{i}", cache_negative=False)

        assert list(registry.did_index_dir.glob("*.json")) == []
