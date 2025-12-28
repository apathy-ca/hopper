"""
MCP server context management.

Handles server context including current user/session tracking,
active project context, recent tasks cache, and conversation state.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .config import MCPServerConfig

logger = logging.getLogger(__name__)


class ServerContext:
    """Manages MCP server context and session state."""

    def __init__(self, config: MCPServerConfig):
        """Initialize server context.

        Args:
            config: MCP server configuration
        """
        self.config = config
        self._user: str | None = None
        self._active_project: str | None = None
        self._recent_tasks: dict[str, tuple[str, datetime]] = {}  # task_id -> (title, timestamp)
        self._conversation_metadata: dict[str, Any] = {}
        self._context_file: Path | None = None

        if self.config.enable_context_persistence:
            self._context_file = Path.home() / ".hopper" / "mcp_context.json"
            self._load_context()

    def set_user(self, user: str) -> None:
        """Set the current user.

        Args:
            user: User identifier
        """
        self._user = user
        self._save_context()

    def get_user(self) -> str | None:
        """Get the current user.

        Returns:
            User identifier or None
        """
        return self._user

    def set_active_project(self, project: str) -> None:
        """Set the active project context.

        Args:
            project: Project identifier
        """
        self._active_project = project
        self._save_context()

    def get_active_project(self) -> str | None:
        """Get the active project.

        Returns:
            Project identifier or None
        """
        return self._active_project

    def add_recent_task(self, task_id: str, title: str) -> None:
        """Add a task to recent tasks cache.

        Args:
            task_id: Task identifier
            title: Task title
        """
        self._recent_tasks[task_id] = (title, datetime.now())
        self._cleanup_old_tasks()
        self._save_context()

    def get_recent_tasks(self, limit: int = 5) -> list[dict[str, str]]:
        """Get recent tasks.

        Args:
            limit: Maximum number of tasks to return

        Returns:
            List of recent tasks with id and title
        """
        self._cleanup_old_tasks()

        # Sort by timestamp (most recent first)
        sorted_tasks = sorted(self._recent_tasks.items(), key=lambda x: x[1][1], reverse=True)

        return [{"id": task_id, "title": title} for task_id, (title, _) in sorted_tasks[:limit]]

    def set_conversation_metadata(self, key: str, value: Any) -> None:
        """Set conversation metadata.

        Args:
            key: Metadata key
            value: Metadata value
        """
        self._conversation_metadata[key] = value
        self._save_context()

    def get_conversation_metadata(self, key: str) -> Any | None:
        """Get conversation metadata.

        Args:
            key: Metadata key

        Returns:
            Metadata value or None
        """
        return self._conversation_metadata.get(key)

    def get_context(self) -> dict[str, Any]:
        """Get complete context for tool calls.

        Returns:
            Context dictionary with user, project, and recent tasks
        """
        context = {}

        if self._user:
            context["user"] = self._user

        if self._active_project:
            context["active_project"] = self._active_project

        recent_tasks = self.get_recent_tasks()
        if recent_tasks:
            context["recent_tasks"] = recent_tasks

        if self._conversation_metadata:
            context["conversation"] = self._conversation_metadata

        return context

    def clear(self) -> None:
        """Clear all context."""
        self._user = None
        self._active_project = None
        self._recent_tasks.clear()
        self._conversation_metadata.clear()
        self._save_context()

    def _cleanup_old_tasks(self) -> None:
        """Remove tasks older than the cache TTL."""
        if not self.config.enable_context_persistence:
            return

        cutoff = datetime.now() - timedelta(seconds=self.config.context_cache_ttl)
        old_task_ids = [
            task_id for task_id, (_, timestamp) in self._recent_tasks.items() if timestamp < cutoff
        ]

        for task_id in old_task_ids:
            del self._recent_tasks[task_id]

    def _save_context(self) -> None:
        """Save context to disk."""
        if not self.config.enable_context_persistence or not self._context_file:
            return

        try:
            # Ensure directory exists
            self._context_file.parent.mkdir(parents=True, exist_ok=True)

            # Convert timestamps to ISO format for JSON serialization
            serializable_tasks = {
                task_id: {"title": title, "timestamp": timestamp.isoformat()}
                for task_id, (title, timestamp) in self._recent_tasks.items()
            }

            context_data = {
                "user": self._user,
                "active_project": self._active_project,
                "recent_tasks": serializable_tasks,
                "conversation_metadata": self._conversation_metadata,
                "last_updated": datetime.now().isoformat(),
            }

            with open(self._context_file, "w") as f:
                json.dump(context_data, f, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save context: {e}")

    def _load_context(self) -> None:
        """Load context from disk."""
        if not self._context_file or not self._context_file.exists():
            return

        try:
            with open(self._context_file) as f:
                context_data = json.load(f)

            self._user = context_data.get("user")
            self._active_project = context_data.get("active_project")
            self._conversation_metadata = context_data.get("conversation_metadata", {})

            # Restore recent tasks with timestamp conversion
            recent_tasks = context_data.get("recent_tasks", {})
            self._recent_tasks = {
                task_id: (data["title"], datetime.fromisoformat(data["timestamp"]))
                for task_id, data in recent_tasks.items()
            }

            # Clean up old tasks after loading
            self._cleanup_old_tasks()

            logger.info("Context loaded successfully")

        except Exception as e:
            logger.warning(f"Failed to load context: {e}")

    async def cleanup(self) -> None:
        """Clean up context resources."""
        # Save final state before cleanup
        self._save_context()
