"""Endpoint-level regression coverage for round-6 findings on PR
owner-identity-instance-discovery, using the real FastAPI app (TestClient
+ signed requests) rather than calling storage-layer functions directly —
these are specifically bugs in how server.py wires request handling
(existence-oracle ordering, validation), not in DIDRegistry/OwnerRegistry
themselves (those have direct unit coverage in test_did_registry_owner_
fallthrough.py's TestRevokeOwnerOrgDerivedAccessDoesNotSilentlyNoOp and
TestApproveRevokeBlocksNonAdminFromOwnerOrgTargets classes).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hopper.upstream.did import DIDKey, generate_did_key, sign_request
from hopper.upstream.server import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    storage_path = tmp_path / "storage"
    storage_path.mkdir(parents=True)
    app = create_app(storage_path)
    return TestClient(app)


def signed(client: TestClient, method: str, path: str, key: DIDKey, body: dict | None = None):
    body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode() if body else b""
    auth = sign_request(key, method, path, body=body_bytes if body else None)
    headers = {"Authorization": auth}
    if method == "GET":
        return client.get(path, headers=headers)
    return client.post(path, headers=headers, content=body_bytes)


def _sync_body() -> dict:
    return {"instance": "eigan", "since": 0, "tasks": [], "client_time": int(time.time() * 1000)}


@pytest.fixture
def admin_key(client: TestClient) -> DIDKey:
    key = generate_did_key()
    r = signed(client, "POST", "/sync", key, _sync_body())
    assert r.status_code == 200
    return key


class TestExistenceOracleCollapsedForNonAdmins:
    """A non-admin, never-approved caller must not be able to distinguish
    'owner/org id does not exist' (404) from 'exists but I have no rights
    to it' (403) -- both now collapse to 403 for these four endpoints."""

    def test_owner_instances_404_and_403_collapse_for_non_admin(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        stranger = generate_did_key()
        signed(client, "POST", "/sync", stranger, _sync_body())  # lands PENDING, never approved

        unknown = signed(client, "GET", "/admin/instances?owner=nobody", stranger)
        real = signed(client, "GET", "/admin/instances?owner=james", stranger)

        assert unknown.status_code == 403
        assert real.status_code == 403  # james doesn't exist yet either, but same response class

        # Now james exists but stranger still isn't linked to it.
        signed(
            client, "POST", "/admin/owners", admin_key, {"id": "james", "primary_email": "j@e.ai"}
        )
        real_exists = signed(client, "GET", "/admin/instances?owner=james", stranger)
        assert real_exists.status_code == 403  # still 403, not 404 -- existence not revealed

    def test_owner_instances_admin_still_gets_404_for_a_real_typo(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        r = signed(client, "GET", "/admin/instances?owner=nobody", admin_key)
        assert r.status_code == 404

    def test_owner_instances_self_service_still_works(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        signed(
            client, "POST", "/admin/owners", admin_key, {"id": "james", "primary_email": "j@e.ai"}
        )
        device = generate_did_key()
        signed(
            client,
            "POST",
            "/admin/owners/link-did",
            admin_key,
            {"owner_id": "james", "did": device.did},
        )

        r = signed(client, "GET", "/admin/instances?owner=james", device)

        assert r.status_code == 200

    def test_get_org_404_and_403_collapse_for_non_admin(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        stranger = generate_did_key()
        signed(client, "POST", "/sync", stranger, _sync_body())

        unknown = signed(client, "GET", "/admin/orgs/nobody-corp", stranger)
        assert unknown.status_code == 403

        signed(client, "POST", "/admin/orgs", admin_key, {"id": "eigan-corp", "name": "Eigan"})
        not_a_member = signed(client, "GET", "/admin/orgs/eigan-corp", stranger)
        assert not_a_member.status_code == 403  # exists, but still 403 not 404

    def test_org_instances_404_and_403_collapse_for_non_admin(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        stranger = generate_did_key()
        signed(client, "POST", "/sync", stranger, _sync_body())

        unknown = signed(client, "GET", "/admin/orgs/nobody-corp/instances", stranger)
        assert unknown.status_code == 403

        signed(client, "POST", "/admin/orgs", admin_key, {"id": "eigan-corp", "name": "Eigan"})
        not_a_member = signed(client, "GET", "/admin/orgs/eigan-corp/instances", stranger)
        assert not_a_member.status_code == 403

    def test_invite_create_device_404_and_403_collapse_for_non_admin(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        stranger = generate_did_key()
        signed(client, "POST", "/sync", stranger, _sync_body())

        unknown = signed(
            client,
            "POST",
            "/invite/create",
            stranger,
            {"kind": "device", "owner_id": "nobody"},
        )
        assert unknown.status_code == 403

        signed(
            client, "POST", "/admin/owners", admin_key, {"id": "james", "primary_email": "j@e.ai"}
        )
        not_linked = signed(
            client,
            "POST",
            "/invite/create",
            stranger,
            {"kind": "device", "owner_id": "james"},
        )
        assert not_linked.status_code == 403  # exists, but stranger isn't linked -- still 403


class TestNewOwnerInviteMaxUsesValidation:
    def test_max_uses_greater_than_one_rejected(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        r = signed(
            client,
            "POST",
            "/invite/create",
            admin_key,
            {"kind": "new_owner", "owner_id": "james", "email": "j@e.ai", "max_uses": 3},
        )
        assert r.status_code == 400

    def test_max_uses_one_still_works(self, client: TestClient, admin_key: DIDKey) -> None:
        r = signed(
            client,
            "POST",
            "/invite/create",
            admin_key,
            {"kind": "new_owner", "owner_id": "james", "email": "j@e.ai", "max_uses": 1},
        )
        assert r.status_code == 200


class TestRevokeBypassEndToEnd:
    def test_revoking_an_owner_derived_did_fails_and_access_persists(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        signed(
            client, "POST", "/admin/owners", admin_key, {"id": "james", "primary_email": "j@e.ai"}
        )
        signed(
            client,
            "POST",
            "/admin/approve",
            admin_key,
            {"did": "owner:james", "namespace": "eigan"},
        )
        device = generate_did_key()
        signed(
            client,
            "POST",
            "/admin/owners/link-did",
            admin_key,
            {"owner_id": "james", "did": device.did},
        )
        # First sync as the device: authorized purely via the owner grant,
        # register_or_get writes no direct per-DID entry for it.
        ok = signed(client, "POST", "/sync", device, _sync_body())
        assert ok.status_code == 200

        revoke = signed(
            client, "POST", "/admin/revoke", admin_key, {"did": device.did, "namespace": "eigan"}
        )

        assert revoke.status_code == 403  # honest failure, not a false "revoked"
        still_works = signed(client, "POST", "/sync", device, _sync_body())
        assert still_works.status_code == 200  # access genuinely persists


class TestApproverCannotGrantOwnerOrgTargets:
    def test_namespace_approver_gets_403_granting_an_owner_key(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        approver = generate_did_key()
        signed(client, "POST", "/sync", approver, _sync_body())
        signed(
            client,
            "POST",
            "/admin/approve",
            admin_key,
            {"did": approver.did, "namespace": "eigan", "role": "approver"},
        )

        r = signed(
            client,
            "POST",
            "/admin/approve",
            approver,
            {"did": "owner:mallory", "namespace": "eigan"},
        )

        assert r.status_code == 403
