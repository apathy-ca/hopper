"""
Semantic Search package.

Provides TF-IDF based text similarity and tag matching for finding similar tasks.
"""

from .searcher import TaskSearcher
from .similarity import SimilarityResult, TaskSimilarity

__all__ = [
    "TaskSimilarity",
    "SimilarityResult",
    "TaskSearcher",
]
