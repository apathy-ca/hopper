"""Server-side storage for upstream sync.

Simple flat file storage with JSON tasks and an index for quick lookups.
"""

from __future__ import annotations

import hashlib
import json
import time
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
        self._load_registry()

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
        if owner_id is not None and self._is_directly_authorized(
            owner_key(owner_id), namespace
        ):
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
        """
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

        if owner_id is not None and self._is_directly_authorized(owner_key(owner_id), namespace):
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
        """
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

    def approve(
        self,
        target: str,
        namespace: str,
        by_did: str,
        role: DIDStatus = DIDStatus.APPROVED,
    ) -> tuple[bool, str]:
        """Approve a DID — or (Phase B) an ``owner:<id>`` key — for a
        namespace at a given role.

        Authority:
        - Admin may set any role, any namespace (including '*').
        - Approver may set role=APPROVED on their specific namespace only.

        Approving an owner key grants every DID currently *and future*
        linked to that owner, without touching any of them individually.
        """
        if role not in (DIDStatus.APPROVED, DIDStatus.APPROVER):
            return False, f"invalid role: {role}"
        if self.is_admin(target):
            return False, "cannot modify admin DID"

        by_is_admin = self.is_admin(by_did)
        if not by_is_admin:
            if role == DIDStatus.APPROVER:
                return False, "only admin can grant approver role"
            if namespace == GLOBAL_NS:
                return False, "only admin can approve across all namespaces"
            if not self.is_approver(by_did, namespace):
                return False, f"not authorized to approve for namespace '{namespace}'"

        self.set_status(target, namespace, role, by_did)
        scope = "all namespaces" if namespace == GLOBAL_NS else namespace
        label = "approver on" if role == DIDStatus.APPROVER else "approved for"
        return True, f"{label} {scope}"

    def revoke(self, target: str, namespace: str, by_did: str) -> tuple[bool, str]:
        """Revoke a DID's — or (Phase B) an owner's — access to a namespace
        (or all if namespace == '*').

        Admin can revoke anyone. Approver can revoke only APPROVED members of
        their specific namespace (never another approver or admin).
        """
        if self.is_admin(target):
            return False, "cannot revoke admin DID"

        by_is_admin = self.is_admin(by_did)
        if not by_is_admin:
            if namespace == GLOBAL_NS:
                return False, "only admin can revoke across all namespaces"
            if not self.is_approver(by_did, namespace):
                return False, f"not authorized to revoke for namespace '{namespace}'"
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


