"""
Routing suggestion types.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class SuggestionSource(Enum):
    """Source of a routing suggestion."""

    PATTERN = "pattern"  # From consolidated patterns
    SIMILAR_TASK = "similar_task"  # From similar past tasks
    RULES = "rules"  # From rules engine
    DEFAULT = "default"  # Default routing


@dataclass
class RoutingSuggestion:
    """A routing suggestion from the learning system."""

    target_instance: str
    confidence: float
    source: SuggestionSource
    reasoning: str

    # Supporting data
    pattern_id: str | None = None
    similar_task_ids: list[str] = field(default_factory=list)
    factors: dict[str, Any] = field(default_factory=dict)

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_instance": self.target_instance,
            "confidence": self.confidence,
            "source": self.source.value,
            "reasoning": self.reasoning,
            "pattern_id": self.pattern_id,
            "similar_task_ids": self.similar_task_ids,
            "factors": self.factors,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_pattern(
        cls,
        target_instance: str,
        confidence: float,
        pattern_id: str,
        pattern_name: str,
    ) -> "RoutingSuggestion":
        """Create suggestion from a pattern match."""
        return cls(
            target_instance=target_instance,
            confidence=confidence,
            source=SuggestionSource.PATTERN,
            reasoning=f"Matched pattern: {pattern_name}",
            pattern_id=pattern_id,
        )

    @classmethod
    def from_similar_tasks(
        cls,
        target_instance: str,
        confidence: float,
        similar_task_ids: list[str],
        success_rate: float,
    ) -> "RoutingSuggestion":
        """Create suggestion from similar task analysis."""
        return cls(
            target_instance=target_instance,
            confidence=confidence,
            source=SuggestionSource.SIMILAR_TASK,
            reasoning=f"Based on {len(similar_task_ids)} similar tasks ({success_rate:.0%} success rate)",
            similar_task_ids=similar_task_ids,
            factors={"success_rate": success_rate},
        )
