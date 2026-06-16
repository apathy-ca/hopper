"""
Task management API endpoints.

Provides CRUD operations, filtering, search, and status updates for tasks.
"""

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from hopper.api.dependencies import PaginationParams, get_db, records_backend_enabled
from hopper.api.exceptions import (
    InvalidStateTransitionException,
    NotFoundException,
    ValidationException,
)
from hopper.api.repositories.record_tasks import RecordTaskRepository
from hopper.api.schemas.task import (
    Priority,
    TaskCreate,
    TaskFeedbackCreate,
    TaskFeedbackResponse,
    TaskList,
    TaskResponse,
    TaskStatusUpdate,
    TaskUpdate,
)
from hopper.api.schemas.task import (
    Status as TaskStatus,
)
from hopper.models import TaskFeedback
from hopper.models import TaskStatus as StatusEnum
from hopper.timeutils import utc_now_naive

router = APIRouter()


# Valid status transitions
VALID_TRANSITIONS = {
    StatusEnum.PENDING: [StatusEnum.CLAIMED, StatusEnum.CANCELLED],
    StatusEnum.CLAIMED: [StatusEnum.IN_PROGRESS, StatusEnum.PENDING, StatusEnum.CANCELLED],
    StatusEnum.IN_PROGRESS: [StatusEnum.BLOCKED, StatusEnum.DONE, StatusEnum.CANCELLED],
    StatusEnum.BLOCKED: [StatusEnum.IN_PROGRESS, StatusEnum.CANCELLED],
    StatusEnum.DONE: [],  # Terminal state
    StatusEnum.CANCELLED: [],  # Terminal state
}


# ---------------------------------------------------------------------------
# Records/revisions backend helpers (Phase 2/3)
#
# The REST task routes carry no DID-auth context (unlike the MCP path), so
# server-side writes are attributed to a documented placeholder identity
# standing in for the configured instance DID. Revision history still records
# a non-null author_did/author_location per write.
# ---------------------------------------------------------------------------
_SERVER_AUTHOR_DID = "did:key:hopper-api-server"
_SERVER_AUTHOR_LOCATION = "api"

# Defaults for fields the records payload doesn't carry but TaskResponse
# requires (these have no schema-level default).
_RESPONSE_DEFAULTS: dict[str, Any] = {
    "velocity_requirement": "medium",
    "source": "api",
}


def _record_to_response(rec: dict[str, Any]) -> TaskResponse:
    """Map a records-backend task-shaped dict onto TaskResponse.

    Mirrors the field shape the legacy Task ORM produces. ``assigned_to`` in
    the payload maps to the response ``owner`` field; missing required fields
    fall back to documented defaults.
    """
    data: dict[str, Any] = dict(_RESPONSE_DEFAULTS)
    data.update(
        {
            "id": rec.get("id"),
            "title": rec.get("title") or "",
            "description": rec.get("description") or "",
            "project": rec.get("project"),
            "tags": rec.get("tags") or [],
            "priority": rec.get("priority") or "medium",
            "status": rec.get("status") or "pending",
            "owner": rec.get("assigned_to"),
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
            "kind": rec.get("kind") or "task",
        }
    )
    # Carry through any explicitly-present payload fields that TaskResponse
    # knows about (requester, external_*, context, deps, memory fields, etc.).
    for key in (
        "executor_preference",
        "required_capabilities",
        "estimated_effort",
        "velocity_requirement",
        "requester",
        "source",
        "external_id",
        "external_url",
        "external_platform",
        "conversation_id",
        "context",
        "depends_on",
        "blocks",
        "subject",
        "scope",
        "provenance",
    ):
        if rec.get(key) is not None:
            data[key] = rec[key]
    return TaskResponse.model_validate(data)


