"""
Pydantic schemas for RoutingDecision entities.

Request and response models for routing decision-related API endpoints.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ProjectMatch(BaseModel):
    """Schema for a potential project match."""

    project: str = Field(..., description="Project identifier")
    score: float = Field(..., ge=0.0, le=1.0, description="Match score")
    reasoning: str = Field(..., description="Explanation of the match")
    factor_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="Individual factor scores"
    )
    adjusted_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Score after attention shaping"
    )

    model_config = ConfigDict(from_attributes=True)


class DecisionCreate(BaseModel):
    """Schema for creating a routing decision."""

    task_id: str = Field(..., description="Task ID being routed")
    project: str = Field(..., description="Selected project")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    reasoning: str = Field(..., description="Explanation of the decision")

    # Alternatives considered
    alternatives: List[ProjectMatch] = Field(
        default_factory=list,
        description="Alternative project matches"
    )

    # Context at decision time
    workload_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="Project workloads when decided"
    )
    sprint_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Active sprints/milestones"
    )
    recent_history: List[str] = Field(
        default_factory=list,
        description="Recent similar task IDs"
    )

    # Decision metadata
    decided_by: str = Field(..., description="Who/what made the decision (rules, llm, sage-name)")
    decision_time_ms: float = Field(..., ge=0.0, description="Time taken to decide in ms")


class DecisionResponse(DecisionCreate):
    """Schema for routing decision response."""

    id: str
    decided_at: datetime

    # Task information (denormalized for convenience)
    task_title: Optional[str] = None
    task_tags: List[str] = []

    # Project information
    project_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DecisionList(BaseModel):
    """Schema for paginated decision list response."""

    items: List[DecisionResponse]
    total: int = Field(..., description="Total number of decisions")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items")

    model_config = ConfigDict(from_attributes=True)


class DecisionStats(BaseModel):
    """Schema for routing decision statistics."""

    total_decisions: int
    by_decider: Dict[str, int] = Field(
        default_factory=dict,
        description="Count by decision maker"
    )
    avg_confidence: float
    avg_decision_time_ms: float

    # Top projects
    top_projects: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Most routed-to projects"
    )

    # Accuracy metrics (if feedback available)
    accuracy_rate: Optional[float] = None
    reroute_rate: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)
