"""Tests for RecordTaskRepository — the records+revisions-backed task repo.

Phase 1 is additive: this proves the repository persists with the correct
``records.type`` per kind, hydrates from revision payloads, segments list by
kind, applies payload-derived filters in Python, merges updates, tombstones on
soft-delete, and substring-searches title/description/tags.

Uses the sync ``db_session`` fixture (in-memory SQLite, rolled back per test).
"""

import pytest

from hopper.api.repositories.record_tasks import RecordTaskRepository
from hopper.models import Record
from hopper.models.enums import HopperScope, InstanceStatus, InstanceType
from hopper.models.hopper_instance import HopperInstance

AUTHOR_DID = "did:key:test-author"
AUTHOR_LOCATION = "pytest"


@pytest.fixture
def repo(db_session):
    # Seed the 'local' hopper_instances row via the ORM so the revision
    # writer's raw-SQL _ensure_instance (which omits the NOT NULL
    # instance_type column) finds an existing row and skips its insert.
    if db_session.get(HopperInstance, "local") is None:
        db_session.add(
            HopperInstance(
                id="local",
                name="local",
                scope=HopperScope.PERSONAL,
                instance_type=InstanceType.PERSISTENT,
                status=InstanceStatus.RUNNING,
            )
        )
        db_session.flush()
    return RecordTaskRepository(db_session)


def _create(repo, **payload):
    return repo.create(payload, author_did=AUTHOR_DID, author_location=AUTHOR_LOCATION)


class TestCreatePersistsKind:
    @pytest.mark.parametrize("kind", ["task", "memory", "job"])
    def test_create_sets_records_type(self, repo, db_session, kind):
        result = _create(repo, title=f"a {kind}", kind=kind)
        assert result["kind"] == kind
        record = db_session.get(Record, result["id"])
        assert record is not None
        assert record.type == kind

    def test_create_defaults_to_task(self, repo, db_session):
        result = _create(repo, title="no kind given")
        assert result["kind"] == "task"
        assert db_session.get(Record, result["id"]).type == "task"

    def test_create_returns_task_shaped_dict(self, repo):
        result = _create(
            repo,
            title="shaped",
            description="d",
            status="in_progress",
            priority="high",
            tags=["a", "b"],
            project="hopper",
        )
        for key in (
            "id",
            "kind",
            "title",
            "description",
            "status",
            "priority",
            "tags",
            "project",
            "parent_id",
            "assigned_to",
            "created_at",
            "updated_at",
        ):
            assert key in result
        assert result["status"] == "in_progress"
        assert result["priority"] == "high"
        assert result["tags"] == ["a", "b"]

    def test_create_passes_through_memory_fields(self, repo):
        result = _create(
            repo,
            title="a memory",
            kind="memory",
            subject="user:prefs",
            scope="private",
            provenance="observation",
        )
        assert result["subject"] == "user:prefs"
        assert result["scope"] == "private"
        assert result["provenance"] == "observation"


class TestGetHydrates:
    def test_get_hydrates_from_payload(self, repo):
        created = _create(repo, title="fetch me", description="body", tags=["x"])
        got = repo.get(created["id"])
        assert got is not None
        assert got["id"] == created["id"]
        assert got["title"] == "fetch me"
        assert got["description"] == "body"
        assert got["tags"] == ["x"]
        assert got["kind"] == "task"

    def test_get_missing_returns_none(self, repo):
        assert repo.get("does-not-exist") is None


class TestListSegmentsByKind:
    def test_list_defaults_to_task_only(self, repo):
        _create(repo, title="real task", kind="task")
        _create(repo, title="a memory", kind="memory")
        _create(repo, title="a job", kind="job")

        items, total = repo.list()
        titles = {t["title"] for t in items}
        assert titles == {"real task"}
        assert total == 1

    def test_all_kinds_includes_everything(self, repo):
        _create(repo, title="real task", kind="task")
        _create(repo, title="a memory", kind="memory")
        _create(repo, title="a job", kind="job")

        items, total = repo.list(all_kinds=True)
        assert total == 3
        assert {t["kind"] for t in items} == {"task", "memory", "job"}

    def test_list_kind_memory(self, repo):
        _create(repo, title="real task", kind="task")
        _create(repo, title="a memory", kind="memory")

        items, total = repo.list(kind="memory")
        assert total == 1
        assert items[0]["title"] == "a memory"

    def test_list_status_filter(self, repo):
        _create(repo, title="pending one", status="pending")
        _create(repo, title="done one", status="done")

        items, total = repo.list(status="done")
        assert total == 1
        assert items[0]["title"] == "done one"

    def test_list_tag_filter(self, repo):
        _create(repo, title="tagged", tags=["urgent", "backend"])
        _create(repo, title="other", tags=["frontend"])

        items, total = repo.list(tags=["urgent"])
        assert total == 1
        assert items[0]["title"] == "tagged"

    def test_list_sort_and_paginate(self, repo):
        for i in range(3):
            _create(repo, title=f"t{i}", priority="medium")
        items, total = repo.list(sort_by="title", sort_order="asc", limit=2)
        assert total == 3
        assert [t["title"] for t in items] == ["t0", "t1"]


class TestUpdateMerges:
    def test_update_merges_changes(self, repo):
        created = _create(repo, title="orig", description="keep me", status="pending")
        updated = repo.update(
            created["id"],
            {"status": "in_progress", "title": "changed"},
            author_did=AUTHOR_DID,
            author_location=AUTHOR_LOCATION,
        )
        assert updated["status"] == "in_progress"
        assert updated["title"] == "changed"
        # Unchanged fields preserved from prior payload.
        assert updated["description"] == "keep me"

    def test_update_preserves_kind(self, repo):
        created = _create(repo, title="mem", kind="memory")
        updated = repo.update(
            created["id"],
            {"kind": "task", "title": "still memory"},
            author_did=AUTHOR_DID,
            author_location=AUTHOR_LOCATION,
        )
        assert updated["kind"] == "memory"

    def test_update_missing_returns_none(self, repo):
        assert (
            repo.update(
                "nope",
                {"status": "done"},
                author_did=AUTHOR_DID,
                author_location=AUTHOR_LOCATION,
            )
            is None
        )


class TestSoftDeleteTombstones:
    def test_soft_delete_excludes_from_list_and_get(self, repo, db_session):
        created = _create(repo, title="delete me", kind="task")
        ok = repo.soft_delete(created["id"], author_did=AUTHOR_DID, author_location=AUTHOR_LOCATION)
        assert ok is True

        record = db_session.get(Record, created["id"])
        assert record.tombstoned_at is not None

        assert repo.get(created["id"]) is None
        items, total = repo.list()
        assert total == 0
        assert items == []

    def test_soft_delete_missing_returns_false(self, repo):
        assert (
            repo.soft_delete("nope", author_did=AUTHOR_DID, author_location=AUTHOR_LOCATION)
            is False
        )


class TestSearch:
    def test_search_matches_title(self, repo):
        _create(repo, title="authentication work")
        _create(repo, title="unrelated")
        items, total = repo.search("authentication")
        assert total == 1
        assert items[0]["title"] == "authentication work"

    def test_search_matches_description(self, repo):
        _create(repo, title="t1", description="needs OAuth flow")
        _create(repo, title="t2", description="something else")
        items, total = repo.search("oauth")
        assert total == 1
        assert items[0]["title"] == "t1"

    def test_search_matches_tags(self, repo):
        _create(repo, title="t1", tags=["security"])
        _create(repo, title="t2", tags=["ui"])
        items, total = repo.search("security")
        assert total == 1
        assert items[0]["title"] == "t1"
