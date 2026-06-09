"""Tests for first-class kind on the SSE MCP server's upstream-backed path.

The SSE server resolves to one of two clients per session:
  - LocalClient (fully kind-aware) — covered end-to-end in
    tests/mcp/test_kind_first_class.py;
  - UpstreamNamespaceClient (backed by UpstreamStorage) — covered here.

UpstreamNamespaceClient sets a real `kind` (plus subject/scope/provenance) on
create. Those fields are real columns on SyncTask (hopper/upstream/protocol.py),
so they persist through UpstreamStorage and round-trip on read — no kind-tag
injection. The list path still tolerates legacy tag-encoded records (created
before the kind field existed and not yet migrated).
"""

import pytest

from hopper.api.mcp_sse import UpstreamNamespaceClient
from hopper.upstream.storage import UpstreamStorage


@pytest.fixture
def upstream_client(tmp_path):
    storage = UpstreamStorage(storage_path=tmp_path / "upstream-data")
    return UpstreamNamespaceClient("test-ns", storage)


class TestUpstreamCreatePersistsKind:
    def test_create_sets_real_kind_and_structured_fields(self, upstream_client):
        result = upstream_client.create_task(
            {
                "title": "User prefers terse replies",
                "description": "Keep answers short.",
                "kind": "memory",
                "subject": "user:preferences",
                "scope": "shared-with-user",
                "provenance": "conversation 2026-05-30",
            }
        )
        assert result["kind"] == "memory"
        assert result["subject"] == "user:preferences"
        assert result["scope"] == "shared-with-user"
        assert result["provenance"] == "conversation 2026-05-30"
        assert result["description"] == "Keep answers short."
        # No kind-tag injection — kind is a real field, not a tag.
        assert "memory" not in result["tags"]

    def test_kind_and_structured_fields_roundtrip_through_storage(self, upstream_client):
        created = upstream_client.create_task(
            {
                "title": "a memory",
                "kind": "memory",
                "subject": "user:preferences",
                "scope": "private",
                "provenance": "observation",
            }
        )
        # Read back fresh from UpstreamStorage (deserializes via SyncTask).
        got = upstream_client.get_task(created["id"])
        assert got["kind"] == "memory"
        assert got["subject"] == "user:preferences"
        assert got["scope"] == "private"
        assert got["provenance"] == "observation"
        assert "memory" not in (got.get("tags") or [])


class TestUpstreamListSegmentsByKind:
    def test_list_defaults_and_kind_filter(self, upstream_client):
        upstream_client.create_task({"title": "real task", "kind": "task"})
        upstream_client.create_task({"title": "a memory", "kind": "memory", "subject": "self"})

        # kind="task" excludes the memory.
        titles = {t["title"] for t in upstream_client.list_tasks(kind="task")}
        assert "real task" in titles
        assert "a memory" not in titles

        # kind="memory" selects it via the real kind field.
        assert {m["title"] for m in upstream_client.list_tasks(kind="memory")} == {"a memory"}

        # No kind filter → everything.
        assert len(upstream_client.list_tasks()) == 2

    def test_list_finds_legacy_tag_encoded_memory(self, upstream_client):
        # A record created before the kind field existed: kind unset, memory
        # encoded as a tag. The kind="memory" filter must still find it.
        upstream_client.create_task({"title": "legacy memory", "tags": ["memory"]})
        # Simulate "no kind" by confirming the tag fallback path matches.
        found = upstream_client.list_tasks(kind="memory")
        assert any(m["title"] == "legacy memory" for m in found)
