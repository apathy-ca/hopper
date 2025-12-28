"""
Common test utilities and helper functions.

Provides utilities for:
- Assertion helpers
- Data validation helpers
- Database cleanup utilities
- Mock response builders
- API testing helpers
- Time manipulation helpers
"""

import json
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import Mock

from sqlalchemy import inspect
from sqlalchemy.orm import Session

# ============================================================================
# Assertion Helpers
# ============================================================================


def assert_task_equal(task1: Any, task2: Any, ignore_fields: list[str] | None = None):
    """
    Assert that two tasks are equal, ignoring specified fields.

    Args:
        task1: First task instance
        task2: Second task instance
        ignore_fields: List of field names to ignore in comparison
    """
    ignore_fields = ignore_fields or ["created_at", "updated_at"]

    for field in ["id", "title", "description", "project", "status", "priority"]:
        if field not in ignore_fields:
            assert getattr(task1, field) == getattr(
                task2, field
            ), f"Field {field} differs: {getattr(task1, field)} != {getattr(task2, field)}"


def assert_dict_contains(expected: dict[str, Any], actual: dict[str, Any]):
    """
    Assert that actual dictionary contains all expected key-value pairs.

    Args:
        expected: Expected dictionary (subset)
        actual: Actual dictionary (superset)
    """
    for key, value in expected.items():
        assert key in actual, f"Key '{key}' not found in actual dictionary"
        assert (
            actual[key] == value
        ), f"Value for key '{key}' differs: expected {value}, got {actual[key]}"


def assert_response_success(response: Any, status_code: int = 200):
    """
    Assert that an API response is successful.

    Args:
        response: HTTP response object
        status_code: Expected status code (default: 200)
    """
    assert (
        response.status_code == status_code
    ), f"Expected status {status_code}, got {response.status_code}. Body: {response.text}"


def assert_response_error(response: Any, status_code: int, error_detail: str | None = None):
    """
    Assert that an API response contains an error.

    Args:
        response: HTTP response object
        status_code: Expected error status code
        error_detail: Expected error detail message (optional)
    """
    assert (
        response.status_code == status_code
    ), f"Expected status {status_code}, got {response.status_code}"

    if error_detail:
        body = response.json()
        assert "detail" in body, "Error response missing 'detail' field"
        assert (
            error_detail in body["detail"]
        ), f"Expected error detail to contain '{error_detail}', got '{body['detail']}'"


def assert_timestamp_recent(timestamp: datetime, seconds: int = 5):
    """
    Assert that a timestamp is recent (within last N seconds).

    Args:
        timestamp: Datetime to check
        seconds: Number of seconds to consider "recent" (default: 5)
    """
    now = datetime.utcnow()
    delta = now - timestamp
    assert (
        delta.total_seconds() <= seconds
    ), f"Timestamp {timestamp} is not recent (more than {seconds} seconds old)"


# ============================================================================
# Data Validation Helpers
# ============================================================================


def validate_task_schema(task_data: dict[str, Any]) -> bool:
    """
    Validate that a dictionary conforms to the task schema.

    Args:
        task_data: Dictionary representing a task

    Returns:
        True if valid, raises AssertionError otherwise
    """
    required_fields = ["id", "title", "status", "priority"]
    for field in required_fields:
        assert field in task_data, f"Missing required field: {field}"

    # Validate field types
    assert isinstance(task_data["id"], str), "id must be a string"
    assert isinstance(task_data["title"], str), "title must be a string"
    assert isinstance(task_data["status"], str), "status must be a string"
    assert isinstance(task_data["priority"], str), "priority must be a string"

    # Validate enum values
    valid_statuses = ["pending", "routed", "in_progress", "completed", "archived"]
    assert task_data["status"] in valid_statuses, f"Invalid status: {task_data['status']}"

    valid_priorities = ["low", "medium", "high", "urgent"]
    assert task_data["priority"] in valid_priorities, f"Invalid priority: {task_data['priority']}"

    return True


def validate_project_schema(project_data: dict[str, Any]) -> bool:
    """
    Validate that a dictionary conforms to the project schema.

    Args:
        project_data: Dictionary representing a project

    Returns:
        True if valid, raises AssertionError otherwise
    """
    required_fields = ["id", "name", "slug"]
    for field in required_fields:
        assert field in project_data, f"Missing required field: {field}"

    assert isinstance(project_data["id"], str), "id must be a string"
    assert isinstance(project_data["name"], str), "name must be a string"
    assert isinstance(project_data["slug"], str), "slug must be a string"

    return True


