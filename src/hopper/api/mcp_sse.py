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

import os
from contextvars import ContextVar
from pathlib import Path

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

# Context variable for current session's instance path
# Set by the SSE handler based on the authenticated token
_current_instance_path: ContextVar[Path | None] = ContextVar("instance_path", default=None)


def _get_client() -> LocalClient:
    """Get a LocalClient for the current session's instance.

    Uses the instance_path from the authenticated token if available,
    otherwise uses the default (~/.hopper).
    """
    instance_path = _current_instance_path.get()
    if instance_path:
        return LocalClient(storage_path=instance_path)
    return LocalClient()


# Initialize FastMCP server
mcp = FastMCP("hopper")


# =============================================================================
# Task Tools
# =============================================================================


@mcp.tool()
def hopper_create_task(
    title: str,
    description: str = "",
    priority: str = "medium",
    tags: list[str] | None = None,
) -> dict:
    """Create a new task in Hopper.

    Use this to track work items, TODOs, learnings, or any persistent notes
    that should survive across sessions.

    Args:
        title: Task title (required) - a concise summary of the task
        description: Detailed task description or notes
        priority: Task priority - one of: low, medium, high, urgent
        tags: List of tags for categorization and filtering
    """
    try:
        with _get_client() as client:
            result = client.create_task({
                "title": title,
                "description": description,
                "priority": priority,
                "tags": tags or [],
            })
            return {"status": "created", "task": result}
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
# SSE Server Creation
# =============================================================================


def _check_auth(request, body: bytes = b"") -> tuple[JSONResponse | None, str | None, Path | None]:
    """Check authentication (DID or Bearer token).

    Returns (error_response, authenticated_id, instance_path) where:
    - error_response is None if auth passes, or a JSONResponse with 401/403 if it fails
    - authenticated_id is the DID if auth passes
    - instance_path is the storage path for this token's instance (or None for default)

    Auth methods (checked in order):
    1. DID auth: `Authorization: DID <did> <signature>`
    2. Bearer token: `Authorization: Bearer <token>`

    If no auth is configured (no token, no allowed DIDs), allows all requests.
    """
    auth_header = request.headers.get("Authorization", "")

    # Check if any auth is required
    auth_required = MCP_AUTH_TOKEN or MCP_ALLOWED_DIDS or MCP_DID_OPEN_ACCESS

    if not auth_header:
        if not auth_required:
            return None, None, None  # No auth required, allow
        return JSONResponse(
            {"error": "Missing Authorization header"},
            status_code=401,
            headers={"WWW-Authenticate": "DID, Bearer"},
        ), None, None

    # Try DID auth first
    if auth_header.startswith("DID "):
        from hopper.upstream.did import verify_signature

        # For SSE, we verify against GET method and path (no body for initial connect)
        method = request.method
        path = request.url.path

        valid, did = verify_signature(
            auth_header=auth_header,
            method=method,
            path=path,
            body=body,
        )

        if not valid or not did:
            return JSONResponse(
                {"error": "Invalid DID signature"},
                status_code=401,
                headers={"WWW-Authenticate": "DID"},
            ), None, None

        # Check if DID is allowed
        if MCP_ALLOWED_DIDS and did not in MCP_ALLOWED_DIDS:
            return JSONResponse(
                {"error": f"DID not authorized: {did}"},
                status_code=403,
            ), None, None

        # DID is valid and allowed (or open access) - no instance path for direct DID auth
        return None, did, None

    # Try Bearer token
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # Strip "Bearer "

        # Check if it's a registered hpr_ token (maps to DID + instance)
        if token.startswith("hpr_"):
            from hopper.api.mcp_tokens import get_token_store

            try:
                store = get_token_store()
                token_info = store.lookup_full(token)
                if token_info:
                    did = token_info["did"]
                    instance_path = token_info.get("instance_path")
                    if instance_path:
                        instance_path = Path(instance_path)
                    return None, did, instance_path
            except Exception:
                pass  # Fall through to error

            return JSONResponse(
                {"error": "Invalid or expired token"},
                status_code=401,
                headers={"WWW-Authenticate": "Bearer"},
            ), None, None

        # Legacy: check against simple HOPPER_MCP_TOKEN env var
        if MCP_AUTH_TOKEN and token == MCP_AUTH_TOKEN:
            import hashlib
            token_id = f"bearer:{hashlib.sha256(token.encode()).hexdigest()[:16]}"
            return None, token_id, None

        # No valid token
        return JSONResponse(
            {"error": "Invalid token"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        ), None, None

    # Unknown auth scheme
    return JSONResponse(
        {"error": "Unsupported Authorization scheme. Use 'DID' or 'Bearer'"},
        status_code=401,
        headers={"WWW-Authenticate": "DID, Bearer"},
    ), None, None


def create_sse_server():
    """Create Starlette app for MCP SSE transport.

    Returns a Starlette application that can be mounted on an existing
    ASGI app or run standalone for MCP SSE communication.

    The server exposes two endpoints:
    - /sse/ - SSE endpoint for server-to-client communication
    - /messages/ - POST endpoint for client-to-server messages

    Authentication:
        Set HOPPER_MCP_TOKEN env var to require Bearer token auth.
        Token is passed via authorization_token in Claude's mcp_servers config.
    """
    transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        """Handle SSE connection for MCP communication."""
        # Check authentication (no body for SSE GET)
        auth_error, auth_id, instance_path = _check_auth(request)
        if auth_error:
            return auth_error

        # Set instance path for this session's tool calls
        token = _current_instance_path.set(instance_path)
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
            _current_instance_path.reset(token)

    async def handle_messages(request):
        """Handle POST messages with auth check."""
        # Read body for DID signature verification
        body = await request.body()
        auth_error, auth_id, instance_path = _check_auth(request, body)
        if auth_error:
            return auth_error

        # Set instance path for this request's tool calls
        token = _current_instance_path.set(instance_path)
        try:
            return await transport.handle_post_message(request.scope, request.receive, request._send)
        finally:
            _current_instance_path.reset(token)

    return Starlette(
        routes=[
            Route("/sse/", endpoint=handle_sse),
            Route("/messages/", endpoint=handle_messages, methods=["POST"]),
        ]
    )


def get_mcp_app():
    """Get the MCP SSE Starlette application.

    Convenience function for importing and mounting the MCP SSE server.

    Usage:
        from hopper.api.mcp_sse import get_mcp_app
        mcp_app = get_mcp_app()
        # Mount on FastAPI: app.mount("/mcp", mcp_app)

    Authentication (two methods):

    1. DID Auth (recommended):
        # Allow specific DIDs
        export HOPPER_MCP_ALLOWED_DIDS="did:key:z6Mk...,did:key:z6Mk..."
        hopper server start

        # Or allow any valid DID signature (open access with identity)
        export HOPPER_MCP_DID_OPEN=true
        hopper server start

        Clients sign requests with their DID key:
        Authorization: DID did:key:z6Mk... <base64-signature>

    2. Bearer Token (simple):
        export HOPPER_MCP_TOKEN="your-secret-token"
        hopper server start

        In Claude API/Web config:
        {
            "mcp_servers": [{
                "type": "url",
                "url": "https://your-server.com/mcp/sse/",
                "name": "hopper",
                "authorization_token": "your-secret-token"
            }]
        }
    """
    return create_sse_server()
