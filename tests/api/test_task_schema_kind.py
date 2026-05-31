"""Tests for first-class kind + structured memory fields on task schemas.

These fields are additive: TaskResponse must default kind="task" and leave the
memory fields None when absent (so legacy Task ORM rows that lack the attributes
still validate via from_attributes), and round-trip the values when present.
"""

from datetime import datetime

from hopper.api.schemas.task import (
    Priority,
    Status,
    TaskCreate,
    TaskResponse,
    TaskSource,
    VelocityRequirement,
)


class _LegacyOrmTask:
    """Stand-in for a legacy Task ORM row with no kind/subject/scope/provenance."""

    def __init__(self):
        self.id = "task-1"
        self.title = "Legacy task"
        self.description = "Created before kind existed"
        self.project = None
        self.tags = []
        self.priority = Priority.MEDIUM
        self.executor_preference = None
        self.required_capabilities = []
        self.estimated_effort = None
        self.velocity_requirement = VelocityRequirement.MEDIUM
        self.requester = None
        self.created_at = datetime(2026, 5, 30, 12, 0, 0)
        self.updated_at = datetime(2026, 5, 30, 12, 0, 0)
        self.status = Status.PENDING
        self.owner = None
        self.external_id = None
        self.external_url = None
        self.external_platform = None
        self.source = TaskSource.API
        self.conversation_id = None
        self.context = None
        self.depends_on = []
        self.blocks = []


class TestTaskResponseKindDefaults:
    def test_legacy_orm_row_without_fields_validates_with_defaults(self):
        # model_validate over an ORM object missing these attributes must not
        # raise; it falls back to the defaults.
        resp = TaskResponse.model_validate(_LegacyOrmTask())
        assert resp.kind == "task"
        assert resp.subject is None
        assert resp.scope is None
        assert resp.provenance is None

    def test_memory_fields_roundtrip_when_present(self):
        orm = _LegacyOrmTask()
        orm.kind = "memory"
        orm.subject = "user:preferences"
        orm.scope = "shared-with-user"
        orm.provenance = "conversation 2026-05-30"

        resp = TaskResponse.model_validate(orm)
        assert resp.kind == "memory"
        assert resp.subject == "user:preferences"
        assert resp.scope == "shared-with-user"
        assert resp.provenance == "conversation 2026-05-30"


class TestTaskCreateKind:
    def test_defaults_when_absent(self):
        create = TaskCreate(title="A task", description="do the thing")
        assert create.kind == "task"
        assert create.subject is None
        assert create.scope is None
        assert create.provenance is None

    def test_accepts_memory_fields(self):
        create = TaskCreate(
            title="A memory",
            description="remember this",
            kind="memory",
            subject="self",
            scope="private",
            provenance="observation",
        )
        assert create.kind == "memory"
        assert create.subject == "self"
        assert create.scope == "private"
        assert create.provenance == "observation"