def validate_routing_decision_schema(decision_data: dict[str, Any]) -> bool:
    """
    Validate that a dictionary conforms to the routing decision schema.

    Args:
        decision_data: Dictionary representing a routing decision

    Returns:
        True if valid, raises AssertionError otherwise
    """
    required_fields = ["id", "task_id", "destination", "strategy", "confidence"]
    for field in required_fields:
        assert field in decision_data, f"Missing required field: {field}"

    assert isinstance(decision_data["confidence"], (int, float)), "confidence must be a number"
    assert 0 <= decision_data["confidence"] <= 1, "confidence must be between 0 and 1"

    valid_strategies = ["rules", "llm", "sage"]
    assert (
        decision_data["strategy"] in valid_strategies
    ), f"Invalid strategy: {decision_data['strategy']}"

    return True


# ============================================================================
# Database Helpers
# ============================================================================


def clear_database(session: Session, *models):
    """
    Clear all data from specified models.

    Args:
        session: SQLAlchemy session
        *models: Model classes to clear
    """
    for model in models:
        session.query(model).delete()
    session.commit()


def count_records(session: Session, model: Any, **filters) -> int:
    """
    Count records in a table with optional filters.

    Args:
        session: SQLAlchemy session
        model: Model class
        **filters: Filter conditions

    Returns:
        Number of matching records
    """
    query = session.query(model)
    for key, value in filters.items():
        query = query.filter(getattr(model, key) == value)
    return query.count()


def get_all_records(session: Session, model: Any, **filters) -> list[Any]:
    """
    Get all records from a table with optional filters.

    Args:
        session: SQLAlchemy session
        model: Model class
        **filters: Filter conditions

    Returns:
        List of model instances
    """
    query = session.query(model)
    for key, value in filters.items():
        query = query.filter(getattr(model, key) == value)
    return query.all()


def refresh_from_db(session: Session, instance: Any) -> Any:
    """
    Refresh an instance from the database.

    Args:
        session: SQLAlchemy session
        instance: Model instance to refresh

    Returns:
        Refreshed instance
    """
    session.refresh(instance)
    return instance


def model_to_dict(instance: Any, exclude: list[str] | None = None) -> dict[str, Any]:
    """
    Convert a SQLAlchemy model instance to a dictionary.

    Args:
        instance: Model instance
        exclude: List of fields to exclude

    Returns:
        Dictionary representation of the model
    """
    exclude = exclude or []
    mapper = inspect(instance.__class__)

    result = {}
    for column in mapper.columns:
        if column.name not in exclude:
            value = getattr(instance, column.name)
            # Convert datetime to ISO string
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value

    return result


# ============================================================================
# Mock Response Builders
# ============================================================================


def build_api_response(
    data: Any, status_code: int = 200, headers: dict[str, str] | None = None
) -> Mock:
    """
    Build a mock API response.

    Args:
        data: Response data
        status_code: HTTP status code
        headers: Response headers

    Returns:
        Mock response object
    """
    response = Mock()
    response.status_code = status_code
    response.json.return_value = data
    response.text = json.dumps(data)
    response.headers = headers or {}
    return response


def build_error_response(
    status_code: int, detail: str, headers: dict[str, str] | None = None
) -> Mock:
    """
    Build a mock error response.

    Args:
        status_code: HTTP error status code
        detail: Error detail message
        headers: Response headers

    Returns:
        Mock response object
    """
    error_data = {"detail": detail}
    return build_api_response(error_data, status_code, headers)


def build_task_response(task_data: dict[str, Any]) -> dict[str, Any]:
    """
    Build a standardized task API response.

    Args:
        task_data: Task data dictionary

    Returns:
        Formatted task response
    """
    return {
        "id": task_data["id"],
        "title": task_data["title"],
        "description": task_data.get("description"),
        "project": task_data.get("project"),
        "status": task_data["status"],
        "priority": task_data["priority"],
        "created_at": task_data.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": task_data.get("updated_at", datetime.utcnow().isoformat()),
    }


def build_paginated_response(
    items: list[Any], page: int = 1, page_size: int = 10, total: int | None = None
) -> dict[str, Any]:
    """
    Build a paginated API response.

    Args:
        items: List of items
        page: Current page number
        page_size: Items per page
        total: Total number of items (defaults to len(items))

    Returns:
        Paginated response dictionary
    """
    total = total or len(items)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


# ============================================================================
# Time Helpers
# ============================================================================


def days_ago(days: int) -> datetime:
    """
    Get a datetime N days in the past.

    Args:
        days: Number of days ago

    Returns:
        Datetime object
    """
    return datetime.utcnow() - timedelta(days=days)


