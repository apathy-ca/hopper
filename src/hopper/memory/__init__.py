"""
Hopper memory management.

3-tier memory system:
- Working Memory: Immediate context for routing (fast, ephemeral)
- Episodic Memory: Historical routing decisions (searchable)
- Consolidated Memory: Learned patterns (persistent)

Plus:
- Learning Loop: Integrates all components for continuous improvement
"""

from .consolidated import ConsolidatedStore, PatternExtractor, RoutingPattern
from .episodic import EpisodicStore, RoutingEpisode
from .feedback import FeedbackAnalytics, FeedbackStore
from .learning import LearningEngine, RoutingSuggestion, SuggestionSource
from .search import SimilarityResult, TaskSearcher, TaskSimilarity
from .working import RoutingContext, WorkingMemory

__all__ = [
    # Working Memory
    "WorkingMemory",
    "RoutingContext",
    # Episodic Memory
    "EpisodicStore",
    "RoutingEpisode",
    # Semantic Search
    "TaskSimilarity",
    "SimilarityResult",
    "TaskSearcher",
    # Feedback
    "FeedbackStore",
    "FeedbackAnalytics",
    # Consolidated Memory
    "RoutingPattern",
    "ConsolidatedStore",
    "PatternExtractor",
    # Learning Loop
    "LearningEngine",
    "RoutingSuggestion",
    "SuggestionSource",
]
