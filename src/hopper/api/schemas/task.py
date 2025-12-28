"""
Pydantic schemas for Task entities.

Request and response models for task-related API endpoints.
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Priority(str, Enum):
    """Task priority levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Status(str, Enum):
    """Task status values."""

    PENDING = "pending"
    CLAIMED = "claimed"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    CANCELLED = "cancelled"


class VelocityRequirement(str, Enum):
    """Task velocity/speed requirements."""

    FAST = "fast"  # Hours
    MEDIUM = "medium"  # Days
    SLOW = "slow"  # Weeks
    GLACIAL = "glacial"  # Months


class TaskSource(str, Enum):
    """Task source/origin."""

    MCP = "mcp"
    CLI = "cli"
    API = "api"
    WEBHOOK = "webhook"
    EMAIL = "email"
    GITHUB = "github"
    GITLAB = "gitlab"


class TaskCreate(BaseModel):
    """Schema for creating a new task."""

    title: str = Field(..., min_length=1, max_length=200, description="Brief task description")
    description: str = Field(..., min_length=1, description="Detailed task explanation")

    # Categorization
    project: str | None = Field(None, description="Explicit project assignment")
    tags: list[str] = Field(default_factory=list, description="Task tags")
    priority: Priority = Field(default=Priority.MEDIUM, description="Task priority")

    # Routing
    executor_preference: str | None = Field(None, description="Preferred executor type")
    required_capabilities: list[str] = Field(
        default_factory=list, description="Required capabilities"
    )
    estimated_effort: str | None = Field(None, description="Estimated effort (e.g., '2h', '3d')")
    velocity_requirement: VelocityRequirement = Field(
        default=VelocityRequirement.MEDIUM, description="Task velocity requirement"
    )

    # Metadata
    requester: str | None = Field(None, description="Task requester")
    source: TaskSource = Field(default=TaskSource.API, description="Task source")

    # External links
    external_id: str | None = Field(None, description="External platform ID")
    external_url: str | None = Field(None, description="External platform URL")
    external_platform: str | None = Field(None, description="External platform name")

    # Context
    conversation_id: str | None = Field(None, description="Originating conversation ID")
    context: str | None = Field(None, description="Additional routing context")

    # Dependencies
    depends_on: list[str] = Field(default_factory=list, description="Task IDs this depends on")
    blocks: list[str] = Field(default_factory=list, description="Task IDs this blocks")

    model_config = ConfigDict(use_enum_values=True)


class TaskUpdate(BaseModel):
    """Schema for updating an existing task."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, min_length=1)

    # Categorization
    project: str | None = None
    tags: list[str] | None = None
    priority: Priority | None = None

    # Routing
    executor_preference: str | None = None
    required_capabilities: list[str] | None = None
    estimated_effort: str | None = None
    velocity_requirement: VelocityRequirement | None = None

    # Status
    status: Status | None = None
    owner: str | None = None

    # External links
    external_id: str | None = None
    external_url: str | None = None
    external_platform: str | None = None

    # Context
    context: str | None = None

    # Dependencies
    depends_on: list[str] | None = None
    blocks: list[str] | None = None

    model_config = ConfigDict(use_enum_values=True)


class TaskStatusUpdate(BaseModel):
    """Schema for updating task status."""

    status: Status = Field(..., description="New task status")
    owner: str | None = Field(None, description="Task owner/assignee")

    model_config = ConfigDict(use_enum_values=True)


class TaskResponse(BaseModel):
    """Schema for task response."""

    # Identity
    id: str = Field(..., description="Task ID")
    title: str
    description: str

    # Categorization
    project: str | None = None
    tags: list[str] = []
    priority: Priority

    # Routing
    executor_preference: str | None = None
    required_capabilities: list[str] = []
    estimated_effort: str | None = None
    velocity_requirement: VelocityRequirement

    # Metadata
    requester: str | None = None
    created_at: datetime
    updated_at: datetime
    status: Status
    owner: str | None = None

    # External links
    external_id: str | None = None
    external_url: str | None = None
    external_platform: str | None = None

    # Source
    source: TaskSource
    conversation_id: str | None = None
    context: str | None = None

    # Dependencies
    depends_on: list[str] = []
    blocks: list[str] = []

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class TaskList(BaseModel):
    """Schema for paginated task list response."""

    items: list[TaskResponse]
    total: int = Field(..., description="Total number of tasks")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class TaskFeedbackCreate(BaseModel):
    """Schema for creating task feedback."""

    # Effort accuracy
    estimated_duration: str
    actual_duration: str
    complexity_rating: int = Field(..., ge=1, le=5, description="Complexity rating 1-5")

    # Routing accuracy
    was_good_match: bool
    should_have_routed_to: str | None = None
    routing_feedback: str

    # Quality
    quality_score: float = Field(..., ge=0.0, le=5.0, description="Quality score 0.0-5.0")
    required_rework: bool
    rework_reason: str | None = None

    # Learning
    unexpected_blockers: list[str] = Field(default_factory=list)
    required_skills_not_tagged: list[str] = Field(default_factory=list)

    # General
    notes: str


class TaskFeedbackResponse(TaskFeedbackCreate):
    """Schema for task feedback response."""

    id: str
    task_id: str
    timestamp: datetime

    model_config = ConfigDict(from_attributes=True)
