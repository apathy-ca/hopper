"""Tests for first-class record kind on the MCP surfaces.

Covers BOTH MCP servers:
  - stdio server (hopper.mcp.tools.task_tools), which talks to the REST API
    over httpx — verified by asserting the request payload/params it sends.
  - SSE server (hopper.api.mcp_sse), whose tools delegate to a LocalClient
    (fully kind-aware) — verified end-to-end against a markdown store.

The model under test (mirrors the CLI):
  - create writes a real `kind`/`subject`/`scope`/`provenance`, not a tag/preamble;
  - list defaults to kind="task" and segments memory/job/etc. out, with an
    escape hatch (kind=<x> or all_kinds=true);
  - memory is retrieved by kind, not by tags=["memory"].
"""

import pytest

from hopper.mcp.tools.task_tools import (
    create_task,
    get_task_tools,
    list_memory,
    list_tasks,
)

# ---------------------------------------------------------------------------
# stdio server (REST-backed) — assert the outbound HTTP payload/params
# ---------------------------------------------------------------------------


class TestStdioCreatePersistsKind:
    """The stdio create tool sends real kind/subject/scope/provenance fields."""

    @pytest.mark.asyncio
    async def test_create_memory_sends_structured_fields_not_preamble(
        self, mock_http_client, mock_http_response
    ):
        mock_http_client.post.return_value = mock_http_response(
            json_data={"id": "m-1", "title": "User prefers terse replies"}
        )

        await create_task(
            client=mock_http_client,
            args={
                "title": "User prefers terse replies",
                "description": "Keep answers short.",
                "kind": "memory",
                "subject": "user:preferences",
                "scope": "shared-with-user",
                "provenance": "conversation 2026-05-30",
            },
            context={},
            default_priority="medium",
        )

        payload = mock_http_client.post.call_args[1]["json"]
        # Kind is a real field, not encoded as a tag.
        assert payload["kind"] == "memory"
        assert "memory" not in payload.get("tags", [])
        # subject/scope/provenance are structured fields, not description preamble.
        assert payload["subject"] == "user:preferences"
        assert payload["scope"] == "shared-with-user"
        assert payload["provenance"] == "conversation 2026-05-30"
        assert payload["description"] == "Keep answers short."
        assert "Subject:" not in payload["description"]

    @pytest.mark.asyncio
    async def test_create_task_defaults_kind_task_without_subject_fields(
        self, mock_http_client, mock_http_response
    ):
        mock_http_client.post.return_value = mock_http_response(
            json_data={"id": "t-1", "title": "Plain task"}
        )

        await create_task(
            client=mock_http_client,
            args={"title": "Plain task"},
            context={},
            default_priority="medium",
        )

        payload = mock_http_client.post.call_args[1]["json"]
        assert payload["kind"] == "task"
        assert "subject" not in payload
        assert "scope" not in payload
        assert "provenance" not in payload


class TestStdioListSegmentsByKind:
    """The stdio list tool defaults to kind=task and exposes an escape hatch."""

    @pytest.mark.asyncio
    async def test_list_defaults_to_kind_task(self, mock_http_client, mock_http_response):
        mock_http_client.get.return_value = mock_http_response(json_data={"tasks": [], "total": 0})

        await list_tasks(client=mock_http_client, args={}, default_limit=10)

        params = mock_http_client.get.call_args[1]["params"]
        assert params["kind"] == "task"

    @pytest.mark.asyncio
    async def test_list_explicit_kind_overrides_default(self, mock_http_client, mock_http_response):
        mock_http_client.get.return_value = mock_http_response(json_data={"tasks": [], "total": 0})

        await list_tasks(client=mock_http_client, args={"kind": "memory"}, default_limit=10)

        params = mock_http_client.get.call_args[1]["params"]
        assert params["kind"] == "memory"

    @pytest.mark.asyncio
    async def test_list_all_kinds_disables_default_filter(
        self, mock_http_client, mock_http_response
    ):
        mock_http_client.get.return_value = mock_http_response(json_data={"tasks": [], "total": 0})

        await list_tasks(client=mock_http_client, args={"all_kinds": True}, default_limit=10)

        params = mock_http_client.get.call_args[1]["params"]
        assert "kind" not in params

    @pytest.mark.asyncio
    async def test_list_memory_filters_kind_memory(self, mock_http_client, mock_http_response):
        mock_http_client.get.return_value = mock_http_response(
            json_data={
                "tasks": [
                    {"id": "m-1", "kind": "memory", "subject": "user:preferences"},
                    {"id": "m-2", "kind": "memory", "subject": "project:hopper"},
                ],
                "total": 2,
            }
        )

        result = await list_memory(
            client=mock_http_client,
            args={"subject": "user:preferences"},
            default_limit=10,
        )

        params = mock_http_client.get.call_args[1]["params"]
        assert params["kind"] == "memory"
        # subject filter applied on the structured field, not a tag.
        assert result["total"] == 1
        assert result["memories"][0]["id"] == "m-1"


