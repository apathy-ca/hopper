"""
Working Memory package.

Provides immediate context storage for routing decisions.
Fast, ephemeral storage with optional Redis backing.
"""

from .context import RoutingContext
from .memory import WorkingMemory

__all__ = [
    "WorkingMemory",
    "RoutingContext",
]
