"""
Consolidated Memory package.

Provides pattern extraction and learning from episodic memory.
Patterns are extracted from successful routing episodes and used
to improve future routing decisions.
"""

from .models import RoutingPattern
from .store import ConsolidatedStore
from .extractor import PatternExtractor

__all__ = [
    "RoutingPattern",
    "ConsolidatedStore",
    "PatternExtractor",
]
