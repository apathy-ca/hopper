"""
Learning engine that integrates all memory components.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from hopper.models import Task

from ..working import WorkingMemory, RoutingContext
from ..working.context import SimilarTask, InstanceInfo
from ..episodic import EpisodicStore, RoutingEpisode
from ..search import TaskSearcher
from ..consolidated import ConsolidatedStore, PatternExtractor, RoutingPattern
from ..feedback import FeedbackStore
from .suggestion import RoutingSuggestion, SuggestionSource

logger = logging.getLogger(__name__)


@dataclass
class LearningResult:
    """Result of a learning operation."""

    episodes_created: int = 0
    patterns_updated: int = 0
    patterns_created: int = 0
    feedback_processed: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "episodes_created": self.episodes_created,
            "patterns_updated": self.patterns_updated,
            "patterns_created": self.patterns_created,
            "feedback_processed": self.feedback_processed,
        }


class LearningEngine:
    """
    Central learning engine that integrates all memory components.

    Provides:
    - Context building with similar tasks and patterns
    - Routing suggestions based on learned patterns
    - Episode recording for routing decisions
    - Feedback processing and pattern refinement
    """

    def __init__(
        self,
        session: Session,
        working_memory: WorkingMemory | None = None,
        episodic_store: EpisodicStore | None = None,
        consolidated_store: ConsolidatedStore | None = None,
        task_searcher: TaskSearcher | None = None,
        feedback_store: FeedbackStore | None = None,
    ):
        """
        Initialize learning engine.

        Args:
            session: Database session
            working_memory: Working memory (created if not provided)
            episodic_store: Episodic store (created if not provided)
            consolidated_store: Consolidated store (created if not provided)
            task_searcher: Task searcher (created if not provided)
            feedback_store: Feedback store (created if not provided)
        """
        self.session = session

        # Initialize components
        self.working_memory = working_memory or WorkingMemory()
        self.episodic_store = episodic_store or EpisodicStore(session)
        self.consolidated_store = consolidated_store or ConsolidatedStore(session)
        self.task_searcher = task_searcher or TaskSearcher(session)
        self.feedback_store = feedback_store or FeedbackStore(
            session, self.episodic_store
        )

        # Pattern extractor for consolidation
        self._pattern_extractor = PatternExtractor(
            session,
            episodic_store=self.episodic_store,
            consolidated_store=self.consolidated_store,
        )

    def build_context(
        self,
        task: Task,
        available_instances: list[InstanceInfo] | None = None,
    ) -> RoutingContext:
        """
        Build complete routing context for a task.

        Includes similar tasks, patterns, and recent decisions.

        Args:
            task: Task to build context for
            available_instances: Available instances for routing

        Returns:
            RoutingContext with all relevant information
        """
        # Check cache first
        cached = self.working_memory.get_context(task.id)
        if cached:
            return cached

        # Find similar tasks
        similar = self._find_similar_tasks(task)

        # Build context
        context = RoutingContext(
            task_id=task.id,
            task_title=task.title or "",
            task_tags=list(task.tags.keys()) if task.tags else [],
            task_priority=task.priority or "medium",
            similar_tasks=similar,
            available_instances=available_instances or [],
        )

        # Cache context
        self.working_memory.set_context(context)

        return context

    def _find_similar_tasks(self, task: Task, limit: int = 5) -> list[SimilarTask]:
        """Find tasks similar to the given task."""
        # Use searcher to find similar tasks
        search_results = self.task_searcher.search_by_task(
            task,
            limit=limit,
            min_score=0.3,
        )

        similar = []
        for result in search_results:
            # Get episode outcome for this task
            episode = self.episodic_store.get_latest_episode_for_task(result.task_id)

            similar.append(
                SimilarTask(
                    task_id=result.task_id,
                    title=result.title,
                    similarity_score=result.similarity_score,
                    routed_to=result.instance_id,
                    outcome_success=episode.outcome_success if episode else None,
                )
            )

        return similar

    def get_routing_suggestions(
        self,
        task: Task,
        context: RoutingContext | None = None,
        limit: int = 3,
    ) -> list[RoutingSuggestion]:
        """
        Get routing suggestions for a task.

        Combines suggestions from:
        1. Consolidated patterns
        2. Similar task analysis
        3. Default rules

        Args:
            task: Task to route
            context: Pre-built context (optional)
            limit: Maximum suggestions

        Returns:
            List of routing suggestions, sorted by confidence
        """
        suggestions = []

        # Get tags
        tags = task.tags or {}
        priority = task.priority
        title = task.title

        # 1. Check consolidated patterns
        pattern_matches = self.consolidated_store.find_matching_patterns(
            tags=tags,
            priority=priority,
            title=title,
            min_confidence=0.4,
            limit=limit,
        )

        for pattern, score in pattern_matches:
            suggestions.append(
                RoutingSuggestion.from_pattern(
                    target_instance=pattern.target_instance,
                    confidence=score,
                    pattern_id=pattern.id,
                    pattern_name=pattern.name,
                )
            )

        # 2. Analyze similar tasks (if context provided or we can build it)
        if context is None:
            context = self.build_context(task)

        if context.similar_tasks:
            similar_suggestion = self._analyze_similar_tasks(context.similar_tasks)
            if similar_suggestion:
                suggestions.append(similar_suggestion)

        # Sort by confidence and return top suggestions
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions[:limit]

    def _analyze_similar_tasks(
        self,
        similar_tasks: list[SimilarTask],
    ) -> RoutingSuggestion | None:
        """Analyze similar tasks to generate a suggestion."""
        if not similar_tasks:
            return None

        # Count successful routings by instance
        instance_successes: Counter[str] = Counter()
        instance_totals: Counter[str] = Counter()

        for task in similar_tasks:
            if task.routed_to:
                instance_totals[task.routed_to] += 1
                if task.outcome_success:
                    instance_successes[task.routed_to] += 1

        if not instance_totals:
            return None

        # Find best instance
        best_instance = None
        best_score = 0.0

        for instance_id, total in instance_totals.items():
            successes = instance_successes[instance_id]
            success_rate = successes / total if total > 0 else 0

            # Score based on success rate and volume
            score = success_rate * min(1.0, total / 3)  # Cap volume bonus at 3 tasks

            if score > best_score:
                best_score = score
                best_instance = instance_id

        if best_instance and best_score > 0.3:
            total = instance_totals[best_instance]
            successes = instance_successes[best_instance]
            success_rate = successes / total if total > 0 else 0

            return RoutingSuggestion.from_similar_tasks(
                target_instance=best_instance,
                confidence=best_score,
                similar_task_ids=[t.task_id for t in similar_tasks if t.routed_to == best_instance],
                success_rate=success_rate,
            )

        return None

    def record_routing(
        self,
        task: Task,
        chosen_instance: str,
        confidence: float,
        strategy: str = "learning",
        reasoning: str | None = None,
        suggestion: RoutingSuggestion | None = None,
    ) -> RoutingEpisode:
        """
        Record a routing decision as an episode.

        Args:
            task: Task being routed
            chosen_instance: Instance chosen for routing
            confidence: Routing confidence
            strategy: Strategy used for routing
            reasoning: Explanation for the decision
            suggestion: Suggestion that led to this decision

        Returns:
            Created RoutingEpisode
        """
        # Build decision factors
        factors = {}
        if suggestion:
            factors["source"] = suggestion.source.value
            factors["pattern_id"] = suggestion.pattern_id
            factors["similar_task_ids"] = suggestion.similar_task_ids

        # Get available instances from context
        context = self.working_memory.get_context(task.id)
        available = (
            [i.instance_id for i in context.available_instances]
            if context and context.available_instances
            else []
        )

        # Record episode
        episode = self.episodic_store.record_episode(
            task=task,
            chosen_instance=chosen_instance,
            confidence=confidence,
            reasoning=reasoning or (suggestion.reasoning if suggestion else None),
            strategy_used=strategy,
            available_instances=available,
            decision_factors=factors,
        )

        logger.info(f"Recorded routing episode {episode.id} for task {task.id}")

        return episode

    def record_outcome(
        self,
        task_id: str,
        success: bool,
        duration: str | None = None,
        notes: str | None = None,
    ) -> LearningResult:
        """
        Record the outcome of a routing decision.

        Updates episode, feedback, and pattern confidence.

        Args:
            task_id: Task ID
            success: Whether routing was successful
            duration: Task duration
            notes: Outcome notes

        Returns:
            LearningResult summarizing updates
        """
        result = LearningResult()

        # Get latest episode for task
        episode = self.episodic_store.get_latest_episode_for_task(task_id)
        if episode:
            # Update episode outcome
            self.episodic_store.record_outcome(
                episode_id=episode.id,
                success=success,
                duration=duration,
                notes=notes,
            )
            result.episodes_created = 1

            # Update pattern confidence if used
            if episode.decision_factors:
                pattern_id = episode.decision_factors.get("pattern_id")
                if pattern_id:
                    self.consolidated_store.update_pattern_confidence(
                        pattern_id, success
                    )
                    result.patterns_updated = 1

        return result

    def process_feedback(
        self,
        task_id: str,
        was_good_match: bool,
        routing_feedback: str | None = None,
        should_have_routed_to: str | None = None,
        **kwargs,
    ) -> LearningResult:
        """
        Process feedback for a routing decision.

        Args:
            task_id: Task ID
            was_good_match: Whether routing was correct
            routing_feedback: Text feedback
            should_have_routed_to: Correct instance (if misrouted)
            **kwargs: Additional feedback fields

        Returns:
            LearningResult summarizing updates
        """
        result = LearningResult()

        # Record feedback
        feedback = self.feedback_store.record_feedback(
            task_id=task_id,
            was_good_match=was_good_match,
            routing_feedback=routing_feedback,
            should_have_routed_to=should_have_routed_to,
            **kwargs,
        )

        if feedback:
            result.feedback_processed = 1

            # Update episode outcome based on feedback
            episode = self.episodic_store.get_latest_episode_for_task(task_id)
            if episode:
                if was_good_match:
                    episode.mark_success(notes=routing_feedback)
                else:
                    episode.mark_failure(notes=routing_feedback)

                # Update pattern confidence
                if episode.decision_factors:
                    pattern_id = episode.decision_factors.get("pattern_id")
                    if pattern_id:
                        self.consolidated_store.update_pattern_confidence(
                            pattern_id, was_good_match
                        )
                        result.patterns_updated = 1

        return result

    def run_consolidation(
        self,
        since: datetime | None = None,
    ) -> LearningResult:
        """
        Run pattern consolidation from recent episodes.

        Args:
            since: Only consider episodes after this time

        Returns:
            LearningResult summarizing consolidation
        """
        if since is None:
            since = datetime.utcnow() - timedelta(days=7)

        consolidation = self._pattern_extractor.run_consolidation(
            since=since,
            min_confidence=0.5,
        )

        return LearningResult(
            patterns_created=consolidation["patterns_created"],
        )

    def get_statistics(self) -> dict[str, Any]:
        """Get learning engine statistics."""
        episodic_stats = self.episodic_store.get_statistics()
        pattern_stats = self.consolidated_store.get_statistics()

        return {
            "episodic": episodic_stats,
            "patterns": pattern_stats,
            "searcher": self.task_searcher.get_statistics(),
        }
