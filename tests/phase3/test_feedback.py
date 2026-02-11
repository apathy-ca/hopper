"""
Tests for feedback collection and analytics.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from hopper.memory.feedback import FeedbackStore, FeedbackAnalytics
from hopper.memory.episodic import EpisodicStore
from hopper.models import Task, TaskFeedback, TaskStatus


@pytest.fixture
def episodic_store(db_session) -> EpisodicStore:
    """Create episodic store for testing."""
    return EpisodicStore(db_session)


@pytest.fixture
def feedback_store(db_session, episodic_store) -> FeedbackStore:
    """Create feedback store for testing."""
    return FeedbackStore(db_session, episodic_store)


@pytest.fixture
def feedback_analytics(db_session) -> FeedbackAnalytics:
    """Create feedback analytics for testing."""
    return FeedbackAnalytics(db_session)


@pytest.fixture
def test_instances(db_session):
    """Create test instances for FK constraints."""
    from hopper.models import HopperInstance, HopperScope, InstanceStatus, InstanceType

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
def sample_task(db_session, test_instances) -> Task:
    """Create a sample task."""
    task = Task(
        id=f"task-{uuid4().hex[:8]}",
        title="Test task",
        description="A test task",
        project="test-project",
        status=TaskStatus.DONE,
        instance_id="api-instance",
        tags={"api": True, "python": True},
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def multiple_tasks(db_session, test_instances) -> list[Task]:
    """Create multiple tasks for testing."""
    tasks = []
    for i in range(5):
        task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title=f"Task {i}",
            description=f"Description {i}",
            project="test-project",
            status=TaskStatus.DONE,
            instance_id="api-instance" if i < 3 else "web-instance",
            tags={"api": True} if i < 3 else {"frontend": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(task)
        tasks.append(task)
    db_session.flush()
    return tasks


class TestFeedbackStore:
    """Tests for FeedbackStore."""

    def test_record_feedback(self, feedback_store, sample_task):
        """Test recording feedback for a task."""
        feedback = feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            routing_feedback="Perfect routing",
            estimated_duration="2h",
            actual_duration="1h30m",
            complexity_rating=3,
            quality_score=4.5,
        )

        assert feedback is not None
        assert feedback.task_id == sample_task.id
        assert feedback.was_good_match is True
        assert feedback.routing_feedback == "Perfect routing"
        assert feedback.complexity_rating == 3

    def test_record_feedback_bad_match(self, feedback_store, sample_task):
        """Test recording feedback for bad routing."""
        feedback = feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=False,
            should_have_routed_to="web-instance",
            routing_feedback="Should have gone to frontend team",
        )

        assert feedback.was_good_match is False
        assert feedback.should_have_routed_to == "web-instance"

    def test_record_feedback_with_blockers(self, feedback_store, sample_task):
        """Test recording feedback with blockers."""
        feedback = feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            unexpected_blockers=["Missing docs", "API rate limits"],
            required_skills_not_tagged=["docker", "kubernetes"],
        )

        assert feedback.unexpected_blockers == {"blockers": ["Missing docs", "API rate limits"]}
        assert feedback.required_skills_not_tagged == {"skills": ["docker", "kubernetes"]}

    def test_record_feedback_nonexistent_task(self, feedback_store):
        """Test recording feedback for nonexistent task."""
        feedback = feedback_store.record_feedback(
            task_id="nonexistent",
            was_good_match=True,
        )

        assert feedback is None

    def test_update_existing_feedback(self, feedback_store, sample_task):
        """Test updating existing feedback."""
        # Create initial feedback
        feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            routing_feedback="Initial feedback",
        )

        # Update feedback
        updated = feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=False,
            routing_feedback="Updated feedback",
        )

        assert updated.was_good_match is False
        assert updated.routing_feedback == "Updated feedback"

    def test_get_feedback(self, feedback_store, sample_task):
        """Test getting feedback."""
        feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
        )

        retrieved = feedback_store.get_feedback(sample_task.id)

        assert retrieved is not None
        assert retrieved.task_id == sample_task.id

    def test_get_feedback_not_found(self, feedback_store):
        """Test getting nonexistent feedback."""
        result = feedback_store.get_feedback("nonexistent")
        assert result is None

    def test_get_all_feedback(self, feedback_store, multiple_tasks):
        """Test getting all feedback."""
        # Create feedback for multiple tasks
        for i, task in enumerate(multiple_tasks):
            feedback_store.record_feedback(
                task_id=task.id,
                was_good_match=(i % 2 == 0),
            )

        all_feedback = feedback_store.get_all_feedback()
        assert len(all_feedback) == 5

    def test_get_all_feedback_filtered(self, feedback_store, multiple_tasks):
        """Test getting feedback filtered by match status."""
        for i, task in enumerate(multiple_tasks):
            feedback_store.record_feedback(
                task_id=task.id,
                was_good_match=(i % 2 == 0),
            )

        good_only = feedback_store.get_all_feedback(good_matches_only=True)
        bad_only = feedback_store.get_all_feedback(good_matches_only=False)

        assert len(good_only) == 3  # tasks 0, 2, 4
        assert len(bad_only) == 2  # tasks 1, 3

    def test_get_feedback_for_instance(self, feedback_store, multiple_tasks):
        """Test getting feedback for specific instance."""
        for task in multiple_tasks:
            feedback_store.record_feedback(
                task_id=task.id,
                was_good_match=True,
            )

        api_feedback = feedback_store.get_feedback_for_instance("api-instance")
        web_feedback = feedback_store.get_feedback_for_instance("web-instance")

        assert len(api_feedback) == 3
        assert len(web_feedback) == 2

    def test_get_misrouted_feedback(self, feedback_store, multiple_tasks):
        """Test getting misrouted feedback."""
        for i, task in enumerate(multiple_tasks):
            feedback_store.record_feedback(
                task_id=task.id,
                was_good_match=(i % 2 == 0),
            )

        misrouted = feedback_store.get_misrouted_feedback()
        assert len(misrouted) == 2

    def test_get_tasks_needing_feedback(self, db_session, feedback_store, multiple_tasks):
        """Test getting tasks without feedback."""
        # Give feedback to only some tasks
        feedback_store.record_feedback(
            task_id=multiple_tasks[0].id,
            was_good_match=True,
        )
        feedback_store.record_feedback(
            task_id=multiple_tasks[1].id,
            was_good_match=True,
        )

        needing = feedback_store.get_tasks_needing_feedback()

        # 3 tasks should need feedback
        assert len(needing) == 3
        assert all(t.id not in [multiple_tasks[0].id, multiple_tasks[1].id] for t in needing)

    def test_delete_feedback(self, feedback_store, sample_task):
        """Test deleting feedback."""
        feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
        )

        deleted = feedback_store.delete_feedback(sample_task.id)
        assert deleted is True

        # Verify deleted
        assert feedback_store.get_feedback(sample_task.id) is None

    def test_delete_nonexistent_feedback(self, feedback_store):
        """Test deleting nonexistent feedback."""
        deleted = feedback_store.delete_feedback("nonexistent")
        assert deleted is False

    def test_to_dict(self, feedback_store, sample_task):
        """Test feedback serialization."""
        feedback = feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            routing_feedback="Good routing",
            quality_score=4.5,
        )

        data = feedback_store.to_dict(feedback)

        assert data["task_id"] == sample_task.id
        assert data["was_good_match"] is True
        assert data["routing_feedback"] == "Good routing"
        assert data["quality_score"] == 4.5

    def test_feedback_updates_episode(self, db_session, feedback_store, episodic_store, sample_task):
        """Test that feedback updates linked episode."""
        # Create episode
        episode = episodic_store.record_episode(
            task=sample_task,
            chosen_instance="api-instance",
        )

        # Record feedback
        feedback_store.record_feedback(
            task_id=sample_task.id,
            was_good_match=True,
            actual_duration="2h",
            routing_feedback="Good choice",
        )

        # Check episode was updated
        updated_episode = episodic_store.get_episode(episode.id)
        assert updated_episode.outcome_success is True
        assert updated_episode.outcome_duration == "2h"


class TestFeedbackAnalytics:
    """Tests for FeedbackAnalytics."""

    @pytest.fixture
    def feedback_with_data(self, db_session, multiple_tasks):
        """Create feedback data for analytics."""
        store = FeedbackStore(db_session)

        for i, task in enumerate(multiple_tasks):
            store.record_feedback(
                task_id=task.id,
                was_good_match=(i < 3),
                should_have_routed_to="other-instance" if i >= 3 else None,
                complexity_rating=i + 1,
                quality_score=float(i + 1),
                required_rework=(i == 4),
                unexpected_blockers=["blocker"] if i == 4 else None,
                required_skills_not_tagged=["skill"] if i == 4 else None,
            )

        return store

    def test_get_routing_accuracy(self, db_session, feedback_with_data):
        """Test routing accuracy calculation."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_routing_accuracy()

        assert report.total_feedback == 5
        assert report.good_matches == 3
        assert report.bad_matches == 2
        assert report.accuracy_rate == 0.6

    def test_get_routing_accuracy_by_period(self, db_session, feedback_with_data):
        """Test routing accuracy with time filter."""
        analytics = FeedbackAnalytics(db_session)

        # Filter by recent period
        since = datetime.utcnow() - timedelta(hours=1)
        report = analytics.get_routing_accuracy(since=since)

        assert report.total_feedback == 5
        assert report.period_start == since

    def test_routing_accuracy_by_instance(self, db_session, feedback_with_data):
        """Test per-instance accuracy breakdown."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_routing_accuracy()

        # Should have breakdown by instance
        assert "api-instance" in report.by_instance or "web-instance" in report.by_instance

    def test_get_quality_report(self, db_session, feedback_with_data):
        """Test quality report generation."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_quality_report()

        assert report.total_tasks == 5
        assert report.average_quality_score > 0
        assert report.average_complexity > 0
        assert report.rework_rate == 0.2  # 1 out of 5
        assert report.tasks_with_blockers == 1
        assert report.missing_skills_count == 1

    def test_quality_by_complexity(self, db_session, feedback_with_data):
        """Test quality breakdown by complexity."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_quality_report()

        # Should have breakdown for each complexity level
        assert len(report.by_complexity) == 5
        assert 1 in report.by_complexity
        assert 5 in report.by_complexity

    def test_get_misrouting_patterns(self, db_session, feedback_with_data):
        """Test misrouting pattern analysis."""
        analytics = FeedbackAnalytics(db_session)

        patterns = analytics.get_misrouting_patterns()

        # Should identify patterns for bad matches
        assert len(patterns) > 0

    def test_get_summary(self, db_session, feedback_with_data):
        """Test summary report."""
        analytics = FeedbackAnalytics(db_session)

        summary = analytics.get_summary(days=30)

        assert "routing_accuracy" in summary
        assert "quality_metrics" in summary
        assert summary["period_days"] == 30

    def test_routing_accuracy_to_dict(self, db_session, feedback_with_data):
        """Test report serialization."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_routing_accuracy()
        data = report.to_dict()

        assert "total_feedback" in data
        assert "accuracy_rate" in data
        assert "common_misrouting_targets" in data

    def test_quality_report_to_dict(self, db_session, feedback_with_data):
        """Test quality report serialization."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_quality_report()
        data = report.to_dict()

        assert "total_tasks" in data
        assert "average_quality_score" in data
        assert "by_complexity" in data

    def test_empty_analytics(self, db_session):
        """Test analytics with no data."""
        analytics = FeedbackAnalytics(db_session)

        report = analytics.get_routing_accuracy()

        assert report.total_feedback == 0
        assert report.accuracy_rate == 0.0

        quality = analytics.get_quality_report()
        assert quality.total_tasks == 0
