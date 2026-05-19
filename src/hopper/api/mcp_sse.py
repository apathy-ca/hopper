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
import uuid
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hopper.upstream.protocol import SyncTask
    from hopper.upstream.storage import UpstreamStorage

logger = logging.getLogger(__name__)

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from hopper.cli.local_client import LocalClient, LocalClientError


# Authentication configuration
MCP_AUTH_TOKEN = os.getenv("HOPPER_MCP_TOKEN")
MCP_ALLOWED_DIDS = os.getenv("HOPPER_MCP_ALLOWED_DIDS", "").split(",") if os.getenv("HOPPER_MCP_ALLOWED_DIDS") else []
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

    def list_tasks(self, status=None, priority=None, tags=None, limit=50, **_) -> list[dict]:
        tasks = self._all_tasks()
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        if priority:
            tasks = [t for t in tasks if t.get("priority") == priority]
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
        import uuid as _uuid, datetime as _dt
        task_id = "t" + _uuid.uuid4().hex[:8]
        now = _dt.datetime.utcnow().isoformat() + "Z"
        task = {
            "id": task_id,
            "title": data.get("title", ""),
            "status": data.get("status", "open"),
            "priority": data.get("priority", "medium"),
            "description": data.get("description"),
            "tags": data.get("tags", []),
            "instance": self._ns,
            "source": "mcp",
            "created_at": now,
            "updated_at": now,
            "assigned_to": None,
            "parent_id": None,
            "deleted": False,
        }
        self._put(task)
        return task

    def update_task(self, task_id: str, data: dict) -> dict:
        import datetime as _dt
        task = self.get_task(task_id)
        if "add_tags" in data:
            task["tags"] = list(set(task.get("tags") or []) | set(data.pop("add_tags")))
        if "remove_tags" in data:
            task["tags"] = [t for t in (task.get("tags") or []) if t not in data.pop("remove_tags")]
        for k, v in data.items():
            if k not in ("add_tags", "remove_tags"):
                task[k] = v
        task["updated_at"] = _dt.datetime.utcnow().isoformat() + "Z"
        self._put(task)
        return task

    def delete_task(self, task_id: str) -> None:
        self.update_task(task_id, {"deleted": True})

    def search_tasks(self, query: str, status=None, limit=20, **_) -> list[dict]:
        q = query.lower()
        tasks = [t for t in self._all_tasks()
                 if q in (t.get("title") or "").lower() or q in (t.get("description") or "").lower()]
        if status:
            tasks = [t for t in tasks if t.get("status") == status]
        return tasks[:limit]

    def heartbeat_task(self, task_id: str, expect_minutes=None) -> dict:
        import datetime as _dt
        data = {"last_heartbeat": _dt.datetime.utcnow().isoformat() + "Z"}
        if expect_minutes:
            exp = _dt.datetime.utcnow() + _dt.timedelta(minutes=expect_minutes)
            data["expected_heartbeat"] = exp.isoformat() + "Z"
        return self.update_task(task_id, data)

    def list_stale_tasks(self, minutes: int = 30) -> list[dict]:
        import datetime as _dt
        threshold = _dt.datetime.utcnow() - _dt.timedelta(minutes=minutes)
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

    def list_projects(self) -> list: return []
    def list_instances(self) -> list: return [{"id": self._ns, "name": self._ns}]
    def match_patterns(self, **_) -> list: return []
    def submit_feedback(self, task_id, data): return {"status": "ok"}
    def get_learning_statistics(self) -> dict: return {}
    def list_patterns(self, active_only=True) -> dict: return {"patterns": [], "total": 0}
    def create_pattern(self, data) -> dict: return data


