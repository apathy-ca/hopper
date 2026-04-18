"""MCP authentication API endpoints.

Provides endpoints for MCP token registration and management using DID authentication.
Tokens issued here can be used as Bearer tokens for MCP SSE connections from
Claude Web and other MCP clients.

Authentication:
    All endpoints require DID authentication via the Authorization header:
    Authorization: DID <did:key:z6Mk...> <base64-signature>

Endpoints:
    POST /mcp/register - Register a new Bearer token for the authenticated DID
    GET /mcp/tokens - List tokens for the authenticated DID
    DELETE /mcp/tokens/{token_prefix} - Revoke a token by its prefix
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from hopper.api.mcp_tokens import get_token_store
from hopper.upstream.did import verify_signature

if TYPE_CHECKING:
    pass


router = APIRouter(prefix="/mcp", tags=["MCP Auth"])


# =============================================================================
# Request/Response Models
# =============================================================================


class TokenRegisterRequest(BaseModel):
    """Request body for token registration."""

    label: str = Field(
        default="",
        description="Optional label for the token (e.g., 'claude-web')",
        max_length=64,
    )
    instance: str = Field(
        default="default",
        description="Instance name (e.g., 'work', 'personal')",
        max_length=64,
    )
    instance_path: str | None = Field(
        default=None,
        description="Path to instance storage directory (e.g., '/home/user/projects/myproject/.hopper')",
    )


class TokenRegisterResponse(BaseModel):
    """Response from token registration."""

    token: str = Field(description="The Bearer token to use for MCP authentication")
    did: str = Field(description="The DID that owns this token")
    instance: str = Field(description="The instance this token is for")
    message: str = Field(description="Instructions for using the token")


class TokenInfo(BaseModel):
    """Information about a token (without the full token value)."""

    token_prefix: str = Field(description="First 12 characters of the token")
    did: str = Field(description="The DID that owns this token")
    instance: str = Field(description="Instance name")
    instance_path: str | None = Field(description="Instance storage path")
    label: str = Field(description="User-provided label")
    created_at: int = Field(description="Unix timestamp of creation")
    last_used_at: int = Field(description="Unix timestamp of last use")


class TokenListResponse(BaseModel):
    """Response from listing tokens."""

    tokens: list[TokenInfo]
    count: int


class TokenRevokeResponse(BaseModel):
    """Response from revoking a token."""

    revoked: bool
    token_prefix: str
    message: str


# =============================================================================
# Authentication Dependency
# =============================================================================


async def verify_did_auth(request: Request) -> str:
    """Dependency to verify DID auth and return the authenticated DID.

    Extracts the DID and signature from the Authorization header,
    verifies the signature against the request, and returns the DID
    if valid.

    Args:
        request: The FastAPI request object

    Returns:
        The verified DID string

    Raises:
        HTTPException: 401 if auth is missing or invalid
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("DID "):
        raise HTTPException(
            status_code=401,
            detail="DID auth required. Use 'Authorization: DID <did> <signature>'",
            headers={"WWW-Authenticate": "DID"},
        )

    # Read request body for signature verification
    body = await request.body()

    # Verify the signature
    valid, did = verify_signature(
        auth_header=auth_header,
        method=request.method,
        path=request.url.path,
        body=body,
    )

    if not valid or not did:
        raise HTTPException(
            status_code=401,
            detail="Invalid DID signature",
            headers={"WWW-Authenticate": "DID"},
        )

    return did


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/register", response_model=TokenRegisterResponse)
async def register_token(
    request: Request,
    body: TokenRegisterRequest | None = None,
    did: str = Depends(verify_did_auth),
) -> TokenRegisterResponse:
    """Register a new Bearer token for the authenticated DID.

    Creates a new Bearer token that can be used for MCP SSE authentication.
    The token is returned only once - store it securely.

    The token should be added to Claude Web config as:
    ```json
    {
        "mcp_servers": [{
            "type": "url",
            "url": "https://your-server.com/mcp/sse/",
            "name": "hopper",
            "authorization_token": "hpr_..."
        }]
    }
    ```

    Args:
        request: The FastAPI request object
        body: Optional request body with label
        did: The authenticated DID (from dependency)

    Returns:
        The generated token and usage instructions
    """
    label = body.label if body else ""
    instance = body.instance if body else "default"
    instance_path = body.instance_path if body else None

    store = get_token_store()
    token = store.generate_token(
        did=did,
        label=label,
        instance=instance,
        instance_path=instance_path,
    )

    return TokenRegisterResponse(
        token=token,
        did=did,
        instance=instance,
        message="Token created. Add to Claude Web config as authorization_token",
    )


@router.get("/tokens", response_model=TokenListResponse)
async def list_tokens(
    request: Request,
    did: str = Depends(verify_did_auth),
) -> TokenListResponse:
    """List tokens for the authenticated DID.

    Returns metadata about all tokens owned by the authenticated DID.
    For security, only the token prefix (first 12 characters) is returned,
    not the full token value.

    Args:
        request: The FastAPI request object
        did: The authenticated DID (from dependency)

    Returns:
        List of token metadata
    """
    store = get_token_store()
    tokens = store.list_tokens(did=did)

    return TokenListResponse(
        tokens=[TokenInfo(**t) for t in tokens],
        count=len(tokens),
    )


@router.delete("/tokens/{token_prefix}", response_model=TokenRevokeResponse)
async def revoke_token(
    token_prefix: str,
    request: Request,
    did: str = Depends(verify_did_auth),
) -> TokenRevokeResponse:
    """Revoke a token by its prefix.

    Revokes the token matching the given prefix (first 12 characters).
    The token must be owned by the authenticated DID.

    Args:
        token_prefix: First 12 characters of the token to revoke
        request: The FastAPI request object
        did: The authenticated DID (from dependency)

    Returns:
        Revocation status

    Raises:
        HTTPException: 404 if token not found or not owned by DID
    """
    # Validate prefix format
    if len(token_prefix) < 8:
        raise HTTPException(
            status_code=400,
            detail="Token prefix must be at least 8 characters",
        )

    store = get_token_store()
    revoked = store.revoke_by_prefix(token_prefix=token_prefix, did=did)

    if not revoked:
        raise HTTPException(
            status_code=404,
            detail=f"Token with prefix '{token_prefix}' not found or not owned by you",
        )

    return TokenRevokeResponse(
        revoked=True,
        token_prefix=token_prefix,
        message="Token revoked successfully",
    )
