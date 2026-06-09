"""Upstream sync server.

FastAPI server that accepts sync requests with DID authentication.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .did import verify_signature
from .protocol import SyncConflict, SyncRequest, SyncResponse
from .storage import GLOBAL_NS, DIDRecord, DIDStatus, Invite, UpstreamStorage


class NamespaceApprovalInfo(BaseModel):
    status: str
    approved_by: str | None = None
    approved_at: int | None = None


class DIDInfo(BaseModel):
    """DID information for API responses."""

    did: str
    created_at: int
    namespaces: dict[str, NamespaceApprovalInfo] = {}


class AdminResponse(BaseModel):
    """Response for admin operations."""

    success: bool
    message: str
    namespace: str | None = None


class DIDListResponse(BaseModel):
    """Response for listing DIDs."""

    admin_did: str | None
    dids: list[DIDInfo]


router = APIRouter()

# Storage instance (configured at startup)
_storage: UpstreamStorage | None = None


def get_storage() -> UpstreamStorage:
    """Get the storage instance."""
    if _storage is None:
        raise HTTPException(status_code=500, detail="Storage not configured")
    return _storage


def configure_storage(
    storage_path: Path,
    shadow_sqlite_url: str | None = None,
) -> None:
    """Configure the storage backend.

    ``shadow_sqlite_url``: optional SQLAlchemy URL. When set, each JSON
    task write also produces a records + revisions pair in the SQL store.
    Shadow writes are fail-soft — failures there never break the JSON
    path. Intended for Phase 4a (second half) rollout on ember.
    """
    global _storage
    shadow_writer = None
    if shadow_sqlite_url:
        from .shadow import RevisionShadowWriter

        shadow_writer = RevisionShadowWriter(shadow_sqlite_url)
    _storage = UpstreamStorage(storage_path, shadow_writer=shadow_writer)


async def verify_did_auth(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    """Verify DID authentication and return the DID."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    # Read body for signature verification
    body = await request.body()

    # Verify signature
    valid, did = verify_signature(
        auth_header=authorization,
        method=request.method,
        path=request.url.path,
        body=body,
    )

    if not valid or not did:
        raise HTTPException(status_code=401, detail="Invalid DID signature")

    return did


@router.post("/sync")
async def sync(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> SyncResponse:
    """Sync tasks with the server.

    Accepts tasks from client, applies last-write-wins conflict resolution,
    and returns tasks updated since the client's 'since' timestamp.

    First DID to connect becomes admin. Subsequent DIDs must be approved.
    """
    # Parse body first so we know the namespace before auth checks
    body = await request.body()
    try:
        sync_req = SyncRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}") from e

    namespace = sync_req.instance

    # Register DID for this namespace if new, check authorization
    status, is_new = storage.did_registry.register_or_get(did, namespace)

    if is_new and status == DIDStatus.ADMIN:
        pass  # First DID — global admin
    elif not storage.did_registry.is_authorized(did, namespace):
        raise HTTPException(
            status_code=403,
            detail=f"DID not approved for namespace '{namespace}'. Contact admin: {did}",
        )

    server_time = int(time.time() * 1000)
    accepted: list[str] = []
    rejected: list[SyncConflict] = []

    # Process incoming tasks
    for task in sync_req.tasks:
        ok, reason = storage.put(task, from_did=did)
        if ok:
            accepted.append(task.id)
        else:
            # Extract server timestamp from index
            server_ts = storage.get_updated_at(task.instance or "local", task.id) or 0
            client_ts = 0
            if task.updated_at:
                if isinstance(task.updated_at, str):
                    from datetime import datetime

                    dt = datetime.fromisoformat(task.updated_at.replace("Z", "+00:00"))
                    client_ts = int(dt.timestamp() * 1000)
                else:
                    client_ts = int(task.updated_at.timestamp() * 1000)

            rejected.append(
                SyncConflict(
                    task_id=task.id,
                    local_updated_at=client_ts,
                    server_updated_at=server_ts,
                    resolution="server_wins",
                )
            )

    # Get tasks updated since client's timestamp, scoped to this instance namespace
    updated_tasks = storage.list_since(sync_req.since, instance=sync_req.instance)

    return SyncResponse(
        tasks=updated_tasks,
        server_time=server_time,
        accepted=accepted,
        rejected=rejected,
    )


def _did_info(record: DIDRecord) -> DIDInfo:
    return DIDInfo(
        did=record.did,
        created_at=record.created_at,
        namespaces={
            ns: NamespaceApprovalInfo(
                status=a.status.value,
                approved_by=a.approved_by,
                approved_at=a.approved_at,
            )
            for ns, a in record.namespaces.items()
        },
    )


@router.get("/admin/dids")
async def list_dids(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
    namespace: str | None = None,
) -> DIDListResponse:
    """List registered DIDs, optionally filtered to a namespace."""
    if not storage.did_registry.is_admin(did):
        raise HTTPException(status_code=403, detail="Only admin can list DIDs")
    records = storage.did_registry.list_all(namespace=namespace)
    return DIDListResponse(
        admin_did=storage.did_registry.admin_did,
        dids=[_did_info(r) for r in records],
    )


