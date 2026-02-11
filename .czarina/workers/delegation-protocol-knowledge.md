# Knowledge Base: delegation-protocol

Custom knowledge for the Delegation Protocol worker, extracted from agent-knowledge library.

## Service Layer Patterns

### Async Service Class Structure

```python
from sqlalchemy.ext.asyncio import AsyncSession
from hopper.database.repositories import TaskDelegationRepository, InstanceRepository
from hopper.models import Task, TaskDelegation, HopperInstance
import structlog

logger = structlog.get_logger()

class Delegator:
    """Main delegation service for task routing."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db
        self.delegation_repo = TaskDelegationRepository()
        self.instance_repo = InstanceRepository()

    async def delegate_task(
        self,
        task: Task,
        target_instance: HopperInstance,
        delegation_type: DelegationType = DelegationType.ROUTE,
    ) -> TaskDelegation:
        """Delegate task to target instance.

        Args:
            task: Task to delegate
            target_instance: Instance to delegate to
            delegation_type: Type of delegation

        Returns:
            Created delegation record

        Raises:
            ValueError: If delegation is invalid
        """
        # Validate delegation
        source_instance = await self.instance_repo.get_by_id(
            self.db, task.instance_id
        )
        if not source_instance:
            raise ValueError(f"Source instance not found: {task.instance_id}")

        if not await self._can_delegate(source_instance, target_instance):
            raise ValueError(
                f"Cannot delegate from {source_instance.scope} to {target_instance.scope}"
            )

        # Create delegation record
        delegation = await self.delegation_repo.create(
            self.db,
            task_id=task.id,
            source_instance_id=source_instance.id,
            target_instance_id=target_instance.id,
            delegation_type=delegation_type,
        )

        logger.info(
            "task_delegated",
            task_id=task.id,
            source=source_instance.id,
            target=target_instance.id,
            delegation_id=delegation.id,
        )

        return delegation

    async def _can_delegate(
        self,
        source: HopperInstance,
        target: HopperInstance,
    ) -> bool:
        """Check if delegation is valid.

        Rules:
        - Global can delegate to Project
        - Project can delegate to Orchestration
        - Cannot delegate to same or higher level
        """
        valid_delegations = {
            HopperScope.GLOBAL: [HopperScope.PROJECT],
            HopperScope.PROJECT: [HopperScope.ORCHESTRATION],
            HopperScope.ORCHESTRATION: [],  # Cannot delegate further
        }

        return target.scope in valid_delegations.get(source.scope, [])
```

## Completion Bubbling Pattern

### CompletionBubbler Implementation

```python
class CompletionBubbler:
    """Handles completion status bubbling up the hierarchy."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.delegation_repo = TaskDelegationRepository()
        self.task_repo = TaskRepository()

    async def bubble_completion(self, task: Task) -> None:
        """Bubble task completion up the delegation chain.

        When a task completes at a lower level (e.g., Orchestration),
        this method updates all parent delegations in the chain.
        """
        # Get delegation chain for this task
        chain = await self.delegation_repo.get_delegation_chain(
            self.db, task.id
        )

        if not chain:
            logger.debug("no_delegation_chain", task_id=task.id)
            return

        # Process chain in reverse (child to parent)
        for delegation in reversed(chain):
            if delegation.status == DelegationStatus.ACCEPTED:
                await self.delegation_repo.complete(
                    self.db,
                    delegation.id,
                    result={
                        "task_status": task.status,
                        "completed_at": task.completed_at.isoformat(),
                    }
                )

                logger.info(
                    "delegation_completed",
                    delegation_id=delegation.id,
                    task_id=task.id,
                )

        await self.db.commit()

    async def aggregate_child_completions(
        self,
        parent_task: Task,
    ) -> bool:
        """Check if all child tasks are complete.

        For decomposed tasks, we need to wait for all children.

        Returns:
            True if all children are complete
        """
        # Find all delegations where this task was source
        children = await self.delegation_repo.get_delegations_from_task(
            self.db, parent_task.id
        )

        if not children:
            return True  # No children means complete

        # Check if all children are completed
        return all(
            d.status == DelegationStatus.COMPLETED
            for d in children
        )
```

## Router Implementation

### Instance Router Pattern

