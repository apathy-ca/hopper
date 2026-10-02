"""Tests for the /sync authorization gate and its rejection message."""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from hopper.upstream.did import generate_did_key, sign_request
from hopper.upstream.server import _build_standalone_app, configure_storage


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    configure_storage(tmp_path / "upstream-data")
    with TestClient(_build_standalone_app()) as c:
        yield c


def _sync(client: TestClient, did_key, namespace: str):
    """POST /sync as `did_key` for `namespace`, with no tasks."""
    body = json.dumps(
        {"tasks": [], "since": 0, "client_time": 0, "instance": namespace},
        separators=(",", ":"),
    ).encode()
    return client.post(
        "/sync",
        content=body,
        headers={
            "Authorization": sign_request(did_key, "POST", "/sync", body),
            "Content-Type": "application/json",
        },
    )


def test_first_did_becomes_admin(client):
    """TOFU bootstrap: the first DID to sync is accepted as global admin."""
    assert _sync(client, generate_did_key(), "proj").status_code == 200


def test_second_did_is_rejected_pending_approval(client):
    _sync(client, generate_did_key(), "proj")  # claim admin

    resp = _sync(client, generate_did_key(), "proj")

    assert resp.status_code == 403
    assert "not approved for namespace 'proj'" in resp.json()["detail"]


def test_rejection_names_the_admin_not_the_requester(client):
    """Regression: the message used to interpolate the requester's own DID,
    telling callers to contact themselves."""
    admin = generate_did_key()
    stranger = generate_did_key()
    _sync(client, admin, "proj")

    detail = _sync(client, stranger, "proj").json()["detail"]

    assert admin.did in detail
    assert f"request approval from {admin.did}" in detail
    # The requester's DID still appears, but labelled as theirs to pass along.
    assert f"Your DID is {stranger.did}" in detail


def test_admin_contact_env_var_overrides_admin_did(client, monkeypatch):
    monkeypatch.setenv("HOPPER_UPSTREAM_ADMIN_CONTACT", "webmaster@example.com")
    admin = generate_did_key()
    _sync(client, admin, "proj")

    detail = _sync(client, generate_did_key(), "proj").json()["detail"]

    assert "request approval from webmaster@example.com" in detail
    assert admin.did not in detail
