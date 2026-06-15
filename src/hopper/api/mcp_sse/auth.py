"""Authentication for the MCP SSE / Streamable HTTP transports.

Supports DID auth, OAuth 2.1 access tokens (hpo_), registered Hopper
tokens (hpr_), and a legacy shared-secret bearer token.
"""

import os
from pathlib import Path

from starlette.responses import JSONResponse


def _canonical_base_url(request) -> str:
    """Server's canonical base URL for audience validation + metadata hints.

    Priority: HOPPER_PUBLIC_URL env var, else the request's scheme+host.
    """
    env = os.getenv("HOPPER_PUBLIC_URL")
    if env:
        return env.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


def _bearer_challenge(request, error: str | None = None) -> dict[str, str]:
    """Build a WWW-Authenticate Bearer challenge with RFC 9728 metadata hint."""
    base = _canonical_base_url(request)
    metadata_url = f"{base}/.well-known/oauth-protected-resource"
    parts = [f'Bearer resource_metadata="{metadata_url}"']
    if error:
        parts.append(f'error="{error}"')
    return {"WWW-Authenticate": ", ".join(parts)}


def _check_auth(
    request, body: bytes = b""
) -> tuple[JSONResponse | None, str | None, Path | None, str | None]:
    """Check authentication (DID, OAuth access token, or legacy Bearer).

    Returns (error_response, authenticated_id, instance_path, instance_name) where:
    - error_response is None if auth passes, or a JSONResponse with 401/403 if it fails
    - authenticated_id is the DID if auth passes
    - instance_path is the storage path for this token's instance (or None)
    - instance_name is the instance name from the token (or None)

    Auth methods (checked in order):
    1. DID auth: `Authorization: DID <did> <signature>`
    2. Bearer hpo_ (OAuth 2.1 access token, resource-bound)
    3. Bearer hpr_ (registered Hopper token)
    4. Bearer <legacy HOPPER_MCP_TOKEN>

    If no auth is configured (no token, no allowed DIDs), allows all requests.
    """
    from hopper.api import mcp_sse as _sse

    auth_header = request.headers.get("Authorization", "")

    # Check if any auth is required
    auth_required = _sse.MCP_AUTH_TOKEN or _sse.MCP_ALLOWED_DIDS or _sse.MCP_DID_OPEN_ACCESS

    if not auth_header:
        if not auth_required:
            return None, None, None, None  # No auth required, allow
        return (
            JSONResponse(
                {"error": "Missing Authorization header"},
                status_code=401,
                headers=_bearer_challenge(request),
            ),
            None,
            None,
            None,
        )

    # Try DID auth first
    if auth_header.startswith("DID "):
        from hopper.upstream.did import verify_signature

        valid, did = verify_signature(
            auth_header=auth_header,
            method=request.method,
            path=request.url.path,
            body=body,
        )
        if not valid or not did:
            return (
                JSONResponse(
                    {"error": "Invalid DID signature"},
                    status_code=401,
                    headers={"WWW-Authenticate": "DID"},
                ),
                None,
                None,
                None,
            )
        if _sse.MCP_ALLOWED_DIDS and did not in _sse.MCP_ALLOWED_DIDS:
            return (
                JSONResponse(
                    {"error": f"DID not authorized: {did}"},
                    status_code=403,
                ),
                None,
                None,
                None,
            )
        # Restore last instance for this DID
        last_instance = None
        try:
            from hopper.upstream.server import get_storage

            storage = get_storage()
            last_instance = storage.did_registry.get_last_instance(did)
        except Exception:
            pass  # Storage not configured or DID not found
        return None, did, None, last_instance

    # Try Bearer token
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

        # OAuth 2.1 access token (issued by /oauth/token)
        if token.startswith("hpo_"):
            from hopper.api.oauth_store import get_oauth_store

            try:
                record = get_oauth_store().lookup_access_token(token)
            except Exception:
                record = None
            if not record:
                return (
                    JSONResponse(
                        {"error": "Invalid or expired access token"},
                        status_code=401,
                        headers=_bearer_challenge(request, error="invalid_token"),
                    ),
                    None,
                    None,
                    None,
                )
            canonical = _canonical_base_url(request)
            recorded = str(record.get("resource", "")).rstrip("/")
            if not (
                recorded == canonical
                or recorded == f"{canonical}/mcp"
                or recorded == f"{canonical}/mcp/sse"
            ):
                return (
                    JSONResponse(
                        {"error": "Token audience does not match this resource"},
                        status_code=401,
                        headers=_bearer_challenge(request, error="invalid_token"),
                    ),
                    None,
                    None,
                    None,
                )
            did = record["did"]
            instance_path = record.get("instance_path")
            instance_name = record.get("instance")
            if instance_path:
                instance_path = Path(instance_path)
                if not instance_path.exists():
                    instance_path = None  # Fall back to upstream lookup by name
            return None, did, instance_path, instance_name

        # Registered hpr_ token (maps to DID + instance)
        if token.startswith("hpr_"):
            from hopper.api.mcp_tokens import get_token_store

            try:
                store = get_token_store()
                token_info = store.lookup_full(token)
                if token_info:
                    did = token_info["did"]
                    instance_path = token_info.get("instance_path")
                    instance_name = token_info.get("instance")
                    if instance_path:
                        instance_path = Path(instance_path)
                        if not instance_path.exists():
                            instance_path = None
                    return None, did, instance_path, instance_name
            except Exception:
                pass
            return (
                JSONResponse(
                    {"error": "Invalid or expired token"},
                    status_code=401,
                    headers=_bearer_challenge(request, error="invalid_token"),
                ),
                None,
                None,
                None,
            )

        # Legacy: check against simple HOPPER_MCP_TOKEN env var
        if _sse.MCP_AUTH_TOKEN and token == _sse.MCP_AUTH_TOKEN:
            import hashlib

            token_id = f"bearer:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
            return None, token_id, None, None

        return (
            JSONResponse(
                {"error": "Invalid token"},
                status_code=401,
                headers=_bearer_challenge(request, error="invalid_token"),
            ),
            None,
            None,
            None,
        )

    return (
        JSONResponse(
            {"error": "Unsupported Authorization scheme. Use 'DID' or 'Bearer'"},
            status_code=401,
            headers=_bearer_challenge(request),
        ),
        None,
        None,
        None,
    )