```python
class InstanceRouter:
    """Routes tasks to appropriate instances."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.instance_repo = InstanceRepository()

    async def find_target_instance(
        self,
        task: Task,
        source_instance: HopperInstance,
    ) -> HopperInstance | None:
        """Find appropriate target instance for delegation.

        Uses routing intelligence to determine best target.
        """
        # Determine target scope
        if source_instance.scope == HopperScope.GLOBAL:
            target_scope = HopperScope.PROJECT
        elif source_instance.scope == HopperScope.PROJECT:
            target_scope = HopperScope.ORCHESTRATION
        else:
            return None  # Cannot delegate further

        # Get available instances at target scope
        candidates = await self.get_available_instances(target_scope)
        if not candidates:
            return None

        # Apply routing strategy
        return await self._select_best_instance(task, candidates)

    async def get_available_instances(
        self,
        scope: HopperScope,
    ) -> list[HopperInstance]:
        """Get instances that can accept tasks."""
        instances = await self.instance_repo.get_by_scope(self.db, scope)

        # Filter to running instances
        return [
            i for i in instances
            if i.status == InstanceStatus.RUNNING
        ]

    async def _select_best_instance(
        self,
        task: Task,
        candidates: list[HopperInstance],
    ) -> HopperInstance:
        """Select best instance for task.

        Strategy:
        1. Match by task tags
        2. Match by task content keywords
        3. Load balance (least busy)
        """
        # Tag matching
        if task.tags:
            for instance in candidates:
                instance_tags = instance.config.get("capabilities", [])
                if any(tag in instance_tags for tag in task.tags):
                    return instance

        # Keyword matching (from routing engine)
        # ... routing intelligence integration ...

        # Fallback: least busy (by task count)
        return min(
            candidates,
            key=lambda i: self._get_task_count(i)
        )
```

## Error Recovery Patterns

### Retry with Exponential Backoff

```python
import asyncio
from typing import TypeVar, Callable

T = TypeVar("T")

async def retry_with_backoff(
    func: Callable[[], T],
    max_attempts: int = 3,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,),
) -> T:
    """Retry function with exponential backoff.

    Args:
        func: Async function to retry
        max_attempts: Maximum attempts
        backoff_factor: Backoff multiplier
        exceptions: Exceptions to catch and retry

    Returns:
        Result from successful call

    Raises:
        Last exception if all retries fail
    """
    last_exception = None

    for attempt in range(max_attempts):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_attempts - 1:
                wait_time = backoff_factor ** attempt
                logger.warning(
                    "retry_attempt",
                    attempt=attempt + 1,
                    max_attempts=max_attempts,
                    wait_time=wait_time,
                    error=str(e),
                )
                await asyncio.sleep(wait_time)

    raise last_exception
```

### Transaction Management

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def delegation_transaction(db: AsyncSession):
    """Context manager for delegation transactions.

    Ensures atomic operations for multi-step delegations.
    """
    try:
        yield
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(
            "delegation_transaction_failed",
            error=str(e),
            exc_info=True,
        )
        raise
```

## API Endpoints Pattern

```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api/v1", tags=["delegations"])

@router.post("/tasks/{task_id}/delegate")
async def delegate_task(
    task_id: str,
    request: DelegateTaskRequest,
    db: AsyncSession = Depends(get_db),
):
    """Delegate task to another instance."""
    delegator = Delegator(db)

    task = await task_repo.get_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    target = await instance_repo.get_by_id(db, request.target_instance_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target instance not found")

    try:
        delegation = await delegator.delegate_task(task, target)
        return DelegationResponse.from_orm(delegation)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/delegations/{delegation_id}/complete")
async def complete_delegation(
    delegation_id: str,
    request: CompleteDelegationRequest,
    db: AsyncSession = Depends(get_db),
):
    """Mark delegation as complete and trigger bubbling."""
    repo = TaskDelegationRepository()
    bubbler = CompletionBubbler(db)

    delegation = await repo.complete(db, delegation_id, request.result)

    # Bubble completion up
    task = await task_repo.get_by_id(db, delegation.task_id)
    await bubbler.bubble_completion(task)

    return {"status": "completed", "delegation_id": delegation_id}
```

## Testing Integration Flows

```python
@pytest.mark.asyncio
async def test_full_delegation_flow(db, instance_hierarchy, task):
    """Test complete delegation flow from Global to Orchestration."""
    global_inst, project_inst, orch_inst = instance_hierarchy

    delegator = Delegator(db)
    bubbler = CompletionBubbler(db)

    # Delegate Global -> Project
    d1 = await delegator.delegate_task(task, project_inst)
    await delegator.accept_delegation(d1.id)

    # Delegate Project -> Orchestration
    task.instance_id = project_inst.id
    d2 = await delegator.delegate_task(task, orch_inst)
    await delegator.accept_delegation(d2.id)

    # Complete at Orchestration
    task.status = TaskStatus.COMPLETED
    await bubbler.bubble_completion(task)

    # Verify chain completed
    chain = await TaskDelegationRepository().get_delegation_chain(db, task.id)
    assert all(d.status == DelegationStatus.COMPLETED for d in chain)
```

## Best Practices

### DO
- Use transactions for multi-step operations
- Log all delegation events for debugging
- Make bubbling idempotent (safe to call multiple times)
- Validate delegation rules before creating records
- Handle edge cases (deleted instances, error recovery)

### DON'T
- Create circular delegations
- Skip validation on status transitions
- Block on long-running operations
- Expose internal errors to API callers

## References

- Async patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/python-standards/ASYNC_PATTERNS.md`
- Error handling: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/python-standards/ERROR_HANDLING.md`
- Error recovery patterns: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/patterns/error-recovery/`