@dataclass
class OwnerRegistry:
    """Registry of owners — one JSON file per owner, plus an email index.

    Directory structure:
        storage_path/
        └── owners/
            ├── index.json        # email -> owner_id
            └── {owner_id_hash}.json

    Phase A only: pure CRUD, no authorization behavior. A DID linking to an
    owner does not yet change what that DID can access — grant resolution
    falling through owner -> DID is Phase B (``DIDRegistry.is_authorized``).
    """

    storage_path: Path
    _email_index: dict[str, str] = field(default_factory=dict)  # email -> owner_id

    def __post_init__(self) -> None:
        self.owners_dir = self.storage_path / "owners"
        self.owners_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.owners_dir / "index.json"
        self._load_index()

    def _load_index(self) -> None:
        if self.index_path.exists():
            try:
                with open(self.index_path) as f:
                    self._email_index = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._email_index = {}
        else:
            self._email_index = {}

    def _save_index(self) -> None:
        with open(self.index_path, "w") as f:
            json.dump(self._email_index, f)

    def _owner_path(self, owner_id: str) -> Path:
        owner_hash = hashlib.sha256(owner_id.encode()).hexdigest()[:16]
        return self.owners_dir / f"{owner_hash}.json"

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
        owner_id = self._email_index.get(email)
        return self.get(owner_id) if owner_id else None

    def get_by_did(self, did: str) -> Owner | None:
        """Find the owner a DID is linked to, if any.

        O(n) over owners via directory scan — fine at personal-server scale;
        revisit (maintain a did -> owner_id index like the email one) if the
        owner count ever grows large enough to matter.
        """
        for path in self.owners_dir.glob("*.json"):
            if path == self.index_path:
                continue
            try:
                with open(path) as f:
                    d = json.load(f)
                if did in d.get("linked_dids", []):
                    return self.get(d["id"])
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        return None

    def list_all(self) -> list[Owner]:
        owners = []
        for path in self.owners_dir.glob("*.json"):
            if path == self.index_path:
                continue
            try:
                with open(path) as f:
                    d = json.load(f)
                owner = self.get(d["id"])
                if owner:
                    owners.append(owner)
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        # created_at is millisecond resolution — two owners created in the
        # same request burst can tie, so id is a deterministic tiebreaker
        # rather than leaving order to directory-iteration happenstance.
        return sorted(owners, key=lambda o: (o.created_at, o.id))

    def create(self, owner_id: str, primary_email: str) -> tuple[Owner | None, str]:
        """Create a new owner. Fails if the id or email is already taken."""
        if self._owner_path(owner_id).exists():
            return None, f"owner '{owner_id}' already exists"
        if primary_email in self._email_index:
            existing = self._email_index[primary_email]
            return None, f"email '{primary_email}' already linked to owner '{existing}'"

        now = int(time.time() * 1000)
        owner = Owner(
            id=owner_id, created_at=now, primary_email=primary_email, emails=[primary_email]
        )
        self._save_owner(owner)
        self._email_index[primary_email] = owner_id
        self._save_index()
        return owner, "created"

    def add_email(self, owner_id: str, email: str) -> tuple[bool, str]:
        owner = self.get(owner_id)
        if owner is None:
            return False, f"owner '{owner_id}' not found"
        if email in self._email_index:
            existing = self._email_index[email]
            if existing == owner_id:
                return False, f"email already linked to '{owner_id}'"
            return False, f"email already linked to a different owner '{existing}'"

        owner.emails.append(email)
        self._save_owner(owner)
        self._email_index[email] = owner_id
        self._save_index()
        return True, f"added {email} to '{owner_id}'"

    def link_did(self, owner_id: str, did: str) -> tuple[bool, str]:
        """Link a DID to an owner.

        Rejects a DID already linked to a *different* owner rather than
        silently reassigning it — matches the "conflicting owner claims"
        leaning in the design doc (admin must explicitly unlink first).
        """
        owner = self.get(owner_id)
        if owner is None:
            return False, f"owner '{owner_id}' not found"
        existing = self.get_by_did(did)
        if existing is not None and existing.id != owner_id:
            return False, f"DID already linked to a different owner '{existing.id}'"
        if did in owner.linked_dids:
            return False, f"DID already linked to '{owner_id}'"

        owner.linked_dids.append(did)
        self._save_owner(owner)
        return True, f"linked {did} to '{owner_id}'"

    def unlink_did(self, owner_id: str, did: str) -> tuple[bool, str]:
        owner = self.get(owner_id)
        if owner is None:
            return False, f"owner '{owner_id}' not found"
        if did not in owner.linked_dids:
            return False, f"DID not linked to '{owner_id}'"

        owner.linked_dids.remove(did)
        self._save_owner(owner)
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
            └── {org_id_hash}.json
    """

    storage_path: Path

    def __post_init__(self) -> None:
        self.orgs_dir = self.storage_path / "orgs"
        self.orgs_dir.mkdir(parents=True, exist_ok=True)

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
                org = self.get(d["id"])
                if org:
                    orgs.append(org)
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        # Deterministic even when created_at ties (see OwnerRegistry.list_all).
        return sorted(orgs, key=lambda o: (o.created_at, o.id))

    def orgs_for_owner(self, owner_id: str) -> list[Org]:
        """Every org the given owner is a member of."""
        return [o for o in self.list_all() if owner_id in o.member_owner_ids]

    def create(self, org_id: str, name: str) -> tuple[Org | None, str]:
        if self._org_path(org_id).exists():
            return None, f"org '{org_id}' already exists"
        now = int(time.time() * 1000)
        org = Org(id=org_id, created_at=now, name=name)
        self._save_org(org)
        return org, "created"

    def add_member(self, org_id: str, owner_id: str) -> tuple[bool, str]:
        org = self.get(org_id)
        if org is None:
            return False, f"org '{org_id}' not found"
        if owner_id in org.member_owner_ids:
            return False, f"owner '{owner_id}' already a member of '{org_id}'"
        org.member_owner_ids.append(owner_id)
        self._save_org(org)
        return True, f"added {owner_id} to '{org_id}'"

    def remove_member(self, org_id: str, owner_id: str) -> tuple[bool, str]:
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
        """Atomically redeem an invite. Returns (invite, message)."""
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

    def list_all(self, namespace: str | None = None) -> list[Invite]:
        invites = []
        for p in self.invites_dir.glob("*.json"):
            inv = self._load_path(p)
            if inv and (namespace is None or inv.namespace == namespace):
                invites.append(inv)
        return sorted(invites, key=lambda i: i.created_at, reverse=True)

    def revoke(self, token_hash_prefix: str) -> tuple[bool, str]:
        """Revoke by full hash or unique prefix."""
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
