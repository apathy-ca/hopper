"""Tests for DIDRegistry's owner fallthrough (Phase B of
Owner-Identity-and-Instance-Discovery-Plan.md).

DIDRegistry had zero direct test coverage before this phase — these tests
cover both the new owner-fallthrough behavior and lock down the pre-existing
DID-only behavior that Phase B refactored around (``_is_directly_authorized``
/ ``_is_directly_approver`` are meant to be byte-for-byte the same logic the
original ``is_authorized``/``is_approver`` had, just factored out for reuse).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hopper.upstream.storage import DIDRegistry, DIDStatus, OwnerRegistry, owner_key


@pytest.fixture
def registry(tmp_path: Path) -> DIDRegistry:
    return DIDRegistry(tmp_path)


ADMIN = "did:key:zAdmin"
ALICE = "did:key:zAlice"  # the admin's second device
BOB = "did:key:zBob"  # an unrelated collaborator's device


def _bootstrap_admin(registry: DIDRegistry) -> None:
    """First DID to register becomes admin — mirrors sync()'s bootstrap."""
    registry.register_or_get(ADMIN, "some-namespace")


class TestDidOnlyBehaviorUnchanged:
    """Phase A/pre-existing behavior — owner_id is never passed, so this
    must match the original implementation exactly."""

    def test_unregistered_did_not_authorized(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        assert registry.is_authorized(ALICE, "eigan") is False

    def test_approve_then_authorized(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        assert registry.is_authorized(ALICE, "eigan") is True

    def test_global_approval_covers_every_namespace(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "*", by_did=ADMIN)
        assert registry.is_authorized(ALICE, "eigan") is True
        assert registry.is_authorized(ALICE, "waypoint") is True

    def test_revoke_removes_authorization(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        registry.revoke(ALICE, "eigan", by_did=ADMIN)
        assert registry.is_authorized(ALICE, "eigan") is False

    def test_admin_is_authorized_everywhere(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        assert registry.is_authorized(ADMIN, "anything") is True

    def test_approver_role_grants_is_approver_not_plain_approve(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)
        assert registry.is_approver(ALICE, "eigan") is True
        assert registry.is_approver(BOB, "eigan") is False


class TestOwnerFallthrough:
    """The actual Phase B behavior: a DID with no direct grant inherits
    through its linked owner."""

    def test_owner_grant_authorizes_a_did_with_no_direct_grant(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True

    def test_owner_grant_does_not_leak_to_a_different_owner(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        assert registry.is_authorized(BOB, "eigan", owner_id="sarah") is False

    def test_no_owner_id_means_no_fallthrough(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan", owner_id=None) is False

    def test_owner_global_grant_covers_every_namespace(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "*", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True
        assert registry.is_authorized(ALICE, "waypoint", owner_id="james") is True

    def test_revoking_the_owner_immediately_denies_every_linked_did(
        self, registry: DIDRegistry
    ) -> None:
        """The property this phase exists for: approve/revoke once, every
        device (present and future) follows — no per-device bookkeeping,
        no orphaned grants left behind."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)
        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True

        registry.revoke(owner_key("james"), "eigan", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is False

    def test_a_dids_own_direct_grant_still_wins_if_owner_has_none(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True

    def test_owner_approve_does_not_create_a_did_record_file(
        self, registry: DIDRegistry, tmp_path: Path
    ) -> None:
        """set_status must skip the per-DID file write for an owner key —
        'owner:james' is not a DID and has no per-DID record to write."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        assert registry._load_record(owner_key("james")) is None

    def test_owner_approver_role_grants_is_approver_via_fallthrough(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        assert registry.is_approver(ALICE, "eigan", owner_id="james") is True


class TestRegisterOrGetOwnerAwareness:
    """The register_or_get fix: a device syncing for the first time under
    an already-granted owner should never land as PENDING."""

    def test_first_sync_from_owner_granted_device_is_approved_not_pending(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        status, is_new = registry.register_or_get(ALICE, "eigan", owner_id="james")

        assert status == DIDStatus.APPROVED

    def test_owner_shortcut_writes_no_registry_entry(self, registry: DIDRegistry) -> None:
        """Deliberately not materialized — so a later revoke of the owner's
        grant takes effect without needing to clean up a stale per-DID
        entry (see TestOwnerFallthrough.test_revoking_the_owner_...)."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        registry.register_or_get(ALICE, "eigan", owner_id="james")

        assert registry.get_status(ALICE, "eigan") is None

    def test_first_sync_with_no_owner_grant_still_lands_pending(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)

        status, is_new = registry.register_or_get(BOB, "eigan", owner_id="sarah")

        assert status == DIDStatus.PENDING
        assert is_new is True

    def test_first_sync_with_no_owner_at_all_still_lands_pending(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)

        status, is_new = registry.register_or_get(BOB, "eigan", owner_id=None)

        assert status == DIDStatus.PENDING


class TestNamespacesForKeys:
    def test_empty_when_no_grants(self, registry: DIDRegistry) -> None:
        has_global, namespaces = registry.namespaces_for_keys({owner_key("james")})
        assert has_global is False
        assert namespaces == []

    def test_collects_namespaces_across_multiple_keys(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        registry.approve(owner_key("james"), "waypoint", by_did=ADMIN)

        has_global, namespaces = registry.namespaces_for_keys({ALICE, owner_key("james")})

        assert has_global is False
        assert namespaces == ["eigan", "waypoint"]

    def test_global_grant_reported_as_flag_not_enumerated(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "*", by_did=ADMIN)

        has_global, namespaces = registry.namespaces_for_keys({owner_key("james")})

        assert has_global is True
        assert namespaces == []  # "*" itself is never listed as an explicit namespace

    def test_deduplicates_a_namespace_granted_via_two_different_keys(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        _, namespaces = registry.namespaces_for_keys({ALICE, owner_key("james")})

        assert namespaces == ["eigan"]


def test_owner_registry_and_did_registry_compose_end_to_end(tmp_path: Path) -> None:
    """A thin integration check across the seam server.py's sync() actually
    walks: OwnerRegistry.get_by_did() -> owner_id -> DIDRegistry
    fallthrough. Both registries share one storage_path, same as
    UpstreamStorage wires them."""
    did_registry = DIDRegistry(tmp_path)
    owner_registry = OwnerRegistry(tmp_path)

    did_registry.register_or_get(ADMIN, "eigan")  # bootstrap admin
    owner_registry.create("james", "james@eigan.ai")
    owner_registry.link_did("james", ALICE)
    did_registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

    owner = owner_registry.get_by_did(ALICE)
    assert owner is not None
    assert did_registry.is_authorized(ALICE, "eigan", owner_id=owner.id) is True
