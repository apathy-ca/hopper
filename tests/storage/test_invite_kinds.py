"""Tests for the three invite kinds (Phase C of
Owner-Identity-and-Instance-Discovery-Plan.md).

Invite/InviteStore were generalized from namespace-only to also cover
DEVICE (self-service, links a new DID to an existing owner) and NEW_OWNER
(admin-only, creates a brand-new owner). These tests cover: the new kinds
round-trip correctly, and — critically — an invite file written before
Phase C (no "kind" key at all) still loads correctly as a NAMESPACE
invite, since that's real data already on disk for anyone upgrading.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hopper.upstream.storage import DIDStatus, InviteKind, InviteStore


@pytest.fixture
def store(tmp_path: Path) -> InviteStore:
    return InviteStore(tmp_path)


class TestNamespaceInviteUnchanged:
    """Locks down the pre-Phase-C behavior — kind defaults to NAMESPACE,
    namespace/role round-trip exactly as before."""

    def test_create_defaults_to_namespace_kind(self, store: InviteStore) -> None:
        token, invite = store.create(
            issued_by="did:key:zAdmin",
            expires_at=None,
            namespace="eigan",
            role=DIDStatus.APPROVED,
        )

        assert invite.kind == InviteKind.NAMESPACE
        assert invite.namespace == "eigan"
        assert invite.role == DIDStatus.APPROVED
        assert invite.owner_id == ""
        assert invite.new_owner_email == ""

    def test_get_round_trips_namespace_invite(self, store: InviteStore) -> None:
        token, _ = store.create(issued_by="did:key:zAdmin", expires_at=None, namespace="eigan")

        fetched = store.get(token)

        assert fetched is not None
        assert fetched.kind == InviteKind.NAMESPACE
        assert fetched.namespace == "eigan"


class TestDeviceInvite:
    def test_create_and_round_trip(self, store: InviteStore) -> None:
        token, invite = store.create(
            issued_by="did:key:zAlice",
            expires_at=None,
            kind=InviteKind.DEVICE,
            owner_id="james",
        )

        assert invite.kind == InviteKind.DEVICE
        assert invite.owner_id == "james"
        assert invite.namespace == ""

        fetched = store.get(token)
        assert fetched is not None
        assert fetched.kind == InviteKind.DEVICE
        assert fetched.owner_id == "james"

    def test_redeem_bookkeeping_is_kind_agnostic(self, store: InviteStore) -> None:
        """The lifecycle mechanics (hash lookup, uses, redeemed_by) don't
        care which kind an invite is — only the server endpoint's
        post-redeem side effects differ."""
        token, _ = store.create(
            issued_by="did:key:zAlice", expires_at=None, kind=InviteKind.DEVICE, owner_id="james"
        )

        invite, message = store.redeem(token, by_did="did:key:zNewDevice")

        assert invite is not None
        assert message == "redeemed"
        assert invite.uses == 1
        assert "did:key:zNewDevice" in invite.redeemed_by


class TestNewOwnerInvite:
    def test_create_and_round_trip(self, store: InviteStore) -> None:
        token, invite = store.create(
            issued_by="did:key:zAdmin",
            expires_at=None,
            kind=InviteKind.NEW_OWNER,
            owner_id="sarah",
            new_owner_email="sarah@eigan.ai",
        )

        assert invite.kind == InviteKind.NEW_OWNER
        assert invite.owner_id == "sarah"
        assert invite.new_owner_email == "sarah@eigan.ai"

        fetched = store.get(token)
        assert fetched is not None
        assert fetched.new_owner_email == "sarah@eigan.ai"


class TestBackwardCompatibleLoading:
    """The real-world case: an invite JSON file written by the pre-Phase-C
    code has no 'kind', 'owner_id', or 'new_owner_email' keys at all."""

    def test_pre_phase_c_file_loads_as_namespace_invite(
        self, store: InviteStore, tmp_path: Path
    ) -> None:
        token = "hinv_legacy_test_token"
        token_hash = InviteStore._hash(token)
        legacy_path = tmp_path / "invites" / f"{token_hash}.json"
        legacy_path.write_text(
            json.dumps(
                {
                    "token_hash": token_hash,
                    "namespace": "eigan",
                    "role": "approved",
                    "issued_by": "did:key:zAdmin",
                    "created_at": 1700000000000,
                    "expires_at": None,
                    "max_uses": 1,
                    "uses": 0,
                    "redeemed_by": [],
                }
            )
        )

        loaded = store.get(token)

        assert loaded is not None
        assert loaded.kind == InviteKind.NAMESPACE
        assert loaded.namespace == "eigan"
        assert loaded.owner_id == ""
        assert loaded.new_owner_email == ""
