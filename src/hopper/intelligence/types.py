"""
Core types for the routing intelligence system.

Defines data structures used across all routing intelligence implementations.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DecisionStrategy(Enum):
    """
    Routing decision strategy types.

    Represents which intelligence system made the routing decision.
    """

    RULES = "rules"  # Phase 1: Rules-based routing
    LLM = "llm"  # Phase 4: LLM-based routing
    SAGE = "sage"  # Phase 4: Sage-based routing
    HYBRID = "hybrid"  # Combination of multiple strategies
    MANUAL = "manual"  # Human-assigned routing


@dataclass
class RoutingContext:
    """
    Context information for routing decisions.

    Contains all information needed to make an intelligent routing decision,
    including task details, available destinations, and historical data.
    """

    # Task information
    task_id: str
    task_title: str
    task_description: str
    task_tags: List[str] = field(default_factory=list)
    task_priority: Optional[str] = None  # low, medium, high, critical
    task_metadata: Dict[str, Any] = field(default_factory=dict)

    # Available destinations
    available_destinations: List[str] = field(default_factory=list)

    # Historical context
    similar_tasks: List[Dict[str, Any]] = field(default_factory=list)
    recent_decisions: List[Dict[str, Any]] = field(default_factory=list)

    # User preferences
    user_id: Optional[str] = None
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    # Timing information
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Additional context
    source: Optional[str] = None  # Where the task came from (MCP, CLI, API, etc.)
    conversation_id: Optional[str] = None  # Link to conversation if from MCP


@dataclass
class RoutingDecision:
    """
    A routing decision with confidence and reasoning.

    Represents a single routing decision, including where to route,
    how confident we are, and why this decision was made.
    """

    # Core decision
    destination: str  # Where to route (project:name, instance:name, user:name)
    confidence: float  # 0.0 to 1.0

    # Decision context
    strategy: DecisionStrategy
    reasoning: str  # Human-readable explanation
    matched_rules: List[str] = field(default_factory=list)  # For rules-based routing
    decision_factors: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    decision_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    intelligence_version: Optional[str] = None

    # Alternative suggestions
    alternatives: List["RoutingDecision"] = field(default_factory=list)

    def __post_init__(self):
        """Validate confidence score is in valid range."""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")

    def is_confident(self, threshold: float = 0.7) -> bool:
        """
        Check if this decision meets a confidence threshold.

        Args:
            threshold: Minimum confidence required (default 0.7)

        Returns:
            True if confidence >= threshold
        """
        return self.confidence >= threshold


@dataclass
class DecisionFeedback:
    """
    Feedback on a routing decision.

    Used to improve routing intelligence over time by learning from
    whether decisions were correct or not.
    """

    decision_id: str
    correct: bool
    actual_destination: Optional[str] = None  # If incorrect, what was the right answer
    feedback_type: str = "binary"  # binary, rating, detailed
    rating: Optional[float] = None  # 0.0 to 1.0 for more nuanced feedback
    notes: Optional[str] = None

    # Who provided feedback
    feedback_source: str = "user"  # user, system, automatic
    feedback_by: Optional[str] = None  # User ID

    # When
    timestamp: datetime = field(default_factory=datetime.utcnow)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingRule:
    """
    A rule for routing decisions.

    Base class for all rule types in the rules-based routing system.
    """

    rule_id: str
    name: str
    description: str
    destination: str
    weight: float = 1.0  # Rule importance (higher = more important)
    enabled: bool = True
    priority: int = 0  # Higher priority rules evaluated first

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None

    # Statistics
    times_matched: int = 0
    times_correct: int = 0
    times_incorrect: int = 0

    def success_rate(self) -> Optional[float]:
        """
        Calculate the success rate of this rule.

        Returns:
            Success rate (0.0 to 1.0) or None if no feedback yet.
        """
        total_feedback = self.times_correct + self.times_incorrect
        if total_feedback == 0:
            return None
        return self.times_correct / total_feedback


@dataclass
class RoutingStatistics:
    """
    Statistics about routing performance.

    Tracks how well the routing system is performing over time.
    """

    total_decisions: int = 0
    decisions_by_strategy: Dict[DecisionStrategy, int] = field(default_factory=dict)

    # Feedback statistics
    total_feedback: int = 0
    correct_decisions: int = 0
    incorrect_decisions: int = 0

    # Confidence statistics
    average_confidence: float = 0.0
    high_confidence_correct: int = 0  # High confidence and correct
    high_confidence_incorrect: int = 0  # High confidence but wrong
    low_confidence_correct: int = 0  # Low confidence but correct

    # Performance over time
    decisions_per_day: Dict[str, int] = field(default_factory=dict)
    accuracy_per_day: Dict[str, float] = field(default_factory=dict)

    def overall_accuracy(self) -> Optional[float]:
        """
        Calculate overall routing accuracy.

        Returns:
            Accuracy (0.0 to 1.0) or None if no feedback yet.
        """
        if self.total_feedback == 0:
            return None
        return self.correct_decisions / self.total_feedback

    def precision_at_high_confidence(self, threshold: float = 0.7) -> Optional[float]:
        """
        Calculate precision when making high-confidence decisions.

        Args:
            threshold: Confidence threshold for "high confidence"

        Returns:
            Precision (0.0 to 1.0) or None if no high-confidence decisions yet.
        """
        total_high_confidence = self.high_confidence_correct + self.high_confidence_incorrect
        if total_high_confidence == 0:
            return None
        return self.high_confidence_correct / total_high_confidence
