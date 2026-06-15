"""SSE and Streamable HTTP transports for the MCP server.

Wires the FastMCP server (defined in ``hopper.api.mcp_sse``) up to the two
HTTP transports MCP clients use: the legacy SSE transport (``/mcp/sse/``)
and the Streamable HTTP transport (``/mcp``, MCP 1.26+).
"""

import logging
import uuid

from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import MCP_SESSION_ID_HEADER
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Route

from hopper.api.mcp_sse.auth import _check_auth

logger = logging.getLogger(__name__)


def create_sse_server():
    """Create Starlette app for MCP SSE transport (legacy path /mcp/sse/).

    Returns a Starlette application mounting the SSE transport at /sse/
    and the POST message endpoint at /messages/.
    """
    from hopper.api import mcp_sse as _sse

    transport = SseServerTransport("/messages/")

    async def handle_sse(request):
        auth_error, auth_id, instance_path, instance_name = _check_auth(request)
        if auth_error:
            return auth_error

        sid = str(uuid.uuid4())
        _sse._session_instances[sid] = (instance_path, instance_name)
        # Persist the instance for this DID (for future reconnections)
        if auth_id and instance_name:
            try:
                from hopper.upstream.server import get_storage

                get_storage().did_registry.update_last_instance(auth_id, instance_name)
            except Exception:
                pass  # Best effort
        sid_token = _sse._session_id.set(sid)
        did_token = _sse._session_did.set(auth_id)
        try:
            async with transport.connect_sse(
                request.scope, request.receive, request._send
            ) as streams:
                await _sse.mcp._mcp_server.run(
                    streams[0],
                    streams[1],
                    _sse.mcp._mcp_server.create_initialization_options(),
                )
        finally:
            _sse._session_instances.pop(sid, None)
            _sse._session_id.reset(sid_token)
            _sse._session_did.reset(did_token)

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


# Module-level session manager — started by the main app lifespan (see app.py)
_streamable_session_manager: StreamableHTTPSessionManager | None = None
# Stateless fallback — used for stale-session reconnects so valid requests succeed
# without 400/404. Each request gets its own ephemeral transport; no session ID
# is required or returned, so the client can keep using whatever ID it has.
_stateless_session_manager: StreamableHTTPSessionManager | None = None


def get_streamable_session_manager() -> StreamableHTTPSessionManager:
    """Return the module-level Streamable HTTP session manager, creating it if needed."""
    global _streamable_session_manager
    if _streamable_session_manager is None:
        from hopper.api import mcp_sse as _sse

        _streamable_session_manager = StreamableHTTPSessionManager(
            app=_sse.mcp._mcp_server,
            json_response=True,
            stateless=False,
        )
    return _streamable_session_manager


def get_stateless_session_manager() -> StreamableHTTPSessionManager:
    """Return the stateless session manager used for stale-session reconnect fallback."""
    global _stateless_session_manager
    if _stateless_session_manager is None:
        from hopper.api import mcp_sse as _sse

        _stateless_session_manager = StreamableHTTPSessionManager(
            app=_sse.mcp._mcp_server,
            json_response=True,
            stateless=True,
        )
    return _stateless_session_manager


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

        from hopper.api import mcp_sse as _sse

        request = StarletteRequest(scope, receive)

        # Read body once for auth (may be empty for GET/DELETE)
        body = await request.body()

        auth_error, auth_id, instance_path, instance_name = _check_auth(request, body)
        if auth_error:
            await auth_error(scope, receive, send)
            return

        # Session routing. Three cases:
        # 1. Known session ID → normal stateful path.
        # 2. No session ID (fresh initialize) → normal stateful path (manager
        #    creates a new session).
        # 3. Unknown/stale session ID → route through the stateless manager so
        #    the request succeeds without 400 or 404. The stateless manager
        #    creates an ephemeral transport per request; since all hopper tools
        #    are side-effect-free with respect to session state, this is safe.
        #    We do NOT strip the session ID here — the stateless manager ignores
        #    it, and leaving it in the scope means initialize requests also work
        #    (the stateless transport returns no session ID, so the client will
        #    get a clean response and can establish a new stateful session on
        #    its next initialize).
        sm = get_streamable_session_manager()
        raw_sid = request.headers.get(MCP_SESSION_ID_HEADER)
        _use_stateless = raw_sid is not None and raw_sid not in sm._server_instances
        if _use_stateless:
            try:
                import json as _json

                _method = _json.loads(body).get("method", "unknown")
            except Exception:
                _method = "unknown"
            logger.info(
                "MCP session %s not found, method=%s — handling statelessly", raw_sid, _method
            )

        sid = raw_sid or str(uuid.uuid4())

        # On first touch for a session, record the authenticated instance
        if sid not in _sse._session_instances:
            _sse._session_instances[sid] = (instance_path, instance_name)
            # Persist the instance for this DID (for future reconnections)
            if auth_id and instance_name:
                try:
                    from hopper.upstream.server import get_storage

                    get_storage().did_registry.update_last_instance(auth_id, instance_name)
                except Exception:
                    pass  # Best effort - storage may not be configured

        sid_token = _sse._session_id.set(sid)
        did_token = _sse._session_did.set(auth_id)

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
                    await send(
                        {
                            "type": "http.response.body",
                            "body": _SSE_KEEPALIVE_PING,
                            "more_body": True,
                        }
                    )
                except Exception:
                    break

        import anyio

        active_sm = get_stateless_session_manager() if _use_stateless else sm
        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(keepalive_loop)
                await active_sm.handle_request(scope, replay_receive, tracked_send)
                tg.cancel_scope.cancel()
        finally:
            _sse._session_id.reset(sid_token)
            _sse._session_did.reset(did_token)
            # Don't pop _session_instances here — the session persists across requests


def create_streamable_http_server() -> _StreamableHTTPASGIHandler:
    """Return auth-gated ASGI handler for MCP Streamable HTTP transport (MCP 1.26+).

    Returns a raw ASGI callable that can be mounted directly on FastAPI with
    app.mount("/mcp", create_streamable_http_server()).

    The underlying StreamableHTTPSessionManager must be started via its run()
    context manager before requests arrive — done in the main app's lifespan.
    """
    return _StreamableHTTPASGIHandler()
