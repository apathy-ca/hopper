"""
Decision recording system for routing intelligence.

Records all routing decisions to enable:
- Decision history tracking
- Feedback collection
- Performance analytics
- Future learning
"""

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from hopper.intelligence.types import (
    DecisionFeedback,
    DecisionStrategy,
    RoutingContext,
    RoutingDecision,
)

logger = logging.getLogger(__name__)


class DecisionRecord:
    """
    Complete record of a routing decision.

    Links the decision, context, and feedback together.
    """

    def __init__(
        self,
        decision_id: str,
        decision: RoutingDecision,
        context: RoutingContext,
        metadata: dict[str, Any] | None = None,
    ):
        """
        Initialize a decision record.

        Args:
            decision_id: Unique identifier for this decision.
            decision: The routing decision that was made.
            context: The context in which the decision was made.
            metadata: Additional metadata.
        """
        self.decision_id = decision_id
        self.decision = decision
        self.context = context
        self.metadata = metadata or {}
        self.recorded_at = datetime.utcnow()
        self.feedback: DecisionFeedback | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary for serialization.

        Returns:
            Dictionary representation.
        """
        return {
            "decision_id": self.decision_id,
            "decision": {
                "destination": self.decision.destination,
                "confidence": self.decision.confidence,
                "strategy": self.decision.strategy.value,
                "reasoning": self.decision.reasoning,
                "matched_rules": self.decision.matched_rules,
                "decision_factors": self.decision.decision_factors,
                "timestamp": self.decision.timestamp.isoformat(),
            },
            "context": {
                "task_id": self.context.task_id,
                "task_title": self.context.task_title,
                "task_description": self.context.task_description,
                "task_tags": self.context.task_tags,
                "task_priority": self.context.task_priority,
                "available_destinations": self.context.available_destinations,
                "source": self.context.source,
            },
            "metadata": self.metadata,
            "recorded_at": self.recorded_at.isoformat(),
            "has_feedback": self.feedback is not None,
        }


class DecisionRecorder:
    """
    Records and manages routing decisions.

    In-memory implementation for Phase 1. Phase 2 will add database persistence.
    """

    def __init__(self):
        """Initialize the decision recorder."""
        self._records: dict[str, DecisionRecord] = {}
        self._task_decisions: dict[str, list[str]] = {}  # task_id -> decision_ids
        self._strategy_decisions: dict[DecisionStrategy, list[str]] = {}

        logger.info("Initialized DecisionRecorder (in-memory)")

    async def record_decision(
        self,
        decision: RoutingDecision,
        context: RoutingContext,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record a routing decision.

        Args:
            decision: The routing decision.
            context: The routing context.
            metadata: Additional metadata.

        Returns:
            Decision ID for future reference.
        """
        decision_id = str(uuid4())

        record = DecisionRecord(
            decision_id=decision_id,
            decision=decision,
            context=context,
            metadata=metadata,
        )

        # Store record
        self._records[decision_id] = record

        # Index by task
        task_id = context.task_id
        if task_id not in self._task_decisions:
            self._task_decisions[task_id] = []
        self._task_decisions[task_id].append(decision_id)

        # Index by strategy
        strategy = decision.strategy
        if strategy not in self._strategy_decisions:
            self._strategy_decisions[strategy] = []
        self._strategy_decisions[strategy].append(decision_id)

        logger.info(
            f"Recorded decision {decision_id} for task {task_id}: "
            f"{decision.destination} (confidence: {decision.confidence:.2f})"
        )

        return decision_id

    async def add_feedback(
        self,
        decision_id: str,
        feedback: DecisionFeedback,
    ) -> None:
        """
        Add feedback to a decision.

        Args:
            decision_id: The decision to add feedback to.
            feedback: The feedback.

        Raises:
            ValueError: If decision_id not found.
        """
        if decision_id not in self._records:
            raise ValueError(f"Unknown decision ID: {decision_id}")

        record = self._records[decision_id]
        record.feedback = feedback

        logger.info(f"Added feedback to decision {decision_id}: " f"correct={feedback.correct}")

    async def get_decision(self, decision_id: str) -> DecisionRecord | None:
        """
        Get a decision record by ID.

        Args:
            decision_id: The decision ID.

        Returns:
            Decision record or None if not found.
        """
        return self._records.get(decision_id)

    async def get_decisions_for_task(self, task_id: str) -> list[DecisionRecord]:
        """
        Get all decisions for a specific task.

        Args:
            task_id: The task ID.

        Returns:
            List of decision records.
        """
        decision_ids = self._task_decisions.get(task_id, [])
        return [self._records[did] for did in decision_ids if did in self._records]

    async def get_decisions_by_strategy(self, strategy: DecisionStrategy) -> list[DecisionRecord]:
        """
        Get all decisions made by a specific strategy.

        Args:
            strategy: The decision strategy.

        Returns:
            List of decision records.
        """
        decision_ids = self._strategy_decisions.get(strategy, [])
        return [self._records[did] for did in decision_ids if did in self._records]

    async def get_decisions_by_destination(self, destination: str) -> list[DecisionRecord]:
        """
        Get all decisions for a specific destination.

        Args:
            destination: The destination.

        Returns:
            List of decision records.
        """
        return [
            record
            for record in self._records.values()
            if record.decision.destination == destination
        ]

    async def get_recent_decisions(self, limit: int = 100) -> list[DecisionRecord]:
        """
        Get recent decisions.

        Args:
            limit: Maximum number to return.

        Returns:
            List of decision records, most recent first.
        """
        sorted_records = sorted(
            self._records.values(),
            key=lambda r: r.recorded_at,
            reverse=True,
        )

        return sorted_records[:limit]

    async def get_decision_success_rate(
        self,
        strategy: DecisionStrategy | None = None,
        destination: str | None = None,
    ) -> float | None:
        """
        Calculate success rate for decisions.

        Args:
            strategy: Optional filter by strategy.
            destination: Optional filter by destination.

        Returns:
            Success rate (0.0-1.0) or None if no feedback.
        """
        # Filter records
        records = self._records.values()

        if strategy:
            records = [r for r in records if r.decision.strategy == strategy]

        if destination:
            records = [r for r in records if r.decision.destination == destination]

        # Count feedback
        total_feedback = 0
        correct_feedback = 0

        for record in records:
            if record.feedback:
                total_feedback += 1
                if record.feedback.correct:
                    correct_feedback += 1

        if total_feedback == 0:
            return None

        return correct_feedback / total_feedback

    async def get_statistics(self) -> dict[str, Any]:
        """
        Get overall statistics about recorded decisions.

        Returns:
            Statistics dictionary.
        """
        total_decisions = len(self._records)

        # Count by strategy
        decisions_by_strategy = {}
        for strategy, decision_ids in self._strategy_decisions.items():
            decisions_by_strategy[strategy.value] = len(decision_ids)

        # Count feedback
        total_feedback = 0
        correct_decisions = 0

        for record in self._records.values():
            if record.feedback:
                total_feedback += 1
                if record.feedback.correct:
                    correct_decisions += 1

        # Calculate average confidence
        if total_decisions > 0:
            avg_confidence = (
                sum(r.decision.confidence for r in self._records.values()) / total_decisions
            )
        else:
            avg_confidence = 0.0

        # High/low confidence statistics
        high_confidence_correct = 0
        high_confidence_incorrect = 0
        low_confidence_correct = 0
        low_confidence_incorrect = 0

        for record in self._records.values():
            if record.feedback:
                if record.decision.confidence >= 0.7:
                    if record.feedback.correct:
                        high_confidence_correct += 1
                    else:
                        high_confidence_incorrect += 1
                else:
                    if record.feedback.correct:
                        low_confidence_correct += 1
                    else:
                        low_confidence_incorrect += 1

        return {
            "total_decisions": total_decisions,
            "decisions_by_strategy": decisions_by_strategy,
            "total_feedback": total_feedback,
            "correct_decisions": correct_decisions,
            "average_confidence": avg_confidence,
            "high_confidence_correct": high_confidence_correct,
            "high_confidence_incorrect": high_confidence_incorrect,
            "low_confidence_correct": low_confidence_correct,
            "low_confidence_incorrect": low_confidence_incorrect,
            "overall_accuracy": (
                correct_decisions / total_feedback if total_feedback > 0 else None
            ),
        }

    async def clear_old_decisions(self, days: int = 90) -> int:
        """
        Clear decisions older than specified days.

        Args:
            days: Age threshold in days.

        Returns:
            Number of decisions cleared.
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days)

        old_decision_ids = [
            did for did, record in self._records.items() if record.recorded_at < cutoff
        ]

        for decision_id in old_decision_ids:
            record = self._records[decision_id]

            # Remove from records
            del self._records[decision_id]

            # Remove from task index
            task_id = record.context.task_id
            if task_id in self._task_decisions:
                self._task_decisions[task_id] = [
                    did for did in self._task_decisions[task_id] if did != decision_id
                ]

            # Remove from strategy index
            strategy = record.decision.strategy
            if strategy in self._strategy_decisions:
                self._strategy_decisions[strategy] = [
                    did for did in self._strategy_decisions[strategy] if did != decision_id
                ]

        logger.info(f"Cleared {len(old_decision_ids)} decisions older than {days} days")

        return len(old_decision_ids)


# Global decision recorder instance
_recorder: DecisionRecorder | None = None


def get_decision_recorder() -> DecisionRecorder:
    """
    Get the global decision recorder instance.

    Returns:
        Decision recorder instance.
    """
    global _recorder

    if _recorder is None:
        _recorder = DecisionRecorder()

    return _recorder


async def record_decision(
    decision: RoutingDecision,
    context: RoutingContext,
    metadata: dict[str, Any] | None = None,
) -> str:
    """
    Record a routing decision using the global recorder.

    Args:
        decision: The routing decision.
        context: The routing context.
        metadata: Additional metadata.

    Returns:
        Decision ID.
    """
    recorder = get_decision_recorder()
    return await recorder.record_decision(decision, context, metadata)


async def add_feedback(decision_id: str, feedback: DecisionFeedback) -> None:
    """
    Add feedback to a decision using the global recorder.

    Args:
        decision_id: The decision ID.
        feedback: The feedback.
    """
    recorder = get_decision_recorder()
    await recorder.add_feedback(decision_id, feedback)
