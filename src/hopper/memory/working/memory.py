"""
Working Memory implementation.

Provides immediate context storage for routing decisions.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from hopper.models import HopperInstance, InstanceStatus, RoutingDecision, Task

from .backends import LocalBackend
from .backends.base import BaseBackend
from .context import InstanceInfo, RecentDecision, RoutingContext, SimilarTask

logger = logging.getLogger(__name__)


class WorkingMemory:
    """
    Working memory for routing context.

    Provides fast access to routing-relevant information:
    - Similar past tasks
    - Available instances
    - Recent routing decisions
    """

    def __init__(
        self,
        backend: BaseBackend | None = None,
        default_ttl: int = 3600,  # 1 hour
        max_similar_tasks: int = 10,
        max_recent_decisions: int = 20,
    ):
        """
        Initialize working memory.

        Args:
            backend: Storage backend (default: LocalBackend)
            default_ttl: Default TTL in seconds
            max_similar_tasks: Max similar tasks to include
            max_recent_decisions: Max recent decisions to include
        """
        self._backend = backend or LocalBackend()
        self._default_ttl = default_ttl
        self._max_similar_tasks = max_similar_tasks
        self._max_recent_decisions = max_recent_decisions

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "WorkingMemory":
        """
        Create from configuration dict.

        Args:
            config: Configuration with keys:
                - backend: "local" or "redis"
                - default_ttl: TTL in seconds
                - max_entries: Max entries (for local)
                - redis_url: Redis URL (for redis)
        """
        backend_type = config.get("backend", "local")
        default_ttl = config.get("default_ttl", 3600)
        max_similar = config.get("max_similar_tasks", 10)
        max_recent = config.get("max_recent_decisions", 20)

        if backend_type == "redis":
            from .backends.redis import RedisBackend

            backend = RedisBackend(
                url=config.get("redis_url", "redis://localhost:6379/0"),
                key_prefix=config.get("key_prefix", "hopper:working:"),
            )
        else:
            backend = LocalBackend(
                max_entries=config.get("max_entries", 10000),
            )

        return cls(
            backend=backend,
            default_ttl=default_ttl,
            max_similar_tasks=max_similar,
            max_recent_decisions=max_recent,
        )

    def _context_key(self, task_id: str) -> str:
        """Generate context key for a task."""
        return f"context:{task_id}"

    def _session_key(self, session_id: str) -> str:
        """Generate key for session context."""
        return f"session:{session_id}"

    def get_context(self, task_id: str) -> RoutingContext | None:
        """
        Get stored routing context for a task.

        Args:
            task_id: Task ID

        Returns:
            RoutingContext or None if not found
        """
        key = self._context_key(task_id)
        data = self._backend.get(key)
        if data is None:
            return None
        return RoutingContext.from_dict(data)

    def set_context(
        self,
        context: RoutingContext,
        ttl: int | None = None,
    ) -> bool:
        """
        Store routing context for a task.

        Args:
            context: RoutingContext to store
            ttl: TTL in seconds (default: self._default_ttl)

        Returns:
            True if successful
        """
        key = self._context_key(context.task_id)
        return self._backend.set(
            key,
            context.to_dict(),
            ttl or self._default_ttl,
        )

    def delete_context(self, task_id: str) -> bool:
        """
        Delete context for a task.

        Args:
            task_id: Task ID

        Returns:
            True if deleted
        """
        key = self._context_key(task_id)
        return self._backend.delete(key)

    def build_routing_context(
        self,
        task: Task,
        session: Session,
        session_id: str | None = None,
    ) -> RoutingContext:
        """
        Build fresh routing context for a task.

        Aggregates:
        - Task information
        - Available instances
        - Recent routing decisions
        - Similar tasks (placeholder - will be enhanced in semantic-search worker)

        Args:
            task: Task to route
            session: Database session
            session_id: Optional session ID

        Returns:
            RoutingContext
        """
        # Get available instances
        available_instances = self._get_available_instances(session)

        # Get recent decisions
        recent_decisions = self._get_recent_decisions(session)

        # Get task tags as list
        tags = []
        if task.tags:
            if isinstance(task.tags, dict):
                tags = list(task.tags.keys())
            elif isinstance(task.tags, list):
                tags = task.tags

        # Build context
        context = RoutingContext(
            task_id=task.id,
            task_title=task.title,
            task_tags=tags,
            task_priority=task.priority or "medium",
            similar_tasks=[],  # Will be populated by semantic-search worker
            available_instances=available_instances,
            recent_decisions=recent_decisions,
            session_id=session_id,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=self._default_ttl),
        )

        # Store the context
        self.set_context(context)

        return context

    def _get_available_instances(self, session: Session) -> list[InstanceInfo]:
        """Get available instances for routing."""
        from sqlalchemy import select

        query = select(HopperInstance).where(
            HopperInstance.status.in_([InstanceStatus.RUNNING, InstanceStatus.CREATED])
        )
        result = session.execute(query)
        instances = result.scalars().all()

        return [
            InstanceInfo(
                instance_id=inst.id,
                name=inst.name,
                scope=inst.scope.value if hasattr(inst.scope, "value") else str(inst.scope),
                status=inst.status.value if hasattr(inst.status, "value") else str(inst.status),
                capabilities=inst.config.get("capabilities", []) if inst.config else [],
                current_load=inst.runtime_metadata.get("active_tasks", 0)
                if inst.runtime_metadata
                else 0,
                max_capacity=inst.config.get("max_concurrent_tasks", 10)
                if inst.config
                else 10,
            )
            for inst in instances
        ]

    def _get_recent_decisions(self, session: Session) -> list[RecentDecision]:
        """Get recent routing decisions."""
        from sqlalchemy import select

        query = (
            select(RoutingDecision)
            .order_by(RoutingDecision.decided_at.desc())
            .limit(self._max_recent_decisions)
        )
        result = session.execute(query)
        decisions = result.scalars().all()

        recent = []
        for decision in decisions:
            # Get task title
            task_title = ""
            if decision.task:
                task_title = decision.task.title

            recent.append(
                RecentDecision(
                    task_id=decision.task_id,
                    task_title=task_title,
                    routed_to=decision.target_project or "",
                    routed_at=decision.decided_at,
                    confidence=decision.confidence_score or 0.0,
                    outcome=None,  # Will be enhanced with feedback
                )
            )

        return recent

    def add_similar_tasks(
        self,
        task_id: str,
        similar_tasks: list[SimilarTask],
    ) -> bool:
        """
        Add similar tasks to existing context.

        Used by semantic-search worker to enhance context.

        Args:
            task_id: Task ID
            similar_tasks: Similar tasks to add

        Returns:
            True if successful
        """
        context = self.get_context(task_id)
        if context is None:
            return False

        context.similar_tasks = similar_tasks[: self._max_similar_tasks]
        return self.set_context(context)

    def update_decision_outcome(
        self,
        task_id: str,
        outcome: str,
    ) -> bool:
        """
        Update outcome for a routing decision in context.

        Args:
            task_id: Task ID
            outcome: Outcome (success, failure, pending)

        Returns:
            True if successful
        """
        # Update in recent decisions across all contexts
        # This is a simplified implementation - production would
        # use a more efficient approach
        for key in self._backend.keys("context:*"):
            data = self._backend.get(key)
            if data:
                context = RoutingContext.from_dict(data)
                updated = False
                for decision in context.recent_decisions:
                    if decision.task_id == task_id:
                        decision.outcome = outcome
                        updated = True
                if updated:
                    self._backend.set(key, context.to_dict())

        return True

    def clear_expired(self) -> int:
        """Clear expired entries."""
        return self._backend.clear_expired()

    def clear_all(self) -> int:
        """Clear all entries."""
        return self._backend.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        base_stats = {
            "backend": type(self._backend).__name__,
            "default_ttl": self._default_ttl,
            "max_similar_tasks": self._max_similar_tasks,
            "max_recent_decisions": self._max_recent_decisions,
            "total_contexts": self._backend.size(),
        }

        # Add backend-specific stats
        if hasattr(self._backend, "get_stats"):
            base_stats.update(self._backend.get_stats())

        return base_stats
