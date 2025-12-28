"""
Hopper API Pydantic schemas.

Request and response models for all API endpoints.
"""

# Task schemas
from hopper.api.schemas.task import (
    Priority,
    Status,
    VelocityRequirement,
    TaskSource,
    TaskCreate,
    TaskUpdate,
    TaskStatusUpdate,
    TaskResponse,
    TaskList,
    TaskFeedbackCreate,
    TaskFeedbackResponse,
)

# Project schemas
from hopper.api.schemas.project import (
    ExecutorType,
    SyncMode,
    SyncConfigCreate,
    SyncConfigResponse,
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectList,
    ProjectTasksResponse,
)

# Instance schemas
from hopper.api.schemas.hopper_instance import (
    HopperScope,
    InstanceStatus,
    InstanceCreate,
    InstanceUpdate,
    InstanceResponse,
    InstanceList,
    InstanceHierarchyNode,
    InstanceHierarchy,
    InstanceTasksResponse,
    InstanceLifecycleRequest,
    InstanceLifecycleResponse,
)

# Routing decision schemas
from hopper.api.schemas.routing_decision import (
    ProjectMatch,
    DecisionCreate,
    DecisionResponse,
    DecisionList,
    DecisionStats,
)

# Common schemas
from hopper.api.schemas.common import (
    PaginationParams,
    SortParams,
    FilterParams,
    PaginatedResponse,
    SuccessResponse,
    ErrorResponse,
    HealthResponse,
    BulkOperationRequest,
    BulkOperationResponse,
    SearchRequest,
    SearchResponse,
)

__all__ = [
    # Task
    "Priority",
    "Status",
    "VelocityRequirement",
    "TaskSource",
    "TaskCreate",
    "TaskUpdate",
    "TaskStatusUpdate",
    "TaskResponse",
    "TaskList",
    "TaskFeedbackCreate",
    "TaskFeedbackResponse",
    # Project
    "ExecutorType",
    "SyncMode",
    "SyncConfigCreate",
    "SyncConfigResponse",
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "ProjectList",
    "ProjectTasksResponse",
    # Instance
    "HopperScope",
    "InstanceStatus",
    "InstanceCreate",
    "InstanceUpdate",
    "InstanceResponse",
    "InstanceList",
    "InstanceHierarchyNode",
    "InstanceHierarchy",
    "InstanceTasksResponse",
    "InstanceLifecycleRequest",
    "InstanceLifecycleResponse",
    # Routing
    "ProjectMatch",
    "DecisionCreate",
    "DecisionResponse",
    "DecisionList",
    "DecisionStats",
    # Common
    "PaginationParams",
    "SortParams",
    "FilterParams",
    "PaginatedResponse",
    "SuccessResponse",
    "ErrorResponse",
    "HealthResponse",
    "BulkOperationRequest",
    "BulkOperationResponse",
    "SearchRequest",
    "SearchResponse",
]
