"""Regression tests for MCP-over-SSE instance-scope resolution.

These guard a TRUST-CRITICAL bug: when the per-process in-memory session map
(`_session_instances`) misses for an authenticated DID — e.g. a request routed
to a uvicorn worker that did not handle the SSE connect / switch_instance, or a
stale-session reroute that never populated the cache — `_get_client()` used to
silently fall back to LocalClient (the server's own "local" instance). A user
who had switched to e.g. "Rosetta_Program" would then read the WRONG instance's
data with no error.

The fix:
  * On a cache miss, recover the instance from the durable DID registry
    (`did_registry.get_last_instance`), repopulate the cache, and serve the
    correct UpstreamNamespaceClient.
  * If an authenticated DID is associated with an upstream instance but no
    instance can be resolved, refuse to serve local data and raise an error
    that tells the caller to run hopper_switch_instance.
  * Genuinely local / anonymous sessions still get LocalClient.
"""

import pytest

import hopper.upstream.server as upstream_server
from hopper.api import mcp_sse
from hopper.api.mcp_sse import (
    LocalClient,
    UpstreamNamespaceClient,
    _get_client,
    _session_did,
    _session_id,
    _session_instances,
)
from hopper.cli.local_client import LocalClientError
from hopper.upstream.storage import UpstreamStorage


@pytest.fixture
def upstream_storage(tmp_path, monkeypatch):
    """Configure the module-level upstream storage with a temp path."""
    storage = UpstreamStorage(storage_path=tmp_path / "upstream-data")
    monkeypatch.setattr(upstream_server, "_storage", storage)
    return storage


@pytest.fixture
def clean_session(monkeypatch):
    """Provide an isolated, empty session map and reset contextvars after."""
    monkeypatch.setattr(mcp_sse, "_session_instances", {}, raising=True)
    sid_token = _session_id.set(None)
    did_token = _session_did.set(None)
    yield
    _session_id.reset(sid_token)
    _session_did.reset(did_token)


class TestDidAffinityRecovery:
    def test_cache_miss_recovers_instance_from_did_registry(
        self, upstream_storage, clean_session
    ):
        """Session-map MISS + registry last_instance → UpstreamNamespaceClient,
        not LocalClient, and the session cache is repopulated."""
        did = "did:key:zRosetta"
        upstream_storage.did_registry.update_last_instance(did, "Rosetta_Program")

        sid = "session-routed-to-other-worker"
        _session_id.set(sid)
        _session_did.set(did)

        # Sanity: nothing in the in-memory map for this session.
        assert sid not in mcp_sse._session_instances

        client = _get_client()

        assert isinstance(client, UpstreamNamespaceClient)
        assert not isinstance(client, LocalClient)
        assert client._ns == "Rosetta_Program"

        # Cache repopulated so subsequent calls hit the fast path.
        assert mcp_sse._session_instances[sid] == (None, "Rosetta_Program")

    def test_authenticated_multi_instance_did_without_resolution_errors(
        self, upstream_storage, clean_session
    ):
        """A DID associated with an upstream instance but with no resolvable
        instance must NOT silently get local data — it gets a switch-instance
        error."""
        did = "did:key:zHasAffinity"
        # The DID is known to be upstream-scoped (has affinity)...
        upstream_storage.did_registry.update_last_instance(did, "Rosetta_Program")

        sid = "session-with-affinity"
        _session_id.set(sid)
        _session_did.set(did)

        # ...but simulate the registry being unable to return it at read time
        # (e.g. transient) while association detection still flags the DID.
        # Force the resolve path to find nothing yet keep the association.
        original_get_last = upstream_storage.did_registry.get_last_instance

        calls = {"n": 0}

        def flaky_get_last(d):
            calls["n"] += 1
            # First call: resolution (return None to simulate miss).
            # Later call: association check (return the instance → associated).
            return None if calls["n"] == 1 else original_get_last(d)

        upstream_storage.did_registry.get_last_instance = flaky_get_last

        with pytest.raises(LocalClientError) as exc:
            _get_client()

        assert "switch_instance" in str(exc.value.message).lower() or \
            "instance" in str(exc.value.message).lower()
        # Did NOT fall back to local data.
        assert "local" not in str(exc.value.message).lower() or \
            "wrong" in str(exc.value.message).lower()

    def test_anonymous_session_still_returns_local_client(self, clean_session):
        """No DID and no upstream association → LocalClient (no regression)."""
        # No upstream storage configured, no DID set.
        _session_id.set("anon-session")
        _session_did.set(None)

        client = _get_client()
        assert isinstance(client, LocalClient)

    def test_did_without_any_association_returns_local_client(
        self, upstream_storage, clean_session
    ):
        """A DID that has neither registry affinity nor instance-scoped tokens
        is treated as local — LocalClient, no error."""
        _session_id.set("unknown-did-session")
        _session_did.set("did:key:zNeverSeen")

        client = _get_client()
        assert isinstance(client, LocalClient)
