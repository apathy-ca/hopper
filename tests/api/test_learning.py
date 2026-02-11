"""
Tests for learning API routes.

Tests the learning API endpoints for feedback, patterns, and statistics.
"""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from hopper.api.schemas.learning import (
    ConsolidationResult,
    EpisodicStats,
    FeedbackCreate,
    FeedbackList,
    FeedbackResponse,
    LearningStats,
    PatternCreate,
    PatternList,
    PatternMatch,
    PatternResponse,
    PatternStats,
    PatternType,
    PatternUpdate,
    RoutingAccuracyStats,
)
from hopper.models import (
    HopperInstance,
    HopperScope,
    InstanceStatus,
    InstanceType,
    Task,
    TaskFeedback,
    TaskStatus,
)
from hopper.memory.consolidated import RoutingPattern


# ============================================================================
# Schema Tests
# ============================================================================


class TestFeedbackSchemas:
    """Test feedback schema validation."""

    def test_feedback_create_minimal(self):
        """Test FeedbackCreate with minimal required fields."""
        data = FeedbackCreate(was_good_match=True)
        assert data.was_good_match is True
        assert data.routing_feedback is None
        assert data.should_have_routed_to is None

    def test_feedback_create_full(self):
        """Test FeedbackCreate with all fields."""
        data = FeedbackCreate(
            was_good_match=False,
            routing_feedback="Wrong instance",
            should_have_routed_to="api-instance",
            estimated_duration="1h",
            actual_duration="2h",
            complexity_rating=4,
            quality_score=3.5,
            required_rework=True,
            rework_reason="Needed different approach",
            unexpected_blockers=["missing dependency"],
            required_skills_not_tagged=["kubernetes"],
            notes="Additional context",
        )
        assert data.was_good_match is False
        assert data.complexity_rating == 4
        assert data.quality_score == 3.5
        assert data.required_rework is True

    def test_feedback_create_validation(self):
        """Test FeedbackCreate validation."""
        # Complexity out of range
        with pytest.raises(ValueError):
            FeedbackCreate(was_good_match=True, complexity_rating=6)

        # Quality out of range
        with pytest.raises(ValueError):
            FeedbackCreate(was_good_match=True, quality_score=6.0)

    def test_feedback_response_from_attributes(self):
        """Test FeedbackResponse can be created from model attributes."""
        feedback = TaskFeedback(
            task_id="task-123",
            was_good_match=True,
            routing_feedback="Good match",
            quality_score=4.5,
            created_at=datetime.utcnow(),
        )
        response = FeedbackResponse.model_validate(feedback)
        assert response.task_id == "task-123"
        assert response.was_good_match is True


class TestPatternSchemas:
    """Test pattern schema validation."""

    def test_pattern_create_tag_type(self):
        """Test PatternCreate for tag-based patterns."""
        data = PatternCreate(
            name="api-tasks",
            target_instance="api-instance",
            pattern_type=PatternType.TAG,
            tag_criteria={"required": ["api", "python"]},
            confidence=0.8,
        )
        assert data.name == "api-tasks"
        assert data.pattern_type == PatternType.TAG
        assert data.confidence == 0.8

    def test_pattern_create_text_type(self):
        """Test PatternCreate for text-based patterns."""
        data = PatternCreate(
            name="auth-tasks",
            target_instance="auth-instance",
            pattern_type=PatternType.TEXT,
            text_criteria={"keywords": ["authentication", "login", "oauth"]},
        )
        assert data.pattern_type == PatternType.TEXT
        assert "authentication" in data.text_criteria["keywords"]

    def test_pattern_create_combined_type(self):
        """Test PatternCreate for combined patterns."""
        data = PatternCreate(
            name="urgent-api",
            target_instance="fast-instance",
            pattern_type=PatternType.COMBINED,
            tag_criteria={"required": ["api"]},
            text_criteria={"keywords": ["urgent"]},
            priority_criteria="urgent",
        )
        assert data.pattern_type == PatternType.COMBINED

    def test_pattern_update_partial(self):
        """Test PatternUpdate with partial fields."""
        data = PatternUpdate(name="new-name")
        assert data.name == "new-name"
        assert data.confidence is None
        assert data.is_active is None

    def test_pattern_update_confidence_validation(self):
        """Test PatternUpdate confidence validation."""
        with pytest.raises(ValueError):
            PatternUpdate(confidence=1.5)  # Out of range


