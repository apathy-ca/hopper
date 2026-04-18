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
from typing import Any

from .protocol import SyncTask


class DIDStatus(str, Enum):
    """Status of a DID for a given namespace."""

    ADMIN = "admin"      # Server admin — implicitly approved for all namespaces
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
            json.dump(
                {
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
                },
                f,
                indent=2,
            )

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
                return DIDRecord(did=data["did"], created_at=data["created_at"], namespaces=ns_map)
            namespaces = {
                ns: NamespaceApproval(
                    status=DIDStatus(a["status"]),
                    approved_by=a.get("approved_by"),
                    approved_at=a.get("approved_at"),
                )
                for ns, a in data.get("namespaces", {}).items()
            }
            return DIDRecord(did=data["did"], created_at=data["created_at"], namespaces=namespaces)
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
        # Global approval
        if did in self._registry.get(GLOBAL_NS, {}):
            return self._registry[GLOBAL_NS][did] == DIDStatus.APPROVED
        # Namespace-specific approval
        return self._registry.get(namespace, {}).get(did) == DIDStatus.APPROVED

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

    def approve(self, did: str, namespace: str, by_did: str) -> tuple[bool, str]:
        """Approve a DID for a namespace (or all namespaces if namespace == '*').

        Only admin can approve.
        """
        if not self.is_admin(by_did):
            return False, "only admin can approve DIDs"
        if self.is_admin(did):
            return False, "cannot modify admin DID"

        now = int(time.time() * 1000)
        self._registry.setdefault(namespace, {})[did] = DIDStatus.APPROVED
        self._save_registry()

        record = self._load_record(did) or DIDRecord(did=did, created_at=now)
        record.namespaces[namespace] = NamespaceApproval(
            status=DIDStatus.APPROVED, approved_by=by_did, approved_at=now
        )
        self._save_record(record)
        return True, f"approved for {'all namespaces' if namespace == GLOBAL_NS else namespace}"

    def revoke(self, did: str, namespace: str, by_did: str) -> tuple[bool, str]:
        """Revoke a DID's access to a namespace (or all if namespace == '*')."""
        if not self.is_admin(by_did):
            return False, "only admin can revoke DIDs"
        if self.is_admin(did):
            return False, "cannot revoke admin DID"

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

    def __post_init__(self) -> None:
        self.tasks_dir = self.storage_path / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_path / "index.json"
        self._migrate_did_partitioned_tasks()
        self._load_index()
        self.did_registry = DIDRegistry(self.storage_path)

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
        self._index = {}
        for task_file in self.tasks_dir.glob("*/*.json"):
            try:
                with open(task_file) as f:
                    data = json.load(f)
                instance = data.get("task", {}).get("instance", "local")
                task_id = data.get("task", {}).get("id")
                updated_at = data.get("task", {}).get("updated_at")
                if task_id and updated_at:
                    if isinstance(updated_at, str):
                        from datetime import datetime
                        dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                        updated_at = int(dt.timestamp() * 1000)
                    self._index[self._index_key(instance, task_id)] = updated_at
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
                    from_did=data["from_did"],
                )
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    def put(self, task: SyncTask, from_did: str) -> tuple[bool, str]:
        """Store a task, returns (accepted, reason).

        Uses last-write-wins. Any approved DID can write to any instance.
        """
        task_id = task.id
        instance = task.instance or "local"
        now = int(time.time() * 1000)
        key = self._index_key(instance, task_id)

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
            stored_ts = self._index[key]
            if incoming_ts <= stored_ts:
                return False, f"conflict: server has newer version ({stored_ts} >= {incoming_ts})"

        stored = StoredTask(task=task, received_at=now, from_did=from_did)
        path = self._task_path(instance, task_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(
                {
                    "task": task.model_dump(mode="json"),
                    "received_at": stored.received_at,
                    "from_did": stored.from_did,
                },
                f,
                indent=2,
                default=str,
            )

        self._index[key] = incoming_ts
        self._save_index()
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
