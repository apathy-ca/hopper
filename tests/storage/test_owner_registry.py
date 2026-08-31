"""Tests for OwnerRegistry (Phase A of Owner-Identity-and-Instance-Discovery-Plan.md).

Phase A is pure CRUD — no authorization behavior. These tests cover the
registry in isolation: create/list/get, email aliasing (the multi-email
requirement — one owner, several addresses), DID linking, and the
conflicting-claim rejection the design doc leans toward for v1.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hopper.upstream.storage import OwnerRegistry


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

        found = registry.get_by_did("did:key:zAbc123")

        assert found is not None
        assert found.id == "james"

    def test_get_by_did_unlinked_returns_none(self, registry: OwnerRegistry) -> None:
        assert registry.get_by_did("did:key:znotlinked") is None

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
        assert registry.get_by_did("did:key:zShared").id == "james"  # type: ignore[union-attr]

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
        assert registry.get_by_did("did:key:zAbc123") is None

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
        assert registry.get_by_did("did:key:zShared").id == "sarah"  # type: ignore[union-attr]


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

    def test_list_all_does_not_include_the_index_file_as_an_owner(
        self, registry: OwnerRegistry
    ) -> None:
        registry.create("james", "james@eigan.ai")

        owners = registry.list_all()

        assert len(owners) == 1
        assert owners[0].id == "james"


class TestGet:
    def test_get_unknown_owner_returns_none(self, registry: OwnerRegistry) -> None:
        assert registry.get("nobody") is None