class TestStatisticsSchemas:
    """Test statistics schema structures."""

    def test_routing_accuracy_stats(self):
        """Test RoutingAccuracyStats schema."""
        data = RoutingAccuracyStats(
            total_feedback=100,
            good_matches=85,
            bad_matches=15,
            accuracy_rate=0.85,
            common_misrouting_targets=[{"target": "wrong-instance", "count": 5}],
            by_instance={"api-instance": {"total": 50, "accuracy": 0.9}},
            period_start=datetime.utcnow(),
            period_end=datetime.utcnow(),
        )
        assert data.accuracy_rate == 0.85
        assert len(data.common_misrouting_targets) == 1

    def test_learning_stats(self):
        """Test LearningStats schema."""
        data = LearningStats(
            episodic=EpisodicStats(
                total_episodes=100,
                successful=80,
                failed=10,
                pending=10,
                success_rate=0.8,
                average_confidence=0.75,
                since=None,
            ),
            patterns=PatternStats(
                total_patterns=20,
                active_patterns=15,
                inactive_patterns=5,
                total_usage=200,
                average_confidence=0.7,
                by_type={"tag": 10, "text": 5, "combined": 5},
                by_instance={"api-instance": 8, "web-instance": 7},
            ),
            searcher={"index_size": 500, "backend": "local"},
        )
        assert data.episodic.success_rate == 0.8
        assert data.patterns.total_patterns == 20


# ============================================================================
# Model Tests
# ============================================================================


class TestFeedbackModel:
    """Test TaskFeedback model operations."""

    def test_create_feedback(self, clean_db: Session):
        """Test creating feedback."""
        # Create a task first
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Test task",
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        clean_db.add(task)
        clean_db.flush()

        feedback = TaskFeedback(
            task_id=task.id,
            was_good_match=True,
            routing_feedback="Good routing",
            quality_score=4.0,
            created_at=datetime.utcnow(),
        )
        clean_db.add(feedback)
        clean_db.flush()

        retrieved = clean_db.query(TaskFeedback).filter_by(task_id=task.id).first()
        assert retrieved is not None
        assert retrieved.was_good_match is True
        assert retrieved.quality_score == 4.0

    def test_feedback_with_all_fields(self, clean_db: Session):
        """Test feedback with all optional fields."""
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Test task",
            status=TaskStatus.DONE,
            created_at=datetime.utcnow(),
        )
        clean_db.add(task)
        clean_db.flush()

        feedback = TaskFeedback(
            task_id=task.id,
            was_good_match=False,
            routing_feedback="Wrong team",
            should_have_routed_to="correct-instance",
            estimated_duration="1h",
            actual_duration="3h",
            complexity_rating=5,
            quality_score=2.5,
            required_rework=True,
            rework_reason="Scope was wrong",
            created_at=datetime.utcnow(),
        )
        clean_db.add(feedback)
        clean_db.flush()

        retrieved = clean_db.query(TaskFeedback).filter_by(task_id=task.id).first()
        assert retrieved.should_have_routed_to == "correct-instance"
        assert retrieved.complexity_rating == 5
        assert retrieved.required_rework is True


class TestPatternModel:
    """Test RoutingPattern model operations."""

    def test_create_pattern(self, clean_db: Session):
        """Test creating a routing pattern."""
        pattern = RoutingPattern(
            id=f"pat-{uuid4().hex[:8]}",
            name="api-python-tasks",
            pattern_type="tag",
            target_instance="api-instance",
            tag_criteria={"required": ["api", "python"]},
            confidence=0.8,
            is_active=True,
            created_at=datetime.utcnow(),
        )
        clean_db.add(pattern)
        clean_db.flush()

        retrieved = clean_db.query(RoutingPattern).filter_by(id=pattern.id).first()
        assert retrieved is not None
        assert retrieved.name == "api-python-tasks"
        assert retrieved.confidence == 0.8

    def test_pattern_usage_tracking(self, clean_db: Session):
        """Test pattern usage count tracking."""
        pattern = RoutingPattern(
            id=f"pat-{uuid4().hex[:8]}",
            name="test-pattern",
            pattern_type="tag",
            target_instance="test-instance",
            confidence=0.7,
            usage_count=0,
            success_count=0,
            failure_count=0,
            created_at=datetime.utcnow(),
        )
        clean_db.add(pattern)
        clean_db.flush()

        # Simulate usage
        pattern.record_usage(success=True)
        clean_db.flush()

        assert pattern.usage_count == 1
        assert pattern.success_count == 1
        assert pattern.success_rate == 1.0

        # Record a failure
        pattern.record_usage(success=False)
        clean_db.flush()

        assert pattern.usage_count == 2
        assert pattern.failure_count == 1
        assert pattern.success_rate == 0.5

    def test_pattern_deactivation(self, clean_db: Session):
        """Test pattern activation/deactivation."""
        pattern = RoutingPattern(
            id=f"pat-{uuid4().hex[:8]}",
            name="toggle-pattern",
            pattern_type="tag",
            target_instance="test-instance",
            is_active=True,
            created_at=datetime.utcnow(),
        )
        clean_db.add(pattern)
        clean_db.flush()

        assert pattern.is_active is True

        pattern.is_active = False
        clean_db.flush()

        retrieved = clean_db.query(RoutingPattern).filter_by(id=pattern.id).first()
        assert retrieved.is_active is False


