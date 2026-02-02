"""Tests for output formatting utilities."""

from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

from hopper.cli.output import (
    format_datetime,
    get_priority_style,
    get_status_style,
    print_instance_tree,
)


def test_format_datetime_with_datetime() -> None:
    """Test formatting datetime objects."""
    now = datetime.now()
    recent = now - timedelta(hours=2)

    result = format_datetime(recent)
    assert "ago" in result


def test_format_datetime_with_iso_string() -> None:
    """Test formatting ISO datetime strings."""
    iso_string = "2025-12-28T00:00:00Z"
    result = format_datetime(iso_string)
    assert result  # Just check it doesn't crash


def test_format_datetime_none() -> None:
    """Test formatting None datetime."""
    result = format_datetime(None)
    assert result == "—"


def test_get_status_style() -> None:
    """Test status style mapping."""
    assert "green" in get_status_style("completed")
    assert "blue" in get_status_style("open")
    assert "yellow" in get_status_style("in_progress")
    assert "red" in get_status_style("blocked")


def test_get_priority_style() -> None:
    """Test priority style mapping."""
    assert "red" in get_priority_style("urgent")
    assert "yellow" in get_priority_style("high")
    assert "blue" in get_priority_style("medium")
    assert "dim" in get_priority_style("low")


def test_status_style_unknown() -> None:
    """Test unknown status defaults to white."""
    result = get_status_style("unknown_status")
    assert "white" in result


def test_priority_style_unknown() -> None:
    """Test unknown priority defaults to white."""
    result = get_priority_style("unknown_priority")
    assert "white" in result


def test_print_instance_tree_empty() -> None:
    """Test printing empty instance tree."""
    with patch("hopper.cli.output.console") as mock_console:
        print_instance_tree([])
        mock_console.print.assert_called_once()


def test_print_instance_tree_with_hierarchy() -> None:
    """Test printing instance tree with hierarchy."""
    instances = [
        {
            "id": "global-1",
            "name": "Global Hopper",
            "scope": "global",
            "status": "active",
            "parent_id": None,
            "task_count": 5,
            "active_task_count": 2,
            "child_instance_count": 2,
        },
        {
            "id": "project-1",
            "name": "Project A",
            "scope": "project",
            "status": "active",
            "parent_id": "global-1",
            "task_count": 3,
            "active_task_count": 1,
            "child_instance_count": 1,
        },
        {
            "id": "orch-1",
            "name": "Orchestration Run 1",
            "scope": "orchestration",
            "status": "active",
            "parent_id": "project-1",
            "task_count": 8,
            "active_task_count": 4,
            "child_instance_count": 0,
        },
    ]

    with patch("hopper.cli.output.console") as mock_console:
        print_instance_tree(instances)
        mock_console.print.assert_called_once()


def test_print_instance_tree_no_tasks() -> None:
    """Test printing instance tree without task counts."""
    instances = [
        {
            "id": "global-1",
            "name": "Global Hopper",
            "scope": "global",
            "status": "active",
            "parent_id": None,
        },
    ]

    with patch("hopper.cli.output.console") as mock_console:
        print_instance_tree(instances, show_tasks=False)
        mock_console.print.assert_called_once()
