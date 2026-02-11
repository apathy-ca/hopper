"""
Base backend interface for working memory.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseBackend(ABC):
    """
    Abstract base class for working memory backends.

    All backends must implement these methods.
    """

    @abstractmethod
    def get(self, key: str) -> dict[str, Any] | None:
        """
        Get a value by key.

        Args:
            key: The key to retrieve

        Returns:
            The stored value or None if not found/expired
        """
        pass

    @abstractmethod
    def set(self, key: str, value: dict[str, Any], ttl: int | None = None) -> bool:
        """
        Set a value with optional TTL.

        Args:
            key: The key to store under
            value: The value to store (must be JSON-serializable)
            ttl: Time-to-live in seconds (None for no expiry)

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete a key.

        Args:
            key: The key to delete

        Returns:
            True if key existed and was deleted
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if a key exists.

        Args:
            key: The key to check

        Returns:
            True if key exists and is not expired
        """
        pass

    @abstractmethod
    def clear(self) -> int:
        """
        Clear all entries.

        Returns:
            Number of entries cleared
        """
        pass

    @abstractmethod
    def clear_expired(self) -> int:
        """
        Remove expired entries.

        Returns:
            Number of entries removed
        """
        pass

    @abstractmethod
    def keys(self, pattern: str = "*") -> list[str]:
        """
        Get keys matching a pattern.

        Args:
            pattern: Glob-style pattern (default "*" for all)

        Returns:
            List of matching keys
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """
        Get the number of entries.

        Returns:
            Number of non-expired entries
        """
        pass
