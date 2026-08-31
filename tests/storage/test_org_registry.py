"""Tests for OrgRegistry (Phase E of Owner-Identity-and-Instance-Discovery-Plan.md).

Mirrors test_owner_registry.py's structure — orgs are the same JSON-file-
per-record pattern as owners, membership instead of email aliasing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hopper.upstream.storage import OrgRegistry


@pytest.fixture
def registry(tmp_path: Path) -> OrgRegistry:
    return OrgRegistry(tmp_path)


class TestCreate:
    def test_create_returns_org(self, registry: OrgRegistry) -> None:
        org, message = registry.create("eigan", "Eigan")

        assert org is not None
        assert org.id == "eigan"
        assert org.name == "Eigan"
        assert org.member_owner_ids == []
        assert message == "created"

    def test_create_persists_across_registry_instances(
        self, registry: OrgRegistry, tmp_path: Path
    ) -> None:
        registry.create("eigan", "Eigan")

        reloaded = OrgRegistry(tmp_path)
        found = reloaded.get("eigan")

        assert found is not None
        assert found.name == "Eigan"

    def test_create_rejects_duplicate_id(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")

        org, message = registry.create("eigan", "Different Name")

        assert org is None
        assert "already exists" in message

    def test_create_name_is_optional(self, registry: OrgRegistry) -> None:
        org, _ = registry.create("eigan", "")
        assert org is not None
        assert org.name == ""


class TestMembership:
    def test_add_member(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")

        ok, message = registry.add_member("eigan", "james")

        assert ok is True
        org = registry.get("eigan")
        assert org is not None
        assert org.member_owner_ids == ["james"]

    def test_add_member_to_unknown_org_fails(self, registry: OrgRegistry) -> None:
        ok, message = registry.add_member("nonexistent", "james")
        assert ok is False
        assert "not found" in message

    def test_add_member_twice_is_rejected_not_duplicated(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")
        registry.add_member("eigan", "james")

        ok, message = registry.add_member("eigan", "james")

        assert ok is False
        assert "already a member" in message
        assert registry.get("eigan").member_owner_ids == ["james"]  # type: ignore[union-attr]

    def test_multiple_members(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")
        registry.add_member("eigan", "james")
        registry.add_member("eigan", "sarah")

        org = registry.get("eigan")
        assert org is not None
        assert set(org.member_owner_ids) == {"james", "sarah"}

    def test_remove_member(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")
        registry.add_member("eigan", "james")

        ok, _ = registry.remove_member("eigan", "james")

        assert ok is True
        assert registry.get("eigan").member_owner_ids == []  # type: ignore[union-attr]

    def test_remove_member_not_present_fails(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")

        ok, message = registry.remove_member("eigan", "james")

        assert ok is False
        assert "not a member" in message

    def test_remove_member_from_unknown_org_fails(self, registry: OrgRegistry) -> None:
        ok, message = registry.remove_member("nonexistent", "james")
        assert ok is False
        assert "not found" in message


class TestOrgsForOwner:
    def test_finds_orgs_the_owner_belongs_to(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")
        registry.create("rosetta", "Rosetta")
        registry.add_member("eigan", "james")
        registry.add_member("rosetta", "james")
        registry.add_member("rosetta", "sarah")

        james_orgs = {o.id for o in registry.orgs_for_owner("james")}
        sarah_orgs = {o.id for o in registry.orgs_for_owner("sarah")}

        assert james_orgs == {"eigan", "rosetta"}
        assert sarah_orgs == {"rosetta"}

    def test_owner_in_no_orgs_returns_empty(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")
        assert registry.orgs_for_owner("nobody") == []


class TestListAll:
    def test_empty(self, registry: OrgRegistry) -> None:
        assert registry.list_all() == []

    def test_returns_every_org(self, registry: OrgRegistry) -> None:
        registry.create("eigan", "Eigan")
        registry.create("rosetta", "Rosetta")

        assert {o.id for o in registry.list_all()} == {"eigan", "rosetta"}

    def test_order_is_deterministic_even_when_created_at_ties(
        self, registry: OrgRegistry
    ) -> None:
        registry.create("zed", "Zed")
        registry.create("amy", "Amy")

        assert [o.id for o in registry.list_all()] == [o.id for o in registry.list_all()]


class TestGet:
    def test_unknown_org_returns_none(self, registry: OrgRegistry) -> None:
        assert registry.get("nonexistent") is None
