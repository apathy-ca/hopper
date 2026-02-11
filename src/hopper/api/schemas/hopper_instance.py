"""
Pydantic schemas for HopperInstance entities.

Request and response models for Hopper instance-related API endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HopperScope(str, Enum):
    """Hopper instance scope levels."""

    GLOBAL = "GLOBAL"
    PROJECT = "PROJECT"
    ORCHESTRATION = "ORCHESTRATION"
    PERSONAL = "PERSONAL"
    FAMILY = "FAMILY"
    EVENT = "EVENT"
    FEDERATED = "FEDERATED"


class InstanceStatus(str, Enum):
    """Hopper instance status."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


class InstanceType(str, Enum):
    """Hopper instance types."""

    PERSISTENT = "persistent"
    EPHEMERAL = "ephemeral"
    TEMPORARY = "temporary"


class InstanceCreate(BaseModel):
    """Schema for creating a new Hopper instance."""

    id: str | None = Field(None, min_length=1, max_length=100, description="Instance ID (auto-generated if not provided)")
    name: str = Field(..., min_length=1, max_length=100, description="Instance name")
    scope: HopperScope = Field(..., description="Instance scope level")
    instance_type: InstanceType = Field(default=InstanceType.PERSISTENT, description="Instance type")

    parent_id: str | None = Field(None, description="Parent instance ID")

    # Configuration
    config: dict[str, Any] = Field(
        default_factory=dict, description="Instance-specific configuration"
    )
    runtime_metadata: dict[str, Any] = Field(
        default_factory=dict, description="Runtime metadata"
    )

    # Metadata
    description: str | None = Field(None, description="Instance description")
    created_by: str | None = Field(None, description="Creator identifier")

    model_config = ConfigDict(use_enum_values=True)


class InstanceUpdate(BaseModel):
    """Schema for updating an existing instance."""

    name: str | None = Field(None, min_length=1, max_length=100)
    status: InstanceStatus | None = None
    instance_type: InstanceType | None = None

    config: dict[str, Any] | None = None
    runtime_metadata: dict[str, Any] | None = None

    description: str | None = None

    model_config = ConfigDict(use_enum_values=True)


class InstanceResponse(BaseModel):
    """Schema for instance response."""

    # Identity
    id: str
    name: str
    scope: HopperScope
    status: InstanceStatus
    instance_type: InstanceType

    # Hierarchy
    parent_id: str | None = None

    # Configuration
    config: dict[str, Any] | None = None
    runtime_metadata: dict[str, Any] | None = None

    # Metadata
    description: str | None = None
    created_at: datetime
    updated_at: datetime
    created_by: str | None = None

    # Lifecycle
    started_at: datetime | None = None
    stopped_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class InstanceList(BaseModel):
    """Schema for paginated instance list response."""

    items: list[InstanceResponse]
    total: int = Field(..., description="Total number of instances")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class InstanceHierarchyNode(BaseModel):
    """Schema for a node in the instance hierarchy tree."""

    instance: InstanceResponse
    children: list["InstanceHierarchyNode"] = []
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
    tasks: list[Any] = []  # Will be TaskResponse when imported
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

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)
