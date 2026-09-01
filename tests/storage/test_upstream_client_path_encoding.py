"""Regression coverage for a round-9 finding on PR
owner-identity-instance-discovery: get_owner/get_org/get_org_instances
built their request path via raw f-string interpolation
(f"/admin/owners/{owner_id}") instead of percent-encoding the id first,
unlike sibling methods in the same diff that pass the id via ``params=``
for query-based routes. Server-side owner/org ids have no format
validation, so an id containing '/', '?', or '#' silently corrupted or
retargeted the request -- confirmed live: "jhenry/../admin" collapsed to
a request for a *different* owner ("admin") entirely, and
"jhenry?x=evil" had the rest of the id reinterpreted as a query string.

These tests exercise the real UpstreamClient against the real FastAPI app
(FastAPI's TestClient, which routes requests through the app's ASGI
transport with no network involved) so the fix is verified end-to-end:
what the client signs and sends is what the server actually resolves to
the right record. ``_make_request`` is monkeypatched only to swap where
the built, signed request gets *sent* (``TestClient.send`` instead of a
throwaway ``httpx.Client``) -- everything about how the request is built
and signed is the real, unmodified client code, so the fix under test is
still exercised faithfully. This avoids depending on any private
transport attributes or constructing a custom ``httpx.Client`` subclass,
which broke across an httpx/starlette version skew between this
environment and CI on an earlier attempt.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hopper.upstream.client import UpstreamClient
from hopper.upstream.did import generate_did_key, sign_request
from hopper.upstream.server import create_app


@pytest.fixture
def live_client(monkeypatch: pytest.MonkeyPatch) -> UpstreamClient:
    """A real UpstreamClient whose HTTP calls are routed in-process to a
    real FastAPI app via TestClient -- exercises the actual client-side
    path construction and the actual server-side routing/signature
    verification together."""
    storage_path = Path(tempfile.mkdtemp()) / "storage"
    storage_path.mkdir(parents=True)
    app = create_app(storage_path)
    test_client = TestClient(app)

    def _make_request_via_test_client(self, method, path, body=None, params=None):
        # Mirrors UpstreamClient._make_request exactly (see its
        # docstring for why the path+query split matters for signing) --
        # only the final send() target differs.
        body_bytes = (
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
            if body is not None
            else b""
        )
        request = test_client.build_request(
            method, f"http://testserver{path}", params=params, content=body_bytes or None
        )
        signed_path = request.url.path
        if request.url.query:
            signed_path = f"{signed_path}?{request.url.query.decode('ascii')}"
        request.headers["Authorization"] = sign_request(
            did_key=self.did_key, method=method, path=signed_path, body=body_bytes
        )
        request.headers["Content-Type"] = "application/json"
        return test_client.send(request)

    monkeypatch.setattr(UpstreamClient, "_make_request", _make_request_via_test_client)

    admin_key = generate_did_key()
    uc = UpstreamClient(server_url="http://testserver", did_key=admin_key)
    uc.sync(tasks=[], instance="eigan")  # bootstrap admin
    return uc


class TestOwnerOrgPathIdsRoundTripCorrectly:
    @pytest.mark.parametrize(
        "weird_id",
        [
            "jhenry?x=evil",
            "jhenry with space",
            "jhenry&more=stuff",
        ],
    )
    def test_get_owner_resolves_the_exact_id_despite_special_characters(
        self, live_client: UpstreamClient, weird_id: str
    ) -> None:
        live_client.create_owner(weird_id, "weird@example.com")

        result = live_client.get_owner(weird_id)

        assert result["owner"]["id"] == weird_id

    @pytest.mark.parametrize("weird_id", ["eigan?x=evil", "eigan corp"])
    def test_get_org_resolves_the_exact_id_despite_special_characters(
        self, live_client: UpstreamClient, weird_id: str
    ) -> None:
        live_client.create_org(weird_id, name="weird")

        result = live_client.get_org(weird_id)

        assert result["org"]["id"] == weird_id

    def test_get_org_instances_resolves_the_exact_id_despite_special_characters(
        self, live_client: UpstreamClient
    ) -> None:
        weird_id = "eigan?x=evil"
        live_client.create_org(weird_id, name="weird")

        result = live_client.get_org_instances(weird_id)

        assert result["org_id"] == weird_id

    def test_a_slash_containing_id_fails_safely_instead_of_silently_retargeting(
        self, live_client: UpstreamClient
    ) -> None:
        """The specific, most dangerous shape from the finding: an id
        containing '/../' used to silently collapse the request onto a
        *different* real owner. It's fine for this to 404 (Starlette's
        default path converter doesn't span an encoded '/') -- what
        matters is it must NOT silently resolve to someone else's
        record. Deliberately catches any Exception rather than the
        client's own UpstreamError: get_owner's exception *translation*
        depends on the response object being an httpx.Response (it
        pattern-matches on ``httpx.HTTPStatusError``), and this test's
        harness -- not the production fix under test -- can hand back a
        differently-typed but API-compatible response depending on which
        HTTP-client generation the TestClient in the resolved starlette
        version is built on. The claim under test is narrower than that:
        the call must not silently succeed with someone else's data."""
        live_client.create_owner("admin-real-owner", "real@example.com")

        with pytest.raises(Exception) as exc_info:  # noqa: B017
            live_client.get_owner("jhenry/../admin-real-owner")
        assert "not found" in str(exc_info.value).lower()
