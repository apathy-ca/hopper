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
from .storage import (
    GLOBAL_NS,
    ORG_KEY_PREFIX,
    OWNER_KEY_PREFIX,
    DIDRecord,
    DIDStatus,
    Invite,
    InviteKind,
    Org,
    Owner,
    UpstreamStorage,
    is_org_key,
    is_owner_key,
    org_key,
    owner_key,
)


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
    owner_id: str | None = None  # set on DEVICE/NEW_OWNER invite redemption


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

    # Reconstruct the exact request-line path the client signed. The client
    # (sign_request callers in UpstreamClient) always signs path+query as
    # one string — request.url.path alone drops the query string, which
    # silently broke auth on every GET endpoint that takes a filter
    # (list_dids/list_pending/invite_list's ?namespace=..., and Phase B's
    # /admin/instances?owner=...). Pre-existing bug, not introduced here —
    # found because it broke a new endpoint built on this same path.
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    # Verify signature
    valid, did = verify_signature(
        auth_header=authorization,
        method=request.method,
        path=path,
        body=body,
    )

    if not valid or not did:
        raise HTTPException(status_code=401, detail="Invalid DID signature")

    return did


def _resolve_owner_and_orgs(
    storage: UpstreamStorage, did: str, cache_negative: bool = True
) -> tuple[str | None, list[str]]:
    """(owner_id, org_ids) for a DID's grant fallthrough — the DID's linked
    owner, if any, and every org that owner is a member of. Used at every
    authority call site (sync, approve, revoke, invite create/redeem/list)
    so a DID that's only authorized *via* an owner or org grant — not
    directly — is actually recognized as authorized everywhere, not just
    in the sync path this was first wired into.

    ``cache_negative`` passes straight through to
    ``OwnerRegistry.get_by_did`` — see that method's docstring. Defaults
    to True for the admin/approver-authenticated call sites where an
    unbounded number of permanent negative-cache files isn't a realistic
    concern; sync() is the one call site any freshly-signed, never-
    approved key can reach for free, so it passes False until the DID has
    some other reason to be considered established.
    """
    owner = storage.owner_registry.get_by_did(did, cache_negative=cache_negative)
    if owner is None:
        return None, []
    org_ids = [o.id for o in storage.org_registry.orgs_for_owner(owner.id)]
    return owner.id, org_ids


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

    # Phase B/E: resolve the caller's linked owner and that owner's orgs, if
    # any — a DID with no direct grant for this namespace can still be
    # authorized through its owner's grant, or an org that owner belongs to.
    #
    # cache_negative is gated on the DID already being an established
    # registry entry (has a DIDRegistry record from a prior call, or is
    # admin). Without this, a caller mints a fresh did:key, signs one
    # /sync call with it, and plants a permanent negative-cache file under
    # owners/did_index/ for free, with zero authorization — this is the
    # one call site reachable by any signed-but-never-approved key before
    # any admission check runs, so looped it's an unbounded disk-
    # exhaustion vector against a server exposed to the internet. A
    # returning DID (one that's already gone through register_or_get at
    # least once, even just to land PENDING) has already paid the same
    # one-file cost DIDRegistry always charged for a first contact, so
    # letting it also earn the did_index/ speedup adds no new attack
    # surface beyond what already existed.
    already_established = storage.did_registry.has_record(did)
    owner_id, org_ids = _resolve_owner_and_orgs(storage, did, cache_negative=already_established)

    # Register DID for this namespace if new, check authorization
    status, is_new = storage.did_registry.register_or_get(
        did, namespace, owner_id=owner_id, org_ids=org_ids
    )

    if is_new and status == DIDStatus.ADMIN:
        pass  # First DID — global admin
    elif not storage.did_registry.is_authorized(did, namespace, owner_id=owner_id, org_ids=org_ids):
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


class MeResponse(BaseModel):
    """Self-information for the authenticated DID."""

    did: str
    owner_id: str | None = None
    is_admin: bool


