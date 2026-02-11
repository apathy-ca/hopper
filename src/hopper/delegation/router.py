"""
Instance routing for task delegation.

Determines which instance should receive a delegated task.
Integrates with the learning system for improved routing.
"""

import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope, InstanceStatus, Task

logger = logging.getLogger(__name__)


@dataclass
class RoutingResult:
    """Result of a routing decision."""

    target_instance: HopperInstance | None
    confidence: float
    strategy: str
    reasoning: str
    suggestion_source: str | None = None
    pattern_id: str | None = None


class RoutingError(Exception):
    """Raised when routing fails."""

    pass


class InstanceRouter:
    """
    Routes tasks to appropriate instances based on scope and content.

    Handles the logic for finding the best delegation target.
    Integrates with the learning system when available.
    """

    def __init__(self, session: Session, learning_engine: Any | None = None):
        """
        Initialize the router.

        Args:
            session: Database session
            learning_engine: Optional LearningEngine for intelligent routing
        """
        self.session = session
        self.learning_engine = learning_engine

    def find_target_instance(
        self,
        task: Task,
        source_instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Find the best target instance for a task delegation.

        Uses scope-specific logic to determine where to route:
        - GLOBAL -> Routes to appropriate PROJECT
        - PROJECT -> Routes to ORCHESTRATION or handles directly
        - ORCHESTRATION -> Does not delegate further

        Args:
            task: Task to route
            source_instance: Current instance holding the task

        Returns:
            Target instance or None if no suitable target found
        """
        scope = source_instance.scope

        if scope == HopperScope.GLOBAL:
            return self._route_from_global(task, source_instance)
        elif scope == HopperScope.PROJECT:
            return self._route_from_project(task, source_instance)
        elif scope == HopperScope.ORCHESTRATION:
            # Orchestration instances execute, don't delegate
            return None
        else:
            # Other scopes (PERSONAL, FAMILY, etc.) - find child or return None
            return self._route_to_child(task, source_instance)

    def find_target_with_learning(
        self,
        task: Task,
        source_instance: HopperInstance,
    ) -> RoutingResult:
        """
        Find target instance using learning-based routing.

        Combines learned patterns with traditional routing logic.

        Args:
            task: Task to route
            source_instance: Current instance

        Returns:
            RoutingResult with target and metadata
        """
        # Try learning engine first
        if self.learning_engine and source_instance.scope == HopperScope.GLOBAL:
            suggestions = self.learning_engine.get_routing_suggestions(task, limit=3)

            for suggestion in suggestions:
                # Verify the suggested instance exists and is available
                target = self._find_project_instance(suggestion.target_instance)
                if target:
                    return RoutingResult(
                        target_instance=target,
                        confidence=suggestion.confidence,
                        strategy="learning",
                        reasoning=suggestion.reasoning,
                        suggestion_source=suggestion.source.value,
                        pattern_id=suggestion.pattern_id,
                    )

        # Fall back to traditional routing
        target = self.find_target_instance(task, source_instance)

        return RoutingResult(
            target_instance=target,
            confidence=0.5 if target else 0.0,
            strategy="rules",
            reasoning="Matched by rules engine" if target else "No suitable target found",
        )

    def _route_from_global(
        self,
        task: Task,
        source_instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Route from a GLOBAL instance to a PROJECT instance.

        Routing factors:
        1. Learning engine suggestions (if available)
        2. Explicit project assignment in task
        3. Task tags matching project capabilities
        4. Load balancing among available projects

        Args:
            task: Task to route
            source_instance: Global instance

        Returns:
            Target PROJECT instance or None
        """
        # 1. Check explicit project assignment
        if task.project:
            project_instance = self._find_project_instance(task.project)
            if project_instance:
                return project_instance

        # 2. Try learning engine suggestions
        if self.learning_engine:
            suggestions = self.learning_engine.get_routing_suggestions(task, limit=1)
            if suggestions:
                target = self._find_project_instance(suggestions[0].target_instance)
                if target:
                    logger.info(
                        f"Routing task {task.id} to {target.name} via learning "
                        f"(confidence={suggestions[0].confidence:.2f})"
                    )
                    return target

        # 3. Find matching project by tags
        if task.tags:
            matching = self._find_project_by_tags(task.tags, source_instance.id)
            if matching:
                return matching

        # 4. Find any available project child (load balance)
        return self._find_available_child(source_instance, HopperScope.PROJECT)

    def _route_from_project(
        self,
        task: Task,
        source_instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Route from a PROJECT instance to an ORCHESTRATION instance.

        Projects decide whether to handle directly or delegate to orchestration.

        Args:
            task: Task to route
            source_instance: Project instance

        Returns:
            Target ORCHESTRATION instance or None (handle directly)
        """
        # Check if task should be delegated to orchestration
        if not self._should_delegate_to_orchestration(task, source_instance):
            return None

        # Find or create orchestration instance
        return self._find_available_child(source_instance, HopperScope.ORCHESTRATION)

    def _route_to_child(
        self,
        task: Task,
        source_instance: HopperInstance,
    ) -> HopperInstance | None:
        """
        Generic routing to find an appropriate child instance.

        Args:
            task: Task to route
            source_instance: Current instance

        Returns:
            Child instance or None
        """
        # Find any running child instance
        children = source_instance.children
        running_children = [
            c for c in children
            if c.status in (InstanceStatus.RUNNING, InstanceStatus.CREATED)
        ]

        if running_children:
            # Simple load balancing: return first available
            return running_children[0]

        return None

    def _find_project_instance(self, project_name: str) -> HopperInstance | None:
        """Find a PROJECT instance by name."""
        query = (
            select(HopperInstance)
            .where(HopperInstance.scope == HopperScope.PROJECT)
            .where(HopperInstance.name == project_name)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        return result.scalar_one_or_none()

    def _find_project_by_tags(
        self,
        task_tags: list[str],
        parent_id: str,
    ) -> HopperInstance | None:
        """Find a PROJECT instance matching task tags."""
        # Get all project children of the global instance
        query = (
            select(HopperInstance)
            .where(HopperInstance.parent_id == parent_id)
            .where(HopperInstance.scope == HopperScope.PROJECT)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        projects = result.scalars().all()

        # Check each project's config for matching capabilities
        for project in projects:
            config = project.config or {}
            capabilities = config.get("capabilities", [])
            tags = config.get("tags", [])

            # Check for any overlap
            if set(task_tags) & set(capabilities + tags):
                return project

        return None

    def _find_available_child(
        self,
        parent: HopperInstance,
        scope: HopperScope,
    ) -> HopperInstance | None:
        """Find an available child instance of a specific scope."""
        query = (
            select(HopperInstance)
            .where(HopperInstance.parent_id == parent.id)
            .where(HopperInstance.scope == scope)
            .where(
                HopperInstance.status.in_(
                    [InstanceStatus.RUNNING, InstanceStatus.CREATED]
                )
            )
        )
        result = self.session.execute(query)
        children = result.scalars().all()

        if children:
            # Simple selection: first available
            # Could be enhanced with load balancing
            return children[0]

        return None

    def _should_delegate_to_orchestration(
        self,
        task: Task,
        project_instance: HopperInstance,
    ) -> bool:
        """
        Determine if a project should delegate to orchestration.

        Factors:
        - Task complexity
        - Project configuration
        - Available orchestration instances

        Args:
            task: Task to evaluate
            project_instance: Project instance

        Returns:
            True if should delegate, False to handle directly
        """
        config = project_instance.config or {}

        # Check if auto-delegation is enabled
        auto_delegate = config.get("auto_delegate", True)
        if not auto_delegate:
            return False

        # Check complexity threshold
        complexity_threshold = config.get("orchestration_threshold", 3)
        task_complexity = self._estimate_task_complexity(task)

        return task_complexity >= complexity_threshold

    def _estimate_task_complexity(self, task: Task) -> int:
        """
        Estimate task complexity for routing decisions.

        Simple heuristic based on task attributes.

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

    def can_delegate_to(
        self,
        source: HopperInstance,
        target: HopperInstance,
    ) -> bool:
        """
        Check if delegation from source to target is valid.

        Rules:
        - Target must be running or created
        - Target must be a child of source OR at same level
        - Cannot delegate to self

        Args:
            source: Source instance
            target: Target instance

        Returns:
            True if delegation is valid
        """
        # Cannot delegate to self
        if source.id == target.id:
            return False

        # Target must be in valid state
        if target.status not in (InstanceStatus.RUNNING, InstanceStatus.CREATED):
            return False

        # Check hierarchy: target should be child of source or at lower scope
        if target.parent_id == source.id:
            return True

        # Allow delegation to siblings for reassignment
        if source.parent_id == target.parent_id:
            return True

        # Check scope hierarchy
        scope_order = {
            HopperScope.GLOBAL: 0,
            HopperScope.PROJECT: 1,
            HopperScope.ORCHESTRATION: 2,
        }

        source_order = scope_order.get(source.scope, 10)
        target_order = scope_order.get(target.scope, 10)

        # Can delegate to same level or lower
        return target_order >= source_order

    def get_available_instances(
        self,
        scope: HopperScope | None = None,
        parent_id: str | None = None,
    ) -> list[HopperInstance]:
        """
        Get instances available for task delegation.

        Args:
            scope: Filter by scope
            parent_id: Filter by parent

        Returns:
            List of available instances
        """
        query = select(HopperInstance).where(
            HopperInstance.status.in_(
                [InstanceStatus.RUNNING, InstanceStatus.CREATED]
            )
        )

        if scope:
            query = query.where(HopperInstance.scope == scope)

        if parent_id:
            query = query.where(HopperInstance.parent_id == parent_id)

        result = self.session.execute(query)
        return list(result.scalars().all())

    def record_routing_decision(
        self,
        task: Task,
        routing_result: RoutingResult,
    ) -> None:
        """
        Record a routing decision for learning.

        Args:
            task: Task that was routed
            routing_result: Result of the routing decision
        """
        if not self.learning_engine or not routing_result.target_instance:
            return

        # Get suggestion if we used one
        suggestion = None
        if routing_result.strategy == "learning" and routing_result.pattern_id:
            from hopper.memory.learning import RoutingSuggestion, SuggestionSource

            suggestion = RoutingSuggestion(
                target_instance=routing_result.target_instance.id,
                confidence=routing_result.confidence,
                source=SuggestionSource(routing_result.suggestion_source or "pattern"),
                reasoning=routing_result.reasoning,
                pattern_id=routing_result.pattern_id,
            )

        self.learning_engine.record_routing(
            task=task,
            chosen_instance=routing_result.target_instance.id,
            confidence=routing_result.confidence,
            strategy=routing_result.strategy,
            reasoning=routing_result.reasoning,
            suggestion=suggestion,
        )
