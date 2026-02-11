"""
Feedback store for managing task feedback.
"""

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from hopper.models import Task, TaskFeedback, TaskStatus

from ..episodic import EpisodicStore

logger = logging.getLogger(__name__)


class FeedbackStore:
    """
    Store for managing task feedback.

    Handles feedback creation, retrieval, and linking to routing episodes.
    """

    def __init__(self, session: Session, episodic_store: EpisodicStore | None = None):
        """
        Initialize feedback store.

        Args:
            session: Database session
            episodic_store: Optional episodic store for linking feedback to episodes
        """
        self.session = session
        self.episodic_store = episodic_store

    def record_feedback(
        self,
        task_id: str,
        was_good_match: bool,
        routing_feedback: str | None = None,
        should_have_routed_to: str | None = None,
        estimated_duration: str | None = None,
        actual_duration: str | None = None,
        complexity_rating: int | None = None,
        quality_score: float | None = None,
        required_rework: bool | None = None,
        rework_reason: str | None = None,
        unexpected_blockers: list[str] | None = None,
        required_skills_not_tagged: list[str] | None = None,
        notes: str | None = None,
    ) -> TaskFeedback | None:
        """
        Record feedback for a task.

        Args:
            task_id: Task ID
            was_good_match: Whether routing was a good match
            routing_feedback: Text feedback about routing
            should_have_routed_to: Where task should have gone
            estimated_duration: Estimated task duration
            actual_duration: Actual task duration
            complexity_rating: Complexity rating (1-5)
            quality_score: Quality score (0.0-5.0)
            required_rework: Whether rework was needed
            rework_reason: Reason for rework
            unexpected_blockers: List of unexpected blockers
            required_skills_not_tagged: Skills needed but not tagged
            notes: Additional notes

        Returns:
            Created TaskFeedback or None if task not found
        """
        # Verify task exists
        task = self.session.execute(
            select(Task).where(Task.id == task_id)
        ).scalar_one_or_none()

        if task is None:
            logger.warning(f"Task {task_id} not found for feedback")
            return None

        # Check for existing feedback
        existing = self.get_feedback(task_id)
        if existing:
            # Update existing feedback
            if routing_feedback is not None:
                existing.routing_feedback = routing_feedback
            if was_good_match is not None:
                existing.was_good_match = was_good_match
            if should_have_routed_to is not None:
                existing.should_have_routed_to = should_have_routed_to
            if estimated_duration is not None:
                existing.estimated_duration = estimated_duration
            if actual_duration is not None:
                existing.actual_duration = actual_duration
            if complexity_rating is not None:
                existing.complexity_rating = complexity_rating
            if quality_score is not None:
                existing.quality_score = quality_score
            if required_rework is not None:
                existing.required_rework = required_rework
            if rework_reason is not None:
                existing.rework_reason = rework_reason
            if unexpected_blockers is not None:
                existing.unexpected_blockers = {"blockers": unexpected_blockers}
            if required_skills_not_tagged is not None:
                existing.required_skills_not_tagged = {"skills": required_skills_not_tagged}
            if notes is not None:
                existing.notes = notes

            self.session.flush()
            logger.info(f"Updated feedback for task {task_id}")

            # Update linked episode
            self._update_episode_outcome(task_id, existing)

            return existing

        # Create new feedback
        feedback = TaskFeedback(
            task_id=task_id,
            was_good_match=was_good_match,
            routing_feedback=routing_feedback,
            should_have_routed_to=should_have_routed_to,
            estimated_duration=estimated_duration,
            actual_duration=actual_duration,
            complexity_rating=complexity_rating,
            quality_score=quality_score,
            required_rework=required_rework,
            rework_reason=rework_reason,
            unexpected_blockers={"blockers": unexpected_blockers} if unexpected_blockers else None,
            required_skills_not_tagged={"skills": required_skills_not_tagged} if required_skills_not_tagged else None,
            notes=notes,
            created_at=datetime.utcnow(),
        )

        self.session.add(feedback)
        self.session.flush()

        logger.info(f"Recorded feedback for task {task_id}: was_good_match={was_good_match}")

        # Update linked episode
        self._update_episode_outcome(task_id, feedback)

        return feedback

    def _update_episode_outcome(self, task_id: str, feedback: TaskFeedback) -> None:
        """Update the linked routing episode with feedback outcome."""
        if self.episodic_store is None:
            return

        episode = self.episodic_store.get_latest_episode_for_task(task_id)
        if episode is None:
            return

        self.episodic_store.record_outcome(
            episode_id=episode.id,
            success=feedback.was_good_match or False,
            duration=feedback.actual_duration,
            notes=feedback.routing_feedback,
            feedback_id=feedback.task_id,
        )

    def get_feedback(self, task_id: str) -> TaskFeedback | None:
        """
        Get feedback for a task.

        Args:
            task_id: Task ID

        Returns:
            TaskFeedback or None
        """
        query = select(TaskFeedback).where(TaskFeedback.task_id == task_id)
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def get_all_feedback(
        self,
        limit: int = 100,
        offset: int = 0,
        good_matches_only: bool | None = None,
    ) -> list[TaskFeedback]:
        """
        Get all feedback records.

        Args:
            limit: Maximum results
            offset: Skip first N results
            good_matches_only: Filter by was_good_match

        Returns:
            List of TaskFeedback records
        """
        query = select(TaskFeedback).order_by(TaskFeedback.created_at.desc())

        if good_matches_only is True:
            query = query.where(TaskFeedback.was_good_match == True)  # noqa: E712
        elif good_matches_only is False:
            query = query.where(TaskFeedback.was_good_match == False)  # noqa: E712

        query = query.offset(offset).limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_feedback_for_instance(
        self,
        instance_id: str,
        limit: int = 100,
    ) -> list[TaskFeedback]:
        """
        Get feedback for tasks routed to a specific instance.

        Args:
            instance_id: Instance ID
            limit: Maximum results

        Returns:
            List of TaskFeedback records
        """
        query = (
            select(TaskFeedback)
            .join(Task, TaskFeedback.task_id == Task.id)
            .where(Task.instance_id == instance_id)
            .order_by(TaskFeedback.created_at.desc())
            .limit(limit)
        )

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_misrouted_feedback(self, limit: int = 100) -> list[TaskFeedback]:
        """
        Get feedback for misrouted tasks.

        Args:
            limit: Maximum results

        Returns:
            List of TaskFeedback records where routing was bad
        """
        query = (
            select(TaskFeedback)
            .where(TaskFeedback.was_good_match == False)  # noqa: E712
            .order_by(TaskFeedback.created_at.desc())
            .limit(limit)
        )

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_tasks_needing_feedback(
        self,
        limit: int = 50,
        status_filter: list[TaskStatus] | None = None,
    ) -> list[Task]:
        """
        Get completed tasks that don't have feedback yet.

        Args:
            limit: Maximum results
            status_filter: Task statuses to include (defaults to DONE)

        Returns:
            List of Tasks without feedback
        """
        if status_filter is None:
            status_filter = [TaskStatus.DONE]

        # Subquery for tasks with feedback
        feedback_subquery = select(TaskFeedback.task_id)

        query = (
            select(Task)
            .where(
                and_(
                    Task.status.in_(status_filter),
                    Task.id.notin_(feedback_subquery),
                )
            )
            .order_by(Task.updated_at.desc())
            .limit(limit)
        )

        result = self.session.execute(query)
        return list(result.scalars().all())

    def delete_feedback(self, task_id: str) -> bool:
        """
        Delete feedback for a task.

        Args:
            task_id: Task ID

        Returns:
            True if deleted
        """
        feedback = self.get_feedback(task_id)
        if feedback is None:
            return False

        self.session.delete(feedback)
        self.session.flush()

        logger.info(f"Deleted feedback for task {task_id}")
        return True

    def to_dict(self, feedback: TaskFeedback) -> dict[str, Any]:
        """
        Convert feedback to dictionary.

        Args:
            feedback: TaskFeedback object

        Returns:
            Dictionary representation
        """
        return {
            "task_id": feedback.task_id,
            "was_good_match": feedback.was_good_match,
            "routing_feedback": feedback.routing_feedback,
            "should_have_routed_to": feedback.should_have_routed_to,
            "estimated_duration": feedback.estimated_duration,
            "actual_duration": feedback.actual_duration,
            "complexity_rating": feedback.complexity_rating,
            "quality_score": feedback.quality_score,
            "required_rework": feedback.required_rework,
            "rework_reason": feedback.rework_reason,
            "unexpected_blockers": feedback.unexpected_blockers,
            "required_skills_not_tagged": feedback.required_skills_not_tagged,
            "notes": feedback.notes,
            "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        }
