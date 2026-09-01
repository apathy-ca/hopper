"""Tests for DIDRegistry's org fallthrough (Phase E of
Owner-Identity-and-Instance-Discovery-Plan.md).

Companion to test_did_registry_owner_fallthrough.py — same shape, one tier
further: DID -> owner -> org. A DID with no direct grant and whose owner
has no direct grant can still be authorized through an org that owner is
a member of.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hopper.upstream.storage import DIDRegistry, DIDStatus, org_key, owner_key

ADMIN = "did:key:zAdmin"
ALICE = "did:key:zAlice"  # james's device, no direct grant
BOB = "did:key:zBob"  # unrelated device


@pytest.fixture
def registry(tmp_path: Path) -> DIDRegistry:
    return DIDRegistry(tmp_path)


def _bootstrap_admin(registry: DIDRegistry) -> None:
    registry.register_or_get(ADMIN, "some-namespace")


class TestOrgFallthrough:
    def test_org_grant_authorizes_via_org_ids(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "rosetta", org_ids=["eigan"]) is True

    def test_no_org_ids_means_no_org_fallthrough(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "rosetta", org_ids=None) is False
        assert registry.is_authorized(ALICE, "rosetta", org_ids=[]) is False

    def test_org_grant_does_not_leak_to_a_different_org(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)

        assert registry.is_authorized(BOB, "rosetta", org_ids=["waypoint-inc"]) is False

    def test_checks_every_org_the_owner_belongs_to(self, registry: DIDRegistry) -> None:
        """An owner can be a member of several orgs — any one of them
        granting the namespace is enough."""
        _bootstrap_admin(registry)
        registry.approve(org_key("second-org"), "rosetta", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "rosetta", org_ids=["first-org", "second-org"]) is True

    def test_owner_grant_checked_before_org_fallthrough(self, registry: DIDRegistry) -> None:
        """Resolution order: DID direct -> owner -> org. An owner grant
        should short-circuit before org lookup is even needed, but the
        end result must be the same either way."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "rosetta", by_did=ADMIN)

        assert (
            registry.is_authorized(ALICE, "rosetta", owner_id="james", org_ids=["no-grant-here"])
            is True
        )

    def test_revoking_the_org_immediately_denies_every_members_devices(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)
        assert registry.is_authorized(ALICE, "rosetta", org_ids=["eigan"]) is True

        registry.revoke(org_key("eigan"), "rosetta", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "rosetta", org_ids=["eigan"]) is False

    def test_org_global_grant_covers_every_namespace(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "*", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "rosetta", org_ids=["eigan"]) is True
        assert registry.is_authorized(ALICE, "waypoint", org_ids=["eigan"]) is True

    def test_org_approver_role_via_fallthrough(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN, role=DIDStatus.APPROVER)

        assert registry.is_approver(ALICE, "rosetta", org_ids=["eigan"]) is True

    def test_org_approve_creates_no_did_record_file(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)

        assert registry._load_record(org_key("eigan")) is None


class TestRegisterOrGetOrgAwareness:
    def test_first_sync_from_org_granted_device_is_approved_not_pending(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)

        status, _ = registry.register_or_get(ALICE, "rosetta", org_ids=["eigan"])

        assert status == DIDStatus.APPROVED

    def test_org_shortcut_writes_no_registry_entry(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(org_key("eigan"), "rosetta", by_did=ADMIN)

        registry.register_or_get(ALICE, "rosetta", org_ids=["eigan"])

        assert registry.get_status(ALICE, "rosetta") is None

    def test_no_matching_org_grant_still_lands_pending(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)

        status, is_new = registry.register_or_get(BOB, "rosetta", org_ids=["no-such-grant"])

        assert status == DIDStatus.PENDING
        assert is_new is True
