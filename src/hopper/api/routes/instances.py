"""
Instance management API endpoints.

Provides CRUD operations, hierarchy management, and lifecycle control for Hopper instances.
"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hopper.api.dependencies import PaginationParams, get_db
from hopper.api.exceptions import (
    InvalidStateTransitionException,
    NotFoundException,
    ValidationException,
)
from hopper.api.schemas.hopper_instance import (
    HopperScope,
    InstanceCreate,
    InstanceHierarchy,
    InstanceHierarchyNode,
    InstanceList,
    InstanceResponse,
    InstanceStatus,
    InstanceUpdate,
)
from hopper.models import HopperInstance, Task
from hopper.models import HopperScope as HopperScopeEnum
from hopper.models import InstanceStatus as InstanceStatusEnum
from hopper.models import InstanceType as InstanceTypeEnum

router = APIRouter()


# Valid status transitions
VALID_TRANSITIONS = {
    InstanceStatusEnum.CREATED: [InstanceStatusEnum.STARTING, InstanceStatusEnum.TERMINATED],
    InstanceStatusEnum.STARTING: [InstanceStatusEnum.RUNNING, InstanceStatusEnum.ERROR],
    InstanceStatusEnum.RUNNING: [InstanceStatusEnum.STOPPING, InstanceStatusEnum.PAUSED, InstanceStatusEnum.ERROR],
    InstanceStatusEnum.STOPPING: [InstanceStatusEnum.STOPPED, InstanceStatusEnum.ERROR],
    InstanceStatusEnum.STOPPED: [InstanceStatusEnum.STARTING, InstanceStatusEnum.TERMINATED],
    InstanceStatusEnum.PAUSED: [InstanceStatusEnum.RUNNING, InstanceStatusEnum.STOPPING],
    InstanceStatusEnum.ERROR: [InstanceStatusEnum.STARTING, InstanceStatusEnum.TERMINATED],
    InstanceStatusEnum.TERMINATED: [],  # Terminal state
}


def _instance_to_response(instance: HopperInstance) -> InstanceResponse:
    """Convert a HopperInstance model to InstanceResponse schema."""
    return InstanceResponse(
        id=instance.id,
        name=instance.name,
        scope=instance.scope.value if isinstance(instance.scope, HopperScopeEnum) else instance.scope,
        status=instance.status.value if isinstance(instance.status, InstanceStatusEnum) else instance.status,
        instance_type=instance.instance_type.value if isinstance(instance.instance_type, InstanceTypeEnum) else instance.instance_type,
        parent_id=instance.parent_id,
        config=instance.config,
        runtime_metadata=instance.runtime_metadata,
        description=instance.description,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        created_by=instance.created_by,
        started_at=instance.started_at,
        stopped_at=instance.stopped_at,
    )


@router.post("/instances", response_model=InstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_instance(
    instance_data: InstanceCreate,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Create a new Hopper instance.

    Args:
        instance_data: Instance creation data
        db: Database session

    Returns:
        Created instance

    Raises:
        ValidationException: If instance data is invalid
        NotFoundException: If parent instance not found
    """
    # Validate parent exists if specified
    if instance_data.parent_id:
        query = select(HopperInstance).where(HopperInstance.id == instance_data.parent_id)
        result = await db.execute(query)
        parent = result.scalar_one_or_none()
        if not parent:
            raise NotFoundException("HopperInstance", instance_data.parent_id)

    # Generate ID if not provided
    instance_id = instance_data.id or f"{instance_data.scope.lower()}-{uuid4().hex[:8]}"

    # Create instance model
    instance = HopperInstance(
        id=instance_id,
        name=instance_data.name,
        scope=HopperScopeEnum(instance_data.scope),
        instance_type=InstanceTypeEnum(instance_data.instance_type),
        parent_id=instance_data.parent_id,
        config=instance_data.config,
        runtime_metadata=instance_data.runtime_metadata,
        description=instance_data.description,
        created_by=instance_data.created_by,
        status=InstanceStatusEnum.CREATED,
    )

    db.add(instance)
    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)


