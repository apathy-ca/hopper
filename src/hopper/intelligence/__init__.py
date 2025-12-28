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

from hopper.intelligence.base import BaseIntelligence
from hopper.intelligence.types import (
    RoutingContext,
    RoutingDecision,
    DecisionStrategy,
)

__all__ = [
    "BaseIntelligence",
    "RoutingContext",
    "RoutingDecision",
    "DecisionStrategy",
]
