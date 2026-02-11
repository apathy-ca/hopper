"""
Pattern extractor for learning from episodic memory.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from ..episodic import EpisodicStore, RoutingEpisode
from .store import ConsolidatedStore
from .models import RoutingPattern

logger = logging.getLogger(__name__)


@dataclass
class PatternCandidate:
    """A candidate pattern extracted from episodes."""

    target_instance: str
    tag_criteria: dict[str, Any]
    text_criteria: dict[str, Any]
    priority_criteria: str | None
    episode_count: int
    success_rate: float
    episode_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "target_instance": self.target_instance,
            "tag_criteria": self.tag_criteria,
            "text_criteria": self.text_criteria,
            "priority_criteria": self.priority_criteria,
            "episode_count": self.episode_count,
            "success_rate": self.success_rate,
            "confidence": self.confidence,
            "episode_ids": self.episode_ids,
        }


class PatternExtractor:
    """
    Extract patterns from episodic memory.

    Analyzes successful routing episodes to identify patterns that can
    be used to improve future routing decisions.
    """

    def __init__(
        self,
        session: Session,
        episodic_store: EpisodicStore | None = None,
        consolidated_store: ConsolidatedStore | None = None,
        min_episodes: int = 3,
        min_success_rate: float = 0.7,
    ):
        """
        Initialize pattern extractor.

        Args:
            session: Database session
            episodic_store: Episodic store (created if not provided)
            consolidated_store: Consolidated store (created if not provided)
            min_episodes: Minimum episodes to form a pattern
            min_success_rate: Minimum success rate for patterns
        """
        self.session = session
        self.episodic_store = episodic_store or EpisodicStore(session)
        self.consolidated_store = consolidated_store or ConsolidatedStore(session)
        self.min_episodes = min_episodes
        self.min_success_rate = min_success_rate

    def extract_patterns(
        self,
        since: datetime | None = None,
        min_confidence: float = 0.5,
    ) -> list[PatternCandidate]:
        """
        Extract pattern candidates from successful episodes.

        Args:
            since: Only consider episodes after this time
            min_confidence: Minimum confidence for candidates

        Returns:
            List of pattern candidates
        """
        # Get successful episodes
        episodes = self.episodic_store.get_successful_episodes(
            limit=1000,
            since=since,
        )

        if not episodes:
            return []

        # Group episodes by target instance
        by_instance: dict[str, list[RoutingEpisode]] = {}
        for ep in episodes:
            if ep.chosen_instance:
                if ep.chosen_instance not in by_instance:
                    by_instance[ep.chosen_instance] = []
                by_instance[ep.chosen_instance].append(ep)

        # Extract patterns for each instance
        candidates = []
        for instance_id, instance_episodes in by_instance.items():
            if len(instance_episodes) < self.min_episodes:
                continue

            candidate = self._extract_pattern_for_instance(
                instance_id, instance_episodes
            )
            if candidate and candidate.confidence >= min_confidence:
                candidates.append(candidate)

        return candidates

    def _extract_pattern_for_instance(
        self,
        instance_id: str,
        episodes: list[RoutingEpisode],
    ) -> PatternCandidate | None:
        """Extract a pattern for a specific instance."""
        # Analyze tag frequency
        tag_counter: Counter[str] = Counter()
        priority_counter: Counter[str] = Counter()
        word_counter: Counter[str] = Counter()

        for ep in episodes:
            snapshot = ep.task_snapshot or {}

            # Count tags
            tags = snapshot.get("tags", {})
            if isinstance(tags, dict):
                tag_counter.update(tags.keys())
            elif isinstance(tags, list):
                tag_counter.update(tags)

            # Count priorities
            priority = snapshot.get("priority")
            if priority:
                priority_counter[priority] += 1

            # Count words in title
            title = snapshot.get("title", "")
            if title:
                words = title.lower().split()
                # Filter common words
                words = [w for w in words if len(w) > 3]
                word_counter.update(words)

        # Build tag criteria
        total_episodes = len(episodes)
        required_tags = [
            tag for tag, count in tag_counter.items()
            if count >= total_episodes * 0.8  # Present in 80%+ of episodes
        ]
        optional_tags = [
            tag for tag, count in tag_counter.items()
            if 0.3 <= count / total_episodes < 0.8  # Present in 30-80%
        ]

        tag_criteria = {}
        if required_tags:
            tag_criteria["required"] = required_tags
        if optional_tags:
            tag_criteria["optional"] = optional_tags

        # Build text criteria
        common_words = [
            word for word, count in word_counter.most_common(5)
            if count >= total_episodes * 0.5
        ]
        text_criteria = {}
        if common_words:
            text_criteria["keywords"] = common_words

        # Build priority criteria
        priority_criteria = None
        if priority_counter:
            most_common = priority_counter.most_common(1)[0]
            if most_common[1] >= total_episodes * 0.7:
                priority_criteria = most_common[0]

        # Skip if no meaningful criteria
        if not tag_criteria and not text_criteria and not priority_criteria:
            return None

        # Calculate confidence based on pattern strength
        confidence = self._calculate_confidence(
            tag_criteria, text_criteria, total_episodes
        )

        return PatternCandidate(
            target_instance=instance_id,
            tag_criteria=tag_criteria,
            text_criteria=text_criteria,
            priority_criteria=priority_criteria,
            episode_count=total_episodes,
            success_rate=1.0,  # These are all successful episodes
            episode_ids=[ep.id for ep in episodes],
            confidence=confidence,
        )

    def _calculate_confidence(
        self,
        tag_criteria: dict[str, Any],
        text_criteria: dict[str, Any],
        episode_count: int,
    ) -> float:
        """Calculate pattern confidence."""
        confidence = 0.0

        # More required tags = higher confidence
        required_tags = tag_criteria.get("required", [])
        if required_tags:
            confidence += min(0.4, len(required_tags) * 0.1)

        # Keywords add confidence
        keywords = text_criteria.get("keywords", [])
        if keywords:
            confidence += min(0.2, len(keywords) * 0.05)

        # More episodes = higher confidence
        confidence += min(0.3, episode_count * 0.03)

        # Base confidence
        confidence += 0.1

        return min(1.0, confidence)

    def create_patterns_from_candidates(
        self,
        candidates: list[PatternCandidate],
        auto_name: bool = True,
    ) -> list[RoutingPattern]:
        """
        Create patterns from candidates.

        Args:
            candidates: Pattern candidates
            auto_name: Auto-generate pattern names

        Returns:
            List of created patterns
        """
        created = []

        for candidate in candidates:
            # Generate name
            if auto_name:
                name = self._generate_pattern_name(candidate)
            else:
                name = f"pattern-{candidate.target_instance}"

            # Check for existing similar pattern
            existing = self.consolidated_store.get_pattern_by_name(name)
            if existing:
                # Refine existing pattern
                self.consolidated_store.refine_pattern(
                    existing.id,
                    new_tag_criteria=candidate.tag_criteria,
                    new_text_criteria=candidate.text_criteria,
                    new_confidence=max(existing.confidence, candidate.confidence),
                )
                continue

            # Create new pattern
            pattern = self.consolidated_store.create_pattern(
                name=name,
                target_instance=candidate.target_instance,
                tag_criteria=candidate.tag_criteria,
                text_criteria=candidate.text_criteria,
                priority_criteria=candidate.priority_criteria,
                pattern_type=self._determine_pattern_type(candidate),
                confidence=candidate.confidence,
                source_episodes=candidate.episode_ids[:20],  # Limit stored IDs
            )
            created.append(pattern)

        return created

    def _generate_pattern_name(self, candidate: PatternCandidate) -> str:
        """Generate a descriptive name for a pattern."""
        parts = []

        # Add required tags
        required = candidate.tag_criteria.get("required", [])
        if required:
            parts.append("-".join(required[:3]))

        # Add priority
        if candidate.priority_criteria:
            parts.append(candidate.priority_criteria)

        # Add target
        parts.append(f"to-{candidate.target_instance}")

        return "_".join(parts) or f"pattern-{candidate.target_instance}"

    def _determine_pattern_type(self, candidate: PatternCandidate) -> str:
        """Determine the type of pattern."""
        has_tags = bool(candidate.tag_criteria)
        has_text = bool(candidate.text_criteria)

        if has_tags and has_text:
            return "combined"
        elif has_tags:
            return "tag"
        elif has_text:
            return "text"
        else:
            return "priority"

    def run_consolidation(
        self,
        since: datetime | None = None,
        min_confidence: float = 0.5,
    ) -> dict[str, Any]:
        """
        Run a full consolidation cycle.

        Args:
            since: Only consider episodes after this time
            min_confidence: Minimum confidence for patterns

        Returns:
            Summary of consolidation
        """
        if since is None:
            since = datetime.utcnow() - timedelta(days=30)

        # Extract candidates
        candidates = self.extract_patterns(
            since=since,
            min_confidence=min_confidence,
        )

        # Create patterns
        created_patterns = self.create_patterns_from_candidates(candidates)

        # Get statistics
        stats = self.consolidated_store.get_statistics()

        return {
            "candidates_found": len(candidates),
            "patterns_created": len(created_patterns),
            "created_pattern_ids": [p.id for p in created_patterns],
            "total_patterns": stats["total_patterns"],
            "active_patterns": stats["active_patterns"],
            "since": since.isoformat(),
            "ran_at": datetime.utcnow().isoformat(),
        }
