"""
Pydantic schemas for learning API endpoints.

Covers feedback, patterns, and statistics.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Feedback Schemas
# ============================================================================


class FeedbackCreate(BaseModel):
    """Schema for creating task feedback."""

    was_good_match: bool = Field(..., description="Whether routing was correct")
    routing_feedback: str | None = Field(None, description="Text feedback about routing")
    should_have_routed_to: str | None = Field(
        None, description="Instance that should have received the task"
    )
    estimated_duration: str | None = Field(None, description="Estimated task duration")
    actual_duration: str | None = Field(None, description="Actual task duration")
    complexity_rating: int | None = Field(
        None, ge=1, le=5, description="Complexity rating 1-5"
    )
    quality_score: float | None = Field(
        None, ge=0.0, le=5.0, description="Quality score 0.0-5.0"
    )
    required_rework: bool | None = Field(None, description="Whether rework was needed")
    rework_reason: str | None = Field(None, description="Reason for rework")
    unexpected_blockers: list[str] | None = Field(
        None, description="List of unexpected blockers"
    )
    required_skills_not_tagged: list[str] | None = Field(
        None, description="Skills needed but not tagged"
    )
    notes: str | None = Field(None, description="Additional notes")


class FeedbackResponse(BaseModel):
    """Schema for feedback response."""

    task_id: str
    was_good_match: bool | None
    routing_feedback: str | None
    should_have_routed_to: str | None
    estimated_duration: str | None
    actual_duration: str | None
    complexity_rating: int | None
    quality_score: float | None
    required_rework: bool | None
    rework_reason: str | None
    unexpected_blockers: dict[str, Any] | None
    required_skills_not_tagged: dict[str, Any] | None
    notes: str | None
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class FeedbackList(BaseModel):
    """Schema for paginated feedback list."""

    items: list[FeedbackResponse]
    total: int
    page: int
    page_size: int


# ============================================================================
# Pattern Schemas
# ============================================================================


class PatternType(str, Enum):
    """Pattern type enum."""

    TAG = "tag"
    TEXT = "text"
    COMBINED = "combined"
    PRIORITY = "priority"


class PatternCreate(BaseModel):
    """Schema for creating a routing pattern."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    pattern_type: PatternType = PatternType.TAG
    target_instance: str = Field(..., description="Target instance ID")
    tag_criteria: dict[str, Any] | None = Field(
        None, description="Tag matching criteria (required, optional)"
    )
    text_criteria: dict[str, Any] | None = Field(
        None, description="Text matching criteria (keywords)"
    )
    priority_criteria: str | None = Field(None, description="Priority to match")
    confidence: float = Field(0.5, ge=0.0, le=1.0, description="Initial confidence")


class PatternUpdate(BaseModel):
    """Schema for updating a pattern."""

    name: str | None = None
    description: str | None = None
    tag_criteria: dict[str, Any] | None = None
    text_criteria: dict[str, Any] | None = None
    priority_criteria: str | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    is_active: bool | None = None


class PatternResponse(BaseModel):
    """Schema for pattern response."""

    id: str
    name: str
    description: str | None
    pattern_type: str
    target_instance: str
    tag_criteria: dict[str, Any] | None
    text_criteria: dict[str, Any] | None
    priority_criteria: str | None
    confidence: float
    usage_count: int
    success_count: int
    failure_count: int
    success_rate: float
    is_active: bool
    source_episodes: list[str] | None
    last_used_at: datetime | None
    last_refined_at: datetime | None
    created_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class PatternList(BaseModel):
    """Schema for paginated pattern list."""

    items: list[PatternResponse]
    total: int
    page: int
    page_size: int


class PatternMatch(BaseModel):
    """Schema for a pattern match result."""

    pattern: PatternResponse
    match_score: float


# ============================================================================
# Statistics Schemas
# ============================================================================


class RoutingAccuracyStats(BaseModel):
    """Schema for routing accuracy statistics."""

    total_feedback: int
    good_matches: int
    bad_matches: int
    accuracy_rate: float
    common_misrouting_targets: list[dict[str, Any]]
    by_instance: dict[str, dict[str, Any]]
    period_start: datetime | None
    period_end: datetime | None


class QualityStats(BaseModel):
    """Schema for quality statistics."""

    total_tasks: int
    average_quality_score: float
    average_complexity: float
    rework_rate: float
    tasks_with_blockers: int
    missing_skills_count: int
    by_complexity: dict[int, dict[str, Any]]


class EpisodicStats(BaseModel):
    """Schema for episodic memory statistics."""

    total_episodes: int
    successful: int
    failed: int
    pending: int
    success_rate: float
    average_confidence: float
    since: str | None


class PatternStats(BaseModel):
    """Schema for pattern statistics."""

    total_patterns: int
    active_patterns: int
    inactive_patterns: int
    total_usage: int
    average_confidence: float
    by_type: dict[str, int]
    by_instance: dict[str, int]


class LearningStats(BaseModel):
    """Schema for overall learning statistics."""

    episodic: EpisodicStats
    patterns: PatternStats
    searcher: dict[str, Any]


class ConsolidationResult(BaseModel):
    """Schema for consolidation run result."""

    candidates_found: int
    patterns_created: int
    created_pattern_ids: list[str]
    total_patterns: int
    active_patterns: int
    since: str
    ran_at: str
