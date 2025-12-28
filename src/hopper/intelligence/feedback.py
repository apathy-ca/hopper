"""
Feedback collection system for routing intelligence.

Enables continuous improvement by:
- Collecting feedback on routing decisions
- Analyzing feedback patterns
- Adjusting routing behavior based on feedback
- Generating feedback analytics
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from hopper.intelligence.decision_recorder import (
    DecisionRecord,
    get_decision_recorder,
)
from hopper.intelligence.types import DecisionFeedback, DecisionStrategy

logger = logging.getLogger(__name__)


class FeedbackCollector:
    """
    Collects and analyzes feedback on routing decisions.

    Provides insights into routing performance and identifies
    areas for improvement.
    """

    def __init__(self):
        """Initialize the feedback collector."""
        self.recorder = get_decision_recorder()
        logger.info("Initialized FeedbackCollector")

    async def provide_feedback(
        self,
        decision_id: str,
        correct: bool,
        actual_destination: Optional[str] = None,
        rating: Optional[float] = None,
        notes: Optional[str] = None,
        feedback_by: Optional[str] = None,
    ) -> DecisionFeedback:
        """
        Provide feedback on a routing decision.

        Args:
            decision_id: The decision to provide feedback on.
            correct: Whether the routing was correct.
            actual_destination: If incorrect, what was the right destination.
            rating: Optional rating (0.0-1.0) for more nuanced feedback.
            notes: Additional notes.
            feedback_by: User ID who provided feedback.

        Returns:
            The created feedback object.

        Raises:
            ValueError: If decision_id not found or feedback invalid.
        """
        # Validate decision exists
        decision = await self.recorder.get_decision(decision_id)
        if not decision:
            raise ValueError(f"Unknown decision ID: {decision_id}")

        # Validate rating if provided
        if rating is not None and not (0.0 <= rating <= 1.0):
            raise ValueError("Rating must be between 0.0 and 1.0")

        # If incorrect, require actual_destination
        if not correct and not actual_destination:
            logger.warning(
                f"Feedback for decision {decision_id} marked incorrect "
                "but no actual_destination provided"
            )

        # Create feedback
        feedback = DecisionFeedback(
            decision_id=decision_id,
            correct=correct,
            actual_destination=actual_destination,
            rating=rating,
            notes=notes,
            feedback_by=feedback_by,
        )

        # Record feedback
        await self.recorder.add_feedback(decision_id, feedback)

        logger.info(
            f"Feedback provided for decision {decision_id}: "
            f"correct={correct}, actual={actual_destination}"
        )

        return feedback

    async def get_feedback_summary(
        self,
        strategy: Optional[DecisionStrategy] = None,
        destination: Optional[str] = None,
        days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get summary of feedback.

        Args:
            strategy: Optional filter by strategy.
            destination: Optional filter by destination.
            days: Optional filter by recent days.

        Returns:
            Feedback summary statistics.
        """
        # Get all decisions
        if strategy:
            records = await self.recorder.get_decisions_by_strategy(strategy)
        elif destination:
            records = await self.recorder.get_decisions_by_destination(destination)
        else:
            records = await self.recorder.get_recent_decisions(limit=10000)

        # Filter by time if specified
        if days:
            cutoff = datetime.utcnow() - timedelta(days=days)
            records = [r for r in records if r.recorded_at >= cutoff]

        # Collect statistics
        total_decisions = len(records)
        total_feedback = 0
        correct_feedback = 0
        incorrect_feedback = 0
        ratings = []

        for record in records:
            if record.feedback:
                total_feedback += 1
                if record.feedback.correct:
                    correct_feedback += 1
                else:
                    incorrect_feedback += 1

                if record.feedback.rating is not None:
                    ratings.append(record.feedback.rating)

        # Calculate accuracy
        accuracy = correct_feedback / total_feedback if total_feedback > 0 else None

        # Calculate average rating
        avg_rating = sum(ratings) / len(ratings) if ratings else None

        return {
            "total_decisions": total_decisions,
            "total_feedback": total_feedback,
            "correct_feedback": correct_feedback,
            "incorrect_feedback": incorrect_feedback,
            "accuracy": accuracy,
            "average_rating": avg_rating,
            "feedback_coverage": (
                total_feedback / total_decisions if total_decisions > 0 else 0.0
            ),
        }

    async def get_problematic_routes(
        self, min_samples: int = 5, max_accuracy: float = 0.7
    ) -> List[Tuple[str, float, int]]:
        """
        Identify routes with low accuracy.

        Args:
            min_samples: Minimum feedback samples required.
            max_accuracy: Maximum accuracy to consider problematic.

        Returns:
            List of (destination, accuracy, sample_count) tuples.
        """
        # Get all unique destinations
        all_records = await self.recorder.get_recent_decisions(limit=10000)
        destinations = set(r.decision.destination for r in all_records)

        problematic = []

        for destination in destinations:
            records = await self.recorder.get_decisions_by_destination(destination)

            # Count feedback
            total_feedback = 0
            correct = 0

            for record in records:
                if record.feedback:
                    total_feedback += 1
                    if record.feedback.correct:
                        correct += 1

            if total_feedback >= min_samples:
                accuracy = correct / total_feedback

                if accuracy <= max_accuracy:
                    problematic.append((destination, accuracy, total_feedback))

        # Sort by accuracy (worst first)
        problematic.sort(key=lambda x: x[1])

        return problematic

    async def get_high_performing_routes(
        self, min_samples: int = 5, min_accuracy: float = 0.9
    ) -> List[Tuple[str, float, int]]:
        """
        Identify routes with high accuracy.

        Args:
            min_samples: Minimum feedback samples required.
            min_accuracy: Minimum accuracy to consider high-performing.

        Returns:
            List of (destination, accuracy, sample_count) tuples.
        """
        # Get all unique destinations
        all_records = await self.recorder.get_recent_decisions(limit=10000)
        destinations = set(r.decision.destination for r in all_records)

        high_performing = []

        for destination in destinations:
            records = await self.recorder.get_decisions_by_destination(destination)

            # Count feedback
            total_feedback = 0
            correct = 0

            for record in records:
                if record.feedback:
                    total_feedback += 1
                    if record.feedback.correct:
                        correct += 1

            if total_feedback >= min_samples:
                accuracy = correct / total_feedback

                if accuracy >= min_accuracy:
                    high_performing.append((destination, accuracy, total_feedback))

        # Sort by accuracy (best first)
        high_performing.sort(key=lambda x: x[1], reverse=True)

        return high_performing

    async def get_confidence_calibration(
        self,
        bins: int = 10,
    ) -> Dict[str, Any]:
        """
        Analyze how well confidence scores match actual accuracy.

        Good calibration means:
        - Decisions with 0.9 confidence are correct 90% of the time
        - Decisions with 0.5 confidence are correct 50% of the time

        Args:
            bins: Number of confidence bins (default 10).

        Returns:
            Calibration analysis.
        """
        all_records = await self.recorder.get_recent_decisions(limit=10000)

        # Initialize bins
        bin_size = 1.0 / bins
        bin_data = {i: {"count": 0, "correct": 0} for i in range(bins)}

        # Collect data
        for record in all_records:
            if record.feedback:
                confidence = record.decision.confidence
                bin_idx = min(int(confidence / bin_size), bins - 1)

                bin_data[bin_idx]["count"] += 1
                if record.feedback.correct:
                    bin_data[bin_idx]["correct"] += 1

        # Calculate calibration
        calibration = {}

        for bin_idx in range(bins):
            bin_min = bin_idx * bin_size
            bin_max = (bin_idx + 1) * bin_size
            bin_center = (bin_min + bin_max) / 2

            count = bin_data[bin_idx]["count"]
            correct = bin_data[bin_idx]["correct"]

            accuracy = correct / count if count > 0 else None

            calibration[f"{bin_min:.1f}-{bin_max:.1f}"] = {
                "expected_accuracy": bin_center,
                "actual_accuracy": accuracy,
                "sample_count": count,
                "calibration_error": (
                    abs(bin_center - accuracy) if accuracy is not None else None
                ),
            }

        return calibration

    async def get_feedback_trends(
        self, days: int = 30, interval_days: int = 7
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get feedback trends over time.

        Args:
            days: Number of days to analyze.
            interval_days: Interval for aggregation.

        Returns:
            Trends by time period.
        """
        all_records = await self.recorder.get_recent_decisions(limit=10000)

        cutoff = datetime.utcnow() - timedelta(days=days)
        recent_records = [r for r in all_records if r.recorded_at >= cutoff]

        # Create time intervals
        intervals = []
        current_start = cutoff

        while current_start < datetime.utcnow():
            current_end = current_start + timedelta(days=interval_days)
            intervals.append((current_start, current_end))
            current_start = current_end

        # Aggregate by interval
        trends = []

        for start, end in intervals:
            interval_records = [
                r for r in recent_records if start <= r.recorded_at < end
            ]

            total = len(interval_records)
            total_feedback = 0
            correct = 0

            for record in interval_records:
                if record.feedback:
                    total_feedback += 1
                    if record.feedback.correct:
                        correct += 1

            accuracy = correct / total_feedback if total_feedback > 0 else None

            trends.append(
                {
                    "period_start": start.isoformat(),
                    "period_end": end.isoformat(),
                    "total_decisions": total,
                    "total_feedback": total_feedback,
                    "accuracy": accuracy,
                }
            )

        return {"intervals": trends}

    async def suggest_rule_improvements(
        self, min_samples: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Suggest improvements to routing rules based on feedback.

        Args:
            min_samples: Minimum samples to make suggestions.

        Returns:
            List of improvement suggestions.
        """
        suggestions = []

        # Get problematic routes
        problematic = await self.get_problematic_routes(min_samples=min_samples)

        for destination, accuracy, count in problematic:
            # Get decisions for this destination
            records = await self.recorder.get_decisions_by_destination(destination)

            # Analyze incorrect decisions
            incorrect_records = [r for r in records if r.feedback and not r.feedback.correct]

            if incorrect_records:
                # Find common patterns in incorrect decisions
                common_keywords = self._find_common_keywords(incorrect_records)
                common_tags = self._find_common_tags(incorrect_records)

                suggestions.append(
                    {
                        "destination": destination,
                        "current_accuracy": accuracy,
                        "sample_count": count,
                        "suggestion_type": "adjust_rules",
                        "details": {
                            "common_keywords_in_errors": common_keywords,
                            "common_tags_in_errors": common_tags,
                            "recommendation": f"Consider excluding these keywords/tags "
                            f"from rules targeting {destination}",
                        },
                    }
                )

        return suggestions

    def _find_common_keywords(self, records: List[DecisionRecord]) -> List[str]:
        """Find common keywords in task titles/descriptions."""
        # Simple keyword extraction (could be enhanced)
        from collections import Counter
        import re

        all_words = []

        for record in records:
            text = f"{record.context.task_title} {record.context.task_description}"
            words = re.findall(r"\b\w+\b", text.lower())
            all_words.extend(words)

        # Get most common (excluding very common words)
        stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for"}
        filtered_words = [w for w in all_words if w not in stopwords]

        counter = Counter(filtered_words)
        most_common = counter.most_common(10)

        return [word for word, count in most_common if count >= 2]

    def _find_common_tags(self, records: List[DecisionRecord]) -> List[str]:
        """Find common tags in tasks."""
        from collections import Counter

        all_tags = []

        for record in records:
            all_tags.extend(record.context.task_tags)

        counter = Counter(all_tags)
        most_common = counter.most_common(10)

        return [tag for tag, count in most_common if count >= 2]


# Global feedback collector instance
_collector: Optional[FeedbackCollector] = None


def get_feedback_collector() -> FeedbackCollector:
    """
    Get the global feedback collector instance.

    Returns:
        Feedback collector instance.
    """
    global _collector

    if _collector is None:
        _collector = FeedbackCollector()

    return _collector


async def provide_feedback(
    decision_id: str,
    correct: bool,
    actual_destination: Optional[str] = None,
    rating: Optional[float] = None,
    notes: Optional[str] = None,
    feedback_by: Optional[str] = None,
) -> DecisionFeedback:
    """
    Provide feedback on a routing decision using the global collector.

    Args:
        decision_id: The decision to provide feedback on.
        correct: Whether the routing was correct.
        actual_destination: If incorrect, what was the right destination.
        rating: Optional rating (0.0-1.0).
        notes: Additional notes.
        feedback_by: User ID who provided feedback.

    Returns:
        The created feedback object.
    """
    collector = get_feedback_collector()
    return await collector.provide_feedback(
        decision_id=decision_id,
        correct=correct,
        actual_destination=actual_destination,
        rating=rating,
        notes=notes,
        feedback_by=feedback_by,
    )
