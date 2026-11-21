"""Tests for memory consolidation engine (consolidation.py).

Uses a minimal in-memory fake client and a mocked LLM response so no network
calls or API keys are required.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from hopper.memory.consolidation import (
    _call_llm,
    rank_for_consolidation,
    run_consolidation,
    run_drift_check,
    run_northbound,
)

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


# ---------------------------------------------------------------------------
# Interleaving with existing consolidated records
# ---------------------------------------------------------------------------


def _mock_anthropic(*responses):
    """Anthropic client mock returning each response dict in turn."""
    import json

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [
        MagicMock(content=[MagicMock(text=json.dumps(r))]) for r in responses
    ]
    return mock_client


@pytest.fixture
def client_with_consolidated(fake_client):
    fake_client.create_task(
        {
            "id": "con-001",
            "title": "Behaviour patterns",
            "description": "Earlier summary of behaviour patterns.",
            "kind": "memory",
            "subject": "project:waypoint",
            "memory_class": "consolidated",
            "source_record_ids": ["old-001", "old-002"],
            "consolidation_run_id": "consolidate-old",
            "consolidated_at": "2026-01-01T00:00:00+00:00",
        }
    )
    # Different subject: must not be offered as context for waypoint records
    fake_client.create_task(
        {
            "id": "con-other",
            "title": "Unrelated",
            "description": "Other project summary.",
            "kind": "memory",
            "subject": "project:other",
            "memory_class": "consolidated",
            "source_record_ids": ["x-1", "x-2"],
        }
    )
    fake_client.notes = {}

    def add_task_note(task_id, body, author=None):
        fake_client.notes.setdefault(task_id, []).append(body)
        return fake_client._tasks[task_id]

    fake_client.add_task_note = add_task_note
    return fake_client


def test_consolidated_records_are_context_not_episodes(client_with_consolidated):
    """Consolidated records appear in the prompt as read-only context, not as records."""
    mock_anth = _mock_anthropic({"classifications": [], "clusters": []})

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            result = run_consolidation(
                client_with_consolidated, subject="project:waypoint", dry_run=True
            )

    assert result["eligible"] == 3
    prompt = mock_anth.messages.create.call_args.kwargs["messages"][0]["content"]
    context, records = prompt.split("Records:\n\n", 1)
    assert "read-only context" in context
    assert "ID: con-001" in context
    assert "Earlier summary of behaviour patterns." in context
    assert "con-001" not in records
    assert "con-other" not in prompt


def test_extends_existing_consolidated_record(client_with_consolidated):
    """A cluster with extends_id updates that record instead of creating a new one."""
    response = {
        "classifications": [
            {"id": "ep-001", "memory_class": "episodic"},
            {"id": "ep-002", "memory_class": "episodic"},
            {"id": "ep-003", "memory_class": "episodic"},
        ],
        "clusters": [
            {
                "source_ids": ["ep-001"],
                "title": "Behaviour patterns (extended)",
                "summary": "Earlier summary plus pattern 1.",
                "extends_id": "con-001",
            },
            {
                "source_ids": ["ep-002", "ep-003"],
                "title": "New cluster",
                "summary": "Patterns 2 and 3.",
                "extends_id": None,
            },
        ],
    }
    client = client_with_consolidated
    before = len(client._tasks)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=_mock_anthropic(response)):
            result = run_consolidation(client, subject="project:waypoint")

    assert result["errors"] == []
    assert result["consolidated_records_updated"] == 1
    assert result["consolidated_records_created"] == 1
    assert result["source_records_superseded"] == 3
    assert len(client._tasks) == before + 1  # only the new cluster was created

    con = client._tasks["con-001"]
    assert con["description"] == "Earlier summary plus pattern 1."
    assert con["title"] == "Behaviour patterns (extended)"
    assert con["source_record_ids"] == ["old-001", "old-002", "ep-001"]
    assert con["consolidation_run_id"] == result["run_id"]
    assert con["consolidated_at"] != "2026-01-01T00:00:00+00:00"
    assert con["memory_class"] == "consolidated"
    assert not con.get("superseded_by")

    assert client._tasks["ep-001"]["superseded_by"] == "con-001"
    new_id = client._tasks["ep-002"]["superseded_by"]
    assert new_id not in ("con-001", None)
    assert client._tasks["ep-003"]["superseded_by"] == new_id

    # Provenance: the previous summary and the added sources are recorded
    (note,) = client.notes["con-001"]
    assert result["run_id"] in note
    assert "ep-001" in note
    assert "Earlier summary of behaviour patterns." in note
    assert "consolidate-old" in note


def test_unknown_ids_from_llm_are_ignored(client_with_consolidated):
    """Unknown extends_id / source ids / classification ids are dropped."""
    response = {
        "classifications": [
            {"id": "ep-001", "memory_class": "episodic"},
            {"id": "con-001", "memory_class": "noise"},  # context record: ignored
            {"id": "bogus", "memory_class": "noise"},
        ],
        "clusters": [
            # Unknown extends_id -> treated as new cluster; needs 2 valid sources
            {
                "source_ids": ["ep-001", "ep-002", "bogus"],
                "title": "T",
                "summary": "S",
                "extends_id": "con-other",  # exists but was not supplied as context
            },
            # Consolidated id smuggled into sources -> stripped, < 2 left -> dropped
            {"source_ids": ["ep-003", "con-001"], "title": "X", "summary": "Y"},
            # Extends a hallucinated id with one source -> dropped
            {"source_ids": ["ep-003"], "title": "Z", "summary": "W", "extends_id": "nope"},
        ],
    }
    client = client_with_consolidated

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=_mock_anthropic(response)):
            result = run_consolidation(client, subject="project:waypoint", dry_run=True)

    assert result["classifications"] == [{"id": "ep-001", "memory_class": "episodic"}]
    assert result["clusters"] == [
        {
            "source_ids": ["ep-001", "ep-002"],
            "title": "T",
            "summary": "S",
            "extends_id": None,
            "pending_id": "new-1",
        }
    ]

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=_mock_anthropic(response)):
            result = run_consolidation(client, subject="project:waypoint")

    assert result["consolidated_records_updated"] == 0
    assert result["consolidated_records_created"] == 1
    assert client._tasks["con-001"]["description"] == "Earlier summary of behaviour patterns."
    assert client._tasks["con-001"].get("memory_class") == "consolidated"
    assert client._tasks["con-other"]["source_record_ids"] == ["x-1", "x-2"]
    assert not client._tasks["ep-003"].get("superseded_by")


def test_dry_run_extension_writes_nothing(client_with_consolidated):
    """dry_run reports extends_id but leaves the consolidated record untouched."""
    response = {
        "classifications": [],
        "clusters": [
            {"source_ids": ["ep-001"], "title": "T", "summary": "S", "extends_id": "con-001"}
        ],
    }
    client = client_with_consolidated
    snapshot = {k: dict(v) for k, v in client._tasks.items()}

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=_mock_anthropic(response)):
            result = run_consolidation(client, subject="project:waypoint", dry_run=True)

    assert result["clusters"][0]["extends_id"] == "con-001"
    assert client._tasks == snapshot
    assert client.notes == {}


def test_extensions_across_batches_compose(client_with_consolidated):
    """A later batch sees the earlier batch's extended summary; both sources are kept."""
    responses = [
        {
            "classifications": [],
            "clusters": [
                {
                    "source_ids": ["ep-001"],
                    "title": "T1",
                    "summary": "Summary after batch 1.",
                    "extends_id": "con-001",
                }
            ],
        },
        {
            "classifications": [],
            "clusters": [
                {
                    "source_ids": ["ep-002"],
                    "title": "T2",
                    "summary": "Summary after batch 2.",
                    "extends_id": "con-001",
                }
            ],
        },
        {"classifications": [], "clusters": []},
    ]
    client = client_with_consolidated
    mock_anth = _mock_anthropic(*responses)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            result = run_consolidation(client, subject="project:waypoint", batch_size=1)

    second_prompt = mock_anth.messages.create.call_args_list[1].kwargs["messages"][0]["content"]
    assert "Summary after batch 1." in second_prompt

    assert result["consolidated_records_updated"] == 1
    con = client._tasks["con-001"]
    assert con["description"] == "Summary after batch 2."
    assert con["source_record_ids"] == ["old-001", "old-002", "ep-001", "ep-002"]
    assert len(client.notes["con-001"]) == 1


