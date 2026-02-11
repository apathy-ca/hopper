"""
Episodic store for routing episode management.
"""

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session

from hopper.models import RoutingDecision, Task, TaskFeedback

from .models import RoutingEpisode

logger = logging.getLogger(__name__)


class EpisodicStore:
    """
    Store for managing routing episodes.

    Provides methods to record, query, and analyze routing decisions.
    """

    def __init__(self, session: Session):
        """
        Initialize the episodic store.

        Args:
            session: Database session
        """
        self.session = session

    def record_episode(
        self,
        task: Task,
        decision: RoutingDecision | None = None,
        chosen_instance: str | None = None,
        confidence: float = 0.0,
        reasoning: str | None = None,
        strategy_used: str = "rules",
        available_instances: list[str] | None = None,
        similar_tasks: list[dict[str, Any]] | None = None,
        decision_factors: dict[str, Any] | None = None,
        instance_context: dict[str, Any] | None = None,
    ) -> RoutingEpisode:
        """
        Record a new routing episode.

        Args:
            task: Task being routed
            decision: Optional RoutingDecision reference
            chosen_instance: Instance chosen for routing
            confidence: Confidence score (0-1)
            reasoning: Explanation for the decision
            strategy_used: Routing strategy used
            available_instances: List of available instance IDs
            similar_tasks: Similar tasks used for decision
            decision_factors: Factors that influenced decision
            instance_context: Context about instances at routing time

        Returns:
            Created RoutingEpisode
        """
        # Create task snapshot
        task_snapshot = {
            "id": task.id,
            "title": task.title,
            "description": task.description,
            "project": task.project,
            "status": task.status.value if hasattr(task.status, "value") else str(task.status),
            "priority": task.priority,
            "tags": task.tags,
            "instance_id": task.instance_id,
        }

        episode = RoutingEpisode(
            id=f"ep-{uuid4().hex[:12]}",
            task_id=task.id,
            decision_task_id=decision.task_id if decision else None,
            task_snapshot=task_snapshot,
            available_instances=available_instances or [],
            similar_tasks_used=similar_tasks,
            chosen_instance=chosen_instance or (decision.project if decision else None),
            confidence=confidence or (decision.confidence if decision else 0.0),
            reasoning=reasoning,
            strategy_used=strategy_used or (decision.decided_by if decision else "rules"),
            decision_factors=decision_factors,
            instance_context=instance_context,
            routed_at=datetime.utcnow(),
        )

        self.session.add(episode)
        self.session.flush()

        logger.info(f"Recorded episode {episode.id} for task {task.id}")

        return episode

    def record_outcome(
        self,
        episode_id: str,
        success: bool,
        duration: str | None = None,
        notes: str | None = None,
        feedback_id: str | None = None,
    ) -> RoutingEpisode | None:
        """
        Record the outcome of a routing episode.

        Args:
            episode_id: Episode ID
            success: Whether routing was successful
            duration: Task duration
            notes: Outcome notes
            feedback_id: Link to feedback record

        Returns:
            Updated episode or None if not found
        """
        episode = self.get_episode(episode_id)
        if episode is None:
            return None

        if success:
            episode.mark_success(duration=duration, notes=notes)
        else:
            episode.mark_failure(notes=notes)

        if feedback_id:
            episode.feedback_id = feedback_id

        self.session.flush()

        logger.info(f"Recorded outcome for episode {episode_id}: success={success}")

        return episode

    def get_episode(self, episode_id: str) -> RoutingEpisode | None:
        """Get episode by ID."""
        query = select(RoutingEpisode).where(RoutingEpisode.id == episode_id)
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_episodes_for_task(self, task_id: str) -> list[RoutingEpisode]:
        """Get all episodes for a task."""
        query = (
            select(RoutingEpisode)
            .where(RoutingEpisode.task_id == task_id)
            .order_by(RoutingEpisode.routed_at.desc())
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_latest_episode_for_task(self, task_id: str) -> RoutingEpisode | None:
        """Get the most recent episode for a task."""
        query = (
            select(RoutingEpisode)
            .where(RoutingEpisode.task_id == task_id)
            .order_by(RoutingEpisode.routed_at.desc())
            .limit(1)
        )
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_episodes_for_instance(
        self,
        instance_id: str,
        limit: int = 100,
        include_outcomes: bool = True,
    ) -> list[RoutingEpisode]:
        """Get episodes where instance was chosen."""
        query = (
            select(RoutingEpisode)
            .where(RoutingEpisode.chosen_instance == instance_id)
            .order_by(RoutingEpisode.routed_at.desc())
            .limit(limit)
        )

        if include_outcomes:
            query = query.where(RoutingEpisode.outcome_success.isnot(None))

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_successful_episodes(
        self,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[RoutingEpisode]:
        """Get successful routing episodes."""
        query = (
            select(RoutingEpisode)
            .where(RoutingEpisode.outcome_success == True)  # noqa: E712
            .order_by(RoutingEpisode.routed_at.desc())
            .limit(limit)
        )

        if since:
            query = query.where(RoutingEpisode.routed_at >= since)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_failed_episodes(
        self,
        limit: int = 100,
        since: datetime | None = None,
    ) -> list[RoutingEpisode]:
        """Get failed routing episodes."""
        query = (
            select(RoutingEpisode)
            .where(RoutingEpisode.outcome_success == False)  # noqa: E712
            .order_by(RoutingEpisode.routed_at.desc())
            .limit(limit)
        )

        if since:
            query = query.where(RoutingEpisode.routed_at >= since)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_pending_episodes(self, limit: int = 100) -> list[RoutingEpisode]:
        """Get episodes without outcomes."""
        query = (
            select(RoutingEpisode)
            .where(RoutingEpisode.outcome_success.is_(None))
            .order_by(RoutingEpisode.routed_at.desc())
            .limit(limit)
        )
        result = self.session.execute(query)
        return list(result.scalars().all())

    def find_similar_episodes(
        self,
        task_tags: list[str],
        limit: int = 10,
        success_only: bool = True,
    ) -> list[RoutingEpisode]:
        """
        Find episodes with similar task tags.

        Simple tag-based matching. Enhanced in semantic-search worker.

        Args:
            task_tags: Tags to match
            limit: Max results
            success_only: Only return successful episodes

        Returns:
            List of similar episodes
        """
        # This is a simplified implementation
        # The semantic-search worker will enhance this with better similarity
        query = select(RoutingEpisode)

        if success_only:
            query = query.where(RoutingEpisode.outcome_success == True)  # noqa: E712

        query = query.order_by(RoutingEpisode.routed_at.desc()).limit(limit * 3)

        result = self.session.execute(query)
        episodes = result.scalars().all()

        # Filter by tag overlap
        matching = []
        tag_set = set(task_tags)
        for episode in episodes:
            snapshot_tags = episode.task_snapshot.get("tags", {})
            if isinstance(snapshot_tags, dict):
                episode_tags = set(snapshot_tags.keys())
            elif isinstance(snapshot_tags, list):
                episode_tags = set(snapshot_tags)
            else:
                episode_tags = set()

            if tag_set & episode_tags:  # Any overlap
                matching.append(episode)
                if len(matching) >= limit:
                    break

        return matching

    def get_statistics(
        self,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        """
        Get episode statistics.

        Args:
            since: Only count episodes after this time

        Returns:
            Statistics dict
        """
        base_query = select(RoutingEpisode)
        if since:
            base_query = base_query.where(RoutingEpisode.routed_at >= since)

        # Total episodes
        total_query = select(func.count(RoutingEpisode.id))
        if since:
            total_query = total_query.where(RoutingEpisode.routed_at >= since)
        total = self.session.execute(total_query).scalar() or 0

        # Success count
        success_query = select(func.count(RoutingEpisode.id)).where(
            RoutingEpisode.outcome_success == True  # noqa: E712
        )
        if since:
            success_query = success_query.where(RoutingEpisode.routed_at >= since)
        successes = self.session.execute(success_query).scalar() or 0

        # Failure count
        failure_query = select(func.count(RoutingEpisode.id)).where(
            RoutingEpisode.outcome_success == False  # noqa: E712
        )
        if since:
            failure_query = failure_query.where(RoutingEpisode.routed_at >= since)
        failures = self.session.execute(failure_query).scalar() or 0

        # Pending count
        pending = total - successes - failures

        # Calculate success rate
        completed = successes + failures
        success_rate = successes / completed if completed > 0 else 0.0

        # Average confidence
        avg_confidence_query = select(func.avg(RoutingEpisode.confidence))
        if since:
            avg_confidence_query = avg_confidence_query.where(
                RoutingEpisode.routed_at >= since
            )
        avg_confidence = self.session.execute(avg_confidence_query).scalar() or 0.0

        return {
            "total_episodes": total,
            "successful": successes,
            "failed": failures,
            "pending": pending,
            "success_rate": success_rate,
            "average_confidence": float(avg_confidence),
            "since": since.isoformat() if since else None,
        }

    def cleanup_old_episodes(
        self,
        retention_days: int = 90,
    ) -> int:
        """
        Delete episodes older than retention period.

        Args:
            retention_days: Days to retain episodes

        Returns:
            Number of episodes deleted
        """
        cutoff = datetime.utcnow() - timedelta(days=retention_days)

        query = select(RoutingEpisode).where(RoutingEpisode.routed_at < cutoff)
        result = self.session.execute(query)
        old_episodes = result.scalars().all()

        count = len(old_episodes)
        for episode in old_episodes:
            self.session.delete(episode)

        self.session.flush()

        logger.info(f"Cleaned up {count} episodes older than {retention_days} days")

        return count
