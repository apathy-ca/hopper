"""drift catchup for hopper_instances and tasks

Reconciles the pre-existing drift between the ORM models and the initial
alembic schema. Unrelated to Phase 4's records/revisions work — kept in
its own migration so the blast-radius of each change is obvious.

Changes:
- Create ``task_delegations`` table (present in models, never in schema).
- Add ``hopper_instances.instance_type`` (default PERSISTENT for existing
  rows), ``runtime_metadata``, ``started_at``, ``stopped_at``.
- Retype ``hopper_instances.scope`` and ``.status`` as non-native enums.
- Add ``tasks.instance_id`` with FK to hopper_instances.

Deferred: changing ``hopper_instances.parent_id`` FK to ON DELETE CASCADE
requires a constraint naming convention to work with batch mode on
SQLite — handled in a follow-up once alembic env.py carries a convention.
- Drop ``tasks.feedback`` (moved to task_feedback table).

SQLite requires batch mode for alter_column and FK changes — all the
mutations to existing tables go through ``op.batch_alter_table``.

Revision ID: d41987b2b8f5
Revises: 7e78d9e045f0
Create Date: 2026-04-22 19:03:00.123686
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = "d41987b2b8f5"
down_revision: Union[str, Sequence[str], None] = "7e78d9e045f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_HOPPER_SCOPE_ENUM = sa.Enum(
    "GLOBAL", "PROJECT", "ORCHESTRATION", "PERSONAL", "FAMILY", "EVENT", "FEDERATED",
    name="hopper_scope",
    native_enum=False,
)
_INSTANCE_STATUS_ENUM = sa.Enum(
    "CREATED", "STARTING", "RUNNING", "STOPPING", "STOPPED", "PAUSED", "ERROR",
    "TERMINATED",
    name="instance_status",
    native_enum=False,
)
_INSTANCE_TYPE_ENUM = sa.Enum(
    "PERSISTENT", "EPHEMERAL", "TEMPORARY",
    name="instance_type",
    native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "task_delegations",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("task_id", sa.String(length=50), nullable=False),
        sa.Column("source_instance_id", sa.String(length=100), nullable=True),
        sa.Column("target_instance_id", sa.String(length=100), nullable=True),
        sa.Column("delegation_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("delegated_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "result",
            postgresql.JSONB(astext_type=Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("delegated_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_instance_id"], ["hopper_instances.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_instance_id"], ["hopper_instances.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_task_delegations_source_instance_id",
        "task_delegations",
        ["source_instance_id"],
    )
    op.create_index("ix_task_delegations_status", "task_delegations", ["status"])
    op.create_index(
        "ix_task_delegations_target_instance_id",
        "task_delegations",
        ["target_instance_id"],
    )
    op.create_index("ix_task_delegations_task_id", "task_delegations", ["task_id"])

    # hopper_instances: add columns, retype scope/status, cascade parent_id
    with op.batch_alter_table("hopper_instances") as batch:
        batch.add_column(
            sa.Column(
                "instance_type",
                _INSTANCE_TYPE_ENUM,
                nullable=False,
                server_default="PERSISTENT",
            )
        )
        batch.add_column(
            sa.Column(
                "runtime_metadata",
                postgresql.JSONB(astext_type=Text()).with_variant(
                    sa.JSON(), "sqlite"
                ),
                nullable=True,
            )
        )
        batch.add_column(sa.Column("started_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("stopped_at", sa.DateTime(), nullable=True))
        batch.alter_column(
            "scope",
            existing_type=sa.VARCHAR(length=50),
            type_=_HOPPER_SCOPE_ENUM,
            existing_nullable=False,
        )
        batch.alter_column(
            "status",
            existing_type=sa.VARCHAR(length=50),
            type_=_INSTANCE_STATUS_ENUM,
            existing_nullable=False,
        )

    # tasks: add instance_id FK, drop feedback column
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("instance_id", sa.String(length=100), nullable=True))
        batch.create_foreign_key(
            "fk_tasks_instance_id",
            "hopper_instances",
            ["instance_id"],
            ["id"],
        )
        batch.drop_column("feedback")


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("feedback", sqlite.JSON(), nullable=True))
        batch.drop_constraint("fk_tasks_instance_id", type_="foreignkey")
        batch.drop_column("instance_id")

    with op.batch_alter_table("hopper_instances") as batch:
        batch.alter_column(
            "status",
            existing_type=_INSTANCE_STATUS_ENUM,
            type_=sa.VARCHAR(length=50),
            existing_nullable=False,
        )
        batch.alter_column(
            "scope",
            existing_type=_HOPPER_SCOPE_ENUM,
            type_=sa.VARCHAR(length=50),
            existing_nullable=False,
        )
        batch.drop_column("stopped_at")
        batch.drop_column("started_at")
        batch.drop_column("runtime_metadata")
        batch.drop_column("instance_type")

    op.drop_index("ix_task_delegations_task_id", table_name="task_delegations")
    op.drop_index(
        "ix_task_delegations_target_instance_id", table_name="task_delegations"
    )
    op.drop_index("ix_task_delegations_status", table_name="task_delegations")
    op.drop_index(
        "ix_task_delegations_source_instance_id", table_name="task_delegations"
    )
    op.drop_table("task_delegations")
