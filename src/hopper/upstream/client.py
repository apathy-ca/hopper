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
    ) -> httpx.Response:
        """Make a signed HTTP request."""
        url = f"{self.server_url}{path}"

        # Serialize body consistently (must match sign_request)
        if body is not None:
            body_bytes = json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        else:
            body_bytes = b""

        # Sign the request
        auth_header = sign_request(
            did_key=self.did_key,
            method=method,
            path=path,
            body=body_bytes,
        )

        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=self.timeout) as client:
            if method == "GET":
                response = client.get(url, headers=headers)
            elif method == "POST":
                response = client.post(url, headers=headers, content=body_bytes)
            else:
                raise ValueError(f"Unsupported method: {method}")

        return response

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
            path = f"/admin/dids?namespace={namespace}" if namespace else "/admin/dids"
            response = self._make_request("GET", path)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can list DIDs") from e
            raise UpstreamError(f"Failed to list DIDs: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_pending(self, namespace: str | None = None) -> dict:
        """List pending DIDs awaiting approval. Requires admin."""
        try:
            path = f"/admin/pending?namespace={namespace}" if namespace else "/admin/pending"
            response = self._make_request("GET", path)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can view pending DIDs") from e
            raise UpstreamError(f"Failed to list pending: {e.response.status_code}") from e
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
                raise NotAdminError(e.response.json().get("detail", "Not authorized")) from e
            raise UpstreamError(f"Failed to approve: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def create_invite(
        self,
        namespace: str,
        role: str = "approved",
        expires_in_ms: int | None = None,
        max_uses: int = 1,
    ) -> dict:
        """Create an invite token. Returns {'token': ..., 'invite': {...}}.

        Admin can invite for any namespace/role. Approvers can invite role=approved
        on their own namespace.
        """
        try:
            response = self._make_request(
                "POST",
                "/invite/create",
                body={
                    "namespace": namespace,
                    "role": role,
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
                raise NotAdminError(e.response.json().get("detail", "Not authorized")) from e
            raise UpstreamError(f"Failed to create invite: {e.response.status_code}") from e
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
                raise NotAuthorizedError(e.response.json().get("detail", "redeem failed")) from e
            raise UpstreamError(f"Failed to redeem: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

    def list_invites(self, namespace: str | None = None) -> dict:
        """List invites. Admin sees all; approvers see invites for their namespaces."""
        try:
            path = f"/invite/list?namespace={namespace}" if namespace else "/invite/list"
            response = self._make_request("GET", path)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed") from e
            raise UpstreamError(f"Failed to list invites: {e.response.status_code}") from e
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
                raise NotAdminError(e.response.json().get("detail", "Not authorized")) from e
            raise UpstreamError(f"Failed to revoke invite: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e

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
                raise NotAdminError(e.response.json().get("detail", "Not authorized")) from e
            raise UpstreamError(f"Failed to revoke: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}") from e
