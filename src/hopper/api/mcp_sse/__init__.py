"""MCP SSE server for Hopper.

Provides an MCP (Model Context Protocol) server using SSE (Server-Sent Events)
transport, enabling Claude Web and other MCP clients to interact with Hopper
for task management, pattern matching, and feedback collection.

Authentication methods (in order of preference):

1. **Registered Token** (recommended for Claude Web):
   Run `hopper mcp init-token --server <url>` to get a token linked to your DID.
   Tokens start with `hpr_` and map to your DID identity and a specific instance.

   Claude Web config:
       mcp_servers: [{
           "type": "url",
           "url": "https://your-server.com/mcp/sse/",
           "name": "hopper",
           "authorization_token": "hpr_abc123..."
       }]

   Multiple instances: Register separate tokens for each instance:
       hopper mcp init-token -s <url> -i work -p /path/to/work/.hopper
       hopper mcp init-token -s <url> -i personal

2. **DID Auth** (direct cryptographic auth):
   Header: `Authorization: DID <did:key:z...> <base64-signature>`
   Set HOPPER_MCP_ALLOWED_DIDS to restrict which DIDs can connect.

3. **Simple Token** (legacy/development):
   Set HOPPER_MCP_TOKEN env var for a shared secret.

If no auth is configured, the server allows unauthenticated access.
"""

import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hopper.upstream.protocol import SyncTask
    from hopper.upstream.storage import UpstreamStorage

from mcp.server.fastmcp import FastMCP

from hopper.api.mcp_sse.auth import _check_auth
from hopper.api.mcp_sse.transport import (
    create_sse_server,
    create_streamable_http_server,
    get_stateless_session_manager,
    get_streamable_session_manager,
)
from hopper.cli.local_client import LocalClient, LocalClientError
from hopper.timeutils import utc_now_naive

logger = logging.getLogger(__name__)

# Authentication configuration
MCP_AUTH_TOKEN = os.getenv("HOPPER_MCP_TOKEN")
MCP_ALLOWED_DIDS = (
    os.getenv("HOPPER_MCP_ALLOWED_DIDS", "").split(",")
    if os.getenv("HOPPER_MCP_ALLOWED_DIDS")
    else []
)
MCP_DID_OPEN_ACCESS = os.getenv("HOPPER_MCP_DID_OPEN", "").lower() in ("1", "true", "yes")

# Session ID ContextVar — set once at SSE connect, inherited by all tool calls
_session_id: ContextVar[str | None] = ContextVar("session_id", default=None)

# Session-level instance store — (instance_path, instance_name) per session ID
_session_instances: dict[str, tuple[Path | None, str | None]] = {}

# DID for the current session — used by switch to validate token ownership
_session_did: ContextVar[str | None] = ContextVar("session_did", default=None)