def _get_client():
    """Get the appropriate client for the current session's instance.

    Instance resolution is server-side only:
    1. Named instance → UpstreamNamespaceClient backed by UpstreamStorage
    2. Fallback → server's default LocalClient (~/.hopper)

    instance_path from client tokens is intentionally ignored — the server
    never accesses arbitrary filesystem paths supplied by clients.
    """
    sid = _session_id.get()
    _, instance_name = _session_instances.get(sid, (None, None)) if sid else (None, None)
    if instance_name:
        from hopper.upstream.server import get_storage
        try:
            storage = get_storage()
        except Exception:
            storage = None
        if storage is not None:
            return UpstreamNamespaceClient(instance_name, storage)
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

        tag_list = list(tags or [])
        if kind != "task" and kind not in tag_list:
            tag_list.insert(0, kind)

        with _get_client() as client:
            result = client.create_task({
                "title": title,
                "description": description,
                "priority": priority,
                "tags": tag_list,
                "source": resolve_location(override=location, transport="mcp"),
            })
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
        tags: Additional tags (the 'memory' tag is added automatically)
        location: Author location — see hopper_create_task for guidance.
    """
    try:
        from hopper.location import resolve_location

        preamble: list[str] = [f"Subject: {subject}", f"Scope: {scope}"]
        if provenance:
            preamble.append(f"Provenance: {provenance}")
        description = "\n".join(preamble) + "\n\n" + content

        tag_list = list(tags or [])
        if "memory" not in tag_list:
            tag_list.insert(0, "memory")

        with _get_client() as client:
            result = client.create_task({
                "title": title,
                "description": description,
                "priority": priority,
                "tags": tag_list,
                "source": resolve_location(override=location, transport="mcp"),
            })
            return {"status": "created", "memory": result}
    except LocalClientError as e:
        return {"status": "error", "message": e.message}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def hopper_list_tasks(
    status: str | None = None,
    priority: str | None = None,
    tags: str | None = None,
    limit: int = 50,
) -> dict:
    """List tasks from Hopper with optional filters.

    Returns tasks sorted by status (in_progress first, then pending, completed last)
    and then by priority within each status group.

    Args:
        status: Filter by status - one of: open, pending, in_progress, blocked, completed, cancelled
        priority: Filter by priority - one of: low, medium, high, urgent
        tags: Comma-separated list of tags to filter by
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
            (t for t in all_tokens if t.get("instance") == instance_name and t.get("instance_path")),
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
    _, instance_name = _session_instances.get(sid, (None, None)) if sid else (None, None)
    instance_line = f"Active instance: **{instance_name}**" if instance_name else "Active instance: **default** (token has no instance scope)"

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

## Searching

  hopper_search_tasks("keyword")
  hopper_list_tasks(status="open", priority="high")
  hopper_list_tasks(tags=["memory"])       # all memories
  hopper_list_tasks(tags=["idea"])         # all ideas

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


def _canonical_base_url(request) -> str:
    """Server's canonical base URL for audience validation + metadata hints.

    Priority: HOPPER_PUBLIC_URL env var, else the request's scheme+host.
    """
    env = os.getenv("HOPPER_PUBLIC_URL")
    if env:
        return env.rstrip("/")
    return f"{request.url.scheme}://{request.url.netloc}".rstrip("/")


def _bearer_challenge(request, error: str | None = None) -> dict[str, str]:
    """Build a WWW-Authenticate Bearer challenge with RFC 9728 metadata hint."""
    base = _canonical_base_url(request)
    metadata_url = f"{base}/.well-known/oauth-protected-resource"
    parts = [f'Bearer resource_metadata="{metadata_url}"']
    if error:
        parts.append(f'error="{error}"')
    return {"WWW-Authenticate": ", ".join(parts)}


