"""
Pydantic schemas for TaskDelegation entities.

Request and response models for task delegation API endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DelegationType(str, Enum):
    """Types of task delegation."""

    ROUTE = "route"
    DECOMPOSE = "decompose"
    ESCALATE = "escalate"
    REASSIGN = "reassign"


class DelegationStatus(str, Enum):
    """Status of a delegation."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class DelegationCreate(BaseModel):
    """Schema for creating a new task delegation."""

    task_id: str = Field(..., description="ID of the task to delegate")
    target_instance_id: str = Field(..., description="ID of the target instance")
    delegation_type: DelegationType = Field(
        default=DelegationType.ROUTE, description="Type of delegation"
    )
    notes: str | None = Field(None, description="Optional notes about the delegation")
    delegated_by: str | None = Field(None, description="Who is delegating the task")

    model_config = ConfigDict(use_enum_values=True)


class DelegationAccept(BaseModel):
    """Schema for accepting a delegation."""

    notes: str | None = Field(None, description="Optional acceptance notes")


class DelegationReject(BaseModel):
    """Schema for rejecting a delegation."""

    reason: str = Field(..., description="Reason for rejection")


class DelegationComplete(BaseModel):
    """Schema for completing a delegation."""

    result: dict[str, Any] | None = Field(None, description="Completion result data")
    notes: str | None = Field(None, description="Completion notes")


class DelegationResponse(BaseModel):
    """Schema for delegation response."""

    id: str
    task_id: str
    source_instance_id: str | None = None
    target_instance_id: str | None = None
    delegation_type: DelegationType
    status: DelegationStatus

    delegated_at: datetime
    accepted_at: datetime | None = None
    completed_at: datetime | None = None

    result: dict[str, Any] | None = None
    rejection_reason: str | None = None
    notes: str | None = None
    delegated_by: str | None = None

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class DelegationList(BaseModel):
    """Schema for paginated delegation list response."""

    items: list[DelegationResponse]
    total: int = Field(..., description="Total number of delegations")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class DelegationChainResponse(BaseModel):
    """Schema for delegation chain response."""

    task_id: str
    delegations: list[DelegationResponse]
    current_instance_id: str | None = Field(
        None, description="Current instance where task resides"
    )
    origin_instance_id: str | None = Field(
        None, description="Instance where task originated"
    )
    total_delegations: int

    model_config = ConfigDict(from_attributes=True)