@router.get("/admin/pending")
async def list_pending(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
    namespace: str | None = None,
) -> DIDListResponse:
    """List pending DIDs, optionally filtered to a namespace."""
    if not storage.did_registry.is_admin(did):
        raise HTTPException(status_code=403, detail="Only admin can view pending DIDs")
    records = storage.did_registry.list_pending(namespace=namespace)
    return DIDListResponse(
        admin_did=storage.did_registry.admin_did,
        dids=[_did_info(r) for r in records],
    )


class ApproveRequest(BaseModel):
    """Request to approve or revoke a DID."""

    did: str
    namespace: str = "*"  # specific namespace or "*" for all
    role: str = "approved"  # "approved" or "approver"


@router.post("/admin/approve")
async def approve_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Approve a DID for a namespace.

    Admin may set any role for any namespace. Approvers may set role=approved
    on their own namespace only.
    """
    body = await request.body()
    try:
        req = ApproveRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    try:
        role = DIDStatus(req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from e

    success, message = storage.did_registry.approve(
        req.did, namespace=req.namespace, by_did=did, role=role
    )
    if not success:
        raise HTTPException(status_code=403, detail=message)
    return AdminResponse(success=True, message=f"Approved {req.did}: {message}")


@router.post("/admin/revoke")
async def revoke_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Revoke a DID's access to a namespace (or all if namespace='*')."""
    body = await request.body()
    try:
        req = ApproveRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    success, message = storage.did_registry.revoke(req.did, namespace=req.namespace, by_did=did)
    if not success:
        raise HTTPException(status_code=403, detail=message)
    return AdminResponse(success=True, message=f"Revoked {req.did}: {message}")


# --- Invite endpoints ---


class InviteCreateRequest(BaseModel):
    namespace: str
    role: str = "approved"  # "approved" or "approver"
    expires_in_ms: int | None = None  # None = no expiry
    max_uses: int = 1


class InviteInfo(BaseModel):
    token_hash: str
    namespace: str
    role: str
    issued_by: str
    created_at: int
    expires_at: int | None
    max_uses: int
    uses: int


class InviteCreateResponse(BaseModel):
    token: str  # Only returned at creation time
    invite: InviteInfo


class InviteListResponse(BaseModel):
    invites: list[InviteInfo]


class InviteRedeemRequest(BaseModel):
    token: str


class InviteRevokeRequest(BaseModel):
    token_hash_prefix: str


def _invite_info(inv: Invite) -> InviteInfo:
    return InviteInfo(
        token_hash=inv.token_hash,
        namespace=inv.namespace,
        role=inv.role.value,
        issued_by=inv.issued_by,
        created_at=inv.created_at,
        expires_at=inv.expires_at,
        max_uses=inv.max_uses,
        uses=inv.uses,
    )