def _check_auth(request, body: bytes = b"") -> tuple[JSONResponse | None, str | None, Path | None, str | None]:
    """Check authentication (DID, OAuth access token, or legacy Bearer).

    Returns (error_response, authenticated_id, instance_path, instance_name) where:
    - error_response is None if auth passes, or a JSONResponse with 401/403 if it fails
    - authenticated_id is the DID if auth passes
    - instance_path is the storage path for this token's instance (or None)
    - instance_name is the instance name from the token (or None)

    Auth methods (checked in order):
    1. DID auth: `Authorization: DID <did> <signature>`
    2. Bearer hpo_ (OAuth 2.1 access token, resource-bound)
    3. Bearer hpr_ (registered Hopper token)
    4. Bearer <legacy HOPPER_MCP_TOKEN>

    If no auth is configured (no token, no allowed DIDs), allows all requests.
    """
    auth_header = request.headers.get("Authorization", "")

    # Check if any auth is required
    auth_required = MCP_AUTH_TOKEN or MCP_ALLOWED_DIDS or MCP_DID_OPEN_ACCESS

    if not auth_header:
        if not auth_required:
            return None, None, None, None  # No auth required, allow
        return JSONResponse(
            {"error": "Missing Authorization header"},
            status_code=401,
            headers=_bearer_challenge(request),
        ), None, None, None

    # Try DID auth first
    if auth_header.startswith("DID "):
        from hopper.upstream.did import verify_signature
        valid, did = verify_signature(
            auth_header=auth_header,
            method=request.method,
            path=request.url.path,
            body=body,
        )
        if not valid or not did:
            return JSONResponse(
                {"error": "Invalid DID signature"},
                status_code=401,
                headers={"WWW-Authenticate": "DID"},
            ), None, None, None
        if MCP_ALLOWED_DIDS and did not in MCP_ALLOWED_DIDS:
            return JSONResponse(
                {"error": f"DID not authorized: {did}"},
                status_code=403,
            ), None, None, None
        # Restore last instance for this DID
        last_instance = None
        try:
            from hopper.upstream.server import get_storage
            storage = get_storage()
            last_instance = storage.did_registry.get_last_instance(did)
        except Exception:
            pass  # Storage not configured or DID not found
        return None, did, None, last_instance

    # Try Bearer token
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

        # OAuth 2.1 access token (issued by /oauth/token)
        if token.startswith("hpo_"):
            from hopper.api.oauth_store import get_oauth_store
            try:
                record = get_oauth_store().lookup_access_token(token)
            except Exception:
                record = None
            if not record:
                return JSONResponse(
                    {"error": "Invalid or expired access token"},
                    status_code=401,
                    headers=_bearer_challenge(request, error="invalid_token"),
                ), None, None, None
            canonical = _canonical_base_url(request)
            recorded = str(record.get("resource", "")).rstrip("/")
            if not (recorded == canonical
                    or recorded == f"{canonical}/mcp"
                    or recorded == f"{canonical}/mcp/sse"):
                return JSONResponse(
                    {"error": "Token audience does not match this resource"},
                    status_code=401,
                    headers=_bearer_challenge(request, error="invalid_token"),
                ), None, None, None
            did = record["did"]
            instance_path = record.get("instance_path")
            instance_name = record.get("instance")
            if instance_path:
                instance_path = Path(instance_path)
                if not instance_path.exists():
                    instance_path = None  # Fall back to upstream lookup by name
            return None, did, instance_path, instance_name

        # Registered hpr_ token (maps to DID + instance)
        if token.startswith("hpr_"):
            from hopper.api.mcp_tokens import get_token_store
            try:
                store = get_token_store()
                token_info = store.lookup_full(token)
                if token_info:
                    did = token_info["did"]
                    instance_path = token_info.get("instance_path")
                    instance_name = token_info.get("instance")
                    if instance_path:
                        instance_path = Path(instance_path)
                        if not instance_path.exists():
                            instance_path = None
                    return None, did, instance_path, instance_name
            except Exception:
                pass
            return JSONResponse(
                {"error": "Invalid or expired token"},
                status_code=401,
                headers=_bearer_challenge(request, error="invalid_token"),
            ), None, None, None

        # Legacy: check against simple HOPPER_MCP_TOKEN env var
        if MCP_AUTH_TOKEN and token == MCP_AUTH_TOKEN:
            import hashlib
            token_id = f"bearer:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
            return None, token_id, None, None

        return JSONResponse(
            {"error": "Invalid token"},
            status_code=401,
            headers=_bearer_challenge(request, error="invalid_token"),
        ), None, None, None

    return JSONResponse(
        {"error": "Unsupported Authorization scheme. Use 'DID' or 'Bearer'"},
        status_code=401,
        headers=_bearer_challenge(request),
    ), None, None, None


