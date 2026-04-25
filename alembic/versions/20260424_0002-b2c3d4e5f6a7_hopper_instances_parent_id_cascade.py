"""Add ON DELETE CASCADE to hopper_instances.parent_id FK.

The initial schema created this FK anonymously which prevented Alembic's
batch-mode from dropping it on SQLite.  Now that Base.metadata carries an
explicit naming_convention and env.py uses render_as_batch=True, we can
safely recreate the table with the named, cascading FK.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24 00:02:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table(
        "hopper_instances",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        },
    ) as batch:
        # Drop the old anonymous FK (SQLite batch-mode recreates the whole table)
        batch.drop_constraint(
            "fk_hopper_instances_parent_id_hopper_instances",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_hopper_instances_parent_id_hopper_instances",
            "hopper_instances",
            ["parent_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "hopper_instances",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        },
    ) as batch:
        batch.drop_constraint(
            "fk_hopper_instances_parent_id_hopper_instances",
            type_="foreignkey",
        )
        batch.create_foreign_key(
            "fk_hopper_instances_parent_id_hopper_instances",
            "hopper_instances",
            ["parent_id"],
            ["id"],
        )
