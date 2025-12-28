"""
Common Pydantic schemas shared across the API.

Includes pagination, filtering, and response wrappers.
"""

from typing import Optional, Generic, TypeVar, List, Any
from pydantic import BaseModel, Field, ConfigDict


T = TypeVar("T")


class PaginationParams(BaseModel):
    """Common pagination parameters."""

    skip: int = Field(default=0, ge=0, description="Number of items to skip")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum items to return")

    model_config = ConfigDict(from_attributes=True)


class SortParams(BaseModel):
    """Common sorting parameters."""

    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")

    model_config = ConfigDict(from_attributes=True)


class FilterParams(BaseModel):
    """Common filtering parameters."""

    search: Optional[str] = Field(None, description="Search query")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    created_after: Optional[str] = Field(None, description="Filter by creation date (ISO 8601)")
    created_before: Optional[str] = Field(None, description="Filter by creation date (ISO 8601)")

    model_config = ConfigDict(from_attributes=True)


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: List[T]
    total: int = Field(..., description="Total number of items")
    skip: int = Field(..., description="Number of items skipped")
    limit: int = Field(..., description="Maximum number of items returned")
    has_more: bool = Field(..., description="Whether there are more items available")

    model_config = ConfigDict(from_attributes=True)


class SuccessResponse(BaseModel):
    """Standard success response."""

    success: bool = True
    message: str
    data: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: dict = Field(..., description="Error details")

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    service: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    timestamp: Optional[str] = None
    checks: Optional[dict] = Field(None, description="Individual health checks")

    model_config = ConfigDict(from_attributes=True)


class BulkOperationRequest(BaseModel):
    """Request for bulk operations."""

    ids: List[str] = Field(..., min_length=1, description="List of IDs to operate on")
    operation: str = Field(..., description="Operation to perform")
    params: Optional[dict] = Field(None, description="Operation parameters")

    model_config = ConfigDict(from_attributes=True)


class BulkOperationResponse(BaseModel):
    """Response for bulk operations."""

    total: int = Field(..., description="Total items processed")
    successful: int = Field(..., description="Successfully processed items")
    failed: int = Field(..., description="Failed items")
    errors: List[dict] = Field(default_factory=list, description="Error details")

    model_config = ConfigDict(from_attributes=True)


class SearchRequest(BaseModel):
    """Request for search operations."""

    query: str = Field(..., min_length=1, description="Search query")
    filters: Optional[dict] = Field(None, description="Additional filters")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum results")

    model_config = ConfigDict(from_attributes=True)


class SearchResponse(BaseModel, Generic[T]):
    """Response for search operations."""

    query: str
    results: List[T]
    total: int = Field(..., description="Total matching results")
    took_ms: float = Field(..., description="Search duration in milliseconds")

    model_config = ConfigDict(from_attributes=True)
