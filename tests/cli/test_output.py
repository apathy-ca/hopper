"""Tests for output formatting utilities."""

import pytest
from datetime import datetime, timedelta

from hopper.cli.output import (
    format_datetime,
    get_status_style,
    get_priority_style,
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
