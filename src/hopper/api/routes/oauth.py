"""OAuth 2.1 + MCP Authorization endpoints.

Implements the minimum surface needed for Claude Web (claude.ai) to add a
Hopper server as a custom remote MCP connector:

    GET  /.well-known/oauth-protected-resource      RFC 9728 metadata
    GET  /.well-known/oauth-authorization-server    RFC 8414 metadata
    POST /oauth/register                            RFC 7591 dyn client reg
    GET  /oauth/authorize                           Auth code + PKCE, HTML
    POST /oauth/authorize                           Handle bearer paste-back
    POST /oauth/token                               Auth code → access token

User authentication at /authorize is bootstrapped off the existing Hopper
bearer-token store (`hopper mcp init-token`): the user pastes their
hpr_... token, the server resolves it to a DID, and issues an OAuth auth
code bound to that DID + the requested resource.

The resulting hpo_... access tokens are recognized by the MCP SSE endpoint
via hopper.api.oauth_store.get_oauth_store().lookup_access_token.
"""

from __future__ import annotations

import base64
import hashlib
import html
import os
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from hopper.api.mcp_tokens import get_token_store
from hopper.api.oauth_store import (
    ACCESS_TOKEN_TTL_SECONDS,
    CLIENT_PREFIX,
    get_oauth_store,
)

router = APIRouter(tags=["OAuth"])


DEFAULT_SCOPE = "mcp"
SUPPORTED_SCOPES = ["mcp"]


def _public_base_url(request: Request) -> str:
    """Return the canonical base URL the server is reachable at.

    Priority: HOPPER_PUBLIC_URL env var, else the request's scheme+host.
    Trailing slash stripped. This is the value advertised in metadata and
    validated against the OAuth `resource` parameter (RFC 8707).
    """
    env = os.getenv("HOPPER_PUBLIC_URL")
    if env:
        return env.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


def _resource_matches(requested: str, canonical: str) -> bool:
    """Accept the canonical URL or the MCP SSE subpath as valid resource."""
    req = requested.rstrip("/")
    canon = canonical.rstrip("/")
    return req == canon or req == f"{canon}/mcp" or req == f"{canon}/mcp/sse"


# =============================================================================
# Metadata discovery
# =============================================================================


@router.get("/.well-known/oauth-protected-resource")
async def protected_resource_metadata(request: Request) -> dict:
    """RFC 9728 protected resource metadata.

    Advertises this server as the resource and itself as its own
    authorization server. MCP clients use this to locate `/authorize`
    and `/token`.
    """
    base = _public_base_url(request)
    return {
        "resource": f"{base}/mcp/",
        "authorization_servers": [base],
        "scopes_supported": SUPPORTED_SCOPES,
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{base}/docs",
    }


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata(request: Request) -> dict:
    """RFC 8414 authorization server metadata."""
    base = _public_base_url(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": SUPPORTED_SCOPES,
        "service_name": "Hopper",
        "logo_uri": f"{base}/icon-512.png",
    }


# =============================================================================
# Dynamic client registration (RFC 7591)
# =============================================================================


class ClientRegistrationRequest(BaseModel):
    """RFC 7591 dynamic client registration request.

    Extra fields per spec are allowed — we preserve redirect_uris,
    client_name, grant_types, response_types, scope and ignore the rest.
    """

    redirect_uris: list[str] = Field(..., min_length=1)
    client_name: str | None = None
    grant_types: list[str] | None = None
    response_types: list[str] | None = None
    scope: str | None = None
    token_endpoint_auth_method: str | None = None

    model_config = {"extra": "allow"}


@router.post("/oauth/register")
async def register_client(body: ClientRegistrationRequest) -> dict:
    """Dynamic client registration (RFC 7591).

    Returns a public client_id with token_endpoint_auth_method=none.
    PKCE is required at /authorize and /token; no client_secret is issued.
    """
    store = get_oauth_store()
    record = store.register_client(
        client_name=body.client_name or "",
        redirect_uris=body.redirect_uris,
        grant_types=body.grant_types,
        response_types=body.response_types,
        scope=body.scope,
    )
    return {
        "client_id": record["client_id"],
        "client_name": record["client_name"],
        "redirect_uris": record["redirect_uris"],
        "grant_types": record["grant_types"],
        "response_types": record["response_types"],
        "scope": record["scope"],
        "token_endpoint_auth_method": "none",
        "client_id_issued_at": record["created_at"],
    }


