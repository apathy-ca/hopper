# Knowledge Base: task-delegation

Custom knowledge for the Task Delegation worker, extracted from agent-knowledge library.

## SQLAlchemy Model Patterns

### Model with Relationships

```python
from sqlalchemy import Column, String, ForeignKey, DateTime, JSON, Enum
from sqlalchemy.orm import relationship
from hopper.models.base import Base, TimestampMixin
import enum
from datetime import datetime
from uuid import uuid4

class DelegationType(str, enum.Enum):
    ROUTE = "route"          # Task routed down hierarchy
    DECOMPOSE = "decompose"  # Task split into subtasks
    ESCALATE = "escalate"    # Task returned up hierarchy

class DelegationStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"

class TaskDelegation(Base, TimestampMixin):
    """Tracks task delegation between instances."""

    __tablename__ = "task_delegations"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False, index=True)
    source_instance_id = Column(
        String, ForeignKey("hopper_instances.id"), nullable=False, index=True
    )
    target_instance_id = Column(
        String, ForeignKey("hopper_instances.id"), nullable=False, index=True
    )
    delegation_type = Column(
        Enum(DelegationType), nullable=False, default=DelegationType.ROUTE
    )
    status = Column(
        Enum(DelegationStatus), nullable=False, default=DelegationStatus.PENDING,
        index=True
    )
    delegated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)  # Completion result
    notes = Column(String, nullable=True)

    # Relationships
    task = relationship("Task", back_populates="delegations")
    source_instance = relationship(
        "HopperInstance", foreign_keys=[source_instance_id]
    )
    target_instance = relationship(
        "HopperInstance", foreign_keys=[target_instance_id]
    )
```

### Update Task Model

```python
# In task.py, add relationship
class Task(Base, TimestampMixin):
    # ... existing fields ...

    # Add delegation relationship
    delegations = relationship(
        "TaskDelegation",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskDelegation.delegated_at"
    )
```

## Repository Pattern

### Async Repository Methods

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

class TaskDelegationRepository:
    """Repository for TaskDelegation operations."""

    async def create(
        self,
        db: AsyncSession,
        task_id: str,
        source_instance_id: str,
        target_instance_id: str,
        delegation_type: DelegationType = DelegationType.ROUTE,
    ) -> TaskDelegation:
        """Create a new delegation record."""
        delegation = TaskDelegation(
            task_id=task_id,
            source_instance_id=source_instance_id,
            target_instance_id=target_instance_id,
            delegation_type=delegation_type,
            status=DelegationStatus.PENDING,
            delegated_at=datetime.utcnow(),
        )
        db.add(delegation)
        await db.flush()  # Get ID without committing
        return delegation

    async def get_by_id(
        self, db: AsyncSession, delegation_id: str
    ) -> TaskDelegation | None:
        """Get delegation by ID."""
        result = await db.execute(
            select(TaskDelegation).where(TaskDelegation.id == delegation_id)
        )
        return result.scalar_one_or_none()

    async def get_delegations_for_task(
        self, db: AsyncSession, task_id: str
    ) -> list[TaskDelegation]:
        """Get all delegations for a task, ordered by time."""
        result = await db.execute(
            select(TaskDelegation)
            .where(TaskDelegation.task_id == task_id)
            .order_by(TaskDelegation.delegated_at)
        )
        return list(result.scalars().all())

    async def get_delegation_chain(
        self, db: AsyncSession, task_id: str
    ) -> list[TaskDelegation]:
        """Get full delegation chain from origin to current location."""
        # Same as get_delegations_for_task but includes relationships
        result = await db.execute(
            select(TaskDelegation)
            .where(TaskDelegation.task_id == task_id)
            .options(
                selectinload(TaskDelegation.source_instance),
                selectinload(TaskDelegation.target_instance),
            )
            .order_by(TaskDelegation.delegated_at)
        )
        return list(result.scalars().all())

    async def get_pending_delegations(
        self, db: AsyncSession, instance_id: str
    ) -> list[TaskDelegation]:
        """Get pending delegations for an instance."""
        result = await db.execute(
            select(TaskDelegation).where(
                and_(
                    TaskDelegation.target_instance_id == instance_id,
                    TaskDelegation.status == DelegationStatus.PENDING,
                )
            )
        )
        return list(result.scalars().all())

    async def accept(
        self, db: AsyncSession, delegation_id: str
    ) -> TaskDelegation:
        """Accept a delegation."""
        delegation = await self.get_by_id(db, delegation_id)
        if not delegation:
            raise ValueError(f"Delegation {delegation_id} not found")
        if delegation.status != DelegationStatus.PENDING:
            raise ValueError(f"Cannot accept delegation in {delegation.status} status")

        delegation.status = DelegationStatus.ACCEPTED
        await db.flush()
        return delegation

    async def reject(
        self, db: AsyncSession, delegation_id: str, reason: str
    ) -> TaskDelegation:
        """Reject a delegation with reason."""
        delegation = await self.get_by_id(db, delegation_id)
        if not delegation:
            raise ValueError(f"Delegation {delegation_id} not found")

        delegation.status = DelegationStatus.REJECTED
        delegation.notes = reason
        await db.flush()
        return delegation

    async def complete(
        self, db: AsyncSession, delegation_id: str, result: dict | None = None
    ) -> TaskDelegation:
        """Mark delegation as completed."""
        delegation = await self.get_by_id(db, delegation_id)
        if not delegation:
            raise ValueError(f"Delegation {delegation_id} not found")

        delegation.status = DelegationStatus.COMPLETED
        delegation.completed_at = datetime.utcnow()
        delegation.result = result
        await db.flush()
        return delegation
