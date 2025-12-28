"""
Hopper API Pydantic schemas.

Request and response models for all API endpoints.
"""

# Task schemas
# Common schemas
from hopper.api.schemas.common import (
    BulkOperationRequest,
    BulkOperationResponse,
    ErrorResponse,
    FilterParams,
    HealthResponse,
    PaginatedResponse,
    PaginationParams,
    SearchRequest,
    SearchResponse,
    SortParams,
    SuccessResponse,
)

# Instance schemas
from hopper.api.schemas.hopper_instance import (
    HopperScope,
    InstanceCreate,
    InstanceHierarchy,
    InstanceHierarchyNode,
    InstanceLifecycleRequest,
    InstanceLifecycleResponse,
    InstanceList,
    InstanceResponse,
    InstanceStatus,
    InstanceTasksResponse,
    InstanceUpdate,
)

# Project schemas
from hopper.api.schemas.project import (
    ExecutorType,
    ProjectCreate,
    ProjectList,
    ProjectResponse,
    ProjectTasksResponse,
    ProjectUpdate,
    SyncConfigCreate,
    SyncConfigResponse,
    SyncMode,
)

# Routing decision schemas
from hopper.api.schemas.routing_decision import (
    DecisionCreate,
    DecisionList,
    DecisionResponse,
    DecisionStats,
    ProjectMatch,
)
from hopper.api.schemas.task import (
    Priority,
    Status,
    TaskCreate,
    TaskFeedbackCreate,
    TaskFeedbackResponse,
    TaskList,
    TaskResponse,
    TaskSource,
    TaskStatusUpdate,
    TaskUpdate,
    VelocityRequirement,
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
