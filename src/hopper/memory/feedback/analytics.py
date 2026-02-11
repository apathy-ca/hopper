"""
Feedback analytics for routing accuracy analysis.
"""

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from hopper.models import Task, TaskFeedback

logger = logging.getLogger(__name__)


@dataclass
class RoutingAccuracyReport:
    """Report on routing accuracy."""

    total_feedback: int
    good_matches: int
    bad_matches: int
    accuracy_rate: float
    common_misrouting_targets: list[tuple[str, int]]
    by_instance: dict[str, dict[str, Any]]
    period_start: datetime | None = None
    period_end: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_feedback": self.total_feedback,
            "good_matches": self.good_matches,
            "bad_matches": self.bad_matches,
            "accuracy_rate": self.accuracy_rate,
            "common_misrouting_targets": [
                {"target": t, "count": c} for t, c in self.common_misrouting_targets
            ],
            "by_instance": self.by_instance,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
        }


@dataclass
class QualityReport:
    """Report on task quality metrics."""

    total_tasks: int
    average_quality_score: float
    average_complexity: float
    rework_rate: float
    tasks_with_blockers: int
    missing_skills_count: int
    by_complexity: dict[int, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_tasks": self.total_tasks,
            "average_quality_score": self.average_quality_score,
            "average_complexity": self.average_complexity,
            "rework_rate": self.rework_rate,
            "tasks_with_blockers": self.tasks_with_blockers,
            "missing_skills_count": self.missing_skills_count,
            "by_complexity": self.by_complexity,
        }