```

## Alembic Migration Patterns

### Migration File Structure

```python
"""Add task_delegations table

Revision ID: 2024_02_02_001
Revises: <previous_revision>
Create Date: 2024-02-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '2024_02_02_001'
down_revision = '<previous_revision>'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create enum types
    delegation_type = postgresql.ENUM(
        'route', 'decompose', 'escalate',
        name='delegationtype',
        create_type=True
    )
    delegation_status = postgresql.ENUM(
        'pending', 'accepted', 'rejected', 'completed',
        name='delegationstatus',
        create_type=True
    )

    # Create table
    op.create_table(
        'task_delegations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('task_id', sa.String(), nullable=False),
        sa.Column('source_instance_id', sa.String(), nullable=False),
        sa.Column('target_instance_id', sa.String(), nullable=False),
        sa.Column('delegation_type', delegation_type, nullable=False),
        sa.Column('status', delegation_status, nullable=False),
        sa.Column('delegated_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('notes', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_instance_id'], ['hopper_instances.id']),
        sa.ForeignKeyConstraint(['target_instance_id'], ['hopper_instances.id']),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for common queries
    op.create_index('ix_task_delegations_task_id', 'task_delegations', ['task_id'])
    op.create_index('ix_task_delegations_source_instance_id', 'task_delegations', ['source_instance_id'])
    op.create_index('ix_task_delegations_target_instance_id', 'task_delegations', ['target_instance_id'])
    op.create_index('ix_task_delegations_status', 'task_delegations', ['status'])

def downgrade() -> None:
    op.drop_index('ix_task_delegations_status')
    op.drop_index('ix_task_delegations_target_instance_id')
    op.drop_index('ix_task_delegations_source_instance_id')
    op.drop_index('ix_task_delegations_task_id')
    op.drop_table('task_delegations')

    # Drop enum types
    op.execute('DROP TYPE IF EXISTS delegationstatus')
    op.execute('DROP TYPE IF EXISTS delegationtype')
```

## Pydantic Schema Patterns

```python
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class DelegationType(str, Enum):
    ROUTE = "route"
    DECOMPOSE = "decompose"
    ESCALATE = "escalate"

class DelegationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"

class TaskDelegationCreate(BaseModel):
    """Request schema for creating delegation."""
    task_id: str
    target_instance_id: str
    delegation_type: DelegationType = DelegationType.ROUTE
    notes: str | None = None

class TaskDelegationResponse(BaseModel):
    """Response schema for delegation."""
    id: str
    task_id: str
    source_instance_id: str
    target_instance_id: str
    delegation_type: DelegationType
    status: DelegationStatus
    delegated_at: datetime
    completed_at: datetime | None
    result: dict | None
    notes: str | None

    class Config:
        from_attributes = True

class DelegationChainResponse(BaseModel):
    """Response schema for delegation chain."""
    task_id: str
    chain: list[TaskDelegationResponse]
    origin_instance_id: str
    current_instance_id: str
```

## Testing Patterns

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

@pytest.fixture
async def delegation_with_chain(db: AsyncSession, task, global_instance, project_instance, orchestration_instance):
    """Create a delegation chain: Global -> Project -> Orchestration."""
    repo = TaskDelegationRepository()

    # First delegation: Global -> Project
    d1 = await repo.create(
        db,
        task_id=task.id,
        source_instance_id=global_instance.id,
        target_instance_id=project_instance.id,
    )
    await repo.accept(db, d1.id)

    # Second delegation: Project -> Orchestration
    d2 = await repo.create(
        db,
        task_id=task.id,
        source_instance_id=project_instance.id,
        target_instance_id=orchestration_instance.id,
    )
    await repo.accept(db, d2.id)

    await db.commit()
    return [d1, d2]

@pytest.mark.asyncio
async def test_get_delegation_chain(db: AsyncSession, delegation_with_chain):
    """Test retrieving full delegation chain."""
    repo = TaskDelegationRepository()
    task_id = delegation_with_chain[0].task_id

    chain = await repo.get_delegation_chain(db, task_id)

    assert len(chain) == 2
    assert chain[0].source_instance_id == delegation_with_chain[0].source_instance_id
    assert chain[1].target_instance_id == delegation_with_chain[1].target_instance_id
```

## Best Practices

### DO
- Use UUID strings for all IDs (matches existing pattern)
- Add indexes for frequently queried columns
- Include CASCADE delete on task_id FK
- Use JSONB for flexible result storage
- Test migration both upgrade and downgrade

### DON'T
- Store large binary data in result field
- Create circular delegation references
- Skip validation on status transitions
- Forget to update Task model with relationship

## References

- Async patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/python-standards/ASYNC_PATTERNS.md`
- Testing: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/UNIT_TESTING.md`
