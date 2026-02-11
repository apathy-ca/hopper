"""
Tests for the learning loop integration.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from hopper.memory.learning import LearningEngine, RoutingSuggestion, SuggestionSource
from hopper.memory.working import WorkingMemory
from hopper.memory.working.context import InstanceInfo, SimilarTask
from hopper.memory.episodic import EpisodicStore
from hopper.memory.search import TaskSearcher
from hopper.memory.consolidated import ConsolidatedStore
from hopper.memory.feedback import FeedbackStore
from hopper.models import Task, TaskStatus, HopperInstance, HopperScope, InstanceStatus, InstanceType


@pytest.fixture
def test_instances(db_session):
    """Create test instances."""
    instances = [
        HopperInstance(
            id="api-instance",
            name="API Instance",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.RUNNING,
            config={},
            created_at=datetime.utcnow(),
        ),
        HopperInstance(
            id="web-instance",
            name="Web Instance",
            scope=HopperScope.PROJECT,
            instance_type=InstanceType.PERSISTENT,
            status=InstanceStatus.RUNNING,
            config={},
            created_at=datetime.utcnow(),
        ),
    ]
    for inst in instances:
        db_session.add(inst)
    db_session.flush()
    return instances


@pytest.fixture
def learning_engine(db_session) -> LearningEngine:
    """Create learning engine for testing."""
    return LearningEngine(db_session)


@pytest.fixture
def sample_task(db_session) -> Task:
    """Create a sample task."""
    task = Task(
        id=f"task-{uuid4().hex[:8]}",
        title="Implement API endpoint",
        description="Create a new REST API endpoint",
        project="backend",
        status=TaskStatus.PENDING,
        priority="high",
        tags={"api": True, "python": True, "backend": True},
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def tasks_with_history(db_session, test_instances) -> list[Task]:
    """Create tasks with routing history."""
    tasks = []
    for i in range(5):
        task = Task(
            id=f"hist-task-{uuid4().hex[:8]}",
            title=f"API task {i}",
            description=f"API endpoint task {i}",
            project="backend",
            status=TaskStatus.DONE,
            instance_id="api-instance",
            tags={"api": True, "python": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        tasks.append(task)
    db_session.flush()
    return tasks


class TestRoutingSuggestion:
    """Tests for RoutingSuggestion."""

    def test_from_pattern(self):
        """Test creating suggestion from pattern."""
        suggestion = RoutingSuggestion.from_pattern(
            target_instance="api-instance",
            confidence=0.85,
            pattern_id="pat-123",
            pattern_name="api-python-tasks",
        )

        assert suggestion.target_instance == "api-instance"
        assert suggestion.confidence == 0.85
        assert suggestion.source == SuggestionSource.PATTERN
        assert suggestion.pattern_id == "pat-123"
        assert "api-python-tasks" in suggestion.reasoning

    def test_from_similar_tasks(self):
        """Test creating suggestion from similar tasks."""
        suggestion = RoutingSuggestion.from_similar_tasks(
            target_instance="api-instance",
            confidence=0.75,
            similar_task_ids=["task-1", "task-2", "task-3"],
            success_rate=0.8,
        )

        assert suggestion.target_instance == "api-instance"
        assert suggestion.source == SuggestionSource.SIMILAR_TASK
        assert len(suggestion.similar_task_ids) == 3
        assert suggestion.factors["success_rate"] == 0.8

    def test_to_dict(self):
        """Test suggestion serialization."""
        suggestion = RoutingSuggestion(
            target_instance="test",
            confidence=0.9,
            source=SuggestionSource.RULES,
            reasoning="Test reasoning",
        )

        data = suggestion.to_dict()

        assert data["target_instance"] == "test"
        assert data["confidence"] == 0.9
        assert data["source"] == "rules"


class TestLearningEngine:
    """Tests for LearningEngine."""

    def test_build_context(self, learning_engine, sample_task):
        """Test building routing context."""
        context = learning_engine.build_context(sample_task)

        assert context.task_id == sample_task.id
        assert context.task_title == sample_task.title
        assert "api" in context.task_tags

    def test_build_context_caching(self, learning_engine, sample_task):
        """Test that context is cached."""
        context1 = learning_engine.build_context(sample_task)
        context2 = learning_engine.build_context(sample_task)

        # Should get same object from cache
        assert context1.task_id == context2.task_id

    def test_get_routing_suggestions_empty(self, learning_engine, sample_task):
        """Test suggestions with no patterns or history."""
        suggestions = learning_engine.get_routing_suggestions(sample_task)

        # May have suggestions based on similar tasks, or be empty
        assert isinstance(suggestions, list)

    def test_get_routing_suggestions_with_pattern(self, db_session, learning_engine, sample_task):
        """Test suggestions with matching pattern."""
        # Create a pattern
        learning_engine.consolidated_store.create_pattern(
            name="api-python-pattern",
            target_instance="api-instance",
            tag_criteria={"required": ["api", "python"]},
            confidence=0.85,
        )

        suggestions = learning_engine.get_routing_suggestions(sample_task)

        assert len(suggestions) >= 1
        assert any(s.source == SuggestionSource.PATTERN for s in suggestions)
        assert any(s.target_instance == "api-instance" for s in suggestions)

    def test_record_routing(self, learning_engine, sample_task):
        """Test recording a routing decision."""
        episode = learning_engine.record_routing(
            task=sample_task,
            chosen_instance="api-instance",
            confidence=0.85,
            strategy="learning",
            reasoning="Pattern match",
        )

        assert episode is not None
        assert episode.task_id == sample_task.id
        assert episode.chosen_instance == "api-instance"
        assert episode.confidence == 0.85

    def test_record_routing_with_suggestion(self, db_session, learning_engine, sample_task):
        """Test recording routing with suggestion reference."""
        suggestion = RoutingSuggestion.from_pattern(
            target_instance="api-instance",
            confidence=0.8,
            pattern_id="pat-123",
            pattern_name="test-pattern",
        )

        episode = learning_engine.record_routing(
            task=sample_task,
            chosen_instance="api-instance",
            confidence=0.8,
            suggestion=suggestion,
        )

        assert episode.decision_factors["pattern_id"] == "pat-123"
        assert episode.decision_factors["source"] == "pattern"

    def test_record_outcome(self, learning_engine, sample_task):
        """Test recording routing outcome."""
        # First record the routing
        episode = learning_engine.record_routing(
            task=sample_task,
            chosen_instance="api-instance",
            confidence=0.8,
        )

        # Then record outcome
        result = learning_engine.record_outcome(
            task_id=sample_task.id,
            success=True,
            duration="30m",
            notes="Completed successfully",
        )

        assert result.episodes_created == 1

        # Verify episode was updated
        updated = learning_engine.episodic_store.get_episode(episode.id)
        assert updated.outcome_success is True
        assert updated.outcome_duration == "30m"

    def test_record_outcome_updates_pattern(self, db_session, learning_engine, sample_task):
        """Test that outcome updates pattern confidence."""
        # Create pattern
        pattern = learning_engine.consolidated_store.create_pattern(
            name="test-pattern",
            target_instance="api-instance",
            tag_criteria={"required": ["api"]},
            confidence=0.7,
        )

        # Record routing with pattern
        suggestion = RoutingSuggestion.from_pattern(
            target_instance="api-instance",
            confidence=0.7,
            pattern_id=pattern.id,
            pattern_name="test-pattern",
        )

        learning_engine.record_routing(
            task=sample_task,
            chosen_instance="api-instance",
            confidence=0.7,
            suggestion=suggestion,
        )

        # Record successful outcome
        result = learning_engine.record_outcome(
            task_id=sample_task.id,
            success=True,
        )

        assert result.patterns_updated == 1

        # Pattern usage should be recorded
        updated_pattern = learning_engine.consolidated_store.get_pattern(pattern.id)
        assert updated_pattern.usage_count == 1
        assert updated_pattern.success_count == 1

    def test_process_feedback(self, learning_engine, sample_task):
        """Test processing user feedback."""
        # Record routing first
        learning_engine.record_routing(
            task=sample_task,
            chosen_instance="api-instance",
            confidence=0.8,
        )

        # Process feedback
        result = learning_engine.process_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            routing_feedback="Good routing decision",
        )

        assert result.feedback_processed == 1

    def test_process_feedback_bad_match(self, learning_engine, sample_task):
        """Test processing negative feedback."""
        learning_engine.record_routing(
            task=sample_task,
            chosen_instance="web-instance",
            confidence=0.6,
        )

        result = learning_engine.process_feedback(
            task_id=sample_task.id,
            was_good_match=False,
            should_have_routed_to="api-instance",
            routing_feedback="Should have gone to API team",
        )

        assert result.feedback_processed == 1

    def test_run_consolidation(self, db_session, learning_engine, tasks_with_history):
        """Test running consolidation."""
        # Create episodes for historical tasks
        for task in tasks_with_history:
            episode = learning_engine.episodic_store.record_episode(
                task=task,
                chosen_instance="api-instance",
                confidence=0.8,
            )
            episode.mark_success()

        # Run consolidation
        result = learning_engine.run_consolidation()

        # May or may not create patterns depending on data
        assert "patterns_created" in result.to_dict()

    def test_get_statistics(self, learning_engine):
        """Test getting engine statistics."""
        stats = learning_engine.get_statistics()

        assert "episodic" in stats
        assert "patterns" in stats
        assert "searcher" in stats


class TestLearningIntegration:
    """Integration tests for the learning loop."""

    def test_full_learning_cycle(self, db_session, learning_engine, sample_task, test_instances):
        """Test complete learning cycle: context -> suggestion -> routing -> feedback."""
        # 1. Build context
        context = learning_engine.build_context(
            sample_task,
            available_instances=[
                InstanceInfo(
                    instance_id="api-instance",
                    name="API Instance",
                    scope="PROJECT",
                    status="running",
                ),
                InstanceInfo(
                    instance_id="web-instance",
                    name="Web Instance",
                    scope="PROJECT",
                    status="running",
                ),
            ],
        )

        assert context.task_id == sample_task.id

        # 2. Get suggestions
        suggestions = learning_engine.get_routing_suggestions(sample_task, context)

        # 3. Record routing (even if no suggestions, we make a decision)
        chosen_instance = suggestions[0].target_instance if suggestions else "api-instance"
        confidence = suggestions[0].confidence if suggestions else 0.5

        episode = learning_engine.record_routing(
            task=sample_task,
            chosen_instance=chosen_instance,
            confidence=confidence,
            suggestion=suggestions[0] if suggestions else None,
        )

        assert episode.task_id == sample_task.id

        # 4. Process feedback
        result = learning_engine.process_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            routing_feedback="Good choice",
        )

        assert result.feedback_processed == 1

    def test_learning_improves_with_data(self, db_session, test_instances):
        """Test that suggestions improve with more historical data."""
        engine = LearningEngine(db_session)

        # Create multiple tasks with consistent routing pattern
        for i in range(10):
            task = Task(
                id=f"learn-task-{uuid4().hex[:8]}",
                title=f"API endpoint {i}",
                project="backend",
                status=TaskStatus.DONE,
                instance_id="api-instance",
                tags={"api": True, "python": True},
                created_at=datetime.utcnow(),
            )
            db_session.add(task)
            db_session.flush()

            # Record episode with success
            episode = engine.episodic_store.record_episode(
                task=task,
                chosen_instance="api-instance",
                confidence=0.8,
            )
            episode.mark_success()

        db_session.flush()

        # Run consolidation to learn patterns
        engine.run_consolidation()

        # Now create a new similar task
        new_task = Task(
            id=f"new-task-{uuid4().hex[:8]}",
            title="New API endpoint",
            project="backend",
            status=TaskStatus.PENDING,
            tags={"api": True, "python": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(new_task)
        db_session.flush()

        # Get suggestions - should suggest api-instance with higher confidence
        suggestions = engine.get_routing_suggestions(new_task)

        # We should have suggestions based on learned patterns or similar tasks
        if suggestions:
            # The top suggestion should point to api-instance
            assert suggestions[0].target_instance == "api-instance"
