"""
Hopper storage backends.

Provides pluggable storage for local (markdown) and server (SQL) modes.
"""

from .base import StorageBackend, StorageConfig
from .markdown import MarkdownStorage
from .tasks import TaskStore, TaskMarkdownStore
from .memory import (
    EpisodeStore,
    PatternStore,
    FeedbackStore,
    EpisodeMarkdownStore,
    PatternMarkdownStore,
    FeedbackMarkdownStore,
)
from .knowledge import (
    initialize_knowledge,
    write_hopper_usage,
    sync_agent_knowledge,
    detect_project_type,
    DEFAULT_KNOWLEDGE_SOURCE,
)

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
    # Knowledge
    "initialize_knowledge",
    "write_hopper_usage",
    "sync_agent_knowledge",
    "detect_project_type",
    "DEFAULT_KNOWLEDGE_SOURCE",
]
