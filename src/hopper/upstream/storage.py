"""Server-side storage for upstream sync.

Simple flat file storage with JSON tasks and an index for quick lookups.
"""

from __future__ import annotations

import hashlib
import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from .protocol import SyncTask

if TYPE_CHECKING:
    from .shadow import RevisionShadowWriter


class DIDStatus(str, Enum):
    """Status of a DID for a given namespace."""

    ADMIN = "admin"  # Server admin — implicitly approved for all namespaces
    APPROVER = "approver"  # Authorized for namespace AND can approve/invite others for it
    APPROVED = "approved"
    PENDING = "pending"


GLOBAL_NS = "*"  # Sentinel: approved for all namespaces

OWNER_KEY_PREFIX = "owner:"  # Sentinel prefix: a registry key naming an owner, not a DID


def owner_key(owner_id: str) -> str:
    """Registry key representing an owner's grant, distinct from a DID's.

    Reuses the same flat ``namespace -> {key: status}`` registry a DID's
    grant lives in — an owner grant is just another key in that dict, the
    same trick ``GLOBAL_NS`` already uses at the namespace level. No second
    grants table.
    """
    return f"{OWNER_KEY_PREFIX}{owner_id}"


def is_owner_key(key: str) -> bool:
    return key.startswith(OWNER_KEY_PREFIX)


@dataclass
class NamespaceApproval:
    """Approval record for one DID+namespace pair."""

    status: DIDStatus
    approved_by: str | None = None
    approved_at: int | None = None


@dataclass
class DIDRecord:
    """A DID record — tracks per-namespace approvals."""

    did: str
    created_at: int
    namespaces: dict[str, NamespaceApproval] = field(default_factory=dict)
    # "*" key means approved for all namespaces
    last_instance: str | None = None  # Last Hopper instance this DID connected to
    last_instance_at: int | None = None  # Timestamp (ms) when last_instance was set


