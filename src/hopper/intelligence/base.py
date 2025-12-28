"""
Base intelligence interface for task routing.

Defines the abstract interface that all routing intelligence implementations
must follow, whether rules-based, LLM-based, or Sage-based.
"""

from abc import ABC, abstractmethod
from typing import Any

from hopper.intelligence.types import RoutingContext, RoutingDecision


class BaseIntelligence(ABC):
    """
    Abstract base class for routing intelligence implementations.

    All routing strategies (rules, LLM, Sage) must implement this interface
    to provide consistent routing behavior across the system.
    """

    @abstractmethod
    async def route_task(
        self,
        context: RoutingContext,
    ) -> RoutingDecision:
        """
        Route a task to the most appropriate destination.

        Args:
            context: The routing context containing task information,
                    available destinations, and historical data.

        Returns:
            A routing decision with destination, confidence score, and reasoning.

        Raises:
            RoutingError: If routing fails or no suitable destination is found.
        """
        pass

    @abstractmethod
    async def suggest_destinations(
        self,
        context: RoutingContext,
        limit: int = 5,
    ) -> list[RoutingDecision]:
        """
        Suggest multiple possible destinations with confidence scores.

        Useful for presenting routing options to users or for getting
        multiple routing alternatives.

        Args:
            context: The routing context.
            limit: Maximum number of suggestions to return.

        Returns:
            List of routing decisions, ordered by confidence (highest first).
        """
        pass

    @abstractmethod
    async def record_decision(
        self,
        decision: RoutingDecision,
        context: RoutingContext,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record a routing decision for future learning and analysis.

        Args:
            decision: The routing decision that was made.
            context: The context in which the decision was made.
            metadata: Additional metadata to store with the decision.

        Returns:
            Decision ID for future reference and feedback.
        """
        pass

    @abstractmethod
    async def provide_feedback(
        self,
        decision_id: str,
        correct: bool,
        actual_destination: str | None = None,
        notes: str | None = None,
    ) -> None:
        """
        Provide feedback on a routing decision for learning.

        Args:
            decision_id: The ID of the decision to provide feedback on.
            correct: Whether the routing decision was correct.
            actual_destination: If incorrect, the correct destination.
            notes: Additional notes about the feedback.
        """
        pass

    @abstractmethod
    async def get_confidence_threshold(self) -> float:
        """
        Get the minimum confidence threshold for automatic routing.

        Decisions below this threshold should be escalated to humans.

        Returns:
            Confidence threshold (0.0 to 1.0).
        """
        pass

    @abstractmethod
    async def explain_decision(
        self,
        decision: RoutingDecision,
    ) -> str:
        """
        Generate a human-readable explanation of why a routing decision was made.

        Args:
            decision: The routing decision to explain.

        Returns:
            Human-readable explanation of the decision reasoning.
        """
        pass


class RoutingError(Exception):
    """Raised when routing fails or no suitable destination is found."""

    def __init__(
        self,
        message: str,
        context: RoutingContext | None = None,
        partial_decision: RoutingDecision | None = None,
    ):
        super().__init__(message)
        self.context = context
        self.partial_decision = partial_decision
