"""repoint_legacy_task_fks_to_records

Revision ID: c3d4e5f6a7b8
Revises: b36aa411c248
Create Date: 2026-06-15 13:26:00.000000

Phase 4: TaskFeedback, RoutingDecision, TaskDelegation, and ExternalMapping
all had FKs pointing at the legacy `tasks.id` column. Re-point them at
`records.id` — the canonical server-side store. All four tables have 0
rows in production, so this is schema-only with no data migration.

Pre-existing tables predate the explicit naming convention in
models/base.py, so their FK constraints are unnamed in SQLite.
`naming_convention` is passed to batch_alter_table so Alembic can
assign conventional names to reflected constraints before dropping them.
"""
from collections.abc import Sequence

from alembic import op

from hopper.models.base import _NAMING_CONVENTION


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: str | Sequence[str] | None = 'b36aa411c248'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Re-point FKs from tasks.id to records.id."""
    with op.batch_alter_table(
        'task_feedback', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_task_feedback_task_id_tasks', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_task_feedback_task_id_records', 'records', ['task_id'], ['id']
        )

    with op.batch_alter_table(
        'routing_decisions', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_routing_decisions_task_id_tasks', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_routing_decisions_task_id_records', 'records', ['task_id'], ['id']
        )

    with op.batch_alter_table(
        'task_delegations', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_task_delegations_task_id_tasks', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_task_delegations_task_id_records', 'records', ['task_id'], ['id'],
            ondelete='CASCADE',
        )

    with op.batch_alter_table(
        'external_mappings', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_external_mappings_task_id_tasks', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_external_mappings_task_id_records', 'records', ['task_id'], ['id']
        )


def downgrade() -> None:
    """Re-point FKs back to the legacy tasks.id."""
    with op.batch_alter_table(
        'external_mappings', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_external_mappings_task_id_records', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_external_mappings_task_id_tasks', 'tasks', ['task_id'], ['id']
        )

    with op.batch_alter_table(
        'task_delegations', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_task_delegations_task_id_records', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_task_delegations_task_id_tasks', 'tasks', ['task_id'], ['id'],
            ondelete='CASCADE',
        )

    with op.batch_alter_table(
        'routing_decisions', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_routing_decisions_task_id_records', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_routing_decisions_task_id_tasks', 'tasks', ['task_id'], ['id']
        )

    with op.batch_alter_table(
        'task_feedback', schema=None, naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint('fk_task_feedback_task_id_records', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_task_feedback_task_id_tasks', 'tasks', ['task_id'], ['id']
        )