def create_sse_server():
    """Create Starlette app for MCP SSE transport (legacy path /mcp/sse/).

    Returns a Starlette application mounting the SSE transport at /sse/
    and the POST message endpoint at /messages/.
    """
    transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        auth_error, auth_id, instance_path, instance_name = _check_auth(request)
        if auth_error:
            return auth_error

        sid = str(uuid.uuid4())
        _session_instances[sid] = (instance_path, instance_name)
        # Persist the instance for this DID (for future reconnections)
        if auth_id and instance_name:
            try:
                from hopper.upstream.server import get_storage
                get_storage().did_registry.update_last_instance(auth_id, instance_name)
            except Exception:
                pass  # Best effort
        sid_token = _session_id.set(sid)
        did_token = _session_did.set(auth_id)
        try:
            async with transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await mcp._mcp_server.run(
                    streams[0],
                    streams[1],
                    mcp._mcp_server.create_initialization_options(),
                )
        finally:
            _session_instances.pop(sid, None)
            _session_id.reset(sid_token)
            _session_did.reset(did_token)

    async def handle_messages(request):
        body = await request.body()
        auth_error, auth_id, instance_path, instance_name = _check_auth(request, body)
        if auth_error:
            return auth_error

        async def replay_receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return await transport.handle_post_message(request.scope, replay_receive, request._send)

    return Starlette(
        routes=[
            Route("/sse/", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )


from mcp.server.streamable_http import MCP_SESSION_ID_HEADER
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

# Module-level session manager — started by the main app lifespan (see app.py)
_streamable_session_manager: StreamableHTTPSessionManager | None = None


def get_streamable_session_manager() -> StreamableHTTPSessionManager:
    """Return the module-level Streamable HTTP session manager, creating it if needed."""
    global _streamable_session_manager
    if _streamable_session_manager is None:
        _streamable_session_manager = StreamableHTTPSessionManager(
            app=mcp._mcp_server,
            json_response=True,
            stateless=False,
        )
    return _streamable_session_manager


_SSE_KEEPALIVE_INTERVAL = 1500  # seconds — fires before nginx's 3600s proxy_read_timeout
_SSE_KEEPALIVE_PING = b": ping\n\n"


class _StreamableHTTPASGIHandler:
    """Auth-gated ASGI handler for MCP Streamable HTTP transport.

    Acts as a raw ASGI callable so that it can drive the full ASGI lifecycle
    (headers + body streaming) without Starlette expecting a Response return value.
    """

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return

        from starlette.requests import Request as StarletteRequest
        request = StarletteRequest(scope, receive)

        # Read body once for auth (may be empty for GET/DELETE)
        body = await request.body()

        auth_error, auth_id, instance_path, instance_name = _check_auth(request, body)
        if auth_error:
            await auth_error(scope, receive, send)
            return

        # Extract or allocate a session ID for context-var based instance routing.
        # If the client sends a stale session ID (expired after server restart or
        # timeout) AND the request is an initialize, strip the session ID so the
        # MCP manager creates a fresh session. For non-initialize requests with a
        # stale session ID, pass through unchanged so MCP returns 404 — clients
        # that handle 404 will reinitialize; those that don't would break on 400
        # anyway. Stripping on non-initialize causes 400 "Missing session ID".
        sm = get_streamable_session_manager()
        raw_sid = request.headers.get(MCP_SESSION_ID_HEADER)
        if raw_sid and raw_sid not in sm._server_instances:
            try:
                import json as _json
                _method = _json.loads(body).get("method", "")
            except Exception:
                _method = ""
            if _method == "initialize":
                logger.info("MCP session %s not found — reconnecting as new session", raw_sid)
                scope = dict(scope)
                _sid_header_bytes = MCP_SESSION_ID_HEADER.lower().encode()
                scope["headers"] = [
                    (k, v) for k, v in scope.get("headers", [])
                    if k.lower() != _sid_header_bytes
                ]
                raw_sid = None
            else:
                logger.info("MCP session %s not found, method=%s — returning 404 to trigger reinitialize", raw_sid, _method)

        sid = raw_sid or str(uuid.uuid4())

        # On first touch for a session, record the authenticated instance
        if sid not in _session_instances:
            _session_instances[sid] = (instance_path, instance_name)
            # Persist the instance for this DID (for future reconnections)
            if auth_id and instance_name:
                try:
                    from hopper.upstream.server import get_storage
                    get_storage().did_registry.update_last_instance(auth_id, instance_name)
                except Exception:
                    pass  # Best effort - storage may not be configured

        sid_token = _session_id.set(sid)
        did_token = _session_did.set(auth_id)

        # Replay body once, then forward real receive so http.disconnect is
        # properly delivered (SSE streams block until client disconnect).
        _replayed = False

        async def replay_receive():
            nonlocal _replayed
            if not _replayed:
                _replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        # For SSE responses, inject periodic comment pings so the nginx
        # proxy_read_timeout (3600s) never fires on an idle stream.
        _is_sse = False

        async def tracked_send(message):
            nonlocal _is_sse
            if message.get("type") == "http.response.start":
                for k, v in message.get("headers", []):
                    if k == b"content-type" and b"text/event-stream" in v:
                        _is_sse = True
            await send(message)

        async def keepalive_loop():
            import anyio
            while True:
                await anyio.sleep(_SSE_KEEPALIVE_INTERVAL)
                if not _is_sse:
                    continue
                try:
                    await send({"type": "http.response.body", "body": _SSE_KEEPALIVE_PING, "more_body": True})
                except Exception:
                    break

        import anyio
        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(keepalive_loop)
                await sm.handle_request(scope, replay_receive, tracked_send)
                tg.cancel_scope.cancel()
        finally:
            _session_id.reset(sid_token)
            _session_did.reset(did_token)
            # Don't pop _session_instances here — the session persists across requests


def create_streamable_http_server() -> _StreamableHTTPASGIHandler:
    """Return auth-gated ASGI handler for MCP Streamable HTTP transport (MCP 1.26+).

    Returns a raw ASGI callable that can be mounted directly on FastAPI with
    app.mount("/mcp", create_streamable_http_server()).

    The underlying StreamableHTTPSessionManager must be started via its run()
    context manager before requests arrive — done in the main app's lifespan.
    """
    return _StreamableHTTPASGIHandler()
