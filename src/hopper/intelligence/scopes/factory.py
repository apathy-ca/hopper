"""
Factory for creating scope behaviors.

Provides functions to get the appropriate behavior for a scope or instance.
"""

from sqlalchemy.orm import Session

from hopper.models import HopperInstance, HopperScope

from .base import BaseScopeBehavior
from .global_scope import GlobalScopeBehavior
from .orchestration_scope import OrchestrationScopeBehavior
from .project_scope import ProjectScopeBehavior


class PersonalScopeBehavior(ProjectScopeBehavior):
    """
    Behavior for PERSONAL scope instances.

    Personal instances behave similarly to projects but for individual users.
    They typically handle tasks directly without delegation.
    """

    @property
    def scope_name(self) -> str:
        return "PERSONAL"

    async def should_delegate(
        self,
        task,
        instance,
    ) -> bool:
        """Personal instances typically don't delegate."""
        return False


class FamilyScopeBehavior(ProjectScopeBehavior):
    """
    Behavior for FAMILY scope instances.

    Family instances handle household/family tasks.
    """

    @property
    def scope_name(self) -> str:
        return "FAMILY"


class EventScopeBehavior(ProjectScopeBehavior):
    """
    Behavior for EVENT scope instances.

    Event instances handle event-specific tasks.
    """

    @property
    def scope_name(self) -> str:
        return "EVENT"


class FederatedScopeBehavior(GlobalScopeBehavior):
    """
    Behavior for FEDERATED scope instances.

    Federated instances route tasks across Hopper federations.
    """

    @property
    def scope_name(self) -> str:
        return "FEDERATED"


# Scope to behavior class mapping
_SCOPE_BEHAVIORS: dict[HopperScope, type[BaseScopeBehavior]] = {
    HopperScope.GLOBAL: GlobalScopeBehavior,
    HopperScope.PROJECT: ProjectScopeBehavior,
    HopperScope.ORCHESTRATION: OrchestrationScopeBehavior,
    HopperScope.PERSONAL: PersonalScopeBehavior,
    HopperScope.FAMILY: FamilyScopeBehavior,
    HopperScope.EVENT: EventScopeBehavior,
    HopperScope.FEDERATED: FederatedScopeBehavior,
}


def get_behavior_for_scope(
    scope: HopperScope,
    session: Session,
) -> BaseScopeBehavior:
    """
    Get the behavior implementation for a scope.

    Args:
        scope: The scope to get behavior for
        session: Database session

    Returns:
        Behavior instance for the scope
    """
    behavior_class = _SCOPE_BEHAVIORS.get(scope, ProjectScopeBehavior)
    return behavior_class(session)


def get_behavior_for_instance(
    instance: HopperInstance,
    session: Session,
) -> BaseScopeBehavior:
    """
    Get the behavior implementation for an instance.

    Args:
        instance: The instance to get behavior for
        session: Database session

    Returns:
        Behavior instance
    """
    return get_behavior_for_scope(instance.scope, session)


def get_available_scopes() -> list[HopperScope]:
    """
    Get list of scopes that have behavior implementations.

    Returns:
        List of supported scopes
    """
    return list(_SCOPE_BEHAVIORS.keys())


def register_behavior(
    scope: HopperScope,
    behavior_class: type[BaseScopeBehavior],
) -> None:
    """
    Register a custom behavior for a scope.

    Allows extending the system with custom scope behaviors.

    Args:
        scope: Scope to register behavior for
        behavior_class: Behavior class to use
    """
    _SCOPE_BEHAVIORS[scope] = behavior_class
