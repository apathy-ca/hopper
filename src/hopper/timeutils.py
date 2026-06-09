"""Shared time helpers.

The storage layers (SQLite shadow, markdown frontmatter, plain ``DateTime``
columns) persist naive UTC datetimes, so the default helper here stays naive
to match what is already on disk. Use :func:`utc_now` for new code that can
handle timezone-aware values.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Current UTC time as a timezone-aware datetime."""
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    """Current UTC time as a naive datetime.

    Drop-in replacement for the deprecated ``datetime.utcnow``: identical
    values, safe to compare with and store alongside existing naive UTC
    timestamps.
    """
    return datetime.now(UTC).replace(tzinfo=None)
