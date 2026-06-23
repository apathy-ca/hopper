"""Overseer tools for MCP.

Provides cross-instance visibility for overseer instances: status across
sub-instances, search across the DAG, and access to northbound summaries.
"""

from typing import Any

import httpx
from mcp.types import Tool


def get_overseer_tools() -> list[Tool]:
    """Get list of overseer-specific MCP tools."""
    return [
        Tool(
            name="hopper_overseer_status",
            description=(
                "Get an overview of an overseer's sub-instances including task "
                "counts, memory counts, and last consolidation timestamps. Use "
                "this to understand what's happening across all sub-instances."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "Overseer instance ID to query.",
                    },
                },
                "required": ["instance_id"],
            },
        ),
        Tool(
            name="hopper_overseer_search",
            description=(
                "Search across all sub-instances of an overseer for tasks or "
                "memories matching a query. Returns results tagged with their "
                "source instance so you know where each result lives."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "Overseer instance ID whose sub-instances to search.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query (matched against title and description).",
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["task", "memory", "idea", "note", "reference"],
                        "description": "Filter by record kind (default: all kinds).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results per sub-instance (default: 10).",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                    },
                },
                "required": ["instance_id", "query"],
            },
        ),
        Tool(
            name="hopper_overseer_northbound",
            description=(
                "Get the northbound summaries for an overseer — cross-cutting "
                "insights synthesized from sub-instance memories. These are the "
                "high-level themes and connections that span projects. Each "
                "summary includes pointers to the source instances and records."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {
                        "type": "string",
                        "description": "Overseer instance ID.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum summaries to return (default: 20).",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["instance_id"],
            },
        ),
        Tool(
            name="hopper_get_sub_instance_record",
            description=(
                "Fetch a specific record from any sub-instance. Use this to "
                "drill down into a source record referenced by a northbound "
                "summary or cross-instance search result."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Record ID to retrieve (from any instance).",
                    },
                },
                "required": ["task_id"],
            },
        ),
    ]


async def overseer_status(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Get status overview of an overseer's sub-instances."""
    instance_id = args["instance_id"]

    # Get children via the DAG endpoint
    children_resp = await client.get(f"/api/v1/instances/{instance_id}/children")
    children_resp.raise_for_status()
    children = children_resp.json()

    if not children:
        return {
            "instance_id": instance_id,
            "sub_instances": [],
            "message": "No sub-instances registered for this overseer.",
        }

    sub_statuses = []
    for child in children:
        child_id = child["id"]
        summary: dict[str, Any] = {
            "id": child_id,
            "name": child.get("name", child_id),
            "scope": child.get("scope", "unknown"),
        }

        # Get task count
        try:
            tasks_resp = await client.get(
                "/api/v1/tasks", params={"kind": "task", "limit": 1}
            )
            tasks_resp.raise_for_status()
            summary["task_count"] = tasks_resp.json().get("total", 0)
        except Exception:
            summary["task_count"] = "unknown"

        # Get memory count
        try:
            mem_resp = await client.get(
                "/api/v1/tasks", params={"kind": "memory", "limit": 1}
            )
            mem_resp.raise_for_status()
            summary["memory_count"] = mem_resp.json().get("total", 0)
        except Exception:
            summary["memory_count"] = "unknown"

        # Get consolidation metadata
        meta = child.get("runtime_metadata") or {}
        summary["last_consolidation_at"] = meta.get("last_consolidation_at")
        summary["last_northbound_at"] = meta.get("last_northbound_at")

        sub_statuses.append(summary)

    return {
        "instance_id": instance_id,
        "sub_instance_count": len(sub_statuses),
        "sub_instances": sub_statuses,
    }


async def overseer_search(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Search across all sub-instances of an overseer."""
    instance_id = args["instance_id"]
    query = args["query"]
    kind = args.get("kind")
    limit = args.get("limit", 10)

    # Get children
    children_resp = await client.get(f"/api/v1/instances/{instance_id}/children")
    children_resp.raise_for_status()
    children = children_resp.json()

    if not children:
        return {"instance_id": instance_id, "results": [], "total": 0}

    # Search uses the tasks search endpoint which searches across all instances.
    # We tag results with their source instance from the record metadata.
    params: dict[str, Any] = {"q": query, "limit": limit * len(children)}
    if kind:
        params["kind"] = kind

    search_resp = await client.get("/api/v1/tasks/search", params=params)
    search_resp.raise_for_status()
    data = search_resp.json()

    results = data.get("tasks", data.get("items", []))

    # Tag each result with source instance info
    for r in results:
        r["source_instance"] = r.get("instance") or r.get("instance_id") or "unknown"

    return {
        "instance_id": instance_id,
        "query": query,
        "results": results[:limit],
        "total": len(results),
        "sub_instances_searched": [c["id"] for c in children],
    }


async def overseer_northbound(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Get northbound summaries for an overseer instance."""
    instance_id = args["instance_id"]
    limit = args.get("limit", 20)

    # Query memories with memory_class=northbound for this instance
    params: dict[str, Any] = {
        "kind": "memory",
        "limit": limit,
        "tags": "northbound",
    }

    resp = await client.get("/api/v1/tasks", params=params)
    resp.raise_for_status()
    data = resp.json()

    memories = data.get("tasks", data.get("items", []))

    # Filter to northbound class
    northbound_summaries = [
        m for m in memories if m.get("memory_class") == "northbound"
    ]

    return {
        "instance_id": instance_id,
        "summaries": northbound_summaries,
        "total": len(northbound_summaries),
    }


async def get_sub_instance_record(
    client: httpx.AsyncClient,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Fetch a specific record from any instance (cross-instance drill-down)."""
    task_id = args["task_id"]

    response = await client.get(f"/api/v1/tasks/{task_id}")
    response.raise_for_status()

    return response.json()
