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


class TestIsDirectlyAuthorizedChecksBothBucketsNotJustPresence:
    """Regression coverage for a round-8 finding on PR
    owner-identity-instance-discovery: a genuine pre-existing bug
    (confirmed present in master, not introduced by this branch, but
    _residual_authorization_reason's revoke logic now depends on this
    same primitive so it's worth closing here too). ``_is_directly_
    authorized`` used to return as soon as ``key`` was merely *present*
    in the GLOBAL_NS bucket, even at a non-authorized status (e.g.
    PENDING) there -- never falling through to check the namespace-
    specific bucket for a real, separate APPROVED grant.
    """

    def test_pending_global_entry_does_not_shadow_a_real_namespace_specific_approval(
        self, registry: DIDRegistry
    ) -> None:
        """The exact repro: a DID's first sync happens to target instance
        name '*' (unvalidated free text), landing it PENDING in GLOBAL_NS
        -- an admin then explicitly approves it for 'eigan'. That
        explicit approval must not be shadowed by the earlier PENDING
        global entry."""
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "*")  # lands PENDING in GLOBAL_NS
        assert registry.get_status(ALICE, "*") == DIDStatus.PENDING

        registry.approve(ALICE, "eigan", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan") is True

    def test_pending_global_entry_alone_still_correctly_denies(self, registry: DIDRegistry) -> None:
        """Sanity check the fix doesn't over-correct into always
        authorizing once any GLOBAL_NS entry exists."""
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "*")  # lands PENDING in GLOBAL_NS

        assert registry.is_authorized(ALICE, "eigan") is False

    def test_approved_global_entry_still_authorizes_every_namespace(
        self, registry: DIDRegistry
    ) -> None:
        """Sanity check the ordinary global-approval case (the common,
        already-tested path) isn't disturbed by this fix."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "*", by_did=ADMIN)

        assert registry.is_authorized(ALICE, "eigan") is True
        assert registry.is_authorized(ALICE, "waypoint") is True


class TestGetStatusChecksBothBucketsNotJustPresence:
    """Regression coverage for a round-9 finding on PR
    owner-identity-instance-discovery: ``get_status`` had the exact same
    bug class round 8 fixed in ``_is_directly_authorized`` -- presence in
    GLOBAL_NS, not its value, used to shadow a real, different-status
    namespace-specific entry. Not a live authorization bypass (the actual
    gate, ``is_authorized``, was already fixed and correct for this same
    pair), but the same broken contract one function away, and
    ``register_or_get`` calls ``get_status`` internally.
    """

    def test_pending_global_entry_does_not_shadow_a_real_namespace_specific_approval(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "*")  # lands PENDING in GLOBAL_NS
        registry.approve(ALICE, "eigan", by_did=ADMIN)

        assert registry.get_status(ALICE, "eigan") == DIDStatus.APPROVED

    def test_pending_global_entry_alone_still_reported_as_pending(
        self, registry: DIDRegistry
    ) -> None:
        """No namespace-specific entry at all -- must still fall back to
        the global one rather than returning None."""
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "*")  # lands PENDING in GLOBAL_NS

        assert registry.get_status(ALICE, "eigan") == DIDStatus.PENDING

    def test_approved_global_entry_wins_over_a_lesser_namespace_specific_entry(
        self, registry: DIDRegistry
    ) -> None:
        """An authorized global grant is the DID's real overall status,
        regardless of what a specific namespace bucket separately holds."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "*", by_did=ADMIN)
        registry.register_or_get(BOB, "eigan")  # unrelated DID, sanity only

        assert registry.get_status(ALICE, "eigan") == DIDStatus.APPROVED

    def test_register_or_get_is_not_fooled_by_a_stray_global_pending_entry(
        self, registry: DIDRegistry
    ) -> None:
        """register_or_get calls get_status internally -- confirm the fix
        actually reaches that caller, not just direct get_status callers."""
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "*")  # lands PENDING in GLOBAL_NS
        registry.approve(ALICE, "eigan", by_did=ADMIN)

        status, is_new = registry.register_or_get(ALICE, "eigan")

        assert status == DIDStatus.APPROVED
        assert is_new is False


