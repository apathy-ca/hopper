"""
Learning API endpoints.

Provides endpoints for feedback, patterns, and learning statistics.
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from hopper.api.dependencies import PaginationParams, get_db
from hopper.api.exceptions import NotFoundException, ValidationException
from hopper.api.schemas.learning import (
    ConsolidationResult,
    FeedbackCreate,
    FeedbackList,
    FeedbackResponse,
    LearningStats,
    PatternCreate,
    PatternList,
    PatternMatch,
    PatternResponse,
    PatternUpdate,
    RoutingAccuracyStats,
)
from hopper.models import Task, TaskFeedback

router = APIRouter()


# ============================================================================
# Helper to run sync operations
# ============================================================================


def _get_sync_components(session: AsyncSession):
    """Get sync learning components from async session."""
    # Run sync operations using session.run_sync
    from hopper.memory import (
        ConsolidatedStore,
        EpisodicStore,
        FeedbackAnalytics,
        FeedbackStore,
        LearningEngine,
    )

    # Get the sync connection from async session
    sync_session = session.sync_session

    episodic_store = EpisodicStore(sync_session)
    consolidated_store = ConsolidatedStore(sync_session)
    feedback_store = FeedbackStore(sync_session, episodic_store)
    feedback_analytics = FeedbackAnalytics(sync_session)
    learning_engine = LearningEngine(
        sync_session,
        episodic_store=episodic_store,
        consolidated_store=consolidated_store,
        feedback_store=feedback_store,
    )

    return {
        "episodic_store": episodic_store,
        "consolidated_store": consolidated_store,
        "feedback_store": feedback_store,
        "feedback_analytics": feedback_analytics,
        "learning_engine": learning_engine,
    }


# ============================================================================
# Feedback Endpoints
# ============================================================================


@router.post(
    "/tasks/{task_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["feedback"],
)
async def submit_feedback(
    task_id: str,
    feedback_data: FeedbackCreate,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """
    Submit feedback for a task's routing decision.

    Args:
        task_id: Task ID
        feedback_data: Feedback data
        db: Database session

    Returns:
        Created feedback

    Raises:
        NotFoundException: If task not found
    """
    # Verify task exists
    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise NotFoundException(f"Task {task_id} not found")

    # Use sync session for learning operations
    def _create_feedback(session):
        components = _get_sync_components(db)
        return components["feedback_store"].record_feedback(
            task_id=task_id,
            was_good_match=feedback_data.was_good_match,
            routing_feedback=feedback_data.routing_feedback,
            should_have_routed_to=feedback_data.should_have_routed_to,
            estimated_duration=feedback_data.estimated_duration,
            actual_duration=feedback_data.actual_duration,
            complexity_rating=feedback_data.complexity_rating,
            quality_score=feedback_data.quality_score,
            required_rework=feedback_data.required_rework,
            rework_reason=feedback_data.rework_reason,
            unexpected_blockers=feedback_data.unexpected_blockers,
            required_skills_not_tagged=feedback_data.required_skills_not_tagged,
            notes=feedback_data.notes,
        )

    feedback = await db.run_sync(lambda s: _create_feedback(s))

    if not feedback:
        raise ValidationException("Failed to create feedback")

    return FeedbackResponse.model_validate(feedback)


@router.get(
    "/tasks/{task_id}/feedback",
    response_model=FeedbackResponse,
    tags=["feedback"],
)
async def get_task_feedback(
    task_id: str,
    db: AsyncSession = Depends(get_db),
) -> FeedbackResponse:
    """
    Get feedback for a specific task.

    Args:
        task_id: Task ID
        db: Database session

    Returns:
        Task feedback

    Raises:
        NotFoundException: If feedback not found
    """
    result = await db.execute(
        select(TaskFeedback).where(TaskFeedback.task_id == task_id)
    )
    feedback = result.scalar_one_or_none()

    if not feedback:
        raise NotFoundException(f"Feedback for task {task_id} not found")

    return FeedbackResponse.model_validate(feedback)


@router.get(
    "/feedback",
    response_model=FeedbackList,
    tags=["feedback"],
)
async def list_feedback(
    pagination: PaginationParams = Depends(),
    good_matches_only: bool | None = Query(None, description="Filter by match status"),
    db: AsyncSession = Depends(get_db),
) -> FeedbackList:
    """
    List all feedback records.

    Args:
        pagination: Pagination parameters
        good_matches_only: Filter by was_good_match
        db: Database session

    Returns:
        Paginated feedback list
    """
    query = select(TaskFeedback).order_by(TaskFeedback.created_at.desc())

    if good_matches_only is True:
        query = query.where(TaskFeedback.was_good_match == True)  # noqa: E712
    elif good_matches_only is False:
        query = query.where(TaskFeedback.was_good_match == False)  # noqa: E712

    # Get total count
    count_query = select(func.count(TaskFeedback.task_id))
    if good_matches_only is not None:
        count_query = count_query.where(TaskFeedback.was_good_match == good_matches_only)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    query = query.offset(pagination.skip).limit(pagination.limit)
    result = await db.execute(query)
    items = [FeedbackResponse.model_validate(f) for f in result.scalars().all()]

    return FeedbackList(
        items=items,
        total=total,
        page=pagination.skip // pagination.limit + 1,
        page_size=pagination.limit,
    )


@router.get(
    "/feedback/accuracy",
    response_model=RoutingAccuracyStats,
    tags=["feedback"],
)
async def get_routing_accuracy(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_db),
) -> RoutingAccuracyStats:
    """
    Get routing accuracy statistics.

    Args:
        days: Number of days to analyze
        db: Database session

    Returns:
        Routing accuracy statistics
    """

    def _get_accuracy(session):
        components = _get_sync_components(db)
        since = datetime.utcnow() - timedelta(days=days)
        return components["feedback_analytics"].get_routing_accuracy(since=since)

    report = await db.run_sync(lambda s: _get_accuracy(s))

    return RoutingAccuracyStats(
        total_feedback=report.total_feedback,
        good_matches=report.good_matches,
        bad_matches=report.bad_matches,
        accuracy_rate=report.accuracy_rate,
        common_misrouting_targets=[
            {"target": t, "count": c} for t, c in report.common_misrouting_targets
        ],
        by_instance=report.by_instance,
        period_start=report.period_start,
        period_end=report.period_end,
    )


# ============================================================================
# Pattern Endpoints
# ============================================================================


@router.post(
    "/patterns",
    response_model=PatternResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["patterns"],
)
async def create_pattern(
    pattern_data: PatternCreate,
    db: AsyncSession = Depends(get_db),
) -> PatternResponse:
    """
    Create a new routing pattern.

    Args:
        pattern_data: Pattern data
        db: Database session

    Returns:
        Created pattern
    """

    def _create(session):
        components = _get_sync_components(db)
        return components["consolidated_store"].create_pattern(
            name=pattern_data.name,
            target_instance=pattern_data.target_instance,
            description=pattern_data.description,
            pattern_type=pattern_data.pattern_type.value,
            tag_criteria=pattern_data.tag_criteria,
            text_criteria=pattern_data.text_criteria,
            priority_criteria=pattern_data.priority_criteria,
            confidence=pattern_data.confidence,
        )

    pattern = await db.run_sync(lambda s: _create(s))

    return PatternResponse(
        id=pattern.id,
        name=pattern.name,
        description=pattern.description,
        pattern_type=pattern.pattern_type,
        target_instance=pattern.target_instance,
        tag_criteria=pattern.tag_criteria,
        text_criteria=pattern.text_criteria,
        priority_criteria=pattern.priority_criteria,
        confidence=pattern.confidence,
        usage_count=pattern.usage_count,
        success_count=pattern.success_count,
        failure_count=pattern.failure_count,
        success_rate=pattern.success_rate,
        is_active=pattern.is_active,
        source_episodes=pattern.source_episodes,
        last_used_at=pattern.last_used_at,
        last_refined_at=pattern.last_refined_at,
        created_at=pattern.created_at,
    )


@router.get(
    "/patterns",
    response_model=PatternList,
    tags=["patterns"],
)
async def list_patterns(
    pagination: PaginationParams = Depends(),
    active_only: bool = Query(True, description="Only return active patterns"),
    instance_id: str | None = Query(None, description="Filter by target instance"),
    db: AsyncSession = Depends(get_db),
) -> PatternList:
    """
    List routing patterns.

    Args:
        pagination: Pagination parameters
        active_only: Only return active patterns
        instance_id: Filter by target instance
        db: Database session

    Returns:
        Paginated pattern list
    """
    from hopper.memory.consolidated import RoutingPattern

    query = select(RoutingPattern).order_by(RoutingPattern.confidence.desc())

    if active_only:
        query = query.where(RoutingPattern.is_active == True)  # noqa: E712

    if instance_id:
        query = query.where(RoutingPattern.target_instance == instance_id)

    # Get total count
    count_query = select(func.count(RoutingPattern.id))
    if active_only:
        count_query = count_query.where(RoutingPattern.is_active == True)  # noqa: E712
    if instance_id:
        count_query = count_query.where(RoutingPattern.target_instance == instance_id)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Get paginated results
    query = query.offset(pagination.skip).limit(pagination.limit)
    result = await db.execute(query)
    patterns = result.scalars().all()

    items = [
        PatternResponse(
            id=p.id,
            name=p.name,
            description=p.description,
            pattern_type=p.pattern_type,
            target_instance=p.target_instance,
            tag_criteria=p.tag_criteria,
            text_criteria=p.text_criteria,
            priority_criteria=p.priority_criteria,
            confidence=p.confidence,
            usage_count=p.usage_count,
            success_count=p.success_count,
            failure_count=p.failure_count,
            success_rate=p.success_rate,
            is_active=p.is_active,
            source_episodes=p.source_episodes,
            last_used_at=p.last_used_at,
            last_refined_at=p.last_refined_at,
            created_at=p.created_at,
        )
        for p in patterns
    ]

    return PatternList(
        items=items,
        total=total,
        page=pagination.skip // pagination.limit + 1,
        page_size=pagination.limit,
    )


@router.get(
    "/patterns/{pattern_id}",
    response_model=PatternResponse,
    tags=["patterns"],
)
async def get_pattern(
    pattern_id: str,
    db: AsyncSession = Depends(get_db),
) -> PatternResponse:
    """
    Get a specific pattern.

    Args:
        pattern_id: Pattern ID
        db: Database session

    Returns:
        Pattern details

    Raises:
        NotFoundException: If pattern not found
    """
    from hopper.memory.consolidated import RoutingPattern

    result = await db.execute(
        select(RoutingPattern).where(RoutingPattern.id == pattern_id)
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise NotFoundException(f"Pattern {pattern_id} not found")

    return PatternResponse(
        id=pattern.id,
        name=pattern.name,
        description=pattern.description,
        pattern_type=pattern.pattern_type,
        target_instance=pattern.target_instance,
        tag_criteria=pattern.tag_criteria,
        text_criteria=pattern.text_criteria,
        priority_criteria=pattern.priority_criteria,
        confidence=pattern.confidence,
        usage_count=pattern.usage_count,
        success_count=pattern.success_count,
        failure_count=pattern.failure_count,
        success_rate=pattern.success_rate,
        is_active=pattern.is_active,
        source_episodes=pattern.source_episodes,
        last_used_at=pattern.last_used_at,
        last_refined_at=pattern.last_refined_at,
        created_at=pattern.created_at,
    )


@router.patch(
    "/patterns/{pattern_id}",
    response_model=PatternResponse,
    tags=["patterns"],
)
async def update_pattern(
    pattern_id: str,
    pattern_data: PatternUpdate,
    db: AsyncSession = Depends(get_db),
) -> PatternResponse:
    """
    Update a pattern.

    Args:
        pattern_id: Pattern ID
        pattern_data: Update data
        db: Database session

    Returns:
        Updated pattern

    Raises:
        NotFoundException: If pattern not found
    """
    from hopper.memory.consolidated import RoutingPattern

    result = await db.execute(
        select(RoutingPattern).where(RoutingPattern.id == pattern_id)
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise NotFoundException(f"Pattern {pattern_id} not found")

    # Update fields
    if pattern_data.name is not None:
        pattern.name = pattern_data.name
    if pattern_data.description is not None:
        pattern.description = pattern_data.description
    if pattern_data.tag_criteria is not None:
        pattern.tag_criteria = pattern_data.tag_criteria
    if pattern_data.text_criteria is not None:
        pattern.text_criteria = pattern_data.text_criteria
    if pattern_data.priority_criteria is not None:
        pattern.priority_criteria = pattern_data.priority_criteria
    if pattern_data.confidence is not None:
        pattern.confidence = pattern_data.confidence
    if pattern_data.is_active is not None:
        pattern.is_active = pattern_data.is_active

    pattern.last_refined_at = datetime.utcnow()

    await db.flush()

    return PatternResponse(
        id=pattern.id,
        name=pattern.name,
        description=pattern.description,
        pattern_type=pattern.pattern_type,
        target_instance=pattern.target_instance,
        tag_criteria=pattern.tag_criteria,
        text_criteria=pattern.text_criteria,
        priority_criteria=pattern.priority_criteria,
        confidence=pattern.confidence,
        usage_count=pattern.usage_count,
        success_count=pattern.success_count,
        failure_count=pattern.failure_count,
        success_rate=pattern.success_rate,
        is_active=pattern.is_active,
        source_episodes=pattern.source_episodes,
        last_used_at=pattern.last_used_at,
        last_refined_at=pattern.last_refined_at,
        created_at=pattern.created_at,
    )


@router.delete(
    "/patterns/{pattern_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["patterns"],
)
async def delete_pattern(
    pattern_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a pattern.

    Args:
        pattern_id: Pattern ID
        db: Database session

    Raises:
        NotFoundException: If pattern not found
    """
    from hopper.memory.consolidated import RoutingPattern

    result = await db.execute(
        select(RoutingPattern).where(RoutingPattern.id == pattern_id)
    )
    pattern = result.scalar_one_or_none()

    if not pattern:
        raise NotFoundException(f"Pattern {pattern_id} not found")

    await db.delete(pattern)


