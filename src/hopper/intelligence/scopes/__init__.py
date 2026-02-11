"""
Scope behaviors package.

Implements scope-specific routing and behavior logic for each instance type.
"""

from .base import BaseScopeBehavior, TaskAction, TaskActionType
from .factory import get_behavior_for_instance, get_behavior_for_scope
from .global_scope import GlobalScopeBehavior
from .orchestration_scope import OrchestrationScopeBehavior
from .project_scope import ProjectScopeBehavior

__all__ = [
    "BaseScopeBehavior",
    "TaskAction",
    "TaskActionType",
    "GlobalScopeBehavior",
    "ProjectScopeBehavior",
    "OrchestrationScopeBehavior",
    "get_behavior_for_scope",
    "get_behavior_for_instance",
]