class TestOwnerFallthrough:
    """The actual Phase B behavior: a DID with no direct grant inherits
    through its linked owner."""

    def test_owner_grant_authorizes_a_did_with_no_direct_grant(self, registry: DIDRegistry) -> None:
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

    owner = owner_registry.get_by_did(ALICE, cache_negative=True)
    assert owner is not None
    assert did_registry.is_authorized(ALICE, "eigan", owner_id=owner.id) is True


class TestApproveRevokeActorFallthrough:
    """Regression coverage for auditor finding #1 on PR
    owner-identity-instance-discovery: approve()/revoke() only checked the
    *caller's own DID* for approver authority, never its linked owner/org —
    so a DID whose owner (or org) held an APPROVER grant on a namespace
    still got rejected trying to approve/revoke on it. The headline
    capability ("any DID linked to an approver-owner can self-service")
    was silently not working until by_owner_id/by_org_ids were threaded
    into these two methods specifically (is_authorized/is_approver already
    had the fallthrough — these were the call sites that didn't use it)."""

    def test_approve_succeeds_for_a_did_that_is_only_an_approver_via_its_owner(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        # ALICE has no direct grant at all — only reachable via owner_id.
        success, message = registry.approve(BOB, "eigan", by_did=ALICE, by_owner_id="james")

        assert success is True
        assert registry.is_authorized(BOB, "eigan") is True

    def test_approve_still_rejected_without_the_owner_id_hint(self, registry: DIDRegistry) -> None:
        """Same setup as above, but the caller doesn't pass by_owner_id —
        proves the fallthrough is opt-in via the parameter, not a global
        DID->owner lookup happening implicitly inside approve()."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        success, message = registry.approve(BOB, "eigan", by_did=ALICE)

        assert success is False
        assert "not authorized" in message

    def test_revoke_succeeds_for_a_did_that_is_only_an_approver_via_its_org(
        self, registry: DIDRegistry
    ) -> None:
        from hopper.upstream.storage import org_key

        _bootstrap_admin(registry)
        registry.approve(org_key("eigan-corp"), "rosetta", by_did=ADMIN, role=DIDStatus.APPROVER)
        registry.approve(BOB, "rosetta", by_did=ADMIN)  # something to revoke
        assert registry.is_authorized(BOB, "rosetta") is True

        success, message = registry.revoke(BOB, "rosetta", by_did=ALICE, by_org_ids=["eigan-corp"])

        assert success is True
        assert registry.is_authorized(BOB, "rosetta") is False


class TestRevokeOwnerOrgDerivedAccessDoesNotSilentlyNoOp:
    """Regression coverage for a round-6 finding on PR
    owner-identity-instance-discovery: revoke(target=<a plain DID>) only
    ever removed a *direct* per-namespace registry entry — but
    register_or_get's owner/org shortcut deliberately never writes one for
    a DID authorized purely through its owner (see TestIsEstablished's
    ``test_did_authorized_only_via_owner_shortcut_is_not_established``
    just below). Revoking such a DID had nothing to pop, yet still
    reported ``(True, "revoked from ...")`` — an admin cutting off a
    stolen laptop was told it worked while ``is_authorized`` stayed True.

    Passing ``target_owner_id``/``target_org_ids`` lets ``revoke()``
    re-check authorization after the pop and fail loudly instead."""

    def test_revoking_a_purely_owner_derived_did_without_the_hint_reports_false_success(
        self, registry: DIDRegistry
    ) -> None:
        """Without target_owner_id, the exact bug: nothing to pop, but the
        old behavior claimed success anyway. Locks down that this needs
        the hint to be caught -- it's not a magic global fix."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)
        registry.register_or_get(ALICE, "eigan", owner_id="james")
        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True

        success, message = registry.revoke(ALICE, "eigan", by_did=ADMIN)

        assert success is True  # the old, misleading behavior -- no hint, no detection
        assert (
            registry.is_authorized(ALICE, "eigan", owner_id="james") is True
        )  # but nothing changed

    def test_revoking_a_purely_owner_derived_did_with_the_hint_fails_loudly(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)
        registry.register_or_get(ALICE, "eigan", owner_id="james")
        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True

        success, message = registry.revoke(ALICE, "eigan", by_did=ADMIN, target_owner_id="james")

        assert success is False
        assert "linked owner's grant" in message
        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True  # still has access

    def test_revoking_a_directly_granted_did_still_succeeds_with_the_hint_present(
        self, registry: DIDRegistry
    ) -> None:
        """The hint must not cause false negatives for the ordinary case —
        a DID with its own direct grant and no owner at all."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)

        success, message = registry.revoke(
            ALICE, "eigan", by_did=ADMIN, target_owner_id=None, target_org_ids=[]
        )

        assert success is True
        assert registry.is_authorized(ALICE, "eigan") is False

    def test_revoking_an_owner_key_still_authorized_via_a_different_org_fails_loudly(
        self, registry: DIDRegistry
    ) -> None:
        """Same shape, one level up: an owner-key target that's also a
        member of an org holding its own grant."""
        from hopper.upstream.storage import org_key

        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "rosetta", by_did=ADMIN)
        registry.approve(org_key("eigan-corp"), "rosetta", by_did=ADMIN)

        success, message = registry.revoke(
            owner_key("james"), "rosetta", by_did=ADMIN, target_org_ids=["eigan-corp"]
        )

        assert success is False
        assert "org grant" in message


class TestRevokeOwnResidualGrantDoesNotSilentlyNoOp:
    """Regression coverage for a round-7 finding on PR
    owner-identity-instance-discovery: round 6's re-check-after-pop fix
    only ever looked at *fallthrough* (owner/org) for continued access —
    it never checked whether the target itself still held a *separate*
    direct grant the revoke call wasn't asked to touch (most commonly, a
    GLOBAL_NS '*' entry independent of a namespace-specific one, or vice
    versa). That left the exact same 'admin is told access was cut off
    when it wasn't' bug this round otherwise fixed, one level up:

    - For an owner/org-key target, this was a silent false *success* —
      the old code's owner/org branches only checked org-membership
      fallthrough, never the target's own remaining direct entry.
    - For a DID target with its own separate global grant, the old code
      *did* detect the residual access (is_authorized checks the target's
      own direct grant first) but mislabeled it as coming from "an
      owner/org grant" with "unlink the DID from its owner" remediation —
      wrong on both counts when no owner was involved at all.
    """

    def test_revoking_a_namespace_grant_from_an_owner_with_a_separate_global_grant_fails_loudly(
        self, registry: DIDRegistry
    ) -> None:
        """The exact round-7 repro: owner:james holds both an 'eigan'
        grant and a separate '*' grant; revoking just 'eigan' must not
        report success while '*' still grants every linked DID 'eigan'
        access."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)
        registry.approve(owner_key("james"), "*", by_did=ADMIN)

        success, message = registry.revoke(owner_key("james"), "eigan", by_did=ADMIN)

        assert success is False
        assert "own separate grant" in message
        assert registry.is_authorized(ALICE, "eigan", owner_id="james") is True

    def test_revoking_a_namespace_grant_from_an_org_with_a_separate_global_grant_fails_loudly(
        self, registry: DIDRegistry
    ) -> None:
        from hopper.upstream.storage import org_key

        _bootstrap_admin(registry)
        registry.approve(org_key("eigan-corp"), "rosetta", by_did=ADMIN)
        registry.approve(org_key("eigan-corp"), "*", by_did=ADMIN)

        success, message = registry.revoke(org_key("eigan-corp"), "rosetta", by_did=ADMIN)

        assert success is False
        assert "own separate grant" in message

    def test_revoking_a_namespace_grant_from_a_did_with_a_separate_global_grant_names_its_own_grant(
        self, registry: DIDRegistry
    ) -> None:
        """The related round-7 finding: this must be labeled as the DID's
        own grant, not misattributed to an owner/org that isn't involved
        at all."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        registry.approve(ALICE, "*", by_did=ADMIN)

        success, message = registry.revoke(
            ALICE, "eigan", by_did=ADMIN, target_owner_id=None, target_org_ids=[]
        )

        assert success is False
        assert "own separate grant" in message
        assert "owner" not in message.lower()

    def test_revoking_the_global_grant_does_not_scan_for_leftover_specific_namespace_grants(
        self, registry: DIDRegistry
    ) -> None:
        """Documents the direction this fix does NOT cover, rather than
        silently leaving it unverified: ``_is_directly_authorized`` checks
        the GLOBAL_NS bucket first specifically because a '*' grant
        implies access to every namespace -- so it's the right check for
        "does a broader grant still cover the namespace I just revoked".
        The reverse isn't symmetric: a leftover 'eigan'-specific entry
        doesn't mean the target is still "authorized for '*'" in any
        meaningful sense, and detecting it would need a scan of every
        namespace bucket, not a targeted check -- out of scope for the
        round-7 finding this class fixes, which was specifically about a
        specific-namespace revoke leaving a broader grant behind."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        registry.approve(ALICE, "*", by_did=ADMIN)

        success, message = registry.revoke(
            ALICE, "*", by_did=ADMIN, target_owner_id=None, target_org_ids=[]
        )

        assert success is True
        assert registry.is_authorized(ALICE, "eigan") is True  # untouched, and not flagged

    def test_approver_revoking_owner_derived_access_gets_an_accurate_message(
        self, registry: DIDRegistry
    ) -> None:
        """Round-7 minor finding: an approver revoking a target with no
        direct entry used to get the generic (and misleading) 'approvers
        can only revoke APPROVED members' -- the real reason is that
        owner/org-derived access is admin-only to touch."""
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)
        registry.register_or_get(BOB, "eigan", owner_id="james")  # owner-derived, no direct entry

        success, message = registry.revoke(BOB, "eigan", by_did=ALICE, target_owner_id="james")

        assert success is False
        assert "no direct grant" in message
        assert "linked owner's grant" in message

    def test_approver_revoking_a_target_whose_only_access_is_its_own_separate_grant_names_it(
        self, registry: DIDRegistry
    ) -> None:
        """Round-8 fix: the message above used to unconditionally blame
        'owner/org-derived' access even when the target's access was its
        own separate grant (e.g. a global '*') with no owner or org
        involved at all -- same message-mislabeling class fixed for the
        admin path, missed here."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)
        registry.approve(BOB, "*", by_did=ADMIN)  # BOB's only grant: his own, global

        success, message = registry.revoke(
            BOB, "eigan", by_did=ALICE, target_owner_id=None, target_org_ids=[]
        )

        assert success is False
        assert "own separate grant" in message
        assert "owner" not in message.lower()

    def test_approver_revoking_a_target_with_no_access_anywhere_gets_a_plain_message(
        self, registry: DIDRegistry
    ) -> None:
        """The genuine-nothing-to-revoke case must not be mislabeled as
        owner/org-derived either. BOB has a real grant, but on a
        different namespace than the one being revoked -- so this
        namespace's bucket has no entry for him at all (not even
        PENDING), and no residual access anywhere explains it either."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)
        registry.approve(BOB, "waypoint", by_did=ADMIN)  # unrelated namespace

        success, message = registry.revoke(
            BOB, "eigan", by_did=ALICE, target_owner_id=None, target_org_ids=[]
        )

        assert success is False
        assert "no grant to revoke" in message

    def test_revoking_the_only_grant_a_did_holds_still_succeeds(
        self, registry: DIDRegistry
    ) -> None:
        """No residual grant anywhere -- must not regress into always
        failing now that a same-target self-check was added."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)

        success, message = registry.revoke(
            ALICE, "eigan", by_did=ADMIN, target_owner_id=None, target_org_ids=[]
        )

        assert success is True
        assert registry.is_authorized(ALICE, "eigan") is False


class TestApproveRevokeBlocksNonAdminFromOwnerOrgTargets:
    """Regression coverage for a round-6 finding on PR
    owner-identity-instance-discovery: can_approve()/can_revoke() checked
    only the *caller's* approver authority for the namespace, never what
    *kind* of target was being granted/revoked — so a plain namespace
    approver (not admin) could pass ``target=owner_key(...)`` or
    ``org_key(...)`` and grant/revoke access for every DID currently and
    future linked to that owner/org in one call, a far bigger blast radius
    than the one-device delegation approver status is meant for."""

    def test_namespace_approver_cannot_grant_an_owner_key(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        success, message = registry.approve(owner_key("mallory"), "eigan", by_did=ALICE)

        assert success is False
        assert "only admin" in message
        assert registry.is_authorized(owner_key("mallory"), "eigan") is False

    def test_namespace_approver_cannot_grant_an_org_key(self, registry: DIDRegistry) -> None:
        from hopper.upstream.storage import org_key

        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        success, message = registry.approve(org_key("mallory-corp"), "eigan", by_did=ALICE)

        assert success is False
        assert "only admin" in message

    def test_namespace_approver_can_still_grant_a_plain_did(self, registry: DIDRegistry) -> None:
        """The restriction is target-kind-specific -- must not regress the
        ordinary approver capability this whole plan is about."""
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        success, message = registry.approve(BOB, "eigan", by_did=ALICE)

        assert success is True
        assert registry.is_authorized(BOB, "eigan") is True

    def test_admin_can_still_grant_an_owner_key(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)

        success, message = registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        assert success is True

    def test_namespace_approver_cannot_revoke_an_owner_key(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        success, message = registry.revoke(owner_key("james"), "eigan", by_did=ALICE)

        assert success is False
        assert "only admin" in message
        assert registry.is_authorized(owner_key("james"), "eigan") is True

    def test_namespace_approver_can_still_revoke_a_plain_approved_did(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)
        registry.approve(BOB, "eigan", by_did=ADMIN)

        success, message = registry.revoke(BOB, "eigan", by_did=ALICE)

        assert success is True
        assert registry.is_authorized(BOB, "eigan") is False


class TestIsEstablished:
    """is_established gates OwnerRegistry's negative-cache writes (round-4
    finding: server.py's sync() must only let a DID earn a permanent
    did_index/ file once it's genuinely established, not on its very
    first, possibly-throwaway contact).

    round-5 tightened this from "has any record at all" (including
    PENDING) to "has actually been APPROVED/APPROVER somewhere" —
    PENDING is what register_or_get hands out to any signed request for
    free, so gating on mere record-existence only doubled an attacker's
    per-DID cost (one throwaway call to go PENDING, then the real one)
    rather than bounding it. APPROVED/APPROVER can't be self-granted.
    """

    def test_admin_is_established(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        assert registry.is_established(ADMIN) is True

    def test_never_seen_did_is_not_established(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        assert registry.is_established(ALICE) is False

    def test_pending_registration_alone_is_not_established(self, registry: DIDRegistry) -> None:
        """The exact gap the round-5 finding identified: landing PENDING
        is free for anyone who can sign a request — it must not be
        enough on its own to earn negative-cache-write privilege."""
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "eigan")

        assert registry.get_status(ALICE, "eigan") == DIDStatus.PENDING
        assert registry.is_established(ALICE) is False

    def test_approved_did_is_established(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)

        assert registry.is_established(ALICE) is True

    def test_approver_did_is_established(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN, role=DIDStatus.APPROVER)

        assert registry.is_established(ALICE) is True

    def test_approved_on_one_namespace_counts_even_if_pending_on_another(
        self, registry: DIDRegistry
    ) -> None:
        _bootstrap_admin(registry)
        registry.register_or_get(ALICE, "waypoint")  # lands PENDING here
        registry.approve(ALICE, "eigan", by_did=ADMIN)  # but APPROVED here

        assert registry.is_established(ALICE) is True

    def test_revoked_did_is_no_longer_established(self, registry: DIDRegistry) -> None:
        _bootstrap_admin(registry)
        registry.approve(ALICE, "eigan", by_did=ADMIN)
        assert registry.is_established(ALICE) is True

        registry.revoke(ALICE, "eigan", by_did=ADMIN)

        assert registry.is_established(ALICE) is False

    def test_did_authorized_only_via_owner_shortcut_is_not_established(
        self, registry: DIDRegistry
    ) -> None:
        """register_or_get's owner/org shortcut deliberately writes
        nothing for the DID itself (see its own docstring) — so a DID
        that's only ever been resolved through an owner/org grant, never
        landing an APPROVED status of its own, correctly still reads as
        'not established' here.
        """
        _bootstrap_admin(registry)
        registry.approve(owner_key("james"), "eigan", by_did=ADMIN)

        registry.register_or_get(ALICE, "eigan", owner_id="james")

        assert registry.is_established(ALICE) is False
