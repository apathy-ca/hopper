"""Endpoint-level regression coverage for round-7 findings on PR
owner-identity-instance-discovery -- the revoke-residual-grant fixes
themselves have direct storage-layer coverage in
tests/storage/test_did_registry_owner_fallthrough.py
(TestRevokeOwnResidualGrantDoesNotSilentlyNoOp); this file covers the
server.py-layer finding: invite_revoke's existence-before-authority
ordering, using the real FastAPI app (TestClient + signed requests), same
pattern as test_upstream_server_round6.py.
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


class TestInviteRevokeExistenceOracleCollapsedForNonAdmins:
    def test_unknown_prefix_gives_a_non_admin_the_same_403_as_a_real_ambiguous_or_unowned_one(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        stranger = generate_did_key()
        signed(client, "POST", "/sync", stranger, _sync_body())  # PENDING, never approved

        unknown = signed(
            client, "POST", "/invite/revoke", stranger, {"token_hash_prefix": "deadbeef"}
        )
        assert unknown.status_code == 403

    def test_real_invite_not_issued_by_or_approvable_by_stranger_is_also_403_not_400_or_404(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        stranger = generate_did_key()
        signed(client, "POST", "/sync", stranger, _sync_body())

        created = signed(
            client,
            "POST",
            "/invite/create",
            admin_key,
            {"kind": "namespace", "namespace": "eigan"},
        )
        assert created.status_code == 200
        token_hash = created.json()["invite"]["token_hash"]

        r = signed(
            client,
            "POST",
            "/invite/revoke",
            stranger,
            {"token_hash_prefix": token_hash[:8]},
        )

        assert r.status_code == 403

    def test_admin_still_gets_a_real_404_for_an_unknown_prefix(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        r = signed(client, "POST", "/invite/revoke", admin_key, {"token_hash_prefix": "deadbeef"})
        assert r.status_code == 404

    def test_admin_can_still_revoke_a_real_invite(
        self, client: TestClient, admin_key: DIDKey
    ) -> None:
        created = signed(
            client,
            "POST",
            "/invite/create",
            admin_key,
            {"kind": "namespace", "namespace": "eigan"},
        )
        token_hash = created.json()["invite"]["token_hash"]

        r = signed(
            client,
            "POST",
            "/invite/revoke",
            admin_key,
            {"token_hash_prefix": token_hash[:8]},
        )

        assert r.status_code == 200

    def test_issuer_can_still_revoke_their_own_invite(
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

        created = signed(
            client,
            "POST",
            "/invite/create",
            approver,
            {"kind": "namespace", "namespace": "eigan"},
        )
        assert created.status_code == 200
        token_hash = created.json()["invite"]["token_hash"]

        r = signed(
            client,
            "POST",
            "/invite/revoke",
            approver,
            {"token_hash_prefix": token_hash[:8]},
        )

        assert r.status_code == 200