# =============================================================================
# Authorization endpoint
# =============================================================================


def _redirect_with_error(redirect_uri: str, error: str, state: str | None) -> RedirectResponse:
    params = {"error": error}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(url=f"{redirect_uri}{sep}{urlencode(params)}", status_code=302)


def _authorize_form_html(
    client_id: str,
    redirect_uri: str,
    response_type: str,
    code_challenge: str,
    code_challenge_method: str,
    scope: str,
    state: str,
    resource: str,
    client_name: str,
    error: str | None = None,
) -> str:
    """Render the paste-bearer-token form for /authorize.

    All user-controlled strings are HTML-escaped — never inject raw URLs
    or scopes into the response body.
    """
    def esc(s: str) -> str:
        return html.escape(s or "", quote=True)

    error_html = f'<p class="err">{esc(error)}</p>' if error else ""
    name = esc(client_name) or "this application"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Authorize {esc(client_name) or 'MCP client'}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 32rem; margin: 3rem auto; padding: 0 1rem; }}
  h1 {{ font-size: 1.25rem; }}
  label {{ display: block; margin-top: 1rem; font-size: 0.9rem; }}
  input[type=text] {{ width: 100%; padding: 0.5rem; font-family: monospace; font-size: 0.9rem; }}
  .err {{ color: #b00; background: #fee; padding: 0.5rem; border-radius: 4px; }}
  .muted {{ color: #666; font-size: 0.85rem; }}
  button {{ margin-top: 1rem; padding: 0.5rem 1rem; }}
  code {{ background: #f4f4f4; padding: 0 0.2rem; }}
</style>
</head>
<body>
<h1>Authorize {name} to access Hopper</h1>
<p class="muted">Resource: <code>{esc(resource)}</code></p>
<p>Paste your Hopper bearer token to grant access. Generate one with
<code>hopper mcp init-token --server &lt;this-server&gt;</code> if you
don't have one.</p>
{error_html}
<form method="post" action="/oauth/authorize">
  <input type="hidden" name="client_id" value="{esc(client_id)}">
  <input type="hidden" name="redirect_uri" value="{esc(redirect_uri)}">
  <input type="hidden" name="response_type" value="{esc(response_type)}">
  <input type="hidden" name="code_challenge" value="{esc(code_challenge)}">
  <input type="hidden" name="code_challenge_method" value="{esc(code_challenge_method)}">
  <input type="hidden" name="scope" value="{esc(scope)}">
  <input type="hidden" name="state" value="{esc(state)}">
  <input type="hidden" name="resource" value="{esc(resource)}">
  <label>Hopper bearer token
    <input type="text" name="bearer_token" autocomplete="off" placeholder="hpr_..." required>
  </label>
  <button type="submit">Authorize</button>
</form>
</body>
</html>"""


def _validate_authorize_params(
    client_id: str,
    redirect_uri: str,
    response_type: str,
    code_challenge: str | None,
    code_challenge_method: str | None,
    resource: str | None,
    request: Request,
) -> tuple[dict, str]:
    """Return (client_record, canonical_resource) or raise HTTPException."""
    if response_type != "code":
        raise HTTPException(400, "unsupported_response_type")
    if not code_challenge:
        raise HTTPException(400, "code_challenge required (PKCE)")
    if code_challenge_method != "S256":
        raise HTTPException(400, "code_challenge_method must be S256")

    store = get_oauth_store()
    client = store.get_client(client_id)
    if not client:
        raise HTTPException(400, "unknown client_id")
    if redirect_uri not in client["redirect_uris"]:
        raise HTTPException(400, "redirect_uri not registered for client")

    canonical = _public_base_url(request)
    if not resource:
        raise HTTPException(400, "resource parameter required (RFC 8707)")
    if not _resource_matches(resource, canonical):
        raise HTTPException(400, f"resource must match {canonical}")
    return client, canonical


@router.get("/oauth/authorize", response_class=HTMLResponse)
async def authorize_get(
    request: Request,
    client_id: Annotated[str, Query()],
    redirect_uri: Annotated[str, Query()],
    response_type: Annotated[str, Query()] = "code",
    code_challenge: Annotated[str | None, Query()] = None,
    code_challenge_method: Annotated[str, Query()] = "S256",
    scope: Annotated[str, Query()] = DEFAULT_SCOPE,
    state: Annotated[str, Query()] = "",
    resource: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    client, _ = _validate_authorize_params(
        client_id, redirect_uri, response_type,
        code_challenge, code_challenge_method, resource, request,
    )
    return HTMLResponse(_authorize_form_html(
        client_id=client_id,
        redirect_uri=redirect_uri,
        response_type=response_type,
        code_challenge=code_challenge or "",
        code_challenge_method=code_challenge_method,
        scope=scope,
        state=state,
        resource=resource or "",
        client_name=client["client_name"],
    ))


@router.post("/oauth/authorize")
async def authorize_post(
    request: Request,
    client_id: Annotated[str, Form()],
    redirect_uri: Annotated[str, Form()],
    response_type: Annotated[str, Form()],
    code_challenge: Annotated[str, Form()],
    code_challenge_method: Annotated[str, Form()],
    resource: Annotated[str, Form()],
    bearer_token: Annotated[str, Form()],
    scope: Annotated[str, Form()] = DEFAULT_SCOPE,
    state: Annotated[str, Form()] = "",
):
    client, _ = _validate_authorize_params(
        client_id, redirect_uri, response_type,
        code_challenge, code_challenge_method, resource, request,
    )

    token_store = get_token_store()
    token_info = token_store.lookup_full(bearer_token.strip())
    if not token_info:
        return HTMLResponse(
            _authorize_form_html(
                client_id=client_id,
                redirect_uri=redirect_uri,
                response_type=response_type,
                code_challenge=code_challenge,
                code_challenge_method=code_challenge_method,
                scope=scope,
                state=state,
                resource=resource,
                client_name=client["client_name"],
                error="Invalid or unknown bearer token. Generate one with `hopper mcp init-token`.",
            ),
            status_code=401,
        )

    oauth_store = get_oauth_store()
    code = oauth_store.create_auth_code(
        client_id=client_id,
        redirect_uri=redirect_uri,
        did=token_info["did"],
        instance=token_info.get("instance", "default"),
        instance_path=token_info.get("instance_path"),
        scope=scope,
        resource=resource,
        code_challenge=code_challenge,
        code_challenge_method=code_challenge_method,
        state=state,
    )
    params = {"code": code}
    if state:
        params["state"] = state
    sep = "&" if "?" in redirect_uri else "?"
    return RedirectResponse(
        url=f"{redirect_uri}{sep}{urlencode(params)}",
        status_code=302,
    )


# =============================================================================
# Token endpoint
# =============================================================================


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return expected == code_challenge


def _token_error(code: str, description: str, status: int = 400) -> JSONResponse:
    return JSONResponse(
        {"error": code, "error_description": description},
        status_code=status,
    )


@router.post("/oauth/token")
async def token_endpoint(
    request: Request,
    grant_type: Annotated[str, Form()],
    code: Annotated[str | None, Form()] = None,
    code_verifier: Annotated[str | None, Form()] = None,
    client_id: Annotated[str | None, Form()] = None,
    redirect_uri: Annotated[str | None, Form()] = None,
    resource: Annotated[str | None, Form()] = None,
):
    if grant_type != "authorization_code":
        return _token_error("unsupported_grant_type", f"Grant type '{grant_type}' not supported")

    if not code or not code_verifier or not client_id or not redirect_uri:
        return _token_error("invalid_request", "Missing required parameter")

    oauth_store = get_oauth_store()
    client = oauth_store.get_client(client_id)
    if not client:
        return _token_error("invalid_client", "Unknown client_id", status=401)

    record = oauth_store.consume_auth_code(code)
    if not record:
        return _token_error("invalid_grant", "Authorization code invalid, expired, or already used")

    if record["client_id"] != client_id:
        return _token_error("invalid_grant", "Code was issued to a different client")
    if record["redirect_uri"] != redirect_uri:
        return _token_error("invalid_grant", "redirect_uri mismatch")
    if resource and record["resource"] != resource:
        return _token_error("invalid_target", "resource mismatch")
    if not _verify_pkce(code_verifier, record["code_challenge"]):
        return _token_error("invalid_grant", "PKCE verification failed")

    access_token, expires_in = oauth_store.create_access_token(
        client_id=client_id,
        did=record["did"],
        instance=record["instance"],
        instance_path=record["instance_path"],
        scope=record["scope"],
        resource=record["resource"],
    )
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": record["scope"],
        "resource": record["resource"],
    }
