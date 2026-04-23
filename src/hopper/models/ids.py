"""ULID generation for revision and record IDs.

ULIDs are 26-character Crockford base32 strings: 48-bit timestamp + 80-bit
randomness. They sort lexicographically by creation time and avoid the
coordination cost of UUIDs.

Inline implementation to avoid adding a dependency for ~20 lines of code.
"""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """Generate a new 26-character ULID string."""
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = int.from_bytes(os.urandom(10), "big")
    value = (ts_ms << 80) | rand
    out = [""] * 26
    for i in range(25, -1, -1):
        out[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(out)
