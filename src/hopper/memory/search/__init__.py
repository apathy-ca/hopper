"""
Semantic Search package.

Provides TF-IDF based text similarity and tag matching for finding similar tasks.
"""

from .similarity import TaskSimilarity, SimilarityResult
from .searcher import TaskSearcher

__all__ = [
    "TaskSimilarity",
    "SimilarityResult",
    "TaskSearcher",
]
