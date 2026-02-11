"""
Abstract storage backend interfaces.

Defines the contract for storage implementations.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass
class StorageConfig:
    """Storage configuration."""

    mode: str = "local"  # local, server, embedded
    path: Path | None = None  # For local/embedded
    server_url: str | None = None  # For server mode
    api_key: str | None = None

    # Sync settings
    sync_enabled: bool = False
    sync_patterns: bool = True
    sync_episodes: bool = False  # Privacy: off by default

    # Instance identity
    instance_id: str = "local"
    instance_name: str = "Local Hopper"

    @classmethod
    def local(cls, path: Path | None = None) -> "StorageConfig":
        """Create local storage config."""
        return cls(
            mode="local",
            path=path or Path.home() / ".hopper",
        )

    @classmethod
    def embedded(cls, path: Path) -> "StorageConfig":
        """Create embedded storage config (project-local)."""
        return cls(
            mode="embedded",
            path=path,
        )

    @classmethod
    def server(cls, url: str, api_key: str | None = None) -> "StorageConfig":
        """Create server storage config."""
        return cls(
            mode="server",
            server_url=url,
            api_key=api_key,
        )


class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def initialize(self) -> None:
        """Initialize storage (create directories, etc.)."""
        ...

    @abstractmethod
    def get_config(self) -> StorageConfig:
        """Get storage configuration."""
        ...

    @property
    @abstractmethod
    def is_local(self) -> bool:
        """Check if this is a local storage backend."""
        ...


@runtime_checkable
class TaskStore(Protocol):
    """Task storage protocol."""

    def get(self, task_id: str) -> Any | None:
        """Get task by ID."""
        ...

    def save(self, task: Any) -> None:
        """Save task."""
        ...

    def delete(self, task_id: str) -> bool:
        """Delete task. Returns True if deleted."""
        ...

    def list(self, **filters: Any) -> list[Any]:
        """List tasks with optional filters."""
        ...

    def search(self, query: str, **filters: Any) -> list[Any]:
        """Search tasks by text query."""
        ...

    def count(self, **filters: Any) -> int:
        """Count tasks matching filters."""
        ...


@runtime_checkable
class EpisodeStore(Protocol):
    """Episode storage protocol."""

    def record(
        self,
        task_id: str,
        chosen_instance: str,
        confidence: float,
        strategy: str = "rules",
        factors: dict[str, Any] | None = None,
    ) -> Any:
        """Record a routing episode."""
        ...

    def get_for_task(self, task_id: str) -> Any | None:
        """Get episode for a task."""
        ...

    def mark_outcome(
        self,
        task_id: str,
        success: bool,
        duration: str | None = None,
    ) -> None:
        """Mark episode outcome."""
        ...

    def list_recent(self, days: int = 7, limit: int = 100) -> list[Any]:
        """List recent episodes."""
        ...

    def get_statistics(self) -> dict[str, Any]:
        """Get episode statistics."""
        ...


@runtime_checkable
class PatternStore(Protocol):
    """Pattern storage protocol."""

    def get(self, pattern_id: str) -> Any | None:
        """Get pattern by ID."""
        ...

    def save(self, pattern: Any) -> None:
        """Save pattern."""
        ...

    def delete(self, pattern_id: str) -> bool:
        """Delete pattern."""
        ...

    def list(self, active_only: bool = True) -> list[Any]:
        """List patterns."""
        ...

    def find_matching(
        self,
        tags: list[str] | None = None,
        text: str | None = None,
        priority: str | None = None,
    ) -> list[tuple[Any, float]]:
        """Find patterns matching criteria. Returns (pattern, score) pairs."""
        ...

    def record_usage(self, pattern_id: str, success: bool) -> None:
        """Record pattern usage."""
        ...


@runtime_checkable
class FeedbackStore(Protocol):
    """Feedback storage protocol."""

    def save(
        self,
        task_id: str,
        was_good_match: bool,
        routing_feedback: str | None = None,
        should_have_routed_to: str | None = None,
        quality_score: float | None = None,
        complexity_rating: int | None = None,
        required_rework: bool | None = None,
        notes: str | None = None,
    ) -> Any:
        """Save feedback for a task."""
        ...

    def get(self, task_id: str) -> Any | None:
        """Get feedback for a task."""
        ...

    def list(self, good_only: bool | None = None, limit: int = 100) -> list[Any]:
        """List feedback records."""
        ...

    def get_accuracy_stats(self, days: int = 30) -> dict[str, Any]:
        """Get routing accuracy statistics."""
        ...
