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
from .storage import DIDStatus, UpstreamStorage


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


def configure_storage(storage_path: Path) -> None:
    """Configure the storage backend."""
    global _storage
    _storage = UpstreamStorage(storage_path)


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
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

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


def _did_info(record: "DIDRecord") -> DIDInfo:
    from .storage import DIDStatus
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


@router.post("/admin/approve")
async def approve_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Approve a DID for a namespace (or all namespaces if namespace='*')."""
    body = await request.body()
    try:
        req = ApproveRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    success, message = storage.did_registry.approve(req.did, namespace=req.namespace, by_did=did)
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
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    success, message = storage.did_registry.revoke(req.did, namespace=req.namespace, by_did=did)
    if not success:
        raise HTTPException(status_code=403, detail=message)
    return AdminResponse(success=True, message=f"Revoked {req.did}: {message}")


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
    host: str = "0.0.0.0",
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
        _storage.did_registry.register_or_get(admin_did)

    uvicorn.run(app, host=host, port=port)
