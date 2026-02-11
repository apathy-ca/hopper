"""
Delegation management API endpoints.

Provides endpoints for task delegation, acceptance, rejection, and completion.
"""

from uuid import uuid4

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hopper.api.dependencies import PaginationParams, get_db
from hopper.api.exceptions import (
    InvalidStateTransitionException,
    NotFoundException,
    ValidationException,
)
from hopper.api.schemas.task_delegation import (
    DelegationAccept,
    DelegationChainResponse,
    DelegationComplete,
    DelegationCreate,
    DelegationList,
    DelegationReject,
    DelegationResponse,
    DelegationStatus as SchemaDelegationStatus,
)
from hopper.models import (
    DelegationStatus,
    DelegationType,
    HopperInstance,
    InstanceStatus,
    Task,
    TaskDelegation,
)

router = APIRouter()


def _delegation_to_response(delegation: TaskDelegation) -> DelegationResponse:
    """Convert a TaskDelegation model to DelegationResponse schema."""
    return DelegationResponse(
        id=delegation.id,
        task_id=delegation.task_id,
        source_instance_id=delegation.source_instance_id,
        target_instance_id=delegation.target_instance_id,
        delegation_type=delegation.delegation_type,
        status=delegation.status,
        delegated_at=delegation.delegated_at,
        accepted_at=delegation.accepted_at,
        completed_at=delegation.completed_at,
        result=delegation.result,
        rejection_reason=delegation.rejection_reason,
        notes=delegation.notes,
        delegated_by=delegation.delegated_by,
        created_at=delegation.created_at,
        updated_at=delegation.updated_at,
    )