def test_later_batch_extends_record_created_earlier_in_same_run(fake_client):
    """A summary created by batch 1 is context for batch 2 and can be extended there."""
    responses = [
        {
            "classifications": [],
            "clusters": [
                {
                    "source_ids": ["ep-001", "ep-002"],
                    "title": "Patterns",
                    "summary": "Patterns 1 and 2.",
                    "extends_id": None,
                }
            ],
        },
        {
            "classifications": [],
            "clusters": [
                {
                    "source_ids": ["ep-003"],
                    "title": "Patterns (all)",
                    "summary": "Patterns 1, 2 and 3.",
                    "extends_id": "new-1",
                }
            ],
        },
    ]
    mock_anth = _mock_anthropic(*responses)
    before = len(fake_client._tasks)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            dry = run_consolidation(
                fake_client, subject="project:waypoint", batch_size=2, dry_run=True
            )
    second_prompt = mock_anth.messages.create.call_args_list[1].kwargs["messages"][0]["content"]
    context = second_prompt.split("Records:\n\n", 1)[0]
    assert "ID: new-1" in context and "Patterns 1 and 2." in context
    assert dry["clusters"][0]["pending_id"] == "new-1"
    assert dry["clusters"][1]["extends_id"] == "new-1"
    assert len(fake_client._tasks) == before

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=_mock_anthropic(*responses)):
            result = run_consolidation(fake_client, subject="project:waypoint", batch_size=2)

    assert result["errors"] == []
    assert result["consolidated_records_created"] == 1
    assert result["consolidated_records_updated"] == 0
    assert result["source_records_superseded"] == 3
    assert len(fake_client._tasks) == before + 1
    new_id = fake_client._tasks["ep-001"]["superseded_by"]
    assert {fake_client._tasks[f"ep-00{i}"]["superseded_by"] for i in (1, 2, 3)} == {new_id}
    created = fake_client._tasks[new_id]
    assert created["title"] == "Patterns (all)"
    assert created["description"] == "Patterns 1, 2 and 3."
    assert created["source_record_ids"] == ["ep-001", "ep-002", "ep-003"]
    assert created["subject"] == "project:waypoint"