class FeedbackAnalytics:
    """
    Analytics service for feedback data.

    Provides insights on routing accuracy, quality metrics, and patterns.
    """

    def __init__(self, session: Session):
        """
        Initialize analytics service.

        Args:
            session: Database session
        """
        self.session = session

    def get_routing_accuracy(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
        instance_id: str | None = None,
    ) -> RoutingAccuracyReport:
        """
        Calculate routing accuracy metrics.

        Args:
            since: Start of period
            until: End of period
            instance_id: Filter by instance

        Returns:
            RoutingAccuracyReport
        """
        # Base query
        query = select(TaskFeedback)

        # Apply filters
        conditions = []
        if since:
            conditions.append(TaskFeedback.created_at >= since)
        if until:
            conditions.append(TaskFeedback.created_at <= until)

        if conditions:
            query = query.where(and_(*conditions))

        # Join with Task if filtering by instance
        if instance_id:
            query = query.join(Task, TaskFeedback.task_id == Task.id).where(
                Task.instance_id == instance_id
            )

        result = self.session.execute(query)
        feedback_list = list(result.scalars().all())

        # Calculate metrics
        total = len(feedback_list)
        good_matches = sum(1 for f in feedback_list if f.was_good_match)
        bad_matches = sum(1 for f in feedback_list if f.was_good_match is False)

        accuracy = good_matches / total if total > 0 else 0.0

        # Find common misrouting targets
        misrouting_targets = [
            f.should_have_routed_to
            for f in feedback_list
            if f.was_good_match is False and f.should_have_routed_to
        ]
        target_counts = Counter(misrouting_targets).most_common(5)

        # Per-instance breakdown
        by_instance = self._calculate_by_instance(feedback_list)

        return RoutingAccuracyReport(
            total_feedback=total,
            good_matches=good_matches,
            bad_matches=bad_matches,
            accuracy_rate=accuracy,
            common_misrouting_targets=target_counts,
            by_instance=by_instance,
            period_start=since,
            period_end=until,
        )

    def _calculate_by_instance(
        self,
        feedback_list: list[TaskFeedback],
    ) -> dict[str, dict[str, Any]]:
        """Calculate per-instance metrics."""
        # Get tasks for feedback
        task_ids = [f.task_id for f in feedback_list]
        if not task_ids:
            return {}

        task_query = select(Task).where(Task.id.in_(task_ids))
        result = self.session.execute(task_query)
        tasks = {t.id: t for t in result.scalars().all()}

        # Group feedback by instance
        by_instance: dict[str, list[TaskFeedback]] = {}
        for feedback in feedback_list:
            task = tasks.get(feedback.task_id)
            if task and task.instance_id:
                if task.instance_id not in by_instance:
                    by_instance[task.instance_id] = []
                by_instance[task.instance_id].append(feedback)

        # Calculate per-instance metrics
        result_dict = {}
        for instance_id, feedbacks in by_instance.items():
            total = len(feedbacks)
            good = sum(1 for f in feedbacks if f.was_good_match)
            accuracy = good / total if total > 0 else 0.0

            result_dict[instance_id] = {
                "total": total,
                "good_matches": good,
                "bad_matches": total - good,
                "accuracy_rate": accuracy,
            }

        return result_dict

    def get_quality_report(
        self,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> QualityReport:
        """
        Generate quality metrics report.

        Args:
            since: Start of period
            until: End of period

        Returns:
            QualityReport
        """
        # Base query
        query = select(TaskFeedback)

        conditions = []
        if since:
            conditions.append(TaskFeedback.created_at >= since)
        if until:
            conditions.append(TaskFeedback.created_at <= until)

        if conditions:
            query = query.where(and_(*conditions))

        result = self.session.execute(query)
        feedback_list = list(result.scalars().all())

        total = len(feedback_list)

        # Quality scores
        quality_scores = [f.quality_score for f in feedback_list if f.quality_score is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        # Complexity
        complexities = [f.complexity_rating for f in feedback_list if f.complexity_rating is not None]
        avg_complexity = sum(complexities) / len(complexities) if complexities else 0.0

        # Rework
        rework_count = sum(1 for f in feedback_list if f.required_rework)
        rework_rate = rework_count / total if total > 0 else 0.0

        # Blockers
        tasks_with_blockers = sum(
            1 for f in feedback_list
            if f.unexpected_blockers and f.unexpected_blockers.get("blockers")
        )

        # Missing skills
        missing_skills = sum(
            1 for f in feedback_list
            if f.required_skills_not_tagged and f.required_skills_not_tagged.get("skills")
        )

        # By complexity
        by_complexity = self._calculate_by_complexity(feedback_list)

        return QualityReport(
            total_tasks=total,
            average_quality_score=avg_quality,
            average_complexity=avg_complexity,
            rework_rate=rework_rate,
            tasks_with_blockers=tasks_with_blockers,
            missing_skills_count=missing_skills,
            by_complexity=by_complexity,
        )

    def _calculate_by_complexity(
        self,
        feedback_list: list[TaskFeedback],
    ) -> dict[int, dict[str, Any]]:
        """Calculate metrics by complexity rating."""
        by_complexity: dict[int, list[TaskFeedback]] = {}

        for feedback in feedback_list:
            if feedback.complexity_rating is not None:
                if feedback.complexity_rating not in by_complexity:
                    by_complexity[feedback.complexity_rating] = []
                by_complexity[feedback.complexity_rating].append(feedback)

        result = {}
        for rating, feedbacks in sorted(by_complexity.items()):
            quality_scores = [f.quality_score for f in feedbacks if f.quality_score is not None]
            avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

            rework_count = sum(1 for f in feedbacks if f.required_rework)
            good_matches = sum(1 for f in feedbacks if f.was_good_match)

            result[rating] = {
                "count": len(feedbacks),
                "average_quality": avg_quality,
                "rework_count": rework_count,
                "good_matches": good_matches,
            }

        return result

    def get_misrouting_patterns(
        self,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Analyze patterns in misrouted tasks.

        Args:
            limit: Maximum patterns to return

        Returns:
            List of pattern dictionaries
        """
        # Get misrouted feedback
        query = (
            select(TaskFeedback)
            .where(TaskFeedback.was_good_match == False)  # noqa: E712
            .where(TaskFeedback.should_have_routed_to.isnot(None))
        )

        result = self.session.execute(query)
        misrouted = list(result.scalars().all())

        # Get associated tasks
        task_ids = [f.task_id for f in misrouted]
        if not task_ids:
            return []

        task_query = select(Task).where(Task.id.in_(task_ids))
        tasks = {t.id: t for t in self.session.execute(task_query).scalars().all()}

        # Analyze patterns: actual -> should_have
        patterns: dict[tuple[str, str], list[dict]] = {}

        for feedback in misrouted:
            task = tasks.get(feedback.task_id)
            if not task or not task.instance_id:
                continue

            key = (task.instance_id, feedback.should_have_routed_to or "unknown")

            if key not in patterns:
                patterns[key] = []

            patterns[key].append({
                "task_id": feedback.task_id,
                "task_title": task.title,
                "tags": task.tags,
                "feedback": feedback.routing_feedback,
            })

        # Convert to list and sort by frequency
        result_list = []
        for (actual, suggested), examples in sorted(
            patterns.items(), key=lambda x: len(x[1]), reverse=True
        )[:limit]:
            # Find common tags in misrouted tasks
            all_tags: Counter[str] = Counter()
            for ex in examples:
                if ex["tags"]:
                    all_tags.update(ex["tags"].keys())

            result_list.append({
                "routed_to": actual,
                "should_have_been": suggested,
                "count": len(examples),
                "common_tags": all_tags.most_common(5),
                "examples": examples[:3],  # Limit examples
            })

        return result_list

    def get_summary(
        self,
        days: int = 30,
    ) -> dict[str, Any]:
        """
        Get summary of feedback for a period.

        Args:
            days: Number of days to analyze

        Returns:
            Summary dictionary
        """
        since = datetime.utcnow() - timedelta(days=days)

        accuracy = self.get_routing_accuracy(since=since)
        quality = self.get_quality_report(since=since)

        return {
            "period_days": days,
            "routing_accuracy": accuracy.to_dict(),
            "quality_metrics": quality.to_dict(),
            "generated_at": datetime.utcnow().isoformat(),
        }
