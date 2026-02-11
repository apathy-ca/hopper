"""
Hopper memory management.

3-tier memory system:
- Working Memory: Immediate context for routing (fast, ephemeral)
- Episodic Memory: Historical routing decisions (searchable)
- Consolidated Memory: Learned patterns (persistent)

Plus:
- Learning Loop: Integrates all components for continuous improvement
"""

from .working import RoutingContext, WorkingMemory
from .episodic import EpisodicStore, RoutingEpisode
from .search import TaskSimilarity, SimilarityResult, TaskSearcher
from .feedback import FeedbackStore, FeedbackAnalytics
from .consolidated import RoutingPattern, ConsolidatedStore, PatternExtractor
from .learning import LearningEngine, RoutingSuggestion, SuggestionSource

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
