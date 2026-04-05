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
            raise UpstreamError(f"Health check failed: {e.response.status_code}")
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}")

    def sync(
        self,
        tasks: list[SyncTask],
        since: int = 0,
    ) -> SyncResponse:
        """Sync tasks with the server.

        Args:
            tasks: Tasks to push to the server
            since: Timestamp (ms) to get updates from

        Returns:
            SyncResponse with server updates and conflict info
        """
        request = SyncRequest(
            since=since,
            tasks=tasks,
            client_time=int(time.time() * 1000),
        )

        try:
            response = self._make_request(
                "POST",
                "/sync",
                body=request.model_dump(mode="json"),
            )

            if response.status_code == 401:
                raise AuthenticationError("DID authentication failed")

            response.raise_for_status()
            return SyncResponse.model_validate(response.json())

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("DID authentication failed")
            if e.response.status_code == 403:
                raise NotAuthorizedError(e.response.text)
            raise UpstreamError(f"Sync failed: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}")

    def list_dids(self) -> dict:
        """List all registered DIDs."""
        try:
            response = self._make_request("GET", "/admin/dids")
            if response.status_code == 401:
                raise AuthenticationError("DID authentication failed")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise UpstreamError(f"Failed to list DIDs: {e.response.status_code}")
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}")

    def list_pending(self) -> dict:
        """List pending DIDs awaiting approval. Requires admin."""
        try:
            response = self._make_request("GET", "/admin/pending")
            if response.status_code == 401:
                raise AuthenticationError("DID authentication failed")
            if response.status_code == 403:
                raise NotAdminError("Only admin can view pending DIDs")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise NotAdminError("Only admin can view pending DIDs")
            raise UpstreamError(f"Failed to list pending: {e.response.status_code}")
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}")

    def approve_did(self, target_did: str) -> dict:
        """Approve a pending DID. Requires admin."""
        try:
            response = self._make_request(
                "POST",
                "/admin/approve",
                body={"did": target_did},
            )
            if response.status_code == 401:
                raise AuthenticationError("DID authentication failed")
            if response.status_code == 403:
                raise NotAdminError(response.json().get("detail", "Not authorized"))
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise NotAdminError(e.response.json().get("detail", "Not authorized"))
            raise UpstreamError(f"Failed to approve: {e.response.status_code}")
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}")

    def revoke_did(self, target_did: str) -> dict:
        """Revoke a DID's access. Requires admin."""
        try:
            response = self._make_request(
                "POST",
                "/admin/revoke",
                body={"did": target_did},
            )
            if response.status_code == 401:
                raise AuthenticationError("DID authentication failed")
            if response.status_code == 403:
                raise NotAdminError(response.json().get("detail", "Not authorized"))
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                raise NotAdminError(e.response.json().get("detail", "Not authorized"))
            raise UpstreamError(f"Failed to revoke: {e.response.status_code}")
        except httpx.RequestError as e:
            raise UpstreamError(f"Connection error: {e}")
