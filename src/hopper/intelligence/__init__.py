"""
Hopper Intelligence Layer

Routing strategies, decision-making logic, and learning capabilities.

This package provides the intelligence layer for task routing, including:
- Base intelligence interfaces
- Rules-based routing (Phase 1)
- LLM-based routing (Phase 4)
- Sage-based routing (Phase 4)
- Decision recording and feedback
"""

from hopper.intelligence.base import BaseIntelligence, RoutingError
from hopper.intelligence.decision_recorder import (
    DecisionRecord,
    DecisionRecorder,
    get_decision_recorder,
    record_decision,
    add_feedback,
)
from hopper.intelligence.feedback import (
    FeedbackCollector,
    get_feedback_collector,
    provide_feedback,
)
from hopper.intelligence.types import (
    DecisionFeedback,
    DecisionStrategy,
    RoutingContext,
    RoutingDecision,
    RoutingRule,
    RoutingStatistics,
)

__all__ = [
    "BaseIntelligence",
    "RoutingError",
    "RoutingContext",
    "RoutingDecision",
    "DecisionStrategy",
    "DecisionFeedback",
    "RoutingRule",
    "RoutingStatistics",
    "DecisionRecord",
    "DecisionRecorder",
    "get_decision_recorder",
    "record_decision",
    "add_feedback",
    "FeedbackCollector",
    "get_feedback_collector",
    "provide_feedback",
]
