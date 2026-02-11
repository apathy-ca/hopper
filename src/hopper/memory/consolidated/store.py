"""
Consolidated store for managing routing patterns.
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from .models import RoutingPattern

logger = logging.getLogger(__name__)


class ConsolidatedStore:
    """
    Store for managing routing patterns.

    Provides CRUD operations and querying for learned patterns.
    """

    def __init__(self, session: Session):
        """
        Initialize consolidated store.

        Args:
            session: Database session
        """
        self.session = session

    def create_pattern(
        self,
        name: str,
        target_instance: str,
        tag_criteria: dict[str, Any] | None = None,
        text_criteria: dict[str, Any] | None = None,
        priority_criteria: str | None = None,
        description: str | None = None,
        pattern_type: str = "tag",
        confidence: float = 0.5,
        source_episodes: list[str] | None = None,
    ) -> RoutingPattern:
        """
        Create a new routing pattern.

        Args:
            name: Pattern name
            target_instance: Target instance for routing
            tag_criteria: Tag matching criteria
            text_criteria: Text matching criteria
            priority_criteria: Priority matching criteria
            description: Pattern description
            pattern_type: Type of pattern
            confidence: Initial confidence score
            source_episodes: Episodes that contributed to this pattern

        Returns:
            Created RoutingPattern
        """
        pattern = RoutingPattern(
            id=f"pat-{uuid4().hex[:12]}",
            name=name,
            description=description,
            pattern_type=pattern_type,
            tag_criteria=tag_criteria,
            text_criteria=text_criteria,
            priority_criteria=priority_criteria,
            target_instance=target_instance,
            confidence=confidence,
            source_episodes=source_episodes,
            is_active=True,
        )

        self.session.add(pattern)
        self.session.flush()

        logger.info(f"Created pattern {pattern.id}: {name} -> {target_instance}")

        return pattern

    def get_pattern(self, pattern_id: str) -> RoutingPattern | None:
        """Get pattern by ID."""
        query = select(RoutingPattern).where(RoutingPattern.id == pattern_id)
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_pattern_by_name(self, name: str) -> RoutingPattern | None:
        """Get pattern by name."""
        query = select(RoutingPattern).where(RoutingPattern.name == name)
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_patterns_for_instance(
        self,
        instance_id: str,
        active_only: bool = True,
    ) -> list[RoutingPattern]:
        """Get all patterns targeting an instance."""
        query = select(RoutingPattern).where(
            RoutingPattern.target_instance == instance_id
        )

        if active_only:
            query = query.where(RoutingPattern.is_active == True)  # noqa: E712

        query = query.order_by(RoutingPattern.confidence.desc())

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_all_patterns(
        self,
        active_only: bool = True,
        limit: int = 100,
    ) -> list[RoutingPattern]:
        """Get all patterns."""
        query = select(RoutingPattern)

        if active_only:
            query = query.where(RoutingPattern.is_active == True)  # noqa: E712

        query = query.order_by(RoutingPattern.confidence.desc()).limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def find_matching_patterns(
        self,
        tags: dict[str, Any] | list[str] | None = None,
        priority: str | None = None,
        title: str | None = None,
        min_confidence: float = 0.3,
        limit: int = 10,
    ) -> list[tuple[RoutingPattern, float]]:
        """
        Find patterns that match the given criteria.

        Args:
            tags: Task tags
            priority: Task priority
            title: Task title
            min_confidence: Minimum pattern confidence
            limit: Maximum results

        Returns:
            List of (pattern, match_score) tuples, sorted by score
        """
        # Get active patterns above confidence threshold
        query = (
            select(RoutingPattern)
            .where(
                and_(
                    RoutingPattern.is_active == True,  # noqa: E712
                    RoutingPattern.confidence >= min_confidence,
                )
            )
            .order_by(RoutingPattern.confidence.desc())
        )

        result = self.session.execute(query)
        patterns = result.scalars().all()

        # Find matching patterns
        matches = []
        for pattern in patterns:
            is_match, score = pattern.matches_task(
                tags=tags,
                priority=priority,
                title=title,
            )
            if is_match:
                matches.append((pattern, score))

        # Sort by score and return top matches
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[:limit]

    def update_pattern_confidence(
        self,
        pattern_id: str,
        success: bool,
    ) -> RoutingPattern | None:
        """
        Update pattern confidence after usage.

        Args:
            pattern_id: Pattern ID
            success: Whether routing was successful

        Returns:
            Updated pattern or None
        """
        pattern = self.get_pattern(pattern_id)
        if pattern is None:
            return None

        pattern.record_usage(success)
        self.session.flush()

        logger.info(f"Updated pattern {pattern_id}: success={success}, confidence={pattern.confidence}")

        return pattern

    def deactivate_pattern(self, pattern_id: str) -> bool:
        """
        Deactivate a pattern.

        Args:
            pattern_id: Pattern ID

        Returns:
            True if deactivated
        """
        pattern = self.get_pattern(pattern_id)
        if pattern is None:
            return False

        pattern.is_active = False
        self.session.flush()

        logger.info(f"Deactivated pattern {pattern_id}")
        return True

    def activate_pattern(self, pattern_id: str) -> bool:
        """
        Activate a pattern.

        Args:
            pattern_id: Pattern ID

        Returns:
            True if activated
        """
        pattern = self.get_pattern(pattern_id)
        if pattern is None:
            return False

        pattern.is_active = True
        self.session.flush()

        logger.info(f"Activated pattern {pattern_id}")
        return True

    def delete_pattern(self, pattern_id: str) -> bool:
        """
        Delete a pattern.

        Args:
            pattern_id: Pattern ID

        Returns:
            True if deleted
        """
        pattern = self.get_pattern(pattern_id)
        if pattern is None:
            return False

        self.session.delete(pattern)
        self.session.flush()

        logger.info(f"Deleted pattern {pattern_id}")
        return True

    def refine_pattern(
        self,
        pattern_id: str,
        new_tag_criteria: dict[str, Any] | None = None,
        new_text_criteria: dict[str, Any] | None = None,
        new_confidence: float | None = None,
    ) -> RoutingPattern | None:
        """
        Refine a pattern with updated criteria.

        Args:
            pattern_id: Pattern ID
            new_tag_criteria: Updated tag criteria
            new_text_criteria: Updated text criteria
            new_confidence: Updated confidence

        Returns:
            Updated pattern or None
        """
        pattern = self.get_pattern(pattern_id)
        if pattern is None:
            return None

        if new_tag_criteria is not None:
            pattern.tag_criteria = new_tag_criteria
        if new_text_criteria is not None:
            pattern.text_criteria = new_text_criteria
        if new_confidence is not None:
            pattern.confidence = new_confidence

        pattern.last_refined_at = datetime.utcnow()
        self.session.flush()

        logger.info(f"Refined pattern {pattern_id}")
        return pattern

    def get_statistics(self) -> dict[str, Any]:
        """Get pattern statistics."""
        all_patterns = self.get_all_patterns(active_only=False, limit=10000)

        active_count = sum(1 for p in all_patterns if p.is_active)
        total_usage = sum(p.usage_count for p in all_patterns)
        avg_confidence = (
            sum(p.confidence for p in all_patterns) / len(all_patterns)
            if all_patterns else 0.0
        )

        # By pattern type
        by_type: dict[str, int] = {}
        for p in all_patterns:
            by_type[p.pattern_type] = by_type.get(p.pattern_type, 0) + 1

        # By target instance
        by_instance: dict[str, int] = {}
        for p in all_patterns:
            by_instance[p.target_instance] = by_instance.get(p.target_instance, 0) + 1

        return {
            "total_patterns": len(all_patterns),
            "active_patterns": active_count,
            "inactive_patterns": len(all_patterns) - active_count,
            "total_usage": total_usage,
            "average_confidence": avg_confidence,
            "by_type": by_type,
            "by_instance": by_instance,
        }
