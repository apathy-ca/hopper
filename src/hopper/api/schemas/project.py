"""
Pydantic schemas for Project entities.

Request and response models for project-related API endpoints.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExecutorType(str):
    """Executor type constants."""

    CZARINA = "czarina"
    SARK = "sark"
    HUMAN = "human"
    CUSTOM = "custom"
    SAGE = "sage"


class SyncMode(str):
    """Sync mode for external platforms."""

    IMPORT = "import"
    EXPORT = "export"
    BIDIRECTIONAL = "bidirectional"


class SyncConfigCreate(BaseModel):
    """Schema for creating sync configuration."""

    platform: str = Field(..., description="Platform name (github, gitlab)")
    owner: str = Field(..., description="GitHub user or GitLab group")
    repo: str = Field(..., description="Repository name")

    sync_mode: str = Field(default=SyncMode.BIDIRECTIONAL, description="Sync mode")
    auto_sync: bool = Field(default=True, description="Enable automatic sync")
    sync_interval: int = Field(default=15, ge=1, description="Sync interval in minutes")

    # Field mapping
    label_to_tag: dict[str, str] = Field(default_factory=dict, description="Label to tag mapping")
    milestone_to_priority: dict[str, str] = Field(
        default_factory=dict, description="Milestone to priority mapping"
    )
    assignee_to_executor: dict[str, str] = Field(
        default_factory=dict, description="Assignee to executor mapping"
    )

    # Filtering
    import_labels: list[str] = Field(
        default_factory=list, description="Only import issues with these labels"
    )
    export_filter: str | None = Field(None, description="Python expression for export filter")

    # Webhook
    webhook_secret: str | None = Field(None, description="Webhook secret for verification")


class SyncConfigResponse(SyncConfigCreate):
    """Schema for sync configuration response."""

    id: str
    project_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProjectCreate(BaseModel):
    """Schema for creating a new project."""

    # Identity
    name: str = Field(..., min_length=1, max_length=100, description="Project name")
    slug: str = Field(
        ..., min_length=1, max_length=50, pattern="^[a-z0-9-]+$", description="URL-friendly slug"
    )
    repository: str = Field(..., description="Git URL or local path")
    description: str | None = Field(None, description="Project description")

    # Capabilities
    capabilities: list[str] = Field(default_factory=list, description="Project capabilities")
    tags: list[str] = Field(default_factory=list, description="Project tags")

    # Executor configuration
    executor_type: str = Field(default=ExecutorType.CUSTOM, description="Executor type")
    executor_config: dict[str, Any] = Field(
        default_factory=dict, description="Type-specific configuration"
    )

    # Routing preferences
    auto_claim: bool = Field(default=False, description="Auto-assign matching tasks")
    priority_boost: dict[str, float] = Field(
        default_factory=dict, description="Priority boost factors"
    )
    velocity: str = Field(default="medium", description="Project velocity")

    # SLA expectations
    sla: dict[str, str] = Field(default_factory=dict, description="SLA configuration")

    # Integration
    webhook_url: str | None = Field(None, description="Webhook URL for task notifications")
    api_endpoint: str | None = Field(None, description="REST API endpoint")

    # External sync
    sync_config: SyncConfigCreate | None = Field(None, description="Sync configuration")


class ProjectUpdate(BaseModel):
    """Schema for updating an existing project."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    repository: str | None = None

    capabilities: list[str] | None = None
    tags: list[str] | None = None

    executor_type: str | None = None
    executor_config: dict[str, Any] | None = None

    auto_claim: bool | None = None
    priority_boost: dict[str, float] | None = None
    velocity: str | None = None

    sla: dict[str, str] | None = None

    webhook_url: str | None = None
    api_endpoint: str | None = None


class ProjectResponse(BaseModel):
    """Schema for project response."""

    # Identity
    id: str
    name: str
    slug: str
    repository: str
    description: str | None = None

    # Capabilities
    capabilities: list[str] = []
    tags: list[str] = []

    # Executor configuration
    executor_type: str
    executor_config: dict[str, Any] = {}

    # Routing preferences
    auto_claim: bool
    priority_boost: dict[str, float] = {}
    velocity: str

    # SLA expectations
    sla: dict[str, str] = {}

    # Integration
    webhook_url: str | None = None
    api_endpoint: str | None = None

    # Metadata
    created_at: datetime
    created_by: str
    updated_at: datetime
    last_sync: datetime | None = None

    # Stats
    task_count: int = Field(default=0, description="Number of tasks in project")
    active_task_count: int = Field(default=0, description="Number of active tasks")

    model_config = ConfigDict(from_attributes=True)


class ProjectList(BaseModel):
    """Schema for paginated project list response."""

    items: list[ProjectResponse]
    total: int = Field(..., description="Total number of projects")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class ProjectTasksResponse(BaseModel):
    """Schema for project tasks response."""

    project_id: str
    project_name: str
    tasks: list[Any] = []  # Will be TaskResponse when imported
    total: int

    model_config = ConfigDict(from_attributes=True)
