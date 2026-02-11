"""
Working memory backends.

Provides different storage backends for working memory:
- LocalBackend: In-memory dict with TTL (default)
- RedisBackend: Redis-backed for persistence
"""

from .base import BaseBackend
from .local import LocalBackend

__all__ = [
    "BaseBackend",
    "LocalBackend",
]

# Redis backend is optional - only import if redis is available
try:
    from .redis import RedisBackend

    __all__.append("RedisBackend")
except ImportError:
    pass
