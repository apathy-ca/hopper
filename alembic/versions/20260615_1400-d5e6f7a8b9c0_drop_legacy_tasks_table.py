"""drop_legacy_tasks_table

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-06-15 14:00:00.000000

Phase 5: Drop the legacy `tasks` table. The table has 0 rows in production
(all writes now go through the records/revisions backend). The four tables
that previously FK'd to tasks.id were re-pointed to records.id in Phase 4
(migration c3d4e5f6a7b8). The HopperInstance.tasks relationship FK to
hopper_instances.id remains in the tasks table definition; dropping the
table removes that FK automatically via cascade DDL.

Downgrade re-creates the table with its original schema and indexes. Note
that any Task rows would need to be restored from backup — schema only is
recovered by downgrade.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: str | Sequence[str] | None = 'c3d4e5f6a7b8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the legacy tasks table."""
    op.drop_table('tasks')


def downgrade() -> None:
    """Re-create the tasks table (schema only — data must be restored from backup)."""
    op.create_table(
        'tasks',
        sa.Column('id', sa.String(length=50), nullable=False),
        sa.Column('instance_id', sa.String(length=100), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('priority', sa.String(length=20), nullable=False),
        sa.Column('requester', sa.String(length=100), nullable=True),
        sa.Column('owner', sa.String(length=100), nullable=True),
        sa.Column('external_id', sa.String(length=100), nullable=True),
        sa.Column('external_url', sa.String(length=500), nullable=True),
        sa.Column('external_platform', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('conversation_id', sa.String(length=100), nullable=True),
        sa.Column('context', sa.Text(), nullable=True),
        sa.Column(
            'tags',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=True,
        ),
        sa.Column(
            'required_capabilities',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=True,
        ),
        sa.Column(
            'depends_on',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=True,
        ),
        sa.Column(
            'blocks',
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), 'sqlite'),
            nullable=True,
        ),
        sa.Column('assigned_to', sa.String(length=200), nullable=True),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('expected_heartbeat', sa.DateTime(), nullable=True),
        sa.Column('parent_id', sa.String(length=50), nullable=True),
        sa.Column('deleted', sa.Boolean(), nullable=False),
        sa.Column('routing_confidence', sa.Float(), nullable=True),
        sa.Column('routing_reasoning', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['instance_id'], ['hopper_instances.id']),
        sa.PrimaryKeyConstraint('id', name='pk_tasks'),
    )
    op.create_index('idx_tasks_assigned_to', 'tasks', ['assigned_to'])
    op.create_index('idx_tasks_created_at', 'tasks', ['created_at'])
    op.create_index('idx_tasks_deleted', 'tasks', ['deleted'])
    op.create_index('idx_tasks_external', 'tasks', ['external_id', 'external_platform'])
    op.create_index('idx_tasks_instance_id', 'tasks', ['instance_id'])
    op.create_index('idx_tasks_owner', 'tasks', ['owner'])
    op.create_index('idx_tasks_parent_id', 'tasks', ['parent_id'])
    op.create_index('idx_tasks_project', 'tasks', ['project'])
    op.create_index('idx_tasks_requester', 'tasks', ['requester'])
    op.create_index('idx_tasks_status', 'tasks', ['status'])
    op.create_index('idx_tasks_updated_at', 'tasks', ['updated_at'])
