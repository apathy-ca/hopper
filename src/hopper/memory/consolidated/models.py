"""
Consolidated memory models.

Defines the RoutingPattern model for storing learned patterns.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, Integer, String, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from hopper.models.base import Base, TimestampMixin


class RoutingPattern(Base, TimestampMixin):
    """
    Model for storing learned routing patterns.

    Patterns are extracted from successful routing episodes and represent
    generalized rules for routing similar tasks.
    """

    __tablename__ = "routing_patterns"

    # Primary key
    id: Mapped[str] = mapped_column(String(100), primary_key=True)

    # Pattern name and description
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Pattern type (tag-based, text-based, combined)
    pattern_type: Mapped[str] = mapped_column(String(50), default="tag", nullable=False)

    # Matching criteria
    tag_criteria: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    text_criteria: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )
    priority_criteria: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Routing target
    target_instance: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Confidence and usage statistics
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Source episodes (IDs of episodes that contributed to this pattern)
    source_episodes: Mapped[list[str] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=True,
    )

    # Active status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Timestamps
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_refined_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RoutingPattern(id={self.id}, name={self.name}, "
            f"target={self.target_instance}, confidence={self.confidence})>"
        )

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def record_usage(self, success: bool) -> None:
        """Record pattern usage."""
        self.usage_count += 1
        self.last_used_at = datetime.utcnow()
        if success:
            self.success_count += 1
        else:
            self.failure_count += 1
        # Update confidence based on success rate
        self._update_confidence()

    def _update_confidence(self) -> None:
        """Update confidence based on usage statistics."""
        if self.usage_count < 5:
            # Not enough data, keep initial confidence
            return

        # Weight recent success rate with initial confidence
        success_rate = self.success_rate
        # Bayesian-like update
        self.confidence = (self.confidence * 0.3) + (success_rate * 0.7)

    def matches_task(
        self,
        tags: dict[str, Any] | list[str] | None = None,
        priority: str | None = None,
        title: str | None = None,
    ) -> tuple[bool, float]:
        """
        Check if this pattern matches a task.

        Only evaluates criteria when the task provides the relevant data.
        For example, if no priority is provided, priority_criteria is skipped.

        Args:
            tags: Task tags
            priority: Task priority
            title: Task title

        Returns:
            Tuple of (matches, match_score)
        """
        match_score = 0.0
        criteria_count = 0

        # Tag matching (only if pattern has tag criteria and task has tags)
        if self.tag_criteria and tags is not None:
            criteria_count += 1
            required_tags = self.tag_criteria.get("required", [])
            optional_tags = self.tag_criteria.get("optional", [])

            # Normalize tags
            if isinstance(tags, dict):
                task_tags = set(tags.keys())
            else:
                task_tags = set(tags)

            # Check required tags
            required_set = set(required_tags)
            if required_set and not required_set.issubset(task_tags):
                return False, 0.0

            # Required tags matched - base score of 1.0
            # Optional tags add a bonus but don't reduce the score
            optional_set = set(optional_tags)
            if optional_set:
                optional_match = len(task_tags & optional_set) / len(optional_set)
                match_score += 1.0 + (0.2 * optional_match)  # 1.0 for required, bonus for optional
            else:
                match_score += 1.0  # All required tags matched, no optional

        # Priority matching (only if both pattern and task have priority)
        if self.priority_criteria and priority is not None:
            criteria_count += 1
            if priority == self.priority_criteria:
                match_score += 1.0

        # Text matching (only if pattern has text criteria and task has title)
        if self.text_criteria and title:
            criteria_count += 1
            keywords = self.text_criteria.get("keywords", [])
            if keywords:
                title_lower = title.lower()
                keyword_matches = sum(1 for k in keywords if k.lower() in title_lower)
                match_score += keyword_matches / len(keywords) if keywords else 0

        if criteria_count == 0:
            return True, self.confidence  # No applicable criteria, matches everything

        # Normalize score
        final_score = match_score / criteria_count
        return final_score >= 0.5, final_score * self.confidence

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "pattern_type": self.pattern_type,
            "tag_criteria": self.tag_criteria,
            "text_criteria": self.text_criteria,
            "priority_criteria": self.priority_criteria,
            "target_instance": self.target_instance,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "success_rate": self.success_rate,
            "source_episodes": self.source_episodes,
            "is_active": self.is_active,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "last_refined_at": self.last_refined_at.isoformat() if self.last_refined_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