@dataclass
class DIDRegistry:
    """Per-namespace DID approval registry.

    Any approved DID can collaborate on a namespace. Admin (first DID) is
    implicitly approved for all namespaces. Other DIDs are approved per
    namespace, or globally via the '*' sentinel.

    Directory structure:
        storage_path/
        └── dids/
            ├── registry.json
            └── {did_hash}.json
    """

    storage_path: Path
    _admin_did: str | None = None
    # _registry: namespace -> {did -> status}
    _registry: dict[str, dict[str, DIDStatus]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.dids_dir = self.storage_path / "dids"
        self.dids_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.dids_dir / "registry.json"
        self.lock_path = self.dids_dir / ".lock"
        self._load_registry()

    def _lock(self):
        return _file_lock(self.lock_path)

    def _load_registry(self) -> None:
        if not self.registry_path.exists():
            return
        try:
            with open(self.registry_path) as f:
                data = json.load(f)
            self._admin_did = data.get("admin_did")
            raw = data.get("namespaces", {})
            # Migrate old flat format: {"dids": {"did": "status"}}
            if "dids" in data and not raw:
                for did, status in data["dids"].items():
                    if status == "admin":
                        pass  # admin_did already set
                    else:
                        self._registry.setdefault(GLOBAL_NS, {})[did] = DIDStatus(status)
            else:
                self._registry = {
                    ns: {did: DIDStatus(s) for did, s in dids.items()} for ns, dids in raw.items()
                }
        except (json.JSONDecodeError, OSError):
            self._admin_did = None
            self._registry = {}

    def _save_registry(self) -> None:
        with open(self.registry_path, "w") as f:
            json.dump(
                {
                    "admin_did": self._admin_did,
                    "namespaces": {
                        ns: {did: s.value for did, s in dids.items()}
                        for ns, dids in self._registry.items()
                    },
                },
                f,
                indent=2,
            )

    def _did_path(self, did: str) -> Path:
        did_hash = hashlib.sha256(did.encode()).hexdigest()[:16]
        return self.dids_dir / f"{did_hash}.json"

    def _save_record(self, record: DIDRecord) -> None:
        with open(self._did_path(record.did), "w") as f:
            data = {
                "did": record.did,
                "created_at": record.created_at,
                "namespaces": {
                    ns: {
                        "status": a.status.value,
                        "approved_by": a.approved_by,
                        "approved_at": a.approved_at,
                    }
                    for ns, a in record.namespaces.items()
                },
            }
            if record.last_instance is not None:
                data["last_instance"] = record.last_instance
                data["last_instance_at"] = record.last_instance_at
            json.dump(data, f, indent=2)

    def _load_record(self, did: str) -> DIDRecord | None:
        path = self._did_path(did)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            # Migrate old format
            if "status" in data:
                ns_map = {}
                if data.get("status") not in ("admin", None):
                    ns_map[GLOBAL_NS] = NamespaceApproval(
                        status=DIDStatus(data["status"]),
                        approved_by=data.get("approved_by"),
                        approved_at=data.get("approved_at"),
                    )
                return DIDRecord(
                    did=data["did"],
                    created_at=data["created_at"],
                    namespaces=ns_map,
                    last_instance=data.get("last_instance"),
                    last_instance_at=data.get("last_instance_at"),
                )
            namespaces = {
                ns: NamespaceApproval(
                    status=DIDStatus(a["status"]),
                    approved_by=a.get("approved_by"),
                    approved_at=a.get("approved_at"),
                )
                for ns, a in data.get("namespaces", {}).items()
            }
            return DIDRecord(
                did=data["did"],
                created_at=data["created_at"],
                namespaces=namespaces,
                last_instance=data.get("last_instance"),
                last_instance_at=data.get("last_instance_at"),
            )
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    @property
    def admin_did(self) -> str | None:
        return self._admin_did

    def is_admin(self, did: str) -> bool:
        return self._admin_did == did

    def is_established(self, did: str) -> bool:
        """Whether this DID has ever actually been granted access
        somewhere — APPROVED or APPROVER on at least one namespace, or
        admin — as opposed to merely having *asked* once.

        Deliberately stronger than "has any record at all": a plain
        PENDING record costs an attacker nothing (one signed request
        against any endpoint self-registers it — see register_or_get) and
        an earlier version of this gate used exactly that weaker test, so
        a synthetic DID could satisfy it for free with one throwaway call
        before the one that actually plants a cache file, merely doubling
        the attacker's request cost rather than bounding it at all.
        APPROVED/APPROVER status cannot be self-granted — it only exists
        because a real admin or approver, or a real invite token minted
        by one, put it there — so this can't be satisfied by spamming
        signed requests alone.

        Checked against the in-memory ``_registry`` (already resident,
        no disk read) rather than the per-DID file ``has_record`` used to
        read — this is called on every ``/sync``, the hottest endpoint,
        so an unconditional extra file read per call for a value that's
        usually unchanged from the last call was worth avoiding.
        """
        if self.is_admin(did):
            return True
        authorized = {DIDStatus.APPROVED, DIDStatus.APPROVER}
        return any(did in dids and dids[did] in authorized for dids in self._registry.values())

    def _is_directly_authorized(self, key: str, namespace: str) -> bool:
        """Original DID-only authorization check — also reused for owner
        keys, since an owner grant lives in the exact same registry shape."""
        if self.is_admin(key):
            return True
        authorized = {DIDStatus.APPROVED, DIDStatus.APPROVER}
        # Global approval
        if key in self._registry.get(GLOBAL_NS, {}):
            return self._registry[GLOBAL_NS][key] in authorized
        # Namespace-specific approval
        return self._registry.get(namespace, {}).get(key) in authorized

    def is_authorized(
        self,
        did: str,
        namespace: str,
        owner_id: str | None = None,
        org_ids: list[str] | None = None,
    ) -> bool:
        """Check if DID is authorized for a namespace.

        Resolution order: the DID's own direct grant first (unchanged
        behavior); then its linked owner's grant (Phase B); then any org
        that owner is a member of (Phase E). Callers resolve owner_id via
        ``OwnerRegistry.get_by_did`` and org_ids via
        ``OrgRegistry.orgs_for_owner``.
        """
        if self._is_directly_authorized(did, namespace):
            return True
        if owner_id is not None and self._is_directly_authorized(owner_key(owner_id), namespace):
            return True
        for org_id in org_ids or []:
            if self._is_directly_authorized(org_key(org_id), namespace):
                return True
        return False

    def _is_directly_approver(self, key: str, namespace: str) -> bool:
        """Original DID-only approver check — also reused for owner keys."""
        if self.is_admin(key):
            return True
        if self._registry.get(GLOBAL_NS, {}).get(key) == DIDStatus.APPROVER:
            return True
        return self._registry.get(namespace, {}).get(key) == DIDStatus.APPROVER

    def is_approver(
        self,
        did: str,
        namespace: str,
        owner_id: str | None = None,
        org_ids: list[str] | None = None,
    ) -> bool:
        """Check if DID can approve/invite others for a namespace.

        Same owner/org fallthrough as ``is_authorized``.
        """
        if self._is_directly_approver(did, namespace):
            return True
        if owner_id is not None and self._is_directly_approver(owner_key(owner_id), namespace):
            return True
        for org_id in org_ids or []:
            if self._is_directly_approver(org_key(org_id), namespace):
                return True
        return False

    def namespaces_for_keys(self, keys: set[str]) -> tuple[bool, list[str]]:
        """Every namespace any of the given registry keys (DIDs or owner
        keys) holds an approved/approver grant in.

        Returns ``(has_global_grant, explicit_namespaces)``. A key holding
        the ``"*"`` global grant can reach every namespace — present and
        future — which can't be enumerated; that's surfaced as a flag
        instead of pretending to list "all of them."
        """
        authorized = {DIDStatus.APPROVED, DIDStatus.APPROVER}
        has_global = any(self._registry.get(GLOBAL_NS, {}).get(k) in authorized for k in keys)
        namespaces = {
            ns
            for ns, grants in self._registry.items()
            if ns != GLOBAL_NS
            for k, status in grants.items()
            if k in keys and status in authorized
        }
        return has_global, sorted(namespaces)

    def get_status(self, did: str, namespace: str) -> DIDStatus | None:
        if self.is_admin(did):
            return DIDStatus.ADMIN
        if did in self._registry.get(GLOBAL_NS, {}):
            return self._registry[GLOBAL_NS][did]
        return self._registry.get(namespace, {}).get(did)

    def register_or_get(
        self,
        did: str,
        namespace: str,
        owner_id: str | None = None,
        org_ids: list[str] | None = None,
    ) -> tuple[DIDStatus, bool]:
        """Register DID for a namespace, or return existing status.

        Returns (status, is_new). First DID becomes global admin.

        A DID whose linked owner (Phase B) or one of that owner's orgs
        (Phase E) already grants this namespace is reported as approved
        *without* writing a registry entry for the DID itself — the grant
        stays purely derived, so revoking it takes effect immediately next
        sync rather than leaving an orphaned direct approval behind. This
        also avoids registering a misleading PENDING entry for a device
        that already works.

        The checks above this docstring's original body ran against this
        process's in-memory ``_registry`` unconditionally; only the
        actually-mutating paths below acquire the lock and reload from
        disk first, then re-check everything fresh before writing
        (double-checked locking) — this is the hottest endpoint in the
        system, and most calls hit the pure-read fast path (a DID that's
        already registered), so unconditionally locking every call would
        undo the point of the did_index fast path in ``OwnerRegistry``.
        """
        if self.is_admin(did):
            return DIDStatus.ADMIN, False
        existing = self.get_status(did, namespace)
        if existing is not None:
            return existing, False
        if owner_id is not None and self._is_directly_authorized(owner_key(owner_id), namespace):
            return DIDStatus.APPROVED, False
        for org_id in org_ids or []:
            if self._is_directly_authorized(org_key(org_id), namespace):
                return DIDStatus.APPROVED, False

        with self._lock():
            self._load_registry()  # refresh — another process may have just written

            if self.is_admin(did):
                return DIDStatus.ADMIN, False
            existing = self.get_status(did, namespace)
            if existing is not None:
                return existing, False

            now = int(time.time() * 1000)
            if self._admin_did is None:
                self._admin_did = did
                self._save_registry()
                record = DIDRecord(did=did, created_at=now)
                self._save_record(record)
                return DIDStatus.ADMIN, True

            if owner_id is not None and self._is_directly_authorized(
                owner_key(owner_id), namespace
            ):
                return DIDStatus.APPROVED, False
            for org_id in org_ids or []:
                if self._is_directly_authorized(org_key(org_id), namespace):
                    return DIDStatus.APPROVED, False

            # Register as pending for this namespace
            self._registry.setdefault(namespace, {})[did] = DIDStatus.PENDING
            self._save_registry()
            record = self._load_record(did) or DIDRecord(did=did, created_at=now)
            record.namespaces[namespace] = NamespaceApproval(status=DIDStatus.PENDING)
            self._save_record(record)
            return DIDStatus.PENDING, True

    def set_status(self, target: str, namespace: str, status: DIDStatus, by_did: str) -> None:
        """Write a status transition to the namespace registry.

        ``target`` is a DID, an ``owner:<id>`` key (Phase B), or an
        ``org:<id>`` key (Phase E). For a plain DID this also updates that
        DID's per-file record, same as always. An owner or org key has no
        per-DID record to update — the grant lives only in the namespace
        registry; ``OwnerRegistry``/``OrgRegistry`` (sibling stores) hold
        that identity's own data.

        Always mutates, so always locks and reloads first — unlike
        ``register_or_get``, there's no pure-read fast path to preserve
        here. This closes the *lost-write* race (two concurrent workers
        both mutating ``_registry`` from their own stale in-memory copy,
        second save silently discarding the first); it does not make the
        *authority check* that ran before this was called (in
        ``approve``/``revoke``) immune to reading stale data — that would
        need every read path (``is_authorized`` et al.) to reload on every
        call too, on the hottest path in the system, for a narrower race
        than the lost-write one. Out of scope here; the lost-write fix is
        what was asked for.
        """
        with self._lock():
            self._load_registry()
            now = int(time.time() * 1000)
            self._registry.setdefault(namespace, {})[target] = status
            self._save_registry()

            if is_owner_key(target) or is_org_key(target):
                return

            record = self._load_record(target) or DIDRecord(did=target, created_at=now)
            record.namespaces[namespace] = NamespaceApproval(
                status=status, approved_by=by_did, approved_at=now
            )
            self._save_record(record)

    def can_approve(
        self,
        by_did: str,
        namespace: str,
        role: DIDStatus = DIDStatus.APPROVED,
        by_owner_id: str | None = None,
        by_org_ids: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Authority-only check for ``approve()`` — no mutation, and no
        opinion on whether the target itself is valid.

        Exposed separately so a caller (the ``/admin/approve`` endpoint)
        can verify authority *before* checking whether an ``owner:<id>``/
        ``org:<id>`` target exists — checking existence first turns the
        404-vs-403 split into an existence oracle: an unauthorized caller
        could learn whether an id exists just from the response code,
        with zero approve authority of its own.
        """
        if role not in (DIDStatus.APPROVED, DIDStatus.APPROVER):
            return False, f"invalid role: {role}"
        if self.is_admin(by_did):
            return True, ""
        if role == DIDStatus.APPROVER:
            return False, "only admin can grant approver role"
        if namespace == GLOBAL_NS:
            return False, "only admin can approve across all namespaces"
        if not self.is_approver(by_did, namespace, owner_id=by_owner_id, org_ids=by_org_ids):
            return False, f"not authorized to approve for namespace '{namespace}'"
        return True, ""

    def approve(
        self,
        target: str,
        namespace: str,
        by_did: str,
        role: DIDStatus = DIDStatus.APPROVED,
        by_owner_id: str | None = None,
        by_org_ids: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Approve a DID — or (Phase B) an ``owner:<id>`` key, or (Phase E)
        an ``org:<id>`` key — for a namespace at a given role.

        Authority — see ``can_approve`` (called internally here too, so
        this stays safe to call directly without a separate pre-check).

        Approving an owner or org key grants every DID currently *and
        future* linked to it, without touching any of them individually.
        """
        ok, reason = self.can_approve(
            by_did, namespace, role, by_owner_id=by_owner_id, by_org_ids=by_org_ids
        )
        if not ok:
            return False, reason
        if self.is_admin(target):
            return False, "cannot modify admin DID"

        self.set_status(target, namespace, role, by_did)
        scope = "all namespaces" if namespace == GLOBAL_NS else namespace
        label = "approver on" if role == DIDStatus.APPROVER else "approved for"
        return True, f"{label} {scope}"

    def can_revoke(
        self,
        by_did: str,
        namespace: str,
        by_owner_id: str | None = None,
        by_org_ids: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Authority-only check for ``revoke()`` — see ``can_approve``'s
        docstring for why this is split out (existence-oracle avoidance).
        Does not check the target's current grant status — that rule
        ("approvers can only revoke APPROVED members") needs the target to
        already be known to exist, so it stays in ``revoke()`` itself,
        after the endpoint's existence check.
        """
        if self.is_admin(by_did):
            return True, ""
        if namespace == GLOBAL_NS:
            return False, "only admin can revoke across all namespaces"
        if not self.is_approver(by_did, namespace, owner_id=by_owner_id, org_ids=by_org_ids):
            return False, f"not authorized to revoke for namespace '{namespace}'"
        return True, ""

    def revoke(
        self,
        target: str,
        namespace: str,
        by_did: str,
        by_owner_id: str | None = None,
        by_org_ids: list[str] | None = None,
    ) -> tuple[bool, str]:
        """Revoke a DID's — or (Phase B) an owner's, or (Phase E) an org's —
        access to a namespace (or all if namespace == '*').

        Admin can revoke anyone. Approver (direct, or via owner/org
        fallthrough — same as ``approve``) can revoke only APPROVED members
        of their specific namespace (never another approver or admin).
        """
        if self.is_admin(target):
            return False, "cannot revoke admin DID"

        by_is_admin = self.is_admin(by_did)
        if not by_is_admin:
            ok, reason = self.can_revoke(
                by_did, namespace, by_owner_id=by_owner_id, by_org_ids=by_org_ids
            )
            if not ok:
                return False, reason

        # Locked + reloaded from here on, same reasoning as set_status: this
        # always mutates, so there's no pure-read fast path to protect.
        with self._lock():
            self._load_registry()

            if not by_is_admin:
                target_status = self._registry.get(namespace, {}).get(target)
                if target_status != DIDStatus.APPROVED:
                    return False, "approvers can only revoke APPROVED members"

            self._registry.get(namespace, {}).pop(target, None)
            if not self._registry.get(namespace):
                self._registry.pop(namespace, None)
            self._save_registry()

            if not (is_owner_key(target) or is_org_key(target)):
                record = self._load_record(target)
                if record:
                    record.namespaces.pop(namespace, None)
                    self._save_record(record)
            return True, f"revoked from {'all namespaces' if namespace == GLOBAL_NS else namespace}"

    def list_all(self, namespace: str | None = None) -> list[DIDRecord]:
        """List all DID records, optionally filtered to a namespace."""
        seen: set[str] = set()
        if namespace:
            dids = set(self._registry.get(namespace, {}).keys()) | set(
                self._registry.get(GLOBAL_NS, {}).keys()
            )
            if self._admin_did:
                dids.add(self._admin_did)
        else:
            dids = {self._admin_did} if self._admin_did else set()
            for ns_dids in self._registry.values():
                dids.update(ns_dids.keys())

        records = []
        for did in dids:
            if did in seen:
                continue
            seen.add(did)
            record = self._load_record(did)
            if record:
                records.append(record)
            elif did == self._admin_did:
                records.append(DIDRecord(did=did, created_at=0))
        return records

    def list_pending(self, namespace: str | None = None) -> list[DIDRecord]:
        """List DIDs pending approval for a namespace (or any namespace)."""
        result = []
        namespaces = [namespace] if namespace else list(self._registry.keys())
        seen: set[str] = set()
        for ns in namespaces:
            for did, status in self._registry.get(ns, {}).items():
                if status == DIDStatus.PENDING and did not in seen:
                    seen.add(did)
                    record = self._load_record(did)
                    if record:
                        result.append(record)
        return result

    def get_last_instance(self, did: str) -> str | None:
        """Get the last Hopper instance this DID connected to."""
        record = self._load_record(did)
        return record.last_instance if record else None

    def update_last_instance(self, did: str, instance: str) -> None:
        """Update the last Hopper instance this DID connected to.

        Creates a minimal DID record if one doesn't exist.
        """
        now = int(time.time() * 1000)
        record = self._load_record(did) or DIDRecord(did=did, created_at=now)
        record.last_instance = instance
        record.last_instance_at = now
        self._save_record(record)


@dataclass
class Owner:
    """A person who owns one or more DIDs.

    Owners group DIDs under one stable identity so grants can be made once
    (Phase B — see Owner-Identity-and-Instance-Discovery-Plan.md) and
    inherited by every linked device, instead of approved per-DID. Email
    addresses are labels, not the primary key — they change (this design
    exists because one already did); ``id`` does not.
    """

    id: str
    created_at: int
    primary_email: str | None = None
    emails: list[str] = field(default_factory=list)
    linked_dids: list[str] = field(default_factory=list)


@contextmanager
def _file_lock(lock_path: Path):
    """Cross-process exclusive lock via flock, guarding a read-modify-write
    critical section against concurrent workers.

    ``hopper server start --workers N>1`` is a supported flag that spawns
    separate OS processes sharing this ``storage_path`` with no other
    coordination between them — without this, two concurrent mutations of
    the same owner/org file race: both read the current state, both mutate
    their own in-memory copy, second write wins, the first mutation is
    silently lost even though its caller was told it succeeded.

    POSIX-only (``fcntl``), imported lazily inside this function rather
    than at module scope — this module is imported by client-side CLI code
    too (for the pure string helpers like ``owner_key``), and merely
    importing it should not require ``fcntl`` to exist. Only actually
    calling a mutating registry method (server-side only, in practice)
    needs it.
    """
    import fcntl

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


@dataclass
class OwnerRegistry:
    """Registry of owners — one JSON file per owner.

    Directory structure:
        storage_path/
        └── owners/
            ├── .lock                  # flock guard for mutations
            ├── did_index/
            │   └── {did_hash}.json    # {"owner_id": ...} — O(1) cache for
            │                          # get_by_did, self-healing against
            │                          # the owner file it points to
            └── {owner_id_hash}.json

    Phase A only: pure CRUD, no authorization behavior. A DID linking to an
    owner does not yet change what that DID can access — grant resolution
    falling through owner -> DID is Phase B (``DIDRegistry.is_authorized``).

    No separate email index: ``get_by_email`` scans, same as ``get_by_did``
    originally did — owners are created rarely, this isn't a hot path, and
    a scan means there is exactly one file written per email/owner
    mutation (the owner file itself), so there's no second index file that
    can desync from it on a crash between writes. ``get_by_did`` *is* a hot
    path — called on every ``/sync`` request, including for the common
    case of a DID never linked to any owner — so it gets the did_index
    fast path below instead; that index is a self-healing cache, not a
    second source of truth, so it doesn't reintroduce the same risk.
    """

    storage_path: Path

    def __post_init__(self) -> None:
        self.owners_dir = self.storage_path / "owners"
        self.owners_dir.mkdir(parents=True, exist_ok=True)
        self.did_index_dir = self.owners_dir / "did_index"
        self.did_index_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.owners_dir / ".lock"

    def _lock(self):
        return _file_lock(self.lock_path)

    def _owner_path(self, owner_id: str) -> Path:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:16]
        return self.owners_dir / f"{owner_hash}.json"

    def _did_index_path(self, did: str) -> Path:
        did_hash = hashlib.sha256(did.encode()).hexdigest()[:16]
        return self.did_index_dir / f"{did_hash}.json"

    def _write_did_pointer(self, did: str, owner_id: str | None) -> None:
        """``owner_id=None`` writes an explicit *negative* cache entry —
        "as of this write, this DID is confirmed linked to no one" — not a
        missing/absent pointer. See ``_get_by_did_fast``'s docstring for
        why the distinction matters."""
        with open(self._did_index_path(did), "w") as f:
            json.dump({"owner_id": owner_id}, f)

    def _save_owner(self, owner: Owner) -> None:
        with open(self._owner_path(owner.id), "w") as f:
            json.dump(
                {
                    "id": owner.id,
                    "created_at": owner.created_at,
                    "primary_email": owner.primary_email,
                    "emails": owner.emails,
                    "linked_dids": owner.linked_dids,
                },
                f,
                indent=2,
            )

    def get(self, owner_id: str) -> Owner | None:
        path = self._owner_path(owner_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                d = json.load(f)
            return Owner(
                id=d["id"],
                created_at=d["created_at"],
                primary_email=d.get("primary_email"),
                emails=d.get("emails", []),
                linked_dids=d.get("linked_dids", []),
            )
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def get_by_email(self, email: str) -> Owner | None:
        """O(n) scan — not a hot path (see class docstring). Use
        ``get_by_did`` for the hot-path case, which has a fast index."""
        for owner in self.list_all():
            if email in owner.emails:
                return owner
        return None

    def _get_by_did_fast(self, did: str) -> tuple[bool, Owner | None]:
        """Pointer-cache check only — no scan, no locking. Safe to call
        from anywhere, including from within a method that already holds
        ``self._lock()`` (``fcntl.flock`` is per-open-file-description,
        not reentrant within a process across separate ``open()`` calls on
        the same path — a second, unconditional lock acquisition from
        inside an already-locked section would deadlock against itself).

        Returns ``(cache_hit, owner)``. ``cache_hit=True`` means no scan is
        needed — either a verified positive hit (``owner`` set) or a
        negative cache entry (``owner=None``, meaning "confirmed unlinked
        as of the last lookup/link/unlink"). ``cache_hit=False`` means
        there's no usable entry — never looked up before, or a stale
        positive pointer that failed verification — and the caller must
        fall through to a (locked) scan.

        A negative entry has no single owner record to re-verify against
        the way a positive one does, so its safety comes from write
        discipline instead: ``link_did`` deletes this exact DID's pointer
        file *before* touching the owner file (see its comment), so the
        only states a reader can ever observe here are "no pointer at
        all" (correctly a cache miss, whatever the owner file currently
        says) or "a pointer that already reflects the current owner
        file" — never a negative entry sitting stale next to owner data
        that's already moved on. That's scoped to exactly the one DID
        being linked, unlike a shared generation counter, which an
        earlier version of this used and which invalidated every DID's
        negative entry on every mutation, not just the affected one's.
        """
        pointer_path = self._did_index_path(did)
        if not pointer_path.exists():
            return False, None
        try:
            with open(pointer_path) as f:
                owner_id = json.load(f).get("owner_id")
            if owner_id is None:
                return True, None  # confirmed negative cache entry
            owner = self.get(owner_id)
            if owner is not None and did in owner.linked_dids:
                return True, owner
        except (json.JSONDecodeError, OSError, KeyError):
            pass
        return False, None  # stale positive pointer; needs a rescan

    def _scan_and_heal_by_did(self, did: str, cache_negative: bool = True) -> Owner | None:
        """Full scan + pointer self-heal (positive *or* negative — a DID
        confirmed unlinked gets a negative cache entry too, so a repeat
        lookup for the same still-unlinked DID doesn't re-scan; see
        ``_get_by_did_fast``). Caller must already hold ``self._lock()`` —
        every current caller does (``get_by_did`` wraps this in its own
        lock; ``link_did``/``unlink_did`` call it directly since they're
        already inside their own locked section, per
        ``_get_by_did_fast``'s docstring on why this can't just call
        ``get_by_did`` and let it re-lock).

        ``cache_negative=False`` skips writing a negative pointer on a
        miss — see ``get_by_did``'s docstring for why a caller would ever
        want that."""
        for owner in self.list_all():
            if did in owner.linked_dids:
                self._write_did_pointer(did, owner.id)  # heal for next time
                return owner
        if cache_negative:
            self._write_did_pointer(did, None)
        return None

    def get_by_did(self, did: str, cache_negative: bool = True) -> Owner | None:
        """Find the owner a DID is linked to, if any.

        Fast path: a per-DID pointer file, checked first, that caches
        *both* outcomes — which owner a DID is linked to, and the
        confirmed-unlinked case too (``owner_id: null``). A negative
        lookup is one file read either way: a DID that's never been
        looked up at all still costs one scan on its first-ever call (as
        `/sync` traffic, that's genuinely unavoidable — nothing on this
        server has ever seen the DID before), but every *subsequent* call
        for that same still-unlinked DID is O(1) instead of re-scanning
        every owner file again — which matters, since the majority of
        real `/sync` traffic is a DID calling in repeatedly, not once.

        ``cache_negative=False`` finds the answer the same way but never
        *writes* a negative pointer file on a miss — the caller still gets
        a correct ``None``, it just doesn't earn a permanent file for
        asking. Exists because this whole method is reachable by any
        freshly-signed, never-approved DID (server.py's sync() resolves
        the caller's owner before checking authorization) — a positive
        cache entry only exists because some real owner really linked a
        real device, self-limiting, but nothing bounds how many *negative*
        entries a single caller could otherwise plant by minting a fresh
        did:key and signing one request each, for free, forever. Callers
        pass this once a DID has some other reason to be considered
        established (e.g. an existing DIDRegistry record) rather than for
        a key that, as far as the server can tell, might be single-use.

        The pointer is a cache, not the source of truth: on a positive
        hit, the owner record is loaded and the DID's presence in its
        ``linked_dids`` is verified before trusting it. A stale or missing
        pointer (a crash mid-write, or data from before this cache
        existed) falls through to a full scan and self-heals — never
        returns a wrong answer, worst case is one slow lookup. A negative
        hit's safety comes from ``link_did``'s write ordering instead —
        see ``_get_by_did_fast``'s docstring for the race that guards
        against.

        The fallback scan-and-heal runs under the same lock link_did/
        unlink_did use. Without it, a concurrent unlocked scan could read
        an owner file mid-relink (unlink_did(old) then link_did(new) are
        two separate locked calls, so there's a window between them) and
        heal the pointer to a momentarily-true-but-about-to-be-wrong
        answer — self-heals again on the *next* lookup either way, but an
        in-flight request in that window could get authorized against the
        wrong owner. The fast path above stays unlocked (it's the hot
        path and a stale hit still gets verified before being trusted).
        """
        cache_hit, owner = self._get_by_did_fast(did)
        if cache_hit:
            return owner
        with self._lock():
            return self._scan_and_heal_by_did(did, cache_negative=cache_negative)

    def list_all(self) -> list[Owner]:
        owners = []
        for path in self.owners_dir.glob("*.json"):
            try:
                with open(path) as f:
                    d = json.load(f)
                # Built directly from the already-read dict — this scan is
                # on the /sync hot path via get_by_did's fallback, so a
                # second open()+json.load() per file (self.get(d["id"]),
                # as this used to do) doubled the disk I/O for no reason.
                owners.append(
                    Owner(
                        id=d["id"],
                        created_at=d["created_at"],
                        primary_email=d.get("primary_email"),
                        emails=d.get("emails", []),
                        linked_dids=d.get("linked_dids", []),
                    )
                )
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        # created_at is millisecond resolution — two owners created in the
        # same request burst can tie, so id is a deterministic tiebreaker
        # rather than leaving order to directory-iteration happenstance.
        return sorted(owners, key=lambda o: (o.created_at, o.id))

    def create(self, owner_id: str, primary_email: str) -> tuple[Owner | None, str]:
        """Create a new owner. Fails if the id or email is already taken."""
        with self._lock():
            if self._owner_path(owner_id).exists():
                return None, f"owner '{owner_id}' already exists"
            existing = self.get_by_email(primary_email)
            if existing is not None:
                return None, f"email '{primary_email}' already linked to owner '{existing.id}'"

            now = int(time.time() * 1000)
            owner = Owner(
                id=owner_id, created_at=now, primary_email=primary_email, emails=[primary_email]
            )
            self._save_owner(owner)
            return owner, "created"

    def add_email(self, owner_id: str, email: str) -> tuple[bool, str]:
        with self._lock():
            owner = self.get(owner_id)
            if owner is None:
                return False, f"owner '{owner_id}' not found"
            existing = self.get_by_email(email)
            if existing is not None:
                if existing.id == owner_id:
                    return False, f"email already linked to '{owner_id}'"
                return False, f"email already linked to a different owner '{existing.id}'"

            owner.emails.append(email)
            self._save_owner(owner)
            return True, f"added {email} to '{owner_id}'"

    def link_did(self, owner_id: str, did: str) -> tuple[bool, str]:
        """Link a DID to an owner.

        Rejects a DID already linked to a *different* owner rather than
        silently reassigning it — matches the "conflicting owner claims"
        leaning in the design doc (admin must explicitly unlink first).
        """
        with self._lock():
            owner = self.get(owner_id)
            if owner is None:
                return False, f"owner '{owner_id}' not found"
            # Not self.get_by_did(did) — that would try to re-acquire this
            # same lock and deadlock. Already inside the lock, so do its
            # fast-path-then-scan directly instead.
            cache_hit, existing = self._get_by_did_fast(did)
            if not cache_hit:
                existing = self._scan_and_heal_by_did(did)
            if existing is not None and existing.id != owner_id:
                return False, f"DID already linked to a different owner '{existing.id}'"
            if did in owner.linked_dids:
                return False, f"DID already linked to '{owner_id}'"

            # Drop any pointer for this exact DID *before* mutating the
            # owner file — if it was a negative entry, that entry is
            # about to become wrong. Deleting it first (rather than
            # overwriting it after, as the positive write below already
            # does) means a reader landing in the gap between this line
            # and the owner-file write below finds no pointer at all —
            # correctly a cache miss, which falls through to the locked
            # scan and waits for this operation to finish — instead of a
            # stale negative entry sitting next to owner data that's
            # already moved on. Scoped to exactly this one DID; see
            # _get_by_did_fast's docstring for why that's better than the
            # shared generation counter an earlier version of this used.
            self._did_index_path(did).unlink(missing_ok=True)
            owner.linked_dids.append(did)
            self._save_owner(owner)
            self._write_did_pointer(did, owner_id)
            return True, f"linked {did} to '{owner_id}'"

    def unlink_did(self, owner_id: str, did: str) -> tuple[bool, str]:
        with self._lock():
            owner = self.get(owner_id)
            if owner is None:
                return False, f"owner '{owner_id}' not found"
            if did not in owner.linked_dids:
                return False, f"DID not linked to '{owner_id}'"

            owner.linked_dids.remove(did)
            self._save_owner(owner)
            # Negative cache entry, not a delete — the DID is now
            # confirmed unlinked, so the *next* lookup should be the fast
            # path too, not fall through to a scan just because there's no
            # pointer file at all (see get_by_did's docstring). No race to
            # guard here the way link_did has: a stale *positive* pointer
            # left over from before this unlink already re-verifies
            # against the owner record on every read and self-corrects
            # (did no longer in linked_dids), so there's no window where
            # trusting the old pointer would give a wrong answer.
            self._write_did_pointer(did, None)
            return True, f"unlinked {did} from '{owner_id}'"


ORG_KEY_PREFIX = "org:"


def org_key(org_id: str) -> str:
    """Registry key representing an org's grant — same trick as owner_key:
    just another key in the flat namespace registry, no second table."""
    return f"{ORG_KEY_PREFIX}{org_id}"


def is_org_key(key: str) -> bool:
    return key.startswith(ORG_KEY_PREFIX)


@dataclass
class Org:
    """A group of owners — a grant-holder for instances that aren't any
    one person's (Phase E). Membership authority is admin-only for v1:
    both creating an org and changing its membership, matching the
    owner-creation gate rather than the self-service device-invite path —
    org membership changes who inherits access far more broadly than one
    person adding their own laptop does, so this plan starts conservative.
    """

    id: str
    created_at: int
    name: str = ""
    member_owner_ids: list[str] = field(default_factory=list)


@dataclass
class OrgRegistry:
    """Registry of orgs — one JSON file per org, same pattern as
    OwnerRegistry (no email-like alias index needed here).

    Directory structure:
        storage_path/
        └── orgs/
            ├── .lock                  # flock guard for mutations
            └── {org_id_hash}.json

    Same multi-worker race as OwnerRegistry (see ``_file_lock``'s
    docstring) applies here too — every mutating method holds the lock for
    its full read-modify-write section.
    """

    storage_path: Path

    def __post_init__(self) -> None:
        self.orgs_dir = self.storage_path / "orgs"
        self.orgs_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.orgs_dir / ".lock"

    def _lock(self):
        return _file_lock(self.lock_path)

    def _org_path(self, org_id: str) -> Path:
        org_hash = hashlib.sha256(org_id.encode()).hexdigest()[:16]
        return self.orgs_dir / f"{org_hash}.json"

    def _save_org(self, org: Org) -> None:
        with open(self._org_path(org.id), "w") as f:
            json.dump(
                {
                    "id": org.id,
                    "created_at": org.created_at,
                    "name": org.name,
                    "member_owner_ids": org.member_owner_ids,
                },
                f,
                indent=2,
            )

    def get(self, org_id: str) -> Org | None:
        path = self._org_path(org_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                d = json.load(f)
            return Org(
                id=d["id"],
                created_at=d["created_at"],
                name=d.get("name", ""),
                member_owner_ids=d.get("member_owner_ids", []),
            )
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def list_all(self) -> list[Org]:
        orgs = []
        for path in self.orgs_dir.glob("*.json"):
            try:
                with open(path) as f:
                    d = json.load(f)
                orgs.append(
                    Org(
                        id=d["id"],
                        created_at=d["created_at"],
                        name=d.get("name", ""),
                        member_owner_ids=d.get("member_owner_ids", []),
                    )
                )
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        # Deterministic even when created_at ties (see OwnerRegistry.list_all).
        return sorted(orgs, key=lambda o: (o.created_at, o.id))

    def orgs_for_owner(self, owner_id: str) -> list[Org]:
        """Every org the given owner is a member of."""
        return [o for o in self.list_all() if owner_id in o.member_owner_ids]

    def create(self, org_id: str, name: str) -> tuple[Org | None, str]:
        with self._lock():
            if self._org_path(org_id).exists():
                return None, f"org '{org_id}' already exists"
            now = int(time.time() * 1000)
            org = Org(id=org_id, created_at=now, name=name)
            self._save_org(org)
            return org, "created"

    def add_member(self, org_id: str, owner_id: str) -> tuple[bool, str]:
        with self._lock():
            org = self.get(org_id)
            if org is None:
                return False, f"org '{org_id}' not found"
            if owner_id in org.member_owner_ids:
                return False, f"owner '{owner_id}' already a member of '{org_id}'"
            org.member_owner_ids.append(owner_id)
            self._save_org(org)
            return True, f"added {owner_id} to '{org_id}'"

    def remove_member(self, org_id: str, owner_id: str) -> tuple[bool, str]:
        with self._lock():
            org = self.get(org_id)
            if org is None:
                return False, f"org '{org_id}' not found"
            if owner_id not in org.member_owner_ids:
                return False, f"owner '{owner_id}' not a member of '{org_id}'"
            org.member_owner_ids.remove(owner_id)
            self._save_org(org)
            return True, f"removed {owner_id} from '{org_id}'"


class InviteKind(str, Enum):
    """What redeeming an invite actually does.

    NAMESPACE (original): grants the redeeming DID ``role`` on ``namespace``
    directly. DEVICE (Phase C): links the redeeming DID to an existing
    owner — self-service, mintable by any DID already linked to that
    owner. NEW_OWNER (Phase C): creates a brand-new owner and links the
    redeeming DID as its first device — admin only to mint, this is the
    server-admission gate.
    """

    NAMESPACE = "namespace"
    DEVICE = "device"
    NEW_OWNER = "new_owner"


@dataclass
class Invite:
    """An invite record — three kinds sharing one token lifecycle (hash
    lookup, expiry/max-uses, atomic redeem bookkeeping). Which fields are
    meaningful depends on ``kind``:

    - NAMESPACE: ``namespace`` + ``role``.
    - DEVICE: ``owner_id`` (the existing owner a new DID will link to).
    - NEW_OWNER: ``owner_id`` (the id to create) + ``new_owner_email``.

    The raw token is never stored — only its SHA256 hash. The full token
    value is returned once, at creation time.
    """

    token_hash: str
    issued_by: str
    created_at: int
    expires_at: int | None
    max_uses: int = 1
    uses: int = 0
    kind: InviteKind = InviteKind.NAMESPACE
    namespace: str = ""
    role: DIDStatus = DIDStatus.APPROVED
    owner_id: str = ""
    new_owner_email: str = ""
    redeemed_by: list[str] = field(default_factory=list)

    def is_valid(self, now_ms: int | None = None) -> tuple[bool, str]:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        if self.expires_at is not None and now >= self.expires_at:
            return False, "invite expired"
        if self.uses >= self.max_uses:
            return False, "invite exhausted"
        return True, ""


@dataclass
class InviteStore:
    """Token-based invite store.

    Tokens are bearer secrets; only their hash is persisted. Directory layout:
        storage_path/invites/{token_hash}.json
    """

    storage_path: Path

    def __post_init__(self) -> None:
        self.invites_dir = self.storage_path / "invites"
        self.invites_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.invites_dir / ".lock"

    def _lock(self):
        return _file_lock(self.lock_path)

    @staticmethod
    def _hash(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _path(self, token_hash: str) -> Path:
        return self.invites_dir / f"{token_hash}.json"

    def _save(self, invite: Invite) -> None:
        with open(self._path(invite.token_hash), "w") as f:
            json.dump(
                {
                    "token_hash": invite.token_hash,
                    "kind": invite.kind.value,
                    "namespace": invite.namespace,
                    "role": invite.role.value,
                    "owner_id": invite.owner_id,
                    "new_owner_email": invite.new_owner_email,
                    "issued_by": invite.issued_by,
                    "created_at": invite.created_at,
                    "expires_at": invite.expires_at,
                    "max_uses": invite.max_uses,
                    "uses": invite.uses,
                    "redeemed_by": invite.redeemed_by,
                },
                f,
                indent=2,
            )

    def _load_path(self, path: Path) -> Invite | None:
        if not path.exists():
            return None
        try:
            with open(path) as f:
                d = json.load(f)
            return Invite(
                token_hash=d["token_hash"],
                # Missing "kind" means a file written before Phase C — those
                # are always namespace invites.
                kind=InviteKind(d.get("kind", InviteKind.NAMESPACE.value)),
                namespace=d.get("namespace", ""),
                role=DIDStatus(d.get("role", DIDStatus.APPROVED.value)),
                owner_id=d.get("owner_id", ""),
                new_owner_email=d.get("new_owner_email", ""),
                issued_by=d["issued_by"],
                created_at=d["created_at"],
                expires_at=d.get("expires_at"),
                max_uses=d["max_uses"],
                uses=d.get("uses", 0),
                redeemed_by=d.get("redeemed_by", []),
            )
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            return None

    def create(
        self,
        issued_by: str,
        expires_at: int | None,
        max_uses: int = 1,
        kind: InviteKind = InviteKind.NAMESPACE,
        namespace: str = "",
        role: DIDStatus = DIDStatus.APPROVED,
        owner_id: str = "",
        new_owner_email: str = "",
    ) -> tuple[str, Invite]:
        """Create an invite and return (token, record). Token is only returned here.

        Which of ``namespace``/``role`` vs ``owner_id``/``new_owner_email``
        matters depends on ``kind`` — see ``Invite``'s docstring. Defaulting
        ``kind`` to NAMESPACE keeps every pre-Phase-C caller working
        unchanged.
        """
        import secrets

        token = "hinv_" + secrets.token_urlsafe(24)
        now = int(time.time() * 1000)
        invite = Invite(
            token_hash=self._hash(token),
            kind=kind,
            namespace=namespace,
            role=role,
            owner_id=owner_id,
            new_owner_email=new_owner_email,
            issued_by=issued_by,
            created_at=now,
            expires_at=expires_at,
            max_uses=max_uses,
            uses=0,
        )
        self._save(invite)
        return token, invite

    def get(self, token: str) -> Invite | None:
        return self._load_path(self._path(self._hash(token)))

    def redeem(self, token: str, by_did: str) -> tuple[Invite | None, str]:
        """Atomically redeem an invite. Returns (invite, message).

        Locked: without it, two concurrent redemptions of the same (often
        max_uses=1) token can both read uses=0, both pass validation, and
        both write — second write wins, silently granting a single-use
        invite to two different identities with neither aware the other
        happened. Call this *before* attempting the caller's actual
        kind-specific grant (link_did, owner create, ...), and if that
        grant then fails, call ``unredeem`` to give the slot back rather
        than leaving the token burned for nothing.
        """
        with self._lock():
            invite = self.get(token)
            if invite is None:
                return None, "invite not found"
            ok, reason = invite.is_valid()
            if not ok:
                return None, reason
            if by_did in invite.redeemed_by:
                return None, "already redeemed by this DID"
            invite.uses += 1
            invite.redeemed_by.append(by_did)
            self._save(invite)
            return invite, "redeemed"

    def unredeem(self, token: str, by_did: str) -> None:
        """Roll back a ``redeem()`` whose caller's actual grant
        subsequently failed to apply (e.g. DEVICE's ``link_did`` losing a
        race after this already reserved the slot) — gives the consumed
        use back instead of leaving an often-single-use token permanently
        burned for a grant that never happened. Best-effort: if the
        invite is gone or wasn't recorded as redeemed by this DID, this is
        a silent no-op rather than an error, since the caller is already
        in an error-handling path of its own.
        """
        with self._lock():
            invite = self.get(token)
            if invite is None or by_did not in invite.redeemed_by:
                return
            invite.redeemed_by.remove(by_did)
            invite.uses = max(0, invite.uses - 1)
            self._save(invite)

    def list_all(self, namespace: str | None = None) -> list[Invite]:
        invites = []
        for p in self.invites_dir.glob("*.json"):
            inv = self._load_path(p)
            if inv and (namespace is None or inv.namespace == namespace):
                invites.append(inv)
        return sorted(invites, key=lambda i: i.created_at, reverse=True)

    def revoke(self, token_hash_prefix: str) -> tuple[bool, str]:
        """Revoke by full hash or unique prefix.

        Locked, matching redeem()/unredeem(): unlocked, a concurrent
        redeem() could read the file, compute its new uses/redeemed_by,
        and self._save() (which reopens for write, recreating the file)
        *after* this had already unlink()'d it — both calls report
        success, and the "revoked" invite ends up back on disk with the
        concurrent redemption recorded, so the grant that revocation was
        supposed to prevent goes through anyway. Revocation is the
        mechanism for killing a leaked token, so this race matters even
        though it's the least-hot of InviteStore's operations.
        """
        with self._lock():
            matches = [
                p for p in self.invites_dir.glob("*.json") if p.stem.startswith(token_hash_prefix)
            ]
            if not matches:
                return False, "no matching invite"
            if len(matches) > 1:
                return False, f"ambiguous prefix: {len(matches)} matches"
            matches[0].unlink()
            return True, "revoked"


@dataclass
class StoredTask:
    """A task stored on the server with metadata."""

    task: SyncTask
    received_at: int  # ms since epoch
    from_did: str


def _did_hash(did: str) -> str:
    return hashlib.sha256(did.encode()).hexdigest()[:16]


@dataclass
class UpstreamStorage:
    """Flat file storage for upstream server.

    Tasks are namespaced by instance name only. DIDs are used for auth and
    attribution, not storage partitioning — any approved DID can collaborate
    on a shared instance namespace.

    Directory structure:
        storage_path/
        ├── tasks/
        │   └── {instance_name}/
        │       └── {task_id}.json
        ├── dids/
        │   ├── registry.json
        │   └── {did_hash}.json
        ├── owners/
        │   ├── index.json
        │   └── {owner_id_hash}.json
        ├── orgs/
        │   └── {org_id_hash}.json
        └── index.json  # {"instance/task_id": updated_at_ms}
    """

    storage_path: Path
    _index: dict[str, int] = field(default_factory=dict)  # "instance/task_id" -> updated_at
    # Sorted list of (timestamp, key) for efficient range queries
    _index_by_time: list[tuple[int, str]] = field(default_factory=list)
    did_registry: DIDRegistry = field(init=False)
    owner_registry: OwnerRegistry = field(init=False)
    org_registry: OrgRegistry = field(init=False)
    invites: InviteStore = field(init=False)
    shadow_writer: RevisionShadowWriter | None = field(default=None)

    def __post_init__(self) -> None:
        self.tasks_dir = self.storage_path / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_path / "index.json"
        self._migrate_did_partitioned_tasks()
        self._load_index()
        self.did_registry = DIDRegistry(self.storage_path)
        self.owner_registry = OwnerRegistry(self.storage_path)
        self.org_registry = OrgRegistry(self.storage_path)
        self.invites = InviteStore(self.storage_path)

    def _migrate_did_partitioned_tasks(self) -> None:
        """Flatten legacy tasks/{did_hash}/{instance}/ into tasks/{instance}/."""
        # Detect old layout: subdirs whose names look like 16-char hex hashes
        import re

        did_hash_re = re.compile(r"^[0-9a-f]{16}$")
        for did_dir in list(self.tasks_dir.iterdir()):
            if not did_dir.is_dir() or not did_hash_re.match(did_dir.name):
                continue
            for instance_dir in list(did_dir.iterdir()):
                if not instance_dir.is_dir():
                    continue
                dest = self.tasks_dir / instance_dir.name
                dest.mkdir(parents=True, exist_ok=True)
                for task_file in list(instance_dir.glob("*.json")):
                    target = dest / task_file.name
                    if not target.exists():
                        task_file.rename(target)
                    else:
                        task_file.unlink()  # duplicate; dest wins
                instance_dir.rmdir()
            try:
                did_dir.rmdir()
            except OSError:
                pass  # non-empty means something unexpected; leave it

        # Also handle original flat tasks/{task_id}.json
        for task_file in list(self.tasks_dir.glob("*.json")):
            try:
                with open(task_file) as f:
                    data = json.load(f)
                instance = data.get("task", {}).get("instance", "local")
                task_id = data.get("task", {}).get("id", task_file.stem)
                dest_dir = self.tasks_dir / instance
                dest_dir.mkdir(parents=True, exist_ok=True)
                task_file.rename(dest_dir / f"{task_id}.json")
            except (json.JSONDecodeError, OSError, KeyError):
                continue

    def _index_key(self, instance: str, task_id: str) -> str:
        return f"{instance}/{task_id}"

    def _task_path(self, instance: str, task_id: str) -> Path:
        return self.tasks_dir / instance / f"{task_id}.json"

    def _load_index(self) -> None:
        if self.index_path.exists():
            try:
                with open(self.index_path) as f:
                    self._index = json.load(f)
                # Rebuild if index has old did_hash/instance/task_id keys (3 parts)
                if any(k.count("/") != 1 for k in self._index if "/" in k):
                    self._rebuild_index()
                elif any("/" not in k for k in self._index):
                    self._rebuild_index()
                else:
                    # Build sorted index from loaded data
                    self._rebuild_sorted_index()
            except (json.JSONDecodeError, OSError):
                self._index = {}
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _rebuild_sorted_index(self) -> None:
        """Rebuild the sorted timestamp index from the main index."""
        self._index_by_time = sorted(
            ((ts, key) for key, ts in self._index.items()),
            key=lambda x: x[0],
        )

    def _save_index(self) -> None:
        with open(self.index_path, "w") as f:
            json.dump(self._index, f)

    def _rebuild_index(self) -> None:
        """Rebuild the index from stored task files.

        The index stores server-received time (received_at), not client-reported
        updated_at, so the pull cursor is on a clock the server controls.
        Falls back to updated_at for older files that predate this convention.
        """
        self._index = {}
        for task_file in self.tasks_dir.glob("*/*.json"):
            try:
                with open(task_file) as f:
                    data = json.load(f)
                instance = data.get("task", {}).get("instance", "local")
                task_id = data.get("task", {}).get("id")
                if not task_id:
                    continue
                # Prefer server-side received_at; fall back to updated_at for
                # files written by older server versions.
                index_ts = data.get("received_at")
                if not index_ts:
                    updated_at = data.get("task", {}).get("updated_at")
                    if updated_at:
                        if isinstance(updated_at, str):
                            from datetime import datetime

                            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                            index_ts = int(dt.timestamp() * 1000)
                        else:
                            index_ts = updated_at
                if index_ts:
                    self._index[self._index_key(instance, task_id)] = index_ts
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        self._save_index()
        self._rebuild_sorted_index()

    def get(self, instance: str, task_id: str) -> StoredTask | None:
        """Get a task by instance and ID."""
        path = self._task_path(instance, task_id)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
                return StoredTask(
                    task=SyncTask(**data["task"]),
                    received_at=data["received_at"],
                    from_did=data.get("from_did", "unknown"),
                )
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def put(self, task: SyncTask, from_did: str) -> tuple[bool, str]:
        """Store a task, returns (accepted, reason).

        Uses last-write-wins based on client-reported updated_at for conflict
        detection (so the best-intentioned write wins), but indexes on
        server-side received_at so that list_since() uses a clock the server
        controls.  This makes the pull cursor immune to client clock skew.
        """
        task_id = task.id
        instance = task.instance or "local"
        now = int(time.time() * 1000)
        key = self._index_key(instance, task_id)

        # Parse client-reported timestamp for conflict detection only.
        if task.updated_at:
            if isinstance(task.updated_at, str):
                from datetime import datetime

                dt = datetime.fromisoformat(task.updated_at.replace("Z", "+00:00"))
                incoming_ts = int(dt.timestamp() * 1000)
            else:
                incoming_ts = int(task.updated_at.timestamp() * 1000)
        else:
            incoming_ts = now

        if key in self._index:
            # _index stores received_at; we need the stored task's updated_at
            # for conflict resolution.  Load it from disk.
            stored_task = self.get(instance, task_id)
            if stored_task is not None and stored_task.task.updated_at:
                stored_updated_at = stored_task.task.updated_at
                if isinstance(stored_updated_at, str):
                    from datetime import datetime

                    stored_updated_at = datetime.fromisoformat(
                        stored_updated_at.replace("Z", "+00:00")
                    )
                stored_ts = int(stored_updated_at.timestamp() * 1000)
                if incoming_ts <= stored_ts:
                    return (
                        False,
                        f"conflict: server has newer version ({stored_ts} >= {incoming_ts})",
                    )

        stored = StoredTask(task=task, received_at=now, from_did=from_did)
        path = self._task_path(instance, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        task_payload = task.model_dump(mode="json")
        with open(path, "w") as f:
            json.dump(
                {
                    "task": task_payload,
                    "received_at": stored.received_at,
                    "from_did": stored.from_did,
                },
                f,
                indent=2,
                default=str,
            )

        # Index on server-received time, not client-reported updated_at.
        # This keeps list_since() on a clock the server controls, eliminating
        # client clock-skew from the pull cursor entirely.
        old_ts = self._index.get(key)
        self._index[key] = now
        self._save_index()

        # Maintain sorted index: remove old entry if exists, insert new one
        if old_ts is not None:
            # Remove old entry (linear scan, but updates are infrequent)
            self._index_by_time = [(ts, k) for ts, k in self._index_by_time if k != key]
        # Insert in sorted position using bisect
        import bisect

        bisect.insort(self._index_by_time, (now, key))

        # Phase 4a shadow write (fail-soft; JSON above is authoritative)
        if self.shadow_writer is not None:
            self.shadow_writer.record_write(task_payload, from_did, stored.received_at)

        return True, "accepted"

    def list_since(self, since_ms: int, instance: str) -> list[SyncTask]:
        """List tasks for an instance updated since a timestamp.

        Uses binary search on sorted timestamp index for O(log n) lookup,
        then batch-loads matching tasks to avoid N+1 disk reads.
        """
        import bisect

        prefix = instance + "/"

        # Binary search to find starting position (first entry > since_ms)
        # bisect_right finds insertion point for (since_ms,) which gives us
        # the first entry with timestamp > since_ms
        start_idx = bisect.bisect_right(self._index_by_time, (since_ms, ""))

        # Collect matching task IDs (only those for this instance)
        task_ids = []
        for i in range(start_idx, len(self._index_by_time)):
            _, key = self._index_by_time[i]
            if key.startswith(prefix):
                _, task_id = key.split("/", 1)
                task_ids.append(task_id)

        # Batch load all matching tasks
        tasks = []
        for task_id in task_ids:
            stored = self.get(instance, task_id)
            if stored:
                tasks.append(stored.task)
        return tasks

    def list_all(self, instance: str) -> list[SyncTask]:
        """List all tasks for an instance."""
        return self.list_since(0, instance)

    def delete(self, instance: str, task_id: str) -> bool:
        """Delete a task."""
        path = self._task_path(instance, task_id)
        key = self._index_key(instance, task_id)
        if path.exists():
            path.unlink()
            self._index.pop(key, None)
            self._save_index()
            # Remove from sorted index
            self._index_by_time = [(ts, k) for ts, k in self._index_by_time if k != key]
            return True
        return False

    def get_updated_at(self, instance: str, task_id: str) -> int | None:
        """Get the updated_at timestamp for a task."""
        return self._index.get(self._index_key(instance, task_id))