@router.get("/instances", response_model=InstanceList)
async def list_instances(
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    # Filters
    scope: list[HopperScope] | None = Query(None),
    status_filter: list[InstanceStatus] | None = Query(None, alias="status"),
    parent_id: str | None = None,
    root_only: bool = Query(False, description="Only return root instances (no parent)"),
    # Sorting
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> InstanceList:
    """
    List instances with filtering, pagination, and sorting.

    Args:
        db: Database session
        pagination: Pagination parameters
        scope: Filter by scope
        status_filter: Filter by status
        parent_id: Filter by parent instance
        root_only: Only return root instances
        sort_by: Sort field
        sort_order: Sort order

    Returns:
        Paginated instance list
    """
    query = select(HopperInstance)

    # Apply filters
    if scope:
        query = query.where(HopperInstance.scope.in_([s.value for s in scope]))
    if status_filter:
        query = query.where(HopperInstance.status.in_([s.value for s in status_filter]))
    if parent_id:
        query = query.where(HopperInstance.parent_id == parent_id)
    if root_only:
        query = query.where(HopperInstance.parent_id.is_(None))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    sort_column = getattr(HopperInstance, sort_by, HopperInstance.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)

    # Execute query
    result = await db.execute(query)
    instances = result.scalars().all()

    return InstanceList(
        items=[_instance_to_response(inst) for inst in instances],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
        has_more=(pagination.skip + len(instances)) < total,
    )


@router.get("/instances/{instance_id}", response_model=InstanceResponse)
async def get_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Get an instance by ID.

    Args:
        instance_id: Instance ID
        db: Database session

    Returns:
        Instance details

    Raises:
        NotFoundException: If instance not found
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    return _instance_to_response(instance)


@router.put("/instances/{instance_id}", response_model=InstanceResponse)
async def update_instance(
    instance_id: str,
    instance_data: InstanceUpdate,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Update an instance.

    Args:
        instance_id: Instance ID
        instance_data: Instance update data
        db: Database session

    Returns:
        Updated instance

    Raises:
        NotFoundException: If instance not found
        InvalidStateTransitionException: If status transition is invalid
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Validate status transition if status is being updated
    if instance_data.status:
        new_status = InstanceStatusEnum(instance_data.status)
        if new_status not in VALID_TRANSITIONS.get(instance.status, []):
            raise InvalidStateTransitionException(instance.status.value, instance_data.status)

    # Update fields
    update_data = instance_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == "status" and value:
            setattr(instance, field, InstanceStatusEnum(value))
        elif field == "instance_type" and value:
            setattr(instance, field, InstanceTypeEnum(value))
        else:
            setattr(instance, field, value)

    instance.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)


@router.delete("/instances/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete an instance (soft delete by setting status to TERMINATED).

    Args:
        instance_id: Instance ID
        db: Database session

    Raises:
        NotFoundException: If instance not found
        ValidationException: If instance has children
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Check for children
    children_query = select(func.count()).where(HopperInstance.parent_id == instance_id)
    children_count = await db.scalar(children_query) or 0
    if children_count > 0:
        raise ValidationException(
            f"Cannot delete instance with {children_count} child instances. Delete children first.",
            "instance_id",
        )

    # Soft delete
    instance.status = InstanceStatusEnum.TERMINATED
    instance.stopped_at = datetime.utcnow()
    instance.updated_at = datetime.utcnow()

    await db.flush()


@router.get("/instances/{instance_id}/children", response_model=InstanceList)
async def get_instance_children(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
) -> InstanceList:
    """
    Get child instances of an instance.

    Args:
        instance_id: Parent instance ID
        db: Database session
        pagination: Pagination parameters

    Returns:
        List of child instances

    Raises:
        NotFoundException: If parent instance not found
    """
    # Verify parent exists
    parent_query = select(HopperInstance).where(HopperInstance.id == instance_id)
    parent_result = await db.execute(parent_query)
    parent = parent_result.scalar_one_or_none()

    if not parent:
        raise NotFoundException("HopperInstance", instance_id)

    # Get children
    query = select(HopperInstance).where(HopperInstance.parent_id == instance_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)

    result = await db.execute(query)
    children = result.scalars().all()

    return InstanceList(
        items=[_instance_to_response(child) for child in children],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
        has_more=(pagination.skip + len(children)) < total,
    )


@router.get("/instances/{instance_id}/hierarchy", response_model=InstanceHierarchy)
async def get_instance_hierarchy(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceHierarchy:
    """
    Get the full hierarchy tree for an instance.

    Args:
        instance_id: Instance ID (will be the root of returned tree)
        db: Database session

    Returns:
        Hierarchy tree rooted at the specified instance

    Raises:
        NotFoundException: If instance not found
    """
    # Get the instance with eager loading of children
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    async def build_tree(inst: HopperInstance, depth: int) -> InstanceHierarchyNode:
        """Recursively build hierarchy tree."""
        # Get children
        children_query = select(HopperInstance).where(HopperInstance.parent_id == inst.id)
        children_result = await db.execute(children_query)
        children = children_result.scalars().all()

        child_nodes = []
        for child in children:
            child_node = await build_tree(child, depth + 1)
            child_nodes.append(child_node)

        return InstanceHierarchyNode(
            instance=_instance_to_response(inst),
            children=child_nodes,
            depth=depth,
        )

    # Count total instances in hierarchy
    async def count_descendants(inst_id: str) -> int:
        """Count all descendants."""
        children_query = select(HopperInstance).where(HopperInstance.parent_id == inst_id)
        children_result = await db.execute(children_query)
        children = children_result.scalars().all()

        count = len(children)
        for child in children:
            count += await count_descendants(child.id)
        return count

    root_node = await build_tree(instance, 0)
    total = 1 + await count_descendants(instance_id)

    return InstanceHierarchy(root=root_node, total_instances=total)


@router.get("/instances/{instance_id}/tasks")
async def get_instance_tasks(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
):
    """
    Get tasks assigned to an instance.

    Args:
        instance_id: Instance ID
        db: Database session
        pagination: Pagination parameters

    Returns:
        List of tasks for the instance

    Raises:
        NotFoundException: If instance not found
    """
    # Verify instance exists
    instance_query = select(HopperInstance).where(HopperInstance.id == instance_id)
    instance_result = await db.execute(instance_query)
    instance = instance_result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Get tasks
    query = select(Task).where(Task.instance_id == instance_id)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)

    result = await db.execute(query)
    tasks = result.scalars().all()

    return {
        "instance_id": instance_id,
        "instance_name": instance.name,
        "tasks": [{"id": t.id, "title": t.title, "status": t.status.value} for t in tasks],
        "total": total,
        "skip": pagination.skip,
        "limit": pagination.limit,
    }


# Lifecycle endpoints

@router.post("/instances/{instance_id}/start", response_model=InstanceResponse)
async def start_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Start an instance.

    Args:
        instance_id: Instance ID
        db: Database session

    Returns:
        Updated instance

    Raises:
        NotFoundException: If instance not found
        InvalidStateTransitionException: If instance cannot be started
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Check valid transition
    if InstanceStatusEnum.STARTING not in VALID_TRANSITIONS.get(instance.status, []):
        raise InvalidStateTransitionException(instance.status.value, "starting")

    instance.status = InstanceStatusEnum.RUNNING
    instance.started_at = datetime.utcnow()
    instance.stopped_at = None
    instance.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)


@router.post("/instances/{instance_id}/stop", response_model=InstanceResponse)
async def stop_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Stop an instance.

    Args:
        instance_id: Instance ID
        db: Database session

    Returns:
        Updated instance

    Raises:
        NotFoundException: If instance not found
        InvalidStateTransitionException: If instance cannot be stopped
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Check valid transition
    if InstanceStatusEnum.STOPPING not in VALID_TRANSITIONS.get(instance.status, []):
        raise InvalidStateTransitionException(instance.status.value, "stopping")

    instance.status = InstanceStatusEnum.STOPPED
    instance.stopped_at = datetime.utcnow()
    instance.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)


