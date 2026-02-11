"""
Delegation policies for different instance scopes.

Defines how each scope level handles delegation decisions.
"""

from abc import ABC, abstractmethod
from typing import Any

from hopper.models import HopperInstance, HopperScope, Task


class DelegationPolicy(ABC):
    """
    Abstract base class for delegation policies.

    Each scope has a policy that determines delegation behavior.
    """

    @abstractmethod
    def should_delegate(self, task: Task, instance: HopperInstance) -> bool:
        """
        Determine if a task should be delegated.

        Args:
            task: Task to evaluate
            instance: Current instance

        Returns:
            True if task should be delegated
        """
        pass

    @abstractmethod
    def get_delegation_criteria(self, instance: HopperInstance) -> dict[str, Any]:
        """
        Get the criteria used for delegation decisions.

        Args:
            instance: Instance to get criteria for

        Returns:
            Dict of criteria and their values
        """
        pass

    @abstractmethod
    def can_handle_directly(self, task: Task, instance: HopperInstance) -> bool:
        """
        Determine if the instance can handle the task directly.

        Args:
            task: Task to evaluate
            instance: Instance to check

        Returns:
            True if instance can handle the task
        """
        pass


class GlobalScopePolicy(DelegationPolicy):
    """
    Delegation policy for GLOBAL scope instances.

    Global instances route tasks to projects but never handle directly.
    """

    def should_delegate(self, task: Task, instance: HopperInstance) -> bool:
        """Global always delegates - it routes, doesn't execute."""
        return True

    def get_delegation_criteria(self, instance: HopperInstance) -> dict[str, Any]:
        """Get criteria for global routing."""
        config = instance.config or {}
        return {
            "routing_strategy": config.get("routing_strategy", "tag_first"),
            "fallback_strategy": config.get("fallback_strategy", "round_robin"),
            "auto_create_projects": config.get("auto_create_projects", False),
        }

    def can_handle_directly(self, task: Task, instance: HopperInstance) -> bool:
        """Global never handles directly."""
        return False


class ProjectScopePolicy(DelegationPolicy):
    """
    Delegation policy for PROJECT scope instances.

    Projects decide between handling simple tasks directly
    or delegating complex tasks to orchestration.
    """

    def should_delegate(self, task: Task, instance: HopperInstance) -> bool:
        """
        Projects delegate based on task complexity and configuration.
        """
        config = instance.config or {}

        # Check if auto-delegation is enabled
        if not config.get("auto_delegate", True):
            return False

        # Check complexity threshold
        threshold = config.get("orchestration_threshold", 3)
        complexity = self._estimate_complexity(task)

        return complexity >= threshold

    def get_delegation_criteria(self, instance: HopperInstance) -> dict[str, Any]:
        """Get criteria for project delegation."""
        config = instance.config or {}
        return {
            "auto_delegate": config.get("auto_delegate", True),
            "orchestration_threshold": config.get("orchestration_threshold", 3),
            "max_orchestrations": config.get("max_orchestrations_per_project", 5),
            "auto_create_orchestrations": config.get("auto_create_orchestrations", True),
        }

    def can_handle_directly(self, task: Task, instance: HopperInstance) -> bool:
        """Projects can handle simple tasks directly."""
        return not self.should_delegate(task, instance)

    def _estimate_complexity(self, task: Task) -> int:
        """Estimate task complexity."""
        complexity = 1

        if task.description and len(task.description) > 500:
            complexity += 1
        if task.tags and len(task.tags) > 3:
            complexity += 1
        if task.depends_on:
            complexity += 1
        if task.priority in ("high", "urgent"):
            complexity += 1

        return min(complexity, 5)


class OrchestrationScopePolicy(DelegationPolicy):
    """
    Delegation policy for ORCHESTRATION scope instances.

    Orchestration instances execute tasks and don't delegate further.
    """

    def should_delegate(self, task: Task, instance: HopperInstance) -> bool:
        """Orchestration instances execute, don't delegate."""
        return False

    def get_delegation_criteria(self, instance: HopperInstance) -> dict[str, Any]:
        """Get criteria for orchestration (execution-focused)."""
        config = instance.config or {}
        return {
            "max_concurrent_tasks": config.get("max_concurrent_tasks", 10),
            "retry_on_failure": config.get("retry_on_failure", True),
            "max_retries": config.get("max_retries", 3),
        }

    def can_handle_directly(self, task: Task, instance: HopperInstance) -> bool:
        """Orchestration always handles directly."""
        return True


class PersonalScopePolicy(DelegationPolicy):
    """
    Delegation policy for PERSONAL scope instances.

    Personal instances handle individual user tasks.
    """

    def should_delegate(self, task: Task, instance: HopperInstance) -> bool:
        """Personal instances typically don't delegate."""
        return False

    def get_delegation_criteria(self, instance: HopperInstance) -> dict[str, Any]:
        """Get criteria for personal instances."""
        config = instance.config or {}
        return {
            "auto_archive": config.get("auto_archive", True),
            "notification_preferences": config.get("notifications", {}),
        }

    def can_handle_directly(self, task: Task, instance: HopperInstance) -> bool:
        """Personal instances handle all tasks."""
        return True


# Policy registry
_POLICIES: dict[HopperScope, type[DelegationPolicy]] = {
    HopperScope.GLOBAL: GlobalScopePolicy,
    HopperScope.PROJECT: ProjectScopePolicy,
    HopperScope.ORCHESTRATION: OrchestrationScopePolicy,
    HopperScope.PERSONAL: PersonalScopePolicy,
}


def get_policy_for_scope(scope: HopperScope) -> DelegationPolicy:
    """
    Get the delegation policy for a scope.

    Args:
        scope: Instance scope

    Returns:
        Policy instance for the scope
    """
    policy_class = _POLICIES.get(scope, PersonalScopePolicy)
    return policy_class()


def get_policy_for_instance(instance: HopperInstance) -> DelegationPolicy:
    """
    Get the delegation policy for an instance.

    Args:
        instance: HopperInstance

    Returns:
        Policy instance
    """
    return get_policy_for_scope(instance.scope)
