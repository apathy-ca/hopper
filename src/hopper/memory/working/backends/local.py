"""
Local in-memory backend for working memory.

Simple dict-based storage with TTL support.
"""

import fnmatch
import threading
import time
from typing import Any

from .base import BaseBackend


class LocalBackend(BaseBackend):
    """
    In-memory backend using a dictionary.

    Thread-safe with TTL support.
    """

    def __init__(self, max_entries: int = 10000):
        """
        Initialize the local backend.

        Args:
            max_entries: Maximum number of entries (LRU eviction when exceeded)
        """
        self._store: dict[str, tuple[dict[str, Any], float | None]] = {}
        self._lock = threading.RLock()
        self._max_entries = max_entries

    def get(self, key: str) -> dict[str, Any] | None:
        """Get a value by key."""
        with self._lock:
            if key not in self._store:
                return None

            value, expires_at = self._store[key]

            # Check expiration
            if expires_at is not None and time.time() > expires_at:
                del self._store[key]
                return None

            return value

    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> bool:
        """Set a value with optional TTL."""
        with self._lock:
            # Calculate expiration time
            expires_at = time.time() + ttl if ttl is not None else None

            # Evict if at capacity
            if len(self._store) >= self._max_entries and key not in self._store:
                self._evict_oldest()

            self._store[key] = (value, expires_at)
            return True

    def delete(self, key: str) -> bool:
        """Delete a key."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        with self._lock:
            if key not in self._store:
                return False

            _, expires_at = self._store[key]
            if expires_at is not None and time.time() > expires_at:
                del self._store[key]
                return False

            return True

    def clear(self) -> int:
        """Clear all entries."""
        with self._lock:
            count = len(self._store)
            self._store.clear()
            return count

    def clear_expired(self) -> int:
        """Remove expired entries."""
        with self._lock:
            now = time.time()
            expired_keys = [
                key
                for key, (_, expires_at) in self._store.items()
                if expires_at is not None and now > expires_at
            ]
            for key in expired_keys:
                del self._store[key]
            return len(expired_keys)

    def keys(self, pattern: str = "*") -> list[str]:
        """Get keys matching a pattern."""
        with self._lock:
            # First clear expired
            self.clear_expired()

            if pattern == "*":
                return list(self._store.keys())

            return [key for key in self._store.keys() if fnmatch.fnmatch(key, pattern)]

    def size(self) -> int:
        """Get the number of entries."""
        with self._lock:
            self.clear_expired()
            return len(self._store)

    def _evict_oldest(self) -> None:
        """Evict the oldest entry (simple LRU approximation)."""
        if self._store:
            # Remove first key (oldest insertion)
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]

    def get_stats(self) -> dict[str, Any]:
        """Get backend statistics."""
        with self._lock:
            now = time.time()
            total = len(self._store)
            expired = sum(
                1
                for _, expires_at in self._store.values()
                if expires_at is not None and now > expires_at
            )
            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
                "max_entries": self._max_entries,
                "utilization": total / self._max_entries if self._max_entries > 0 else 0,
            }