@router.get("/me")
async def whoami_me(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> MeResponse:
    """Self-information — no special authority needed beyond holding the
    key, since it's only ever information about the caller itself.

    Exists so a device can discover its own linked owner without already
    knowing the owner id — the missing piece ``hopper init``'s
    instance-discovery picker (Phase D) needs.
    """
    owner = storage.owner_registry.get_by_did(did)
    return MeResponse(
        did=did,
        owner_id=owner.id if owner else None,
        is_admin=storage.did_registry.is_admin(did),
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


def _check_grant_target_exists(storage: UpstreamStorage, target: str) -> str | None:
    """None if ``target`` is fine to grant/revoke; an error message if it's
    an ``owner:<id>``/``org:<id>`` key naming something that doesn't exist.

    Without this, approving a typo'd id (``owner:jhenrry`` for
    ``jhenry``) succeeds silently and plants a dead grant nobody notices —
    a plain DID has no equivalent existence check (any string is a valid,
    if unapproved-yet, DID), so this only applies to the two key kinds
    that *do* have a real registry to check against.
    """
    if is_owner_key(target):
        owner_id = target[len(OWNER_KEY_PREFIX) :]
        if storage.owner_registry.get(owner_id) is None:
            return f"owner '{owner_id}' not found"
    elif is_org_key(target):
        org_id = target[len(ORG_KEY_PREFIX) :]
        if storage.org_registry.get(org_id) is None:
            return f"org '{org_id}' not found"
    return None


@router.post("/admin/approve")
async def approve_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Approve a DID for a namespace.

    Admin may set any role for any namespace. Approvers — direct, or via a
    linked owner/org's approver grant — may set role=approved on their own
    namespace only.
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

    # Authority before existence — checking existence first would let an
    # unauthorized caller learn whether an owner/org id exists just from
    # 404-vs-403, with zero approve authority of its own.
    by_owner_id, by_org_ids = _resolve_owner_and_orgs(storage, did)
    can, reason = storage.did_registry.can_approve(
        did, req.namespace, role, by_owner_id=by_owner_id, by_org_ids=by_org_ids
    )
    if not can:
        raise HTTPException(status_code=403, detail=reason)

    not_found = _check_grant_target_exists(storage, req.did)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)

    success, message = storage.did_registry.approve(
        req.did,
        namespace=req.namespace,
        by_did=did,
        role=role,
        by_owner_id=by_owner_id,
        by_org_ids=by_org_ids,
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

    # Authority before existence — same existence-oracle reasoning as
    # approve_did above.
    by_owner_id, by_org_ids = _resolve_owner_and_orgs(storage, did)
    can, reason = storage.did_registry.can_revoke(
        did, req.namespace, by_owner_id=by_owner_id, by_org_ids=by_org_ids
    )
    if not can:
        raise HTTPException(status_code=403, detail=reason)

    not_found = _check_grant_target_exists(storage, req.did)
    if not_found:
        raise HTTPException(status_code=404, detail=not_found)

    success, message = storage.did_registry.revoke(
        req.did, namespace=req.namespace, by_did=did, by_owner_id=by_owner_id, by_org_ids=by_org_ids
    )
    if not success:
        raise HTTPException(status_code=403, detail=message)
    return AdminResponse(success=True, message=f"Revoked {req.did}: {message}")


# --- Owner endpoints (Phase A — CRUD only, no authorization behavior yet) ---


class OwnerInfo(BaseModel):
    """Owner information for API responses."""

    id: str
    created_at: int
    primary_email: str | None = None
    emails: list[str] = []
    linked_dids: list[str] = []


class OwnerListResponse(BaseModel):
    owners: list[OwnerInfo]


class OwnerResponse(BaseModel):
    success: bool
    message: str
    owner: OwnerInfo | None = None


class OwnerCreateRequest(BaseModel):
    id: str
    primary_email: str


class OwnerEmailRequest(BaseModel):
    owner_id: str
    email: str


class OwnerDidRequest(BaseModel):
    owner_id: str
    did: str


def _owner_info(owner: Owner) -> OwnerInfo:
    return OwnerInfo(
        id=owner.id,
        created_at=owner.created_at,
        primary_email=owner.primary_email,
        emails=owner.emails,
        linked_dids=owner.linked_dids,
    )


def _require_admin(storage: UpstreamStorage, did: str) -> None:
    if not storage.did_registry.is_admin(did):
        raise HTTPException(status_code=403, detail="Only admin can manage owners")


@router.post("/admin/owners")
async def create_owner(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerResponse:
    """Create a new owner. Admin only — this is the server-admission gate."""
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OwnerCreateRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    owner, message = storage.owner_registry.create(req.id, req.primary_email)
    if owner is None:
        raise HTTPException(status_code=409, detail=message)
    return OwnerResponse(success=True, message=message, owner=_owner_info(owner))


@router.get("/admin/owners")
async def list_owners(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerListResponse:
    """List all owners. Admin only."""
    _require_admin(storage, did)
    return OwnerListResponse(owners=[_owner_info(o) for o in storage.owner_registry.list_all()])


@router.get("/admin/owners/{owner_id}")
async def get_owner(
    owner_id: str,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerResponse:
    """Get one owner by id. Admin only."""
    _require_admin(storage, did)
    owner = storage.owner_registry.get(owner_id)
    if owner is None:
        raise HTTPException(status_code=404, detail=f"owner '{owner_id}' not found")
    return OwnerResponse(success=True, message="found", owner=_owner_info(owner))


@router.post("/admin/owners/add-email")
async def add_owner_email(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerResponse:
    """Add an email alias to an existing owner. Admin only."""
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OwnerEmailRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    success, message = storage.owner_registry.add_email(req.owner_id, req.email)
    if not success:
        raise HTTPException(status_code=409, detail=message)
    owner = storage.owner_registry.get(req.owner_id)
    return OwnerResponse(success=True, message=message, owner=_owner_info(owner) if owner else None)


@router.post("/admin/owners/link-did")
async def link_owner_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerResponse:
    """Link a DID to an owner. Admin only in Phase A.

    Phase C introduces self-service device invites for owners linking their
    own further devices; this endpoint (direct, admin-driven linking) stays
    available regardless as the admin override path.
    """
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OwnerDidRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    success, message = storage.owner_registry.link_did(req.owner_id, req.did)
    if not success:
        raise HTTPException(status_code=409, detail=message)
    owner = storage.owner_registry.get(req.owner_id)
    return OwnerResponse(success=True, message=message, owner=_owner_info(owner) if owner else None)


@router.post("/admin/owners/unlink-did")
async def unlink_owner_did(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerResponse:
    """Unlink a DID from an owner. Admin only."""
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OwnerDidRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    success, message = storage.owner_registry.unlink_did(req.owner_id, req.did)
    if not success:
        raise HTTPException(status_code=409, detail=message)
    owner = storage.owner_registry.get(req.owner_id)
    return OwnerResponse(success=True, message=message, owner=_owner_info(owner) if owner else None)


# --- Owner instance discovery (Phase B) ---


class OwnerInstancesResponse(BaseModel):
    """Every namespace an owner can reach, directly or via a linked DID."""

    owner_id: str
    is_admin: bool
    global_access: bool
    instances: list[str]


def _owner_reach(storage: UpstreamStorage, target_owner: Owner) -> tuple[bool, bool, list[str]]:
    """(is_admin, has_global_grant, explicit_namespaces) for an owner,
    aggregated across the owner's own grant key, every linked DID, and
    (Phase E) every org that owner is a member of."""
    reg = storage.did_registry
    is_admin = any(reg.is_admin(d) for d in target_owner.linked_dids)
    keys = {owner_key(target_owner.id)} | set(target_owner.linked_dids)
    for org in storage.org_registry.orgs_for_owner(target_owner.id):
        keys.add(org_key(org.id))
    has_global, namespaces = reg.namespaces_for_keys(keys)
    return is_admin, has_global, namespaces


@router.get("/admin/instances")
async def owner_instances(
    owner: str,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OwnerInstancesResponse:
    """Every namespace the given owner can reach.

    Self-service: any DID linked to the target owner can query it (this is
    the "what can I reach" audit view, not an admin-only operation). Admin
    can query any owner.
    """
    target = storage.owner_registry.get(owner)
    if target is None:
        raise HTTPException(status_code=404, detail=f"owner '{owner}' not found")

    is_self = did in target.linked_dids
    if not (storage.did_registry.is_admin(did) or is_self):
        raise HTTPException(status_code=403, detail="not authorized to view this owner's instances")

    is_admin, global_access, instances = _owner_reach(storage, target)
    return OwnerInstancesResponse(
        owner_id=target.id, is_admin=is_admin, global_access=global_access, instances=instances
    )


# --- Org endpoints (Phase E — membership authority is admin-only for v1;
# creating an org, adding a member, and removing a member all go through
# the admin. Conservative default, not a hard architectural constraint —
# org membership changes who inherits access far more broadly than one
# person adding their own device does, so this plan starts cautious.) ---


class OrgInfo(BaseModel):
    id: str
    created_at: int
    name: str = ""
    member_owner_ids: list[str] = []


class OrgListResponse(BaseModel):
    orgs: list[OrgInfo]


class OrgResponse(BaseModel):
    success: bool
    message: str
    org: OrgInfo | None = None


class OrgCreateRequest(BaseModel):
    id: str
    name: str = ""


class OrgMemberRequest(BaseModel):
    org_id: str
    owner_id: str


def _org_info(org: Org) -> OrgInfo:
    return OrgInfo(
        id=org.id, created_at=org.created_at, name=org.name, member_owner_ids=org.member_owner_ids
    )


@router.post("/admin/orgs")
async def create_org(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OrgResponse:
    """Create a new org. Admin only — the same admission gate as owner creation."""
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OrgCreateRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    org, message = storage.org_registry.create(req.id, req.name)
    if org is None:
        raise HTTPException(status_code=409, detail=message)
    return OrgResponse(success=True, message=message, org=_org_info(org))


@router.get("/admin/orgs")
async def list_orgs(
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OrgListResponse:
    """List all orgs. Admin only."""
    _require_admin(storage, did)
    return OrgListResponse(orgs=[_org_info(o) for o in storage.org_registry.list_all()])


@router.get("/admin/orgs/{org_id}")
async def get_org(
    org_id: str,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OrgResponse:
    """Get one org. Admin, or any owner who is a member — same self-service
    visibility principle as owner instances."""
    org = storage.org_registry.get(org_id)
    if org is None:
        raise HTTPException(status_code=404, detail=f"org '{org_id}' not found")

    caller_owner = storage.owner_registry.get_by_did(did)
    is_member = caller_owner is not None and caller_owner.id in org.member_owner_ids
    if not (storage.did_registry.is_admin(did) or is_member):
        raise HTTPException(status_code=403, detail="not authorized to view this org")
    return OrgResponse(success=True, message="found", org=_org_info(org))


@router.post("/admin/orgs/add-member")
async def add_org_member(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OrgResponse:
    """Add an owner as a member of an org. Admin only."""
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OrgMemberRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    if storage.owner_registry.get(req.owner_id) is None:
        raise HTTPException(status_code=404, detail=f"owner '{req.owner_id}' not found")

    success, message = storage.org_registry.add_member(req.org_id, req.owner_id)
    if not success:
        raise HTTPException(status_code=409, detail=message)
    org = storage.org_registry.get(req.org_id)
    return OrgResponse(success=True, message=message, org=_org_info(org) if org else None)


@router.post("/admin/orgs/remove-member")
async def remove_org_member(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OrgResponse:
    """Remove an owner from an org. Admin only."""
    _require_admin(storage, did)
    body = await request.body()
    try:
        req = OrgMemberRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    success, message = storage.org_registry.remove_member(req.org_id, req.owner_id)
    if not success:
        raise HTTPException(status_code=409, detail=message)
    org = storage.org_registry.get(req.org_id)
    return OrgResponse(success=True, message=message, org=_org_info(org) if org else None)


class OrgInstancesResponse(BaseModel):
    """Namespaces granted directly to the org itself — not aggregated
    across members' own devices/owner grants (that's owner_instances)."""

    org_id: str
    global_access: bool
    instances: list[str]


@router.get("/admin/orgs/{org_id}/instances")
async def org_instances(
    org_id: str,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> OrgInstancesResponse:
    """Namespaces this org itself has been directly granted. Admin, or any
    member owner, can view."""
    target_org = storage.org_registry.get(org_id)
    if target_org is None:
        raise HTTPException(status_code=404, detail=f"org '{org_id}' not found")

    caller_owner = storage.owner_registry.get_by_did(did)
    is_member = caller_owner is not None and caller_owner.id in target_org.member_owner_ids
    if not (storage.did_registry.is_admin(did) or is_member):
        raise HTTPException(status_code=403, detail="not authorized to view this org")

    has_global, instances = storage.did_registry.namespaces_for_keys({org_key(org_id)})
    return OrgInstancesResponse(org_id=org_id, global_access=has_global, instances=instances)


# --- Invite endpoints ---


class InviteCreateRequest(BaseModel):
    kind: str = "namespace"  # "namespace" | "device" | "new_owner"
    namespace: str = ""  # NAMESPACE kind
    role: str = "approved"  # NAMESPACE kind: "approved" or "approver"
    owner_id: str = ""  # DEVICE: owner to link into. NEW_OWNER: id to create.
    email: str = ""  # NEW_OWNER: the new owner's primary email.
    expires_in_ms: int | None = None  # None = no expiry
    max_uses: int = 1


class InviteInfo(BaseModel):
    token_hash: str
    kind: str = "namespace"
    namespace: str = ""
    role: str = "approved"
    owner_id: str = ""
    new_owner_email: str = ""
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
        kind=inv.kind.value,
        namespace=inv.namespace,
        role=inv.role.value,
        owner_id=inv.owner_id,
        new_owner_email=inv.new_owner_email,
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
    """Create an invite token — namespace, device, or new-owner (Phase C).

    NAMESPACE (original): admin may issue any role for any namespace;
    approvers may issue role=approved on their own namespace only.
    DEVICE: self-service — mintable by any DID already linked to the
    target owner, no admin involvement.
    NEW_OWNER: admin only. This is the actual server-admission gate — who
    gets to exist as a recognized owner doesn't get delegated.
    """
    body = await request.body()
    try:
        req = InviteCreateRequest.model_validate_json(body)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid request: {e}") from e

    try:
        kind = InviteKind(req.kind)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid kind: {req.kind}") from e
    if req.max_uses < 1:
        raise HTTPException(status_code=400, detail="max_uses must be >= 1")

    expires_at = None
    if req.expires_in_ms is not None:
        expires_at = int(time.time() * 1000) + req.expires_in_ms

    reg = storage.did_registry
    is_admin = reg.is_admin(did)
    by_owner_id, by_org_ids = _resolve_owner_and_orgs(storage, did)

    if kind == InviteKind.NAMESPACE:
        try:
            role = DIDStatus(req.role)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid role: {req.role}") from e
        if role not in (DIDStatus.APPROVED, DIDStatus.APPROVER):
            raise HTTPException(status_code=400, detail="role must be approved or approver")
        if not is_admin:
            if role == DIDStatus.APPROVER:
                raise HTTPException(status_code=403, detail="only admin can issue approver invites")
            if req.namespace == GLOBAL_NS:
                raise HTTPException(status_code=403, detail="only admin can issue global invites")
            if not reg.is_approver(did, req.namespace, owner_id=by_owner_id, org_ids=by_org_ids):
                raise HTTPException(
                    status_code=403,
                    detail=f"not authorized to invite for namespace '{req.namespace}'",
                )
        token, invite = storage.invites.create(
            kind=kind,
            namespace=req.namespace,
            role=role,
            issued_by=did,
            expires_at=expires_at,
            max_uses=req.max_uses,
        )

    elif kind == InviteKind.DEVICE:
        if not req.owner_id:
            raise HTTPException(status_code=400, detail="owner_id required for a device invite")
        target_owner = storage.owner_registry.get(req.owner_id)
        if target_owner is None:
            raise HTTPException(status_code=404, detail=f"owner '{req.owner_id}' not found")
        if not is_admin and did not in target_owner.linked_dids:
            raise HTTPException(
                status_code=403,
                detail="must be linked to this owner to mint a device invite for it",
            )
        token, invite = storage.invites.create(
            kind=kind,
            owner_id=req.owner_id,
            issued_by=did,
            expires_at=expires_at,
            max_uses=req.max_uses,
        )

    elif kind == InviteKind.NEW_OWNER:
        if not is_admin:
            raise HTTPException(status_code=403, detail="only admin can issue a new-owner invite")
        if not req.owner_id or not req.email:
            raise HTTPException(
                status_code=400, detail="owner_id and email required for a new-owner invite"
            )
        if storage.owner_registry.get(req.owner_id) is not None:
            raise HTTPException(status_code=409, detail=f"owner '{req.owner_id}' already exists")
        token, invite = storage.invites.create(
            kind=kind,
            owner_id=req.owner_id,
            new_owner_email=req.email,
            issued_by=did,
            expires_at=expires_at,
            max_uses=req.max_uses,
        )

    else:
        raise HTTPException(status_code=400, detail=f"unhandled invite kind: {kind}")

    return InviteCreateResponse(token=token, invite=_invite_info(invite))


@router.post("/invite/redeem")
async def invite_redeem(
    request: Request,
    storage: Annotated[UpstreamStorage, Depends(get_storage)],
    did: Annotated[str, Depends(verify_did_auth)],
) -> AdminResponse:
    """Redeem an invite token for the caller's DID.

    What happens depends on the invite's kind — see ``invite_create``.
    """
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

    # Re-check issuer authority at redeem time — authority granted at issue
    # time can have been revoked before redemption.
    issuer = invite_preview.issued_by
    if invite_preview.kind == InviteKind.NAMESPACE:
        if not reg.is_admin(issuer):
            if invite_preview.role == DIDStatus.APPROVER:
                raise HTTPException(
                    status_code=403, detail="issuer no longer has approver authority"
                )
            issuer_owner_id, issuer_org_ids = _resolve_owner_and_orgs(storage, issuer)
            if not reg.is_approver(
                issuer, invite_preview.namespace, owner_id=issuer_owner_id, org_ids=issuer_org_ids
            ):
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "issuer no longer has approver authority for "
                        f"'{invite_preview.namespace}'"
                    ),
                )
    elif invite_preview.kind == InviteKind.DEVICE:
        issuer_owner = storage.owner_registry.get_by_did(issuer)
        still_linked = issuer_owner is not None and issuer_owner.id == invite_preview.owner_id
        if not reg.is_admin(issuer) and not still_linked:
            raise HTTPException(status_code=403, detail="issuer is no longer linked to this owner")
    elif invite_preview.kind == InviteKind.NEW_OWNER:
        if not reg.is_admin(issuer):
            raise HTTPException(status_code=403, detail="issuer is no longer admin")

    if reg.is_admin(did):
        raise HTTPException(status_code=400, detail="admin does not need to redeem invites")

    # Reserve the slot FIRST, atomically (redeem() is locked — see its
    # docstring): a losing racer in a concurrent redemption of the same
    # max_uses=1 token is rejected right here and never reaches any
    # mutation below, closing both the "two racers both get granted" case
    # and, together with the rollback-on-failure below, the "mutation
    # fails but the invite is already burned" case.
    redeemed, redeem_message = storage.invites.redeem(req.token, by_did=did)
    if redeemed is None:
        raise HTTPException(status_code=403, detail=redeem_message)

    if redeemed.kind == InviteKind.NAMESPACE:
        # register_or_get/set_status are setters with no failure mode —
        # nothing to roll back here even in principle.
        reg.register_or_get(did, redeemed.namespace)
        reg.set_status(did, redeemed.namespace, redeemed.role, by_did=redeemed.issued_by)
        return AdminResponse(
            success=True,
            message=f"redeemed: {redeemed.role.value} on '{redeemed.namespace}'",
            namespace=redeemed.namespace,
        )

    if redeemed.kind == InviteKind.DEVICE:
        link_ok, link_message = storage.owner_registry.link_did(redeemed.owner_id, did)
        if not link_ok:
            storage.invites.unredeem(req.token, by_did=did)
            raise HTTPException(status_code=409, detail=link_message)
        return AdminResponse(
            success=True,
            message=f"redeemed: linked to owner '{redeemed.owner_id}'",
            owner_id=redeemed.owner_id,
        )

    if redeemed.kind == InviteKind.NEW_OWNER:
        owner, create_message = storage.owner_registry.create(
            redeemed.owner_id, redeemed.new_owner_email
        )
        if owner is None:
            storage.invites.unredeem(req.token, by_did=did)
            raise HTTPException(status_code=409, detail=create_message)
        # Checked, unlike before: if this fails (e.g. the redeeming DID was
        # already linked to a different owner by the time we get here),
        # the client must see that its device isn't actually linked rather
        # than a false "success". The just-created owner is left in place
        # rather than rolled back — a rare, admin-recoverable leftover
        # (link-did it manually, or ignore it) beats adding delete-owner
        # machinery for an edge case this narrow; the invite slot itself
        # *is* given back, so the token remains usable.
        link_ok, link_message = storage.owner_registry.link_did(redeemed.owner_id, did)
        if not link_ok:
            storage.invites.unredeem(req.token, by_did=did)
            raise HTTPException(status_code=409, detail=link_message)
        return AdminResponse(
            success=True,
            message=f"redeemed: created owner '{redeemed.owner_id}' and linked this device",
            owner_id=redeemed.owner_id,
        )

    storage.invites.unredeem(req.token, by_did=did)
    raise HTTPException(status_code=400, detail=f"unhandled invite kind: {redeemed.kind}")


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
        # Approver — direct, or via a linked owner/org's approver grant —
        # only sees invites for namespaces they can approve.
        by_owner_id, by_org_ids = _resolve_owner_and_orgs(storage, did)
        visible = [
            inv
            for inv in all_invites
            if reg.is_approver(did, inv.namespace, owner_id=by_owner_id, org_ids=by_org_ids)
            or inv.issued_by == did
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
        by_owner_id, by_org_ids = _resolve_owner_and_orgs(storage, did)
        if invite.issued_by != did and not reg.is_approver(
            did, invite.namespace, owner_id=by_owner_id, org_ids=by_org_ids
        ):
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
