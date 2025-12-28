"""
Hopper data models.

This package contains all SQLAlchemy models for the Hopper system.
"""

from .base import Base, SoftDeleteMixin, TimestampMixin
from .enums import (
    DecisionStrategy,
    ExecutorType,
    ExternalPlatform,
    HopperScope,
    TaskPriority,
    TaskSource,
    TaskStatus,
    VelocityRequirement,
)
from .hopper_instance import HopperInstance, TaskDelegation
from .project import Project
from .routing_decision import RoutingDecision
from .task import Task, TaskFeedback

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    "SoftDeleteMixin",
    # Enums
    "TaskStatus",
    "TaskPriority",
    "HopperScope",
    "DecisionStrategy",
    "ExecutorType",
    "VelocityRequirement",
    "ExternalPlatform",
    "TaskSource",
    # Models
    "Task",
    "TaskFeedback",
    "Project",
    "HopperInstance",
    "TaskDelegation",
    "RoutingDecision",
]