@router.post(
    "/patterns/match",
    response_model=list[PatternMatch],
    tags=["patterns"],
)
async def find_matching_patterns(
    tags: list[str] | None = Query(None, description="Tags to match"),
    priority: str | None = Query(None, description="Priority to match"),
    title: str | None = Query(None, description="Title to match"),
    limit: int = Query(5, ge=1, le=20, description="Maximum results"),
    db: AsyncSession = Depends(get_db),
) -> list[PatternMatch]:
    """
    Find patterns matching criteria.

    Args:
        tags: Tags to match
        priority: Priority to match
        title: Title to match
        limit: Maximum results
        db: Database session

    Returns:
        List of matching patterns with scores
    """

    def _find_matches(session):
        components = _get_sync_components(db)
        tag_dict = {t: True for t in tags} if tags else None
        return components["consolidated_store"].find_matching_patterns(
            tags=tag_dict,
            priority=priority,
            title=title,
            limit=limit,
        )

    matches = await db.run_sync(lambda s: _find_matches(s))

    return [
        PatternMatch(
            pattern=PatternResponse(
                id=p.id,
                name=p.name,
                description=p.description,
                pattern_type=p.pattern_type,
                target_instance=p.target_instance,
                tag_criteria=p.tag_criteria,
                text_criteria=p.text_criteria,
                priority_criteria=p.priority_criteria,
                confidence=p.confidence,
                usage_count=p.usage_count,
                success_count=p.success_count,
                failure_count=p.failure_count,
                success_rate=p.success_rate,
                is_active=p.is_active,
                source_episodes=p.source_episodes,
                last_used_at=p.last_used_at,
                last_refined_at=p.last_refined_at,
                created_at=p.created_at,
            ),
            match_score=score,
        )
        for p, score in matches
    ]


