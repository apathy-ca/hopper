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
(TestClient's ASGI transport wired into a real httpx.Client, not a mocked
response) so the fix is verified end-to-end: what the client signs and
sends is what the server actually resolves to the right record.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from hopper.upstream import client as client_mod
from hopper.upstream.client import UpstreamClient
from hopper.upstream.did import generate_did_key
from hopper.upstream.server import create_app


@pytest.fixture
def live_client(monkeypatch: pytest.MonkeyPatch) -> UpstreamClient:
    """A real UpstreamClient whose HTTP calls are routed in-process to a
    real FastAPI app via TestClient's ASGI transport -- exercises the
    actual client-side path construction and the actual server-side
    routing/signature verification together."""
    storage_path = Path(tempfile.mkdtemp()) / "storage"
    storage_path.mkdir(parents=True)
    app = create_app(storage_path)
    test_client = TestClient(app)

    class _TransportBoundClient(httpx.Client):
        def __init__(self, *args, **kwargs):
            kwargs.pop("transport", None)
            super().__init__(
                *args, transport=test_client._transport, base_url="http://testserver", **kwargs
            )

    monkeypatch.setattr(client_mod.httpx, "Client", _TransportBoundClient)

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
        record."""
        live_client.create_owner("admin-real-owner", "real@example.com")

        from hopper.upstream.client import UpstreamError

        # Must raise (a 404, since Starlette's default path converter
        # doesn't span an encoded '/') rather than silently succeeding
        # with someone else's owner record.
        with pytest.raises(UpstreamError):
            live_client.get_owner("jhenry/../admin-real-owner")
