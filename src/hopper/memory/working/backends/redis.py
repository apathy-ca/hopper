"""
Redis backend for working memory.

Provides persistence across restarts and shared state across processes.
"""

import json
from typing import Any

try:
    import redis
except ImportError:
    redis = None  # type: ignore

from .base import BaseBackend


class RedisBackend(BaseBackend):
    """
    Redis-backed working memory.

    Provides persistence and shared state.
    Requires redis package: pip install redis
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        key_prefix: str = "hopper:working:",
    ):
        """
        Initialize the Redis backend.

        Args:
            url: Redis connection URL
            key_prefix: Prefix for all keys
        """
        if redis is None:
            raise ImportError(
                "Redis package not installed. Install with: pip install redis"
            )

        self._client = redis.from_url(url, decode_responses=True)
        self._prefix = key_prefix

    def _make_key(self, key: str) -> str:
        """Create full key with prefix."""
        return f"{self._prefix}{key}"

    def get(self, key: str) -> dict[str, Any] | None:
        """Get a value by key."""
        full_key = self._make_key(key)
        value = self._client.get(full_key)
        if value is None:
            return None
        return json.loads(value)

    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> bool:
        """Set a value with optional TTL."""
        full_key = self._make_key(key)
        json_value = json.dumps(value)

        if ttl is not None:
            self._client.setex(full_key, ttl, json_value)
        else:
            self._client.set(full_key, json_value)

        return True

    def delete(self, key: str) -> bool:
        """Delete a key."""
        full_key = self._make_key(key)
        return bool(self._client.delete(full_key))

    def exists(self, key: str) -> bool:
        """Check if a key exists."""
        full_key = self._make_key(key)
        return bool(self._client.exists(full_key))

    def clear(self) -> int:
        """Clear all entries with our prefix."""
        pattern = f"{self._prefix}*"
        keys = self._client.keys(pattern)
        if keys:
            return self._client.delete(*keys)
        return 0

    def clear_expired(self) -> int:
        """
        Remove expired entries.

        Note: Redis handles TTL automatically, so this is a no-op.
        Returns 0 since Redis already cleaned up.
        """
        return 0

    def keys(self, pattern: str = "*") -> list[str]:
        """Get keys matching a pattern."""
        redis_pattern = f"{self._prefix}{pattern}"
        full_keys = self._client.keys(redis_pattern)
        # Strip prefix from returned keys
        prefix_len = len(self._prefix)
        return [k[prefix_len:] for k in full_keys]

    def size(self) -> int:
        """Get the number of entries."""
        pattern = f"{self._prefix}*"
        return len(self._client.keys(pattern))

    def get_stats(self) -> dict[str, Any]:
        """Get backend statistics."""
        info = self._client.info("memory")
        pattern = f"{self._prefix}*"
        our_keys = len(self._client.keys(pattern))

        return {
            "total_entries": our_keys,
            "redis_used_memory": info.get("used_memory_human", "unknown"),
            "redis_connected_clients": info.get("connected_clients", 0),
            "backend": "redis",
        }

    def ping(self) -> bool:
        """Check if Redis is available."""
        try:
            return self._client.ping()
        except Exception:
            return False
