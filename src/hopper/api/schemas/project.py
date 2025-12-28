"""
Pydantic schemas for Project entities.

Request and response models for project-related API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


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
    label_to_tag: Dict[str, str] = Field(default_factory=dict, description="Label to tag mapping")
    milestone_to_priority: Dict[str, str] = Field(
        default_factory=dict,
        description="Milestone to priority mapping"
    )
    assignee_to_executor: Dict[str, str] = Field(
        default_factory=dict,
        description="Assignee to executor mapping"
    )

    # Filtering
    import_labels: List[str] = Field(
        default_factory=list,
        description="Only import issues with these labels"
    )
    export_filter: Optional[str] = Field(None, description="Python expression for export filter")

    # Webhook
    webhook_secret: Optional[str] = Field(None, description="Webhook secret for verification")


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
        ...,
        min_length=1,
        max_length=50,
        pattern="^[a-z0-9-]+$",
        description="URL-friendly slug"
    )
    repository: str = Field(..., description="Git URL or local path")
    description: Optional[str] = Field(None, description="Project description")

    # Capabilities
    capabilities: List[str] = Field(default_factory=list, description="Project capabilities")
    tags: List[str] = Field(default_factory=list, description="Project tags")

    # Executor configuration
    executor_type: str = Field(default=ExecutorType.CUSTOM, description="Executor type")
    executor_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Type-specific configuration"
    )

    # Routing preferences
    auto_claim: bool = Field(default=False, description="Auto-assign matching tasks")
    priority_boost: Dict[str, float] = Field(
        default_factory=dict,
        description="Priority boost factors"
    )
    velocity: str = Field(default="medium", description="Project velocity")

    # SLA expectations
    sla: Dict[str, str] = Field(
        default_factory=dict,
        description="SLA configuration"
    )

    # Integration
    webhook_url: Optional[str] = Field(None, description="Webhook URL for task notifications")
    api_endpoint: Optional[str] = Field(None, description="REST API endpoint")

    # External sync
    sync_config: Optional[SyncConfigCreate] = Field(None, description="Sync configuration")


class ProjectUpdate(BaseModel):
    """Schema for updating an existing project."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    repository: Optional[str] = None

    capabilities: Optional[List[str]] = None
    tags: Optional[List[str]] = None

    executor_type: Optional[str] = None
    executor_config: Optional[Dict[str, Any]] = None

    auto_claim: Optional[bool] = None
    priority_boost: Optional[Dict[str, float]] = None
    velocity: Optional[str] = None

    sla: Optional[Dict[str, str]] = None

    webhook_url: Optional[str] = None
    api_endpoint: Optional[str] = None


class ProjectResponse(BaseModel):
    """Schema for project response."""

    # Identity
    id: str
    name: str
    slug: str
    repository: str
    description: Optional[str] = None

    # Capabilities
    capabilities: List[str] = []
    tags: List[str] = []

    # Executor configuration
    executor_type: str
    executor_config: Dict[str, Any] = {}

    # Routing preferences
    auto_claim: bool
    priority_boost: Dict[str, float] = {}
    velocity: str

    # SLA expectations
    sla: Dict[str, str] = {}

    # Integration
    webhook_url: Optional[str] = None
    api_endpoint: Optional[str] = None

    # Metadata
    created_at: datetime
    created_by: str
    updated_at: datetime
    last_sync: Optional[datetime] = None

    # Stats
    task_count: int = Field(default=0, description="Number of tasks in project")
    active_task_count: int = Field(default=0, description="Number of active tasks")

    model_config = ConfigDict(from_attributes=True)


class ProjectList(BaseModel):
    """Schema for paginated project list response."""

    items: List[ProjectResponse]
    total: int = Field(..., description="Total number of projects")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class ProjectTasksResponse(BaseModel):
    """Schema for project tasks response."""

    project_id: str
    project_name: str
    tasks: List[Any] = []  # Will be TaskResponse when imported
    total: int

    model_config = ConfigDict(from_attributes=True)