# ---------------------------------------------------------------------------
# rank_for_consolidation
# ---------------------------------------------------------------------------


def _ids(records):
    return [r["id"] for r in records]


def test_rank_class_tier_first():
    """Unclassified, then episodic, noise, durable_fact, then unknown classes."""
    records = [
        {"id": "a", "memory_class": "durable_fact"},
        {"id": "b", "memory_class": "weird"},
        {"id": "c", "memory_class": "noise"},
        {"id": "d", "memory_class": "episodic"},
        {"id": "e"},
    ]
    assert _ids(rank_for_consolidation(records)) == ["e", "d", "c", "a", "b"]


def test_rank_salient_first_unless_expired():
    records = [
        {"id": "plain"},
        {"id": "expired", "salience": True, "salient_until": "2000-01-01T00:00:00+00:00"},
        {
            "id": "salient-durable",
            "salience": True,
            "salient_until": "2999-01-01T00:00:00+00:00",
            "memory_class": "durable_fact",
        },
    ]
    assert _ids(rank_for_consolidation(records)) == ["salient-durable", "expired", "plain"]


def test_rank_fewer_notes_then_least_recently_touched():
    records = [
        {"id": "many-notes", "notes": [{}, {}], "updated_at": "2020-01-01T00:00:00"},
        {"id": "recent", "updated_at": "2026-06-01T00:00:00+00:00"},
        {"id": "old", "updated_at": "2025-01-01T00:00:00Z"},
        {"id": "created-only", "created_at": "2025-06-01T00:00:00"},
        {"id": "no-ts"},
    ]
    assert _ids(rank_for_consolidation(records)) == [
        "no-ts",
        "old",
        "created-only",
        "recent",
        "many-notes",
    ]


def test_rank_handles_datetimes_and_bad_values_deterministically():
    from datetime import UTC, datetime

    records = [
        {"id": "z", "updated_at": datetime(2026, 1, 1, tzinfo=UTC)},
        {"id": "y", "updated_at": datetime(2025, 1, 1)},  # naive = UTC
        {"id": "x", "updated_at": "not-a-date"},
        {"id": "w", "updated_at": "not-a-date"},
    ]
    ranked = rank_for_consolidation(records)
    assert _ids(ranked) == ["w", "x", "y", "z"]
    assert _ids(rank_for_consolidation(list(reversed(records)))) == _ids(ranked)
    # Input not mutated
    assert _ids(records) == ["z", "y", "x", "w"]


def test_max_records_keeps_weakest(fake_client):
    """max_records is applied after ranking, not to raw list order."""
    fake_client._tasks["ep-001"]["memory_class"] = "durable_fact"
    fake_client._tasks["ep-002"]["memory_class"] = "episodic"
    mock_anth = _mock_anthropic({"classifications": [], "clusters": []})

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            result = run_consolidation(fake_client, dry_run=True, max_records=2)

    assert result["eligible"] == 2
    prompt = mock_anth.messages.create.call_args.kwargs["messages"][0]["content"]
    assert "ID: ep-003" in prompt and "ID: ep-004" in prompt
    assert "ID: ep-001" not in prompt and "ID: ep-002" not in prompt


