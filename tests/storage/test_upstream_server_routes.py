"""Route-registration sanity check for the upstream sync server.

Exists because of a real bug caught during the code-review pass on PR
owner-identity-instance-discovery: a ``@router.post("/admin/approve")``
decorator ended up attached to a plain helper function
(``_check_grant_target_exists``) that was inserted directly above
``approve_did`` during an edit, instead of to ``approve_did`` itself. The
result was a 500 on every single call to ``/admin/approve`` — a complete,
silent route hijack that no unit test caught because nothing exercised
route registration; it only surfaced running a live server by hand.

This doesn't need a running server or DID signing — just building the
FastAPI app and checking each path resolves to the function whose name
matches what the endpoint is supposed to do. Cheap, and it would have
caught that bug in under a second instead of requiring a live smoke test.
"""

from __future__ import annotations

from hopper.upstream.server import _build_standalone_app

EXPECTED_ROUTES = {
    ("POST", "/sync"): "sync",
    ("GET", "/me"): "whoami_me",
    ("GET", "/admin/dids"): "list_dids",
    ("GET", "/admin/pending"): "list_pending",
    ("POST", "/admin/approve"): "approve_did",
    ("POST", "/admin/revoke"): "revoke_did",
    ("POST", "/admin/owners"): "create_owner",
    ("GET", "/admin/owners"): "list_owners",
    ("GET", "/admin/owners/{owner_id}"): "get_owner",
    ("POST", "/admin/owners/add-email"): "add_owner_email",
    ("POST", "/admin/owners/link-did"): "link_owner_did",
    ("POST", "/admin/owners/unlink-did"): "unlink_owner_did",
    ("GET", "/admin/instances"): "owner_instances",
    ("POST", "/admin/orgs"): "create_org",
    ("GET", "/admin/orgs"): "list_orgs",
    ("GET", "/admin/orgs/{org_id}"): "get_org",
    ("POST", "/admin/orgs/add-member"): "add_org_member",
    ("POST", "/admin/orgs/remove-member"): "remove_org_member",
    ("GET", "/admin/orgs/{org_id}/instances"): "org_instances",
    ("POST", "/invite/create"): "invite_create",
    ("POST", "/invite/redeem"): "invite_redeem",
    ("GET", "/invite/list"): "invite_list",
    ("POST", "/invite/revoke"): "invite_revoke",
}


def _route_map() -> dict[tuple[str, str], str]:
    app = _build_standalone_app()
    mapping: dict[tuple[str, str], str] = {}
    for route in app.routes:
        if not hasattr(route, "methods") or not hasattr(route, "path"):
            continue
        for method in route.methods:
            if method == "HEAD":
                continue
            mapping[(method, route.path)] = route.endpoint.__name__
    return mapping


def test_every_expected_route_maps_to_the_right_handler() -> None:
    actual = _route_map()
    for (method, path), expected_handler in EXPECTED_ROUTES.items():
        assert (method, path) in actual, f"{method} {path} is not registered at all"
        assert actual[(method, path)] == expected_handler, (
            f"{method} {path} routes to '{actual[(method, path)]}', "
            f"expected '{expected_handler}' — a decorator likely landed on "
            "the wrong function"
        )


def test_no_unexpected_routes_beyond_health_and_the_expected_set() -> None:
    """Catches the inverse mistake too: an endpoint accidentally left
    undecorated (so it silently isn't registered) would show up here as a
    route count mismatch against EXPECTED_ROUTES, one entry short."""
    actual = _route_map()
    auto_generated = {"/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
    filtered = {k: v for k, v in actual.items() if k[1] not in auto_generated}
    assert filtered == EXPECTED_ROUTES
