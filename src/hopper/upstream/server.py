"""Upstream sync server.

FastAPI server that accepts sync requests with DID authentication.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from .did import verify_signature
from .protocol import SyncConflict, SyncRequest, SyncResponse
from .storage import DIDStatus, UpstreamStorage


class DIDInfo(BaseModel):
    """DID information for API responses."""

    did: str
    status: str
    created_at: int
    approved_by: str | None = None
    approved_at: int | None = None


class AdminResponse(BaseModel):
    """Response for admin operations."""

    success: bool
    message: str


class DIDListResponse(BaseModel):
    """Response for listing DIDs."""

    admin_did: str | None
    dids: list[DIDInfo]

app = FastAPI(
    title="Hopper Upstream",
    description="Lightweight sync server for Hopper instances",
    version="0.1.0",
)

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


@app.get("/health")
async def health() -> dict:
    """Health check endpoint."""
    return {"status": "ok", "time": int(time.time() * 1000)}


@app.post("/sync")
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
    # Register DID if new, check authorization
    status, is_new = storage.did_registry.register_or_get(did)

    if is_new and status == DIDStatus.ADMIN:
        # First DID - automatically authorized
        pass
    elif not storage.did_registry.is_authorized(did):
        raise HTTPException(
            status_code=403,
            detail=f"DID pending approval. Contact admin to approve: {did}",
        )

    # Parse request body
    body = await request.body()
    try:
        sync_req = SyncRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {e}")

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
            server_ts = storage.get_updated_at(task.id) or 0
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

    # Get tasks updated since client's timestamp
    updated_tasks = storage.list_since(sync_req.since)

    return SyncResponse(
        tasks=updated_tasks,
        server_time=server_time,
        accepted=accepted,
        rejected=rejected,
    )


@app.get("/admin/dids")
async def list_dids(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> DIDListResponse:
    """List all registered DIDs. Only admin can see full list."""
    # Anyone can call this but non-admin only sees limited info
    records = storage.did_registry.list_all()

    return DIDListResponse(
        admin_did=storage.did_registry.admin_did,
        dids=[
            DIDInfo(
                did=r.did,
                status=r.status.value,
                created_at=r.created_at,
                approved_by=r.approved_by,
                approved_at=r.approved_at,
            )
            for r in records
        ],
    )


@app.get("/admin/pending")
async def list_pending(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> DIDListResponse:
    """List pending DIDs awaiting approval. Only admin can view."""
    if not storage.did_registry.is_admin(did):
        raise HTTPException(status_code=403, detail="Only admin can view pending DIDs")

    records = storage.did_registry.list_pending()

    return DIDListResponse(
        admin_did=storage.did_registry.admin_did,
        dids=[
            DIDInfo(
                did=r.did,
                status=r.status.value,
                created_at=r.created_at,
                approved_by=r.approved_by,
                approved_at=r.approved_at,
            )
            for r in records
        ],
    )


class ApproveRequest(BaseModel):
    """Request to approve a DID."""

    did: str


@app.post("/admin/approve")
async def approve_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Approve a pending DID. Only admin can approve."""
    body = await request.body()
    try:
        req = ApproveRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    success, message = storage.did_registry.approve(req.did, by_did=did)

    if not success:
        raise HTTPException(status_code=403, detail=message)

    return AdminResponse(success=True, message=f"Approved {req.did}")


@app.post("/admin/revoke")
async def revoke_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Revoke a DID's access. Only admin can revoke."""
    body = await request.body()
    try:
        req = ApproveRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}")

    success, message = storage.did_registry.revoke(req.did, by_did=did)

    if not success:
        raise HTTPException(status_code=403, detail=message)

    return AdminResponse(success=True, message=f"Revoked {req.did}")


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
    port: int = 9000,
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
