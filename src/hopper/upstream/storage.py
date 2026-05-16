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
from typing import TYPE_CHECKING, Any

from .protocol import SyncTask

if TYPE_CHECKING:
    from .shadow import RevisionShadowWriter


class DIDStatus(str, Enum):
    """Status of a DID for a given namespace."""

    ADMIN = "admin"        # Server admin — implicitly approved for all namespaces
    APPROVER = "approver"  # Authorized for namespace AND can approve/invite others for it
    APPROVED = "approved"
    PENDING = "pending"


GLOBAL_NS = "*"  # Sentinel: approved for all namespaces


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
                    ns: {did: DIDStatus(s) for did, s in dids.items()}
                    for ns, dids in raw.items()
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

    def is_authorized(self, did: str, namespace: str) -> bool:
        """Check if DID is authorized for a namespace."""
        if self.is_admin(did):
            return True
        authorized = {DIDStatus.APPROVED, DIDStatus.APPROVER}
        # Global approval
        if did in self._registry.get(GLOBAL_NS, {}):
            return self._registry[GLOBAL_NS][did] in authorized
        # Namespace-specific approval
        return self._registry.get(namespace, {}).get(did) in authorized

    def is_approver(self, did: str, namespace: str) -> bool:
        """Check if DID can approve/invite others for a namespace."""
        if self.is_admin(did):
            return True
        # Global approver via '*'
        if self._registry.get(GLOBAL_NS, {}).get(did) == DIDStatus.APPROVER:
            return True
        return self._registry.get(namespace, {}).get(did) == DIDStatus.APPROVER

    def get_status(self, did: str, namespace: str) -> DIDStatus | None:
        if self.is_admin(did):
            return DIDStatus.ADMIN
        if did in self._registry.get(GLOBAL_NS, {}):
            return self._registry[GLOBAL_NS][did]
        return self._registry.get(namespace, {}).get(did)

    def register_or_get(self, did: str, namespace: str) -> tuple[DIDStatus, bool]:
        """Register DID for a namespace, or return existing status.

        Returns (status, is_new). First DID becomes global admin.
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

        # Register as pending for this namespace
        self._registry.setdefault(namespace, {})[did] = DIDStatus.PENDING
        self._save_registry()
        record = self._load_record(did) or DIDRecord(did=did, created_at=now)
        record.namespaces[namespace] = NamespaceApproval(status=DIDStatus.PENDING)
        self._save_record(record)
        return DIDStatus.PENDING, True

    def set_status(
        self, did: str, namespace: str, status: DIDStatus, by_did: str
    ) -> None:
        """Write a status transition to both registry and per-DID record."""
        now = int(time.time() * 1000)
        self._registry.setdefault(namespace, {})[did] = status
        self._save_registry()

        record = self._load_record(did) or DIDRecord(did=did, created_at=now)
        record.namespaces[namespace] = NamespaceApproval(
            status=status, approved_by=by_did, approved_at=now
        )
        self._save_record(record)

    def approve(
        self,
        did: str,
        namespace: str,
        by_did: str,
        role: DIDStatus = DIDStatus.APPROVED,
    ) -> tuple[bool, str]:
        """Approve a DID for a namespace at a given role.

        Authority:
        - Admin may set any role, any namespace (including '*').
        - Approver may set role=APPROVED on their specific namespace only.
        """
        if role not in (DIDStatus.APPROVED, DIDStatus.APPROVER):
            return False, f"invalid role: {role}"
        if self.is_admin(did):
            return False, "cannot modify admin DID"

        by_is_admin = self.is_admin(by_did)
        if not by_is_admin:
            if role == DIDStatus.APPROVER:
                return False, "only admin can grant approver role"
            if namespace == GLOBAL_NS:
                return False, "only admin can approve across all namespaces"
            if not self.is_approver(by_did, namespace):
                return False, f"not authorized to approve for namespace '{namespace}'"

        self.set_status(did, namespace, role, by_did)
        scope = "all namespaces" if namespace == GLOBAL_NS else namespace
        label = "approver on" if role == DIDStatus.APPROVER else "approved for"
        return True, f"{label} {scope}"

    def revoke(self, did: str, namespace: str, by_did: str) -> tuple[bool, str]:
        """Revoke a DID's access to a namespace (or all if namespace == '*').

        Admin can revoke anyone. Approver can revoke only APPROVED members of
        their specific namespace (never another approver or admin).
        """
        if self.is_admin(did):
            return False, "cannot revoke admin DID"

        by_is_admin = self.is_admin(by_did)
        if not by_is_admin:
            if namespace == GLOBAL_NS:
                return False, "only admin can revoke across all namespaces"
            if not self.is_approver(by_did, namespace):
                return False, f"not authorized to revoke for namespace '{namespace}'"
            target_status = self._registry.get(namespace, {}).get(did)
            if target_status != DIDStatus.APPROVED:
                return False, "approvers can only revoke APPROVED members"

        self._registry.get(namespace, {}).pop(did, None)
        if not self._registry.get(namespace):
            self._registry.pop(namespace, None)
        self._save_registry()

        record = self._load_record(did)
        if record:
            record.namespaces.pop(namespace, None)
            self._save_record(record)
        return True, f"revoked from {'all namespaces' if namespace == GLOBAL_NS else namespace}"

    def list_all(self, namespace: str | None = None) -> list[DIDRecord]:
        """List all DID records, optionally filtered to a namespace."""
        seen: set[str] = set()
        if namespace:
            dids = set(self._registry.get(namespace, {}).keys()) | \
                   set(self._registry.get(GLOBAL_NS, {}).keys())
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
class Invite:
    """An invite record.

    The raw token is never stored — only its SHA256 hash. The full token
    value is returned once, at creation time.
    """

    token_hash: str
    namespace: str
    role: DIDStatus  # APPROVED or APPROVER
    issued_by: str
    created_at: int
    expires_at: int | None
    max_uses: int
    uses: int
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
                    "namespace": invite.namespace,
                    "role": invite.role.value,
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
                namespace=d["namespace"],
                role=DIDStatus(d["role"]),
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
        namespace: str,
        role: DIDStatus,
        issued_by: str,
        expires_at: int | None,
        max_uses: int = 1,
    ) -> tuple[str, Invite]:
        """Create an invite and return (token, record). Token is only returned here."""
        import secrets
        token = "hinv_" + secrets.token_urlsafe(24)
        now = int(time.time() * 1000)
        invite = Invite(
            token_hash=self._hash(token),
            namespace=namespace,
            role=role,
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
            p for p in self.invites_dir.glob("*.json")
            if p.stem.startswith(token_hash_prefix)
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
        └── index.json  # {"instance/task_id": updated_at_ms}
    """

    storage_path: Path
    _index: dict[str, int] = field(default_factory=dict)  # "instance/task_id" -> updated_at
    did_registry: DIDRegistry = field(init=False)
    invites: InviteStore = field(init=False)
    shadow_writer: "RevisionShadowWriter | None" = field(default=None)

    def __post_init__(self) -> None:
        self.tasks_dir = self.storage_path / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_path / "index.json"
        self._migrate_did_partitioned_tasks()
        self._load_index()
        self.did_registry = DIDRegistry(self.storage_path)
        self.invites = InviteStore(self.storage_path)

    def _migrate_did_partitioned_tasks(self) -> None:
        """Flatten legacy tasks/{did_hash}/{instance}/ into tasks/{instance}/."""
        # Detect old layout: subdirs whose names look like 16-char hex hashes
        import re
        did_hash_re = re.compile(r'^[0-9a-f]{16}$')
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
            except (json.JSONDecodeError, OSError):
                self._index = {}
                self._rebuild_index()
        else:
            self._rebuild_index()

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
                    return False, f"conflict: server has newer version ({stored_ts} >= {incoming_ts})"

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
        self._index[key] = now
        self._save_index()

        # Phase 4a shadow write (fail-soft; JSON above is authoritative)
        if self.shadow_writer is not None:
            self.shadow_writer.record_write(task_payload, from_did, stored.received_at)

        return True, "accepted"

    def list_since(self, since_ms: int, instance: str) -> list[SyncTask]:
        """List tasks for an instance updated since a timestamp."""
        prefix = instance + "/"
        tasks = []
        for key, updated_at in self._index.items():
            if not key.startswith(prefix):
                continue
            if updated_at <= since_ms:
                continue
            _, task_id = key.split("/", 1)
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
            return True
        return False

    def get_updated_at(self, instance: str, task_id: str) -> int | None:
        """Get the updated_at timestamp for a task."""
        return self._index.get(self._index_key(instance, task_id))
