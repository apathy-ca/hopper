"""Author-location resolution.

Phase 4b. Every write carries a ``source`` value that becomes
``author_location`` in the revision history — a per-write signal of
"where did this write come from." Prior art set ``source`` to bare
``"cli"`` or ``"mcp"``; that erased the useful distinction between
ember-cli, jay-laptop-cli, phone-claude, waypoint-skill, audit-agent,
etc. This utility picks a richer value.

Precedence (highest first):

1. ``HOPPER_LOCATION`` env var — explicit override. Used by shells
   that know their context (e.g. exported in the waypoint-skill, on
   phone-claude, in the audit-agent's unit file).
2. ``override`` argument — passed by a caller that knows better than
   env (e.g. an MCP handler that carries per-request context).
3. Transport default:
   - MCP → ``mcp:<transport>`` (the ``transport`` arg, if given).
   - CLI → ``<hostname>-cli``.
4. Final fallback: ``"cli"`` (matches pre-Phase-4b behavior).

The returned string goes straight into the task's ``source`` field and
thence into ``revisions.author_location``. Keep it human-readable; it
shows up in ``hopper task history``.
"""

from __future__ import annotations

import os
import socket
from typing import Literal


def _short_hostname() -> str:
    """Return the short hostname (no domain), lowercased, or empty on failure."""
    try:
        return socket.gethostname().split(".")[0].lower()
    except Exception:  # noqa: BLE001
        return ""


def resolve_location(
    *,
    override: str | None = None,
    transport: Literal["cli", "mcp"] | None = "cli",
) -> str:
    """Resolve the author_location token for a write.

    Args:
        override: Caller-provided value. Highest precedence after env.
        transport: The invocation surface. "cli" produces <host>-cli
            by default; "mcp" produces mcp:<transport-id> and callers
            are expected to pass override= with richer context.
    """
    env = os.getenv("HOPPER_LOCATION")
    if env:
        return env.strip()

    if override:
        return override.strip()

    if transport == "mcp":
        return "mcp"

    host = _short_hostname()
    return f"{host}-cli" if host else "cli"