@router.post("/instances/{instance_id}/restart", response_model=InstanceResponse)
async def restart_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Restart an instance (stop then start).

    Args:
        instance_id: Instance ID
        db: Database session

    Returns:
        Updated instance

    Raises:
        NotFoundException: If instance not found
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Set to running (restart)
    instance.status = InstanceStatusEnum.RUNNING
    instance.started_at = datetime.utcnow()
    instance.stopped_at = None
    instance.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)


@router.post("/instances/{instance_id}/pause", response_model=InstanceResponse)
async def pause_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Pause an instance.

    Args:
        instance_id: Instance ID
        db: Database session

    Returns:
        Updated instance

    Raises:
        NotFoundException: If instance not found
        InvalidStateTransitionException: If instance cannot be paused
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Check valid transition
    if InstanceStatusEnum.PAUSED not in VALID_TRANSITIONS.get(instance.status, []):
        raise InvalidStateTransitionException(instance.status.value, "paused")

    instance.status = InstanceStatusEnum.PAUSED
    instance.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)


@router.post("/instances/{instance_id}/resume", response_model=InstanceResponse)
async def resume_instance(
    instance_id: str,
    db: AsyncSession = Depends(get_db),
) -> InstanceResponse:
    """
    Resume a paused instance.

    Args:
        instance_id: Instance ID
        db: Database session

    Returns:
        Updated instance

    Raises:
        NotFoundException: If instance not found
        InvalidStateTransitionException: If instance cannot be resumed
    """
    query = select(HopperInstance).where(HopperInstance.id == instance_id)
    result = await db.execute(query)
    instance = result.scalar_one_or_none()

    if not instance:
        raise NotFoundException("HopperInstance", instance_id)

    # Check valid transition (only from PAUSED)
    if instance.status != InstanceStatusEnum.PAUSED:
        raise InvalidStateTransitionException(instance.status.value, "running")

    instance.status = InstanceStatusEnum.RUNNING
    instance.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(instance)

    return _instance_to_response(instance)