class TestStdioToolSchemas:
    """Tool definitions advertise the kind-based surface."""

    def test_create_schema_exposes_memory_fields(self):
        create = next(t for t in get_task_tools() if t.name == "hopper_create_task")
        props = create.inputSchema["properties"]
        assert "kind" in props
        assert "subject" in props
        assert "scope" in props
        assert "provenance" in props

    def test_list_schema_exposes_kind_and_all_kinds(self):
        lst = next(t for t in get_task_tools() if t.name == "hopper_list_tasks")
        props = lst.inputSchema["properties"]
        assert "kind" in props
        assert "all_kinds" in props

    def test_list_memory_tool_exists(self):
        names = [t.name for t in get_task_tools()]
        assert "hopper_list_memory" in names


# ---------------------------------------------------------------------------
# SSE server — end-to-end against a kind-aware LocalClient (markdown store)
# ---------------------------------------------------------------------------


@pytest.fixture
def sse_local_client(tmp_path, monkeypatch):
    """Point the SSE tools at a throwaway markdown-backed LocalClient."""
    import hopper.api.mcp_sse as sse
    from hopper.cli.local_client import LocalClient

    client = LocalClient(tmp_path / ".hopper")

    class _Ctx:
        def __enter__(self):
            return client

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(sse, "_get_client", lambda: _Ctx())
    return sse


class TestSseMemoryFirstClass:
    def test_create_memory_has_real_kind_and_roundtrips_structured_fields(self, sse_local_client):
        sse = sse_local_client

        res = sse.hopper_create_memory(
            title="User prefers terse replies",
            content="Keep answers short.",
            subject="user:preferences",
            scope="shared-with-user",
            provenance="conversation 2026-05-30",
        )
        assert res["status"] == "created"
        mem = res["memory"]

        # Kind is first-class — not a tag.
        assert mem["kind"] == "memory"
        assert "memory" not in (mem.get("tags") or [])
        # Structured fields round-trip, not buried in description preamble.
        assert mem["subject"] == "user:preferences"
        assert mem["scope"] == "shared-with-user"
        assert mem["provenance"] == "conversation 2026-05-30"
        assert mem["description"] == "Keep answers short."

    def test_list_memory_retrieves_by_kind(self, sse_local_client):
        sse = sse_local_client
        sse.hopper_create_memory(
            title="m", content="c", subject="user:preferences", scope="private"
        )

        out = sse.hopper_list_memory()
        assert out["status"] == "success"
        assert out["count"] == 1
        assert out["memories"][0]["kind"] == "memory"

        # subject filter works against the structured field.
        assert sse.hopper_list_memory(subject="user:preferences")["count"] == 1
        assert sse.hopper_list_memory(subject="project:nope")["count"] == 0


class TestSseListSegmentsByKind:
    def test_list_tasks_excludes_memory_by_default(self, sse_local_client):
        sse = sse_local_client
        sse.hopper_create_task(title="real task", kind="task")
        sse.hopper_create_memory(title="a memory", content="x", subject="self", scope="private")

        default = sse.hopper_list_tasks()
        assert default["status"] == "success"
        kinds = {t.get("kind", "task") for t in default["tasks"]}
        assert kinds == {"task"}
        titles = {t["title"] for t in default["tasks"]}
        assert "a memory" not in titles
        assert "real task" in titles

    def test_all_kinds_escape_hatch_reveals_memory(self, sse_local_client):
        sse = sse_local_client
        sse.hopper_create_task(title="real task", kind="task")
        sse.hopper_create_memory(title="a memory", content="x", subject="self", scope="private")

        revealed = sse.hopper_list_tasks(all_kinds=True)
        titles = {t["title"] for t in revealed["tasks"]}
        assert "a memory" in titles
        assert "real task" in titles

    def test_kind_filter_selects_memory(self, sse_local_client):
        sse = sse_local_client
        sse.hopper_create_task(title="real task", kind="task")
        sse.hopper_create_memory(title="a memory", content="x", subject="self", scope="private")

        only_mem = sse.hopper_list_tasks(kind="memory")
        titles = {t["title"] for t in only_mem["tasks"]}
        assert titles == {"a memory"}

    def test_create_task_does_not_inject_kind_tag(self, sse_local_client):
        sse = sse_local_client
        res = sse.hopper_create_task(title="an idea", kind="idea")
        task = res["task"]
        assert task["kind"] == "idea"
        # The legacy behaviour injected the kind as a tag; it must not anymore.
        assert "idea" not in (task.get("tags") or [])
