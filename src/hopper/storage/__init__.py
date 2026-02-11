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
]