# ============================================================================
# Statistics Endpoints
# ============================================================================


@router.get(
    "/learning/statistics",
    response_model=LearningStats,
    tags=["statistics"],
)
async def get_learning_statistics(
    db: AsyncSession = Depends(get_db),
) -> LearningStats:
    """
    Get overall learning statistics.

    Args:
        db: Database session

    Returns:
        Learning statistics
    """

    def _get_stats(session):
        components = _get_sync_components(db)
        return components["learning_engine"].get_statistics()

    stats = await db.run_sync(lambda s: _get_stats(s))

    from hopper.api.schemas.learning import EpisodicStats, PatternStats

    return LearningStats(
        episodic=EpisodicStats(**stats["episodic"]),
        patterns=PatternStats(**stats["patterns"]),
        searcher=stats["searcher"],
    )


@router.post(
    "/learning/consolidate",
    response_model=ConsolidationResult,
    tags=["statistics"],
)
async def run_consolidation(
    days: int = Query(7, ge=1, le=90, description="Days of data to consolidate"),
    db: AsyncSession = Depends(get_db),
) -> ConsolidationResult:
    """
    Run pattern consolidation from recent episodes.

    Extracts patterns from successful routing decisions.

    Args:
        days: Number of days of data to analyze
        db: Database session

    Returns:
        Consolidation result
    """

    def _consolidate(session):
        components = _get_sync_components(db)
        since = datetime.utcnow() - timedelta(days=days)
        return components["learning_engine"].run_consolidation(since=since)

    result = await db.run_sync(lambda s: _consolidate(s))

    return ConsolidationResult(
        candidates_found=result.patterns_created,  # Simplified
        patterns_created=result.patterns_created,
        created_pattern_ids=[],
        total_patterns=0,
        active_patterns=0,
        since=(datetime.utcnow() - timedelta(days=days)).isoformat(),
        ran_at=datetime.utcnow().isoformat(),
    )