@router.post("/tasks/{task_id}/delegate", response_model=DelegationResponse, status_code=status.HTTP_201_CREATED)
async def delegate_task(
    task_id: str,
    delegation_data: DelegationCreate,
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """
    Delegate a task to another instance.

    Args:
        task_id: Task ID to delegate
        delegation_data: Delegation details
        db: Database session

    Returns:
        Created delegation

    Raises:
        NotFoundException: If task or target instance not found
        ValidationException: If delegation is invalid
    """
    # Get task
    task_query = select(Task).where(Task.id == task_id)
    task_result = await db.execute(task_query)
    task = task_result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    # Get target instance
    target_query = select(HopperInstance).where(HopperInstance.id == delegation_data.target_instance_id)
    target_result = await db.execute(target_query)
    target_instance = target_result.scalar_one_or_none()

    if not target_instance:
        raise NotFoundException("HopperInstance", delegation_data.target_instance_id)

    # Validate target instance is running
    if target_instance.status not in (InstanceStatus.RUNNING, InstanceStatus.CREATED):
        raise ValidationException(
            f"Cannot delegate to instance with status {target_instance.status}",
            "target_instance_id",
        )

    # Create delegation
    delegation = TaskDelegation(
        id=f"del-{uuid4().hex[:12]}",
        task_id=task_id,
        source_instance_id=task.instance_id,
        target_instance_id=delegation_data.target_instance_id,
        delegation_type=delegation_data.delegation_type or DelegationType.ROUTE,
        status=DelegationStatus.PENDING,
        delegated_by=delegation_data.delegated_by,
        notes=delegation_data.notes,
    )

    # Update task's instance
    task.instance_id = delegation_data.target_instance_id

    db.add(delegation)
    await db.flush()
    await db.refresh(delegation)

    return _delegation_to_response(delegation)


@router.post("/delegations/{delegation_id}/accept", response_model=DelegationResponse)
async def accept_delegation(
    delegation_id: str,
    accept_data: DelegationAccept | None = None,
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """
    Accept a pending delegation.

    Args:
        delegation_id: Delegation ID
        accept_data: Optional acceptance notes
        db: Database session

    Returns:
        Updated delegation

    Raises:
        NotFoundException: If delegation not found
        InvalidStateTransitionException: If delegation cannot be accepted
    """
    query = select(TaskDelegation).where(TaskDelegation.id == delegation_id)
    result = await db.execute(query)
    delegation = result.scalar_one_or_none()

    if not delegation:
        raise NotFoundException("TaskDelegation", delegation_id)

    if delegation.status != DelegationStatus.PENDING:
        raise InvalidStateTransitionException(delegation.status, "accepted")

    delegation.accept()
    if accept_data and accept_data.notes:
        delegation.notes = (delegation.notes or "") + f"\nAccepted: {accept_data.notes}"

    await db.flush()
    await db.refresh(delegation)

    return _delegation_to_response(delegation)


@router.post("/delegations/{delegation_id}/reject", response_model=DelegationResponse)
async def reject_delegation(
    delegation_id: str,
    reject_data: DelegationReject,
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """
    Reject a pending delegation.

    Args:
        delegation_id: Delegation ID
        reject_data: Rejection reason
        db: Database session

    Returns:
        Updated delegation

    Raises:
        NotFoundException: If delegation not found
        InvalidStateTransitionException: If delegation cannot be rejected
    """
    query = select(TaskDelegation).where(TaskDelegation.id == delegation_id)
    result = await db.execute(query)
    delegation = result.scalar_one_or_none()

    if not delegation:
        raise NotFoundException("TaskDelegation", delegation_id)

    if delegation.status != DelegationStatus.PENDING:
        raise InvalidStateTransitionException(delegation.status, "rejected")

    delegation.reject(reject_data.reason)

    # Return task to source instance
    task_query = select(Task).where(Task.id == delegation.task_id)
    task_result = await db.execute(task_query)
    task = task_result.scalar_one_or_none()

    if task and delegation.source_instance_id:
        task.instance_id = delegation.source_instance_id

    await db.flush()
    await db.refresh(delegation)

    return _delegation_to_response(delegation)


@router.post("/delegations/{delegation_id}/complete", response_model=DelegationResponse)
async def complete_delegation(
    delegation_id: str,
    complete_data: DelegationComplete | None = None,
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """
    Mark a delegation as completed.

    Args:
        delegation_id: Delegation ID
        complete_data: Optional completion result
        db: Database session

    Returns:
        Updated delegation

    Raises:
        NotFoundException: If delegation not found
        InvalidStateTransitionException: If delegation cannot be completed
    """
    query = select(TaskDelegation).where(TaskDelegation.id == delegation_id)
    result = await db.execute(query)
    delegation = result.scalar_one_or_none()

    if not delegation:
        raise NotFoundException("TaskDelegation", delegation_id)

    if delegation.status not in (DelegationStatus.PENDING, DelegationStatus.ACCEPTED):
        raise InvalidStateTransitionException(delegation.status, "completed")

    result_data = complete_data.result if complete_data else None
    delegation.complete(result_data)

    if complete_data and complete_data.notes:
        delegation.notes = (delegation.notes or "") + f"\nCompleted: {complete_data.notes}"

    await db.flush()
    await db.refresh(delegation)

    return _delegation_to_response(delegation)


@router.get("/delegations/{delegation_id}", response_model=DelegationResponse)
async def get_delegation(
    delegation_id: str,
    db: AsyncSession = Depends(get_db),
) -> DelegationResponse:
    """
    Get a delegation by ID.

    Args:
        delegation_id: Delegation ID
        db: Database session

    Returns:
        Delegation details

    Raises:
        NotFoundException: If delegation not found
    """
    query = select(TaskDelegation).where(TaskDelegation.id == delegation_id)
    result = await db.execute(query)
    delegation = result.scalar_one_or_none()

    if not delegation:
        raise NotFoundException("TaskDelegation", delegation_id)

    return _delegation_to_response(delegation)


@router.get("/tasks/{task_id}/delegations", response_model=DelegationChainResponse)
async def get_task_delegations(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> DelegationChainResponse:
    """
    Get the delegation chain for a task.

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        Delegation chain showing task's journey through instances

    Raises:
        NotFoundException: If task not found
    """
    # Verify task exists
    task_query = select(Task).where(Task.id == task_id)
    task_result = await db.execute(task_query)
    task = task_result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    # Get delegations
    query = (
        select(TaskDelegation)
        .where(TaskDelegation.task_id == task_id)
        .order_by(TaskDelegation.delegated_at.asc())
    )
    result = await db.execute(query)
    delegations = result.scalars().all()

    # Determine current and origin instances
    origin_instance_id = None
    current_instance_id = task.instance_id

    if delegations:
        origin_instance_id = delegations[0].source_instance_id

    return DelegationChainResponse(
        task_id=task_id,
        delegations=[_delegation_to_response(d) for d in delegations],
        current_instance_id=current_instance_id,
        origin_instance_id=origin_instance_id,
        total_delegations=len(delegations),
    )


@router.get("/instances/{instance_id}/delegations", response_model=DelegationList)
async def get_instance_delegations(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    direction: str = Query("incoming", pattern="^(incoming|outgoing|all)$"),
    status_filter: list[SchemaDelegationStatus] | None = Query(None, alias="status"),
) -> DelegationList:
    """
    Get delegations for an instance.

    Args:
        instance_id: Instance ID
        db: Database session
        pagination: Pagination parameters
        direction: incoming, outgoing, or all
        status_filter: Filter by status

    Returns:
        List of delegations

    Raises:
        NotFoundException: If instance not found
    """
    # Verify instance exists
    instance_query = select(HopperInstance).where(HopperInstance.id == instance_id)
    instance_result = await db.execute(instance_query)
    instance = instance_result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Build query
    query = select(TaskDelegation)

    if direction == "incoming":
        query = query.where(TaskDelegation.target_instance_id == instance_id)
    elif direction == "outgoing":
        query = query.where(TaskDelegation.source_instance_id == instance_id)
    else:  # all
        query = query.where(
            (TaskDelegation.target_instance_id == instance_id) |
            (TaskDelegation.source_instance_id == instance_id)
        )

    if status_filter:
        query = query.where(TaskDelegation.status.in_([s.value for s in status_filter]))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.order_by(TaskDelegation.delegated_at.desc())
    query = query.offset(pagination.skip).limit(pagination.limit)

    result = await db.execute(query)
    delegations = result.scalars().all()

    return DelegationList(
        items=[_delegation_to_response(d) for d in delegations],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
        has_more=(pagination.skip + len(delegations)) < total,
    )
