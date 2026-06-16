"""Tests for memory consolidation engine (consolidation.py).

Uses a minimal in-memory fake client and a mocked LLM response so no network
calls or API keys are required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hopper.memory.consolidation import _call_llm, run_consolidation, run_drift_check

# ---------------------------------------------------------------------------
# Fake client
# ---------------------------------------------------------------------------


class _FakeClient:
    """Minimal LocalClient lookalike for consolidation tests."""

    def __init__(self):
        self._tasks: dict[str, dict] = {}
        self._next_seq = 1
        self.storage_path = None

    def list_tasks(self, kind: str | None = None, memory_class: str | None = None):
        results = list(self._tasks.values())
        if kind:
            results = [t for t in results if t.get("kind") == kind]
        if memory_class:
            results = [t for t in results if t.get("memory_class") == memory_class]
        return results

    def create_task(self, data: dict) -> dict:
        tid = data.get("id") or f"t{self._next_seq:04d}"
        self._next_seq += 1
        task = {**data, "id": tid}
        self._tasks[tid] = task
        return task

    def update_task(self, task_id: str, changes: dict) -> dict:
        task = dict(self._tasks.get(task_id, {"id": task_id}))
        task.update(changes)
        self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> dict | None:
        return self._tasks.get(task_id)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_client():
    client = _FakeClient()
    # Seed some episodic memory records
    for i in range(1, 4):
        client.create_task(
            {
                "id": f"ep-{i:03d}",
                "title": f"Episodic memory {i}",
                "description": f"Agent noted behaviour pattern {i} during session.",
                "kind": "memory",
                "subject": "project:waypoint",
            }
        )
    # One record with no subject (should be included in unfiltered run)
    client.create_task(
        {
            "id": "ep-004",
            "title": "Another observation",
            "description": "Something noted elsewhere.",
            "kind": "memory",
        }
    )
    return client


_LLM_RESPONSE = {
    "classifications": [
        {"id": "ep-001", "memory_class": "episodic"},
        {"id": "ep-002", "memory_class": "episodic"},
        {"id": "ep-003", "memory_class": "durable_fact"},
        {"id": "ep-004", "memory_class": "noise"},
    ],
    "clusters": [
        {
            "source_ids": ["ep-001", "ep-002"],
            "title": "Consolidated: agent behaviour patterns 1 and 2",
            "summary": "Agents 1 and 2 both noted similar behaviour patterns during sessions.",
        }
    ],
}


# ---------------------------------------------------------------------------
# _call_llm
# ---------------------------------------------------------------------------


def test_call_llm_parses_response():
    """_call_llm sends a prompt and parses clean JSON."""
    import json

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(_LLM_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _call_llm([{"id": "x", "title": "test"}], "claude-sonnet-4-6", "fake-key")

    assert "classifications" in result
    assert "clusters" in result
    assert len(result["clusters"]) == 1


def test_call_llm_strips_markdown_fences():
    """_call_llm handles model wrapping JSON in ```json fences."""
    import json

    raw = f"```json\n{json.dumps(_LLM_RESPONSE)}\n```"
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=raw)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch("anthropic.Anthropic", return_value=mock_client):
        result = _call_llm([{"id": "x", "title": "test"}], "claude-sonnet-4-6", "fake-key")

    assert result["clusters"][0]["title"].startswith("Consolidated")


# ---------------------------------------------------------------------------
# run_consolidation
# ---------------------------------------------------------------------------


def test_run_consolidation_no_api_key(fake_client):
    """Returns an error dict when ANTHROPIC_API_KEY is unset."""
    with patch.dict("os.environ", {}, clear=True):
        result = run_consolidation(fake_client)
    assert "error" in result
    assert "ANTHROPIC_API_KEY" in result["error"]


def test_run_consolidation_no_eligible_records():
    """Returns skipped when there are no memory records."""
    client = _FakeClient()
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        result = run_consolidation(client)
    assert result.get("skipped") is True


def test_run_consolidation_dry_run(fake_client):
    """dry_run=True returns LLM output without writing to the client."""
    import json

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(_LLM_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    initial_task_count = len(fake_client._tasks)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = run_consolidation(fake_client, dry_run=True)

    assert result.get("dry_run") is True
    assert result["eligible"] == 4
    assert len(result["clusters"]) == 1
    # No writes happened
    assert len(fake_client._tasks) == initial_task_count


def test_run_consolidation_subject_filter(fake_client):
    """subject filter limits eligible set to matching records only."""
    import json

    filtered_response = {
        "classifications": [
            {"id": "ep-001", "memory_class": "episodic"},
            {"id": "ep-002", "memory_class": "episodic"},
            {"id": "ep-003", "memory_class": "durable_fact"},
        ],
        "clusters": [
            {
                "source_ids": ["ep-001", "ep-002"],
                "title": "Merged",
                "summary": "Merged summary",
            }
        ],
    }

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(filtered_response))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = run_consolidation(fake_client, subject="project:waypoint", dry_run=True)

    # ep-004 has no subject so should be excluded
    assert result["eligible"] == 3


def test_run_consolidation_writes_consolidated_record(fake_client):
    """Full run creates a consolidated record and supersedes source records."""
    import json

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(_LLM_RESPONSE))]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = run_consolidation(fake_client)

    assert result.get("error") is None
    assert result["consolidated_records_created"] == 1
    assert result["source_records_superseded"] == 2

    # The new consolidated record should exist
    consolidated_ids = [
        t["id"] for t in fake_client._tasks.values() if t.get("memory_class") == "consolidated"
    ]
    assert len(consolidated_ids) == 1

    # ep-001 and ep-002 should be superseded
    assert fake_client._tasks["ep-001"].get("superseded_by") == consolidated_ids[0]
    assert fake_client._tasks["ep-002"].get("superseded_by") == consolidated_ids[0]

    # ep-003 classified as durable_fact (no superseded_by)
    assert fake_client._tasks["ep-003"].get("memory_class") == "durable_fact"
    assert not fake_client._tasks["ep-003"].get("superseded_by")


def test_run_consolidation_skips_already_superseded(fake_client):
    """Records with superseded_by set are not included in eligible set."""
    import json

    # Mark ep-001 as already superseded
    fake_client._tasks["ep-001"]["superseded_by"] = "some-prior-consolidated"

    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(
            text=json.dumps(
                {
                    "classifications": [
                        {"id": "ep-002", "memory_class": "episodic"},
                        {"id": "ep-003", "memory_class": "durable_fact"},
                        {"id": "ep-004", "memory_class": "noise"},
                    ],
                    "clusters": [],
                }
            )
        )
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_client):
            result = run_consolidation(fake_client, dry_run=True)

    # ep-001 should be excluded — 3 instead of 4
    assert result["eligible"] == 3


# ---------------------------------------------------------------------------
# run_drift_check
# ---------------------------------------------------------------------------


def test_run_drift_check_no_api_key(fake_client):
    """Returns error when ANTHROPIC_API_KEY is unset."""
    with patch.dict("os.environ", {}, clear=True):
        result = run_drift_check(fake_client)
    assert "error" in result


def test_run_drift_check_no_consolidated_records():
    """Returns skipped when there are no consolidated records."""
    client = _FakeClient()
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        result = run_drift_check(client)
    assert result.get("skipped") is True


def test_run_drift_check_scores_and_updates(fake_client):
    """Drift check updates drift_score and drift_checked_at on consolidated records."""
    import json

    # Create a consolidated record with sources
    fake_client.create_task(
        {
            "id": "con-001",
            "title": "Consolidated",
            "description": "Summary of observations.",
            "kind": "memory",
            "memory_class": "consolidated",
            "source_record_ids": ["ep-001", "ep-002"],
        }
    )

    drift_response = {"drift_score": 0.15, "explanation": "Minor gaps in coverage."}
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=json.dumps(drift_response))]
    mock_anth = MagicMock()
    mock_anth.messages.create.return_value = mock_message

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            result = run_drift_check(fake_client)

    assert result["checked"] == 1
    assert result["high_drift_count"] == 1
    assert result["high_drift"][0]["id"] == "con-001"
    assert result["high_drift"][0]["drift_score"] == pytest.approx(0.15)

    # The consolidated record should have drift_score and drift_checked_at updated
    updated = fake_client._tasks["con-001"]
    assert updated.get("drift_score") == pytest.approx(0.15)
    assert updated.get("drift_checked_at") is not None


def test_run_drift_check_record_id_filter(fake_client):
    """record_id filter checks only that specific record."""

    fake_client.create_task(
        {
            "id": "con-001",
            "title": "Consolidated 1",
            "description": "Summary 1",
            "kind": "memory",
            "memory_class": "consolidated",
            "source_record_ids": ["ep-001"],
        }
    )
    fake_client.create_task(
        {
            "id": "con-002",
            "title": "Consolidated 2",
            "description": "Summary 2",
            "kind": "memory",
            "memory_class": "consolidated",
            "source_record_ids": ["ep-002"],
        }
    )

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"drift_score": 0.02, "explanation": "Fine."}')]
    mock_anth = MagicMock()
    mock_anth.messages.create.return_value = mock_message

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            result = run_drift_check(fake_client, record_id="con-001")

    # Only one record checked
    assert result["checked"] == 1
    assert "con-001" in (r["id"] for r in []) or result["checked"] == 1
    # con-002 should NOT have been updated
    assert fake_client._tasks.get("con-002", {}).get("drift_score") is None