# ---------------------------------------------------------------------------
# Operator instructions
# ---------------------------------------------------------------------------


def _prompt_of(mock_anth, call=0):
    return mock_anth.messages.create.call_args_list[call].kwargs["messages"][0]["content"]


def test_call_llm_includes_delimited_operator_guidance():
    mock_anth = _mock_anthropic(_LLM_RESPONSE)
    with patch("anthropic.Anthropic", return_value=mock_anth):
        _call_llm(
            [{"id": "x", "title": "t"}],
            "m",
            "k",
            instructions="  Preserve exact quotes per contract.  ",
        )
    prompt = _prompt_of(mock_anth)
    assert "Operator guidance" in prompt
    assert "<<<OPERATOR GUIDANCE\nPreserve exact quotes per contract.\nOPERATOR GUIDANCE>>>" in (
        prompt
    )
    # Guidance precedes the output spec and the records
    assert prompt.index("OPERATOR GUIDANCE>>>") < prompt.index("Return ONLY valid JSON")


@pytest.mark.parametrize("instructions", [None, "", "   "])
def test_call_llm_omits_guidance_when_empty(instructions):
    mock_anth = _mock_anthropic(_LLM_RESPONSE)
    with patch("anthropic.Anthropic", return_value=mock_anth):
        _call_llm([{"id": "x", "title": "t"}], "m", "k", instructions=instructions)
    assert "OPERATOR GUIDANCE" not in _prompt_of(mock_anth)


def test_run_consolidation_threads_instructions_to_every_batch(fake_client):
    mock_anth = _mock_anthropic(*[{"classifications": [], "clusters": []}] * 2)
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            run_consolidation(fake_client, dry_run=True, batch_size=2, instructions="Focus X")
    assert mock_anth.messages.create.call_count == 2
    for i in range(2):
        assert "Focus X" in _prompt_of(mock_anth, i)


def test_run_consolidation_instructions_env_default(fake_client):
    env = {"ANTHROPIC_API_KEY": "fake", "HOPPER_CONSOLIDATION_INSTRUCTIONS": "From env"}

    mock_anth = _mock_anthropic({"classifications": [], "clusters": []})
    with patch.dict("os.environ", env):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            run_consolidation(fake_client, dry_run=True)
    assert "From env" in _prompt_of(mock_anth)

    # Explicit argument wins over the env var
    mock_anth = _mock_anthropic({"classifications": [], "clusters": []})
    with patch.dict("os.environ", env):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            run_consolidation(fake_client, dry_run=True, instructions="Explicit")
    assert "Explicit" in _prompt_of(mock_anth)
    assert "From env" not in _prompt_of(mock_anth)


