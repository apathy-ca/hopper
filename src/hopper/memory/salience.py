"""Write-time salience flags on memory records, with expiry.

An agent can mark a memory as salient when it writes it ("revisit this"):
``hopper memory add --salient [--salient-for 3d]``. The record then carries
two fields:

  * ``salience`` -- bool, True when flagged;
  * ``salient_until`` -- UTC timestamp after which the flag lapses.

Like a synaptic tag, the flag is temporary: ``is_salient`` returns False once
``salient_until`` has passed. The default window is
``DEFAULT_SALIENCE_WINDOW`` (3 days) -- long enough to span the next few
sessions/consolidation runs, short enough that stale flags don't pile up.

Reinforcement
-------------
A salient record is *reinforced* when something shows it is still in use.
Two events count:

  * a note is added to it (``LocalClient.add_task_note``);
  * another memory record cites it in ``evidence`` (on create, or when an
    update adds the reference).

Reinforcement extends ``salient_until`` to ``now + DEFAULT_SALIENCE_WINDOW``
(see :func:`reinforced_salient_until`). It never shortens the window: a
record flagged ``--salient-for 2w`` keeps its later expiry. It only applies
to records that are *currently* salient -- an unflagged record is never
flagged by reinforcement, and a flag that has already lapsed stays lapsed
(otherwise routine notes would resurrect every stale flag). Edits, reads
and recall do not reinforce.

Consumers (e.g. consolidation prioritising flagged records) should call
``is_salient`` rather than reading ``salience`` directly, so the expiry and
reinforcement rules live in one place.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_SALIENCE_WINDOW = timedelta(days=3)

_UNITS = {"w": "weeks", "d": "days", "h": "hours", "m": "minutes"}
_WINDOW_RE = re.compile(r"(\d+)\s*([wdhm])")


def parse_salience_window(value: str) -> timedelta:
    """Parse '3d', '12h', '90m', '1w', '1d12h' into a timedelta.

    A bare number is days. Raises ValueError on anything else or on zero.
    """
    text = (value or "").strip().lower()
    if text.isdigit():
        window = timedelta(days=int(text))
    else:
        parts = _WINDOW_RE.findall(text)
        if not parts or _WINDOW_RE.sub("", text).strip():
            raise ValueError(f"Cannot parse salience window: {value!r} (try '3d', '12h', '1w')")
        window = timedelta()
        for n, unit in parts:
            window += timedelta(**{_UNITS[unit]: int(n)})
    if window <= timedelta():
        raise ValueError(f"Salience window must be positive: {value!r}")
    return window


def salient_until_from(now: datetime | None = None, window: timedelta | None = None) -> datetime:
    """The expiry timestamp for a flag set at ``now`` (default: utcnow)."""
    now = _as_utc(now) or datetime.now(UTC)
    return now + (window or DEFAULT_SALIENCE_WINDOW)


def is_salient(record: Any, now: datetime | None = None) -> bool:
    """True if ``record`` is flagged salient and the flag has not expired.

    ``record`` may be a LocalTask-like object or a task dict (timestamps as
    datetimes or ISO strings). A flagged record with no ``salient_until``
    falls back to ``created_at + DEFAULT_SALIENCE_WINDOW``; with neither it
    counts as salient.
    """
    if not _get(record, "salience"):
        return False
    now = _as_utc(now) or datetime.now(UTC)
    until = _as_utc(_get(record, "salient_until"))
    if until is None:
        created = _as_utc(_get(record, "created_at"))
        if created is None:
            return True
        until = created + DEFAULT_SALIENCE_WINDOW
    return now < until


def reinforced_salient_until(
    record: Any, now: datetime | None = None, window: timedelta | None = None
) -> datetime | None:
    """New ``salient_until`` for ``record`` after a reinforcing event, or None.

    Returns ``max(current expiry, now + window)`` when the record is currently
    salient and that is later than its current expiry; None when there is
    nothing to do (not flagged, already lapsed, or the existing expiry is
    already later). See the module docstring for which events reinforce.
    """
    now = _as_utc(now) or datetime.now(UTC)
    if not is_salient(record, now):
        return None
    candidate = now + (window or DEFAULT_SALIENCE_WINDOW)
    current = _as_utc(_get(record, "salient_until"))
    if current is not None and current >= candidate:
        return None
    return candidate


def _get(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key, None)


def _as_utc(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)