def _repo(sync_session) -> RecordTaskRepository:
    return RecordTaskRepository(sync_session)


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """
    Create a new task.

    Args:
        task_data: Task creation data
        db: Database session

    Returns:
        Created task

    Raises:
        ValidationException: If task data is invalid
    """
    if records_backend_enabled():
        payload = task_data.model_dump(exclude_none=True)
        # The payload "owner" concept lives under assigned_to in records.
        payload.setdefault("kind", "task")

        def _create(sync_session) -> dict[str, Any]:
            return _repo(sync_session).create(
                payload,
                author_did=_SERVER_AUTHOR_DID,
                author_location=_SERVER_AUTHOR_LOCATION,
            )

        rec = await db.run_sync(_create)
        return _record_to_response(rec)

    # Create task model
    task = Task(
        title=task_data.title,
        description=task_data.description,
        project=task_data.project,
        tags=task_data.tags or [],
        priority=task_data.priority,
        executor_preference=task_data.executor_preference,
        required_capabilities=task_data.required_capabilities or [],
        estimated_effort=task_data.estimated_effort,
        velocity_requirement=task_data.velocity_requirement,
        requester=task_data.requester,
        source=task_data.source,
        external_id=task_data.external_id,
        external_url=task_data.external_url,
        external_platform=task_data.external_platform,
        conversation_id=task_data.conversation_id,
        context=task_data.context,
        depends_on=task_data.depends_on or [],
        blocks=task_data.blocks or [],
    )

    db.add(task)
    await db.flush()
    await db.refresh(task)

    return TaskResponse.model_validate(task)


@router.get("/tasks", response_model=TaskList)
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    # Filters
    status_filter: list[TaskStatus] | None = Query(None, alias="status"),
    priority: list[Priority] | None = Query(None),
    project: str | None = None,
    tags: list[str] | None = Query(None),
    owner: str | None = None,
    requester: str | None = None,
    # Kind segmentation (records backend only; default kind="task")
    kind: str = Query("task", description="Record kind to list (records backend)"),
    all_kinds: bool = Query(False, description="List all kinds (records backend)"),
    # Sorting
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
) -> TaskList:
    """
    List tasks with filtering, pagination, and sorting.

    Args:
        db: Database session
        pagination: Pagination parameters
        status_filter: Filter by status
        priority: Filter by priority
        project: Filter by project
        tags: Filter by tags
        owner: Filter by owner
        requester: Filter by requester
        sort_by: Sort field
        sort_order: Sort order

    Returns:
        Paginated task list
    """
    if records_backend_enabled():
        # Records backend filters single-valued status/priority in Python; the
        # legacy path accepts lists, so collapse to the first value here.
        status_value = status_filter[0].value if status_filter else None
        priority_value = priority[0].value if priority else None

        def _list(sync_session) -> tuple[list[dict[str, Any]], int]:
            return _repo(sync_session).list(
                kind=kind,
                all_kinds=all_kinds,
                status=status_value,
                priority=priority_value,
                project=project,
                owner=owner,
                tags=tags,
                sort_by=sort_by,
                sort_order=sort_order,
                skip=pagination.skip,
                limit=pagination.limit,
            )

        items, total = await db.run_sync(_list)
        return TaskList(
            items=[_record_to_response(r) for r in items],
            total=total,
            skip=pagination.skip,
            limit=pagination.limit,
            has_more=(pagination.skip + len(items)) < total,
        )

    # Build query
    query = select(Task)

    # Apply filters
    if status_filter:
        query = query.where(Task.status.in_([s.value for s in status_filter]))
    if priority:
        query = query.where(Task.priority.in_([p.value for p in priority]))
    if project:
        query = query.where(Task.project == project)
    if tags:
        # Filter tasks that have ANY of the specified tags
        for tag in tags:
            query = query.where(Task.tags.contains([tag]))
    if owner:
        query = query.where(Task.owner == owner)
    if requester:
        query = query.where(Task.requester == requester)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply sorting
    sort_column = getattr(Task, sort_by, Task.created_at)
    if sort_order == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)

    # Execute query
    result = await db.execute(query)
    tasks = result.scalars().all()

    return TaskList(
        items=[TaskResponse.model_validate(task) for task in tasks],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
        has_more=(pagination.skip + len(tasks)) < total,
    )


