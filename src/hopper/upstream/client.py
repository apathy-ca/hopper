"""Upstream sync client.

HTTP client for syncing with an upstream server using DID authentication.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import httpx

from .did import DIDKey, sign_request
from .protocol import SyncRequest, SyncResponse, SyncTask


class UpstreamError(Exception):
    """Error communicating with upstream server."""

    pass


class AuthenticationError(UpstreamError):
    """DID authentication failed."""

    pass


class ConflictError(UpstreamError):
    """Sync conflict occurred."""

    pass


class NotAuthorizedError(UpstreamError):
    """DID not authorized (pending approval)."""

    pass


class NotAdminError(UpstreamError):
    """Operation requires admin privileges."""

    pass


def _detail_or(response: httpx.Response, fallback: str) -> str:
    """The server's JSON ``detail`` field, if the response body has one —
    otherwise ``fallback``.

    Every method's catch-all ``HTTPStatusError`` branch used to build its
    error message from the status code alone (``f"Failed to X:
    {status_code}"``), discarding the response body entirely — including
    detail the server went out of its way to provide, like
    ``_check_grant_target_exists``'s ``"owner 'jhenrry' not found"`` on a
    404 nothing here special-cased. A caller only ever saw a bare status
    code for any status the specific branches above this fallback didn't
    handle.
    """
    try:
        data = response.json()
    except ValueError:
        return fallback
    if isinstance(data, dict):
        return data.get("detail", fallback)
    return fallback


@dataclass
class UpstreamClient:
    """Client for syncing with an upstream server."""

    server_url: str
    did_key: DIDKey
    timeout: int = 30

    def __post_init__(self) -> None:
        """Normalize server URL."""
        self.server_url = self.server_url.rstrip("/")

    def _make_request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a signed HTTP request.

        ``params`` (for a query string, GET requests) are handed to httpx
        directly rather than baked into ``path`` as a hand-built f-string.

        The signature is computed to match exactly what the server's
        ``verify_did_auth`` reconstructs — Starlette decodes a request's
        ``url.path`` but leaves ``url.query`` percent-encoded (confirmed
        live: ``GET /a%20b?x=c%20d`` arrives server-side as
        ``path="/a b"``, ``query="x=c%20d"``, an asymmetry that's
        Starlette's behavior, not a choice made here). httpx's own
        ``request.url.path``/``.query`` have that identical split, so
        signing ``path + "?" + query`` from httpx's parsed request mirrors
        the server's reconstruction byte for byte — regardless of whether
        the varying part sits in the URL path (``get_owner``/``get_org``)
        or the query string (``params=`` above). An earlier version of
        this signed ``request.url.raw_path`` (fully percent-encoded)
        instead, which happened to match for query-only cases but broke
        any path segment containing a character needing encoding — the
        server's decoded ``.path`` and the client's encoded ``raw_path``
        segment could never agree.
        """
        # Serialize body consistently (must match sign_request)
        if body is not None:
            body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        else:
            body_bytes = b""

        with httpx.Client(timeout=self.timeout) as client:
            request = client.build_request(
                method,
                f"{self.server_url}{path}",
                params=params,
                content=body_bytes or None,
            )
            signed_path = request.url.path
            if request.url.query:
                signed_path = f"{signed_path}?{request.url.query.decode('ascii')}"
            auth_header = sign_request(
                did_key=self.did_key,
                method=method,
                path=signed_path,
                body=body_bytes,
            )
            request.headers["Authorization"] = auth_header
            request.headers["Content-Type"] = "application/json"
            response = client.send(request)

        return response

    def me(self) -> dict:
        """Self-information for this client's DID: linked owner (if any),
        admin status. No special authority needed. Used by ``hopper
        init``'s instance-discovery picker (Phase D)."""
        try:
            response = self._make_request("GET", "/me")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to get self info: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def health(self) -> dict:
        """Check server health."""
        try:
            response = self._make_request("GET", "/health")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise UpstreamError(f"Health check failed: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def sync(
        self,
        tasks: list[SyncTask],
        since: int = 0,
        instance: str = "local",
    ) -> SyncResponse:
        """Sync tasks with the server.

        Args:
            tasks: Tasks to push to the server
            since: Timestamp (ms) to get updates from
            instance: Hopper instance name, scopes the pull to this instance

        Returns:
            SyncResponse with server updates and conflict info
        """
        request = SyncRequest(
            since=since,
            tasks=tasks,
            client_time=int(time.time() * 1000),
            instance=instance,
        )

        try:
            response = self._make_request(
                "POST",
                "/sync",
                body=request.model_dump(mode="json"),
            )
            response.raise_for_status()
            return SyncResponse.model_validate(response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAuthorizedError(e.response.text) from e
            raise UpstreamError(f"Sync failed: {e.response.status_code} - {e.response.text}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_dids(self, namespace: str | None = None) -> dict:
        """List all registered DIDs, optionally filtered to a namespace."""
        try:
            params = {"namespace": namespace} if namespace else None
            response = self._make_request("GET", "/admin/dids", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can list DIDs") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to list DIDs: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_pending(self, namespace: str | None = None) -> dict:
        """List pending DIDs awaiting approval. Requires admin."""
        try:
            params = {"namespace": namespace} if namespace else None
            response = self._make_request("GET", "/admin/pending", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can view pending DIDs") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to list pending: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def approve_did(self, target_did: str, namespace: str = "*", role: str = "approved") -> dict:
        """Approve a DID for a namespace.

        Admin may set any role and namespace. An approver may set role=approved
        on their own namespace.
        """
        try:
            response = self._make_request(
                "POST",
                "/admin/approve",
                body={"did": target_did, "namespace": namespace, "role": role},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "Not authorized")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to approve: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def create_invite(
        self,
        namespace: str,
        role: str = "approved",
        expires_in_ms: int | None = None,
        max_uses: int = 1,
    ) -> dict:
        """Create a namespace invite token. Returns {'token': ..., 'invite': {...}}.

        Admin can invite for any namespace/role. Approvers can invite role=approved
        on their own namespace.
        """
        return self._create_invite_raw(
            kind="namespace",
            namespace=namespace,
            role=role,
            expires_in_ms=expires_in_ms,
            max_uses=max_uses,
        )

    def create_device_invite(
        self, owner_id: str, expires_in_ms: int | None = None, max_uses: int = 1
    ) -> dict:
        """Create a device invite — self-service. Mintable by any DID
        already linked to ``owner_id``; redemption links the new DID and
        inherits that owner's grants (Phase C)."""
        return self._create_invite_raw(
            kind="device", owner_id=owner_id, expires_in_ms=expires_in_ms, max_uses=max_uses
        )

    def create_new_owner_invite(
        self, owner_id: str, email: str, expires_in_ms: int | None = None, max_uses: int = 1
    ) -> dict:
        """Create a new-owner invite — admin only. Redemption creates the
        owner and links the redeeming DID as its first device (Phase C)."""
        return self._create_invite_raw(
            kind="new_owner",
            owner_id=owner_id,
            email=email,
            expires_in_ms=expires_in_ms,
            max_uses=max_uses,
        )

    def _create_invite_raw(
        self,
        kind: str,
        namespace: str = "",
        role: str = "approved",
        owner_id: str = "",
        email: str = "",
        expires_in_ms: int | None = None,
        max_uses: int = 1,
    ) -> dict:
        try:
            response = self._make_request(
                "POST",
                "/invite/create",
                body={
                    "kind": kind,
                    "namespace": namespace,
                    "role": role,
                    "owner_id": owner_id,
                    "email": email,
                    "expires_in_ms": expires_in_ms,
                    "max_uses": max_uses,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "Not authorized")) from e
            if e.response.status_code == 404:
                raise UpstreamError(_detail_or(e.response, "not found")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to create invite: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def redeem_invite(self, token: str) -> dict:
        """Redeem an invite token for this client's DID."""
        try:
            response = self._make_request(
                "POST",
                "/invite/redeem",
                body={"token": token},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code in (403, 404):
                raise NotAuthorizedError(_detail_or(e.response, "redeem failed")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to redeem: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_invites(self, namespace: str | None = None) -> dict:
        """List invites. Admin sees all; approvers see invites for their namespaces."""
        try:
            params = {"namespace": namespace} if namespace else None
            response = self._make_request("GET", "/invite/list", params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to list invites: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def revoke_invite(self, token_hash_prefix: str) -> dict:
        """Revoke an invite by token hash prefix."""
        try:
            response = self._make_request(
                "POST",
                "/invite/revoke",
                body={"token_hash_prefix": token_hash_prefix},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "Not authorized")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to revoke invite: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def create_owner(self, owner_id: str, primary_email: str) -> dict:
        """Create a new owner. Admin only."""
        try:
            response = self._make_request(
                "POST",
                "/admin/owners",
                body={"id": owner_id, "primary_email": primary_email},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can create owners") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to create owner: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_owners(self) -> dict:
        """List all owners. Admin only."""
        try:
            response = self._make_request("GET", "/admin/owners")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can list owners") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to list owners: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def get_owner(self, owner_id: str) -> dict:
        """Get one owner by id. Admin only."""
        try:
            response = self._make_request("GET", f"/admin/owners/{owner_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can view owners") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to get owner: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def add_owner_email(self, owner_id: str, email: str) -> dict:
        """Add an email alias to an existing owner. Admin only."""
        try:
            response = self._make_request(
                "POST",
                "/admin/owners/add-email",
                body={"owner_id": owner_id, "email": email},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can edit owners") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to add email: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def link_owner_did(self, owner_id: str, target_did: str) -> dict:
        """Link a DID to an owner. Admin only in Phase A."""
        try:
            response = self._make_request(
                "POST",
                "/admin/owners/link-did",
                body={"owner_id": owner_id, "did": target_did},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can link DIDs to owners") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to link DID: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def unlink_owner_did(self, owner_id: str, target_did: str) -> dict:
        """Unlink a DID from an owner. Admin only."""
        try:
            response = self._make_request(
                "POST",
                "/admin/owners/unlink-did",
                body={"owner_id": owner_id, "did": target_did},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can unlink DIDs from owners") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to unlink DID: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def create_org(self, org_id: str, name: str = "") -> dict:
        """Create a new org. Admin only."""
        try:
            response = self._make_request("POST", "/admin/orgs", body={"id": org_id, "name": name})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can create orgs") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to create org: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_orgs(self) -> dict:
        """List all orgs. Admin only."""
        try:
            response = self._make_request("GET", "/admin/orgs")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can list orgs") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to list orgs: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def get_org(self, org_id: str) -> dict:
        """Get one org. Admin, or any owner who is a member."""
        try:
            response = self._make_request("GET", f"/admin/orgs/{org_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "Not authorized")) from e
            if e.response.status_code == 404:
                raise UpstreamError(_detail_or(e.response, "org not found")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to get org: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def add_org_member(self, org_id: str, owner_id: str) -> dict:
        """Add an owner as a member of an org. Admin only."""
        try:
            response = self._make_request(
                "POST",
                "/admin/orgs/add-member",
                body={"org_id": org_id, "owner_id": owner_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can manage org membership") from e
            if e.response.status_code == 404:
                raise UpstreamError(_detail_or(e.response, "not found")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to add org member: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def remove_org_member(self, org_id: str, owner_id: str) -> dict:
        """Remove an owner from an org. Admin only."""
        try:
            response = self._make_request(
                "POST",
                "/admin/orgs/remove-member",
                body={"org_id": org_id, "owner_id": owner_id},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can manage org membership") from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to remove org member: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def get_org_instances(self, org_id: str) -> dict:
        """Namespaces granted directly to this org (not aggregated across
        members). Admin, or any member owner, can view."""
        try:
            response = self._make_request("GET", f"/admin/orgs/{org_id}/instances")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "Not authorized")) from e
            if e.response.status_code == 404:
                raise UpstreamError(_detail_or(e.response, "org not found")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to get org instances: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def approve_org(self, org_id: str, namespace: str = "*", role: str = "approved") -> dict:
        """Approve an org for a namespace — every member owner's every
        linked DID inherits the grant."""
        from .storage import org_key

        return self.approve_did(org_key(org_id), namespace=namespace, role=role)

    def revoke_org(self, org_id: str, namespace: str = "*") -> dict:
        """Revoke an org's namespace grant (or all with namespace='*')."""
        from .storage import org_key

        return self.revoke_did(org_key(org_id), namespace=namespace)

    def get_owner_instances(self, owner_id: str) -> dict:
        """Every namespace this owner can reach, directly or via any linked
        DID (Phase B). Self-service for the owner's own DIDs; admin can
        query any owner."""
        try:
            response = self._make_request("GET", "/admin/instances", params={"owner": owner_id})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "not authorized")) from e
            if e.response.status_code == 404:
                raise UpstreamError(_detail_or(e.response, "owner not found")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to get owner instances: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def approve_owner(self, owner_id: str, namespace: str = "*", role: str = "approved") -> dict:
        """Approve an owner for a namespace — every DID linked to that
        owner, present and future, inherits the grant. Thin wrapper over
        ``approve_did``: an owner grant is just another key in the same
        namespace registry (see ``upstream.storage.owner_key``)."""
        from .storage import owner_key

        return self.approve_did(owner_key(owner_id), namespace=namespace, role=role)

    def revoke_owner(self, owner_id: str, namespace: str = "*") -> dict:
        """Revoke an owner's namespace grant (or all with namespace='*')."""
        from .storage import owner_key

        return self.revoke_did(owner_key(owner_id), namespace=namespace)

    def revoke_did(self, target_did: str, namespace: str = "*") -> dict:
        """Revoke a DID's access to a namespace (or all if namespace='*'). Requires admin."""
        try:
            response = self._make_request(
                "POST",
                "/admin/revoke",
                body={"did": target_did, "namespace": namespace},
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError(_detail_or(e.response, "Not authorized")) from e
            raise UpstreamError(
                _detail_or(e.response, f"Failed to revoke: {e.response.status_code}")
            ) from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e
