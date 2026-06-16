"""
Hopper storage backends.

Provides pluggable storage for local (markdown) and server (SQL) modes.
"""

from .base import StorageBackend, StorageConfig
from .knowledge import (
    DEFAULT_KNOWLEDGE_SOURCE,
    detect_project_type,
    initialize_knowledge,
    sync_agent_knowledge,
    write_hopper_usage,
)
from .markdown import MarkdownStorage
from .memory import (
    EpisodeMarkdownStore,
    EpisodeStore,
    FeedbackMarkdownStore,
    FeedbackStore,
    PatternMarkdownStore,
    PatternStore,
)
from .sqlite import SQLiteStorage
from .sqlite_memory import EpisodeSQLiteStore, FeedbackSQLiteStore, PatternSQLiteStore
from .tasks import TaskMarkdownStore, TaskStore

__all__ = [
    # Base
    "StorageBackend",
    "StorageConfig",
    # Markdown
    "MarkdownStorage",
    # Task stores
    "TaskStore",
    "TaskMarkdownStore",
    # Memory stores
    "EpisodeStore",
    "PatternStore",
    "FeedbackStore",
    "EpisodeMarkdownStore",
    "PatternMarkdownStore",
    "FeedbackMarkdownStore",
    # SQLite
    "SQLiteStorage",
    "EpisodeSQLiteStore",
    "PatternSQLiteStore",
    "FeedbackSQLiteStore",
    # Knowledge
    "initialize_knowledge",
    "write_hopper_usage",
    "sync_agent_knowledge",
    "detect_project_type",
    "DEFAULT_KNOWLEDGE_SOURCE",
]
