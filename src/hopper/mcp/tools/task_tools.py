"""
Task management tools for MCP.

Provides MCP tools for creating, listing, getting, and updating tasks.
"""

from typing import Any

import httpx
from mcp.types import Tool


def get_task_tools() -> list[Tool]:
    """Get list of task management tools.

    Returns:
        List of MCP Tool definitions for task management
    """
    return [
        Tool(
            name="hopper_create_task",
            description=(
                "Create a new task in Hopper. Tasks can be routed to appropriate "
                "projects based on content. Use this when the user wants to capture "
                "a task, idea, or work item during a conversation."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Task title (required, should be concise)",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed task description with context",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Task priority (default: medium)",
                        "default": "medium",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tags for categorization (e.g., ['bug', 'frontend'])",
                    },
                    "project": {
                        "type": "string",
                        "description": (
                            "Target project identifier. If not provided, the task "
                            "will be automatically routed based on content."
                        ),
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["task", "idea", "note", "memory", "inbox", "log", "reference"],
                        "description": "Record kind (default: task). For memory, prefer setting "
                                       "subject/scope so it is captured as structured knowledge.",
                        "default": "task",
                    },
                    "subject": {
                        "type": "string",
                        "description": "For kind='memory': what the memory is about "
                                       "(e.g. 'user:preferences', 'project:<slug>', 'agent:<name>', 'self').",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["private", "shared-with-user", "shared-across-agents"],
                        "description": "For kind='memory': who can rely on this memory.",
                    },
                    "provenance": {
                        "type": "string",
                        "description": "For kind='memory': how it was learned "
                                       "(e.g. 'conversation 2026-04-22', 'observation').",
                    },
                    "location": {
                        "type": "string",
                        "description": "Author location context (e.g. 'phone-claude', 'ember-cli'). "
                                       "Inferred from HOPPER_LOCATION env var if not supplied.",
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="hopper_list_tasks",
            description=(
                "List records from Hopper, defaulting to kind='task'. Memories, jobs, "
                "ideas and other non-task kinds are excluded by default so the task "
                "list stays focused. Pass kind='memory' (or any kind) to view a "
                "specific kind, or all_kinds=true to see everything. To browse agent "
                "knowledge, prefer hopper_list_memory."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "Filter by task status",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Filter by priority level",
                    },
                    "project": {
                        "type": "string",
                        "description": "Filter by project identifier",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by tags (returns tasks matching any tag)",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["task", "memory", "idea", "note", "reference", "inbox", "log", "job"],
                        "description": "Filter by record kind. Defaults to 'task' when omitted.",
                    },
                    "all_kinds": {
                        "type": "boolean",
                        "description": "If true, return every kind (disables the default kind='task' filter).",
                        "default": False,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
            },
        ),
        Tool(
            name="hopper_list_memory",
            description=(
                "List memory records — first-class agent knowledge. This is the "
                "kind-based retrieval path for memory (it filters kind='memory', NOT "
                "the legacy tags=['memory'] approach). Use it to recall what you and "
                "other agents have learned."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "Filter on the structured subject field "
                                       "(e.g. 'user:preferences', 'project:<slug>').",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["private", "shared-with-user", "shared-across-agents"],
                        "description": "Filter on scope.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional tags to filter by.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memories to return (default: 10)",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
            },
        ),
        Tool(
            name="hopper_get_task",
            description=(
                "Get detailed information about a specific task. Use this when you "
                "need full task details including description, status, routing info, etc."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to retrieve (e.g., 'task-123' or UUID)",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="hopper_update_task",
            description=(
                "Update an existing task. Can update title, description, priority, "
                "or tags. Only provide the fields you want to change."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to update",
                    },
                    "title": {
                        "type": "string",
                        "description": "Updated title",
                    },
                    "description": {
                        "type": "string",
                        "description": "Updated description",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Updated priority",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Updated tags (replaces existing tags)",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="hopper_update_task_status",
            description=(
                "Change the status of a task. Use this to mark tasks as in_progress "
                "when starting work, or completed when done."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task ID to update",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["pending", "in_progress", "completed", "cancelled"],
                        "description": "New status for the task",
                    },
                },
                "required": ["task_id", "status"],
            },
        ),
    ]


async def create_task(
    client: httpx.AsyncClient,
    args: dict[str, Any],
    context: dict[str, Any],
    default_priority: str = "medium",
) -> dict[str, Any]:
    """Create a new task via the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Task creation arguments from MCP tool call
        context: Current server context
        default_priority: Default priority if not specified

    Returns:
        Created task information including ID and routing details
    """
    from hopper.location import resolve_location

    location = args.get("location") or resolve_location(transport="mcp")
    task_data = {
        "title": args["title"],
        "description": args.get("description", ""),
        "priority": args.get("priority", default_priority),
        "tags": args.get("tags", []),
        "source": location,
        "kind": args.get("kind", "task"),
    }

    # Structured memory fields — persisted as real record fields (not preamble)
    # for kind="memory". Mirrors the CLI `hopper memory add`.
    for field in ("subject", "scope", "provenance"):
        if args.get(field) is not None:
            task_data[field] = args[field]

    if "project" in args:
        task_data["project"] = args["project"]

    response = await client.post("/api/v1/tasks", json=task_data)
    response.raise_for_status()

    task = response.json()

    return {
        "task_id": task["id"],
        "title": task["title"],
        "routed_to": task.get("project"),
        "url": task.get("external_url"),
        "status": "created",
        "message": f"Task '{task['title']}' created successfully",
    }


async def list_tasks(
    client: httpx.AsyncClient,
    args: dict[str, Any],
    default_limit: int = 10,
) -> dict[str, Any]:
    """List tasks from the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Filter arguments from MCP tool call
        default_limit: Default limit if not specified

    Returns:
        List of tasks with total count
    """
    params = {
        "limit": args.get("limit", default_limit),
    }

    if "status" in args:
        params["status"] = args["status"]
    if "priority" in args:
        params["priority"] = args["priority"]
    if "project" in args:
        params["project"] = args["project"]
    if "tags" in args:
        params["tags"] = ",".join(args["tags"])

    # Default segmentation: task-oriented views show only kind="task". An
    # explicit kind selects a different kind; all_kinds disables the filter so
    # nothing is hidden. Mirrors the CLI `hopper task list` behaviour.
    if args.get("kind"):
        params["kind"] = args["kind"]
    elif not args.get("all_kinds"):
        params["kind"] = "task"

    response = await client.get("/api/v1/tasks", params=params)
    response.raise_for_status()

    data = response.json()
    return {
        "tasks": data.get("tasks", []),
        "total": data.get("total", 0),
        "filters": params,
    }


async def list_memory(
    client: httpx.AsyncClient,
    args: dict[str, Any],
    default_limit: int = 10,
) -> dict[str, Any]:
    """List memory records (kind='memory') from the Hopper API.

    This is the kind-based retrieval path for agent knowledge, replacing the
    legacy tags=['memory'] approach. subject/scope are matched against the
    structured fields on each memory record.

    Args:
        client: HTTP client configured for the Hopper API
        args: Filter arguments (subject, scope, tags, limit)
        default_limit: Default limit if not specified

    Returns:
        List of memories with total count
    """
    params: dict[str, Any] = {
        "limit": args.get("limit", default_limit),
        "kind": "memory",
    }
    if "tags" in args:
        params["tags"] = ",".join(args["tags"])

    response = await client.get("/api/v1/tasks", params=params)
    response.raise_for_status()

    data = response.json()
    memories = data.get("tasks", data.get("items", []))

    # Filter on structured fields client-side (kind-based, not tag-based).
    subject = args.get("subject")
    scope = args.get("scope")
    if subject:
        memories = [m for m in memories if m.get("subject") == subject]
    if scope:
        memories = [m for m in memories if m.get("scope") == scope]

    return {
        "memories": memories,
        "total": len(memories),
        "filters": params,
    }


async def get_task(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Get a specific task from the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Arguments containing task_id

    Returns:
        Full task details
    """
    task_id = args["task_id"]

    response = await client.get(f"/api/v1/tasks/{task_id}")
    response.raise_for_status()

    return response.json()


async def update_task(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Update a task via the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Update arguments including task_id

    Returns:
        Updated task details
    """
    # Extract task_id and prepare update data
    args_copy = args.copy()
    task_id = args_copy.pop("task_id")

    # Only include fields that were provided
    update_data = {k: v for k, v in args_copy.items() if v is not None}

    if not update_data:
        raise ValueError("No fields provided for update")

    response = await client.patch(f"/api/v1/tasks/{task_id}", json=update_data)
    response.raise_for_status()

    return response.json()


async def update_task_status(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Update task status via the Hopper API.

    Args:
        client: HTTP client configured for the Hopper API
        args: Arguments containing task_id and new status

    Returns:
        Updated task details
    """
    task_id = args["task_id"]
    new_status = args["status"]

    response = await client.patch(f"/api/v1/tasks/{task_id}/status", json={"status": new_status})
    response.raise_for_status()

    return response.json()
