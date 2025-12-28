"""
Pydantic schemas for HopperInstance entities.

Request and response models for Hopper instance-related API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class HopperScope(str, Enum):
    """Hopper instance scope levels."""
    GLOBAL = "global"          # Strategic routing across all projects
    PROJECT = "project"        # Project-level task management
    ORCHESTRATION = "orchestration"  # Execution-level queue management


class InstanceStatus(str, Enum):
    """Hopper instance status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"


class InstanceCreate(BaseModel):
    """Schema for creating a new Hopper instance."""

    name: str = Field(..., min_length=1, max_length=100, description="Instance name")
    scope: HopperScope = Field(..., description="Instance scope level")

    parent_id: Optional[str] = Field(None, description="Parent instance ID")
    project_id: Optional[str] = Field(None, description="Associated project ID")

    # Configuration
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Instance-specific configuration"
    )

    # Routing configuration
    routing_strategy: str = Field(
        default="rules",
        description="Routing strategy (rules, llm, sage)"
    )
    auto_delegate: bool = Field(
        default=True,
        description="Automatically delegate tasks to child instances"
    )

    # Metadata
    description: Optional[str] = Field(None, description="Instance description")
    tags: List[str] = Field(default_factory=list, description="Instance tags")

    model_config = ConfigDict(use_enum_values=True)


class InstanceUpdate(BaseModel):
    """Schema for updating an existing instance."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    status: Optional[InstanceStatus] = None

    config: Optional[Dict[str, Any]] = None
    routing_strategy: Optional[str] = None
    auto_delegate: Optional[bool] = None

    description: Optional[str] = None
    tags: Optional[List[str]] = None

    model_config = ConfigDict(use_enum_values=True)


class InstanceResponse(BaseModel):
    """Schema for instance response."""

    # Identity
    id: str
    name: str
    scope: HopperScope
    status: InstanceStatus

    # Hierarchy
    parent_id: Optional[str] = None
    project_id: Optional[str] = None

    # Configuration
    config: Dict[str, Any] = {}
    routing_strategy: str
    auto_delegate: bool

    # Metadata
    description: Optional[str] = None
    tags: List[str] = []
    created_at: datetime
    updated_at: datetime
    created_by: str

    # Stats
    task_count: int = Field(default=0, description="Number of tasks")
    active_task_count: int = Field(default=0, description="Number of active tasks")
    child_instance_count: int = Field(default=0, description="Number of child instances")

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True
    )


class InstanceList(BaseModel):
    """Schema for paginated instance list response."""

    items: List[InstanceResponse]
    total: int = Field(..., description="Total number of instances")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class InstanceHierarchyNode(BaseModel):
    """Schema for a node in the instance hierarchy tree."""

    instance: InstanceResponse
    children: List["InstanceHierarchyNode"] = []
    depth: int = Field(..., description="Depth in hierarchy (0 = root)")

    model_config = ConfigDict(from_attributes=True)


class InstanceHierarchy(BaseModel):
    """Schema for instance hierarchy tree response."""

    root: InstanceHierarchyNode
    total_instances: int = Field(..., description="Total instances in hierarchy")

    model_config = ConfigDict(from_attributes=True)


class InstanceTasksResponse(BaseModel):
    """Schema for instance tasks response."""

    instance_id: str
    instance_name: str
    tasks: List[Any] = []  # Will be TaskResponse when imported
    total: int

    model_config = ConfigDict(from_attributes=True)


class InstanceLifecycleRequest(BaseModel):
    """Schema for instance lifecycle operations (start/stop)."""

    action: str = Field(..., description="Lifecycle action (start, stop, restart)")
    force: bool = Field(default=False, description="Force the action")
    wait: bool = Field(default=True, description="Wait for completion")

    model_config = ConfigDict(from_attributes=True)


class InstanceLifecycleResponse(BaseModel):
    """Schema for instance lifecycle operation response."""

    instance_id: str
    action: str
    previous_status: InstanceStatus
    current_status: InstanceStatus
    success: bool
    message: str
    timestamp: datetime

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=True
    )
