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
    """Status of a DID in the registry."""

    ADMIN = "admin"  # First DID, can approve others
    APPROVED = "approved"  # Approved by admin
    PENDING = "pending"  # Awaiting approval


@dataclass
class DIDRecord:
    """A DID record in the registry."""

    did: str
    status: DIDStatus
    created_at: int  # ms since epoch
    approved_by: str | None = None  # DID that approved this one
    approved_at: int | None = None  # When approved


@dataclass
class DIDRegistry:
    """Registry of DIDs and their approval status.

    Directory structure:
        storage_path/
        └── dids/
            ├── registry.json  # {did: status, admin_did, ...}
            └── {did_hash}.json  # Full record for each DID
    """

    storage_path: Path
    _admin_did: str | None = None
    _registry: dict[str, DIDStatus] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize registry directory."""
        self.dids_dir = self.storage_path / "dids"
        self.dids_dir.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.dids_dir / "registry.json"
        self._load_registry()

    def _load_registry(self) -> None:
        """Load the registry from disk."""
        if self.registry_path.exists():
            try:
                with open(self.registry_path) as f:
                    data = json.load(f)
                    self._admin_did = data.get("admin_did")
                    self._registry = {
                        did: DIDStatus(status)
                        for did, status in data.get("dids", {}).items()
                    }
            except (json.JSONDecodeError, OSError):
                self._admin_did = None
                self._registry = {}

    def _save_registry(self) -> None:
        """Save the registry to disk."""
        with open(self.registry_path, "w") as f:
            json.dump(
                {
                    "admin_did": self._admin_did,
                    "dids": {did: status.value for did, status in self._registry.items()},
                },
                f,
                indent=2,
            )

    def _did_path(self, did: str) -> Path:
        """Get path for a DID record file."""
        did_hash = hashlib.sha256(did.encode()).hexdigest()[:16]
        return self.dids_dir / f"{did_hash}.json"

    def _save_record(self, record: DIDRecord) -> None:
        """Save a DID record to disk."""
        path = self._did_path(record.did)
        with open(path, "w") as f:
            json.dump(
                {
                    "did": record.did,
                    "status": record.status.value,
                    "created_at": record.created_at,
                    "approved_by": record.approved_by,
                    "approved_at": record.approved_at,
                },
                f,
                indent=2,
            )

    def _load_record(self, did: str) -> DIDRecord | None:
        """Load a DID record from disk."""
        path = self._did_path(did)
        if not path.exists():
            return None
        try:
            with open(path) as f:
                data = json.load(f)
                return DIDRecord(
                    did=data["did"],
                    status=DIDStatus(data["status"]),
                    created_at=data["created_at"],
                    approved_by=data.get("approved_by"),
                    approved_at=data.get("approved_at"),
                )
        except (json.JSONDecodeError, OSError, KeyError):
            return None

    @property
    def admin_did(self) -> str | None:
        """Get the admin DID."""
        return self._admin_did

    def is_admin(self, did: str) -> bool:
        """Check if a DID is the admin."""
        return self._admin_did == did

    def get_status(self, did: str) -> DIDStatus | None:
        """Get the status of a DID."""
        return self._registry.get(did)

    def is_authorized(self, did: str) -> bool:
        """Check if a DID is authorized to sync."""
        status = self._registry.get(did)
        return status in (DIDStatus.ADMIN, DIDStatus.APPROVED)

    def register_or_get(self, did: str) -> tuple[DIDStatus, bool]:
        """Register a new DID or get existing status.

        Returns (status, is_new).
        First DID becomes admin automatically.
        """
        if did in self._registry:
            return self._registry[did], False

        now = int(time.time() * 1000)

        # First DID becomes admin
        if self._admin_did is None:
            self._admin_did = did
            status = DIDStatus.ADMIN
            record = DIDRecord(did=did, status=status, created_at=now)
        else:
            status = DIDStatus.PENDING
            record = DIDRecord(did=did, status=status, created_at=now)

        self._registry[did] = status
        self._save_record(record)
        self._save_registry()

        return status, True

    def approve(self, did: str, by_did: str) -> tuple[bool, str]:
        """Approve a DID. Only admin can approve.

        Returns (success, message).
        """
        if not self.is_admin(by_did):
            return False, "only admin can approve DIDs"

        if did not in self._registry:
            return False, "DID not found"

        current = self._registry[did]
        if current == DIDStatus.ADMIN:
            return False, "cannot modify admin DID"
        if current == DIDStatus.APPROVED:
            return False, "DID already approved"

        now = int(time.time() * 1000)
        self._registry[did] = DIDStatus.APPROVED

        record = self._load_record(did)
        if record:
            record.status = DIDStatus.APPROVED
            record.approved_by = by_did
            record.approved_at = now
            self._save_record(record)

        self._save_registry()
        return True, "approved"

    def revoke(self, did: str, by_did: str) -> tuple[bool, str]:
        """Revoke a DID's access. Only admin can revoke.

        Returns (success, message).
        """
        if not self.is_admin(by_did):
            return False, "only admin can revoke DIDs"

        if did not in self._registry:
            return False, "DID not found"

        current = self._registry[did]
        if current == DIDStatus.ADMIN:
            return False, "cannot revoke admin DID"

        self._registry[did] = DIDStatus.PENDING

        record = self._load_record(did)
        if record:
            record.status = DIDStatus.PENDING
            record.approved_by = None
            record.approved_at = None
            self._save_record(record)

        self._save_registry()
        return True, "revoked"

    def list_all(self) -> list[DIDRecord]:
        """List all DID records."""
        records = []
        for did in self._registry:
            record = self._load_record(did)
            if record:
                records.append(record)
        return records

    def list_pending(self) -> list[DIDRecord]:
        """List pending DID records."""
        return [r for r in self.list_all() if r.status == DIDStatus.PENDING]

    def list_approved(self) -> list[DIDRecord]:
        """List approved DID records (including admin)."""
        return [
            r for r in self.list_all() if r.status in (DIDStatus.ADMIN, DIDStatus.APPROVED)
        ]


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