def _upstream_storage_path() -> Path:
    env = os.getenv("HOPPER_UPSTREAM_STORAGE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".hopper" / "upstream-data"


class UpstreamNamespaceClient:
    """MCP-facing client that delegates to UpstreamStorage.

    Provides the dict-based interface that MCP tool functions expect while
    routing all reads and writes through the canonical UpstreamStorage,
    keeping the sync index consistent.
    """

    def __init__(self, namespace: str, storage: "UpstreamStorage"):
        self._ns = namespace
        self._storage = storage

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def _did(self) -> str:
        """Return the DID for the current MCP session, or a sentinel."""
        return _session_did.get() or "mcp:anonymous"

    @staticmethod
    def _sync_task_to_dict(st: "SyncTask") -> dict:
        return st.model_dump(mode="json")

    def _dict_to_sync_task(self, d: dict) -> "SyncTask":
        from hopper.upstream.protocol import SyncTask

        return SyncTask(**d)

    def _all_tasks(self, include_deleted: bool = False) -> list[dict]:
        sync_tasks = self._storage.list_all(self._ns)
        tasks = [self._sync_task_to_dict(st) for st in sync_tasks]
        if not include_deleted:
            tasks = [t for t in tasks if not t.get("deleted")]
        return tasks

    def _get_one(self, task_id: str) -> dict | None:
        stored = self._storage.get(self._ns, task_id)
        if stored:
            return self._sync_task_to_dict(stored.task)
        # Prefix match — walk the index for this namespace
        prefix = f"{self._ns}/{task_id}"
        matches = [k for k in self._storage._index if k.startswith(prefix)]
        if len(matches) == 1:
            _, full_id = matches[0].split("/", 1)
            stored = self._storage.get(self._ns, full_id)
            if stored:
                return self._sync_task_to_dict(stored.task)
        return None

    def _put(self, task_dict: dict) -> None:
        st = self._dict_to_sync_task(task_dict)
        self._storage.put(st, from_did=self._did())

    def list_tasks(
        self, status=None, priority=None, tags=None, kind=None, limit=50, **_
    ) -> list[dict]:
        tasks = self._all_tasks()
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if priority:
            tasks = [t for t in tasks if t.get("priority") == priority]
        if kind:
            # Kind is first-class: SyncTask carries a real `kind` field that
            # round-trips through UpstreamStorage. Records with no kind (older
            # data) are treated as "task". For non-task kinds, also accept the
            # legacy kind-tag so memories/ideas created before the kind field
            # existed (and not yet migrated) remain findable.
            tasks = [
                t
                for t in tasks
                if (t.get("kind") or "task") == kind
                or (kind != "task" and kind in (t.get("tags") or []))
            ]
        if tags:
            tag_set = set(tags.split(",")) if isinstance(tags, str) else set(tags)
            tasks = [t for t in tasks if tag_set & set(t.get("tags") or [])]
        tasks.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
        return tasks[:limit]

    def get_task(self, task_id: str) -> dict:
        t = self._get_one(task_id)
        if not t:
            raise Exception(f"Task not found: {task_id}")
        return t

    def create_task(self, data: dict) -> dict:
        import uuid as _uuid

        task_id = "t" + _uuid.uuid4().hex[:8]
        now = utc_now_naive().isoformat() + "Z"
        kind = data.get("kind", "task")
        task = {
            "id": task_id,
            "title": data.get("title", ""),
            "status": data.get("status", "open"),
            "priority": data.get("priority", "medium"),
            "description": data.get("description"),
            "tags": data.get("tags", []),
            "kind": kind,
            "subject": data.get("subject"),
            "scope": data.get("scope"),
            "provenance": data.get("provenance"),
            "instance": self._ns,
            "source": data.get("source", "mcp"),
            "created_at": now,
            "updated_at": now,
            "assigned_to": None,
            "parent_id": None,
            "deleted": False,
        }
        # kind/subject/scope/provenance are real fields on SyncTask, so they
        # persist through UpstreamStorage and round-trip on read — no kind-tag
        # injection (the legacy tag approach this work removes).
        self._put(task)
        return task

    def update_task(self, task_id: str, data: dict) -> dict:
        task = self.get_task(task_id)
        if "add_tags" in data:
            task["tags"] = list(set(task.get("tags") or []) | set(data.pop("add_tags")))
        if "remove_tags" in data:
            task["tags"] = [t for t in (task.get("tags") or []) if t not in data.pop("remove_tags")]
        for k, v in data.items():
            if k not in ("add_tags", "remove_tags"):
                task[k] = v
        task["updated_at"] = utc_now_naive().isoformat() + "Z"
        self._put(task)
        return task

    def delete_task(self, task_id: str) -> None:
        self.update_task(task_id, {"deleted": True})

    def search_tasks(self, query: str, status=None, limit=20, **_) -> list[dict]:
        q = query.lower()
        tasks = [
            t
            for t in self._all_tasks()
            if q in (t.get("title") or "").lower() or q in (t.get("description") or "").lower()
        ]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks[:limit]

    def heartbeat_task(self, task_id: str, expect_minutes=None) -> dict:
        import datetime as _dt

        data = {"last_heartbeat": utc_now_naive().isoformat() + "Z"}
        if expect_minutes:
            exp = utc_now_naive() + _dt.timedelta(minutes=expect_minutes)
            data["expected_heartbeat"] = exp.isoformat() + "Z"
        return self.update_task(task_id, data)

    def list_stale_tasks(self, minutes: int = 30) -> list[dict]:
        import datetime as _dt

        threshold = utc_now_naive() - _dt.timedelta(minutes=minutes)
        stale = []
        for t in self._all_tasks():
            if not t.get("assigned_to"):
                continue
            hb = t.get("last_heartbeat")
            if hb and _dt.datetime.fromisoformat(hb.rstrip("Z")) < threshold:
                stale.append(t)
        return stale

    def get_task_children(self, task_id: str) -> list[dict]:
        return [t for t in self._all_tasks() if t.get("parent_id") == task_id]

    def get_task_with_rollup(self, task_id: str) -> dict:
        task = self.get_task(task_id)
        children = self.get_task_children(task_id)
        done = sum(1 for c in children if c.get("status") in ("completed", "cancelled"))
        task["children"] = {"total": len(children), "done": done}
        return task

    def list_projects(self) -> list:
        return []

    def list_instances(self) -> list:
        return [{"id": self._ns, "name": self._ns}]

    def match_patterns(self, **_) -> list:
        return []

    def submit_feedback(self, task_id, data):
        return {"status": "ok"}

    def get_learning_statistics(self) -> dict:
        return {}

    def list_patterns(self, active_only=True) -> dict:
        return {"patterns": [], "total": 0}

    def create_pattern(self, data) -> dict:
        return data


def _did_has_upstream_association(did: str | None) -> bool:
    """Return True if this DID is known to be scoped to an upstream instance.

    A DID is considered "multi-instance / upstream-associated" when either:
      * the durable DID registry records a last_instance for it, or
      * it has at least one registered hpr_ token carrying an instance name.

    For such DIDs we must NEVER silently serve the server's own LocalClient
    ("local" instance) — doing so returns the WRONG instance's data. Plain
    local/anonymous sessions (no DID, no association) are unaffected and keep
    falling back to LocalClient.
    """
    if not did:
        return False
    # 1. Durable registry affinity.
    try:
        from hopper.upstream.server import get_storage

        if get_storage().did_registry.get_last_instance(did):
            return True
    except Exception:
        pass
    # 2. Registered hpr_ tokens that carry an instance scope.
    try:
        from hopper.api.mcp_tokens import get_token_store

        tokens = get_token_store().list_tokens(did=did)
        if any(t.get("instance") for t in tokens):
            return True
    except Exception:
        pass
    return False


def _resolve_instance_name(sid: str | None, did: str | None) -> str | None:
    """Resolve the active instance name for a session.

    Fast path: the in-memory per-process session cache. On a miss (e.g. a
    request routed to a uvicorn worker that did not handle the SSE connect /
    switch_instance, or a stale-session reroute that never populated the cache)
    we fall back to the DURABLE source of truth: the DID registry's
    last_instance, which is shared across workers and restarts. A successful
    registry resolution repopulates the cache and is logged as a warning so
    silent scope-loss is observable in server logs.

    Returns None only when no instance can be determined.
    """
    if sid:
        _, instance_name = _session_instances.get(sid, (None, None))
        if instance_name:
            return instance_name

    # Cache miss — recover scope from the durable DID->instance affinity.
    if did:
        try:
            from hopper.upstream.server import get_storage

            recovered = get_storage().did_registry.get_last_instance(did)
        except Exception:
            recovered = None
        if recovered:
            logger.warning(
                "MCP session %s for DID %s missed the in-memory instance cache; "
                "recovered instance '%s' from DID registry (cross-worker/reconnect). "
                "Repopulating session cache.",
                sid,
                did,
                recovered,
            )
            if sid:
                _session_instances[sid] = (None, recovered)
            return recovered

    return None


def _get_client():
    """Get the appropriate client for the current session's instance.

    Instance resolution is server-side only:
    1. Named instance (session cache, or recovered from the DID registry on a
       cache miss) → UpstreamNamespaceClient backed by UpstreamStorage.
    2. Genuinely local/anonymous session (no DID, no upstream association)
       → server's default LocalClient (~/.hopper).

    TRUST RULE: if the session has an authenticated DID that is associated with
    an upstream instance but we still cannot resolve a concrete instance, we do
    NOT silently fall back to LocalClient (which would return the WRONG, "local"
    instance's data). Instead we raise LocalClientError, which every tool
    already translates into a clear, recoverable error telling the caller to
    run hopper_switch_instance.

    instance_path from client tokens is intentionally ignored — the server
    never accesses arbitrary filesystem paths supplied by clients.
    """
    sid = _session_id.get()
    did = _session_did.get()

    instance_name = _resolve_instance_name(sid, did)
    if instance_name:
        from hopper.upstream.server import get_storage

        try:
            storage = get_storage()
        except Exception:
            storage = None
        if storage is not None:
            return UpstreamNamespaceClient(instance_name, storage)

    # No instance resolved. Refuse to serve the wrong scope for DIDs that are
    # known to be upstream/multi-instance scoped.
    if _did_has_upstream_association(did):
        logger.warning(
            "MCP session %s for DID %s has an upstream instance association but "
            "no instance could be resolved; refusing silent fallback to local data.",
            sid,
            did,
        )
        raise LocalClientError(
            "No Hopper instance is selected for this session. Your identity is "
            "scoped to an upstream instance, so serving the server's local data "
            'would return the wrong records. Call hopper_switch_instance("<name>") '
            "to select your instance (e.g. the one you last used), then retry."
        )

    # Genuinely local / anonymous: LocalClient remains the correct default.
    return LocalClient()


# Initialize FastMCP server
mcp = FastMCP("hopper")


# =============================================================================
# Task Tools
# =============================================================================


_VALID_KINDS = ("inbox", "task", "idea", "note", "memory", "reference", "log")


@mcp.tool()
def hopper_create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    tags: list[str] | None = None,
    kind: str = "task",
    location: str | None = None,
) -> dict:
    """Create a new record in Hopper.

    Records have a 'kind' that shapes how they should be treated:
      - task: work with a status lifecycle (what most agents create)
      - idea: seed or concept, no lifecycle
      - note: durable context, append-only
      - memory: agent knowledge (prefer hopper_create_memory for richer fields)
      - reference: pointer to an external resource
      - log: immutable event record
      - inbox: untriaged capture (triage agent moves to a terminal kind)

    Call hopper_instructions() for the full type guide.

    Args:
        title: Concise summary (required)
        description: Detailed body or notes
        priority: low | medium | high | urgent (default medium)
        tags: Free-form tags for search and filtering
        kind: Record kind, one of inbox, task, idea, note, memory, reference, log
        location: Author location — your execution context. Examples:
            "phone-claude", "web-chat", "waypoint-skill", "rosetta-agent".
            Omit to accept the default ("mcp"). Pass something specific
            when you know where you are so the write is attributed
            richly in revision history.
    """
    if kind not in _VALID_KINDS:
        return {
            "status": "error",
            "message": f"Invalid kind '{kind}'. Use one of: {', '.join(_VALID_KINDS)}",
        }
    try:
        from hopper.location import resolve_location

        with _get_client() as client:
            result = client.create_task(
                {
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "tags": list(tags or []),
                    "kind": kind,
                    "source": resolve_location(override=location, transport="mcp"),
                }
            )
            return {"status": "created", "task": result}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_create_memory(
    title: str,
    content: str,
    subject: str,
    scope: str = "shared-with-user",
    provenance: str | None = None,
    priority: str = "medium",
    tags: list[str] | None = None,
    location: str | None = None,
) -> dict:
    """Create a memory record — first-class agent knowledge.

    Memory is first-class across agents in Hopper: Claude, Rosetta,
    audit-agent, and future agents all share this store. Every memory
    is attributed by author DID so "what does each agent know" is a
    real, queryable question. Unlike Claude's vendor-specific auto-memory,
    this is cross-agent and revisioned.

    Args:
        title: Short memory title (e.g. "User prefers terse responses")
        content: Full memory body, prose or structured
        subject: What the memory is about. Use one of the conventions:
            "user:preferences", "user:<topic>",
            "project:<project>", "agent:<agent-name>", "self"
        scope: Who can read this memory:
            "private" — only the author agent should use it
            "shared-with-user" — surface to the human in conversations
            "shared-across-agents" — any agent can rely on it
        provenance: How the memory was learned. Free-form, but prefer:
            "conversation YYYY-MM-DD", "observation", "inference from <id>"
        priority: low | medium | high | urgent (default medium)
        tags: Additional tags (free-form; kind="memory" is set automatically)
        location: Author location — see hopper_create_task for guidance.
    """
    try:
        from hopper.location import resolve_location

        with _get_client() as client:
            result = client.create_task(
                {
                    "title": title,
                    "description": content,
                    "priority": priority,
                    "tags": list(tags or []),
                    "kind": "memory",
                    "subject": subject,
                    "scope": scope,
                    "provenance": provenance,
                    "source": resolve_location(override=location, transport="mcp"),
                }
            )
            return {"status": "created", "memory": result}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_list_memory(
    subject: str | None = None,
    scope: str | None = None,
    tags: str | None = None,
    limit: int = 50,
) -> dict:
    """List memory records — first-class agent knowledge.

    This is the kind-based retrieval path for memory (it filters kind="memory",
    NOT the legacy tags=["memory"] approach). Use it at the start of a session
    to recall what you and other agents have learned.

    Args:
        subject: Optional filter on the memory subject (e.g. "user:preferences",
                 "project:<slug>"). Matched against the structured subject field.
        scope: Optional filter on scope (private, shared-with-user, shared-across-agents)
        tags: Comma-separated tags to additionally filter by
        limit: Maximum number of memories to return (default 50)
    """
    try:
        with _get_client() as client:
            params = {"limit": limit, "kind": "memory"}
            if tags:
                params["tags"] = tags
            memories = client.list_tasks(**params)
            if subject:
                memories = [m for m in memories if m.get("subject") == subject]
            if scope:
                memories = [m for m in memories if m.get("scope") == scope]
            return {
                "status": "success",
                "memories": memories,
                "count": len(memories),
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_list_tasks(
    status: str | None = None,
    priority: str | None = None,
    tags: str | None = None,
    kind: str | None = None,
    all_kinds: bool = False,
    limit: int = 50,
) -> dict:
    """List records from Hopper, defaulting to kind="task".

    By default this shows only kind="task" — memories, jobs, ideas, notes and
    other non-task kinds are excluded so the task list stays focused. Pass
    kind="memory" (or any kind) to view a specific kind, or all_kinds=true to
    see everything. To browse agent knowledge, prefer hopper_list_memory.

    Returns tasks sorted by status (in_progress first, then pending, completed
    last) and then by priority within each status group.

    Args:
        status: Filter by status - one of: open, pending, in_progress, blocked, completed, cancelled
        priority: Filter by priority - one of: low, medium, high, urgent
        tags: Comma-separated list of tags to filter by
        kind: Filter by record kind (task, memory, job, idea, note, reference, inbox, log).
              Defaults to "task" when omitted.
        all_kinds: If true, return every kind (disables the default kind="task" filter)
        limit: Maximum number of tasks to return (default 50)
    """
    try:
        with _get_client() as client:
            params = {"limit": limit}
            if status:
                params["status"] = status
            if priority:
                params["priority"] = priority
            if tags:
                params["tags"] = tags
            # Default segmentation: task-oriented views show only kind=task.
            # An explicit kind selects a different kind; all_kinds disables the
            # filter entirely so nothing is hidden.
            if kind:
                params["kind"] = kind
            elif not all_kinds:
                params["kind"] = "task"

            tasks = client.list_tasks(**params)
            return {
                "status": "success",
                "tasks": tasks,
                "count": len(tasks),
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_get_task(task_id: str) -> dict:
    """Get details of a specific task by ID.

    Supports ID prefix matching - you can provide a truncated ID as long as
    it uniquely identifies the task.

    Args:
        task_id: Full or partial task ID to retrieve
    """
    try:
        with _get_client() as client:
            task = client.get_task(task_id)
            return {"status": "success", "task": task}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_update_task(
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    status: str | None = None,
    tags: list[str] | None = None,
    add_tags: list[str] | None = None,
    remove_tags: list[str] | None = None,
    assigned_to: str | None = None,
    parent_id: str | None = None,
) -> dict:
    """Update an existing task.

    Only the fields you provide will be updated. Use this for comprehensive
    updates to task metadata.

    Args:
        task_id: Task ID to update (supports prefix matching)
        title: New title for the task
        description: New description for the task
        priority: New priority - one of: low, medium, high, urgent
        status: New status - one of: open, pending, in_progress, blocked, completed, cancelled
        tags: Replace all tags with this list
        add_tags: Add these tags to existing tags
        remove_tags: Remove these tags from existing tags
        assigned_to: Agent identifier (platform:task-name format, e.g., "claude:my-task")
        parent_id: Parent task ID for hierarchical organization
    """
    try:
        with _get_client() as client:
            data = {}
            if title is not None:
                data["title"] = title
            if description is not None:
                data["description"] = description
            if priority is not None:
                data["priority"] = priority
            if status is not None:
                data["status"] = status
            if tags is not None:
                data["tags"] = tags
            if add_tags is not None:
                data["add_tags"] = add_tags
            if remove_tags is not None:
                data["remove_tags"] = remove_tags
            if assigned_to is not None:
                data["assigned_to"] = assigned_to
            if parent_id is not None:
                data["parent_id"] = parent_id

            task = client.update_task(task_id, data)
            return {"status": "updated", "task": task}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_update_task_status(task_id: str, status: str) -> dict:
    """Change a task's status.

    Convenience method for quickly transitioning task status without
    updating other fields.

    Args:
        task_id: Task ID to update (supports prefix matching)
        status: New status - one of: open, pending, in_progress, blocked, completed, cancelled
    """
    try:
        with _get_client() as client:
            task = client.update_task(task_id, {"status": status})
            return {"status": "updated", "task": task}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_delete_task(task_id: str) -> dict:
    """Delete a task permanently.

    This action cannot be undone. Use hopper_update_task_status with
    status="cancelled" if you want to keep a record of the task.

    Args:
        task_id: Task ID to delete (supports prefix matching)
    """
    try:
        with _get_client() as client:
            client.delete_task(task_id)
            return {"status": "deleted", "task_id": task_id}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_heartbeat(task_id: str, expect_minutes: int | None = None) -> dict:
    """Send a heartbeat to signal you're still working on a task.

    Call this periodically (every 10-15 minutes) when working on a task to
    prevent it from being marked as stale. Use expect_minutes for long-running
    operations like GPU jobs or data generation.

    Args:
        task_id: Task ID to heartbeat (supports prefix matching)
        expect_minutes: Expected time until next heartbeat. Use for long operations
                       (e.g., 240 for a 4-hour GPU job) to avoid stale detection.
    """
    try:
        with _get_client() as client:
            task = client.heartbeat_task(task_id, expect_minutes)
            return {"status": "heartbeat_sent", "task": task}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_list_stale_tasks(minutes: int = 30) -> dict:
    """Find tasks that may have been abandoned.

    A task is considered stale when:
    - It has an assigned agent, AND
    - If expected_heartbeat is set: current time > expected_heartbeat
    - If no expected_heartbeat: last_heartbeat is older than the threshold

    Args:
        minutes: Minutes without heartbeat to consider stale (default 30).
                 Only used when no expected_heartbeat is set on the task.
    """
    try:
        with _get_client() as client:
            tasks = client.list_stale_tasks(minutes)
            return {
                "status": "success",
                "stale_tasks": tasks,
                "count": len(tasks),
                "threshold_minutes": minutes,
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_search_tasks(query: str, status: str | None = None, limit: int = 20) -> dict:
    """Search tasks by keyword.

    Searches task titles and descriptions for matching text.

    Args:
        query: Search query string
        status: Optional status filter
        limit: Maximum results to return (default 20)
    """
    try:
        with _get_client() as client:
            params = {"limit": limit}
            if status:
                params["status"] = status
            tasks = client.search_tasks(query, **params)
            return {
                "status": "success",
                "tasks": tasks,
                "count": len(tasks),
                "query": query,
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_get_task_children(task_id: str) -> dict:
    """Get child tasks of a parent task.

    Returns all subtasks associated with a parent task, along with
    status rollup information.

    Args:
        task_id: Parent task ID (supports prefix matching)
    """
    try:
        with _get_client() as client:
            children = client.get_task_children(task_id)
            # Also get rollup info
            parent = client.get_task_with_rollup(task_id)
            return {
                "status": "success",
                "parent_id": task_id,
                "children": children,
                "count": len(children),
                "rollup": parent.get("children"),
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Project/Instance Tools
# =============================================================================


@mcp.tool()
def hopper_list_projects() -> dict:
    """List available projects.

    In local mode, this returns an empty list as projects are a
    multi-instance feature.
    """
    try:
        with _get_client() as client:
            projects = client.list_projects()
            return {
                "status": "success",
                "projects": projects,
                "count": len(projects),
                "note": "Projects are limited in local mode",
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_list_instances() -> dict:
    """List Hopper instances.

    In local mode, this returns only the local instance.
    """
    try:
        with _get_client() as client:
            instances = client.list_instances()
            return {
                "status": "success",
                "instances": instances,
                "count": len(instances),
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_switch_instance(instance_name: str) -> dict:
    """Switch which Hopper instance this session reads from.

    Authentication is DID-based and doesn't change. This just redirects
    which hopper data store subsequent tool calls operate on. The server
    looks up a registered token for the authenticated DID that matches
    the requested instance name.

    Args:
        instance_name: Name of the instance to switch to (e.g. 'Rosetta_Program', 'hopper')
    """
    sid = _session_id.get()
    if not sid:
        return {"status": "error", "message": "No active session"}

    did = _session_did.get()

    # Check upstream-data first — no local mirror required
    ns_dir = _upstream_storage_path() / "tasks" / instance_name
    if ns_dir.exists():
        _session_instances[sid] = (None, instance_name)
        # Persist for next session
        if did:
            try:
                from hopper.upstream.server import get_storage

                get_storage().did_registry.update_last_instance(did, instance_name)
            except Exception:
                pass  # Best effort
        return {"status": "switched", "instance": instance_name, "source": "upstream"}

    # Fall back to a registered hpr_ token with a local path
    try:
        from hopper.api.mcp_tokens import get_token_store

        store = get_token_store()
        all_tokens = store.list_tokens(did=did) if did else []
        match = next(
            (
                t
                for t in all_tokens
                if t.get("instance") == instance_name and t.get("instance_path")
            ),
            None,
        )
    except Exception as e:
        return {"status": "error", "message": f"Token lookup failed: {e}"}

    if not match:
        return {
            "status": "error",
            "message": f"No upstream data or registered token found for instance '{instance_name}'.",
        }

    new_path = Path(match["instance_path"])
    if not new_path.exists():
        return {"status": "error", "message": f"Instance path does not exist on server: {new_path}"}

    _session_instances[sid] = (new_path, instance_name)
    # Persist for next session
    if did:
        try:
            from hopper.upstream.server import get_storage

            get_storage().did_registry.update_last_instance(did, instance_name)
        except Exception:
            pass  # Best effort
    return {"status": "switched", "instance": instance_name, "path": str(new_path)}


# =============================================================================
# Pattern/Learning Tools
# =============================================================================


@mcp.tool()
def hopper_match_patterns(
    tags: list[str] | None = None,
    text: str | None = None,
    priority: str | None = None,
) -> dict:
    """Find routing patterns that match given criteria.

    Patterns are used to automatically route tasks to appropriate
    instances or agents based on tags, text content, and priority.

    Args:
        tags: List of tags to match against pattern tag criteria
        text: Text content to match against pattern text criteria
        priority: Priority level to match against pattern priority criteria
    """
    try:
        with _get_client() as client:
            params = {}
            if tags:
                params["tags"] = tags
            if text:
                params["text"] = text
            if priority:
                params["priority"] = priority

            matches = client.match_patterns(**params)
            return {
                "status": "success",
                "matches": matches,
                "count": len(matches),
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_submit_feedback(
    task_id: str,
    was_good_match: bool,
    notes: str | None = None,
    quality_score: int | None = None,
    routing_feedback: str | None = None,
    should_have_routed_to: str | None = None,
) -> dict:
    """Submit feedback on a task's routing or execution.

    Use this to record whether a task was routed well, provide quality
    assessments, and suggest improvements. This feedback helps improve
    pattern matching over time.

    Args:
        task_id: Task ID to provide feedback for
        was_good_match: True if the task was routed/assigned appropriately
        notes: Free-form notes about the task execution
        quality_score: Quality rating from 1-5
        routing_feedback: Specific feedback about routing
        should_have_routed_to: Suggested alternative routing target
    """
    try:
        with _get_client() as client:
            data = {"was_good_match": was_good_match}
            if notes is not None:
                data["notes"] = notes
            if quality_score is not None:
                data["quality_score"] = quality_score
            if routing_feedback is not None:
                data["routing_feedback"] = routing_feedback
            if should_have_routed_to is not None:
                data["should_have_routed_to"] = should_have_routed_to

            feedback = client.submit_feedback(task_id, data)
            return {"status": "submitted", "feedback": feedback}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_get_learning_statistics() -> dict:
    """Get overall learning and routing statistics.

    Returns statistics about episodes, patterns, and feedback
    collected over time.
    """
    try:
        with _get_client() as client:
            stats = client.get_learning_statistics()
            return {"status": "success", "statistics": stats}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_list_patterns(active_only: bool = True) -> dict:
    """List routing patterns.

    Patterns define rules for automatically routing tasks based on
    tags, text content, and priority.

    Args:
        active_only: If True, only return active patterns (default True)
    """
    try:
        with _get_client() as client:
            result = client.list_patterns(active_only=active_only)
            return {
                "status": "success",
                "patterns": result["patterns"],
                "count": result["total"],
            }
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_create_pattern(
    name: str,
    description: str | None = None,
    match_tags: list[str] | None = None,
    match_keywords: list[str] | None = None,
    match_priority: str | None = None,
    target_instance: str = "local",
    confidence: float = 0.8,
) -> dict:
    """Create a new routing pattern.

    Patterns help automatically route tasks to appropriate instances
    or agents based on matching criteria.

    Args:
        name: Pattern name
        description: Description of when this pattern applies
        match_tags: Tags that trigger this pattern
        match_keywords: Keywords in text that trigger this pattern
        match_priority: Priority level that triggers this pattern
        target_instance: Instance to route matching tasks to
        confidence: Confidence threshold (0.0 to 1.0)
    """
    try:
        with _get_client() as client:
            data = {
                "name": name,
                "target_instance": target_instance,
                "confidence": confidence,
            }
            if description is not None:
                data["description"] = description
            if match_tags:
                data["match_tags"] = match_tags
            if match_keywords:
                data["match_keywords"] = match_keywords
            if match_priority:
                data["match_priority"] = match_priority

            pattern = client.create_pattern(data)
            return {"status": "created", "pattern": pattern}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# =============================================================================
# Usage / bootstrap tool
# =============================================================================


@mcp.tool()
def hopper_instructions() -> str:
    """Return usage instructions for Hopper. Call this first to understand how to use the available tools effectively.

    Returns a guide covering the task lifecycle, heartbeats, instance switching,
    patterns, learning feedback, and agent identity conventions.
    """
    sid = _session_id.get()
    did = _session_did.get()
    # Resolve consistently with _get_client(): on a session-cache miss, recover
    # the instance from the durable DID registry rather than misreporting the
    # active scope as "default".
    instance_name = _resolve_instance_name(sid, did)
    if instance_name:
        instance_line = f"Active instance: **{instance_name}**"
    elif _did_has_upstream_association(did):
        instance_line = (
            "Active instance: **none selected** — your identity is scoped to an "
            'upstream instance. Call hopper_switch_instance("<name>") before '
            "reading or writing, or tools will return a 'no instance selected' error."
        )
    else:
        instance_line = "Active instance: **default** (token has no instance scope)"

    return f"""# Hopper — Persistent Record Store for AI Agents

Hopper is a long-term store shared across agents (Claude, Rosetta-agent,
audit-agent, and future agents). Records persist across sessions and are
queryable by type, author, and location.

## Your session

{instance_line}

This is set by your authentication token and applies to all tool calls
in this session. Use hopper_switch_instance("name") only if you need to
explicitly change it.

## Record types

Records have a `kind` that shapes how they behave. Pick the right one at
capture time when you can — a triage agent will move `inbox` items to a
terminal kind otherwise.

  task       Work item with a status lifecycle. Has an owner, a status
             (open/in_progress/blocked/completed), and heartbeats when
             being worked. Default kind for hopper_create_task.

  idea       A seed or concept. No status lifecycle — ideas may never
             be "done." Use for "something worth writing about later"
             or "what if we built X." Do NOT use `task` for these; it
             pollutes task lists with items that will never complete.

  note       Durable context, append-only. Architecture decisions,
             session handoff notes, design rationale that should
             survive sessions. Not actionable.

  memory     Agent knowledge (use hopper_create_memory for richer
             fields). Cross-agent: what YOU learned is readable by
             other agents. First-class in Hopper — do not silo memory
             in your own vendor-specific store when it could be shared.

  reference  Pointer to an external resource: a dashboard URL, a doc,
             a ticket. Cheap to create, useful for "where was that thing."

  log        Immutable event record. Published a post, triggered a
             deploy, GPU state transitioned. Write, never update.

  inbox      Untriaged capture. Default when you're unsure. A triage
             agent will move it to a terminal kind later.

Create with:
  hopper_create_task(title=..., kind="idea")       # or task/note/log/etc.
  hopper_create_memory(title=..., content=...,
                        subject="user:preferences",
                        scope="shared-with-user")

## Core task workflow

Check what's open before starting work:
  hopper_list_tasks(status="open", limit=20)

Claim a task when you start it:
  hopper_update_task_status(task_id, "in_progress",
                             assigned_to="claude:<task-name>")

Send heartbeats every 10-15 min during long work:
  hopper_heartbeat(task_id)

Complete or release when done:
  hopper_update_task_status(task_id, "completed")
  — or to release without finishing:
  hopper_update_task(task_id, assigned_to=None, status="open")

## Author location — identify WHERE you are

Every write carries a `location` that becomes part of the revision
history. Prior art was just "cli" or "mcp" — not useful. Pass a specific
token that identifies your execution context:

  phone-claude         Claude Desktop on phone
  web-chat             claude.ai / web chat surface
  waypoint-skill       /hopper skill inside the Waypoint project
  rosetta-agent        Rosetta's GPU task controller
  audit-agent@ember    Hopper's own audit agent on ember
  jay-laptop-cli       CLI from jay's laptop
  ember-cli            CLI on the ember server

Pass the `location` argument on any creation tool call. If omitted, the
server records a generic "mcp" token, which is lossy. Err on the side
of being specific.

## Memory — how to capture agent knowledge

Use hopper_create_memory, not hopper_create_task, for things you've
learned:

  - User preferences ("User prefers terse responses")
  - Project context ("Waypoint's CLAUDE.md requires ember-specific build step")
  - Observations about other agents ("Rosetta-agent queues peak at 03:00")
  - Inferences that took work to derive

subject: identify the target of the memory. Conventions:
  user:preferences, user:<topic>, project:<slug>,
  agent:<agent-name>, self

scope:
  private                 only the author agent should act on this
  shared-with-user        surface to the human in conversations (default)
  shared-across-agents    any agent can rely on it (for widely-useful facts)

provenance: how you learned it ("conversation 2026-04-22", "observation",
"inference from memory-id abc123").

subject/scope/provenance are stored as STRUCTURED fields on the memory
record (a real kind="memory"), not as preamble text. Retrieve memory by
kind, not by a magic tag:

  hopper_list_memory()                              # all memories
  hopper_list_memory(subject="user:preferences")    # by subject
  hopper_list_memory(scope="shared-across-agents")  # by scope

## Searching

  hopper_search_tasks("keyword")
  hopper_list_tasks(status="open", priority="high")  # kind=task by default
  hopper_list_memory()                     # all memories (kind-based)
  hopper_list_tasks(kind="memory")         # equivalent, via the kind filter
  hopper_list_tasks(kind="idea")           # all ideas
  hopper_list_tasks(all_kinds=True)        # every kind, nothing hidden

hopper_list_tasks defaults to kind="task": memories, jobs, ideas and other
non-task kinds are segmented out so the task list stays focused. Use the
kind= argument or all_kinds=True to reach them.

## Instances

Each token is scoped to a Hopper instance (project namespace).
  hopper_list_instances()        — see available instances
  hopper_switch_instance("name") — switch context for subsequent calls

## Patterns & learning

Patterns route tasks to instances automatically.
  hopper_list_patterns()
  hopper_match_patterns(title, tags, priority)
  hopper_submit_feedback(task_id, "routed correctly", outcome="correct")

## Agent identity convention

Use "platform:task-name" when assigning yourself:
  "claude:auth-refactor", "claude:data-pipeline"
Never use generic names like "claude:main".

## Stale task detection

  hopper_list_stale_tasks()  — tasks with no heartbeat in 30+ min

## Record schema fields (surface)

  id, title, status, priority, description, tags, instance
  source (== author location, e.g. "ember-cli", "phone-claude")
  depends_on, parent_id, assigned_to, owner, requester
  external_id, external_url, external_platform, context
  created_at, updated_at, last_heartbeat, expected_heartbeat

Revision history (author_did, author_location per write) is tracked
internally when the server is running with the SQLite shadow enabled.
"""

