"""
Consolidated Memory package.

Provides pattern extraction and learning from episodic memory.
Patterns are extracted from successful routing episodes and used
to improve future routing decisions.
"""

from .extractor import PatternExtractor
from .models import RoutingPattern
from .store import ConsolidatedStore

__all__ = [
    "RoutingPattern",
    "ConsolidatedStore",
    "PatternExtractor",
]
