"""
Routing context models for working memory.

Defines the context structure used during routing decisions.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SimilarTask:
    """Reference to a similar past task."""

    task_id: str
    title: str
    similarity_score: float
    routed_to: str | None = None
    outcome_success: bool | None = None


@dataclass
class InstanceInfo:
    """Information about an available instance."""

    instance_id: str
    name: str
    scope: str
    status: str
    capabilities: list[str] = field(default_factory=list)
    current_load: int = 0
    max_capacity: int = 10


@dataclass
class RecentDecision:
    """A recent routing decision for context."""

    task_id: str
    task_title: str
    routed_to: str
    routed_at: datetime
    confidence: float
    outcome: str | None = None  # success, failure, pending


@dataclass
class RoutingContext:
    """
    Context for making routing decisions.

    Aggregates all relevant information for the routing engine.
    """

    # Task being routed
    task_id: str
    task_title: str
    task_tags: list[str] = field(default_factory=list)
    task_priority: str = "medium"

    # Similar past tasks
    similar_tasks: list[SimilarTask] = field(default_factory=list)

    # Available instances
    available_instances: list[InstanceInfo] = field(default_factory=list)

    # Recent routing decisions
    recent_decisions: list[RecentDecision] = field(default_factory=list)

    # Session info
    session_id: str | None = None
    user_id: str | None = None

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None

    # Additional context
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "task_id": self.task_id,
            "task_title": self.task_title,
            "task_tags": self.task_tags,
            "task_priority": self.task_priority,
            "similar_tasks": [
                {
                    "task_id": st.task_id,
                    "title": st.title,
                    "similarity_score": st.similarity_score,
                    "routed_to": st.routed_to,
                    "outcome_success": st.outcome_success,
                }
                for st in self.similar_tasks
            ],
            "available_instances": [
                {
                    "instance_id": inst.instance_id,
                    "name": inst.name,
                    "scope": inst.scope,
                    "status": inst.status,
                    "capabilities": inst.capabilities,
                    "current_load": inst.current_load,
                    "max_capacity": inst.max_capacity,
                }
                for inst in self.available_instances
            ],
            "recent_decisions": [
                {
                    "task_id": rd.task_id,
                    "task_title": rd.task_title,
                    "routed_to": rd.routed_to,
                    "routed_at": rd.routed_at.isoformat(),
                    "confidence": rd.confidence,
                    "outcome": rd.outcome,
                }
                for rd in self.recent_decisions
            ],
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RoutingContext":
        """Create from dictionary."""
        similar_tasks = [
            SimilarTask(
                task_id=st["task_id"],
                title=st["title"],
                similarity_score=st["similarity_score"],
                routed_to=st.get("routed_to"),
                outcome_success=st.get("outcome_success"),
            )
            for st in data.get("similar_tasks", [])
        ]

        available_instances = [
            InstanceInfo(
                instance_id=inst["instance_id"],
                name=inst["name"],
                scope=inst["scope"],
                status=inst["status"],
                capabilities=inst.get("capabilities", []),
                current_load=inst.get("current_load", 0),
                max_capacity=inst.get("max_capacity", 10),
            )
            for inst in data.get("available_instances", [])
        ]

        recent_decisions = [
            RecentDecision(
                task_id=rd["task_id"],
                task_title=rd["task_title"],
                routed_to=rd["routed_to"],
                routed_at=datetime.fromisoformat(rd["routed_at"]),
                confidence=rd["confidence"],
                outcome=rd.get("outcome"),
            )
            for rd in data.get("recent_decisions", [])
        ]

        return cls(
            task_id=data["task_id"],
            task_title=data["task_title"],
            task_tags=data.get("task_tags", []),
            task_priority=data.get("task_priority", "medium"),
            similar_tasks=similar_tasks,
            available_instances=available_instances,
            recent_decisions=recent_decisions,
            session_id=data.get("session_id"),
            user_id=data.get("user_id"),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=(
                datetime.fromisoformat(data["expires_at"])
                if data.get("expires_at")
                else None
            ),
            metadata=data.get("metadata", {}),
        )

    def get_successful_routings(self) -> list[SimilarTask]:
        """Get similar tasks that were successfully routed."""
        return [st for st in self.similar_tasks if st.outcome_success is True]

    def get_instance_by_id(self, instance_id: str) -> InstanceInfo | None:
        """Get instance info by ID."""
        for inst in self.available_instances:
            if inst.instance_id == instance_id:
                return inst
        return None

    def get_instances_with_capacity(self) -> list[InstanceInfo]:
        """Get instances that have capacity for more tasks."""
        return [
            inst
            for inst in self.available_instances
            if inst.current_load < inst.max_capacity and inst.status == "running"
        ]
