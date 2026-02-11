"""
Base scope behavior interface.

Defines the abstract interface that all scope behaviors must implement.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from hopper.models import HopperInstance, Task


class TaskActionType(str, Enum):
    """Types of actions a scope behavior can take on a task."""

    DELEGATE = "delegate"      # Delegate to child instance
    HANDLE = "handle"          # Handle directly at this instance
    QUEUE = "queue"            # Add to execution queue
    ESCALATE = "escalate"      # Escalate to parent instance
    REJECT = "reject"          # Reject the task


@dataclass
class TaskAction:
    """
    Represents an action to take on a task.

    Returned by scope behaviors to indicate how to handle incoming tasks.
    """

    action_type: TaskActionType
    target_instance_id: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] | None = None

    @classmethod
    def delegate(cls, target_instance_id: str, reason: str | None = None) -> "TaskAction":
        """Create a delegate action."""
        return cls(
            action_type=TaskActionType.DELEGATE,
            target_instance_id=target_instance_id,
            reason=reason,
        )

    @classmethod
    def handle(cls, reason: str | None = None) -> "TaskAction":
        """Create a handle-directly action."""
        return cls(action_type=TaskActionType.HANDLE, reason=reason)

    @classmethod
    def queue(cls, reason: str | None = None) -> "TaskAction":
        """Create an add-to-queue action."""
        return cls(action_type=TaskActionType.QUEUE, reason=reason)

    @classmethod
    def escalate(cls, target_instance_id: str, reason: str | None = None) -> "TaskAction":
        """Create an escalate action."""
        return cls(
            action_type=TaskActionType.ESCALATE,
            target_instance_id=target_instance_id,
            reason=reason,
        )

    @classmethod
    def reject(cls, reason: str) -> "TaskAction":
        """Create a reject action."""
        return cls(action_type=TaskActionType.REJECT, reason=reason)


class BaseScopeBehavior(ABC):
    """
    Abstract base class for scope-specific behaviors.

    Each scope (Global, Project, Orchestration) implements this interface
    to define how it handles tasks and routing decisions.
    """

    @property
    @abstractmethod
    def scope_name(self) -> str:
        """Return the name of this scope."""
        pass

    @abstractmethod
    async def handle_incoming_task(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> TaskAction:
        """
        Handle an incoming task at this instance.

        Determines what action to take: delegate, handle directly,
        queue for execution, or reject.

        Args:
            task: The incoming task
            instance: The instance receiving the task

        Returns:
            TaskAction indicating what to do with the task
        """
        pass

    @abstractmethod
    async def should_delegate(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> bool:
        """
        Determine if a task should be delegated to a child instance.

        Args:
            task: Task to evaluate
            instance: Current instance

        Returns:
            True if task should be delegated
        """
        pass

    @abstractmethod
    async def find_delegation_target(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Find the best target instance for delegation.

        Args:
            task: Task to delegate
            instance: Current instance

        Returns:
            Target instance or None if no suitable target
        """
        pass

    @abstractmethod
    async def on_task_completed(
        self,
        task: Task,
        instance: HopperInstance,
    ) -> None:
        """
        Handle task completion at this instance.

        Called when a task is marked as completed. Used for
        cleanup, metrics, and notifying parent instances.

        Args:
            task: Completed task
            instance: Instance where task completed
        """
        pass

    @abstractmethod
    async def get_task_queue(
        self,
        instance: HopperInstance,
    ) -> list[Task]:
        """
        Get the current task queue for this instance.

        Args:
            instance: Instance to get queue for

        Returns:
            List of tasks in the queue
        """
        pass

    def get_config_value(
        self,
        instance: HopperInstance,
        key: str,
        default: Any = None,
    ) -> Any:
        """
        Get a configuration value from the instance config.

        Args:
            instance: Instance to get config from
            key: Config key
            default: Default value if key not found

        Returns:
            Config value or default
        """
        config = instance.config or {}
        return config.get(key, default)

    def estimate_task_complexity(self, task: Task) -> int:
        """
        Estimate task complexity for routing decisions.

        Args:
            task: Task to evaluate

        Returns:
            Complexity score (1-5)
        """
        complexity = 1

        # Description length suggests complexity
        if task.description and len(task.description) > 500:
            complexity += 1

        # Multiple tags suggest broader scope
        if task.tags and len(task.tags) > 3:
            complexity += 1

        # Dependencies add complexity
        if task.depends_on:
            complexity += 1

        # High priority often means complex
        if task.priority in ("high", "urgent"):
            complexity += 1

        return min(complexity, 5)
