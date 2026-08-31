"""Regression coverage for a round-6 finding on PR
owner-identity-instance-discovery: every UpstreamClient method's catch-all
HTTPStatusError branch discarded the response body entirely, building its
error message from the bare status code -- so a 404's actionable detail
(e.g. ``_check_grant_target_exists``'s "owner 'jhenrry' not found") never
reached the caller. ``_detail_or`` centralizes surfacing it.
"""

from __future__ import annotations

import httpx

from hopper.upstream.client import _detail_or


def _response(status: int, json_body=None, text: str = "") -> httpx.Response:
    content = httpx.Response(status, json=json_body, text=text if json_body is None else None)
    return content


class TestDetailOr:
    def test_returns_detail_when_present(self) -> None:
        r = _response(404, json_body={"detail": "owner 'jhenrry' not found"})
        assert _detail_or(r, "fallback") == "owner 'jhenrry' not found"

    def test_falls_back_when_no_detail_key(self) -> None:
        r = _response(404, json_body={"other": "field"})
        assert _detail_or(r, "fallback") == "fallback"

    def test_falls_back_on_non_json_body(self) -> None:
        r = _response(500, text="internal server error, not json")
        assert _detail_or(r, "fallback") == "fallback"

    def test_falls_back_when_body_is_a_json_list_not_a_dict(self) -> None:
        r = _response(422, json_body=["some", "validation", "errors"])
        assert _detail_or(r, "fallback") == "fallback"

    def test_falls_back_on_empty_body(self) -> None:
        r = _response(404, text="")
        assert _detail_or(r, "fallback") == "fallback"
