"""Tests for OAuth 2.1 + MCP authorization flow.

Covers metadata discovery, RFC 7591 client registration, the authorization
code + PKCE flow (including the paste-bearer-token user auth step), token
issuance, and audience binding at the MCP SSE auth layer.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hopper.api.app import create_app
from hopper.api import mcp_tokens as mcp_tokens_mod
from hopper.api import oauth_store as oauth_store_mod


@pytest.fixture
def isolated_stores(tmp_path: Path, monkeypatch):
    """Point both token stores at a tmp dir and reset the singletons."""
    monkeypatch.setenv("HOPPER_SERVER_PATH", str(tmp_path))
    monkeypatch.setenv("HOPPER_PUBLIC_URL", "https://test.example.com")
    mcp_tokens_mod._store = None
    oauth_store_mod._store = None
    yield tmp_path
    mcp_tokens_mod._store = None
    oauth_store_mod._store = None


@pytest.fixture
def client(isolated_stores) -> TestClient:
    return TestClient(create_app(), base_url="https://test.example.com")


@pytest.fixture
def bearer_token(isolated_stores) -> tuple[str, str]:
    """Create a registered hpr_ token. Returns (token, did)."""
    store = mcp_tokens_mod.get_token_store()
    did = "did:key:z6MkTestDIDFor OAuth"
    token = store.generate_token(did=did, label="test", instance="default")
    return token, did


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


def _register_client(client: TestClient) -> str:
    resp = client.post(
        "/oauth/register",
        json={
            "client_name": "Claude Web",
            "redirect_uris": ["https://claude.ai/callback"],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "scope": "mcp",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_endpoint_auth_method"] == "none"
    return body["client_id"]


class TestMetadata:
    def test_protected_resource_metadata(self, client: TestClient):
        resp = client.get("/.well-known/oauth-protected-resource")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource"] == "https://test.example.com"
        assert body["authorization_servers"] == ["https://test.example.com"]
        assert "mcp" in body["scopes_supported"]

    def test_authorization_server_metadata(self, client: TestClient):
        resp = client.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        body = resp.json()
        assert body["issuer"] == "https://test.example.com"
        assert body["authorization_endpoint"].endswith("/oauth/authorize")
        assert body["token_endpoint"].endswith("/oauth/token")
        assert body["registration_endpoint"].endswith("/oauth/register")
        assert "S256" in body["code_challenge_methods_supported"]
        assert "authorization_code" in body["grant_types_supported"]
        assert "none" in body["token_endpoint_auth_methods_supported"]


class TestClientRegistration:
    def test_registration_returns_client_id(self, client: TestClient):
        client_id = _register_client(client)
        assert client_id.startswith("hpc_")

    def test_registration_requires_redirect_uris(self, client: TestClient):
        resp = client.post("/oauth/register", json={"client_name": "x"})
        assert resp.status_code == 422


class TestAuthorize:
    def test_get_shows_form(self, client: TestClient):
        client_id = _register_client(client)
        _, challenge = _pkce()
        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "mcp",
                "state": "xyz",
                "resource": "https://test.example.com",
            },
        )
        assert resp.status_code == 200
        assert "bearer_token" in resp.text
        assert "Claude Web" in resp.text

    def test_rejects_non_s256_challenge(self, client: TestClient):
        client_id = _register_client(client)
        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "response_type": "code",
                "code_challenge": "xxx",
                "code_challenge_method": "plain",
                "resource": "https://test.example.com",
            },
        )
        assert resp.status_code == 400

    def test_rejects_unregistered_redirect(self, client: TestClient):
        client_id = _register_client(client)
        _, challenge = _pkce()
        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://attacker.example.com/cb",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://test.example.com",
            },
        )
        assert resp.status_code == 400

    def test_rejects_wrong_resource(self, client: TestClient):
        client_id = _register_client(client)
        _, challenge = _pkce()
        resp = client.get(
            "/oauth/authorize",
            params={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://otherhost.example.com",
            },
        )
        assert resp.status_code == 400

    def test_post_with_valid_bearer_issues_code(
        self, client: TestClient, bearer_token
    ):
        token, _did = bearer_token
        client_id = _register_client(client)
        _, challenge = _pkce()
        resp = client.post(
            "/oauth/authorize",
            data={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "mcp",
                "state": "abc",
                "resource": "https://test.example.com",
                "bearer_token": token,
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        loc = resp.headers["location"]
        assert loc.startswith("https://claude.ai/callback")
        assert "code=hpa_" in loc
        assert "state=abc" in loc

    def test_post_with_bad_bearer_returns_401(self, client: TestClient):
        client_id = _register_client(client)
        _, challenge = _pkce()
        resp = client.post(
            "/oauth/authorize",
            data={
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "response_type": "code",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "mcp",
                "state": "",
                "resource": "https://test.example.com",
                "bearer_token": "hpr_not_a_real_token",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert "Invalid or unknown bearer token" in resp.text


def _complete_to_code(client: TestClient, client_id: str, token: str) -> tuple[str, str]:
    """Run authorize POST and return (code, code_verifier)."""
    verifier, challenge = _pkce()
    resp = client.post(
        "/oauth/authorize",
        data={
            "client_id": client_id,
            "redirect_uri": "https://claude.ai/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "mcp",
            "state": "s",
            "resource": "https://test.example.com",
            "bearer_token": token,
        },
        follow_redirects=False,
    )
    loc = resp.headers["location"]
    code = loc.split("code=")[1].split("&")[0]
    return code, verifier


class TestToken:
    def test_exchange_code_for_access_token(self, client: TestClient, bearer_token):
        token, did = bearer_token
        client_id = _register_client(client)
        code, verifier = _complete_to_code(client, client_id, token)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "resource": "https://test.example.com",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["access_token"].startswith("hpo_")
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] > 0
        assert body["resource"] == "https://test.example.com"

        # The issued token resolves to the original DID.
        rec = oauth_store_mod.get_oauth_store().lookup_access_token(body["access_token"])
        assert rec is not None
        assert rec["did"] == did

    def test_code_is_single_use(self, client: TestClient, bearer_token):
        token, _ = bearer_token
        client_id = _register_client(client)
        code, verifier = _complete_to_code(client, client_id, token)

        body = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": "https://claude.ai/callback",
            "resource": "https://test.example.com",
        }
        first = client.post("/oauth/token", data=body)
        assert first.status_code == 200
        second = client.post("/oauth/token", data=body)
        assert second.status_code == 400
        assert second.json()["error"] == "invalid_grant"

    def test_pkce_mismatch_rejected(self, client: TestClient, bearer_token):
        token, _ = bearer_token
        client_id = _register_client(client)
        code, _verifier = _complete_to_code(client, client_id, token)

        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": "wrong-verifier-value-xxxxxxxxxxxxxxx",
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "resource": "https://test.example.com",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    def test_wrong_client_rejected(self, client: TestClient, bearer_token):
        token, _ = bearer_token
        client_id = _register_client(client)
        code, verifier = _complete_to_code(client, client_id, token)

        other_client = _register_client(client)
        resp = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": other_client,
                "redirect_uri": "https://claude.ai/callback",
                "resource": "https://test.example.com",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_grant"

    def test_unsupported_grant_type(self, client: TestClient):
        resp = client.post(
            "/oauth/token",
            data={"grant_type": "password"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "unsupported_grant_type"


class TestSSEAudienceBinding:
    def test_oauth_token_accepted_with_matching_audience(
        self, client: TestClient, bearer_token, monkeypatch
    ):
        """An hpo_ token whose resource matches the server is accepted by _check_auth."""
        from hopper.api import mcp_sse

        token, _ = bearer_token
        client_id = _register_client(client)
        code, verifier = _complete_to_code(client, client_id, token)
        exchange = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "resource": "https://test.example.com",
            },
        )
        access_token = exchange.json()["access_token"]

        # Force auth_required so missing-auth doesn't short-circuit.
        monkeypatch.setattr(mcp_sse, "MCP_DID_OPEN_ACCESS", True)

        class FakeURL:
            scheme = "https"
            netloc = "test.example.com"
            path = "/mcp/sse/"

        class FakeRequest:
            headers = {"Authorization": f"Bearer {access_token}"}
            method = "GET"
            url = FakeURL()

        err, did, _inst = mcp_sse._check_auth(FakeRequest())
        assert err is None, err.body if err else ""
        assert did is not None

    def test_oauth_token_rejected_on_audience_mismatch(
        self, client: TestClient, bearer_token, monkeypatch
    ):
        from hopper.api import mcp_sse

        token, _ = bearer_token
        client_id = _register_client(client)
        code, verifier = _complete_to_code(client, client_id, token)
        exchange = client.post(
            "/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": client_id,
                "redirect_uri": "https://claude.ai/callback",
                "resource": "https://test.example.com",
            },
        )
        access_token = exchange.json()["access_token"]

        # Point the server's idea of canonical URL somewhere else.
        monkeypatch.setenv("HOPPER_PUBLIC_URL", "https://different.example.com")
        monkeypatch.setattr(mcp_sse, "MCP_DID_OPEN_ACCESS", True)

        class FakeURL:
            scheme = "https"
            netloc = "different.example.com"
            path = "/mcp/sse/"

        class FakeRequest:
            headers = {"Authorization": f"Bearer {access_token}"}
            method = "GET"
            url = FakeURL()

        err, _did, _inst = mcp_sse._check_auth(FakeRequest())
        assert err is not None
        assert err.status_code == 401

    def test_unauth_request_includes_resource_metadata_hint(
        self, monkeypatch
    ):
        """401 responses must advertise RFC 9728 metadata URL for client discovery."""
        from hopper.api import mcp_sse

        monkeypatch.setenv("HOPPER_PUBLIC_URL", "https://test.example.com")
        monkeypatch.setattr(mcp_sse, "MCP_DID_OPEN_ACCESS", True)

        class FakeURL:
            scheme = "https"
            netloc = "test.example.com"
            path = "/mcp/sse/"

        class FakeRequest:
            headers = {}  # no auth
            method = "GET"
            url = FakeURL()

        err, _did, _inst = mcp_sse._check_auth(FakeRequest())
        assert err is not None
        assert err.status_code == 401
        www_auth = err.headers["www-authenticate"]
        assert "resource_metadata=" in www_auth
        assert "/.well-known/oauth-protected-resource" in www_auth