def days_from_now(days: int) -> datetime:
    """
    Get a datetime N days in the future.

    Args:
        days: Number of days from now

    Returns:
        Datetime object
    """
    return datetime.utcnow() + timedelta(days=days)


def hours_ago(hours: int) -> datetime:
    """
    Get a datetime N hours in the past.

    Args:
        hours: Number of hours ago

    Returns:
        Datetime object
    """
    return datetime.utcnow() - timedelta(hours=hours)


# ============================================================================
# API Testing Helpers
# ============================================================================


def extract_id_from_location(location: str) -> str:
    """
    Extract resource ID from Location header.

    Args:
        location: Location header value (e.g., "/api/v1/tasks/task-123")

    Returns:
        Resource ID
    """
    return location.split("/")[-1]


def assert_pagination_valid(response_data: dict[str, Any]):
    """
    Assert that a paginated response has valid pagination metadata.

    Args:
        response_data: API response data
    """
    required_fields = ["items", "page", "page_size", "total", "pages"]
    for field in required_fields:
        assert field in response_data, f"Missing pagination field: {field}"

    assert isinstance(response_data["items"], list), "items must be a list"
    assert isinstance(response_data["page"], int), "page must be an integer"
    assert isinstance(response_data["page_size"], int), "page_size must be an integer"
    assert isinstance(response_data["total"], int), "total must be an integer"
    assert isinstance(response_data["pages"], int), "pages must be an integer"

    assert response_data["page"] >= 1, "page must be >= 1"
    assert response_data["page_size"] >= 1, "page_size must be >= 1"
    assert response_data["total"] >= 0, "total must be >= 0"
    assert response_data["pages"] >= 0, "pages must be >= 0"


# ============================================================================
# CLI Testing Helpers
# ============================================================================


def parse_cli_table_output(output: str) -> list[dict[str, str]]:
    """
    Parse CLI table output into list of dictionaries.

    Args:
        output: CLI table output string

    Returns:
        List of dictionaries representing table rows
    """
    lines = output.strip().split("\n")
    if len(lines) < 2:
        return []

    # First line is headers
    headers = [h.strip() for h in lines[0].split("|") if h.strip()]

    # Parse data rows
    rows = []
    for line in lines[2:]:  # Skip header and separator line
        if line.strip() and not line.strip().startswith("-"):
            values = [v.strip() for v in line.split("|") if v.strip()]
            if len(values) == len(headers):
                rows.append(dict(zip(headers, values)))

    return rows


def assert_cli_success(result: Any, expected_output: str | None = None):
    """
    Assert that a CLI command succeeded.

    Args:
        result: Click CLI result
        expected_output: Expected output string (optional)
    """
    assert (
        result.exit_code == 0
    ), f"CLI command failed with exit code {result.exit_code}. Output: {result.output}"

    if expected_output:
        assert (
            expected_output in result.output
        ), f"Expected output to contain '{expected_output}', got: {result.output}"


def assert_cli_error(result: Any, expected_error: str | None = None):
    """
    Assert that a CLI command failed.

    Args:
        result: Click CLI result
        expected_error: Expected error message (optional)
    """
    assert (
        result.exit_code != 0
    ), f"Expected CLI command to fail, but it succeeded. Output: {result.output}"

    if expected_error:
        assert (
            expected_error in result.output
        ), f"Expected error to contain '{expected_error}', got: {result.output}"


# ============================================================================
# MCP Testing Helpers
# ============================================================================


def build_mcp_tool_call(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Build an MCP tool call request.

    Args:
        tool_name: Name of the MCP tool
        arguments: Tool arguments

    Returns:
        MCP tool call dictionary
    """
    return {
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def build_mcp_tool_response(result: Any, is_error: bool = False) -> dict[str, Any]:
    """
    Build an MCP tool call response.

    Args:
        result: Tool result data
        is_error: Whether this is an error response

    Returns:
        MCP tool response dictionary
    """
    if is_error:
        return {
            "error": {
                "code": -32000,
                "message": str(result),
            }
        }
    else:
        return {"result": result}


def assert_mcp_tool_response_valid(response: dict[str, Any]):
    """
    Assert that an MCP tool response is valid.

    Args:
        response: MCP tool response
    """
    assert (
        "result" in response or "error" in response
    ), "MCP response must contain either 'result' or 'error'"

    if "error" in response:
        assert "code" in response["error"], "MCP error must have 'code'"
        assert "message" in response["error"], "MCP error must have 'message'"