@router.get("/tasks/search", response_model=TaskList)
async def search_tasks(
    q: str = Query(..., min_length=1, description="Search query"),
    db: AsyncSession = Depends(get_db),
    pagination: PaginationParams = Depends(),
    kind: str = Query("task", description="Record kind to search (records backend)"),
    all_kinds: bool = Query(False, description="Search all kinds (records backend)"),
) -> TaskList:
    """
    Search tasks by title, description, or tags.

    Basic full-text search for Phase 1. Will be enhanced with
    proper search in later phases.

    NOTE: declared before ``/tasks/{task_id}`` so the static ``/search``
    segment is matched ahead of the dynamic id route.

    Args:
        q: Search query
        db: Database session
        pagination: Pagination parameters

    Returns:
        Matching tasks
    """
    if records_backend_enabled():

        def _search(sync_session) -> tuple[list[dict[str, Any]], int]:
            return _repo(sync_session).search(
                q,
                kind=kind,
                all_kinds=all_kinds,
                skip=pagination.skip,
                limit=pagination.limit,
            )

        items, total = await db.run_sync(_search)
        return TaskList(
            items=[_record_to_response(r) for r in items],
            total=total,
            skip=pagination.skip,
            limit=pagination.limit,
            has_more=(pagination.skip + len(items)) < total,
        )

    # Simple search - will be enhanced with proper search later
    search_pattern = f"%{q}%"
    query = select(Task).where(
        or_(
            Task.title.ilike(search_pattern),
            Task.description.ilike(search_pattern),
        )
    )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = await db.scalar(count_query) or 0

    # Apply pagination
    query = query.offset(pagination.skip).limit(pagination.limit)

    # Execute query
    result = await db.execute(query)
    tasks = result.scalars().all()

    return TaskList(
        items=[TaskResponse.model_validate(task) for task in tasks],
        total=total,
        skip=pagination.skip,
        limit=pagination.limit,
        has_more=(pagination.skip + len(tasks)) < total,
    )


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """
    Get a task by ID.

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        Task details

    Raises:
        NotFoundException: If task not found
    """
    if records_backend_enabled():
        rec = await db.run_sync(lambda s: _repo(s).get(task_id))
        if rec is None:
            raise NotFoundException("Task", task_id)
        return _record_to_response(rec)

    query = select(Task).where(Task.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    return TaskResponse.model_validate(task)


@router.put("/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """
    Update a task.

    Args:
        task_id: Task ID
        task_data: Task update data
        db: Database session

    Returns:
        Updated task

    Raises:
        NotFoundException: If task not found
        InvalidStateTransitionException: If status transition is invalid
    """
    if records_backend_enabled():
        rec = await db.run_sync(lambda s: _repo(s).get(task_id))
        if rec is None:
            raise NotFoundException("Task", task_id)

        current_status = rec.get("status") or "pending"
        # Validate status transition if status is being updated
        if task_data.status and task_data.status != current_status:
            current_enum = StatusEnum(current_status)
            new_status = StatusEnum(task_data.status)
            if new_status not in VALID_TRANSITIONS.get(current_enum, []):
                raise InvalidStateTransitionException(current_status, task_data.status)

        changes = task_data.model_dump(exclude_unset=True)
        # Response uses "owner"; the records payload stores it as assigned_to.
        if "owner" in changes:
            changes["assigned_to"] = changes.pop("owner")

        def _update(sync_session) -> dict[str, Any] | None:
            return _repo(sync_session).update(
                task_id,
                changes,
                author_did=_SERVER_AUTHOR_DID,
                author_location=_SERVER_AUTHOR_LOCATION,
            )

        updated = await db.run_sync(_update)
        if updated is None:
            raise NotFoundException("Task", task_id)
        return _record_to_response(updated)

    query = select(Task).where(Task.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    # Validate status transition if status is being updated
    if task_data.status and task_data.status != task.status.value:
        new_status = StatusEnum(task_data.status)
        if new_status not in VALID_TRANSITIONS.get(task.status, []):
            raise InvalidStateTransitionException(task.status.value, task_data.status)

    # Update fields
    update_data = task_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(task, field, value)

    task.updated_at = utc_now_naive()

    await db.flush()
    await db.refresh(task)

    return TaskResponse.model_validate(task)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a task (soft delete by setting status to CANCELLED).

    Args:
        task_id: Task ID
        db: Database session

    Raises:
        NotFoundException: If task not found
    """
    if records_backend_enabled():

        def _delete(sync_session) -> bool:
            return _repo(sync_session).soft_delete(
                task_id,
                author_did=_SERVER_AUTHOR_DID,
                author_location=_SERVER_AUTHOR_LOCATION,
            )

        ok = await db.run_sync(_delete)
        if not ok:
            raise NotFoundException("Task", task_id)
        return

    query = select(Task).where(Task.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    # Soft delete by setting status to CANCELLED
    task.status = StatusEnum.CANCELLED
    task.updated_at = utc_now_naive()

    await db.flush()


@router.post("/tasks/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: str,
    status_update: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),
) -> TaskResponse:
    """
    Update task status.

    Args:
        task_id: Task ID
        status_update: Status update data
        db: Database session

    Returns:
        Updated task

    Raises:
        NotFoundException: If task not found
        InvalidStateTransitionException: If status transition is invalid
    """
    if records_backend_enabled():
        rec = await db.run_sync(lambda s: _repo(s).get(task_id))
        if rec is None:
            raise NotFoundException("Task", task_id)

        current_status = rec.get("status") or "pending"
        current_enum = StatusEnum(current_status)
        new_status = StatusEnum(status_update.status)
        if new_status not in VALID_TRANSITIONS.get(current_enum, []):
            raise InvalidStateTransitionException(current_status, status_update.status)

        changes: dict[str, Any] = {"status": new_status.value}
        if status_update.owner is not None:
            changes["assigned_to"] = status_update.owner

        def _update_status(sync_session) -> dict[str, Any] | None:
            return _repo(sync_session).update(
                task_id,
                changes,
                author_did=_SERVER_AUTHOR_DID,
                author_location=_SERVER_AUTHOR_LOCATION,
            )

        updated = await db.run_sync(_update_status)
        if updated is None:
            raise NotFoundException("Task", task_id)
        return _record_to_response(updated)

    query = select(Task).where(Task.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    # Validate status transition
    new_status = StatusEnum(status_update.status)
    if new_status not in VALID_TRANSITIONS.get(task.status, []):
        raise InvalidStateTransitionException(task.status.value, status_update.status)

    task.status = new_status
    if status_update.owner is not None:
        task.owner = status_update.owner
    task.updated_at = utc_now_naive()

    await db.flush()
    await db.refresh(task)

    return TaskResponse.model_validate(task)


@router.post(
    "/tasks/{task_id}/feedback",
    response_model=TaskFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task_feedback(
    task_id: str,
    feedback_data: TaskFeedbackCreate,
    db: AsyncSession = Depends(get_db),
) -> TaskFeedbackResponse:
    """
    Create feedback for a completed task.

    Args:
        task_id: Task ID
        feedback_data: Feedback data
        db: Database session

    Returns:
        Created feedback

    Raises:
        NotFoundException: If task not found
        ValidationException: If task is not done or already has feedback
    """
    # Check task exists
    query = select(Task).where(Task.id == task_id)
    result = await db.execute(query)
    task = result.scalar_one_or_none()

    if not task:
        raise NotFoundException("Task", task_id)

    # Check task is done
    if task.status != StatusEnum.DONE:
        raise ValidationException("Feedback can only be added to completed tasks", "task_id")

    # Check if feedback already exists
    existing_fb = await db.execute(select(TaskFeedback).where(TaskFeedback.task_id == task_id))
    if existing_fb.scalar_one_or_none():
        raise ValidationException("Task already has feedback", "task_id")

    # Create feedback
    feedback = TaskFeedback(
        task_id=task_id,
        estimated_duration=feedback_data.estimated_duration,
        actual_duration=feedback_data.actual_duration,
        complexity_rating=feedback_data.complexity_rating,
        was_good_match=feedback_data.was_good_match,
        should_have_routed_to=feedback_data.should_have_routed_to,
        routing_feedback=feedback_data.routing_feedback,
        quality_score=feedback_data.quality_score,
        required_rework=feedback_data.required_rework,
        rework_reason=feedback_data.rework_reason,
        unexpected_blockers=feedback_data.unexpected_blockers or [],
        required_skills_not_tagged=feedback_data.required_skills_not_tagged or [],
        notes=feedback_data.notes,
    )

    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)

    return TaskFeedbackResponse.model_validate(feedback)


@router.get("/tasks/{task_id}/feedback", response_model=TaskFeedbackResponse)
async def get_task_feedback(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> TaskFeedbackResponse:
    """
    Get feedback for a task.

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        Task feedback

    Raises:
        NotFoundException: If task or feedback not found
    """
    query = select(TaskFeedback).where(TaskFeedback.task_id == task_id)
    result = await db.execute(query)
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise NotFoundException("TaskFeedback", task_id)

    return TaskFeedbackResponse.model_validate(feedback)