@router.post("/invite/create")
async def invite_create(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> InviteCreateResponse:
    """Create an invite token.

    Admin may issue any role for any namespace. Approvers may issue role=approved
    on their own namespace only.
    """
    body = await request.body()
    try:
        req = InviteCreateRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    try:
        role = DIDStatus(req.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from e
    if role not in (DIDStatus.APPROVED, DIDStatus.APPROVER):
        raise HTTPException(status_code=400, detail="role must be approved or approver")

    reg = storage.did_registry
    is_admin = reg.is_admin(did)
    if not is_admin:
        if role == DIDStatus.APPROVER:
            raise HTTPException(status_code=403, detail="only admin can issue approver invites")
        if req.namespace == GLOBAL_NS:
            raise HTTPException(status_code=403, detail="only admin can issue global invites")
        if not reg.is_approver(did, req.namespace):
            raise HTTPException(
                status_code=403,
                detail=f"not authorized to invite for namespace '{req.namespace}'",
            )

    if req.max_uses < 1:
        raise HTTPException(status_code=400, detail="max_uses must be >= 1")

    expires_at = None
    if req.expires_in_ms is not None:
        expires_at = int(time.time() * 1000) + req.expires_in_ms

    token, invite = storage.invites.create(
        namespace=req.namespace,
        role=role,
        issued_by=did,
        expires_at=expires_at,
        max_uses=req.max_uses,
    )
    return InviteCreateResponse(token=token, invite=_invite_info(invite))


@router.post("/invite/redeem")
async def invite_redeem(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Redeem an invite token for the caller's DID."""
    body = await request.body()
    try:
        req = InviteRedeemRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    reg = storage.did_registry

    # Fetch invite first to validate before mutating.
    invite_preview = storage.invites.get(req.token)
    if invite_preview is None:
        raise HTTPException(status_code=404, detail="invite not found")

    # Re-check issuer authority at redeem time — admin authority is stable, but
    # an approver could have been revoked between issue and redeem.
    issuer = invite_preview.issued_by
    if not reg.is_admin(issuer):
        if invite_preview.role == DIDStatus.APPROVER:
            raise HTTPException(status_code=403, detail="issuer no longer has approver authority")
        if not reg.is_approver(issuer, invite_preview.namespace):
            raise HTTPException(
                status_code=403,
                detail=f"issuer no longer has approver authority for '{invite_preview.namespace}'",
            )

    if reg.is_admin(did):
        raise HTTPException(status_code=400, detail="admin does not need to redeem invites")

    invite, message = storage.invites.redeem(req.token, by_did=did)
    if invite is None:
        raise HTTPException(status_code=403, detail=message)

    # Register the DID first (creates record if new), then apply the role.
    reg.register_or_get(did, invite.namespace)
    reg.set_status(did, invite.namespace, invite.role, by_did=invite.issued_by)
    return AdminResponse(
        success=True,
        message=f"redeemed: {invite.role.value} on '{invite.namespace}'",
        namespace=invite.namespace,
    )


@router.get("/invite/list")
async def invite_list(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
    namespace: str | None = None,
) -> InviteListResponse:
    """List invites. Admin sees all; approvers see invites for their namespaces."""
    reg = storage.did_registry
    all_invites = storage.invites.list_all(namespace=namespace)

    if reg.is_admin(did):
        visible = all_invites
    else:
        # Approver only sees invites for namespaces they can approve.
        visible = [
            inv
            for inv in all_invites
            if reg.is_approver(did, inv.namespace) or inv.issued_by == did
        ]
    return InviteListResponse(invites=[_invite_info(i) for i in visible])


@router.post("/invite/revoke")
async def invite_revoke(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Revoke an invite by token hash (or unique prefix)."""
    body = await request.body()
    try:
        req = InviteRevokeRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    # Look up first so we can authority-check before revoking.
    reg = storage.did_registry
    matches = [
        p
        for p in storage.invites.invites_dir.glob("*.json")
        if p.stem.startswith(req.token_hash_prefix)
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="no matching invite")
    if len(matches) > 1:
        raise HTTPException(status_code=400, detail=f"ambiguous prefix: {len(matches)} matches")
    invite = storage.invites._load_path(matches[0])
    if invite is None:
        raise HTTPException(status_code=500, detail="invite record corrupt")

    if not reg.is_admin(did):
        if invite.issued_by != did and not reg.is_approver(did, invite.namespace):
            raise HTTPException(status_code=403, detail="not authorized to revoke this invite")

    success, message = storage.invites.revoke(req.token_hash_prefix)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return AdminResponse(success=True, message=message)


def _build_standalone_app() -> FastAPI:
    """Build a standalone FastAPI app that exposes the upstream router.

    Adds a /health endpoint for standalone deployments. When the router is
    included in the main Hopper API (see hopper.api.app), the main app's
    /health is used instead.
    """
    standalone = FastAPI(
        title="Hopper Upstream",
        description="Lightweight sync server for Hopper instances",
        version="0.1.0",
    )

    @standalone.get("/health")
    async def _health() -> dict:
        return {"status": "ok", "time": int(time.time() * 1000)}

    standalone.include_router(router)
    return standalone


# Module-level FastAPI app for standalone deployments (run_server / uvicorn entrypoints).
app = _build_standalone_app()


def create_app(storage_path: Path) -> FastAPI:
    """Create and configure the FastAPI app."""
    configure_storage(storage_path)
    return app


def _init_admin_did(storage_path: Path) -> tuple[str, bool]:
    """Initialize admin DID if not already set.

    Returns (admin_did, is_new).
    """
    from .did import generate_did_key, load_did_key

    admin_key_path = storage_path / "admin.key"

    # Check if admin key already exists
    if admin_key_path.exists():
        did_key = load_did_key(admin_key_path)
        return did_key.did, False

    # Generate new admin key
    did_key = generate_did_key()
    did_key.save(admin_key_path)

    return did_key.did, True


def run_server(
    storage_path: Path,
    # The upstream server is meant to be network-reachable by default.
    host: str = "0.0.0.0",  # nosec B104
    port: int = 8080,
) -> None:
    """Run the upstream server."""
    import uvicorn

    # Ensure storage path exists
    storage_path.mkdir(parents=True, exist_ok=True)

    # Initialize admin DID
    admin_did, is_new = _init_admin_did(storage_path)
    admin_key_path = storage_path / "admin.key"

    if is_new:
        print(f"\n{'='*60}", flush=True)
        print("SERVER ADMIN INITIALIZED", flush=True)
        print(f"{'='*60}", flush=True)
        print(f"Admin DID: {admin_did}", flush=True)
        print(f"Admin key: {admin_key_path}", flush=True)
        print(flush=True)
        print("To administer remotely, copy the key:", flush=True)
        print(f"  scp <server>:{admin_key_path} ~/.hopper/did.key", flush=True)
        print(f"{'='*60}\n", flush=True)
    else:
        print(f"Admin DID: {admin_did}", flush=True)

    # Configure storage and pre-register admin
    configure_storage(storage_path)

    # Pre-register admin DID
    if _storage:
        from hopper.upstream.storage import GLOBAL_NS

        _storage.did_registry.register_or_get(admin_did, GLOBAL_NS)

    uvicorn.run(app, host=host, port=port)
