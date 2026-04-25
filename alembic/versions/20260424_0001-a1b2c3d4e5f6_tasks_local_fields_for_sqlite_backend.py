"""Add missing LocalTask fields to tasks table for SQLite storage backend.

Adds the five columns present in LocalTask that were never reflected in the
tasks ORM model: assigned_to, last_heartbeat, expected_heartbeat, parent_id,
deleted. These are required for the SQLite storage path to replace markdown.

All columns are nullable / have defaults so existing rows are unaffected.
SQLite requires batch mode for alter operations.

Revision ID: a1b2c3d4e5f6
Revises: d41987b2b8f5
Create Date: 2026-04-24 00:01:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "d41987b2b8f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(
            sa.Column("assigned_to", sa.String(length=200), nullable=True)
        )
        batch.add_column(
            sa.Column("last_heartbeat", sa.DateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column("expected_heartbeat", sa.DateTime(), nullable=True)
        )
        batch.add_column(
            sa.Column("parent_id", sa.String(length=50), nullable=True)
        )
        batch.add_column(
            sa.Column("deleted", sa.Boolean(), nullable=False, server_default="0")
        )

    # Index for parent_id lookups (get_children)
    op.create_index("idx_tasks_parent_id", "tasks", ["parent_id"])
    # Index for stale detection (in_progress + assigned_to)
    op.create_index("idx_tasks_assigned_to", "tasks", ["assigned_to"])


def downgrade() -> None:
    op.drop_index("idx_tasks_assigned_to", table_name="tasks")
    op.drop_index("idx_tasks_parent_id", table_name="tasks")

    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("deleted")
        batch.drop_column("parent_id")
        batch.drop_column("expected_heartbeat")
        batch.drop_column("last_heartbeat")
        batch.drop_column("assigned_to")