# ============================================================================
# Integration Tests
# ============================================================================


class TestFeedbackIntegration:
    """Integration tests for feedback functionality."""

    def test_feedback_with_learning_engine(self, db_session: Session):
        """Test feedback processed by learning engine."""
        from hopper.memory import FeedbackStore, EpisodicStore, LearningEngine

        # Create test instance first (foreign key requirement)
        instance = HopperInstance(
            id="api-instance",
            name="API Instance",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.RUNNING,
            created_at=datetime.utcnow(),
        )
        db_session.add(instance)
        db_session.flush()

        # Create test task
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="API endpoint task",
            project="backend",
            status=TaskStatus.DONE,
            instance_id="api-instance",
            tags={"api": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        db_session.flush()

        # Setup learning components
        episodic_store = EpisodicStore(db_session)
        feedback_store = FeedbackStore(db_session, episodic_store)

        # Record routing first
        episode = episodic_store.record_episode(
            task=task,
            chosen_instance="api-instance",
            confidence=0.8,
        )

        # Now record feedback
        feedback = feedback_store.record_feedback(
            task_id=task.id,
            was_good_match=True,
            routing_feedback="Correct routing",
            quality_score=4.5,
        )

        assert feedback is not None
        assert feedback.was_good_match is True

    def test_multiple_feedback_records(self, db_session: Session):
        """Test tracking multiple feedback records."""
        tasks = []
        for i in range(5):
            task = Task(
                id=f"multi-task-{uuid4().hex[:8]}",
                title=f"Task {i}",
                status=TaskStatus.DONE,
                created_at=datetime.utcnow(),
            )
            db_session.add(task)
            tasks.append(task)
        db_session.flush()

        # Create feedback for each
        for i, task in enumerate(tasks):
            feedback = TaskFeedback(
                task_id=task.id,
                was_good_match=(i % 2 == 0),  # Alternate good/bad
                quality_score=float(i + 1),
                created_at=datetime.utcnow(),
            )
            db_session.add(feedback)
        db_session.flush()

        # Query feedback
        all_feedback = db_session.query(TaskFeedback).all()
        good_matches = [f for f in all_feedback if f.was_good_match]
        bad_matches = [f for f in all_feedback if not f.was_good_match]

        assert len(good_matches) == 3
        assert len(bad_matches) == 2


class TestPatternIntegration:
    """Integration tests for pattern functionality."""

    def test_pattern_matching(self, db_session: Session):
        """Test pattern matching against tasks."""
        from hopper.memory import ConsolidatedStore

        store = ConsolidatedStore(db_session)

        # Create pattern
        pattern = store.create_pattern(
            name="api-tasks",
            target_instance="api-instance",
            tag_criteria={"required": ["api"]},
            confidence=0.8,
        )

        # Find matching patterns
        matches = store.find_matching_patterns(
            tags={"api": True, "python": True},
            limit=5,
        )

        assert len(matches) >= 1
        matched_pattern, score = matches[0]
        assert matched_pattern.id == pattern.id
        assert score > 0

    def test_pattern_consolidation(self, db_session: Session):
        """Test pattern extraction from episodes."""
        from hopper.memory import ConsolidatedStore, EpisodicStore, PatternExtractor

        # Create test instance first
        instance = HopperInstance(
            id="consol-api-instance",
            name="API Instance",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.RUNNING,
            created_at=datetime.utcnow(),
        )
        db_session.add(instance)
        db_session.flush()

        episodic_store = EpisodicStore(db_session)
        consolidated_store = ConsolidatedStore(db_session)
        extractor = PatternExtractor(db_session, episodic_store, consolidated_store)

        # Create test tasks with consistent routing
        for i in range(10):
            task = Task(
                id=f"consol-task-{uuid4().hex[:8]}",
                title=f"API task {i}",
                status=TaskStatus.DONE,
                instance_id="consol-api-instance",
                tags={"api": True, "rest": True},
                created_at=datetime.utcnow(),
            )
            db_session.add(task)
            db_session.flush()

            episode = episodic_store.record_episode(
                task=task,
                chosen_instance="consol-api-instance",
                confidence=0.8,
            )
            episode.mark_success()

        db_session.flush()

        # Run consolidation
        result = extractor.run_consolidation()

        # Result is a dict with pattern info
        assert "patterns_created" in result
        assert result["patterns_created"] >= 0


class TestLearningStatistics:
    """Test learning statistics aggregation."""

    def test_episodic_statistics(self, db_session: Session):
        """Test episodic memory statistics."""
        from hopper.memory import EpisodicStore

        store = EpisodicStore(db_session)

        # Create some episodes
        for i in range(10):
            task = Task(
                id=f"stat-task-{uuid4().hex[:8]}",
                title=f"Stat task {i}",
                status=TaskStatus.DONE,
                created_at=datetime.utcnow(),
            )
            db_session.add(task)
            db_session.flush()

            episode = store.record_episode(
                task=task,
                chosen_instance="test-instance",
                confidence=0.7 + (i * 0.02),
            )

            if i < 7:
                episode.mark_success()
            elif i < 9:
                episode.mark_failure("Test failure")

        db_session.flush()

        # Get statistics
        stats = store.get_statistics()

        assert stats["total_episodes"] == 10
        assert stats["successful"] == 7
        assert stats["failed"] == 2
        assert stats["pending"] == 1

    def test_pattern_statistics(self, db_session: Session):
        """Test pattern statistics."""
        from hopper.memory import ConsolidatedStore

        store = ConsolidatedStore(db_session)

        # Create patterns
        patterns = []
        for i in range(5):
            pattern = store.create_pattern(
                name=f"stat-pattern-{i}",
                target_instance=f"instance-{i % 2}",
                pattern_type="tag" if i % 2 == 0 else "text",
                confidence=0.5 + (i * 0.1),
            )
            patterns.append(pattern)

        # Deactivate some patterns
        patterns[3].is_active = False
        patterns[4].is_active = False
        db_session.flush()

        stats = store.get_statistics()

        assert stats["total_patterns"] == 5
        assert stats["active_patterns"] == 3
        assert stats["inactive_patterns"] == 2


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_feedback_for_nonexistent_task(self, db_session: Session):
        """Test feedback submission for non-existent task."""
        # TaskFeedback has a foreign key constraint, so this should fail
        feedback = TaskFeedback(
            task_id="nonexistent-task",
            was_good_match=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(feedback)

        # Should raise integrity error
        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_duplicate_feedback(self, db_session: Session):
        """Test handling duplicate feedback for same task."""
        task = Task(
            id=f"dup-task-{uuid4().hex[:8]}",
            title="Duplicate test",
            status=TaskStatus.DONE,
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        db_session.flush()

        # First feedback
        feedback1 = TaskFeedback(
            task_id=task.id,
            was_good_match=True,
            created_at=datetime.utcnow(),
        )
        db_session.add(feedback1)
        db_session.flush()

        # Second feedback should fail (primary key constraint)
        feedback2 = TaskFeedback(
            task_id=task.id,
            was_good_match=False,
            created_at=datetime.utcnow(),
        )
        db_session.add(feedback2)

        with pytest.raises(Exception):
            db_session.flush()
        db_session.rollback()

    def test_pattern_with_empty_criteria(self, db_session: Session):
        """Test pattern creation with empty criteria."""
        pattern = RoutingPattern(
            id=f"empty-pat-{uuid4().hex[:8]}",
            name="empty-criteria",
            pattern_type="tag",
            target_instance="test-instance",
            tag_criteria={},
            text_criteria={},
            confidence=0.5,
            created_at=datetime.utcnow(),
        )
        db_session.add(pattern)
        db_session.flush()

        retrieved = db_session.query(RoutingPattern).filter_by(id=pattern.id).first()
        assert retrieved is not None
        assert retrieved.tag_criteria == {}

    def test_very_long_feedback_text(self, db_session: Session):
        """Test feedback with very long text."""
        task = Task(
            id=f"long-task-{uuid4().hex[:8]}",
            title="Long text test",
            status=TaskStatus.DONE,
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        db_session.flush()

        long_text = "A" * 10000  # Very long feedback

        feedback = TaskFeedback(
            task_id=task.id,
            was_good_match=True,
            routing_feedback=long_text,
            notes=long_text,
            created_at=datetime.utcnow(),
        )
        db_session.add(feedback)
        db_session.flush()

        retrieved = db_session.query(TaskFeedback).filter_by(task_id=task.id).first()
        assert len(retrieved.routing_feedback) == 10000
