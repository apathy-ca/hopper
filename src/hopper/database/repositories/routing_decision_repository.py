"""
Routing Decision repository for tracking routing outcomes.
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models.routing_decision import RoutingDecision

from .base import BaseRepository


class RoutingDecisionRepository(BaseRepository[RoutingDecision]):
    """Repository for RoutingDecision model with custom queries."""

    def __init__(self, session: Session):
        """Initialize RoutingDecisionRepository."""
        super().__init__(RoutingDecision, session)

    def get_by_task(self, task_id: str) -> RoutingDecision | None:
        """
        Get routing decision for a specific task.

        Args:
            task_id: Task ID

        Returns:
            RoutingDecision or None if not found
        """
        return self.get(task_id)

    def get_decisions_by_project(
        self, project: str, skip: int = 0, limit: int | None = None
    ) -> list[RoutingDecision]:
        """
        Get all routing decisions for a specific project.

        Args:
            project: Project name
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of routing decisions for the project
        """
        return self.filter(filters={"project": project}, skip=skip, limit=limit)

    def get_decisions_by_strategy(
        self, decided_by: str, skip: int = 0, limit: int | None = None
    ) -> list[RoutingDecision]:
        """
        Get all routing decisions made by a specific strategy.

        Args:
            decided_by: Decision strategy (e.g., "rules", "llm", "sage")
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of routing decisions made by the strategy
        """
        return self.filter(filters={"decided_by": decided_by}, skip=skip, limit=limit)

    def get_recent_decisions(
        self, limit: int = 10, hours: int | None = None
    ) -> list[RoutingDecision]:
        """
        Get recent routing decisions.

        Args:
            limit: Maximum number of decisions to return
            hours: Only return decisions from the last N hours (optional)

        Returns:
            List of recent routing decisions
        """
        query = select(RoutingDecision).order_by(RoutingDecision.decided_at.desc())

        if hours:
            cutoff_time = datetime.utcnow() - timedelta(hours=hours)
            query = query.where(RoutingDecision.decided_at >= cutoff_time)

        query = query.limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_decisions_with_low_confidence(
        self, threshold: float = 0.7, skip: int = 0, limit: int | None = None
    ) -> list[RoutingDecision]:
        """
        Get routing decisions with confidence below a threshold.

        Args:
            threshold: Confidence threshold (0.0 to 1.0)
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of low-confidence routing decisions
        """
        query = select(RoutingDecision).where(RoutingDecision.confidence < threshold)

        query = query.offset(skip)
        if limit:
            query = query.limit(limit)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def get_average_decision_time(self, decided_by: str | None = None) -> float | None:
        """
        Get average decision time in milliseconds.

        Args:
            decided_by: Optional strategy to filter by

        Returns:
            Average decision time in ms or None if no decisions
        """
        from sqlalchemy import func

        query = select(func.avg(RoutingDecision.decision_time_ms))

        if decided_by:
            query = query.where(RoutingDecision.decided_by == decided_by)

        result = self.session.execute(query)
        return result.scalar()

    def get_average_confidence(self, decided_by: str | None = None) -> float | None:
        """
        Get average confidence score.

        Args:
            decided_by: Optional strategy to filter by

        Returns:
            Average confidence score or None if no decisions
        """
        from sqlalchemy import func

        query = select(func.avg(RoutingDecision.confidence))

        if decided_by:
            query = query.where(RoutingDecision.decided_by == decided_by)

        result = self.session.execute(query)
        return result.scalar()

    def get_decision_analytics(self) -> dict:
        """
        Get analytics about routing decisions.

        Returns:
            Dictionary with routing decision analytics
        """
        from sqlalchemy import func

        # Total decisions
        total = self.count()

        # Decisions by strategy
        query = select(
            RoutingDecision.decided_by,
            func.count(RoutingDecision.task_id),
            func.avg(RoutingDecision.confidence),
            func.avg(RoutingDecision.decision_time_ms),
        ).group_by(RoutingDecision.decided_by)
        result = self.session.execute(query)
        strategy_stats = {}
        for strategy, count, avg_conf, avg_time in result.all():
            strategy_stats[strategy or "unknown"] = {
                "count": count,
                "avg_confidence": float(avg_conf) if avg_conf else None,
                "avg_decision_time_ms": float(avg_time) if avg_time else None,
            }

        return {
            "total_decisions": total,
            "strategy_stats": strategy_stats,
            "overall_avg_confidence": self.get_average_confidence(),
            "overall_avg_decision_time_ms": self.get_average_decision_time(),
        }
