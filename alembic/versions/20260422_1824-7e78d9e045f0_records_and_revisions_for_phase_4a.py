"""records and revisions for phase 4a

Introduces the append-only revisioned record model. See
plans/Phase-4-Revisions-DID-Agent-Plan.md.

Records are thin identity rows (id, type, instance, pointer to current
revision). Revisions carry the authoritative state at each write along
with author_did and author_location — a per-write signal surface rather
than per-record.

This migration does not touch existing tables. Pre-existing drift between
the Task/HopperInstance models and the initial schema is left alone and
should be reconciled in a separate migration.

Revision ID: 7e78d9e045f0
Revises: 233e207e2773
Create Date: 2026-04-22 18:24:12.566088
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7e78d9e045f0"
down_revision: Union[str, Sequence[str], None] = "233e207e2773"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "records",
        sa.Column("id", sa.String(length=50), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("instance_id", sa.String(length=100), nullable=True),
        sa.Column("current_revision_id", sa.String(length=26), nullable=True),
        sa.Column("tombstoned_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["current_revision_id"], ["revisions.id"], use_alter=True
        ),
        sa.ForeignKeyConstraint(["instance_id"], ["hopper_instances.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_records_type", "records", ["type"])
    op.create_index("idx_records_instance_id", "records", ["instance_id"])
    op.create_index("idx_records_tombstoned_at", "records", ["tombstoned_at"])

    op.create_table(
        "revisions",
        sa.Column("id", sa.String(length=26), nullable=False),
        sa.Column("record_id", sa.String(length=50), nullable=False),
        sa.Column("parent_revision_id", sa.String(length=26), nullable=True),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("author_did", sa.String(length=200), nullable=True),
        sa.Column("author_location", sa.String(length=100), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["parent_revision_id"], ["revisions.id"]),
        sa.ForeignKeyConstraint(["record_id"], ["records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_revisions_record_created", "revisions", ["record_id", "created_at"]
    )
    op.create_index("idx_revisions_author_did", "revisions", ["author_did"])
    op.create_index("idx_revisions_action", "revisions", ["action"])


def downgrade() -> None:
    op.drop_index("idx_revisions_action", table_name="revisions")
    op.drop_index("idx_revisions_author_did", table_name="revisions")
    op.drop_index("idx_revisions_record_created", table_name="revisions")
    op.drop_table("revisions")
    op.drop_index("idx_records_tombstoned_at", table_name="records")
    op.drop_index("idx_records_instance_id", table_name="records")
    op.drop_index("idx_records_type", table_name="records")
    op.drop_table("records")
