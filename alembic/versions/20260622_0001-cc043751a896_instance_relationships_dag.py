"""instance_relationships_dag

Revision ID: cc043751a896
Revises: d5e6f7a8b9c0
Create Date: 2026-06-22

Add instance_relationships join table to support DAG-based instance hierarchy.
An instance can be a child of multiple overseers (DAG, not tree). Composite PK
on (parent_id, child_id) makes edge inserts idempotent.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "cc043751a896"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instance_relationships",
        sa.Column("parent_id", sa.String(length=100), nullable=False),
        sa.Column("child_id", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["hopper_instances.id"],
            ondelete="CASCADE",
            name="fk_instance_relationships_parent_id_hopper_instances",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["hopper_instances.id"],
            ondelete="CASCADE",
            name="fk_instance_relationships_child_id_hopper_instances",
        ),
        sa.PrimaryKeyConstraint("parent_id", "child_id"),
    )
    op.create_index(
        "ix_instance_relationships_child_id",
        "instance_relationships",
        ["child_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instance_relationships_child_id",
        table_name="instance_relationships",
    )
    op.drop_table("instance_relationships")