def test_cli_consolidate_passes_instructions(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from hopper.cli.main import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hopper" / "tasks").mkdir(parents=True)
    monkeypatch.delenv("HOPPER_CONSOLIDATION_INSTRUCTIONS", raising=False)
    fake_result = {"dry_run": True, "eligible": 0, "classifications": [], "clusters": []}
    runner = CliRunner()

    with patch(
        "hopper.memory.consolidation.run_consolidation", return_value=fake_result
    ) as mock_run:
        result = runner.invoke(
            cli, ["memory", "consolidate", "--dry-run", "--instructions", "Keep quotes"]
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["instructions"] == "Keep quotes"

        result = runner.invoke(
            cli,
            ["memory", "consolidate", "--dry-run"],
            env={"HOPPER_CONSOLIDATION_INSTRUCTIONS": "Env guidance"},
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["instructions"] == "Env guidance"

    help_text = runner.invoke(cli, ["memory", "consolidate", "--help"]).output
    assert "--instructions" in help_text
    assert "line-level edits" in help_text


# ---------------------------------------------------------------------------
# Operator instructions: northbound + overseer
# ---------------------------------------------------------------------------


@pytest.fixture
def northbound_client():
    client = _FakeClient()
    for i, inst in enumerate(["child-a", "child-b"], start=1):
        client.create_task(
            {
                "id": f"c-{i}",
                "title": f"Summary {i}",
                "description": "Durable thing.",
                "kind": "memory",
                "memory_class": "consolidated",
                "instance": inst,
            }
        )
    return client


def test_northbound_threads_instructions(northbound_client):
    mock_anth = _mock_anthropic({"summaries": []})
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            run_northbound(
                northbound_client,
                "Overseer",
                ["child-a", "child-b"],
                dry_run=True,
                instructions="  Focus on shared auth.  ",
            )
    prompt = _prompt_of(mock_anth)
    assert "<<<OPERATOR GUIDANCE\nFocus on shared auth.\nOPERATOR GUIDANCE>>>" in prompt
    assert prompt.index("OPERATOR GUIDANCE>>>") < prompt.index("Return ONLY valid JSON")


def test_northbound_instructions_env_default_and_omitted(northbound_client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    monkeypatch.setenv("HOPPER_CONSOLIDATION_INSTRUCTIONS", "From env")
    mock_anth = _mock_anthropic({"summaries": []})
    with patch("anthropic.Anthropic", return_value=mock_anth):
        run_northbound(northbound_client, "O", ["child-a", "child-b"], dry_run=True)
    assert "From env" in _prompt_of(mock_anth)

    monkeypatch.delenv("HOPPER_CONSOLIDATION_INSTRUCTIONS")
    mock_anth = _mock_anthropic({"summaries": []})
    with patch("anthropic.Anthropic", return_value=mock_anth):
        run_northbound(northbound_client, "O", ["child-a", "child-b"], dry_run=True)
    assert "OPERATOR GUIDANCE" not in _prompt_of(mock_anth)


def test_run_bottom_up_threads_instructions(tmp_path):
    from contextlib import nullcontext

    from hopper.audit_agent import agent

    ok = {"run_id": "r", "eligible": 1}
    with (
        patch.object(agent, "_get_instances_with_memory", return_value=["Overseer", "child"]),
        patch.object(agent, "_get_instance_edges", return_value=[("Overseer", "child")]),
        patch.object(agent, "_ShadowConsolidationClient", lambda *a, **k: nullcontext(None)),
        patch.object(agent, "_update_instance_metadata"),
        patch("hopper.memory.consolidation.run_consolidation", return_value=ok) as mock_cons,
        patch("hopper.memory.consolidation.run_northbound", return_value=ok) as mock_nb,
    ):
        agent.run_bottom_up(
            tmp_path / "shadow.db",
            "did:key:x",
            tmp_path,
            run_northbound_pass=True,
            instructions="Guide",
        )
    assert mock_cons.call_count == 2
    assert all(c.kwargs["instructions"] == "Guide" for c in mock_cons.call_args_list)
    assert mock_nb.call_count == 1
    assert mock_nb.call_args.kwargs["instructions"] == "Guide"


def test_overseer_cli_passes_instructions(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from hopper.cli.main import cli

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".hopper" / "tasks").mkdir(parents=True)
    (tmp_path / ".hopper" / "shadow.db").write_text("")
    monkeypatch.delenv("HOPPER_CONSOLIDATION_INSTRUCTIONS", raising=False)
    runner = CliRunner()

    with (
        patch("hopper.audit_agent.agent._get_or_create_agent_did", return_value="did:key:x"),
        patch("hopper.audit_agent.agent.run_bottom_up", return_value={"instances": {}}) as mock_run,
    ):
        result = runner.invoke(cli, ["overseer", "consolidate", "--instructions", "Keep quotes"])
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["instructions"] == "Keep quotes"

        result = runner.invoke(
            cli,
            ["overseer", "consolidate"],
            env={"HOPPER_CONSOLIDATION_INSTRUCTIONS": "Env guidance"},
        )
        assert result.exit_code == 0, result.output
        assert mock_run.call_args.kwargs["instructions"] == "Env guidance"

    help_text = runner.invoke(cli, ["overseer", "northbound", "--help"]).output
    assert "--instructions" in help_text


# ---------------------------------------------------------------------------
# --propose is unsupported and must fail loudly
# ---------------------------------------------------------------------------


def test_propose_fails_without_writing_or_calling_llm(fake_client):
    fake_client.create_task({"id": "tk-1", "title": "L", "kind": "task", "tags": ["learning"]})
    fake_client.rekind_record = MagicMock()
    snapshot = {k: dict(v) for k, v in fake_client._tasks.items()}
    mock_anth = _mock_anthropic()

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "fake"}):
        with patch("anthropic.Anthropic", return_value=mock_anth):
            result = run_consolidation(fake_client, propose=True)

    assert "--propose is not supported" in result["error"]
    assert "Nothing was written" in result["error"]
    assert fake_client._tasks == snapshot
    fake_client.rekind_record.assert_not_called()
    mock_anth.messages.create.assert_not_called()


def test_cli_propose_exits_nonzero(tmp_path, monkeypatch):
    from click.testing import CliRunner

    from hopper.cli.main import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
    (tmp_path / ".hopper" / "tasks").mkdir(parents=True)
    result = CliRunner().invoke(cli, ["memory", "consolidate", "--propose"])
    assert result.exit_code == 1
    assert "--propose is not supported" in result.output
