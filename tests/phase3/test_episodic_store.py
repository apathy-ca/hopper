"""
Tests for Episodic Store implementation.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4

from hopper.memory.episodic import EpisodicStore, RoutingEpisode
from hopper.models import Task, TaskStatus, RoutingDecision


@pytest.fixture
def episodic_store(db_session) -> EpisodicStore:
    """Create an episodic store for testing."""
    return EpisodicStore(db_session)


@pytest.fixture
def task_for_episode(db_session) -> Task:
    """Create a task for episode testing."""
    task = Task(
        id=f"task-{uuid4().hex[:8]}",
        title="Test task for episode",
        description="A test task",
        project="test-project",
        status=TaskStatus.PENDING,
        priority="medium",
        tags={"python": True, "api": True},
        created_at=datetime.utcnow(),
    )
    db_session.add(task)
    db_session.flush()
    return task


@pytest.fixture
def routing_decision_for_episode(db_session, task_for_episode) -> RoutingDecision:
    """Create a routing decision for testing."""
    decision = RoutingDecision(
        task_id=task_for_episode.id,
        project=None,  # No FK constraint issues
        confidence=0.85,
        decided_at=datetime.utcnow(),
        decided_by="rules",
        reasoning="Matched by tags",
    )
    db_session.add(decision)
    db_session.flush()
    return decision


class TestRoutingEpisode:
    """Tests for RoutingEpisode model."""

    def test_mark_success(self, db_session, episodic_store, task_for_episode):
        """Test marking episode as successful."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
            confidence=0.9,
        )

        episode.mark_success(duration="30m", notes="Completed quickly")

        assert episode.outcome_success is True
        assert episode.completed_at is not None
        assert episode.outcome_duration == "30m"
        assert episode.outcome_notes == "Completed quickly"

    def test_mark_failure(self, db_session, episodic_store, task_for_episode):
        """Test marking episode as failed."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="wrong-project",
            confidence=0.5,
        )

        episode.mark_failure(notes="Wrong routing")

        assert episode.outcome_success is False
        assert episode.completed_at is not None
        assert episode.outcome_notes == "Wrong routing"

    def test_is_completed(self, db_session, episodic_store, task_for_episode):
        """Test is_completed property."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )

        assert episode.is_completed is False

        episode.mark_success()

        assert episode.is_completed is True

    def test_duration_seconds(self, db_session, episodic_store, task_for_episode):
        """Test duration calculation."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )

        assert episode.duration_seconds is None

        episode.completed_at = episode.routed_at + timedelta(minutes=5)

        assert episode.duration_seconds == 300.0

    def test_to_dict(self, db_session, episodic_store, task_for_episode):
        """Test serialization to dict."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
            confidence=0.85,
            reasoning="Matched by tags",
            strategy_used="rules",
        )

        data = episode.to_dict()

        assert data["task_id"] == task_for_episode.id
        assert data["chosen_instance"] == "api-project"
        assert data["confidence"] == 0.85
        assert data["reasoning"] == "Matched by tags"


class TestEpisodicStore:
    """Tests for EpisodicStore."""

    def test_record_episode(
        self, episodic_store, task_for_episode, routing_decision_for_episode
    ):
        """Test recording a new episode."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            decision=routing_decision_for_episode,
            chosen_instance="api-project",
            confidence=0.9,
            reasoning="Strong tag match",
            strategy_used="rules",
            available_instances=["api-project", "web-project"],
            decision_factors={"tag_match": 0.8, "priority": 0.1},
        )

        assert episode.id is not None
        assert episode.task_id == task_for_episode.id
        assert episode.decision_task_id == routing_decision_for_episode.task_id
        assert episode.chosen_instance == "api-project"
        assert episode.confidence == 0.9
        assert len(episode.available_instances) == 2

    def test_record_episode_creates_snapshot(self, episodic_store, task_for_episode):
        """Test that episode captures task snapshot."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )

        snapshot = episode.task_snapshot
        assert snapshot["id"] == task_for_episode.id
        assert snapshot["title"] == task_for_episode.title
        assert snapshot["priority"] == task_for_episode.priority
        assert "tags" in snapshot

    def test_record_outcome_success(self, episodic_store, task_for_episode):
        """Test recording successful outcome."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )

        updated = episodic_store.record_outcome(
            episode_id=episode.id,
            success=True,
            duration="1h",
            notes="Completed well",
        )

        assert updated.outcome_success is True
        assert updated.outcome_duration == "1h"
        assert updated.outcome_notes == "Completed well"

    def test_record_outcome_failure(self, episodic_store, task_for_episode):
        """Test recording failed outcome."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="wrong-project",
        )

        updated = episodic_store.record_outcome(
            episode_id=episode.id,
            success=False,
            notes="Had to re-route",
        )

        assert updated.outcome_success is False
        assert updated.outcome_notes == "Had to re-route"

    def test_get_episode(self, episodic_store, task_for_episode):
        """Test getting episode by ID."""
        episode = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )

        retrieved = episodic_store.get_episode(episode.id)

        assert retrieved is not None
        assert retrieved.id == episode.id

    def test_get_episode_not_found(self, episodic_store):
        """Test getting nonexistent episode."""
        result = episodic_store.get_episode("nonexistent")
        assert result is None

    def test_get_episodes_for_task(self, episodic_store, task_for_episode):
        """Test getting all episodes for a task."""
        # Create multiple episodes
        for _ in range(3):
            episodic_store.record_episode(
                task=task_for_episode,
                chosen_instance="api-project",
            )

        episodes = episodic_store.get_episodes_for_task(task_for_episode.id)

        assert len(episodes) == 3

    def test_get_latest_episode_for_task(self, db_session, episodic_store, task_for_episode):
        """Test getting most recent episode for a task."""
        # Create first episode
        first = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="first-project",
        )
        db_session.flush()

        # Create second episode (most recent)
        second = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="second-project",
        )
        db_session.flush()

        latest = episodic_store.get_latest_episode_for_task(task_for_episode.id)

        assert latest is not None
        assert latest.id == second.id
        assert latest.chosen_instance == "second-project"

    def test_get_episodes_for_instance(self, episodic_store, task_for_episode):
        """Test getting episodes for a specific instance."""
        # Create episodes for different instances
        ep1 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )
        ep1.mark_success()

        ep2 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="web-project",
        )
        ep2.mark_success()

        ep3 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )
        ep3.mark_success()

        api_episodes = episodic_store.get_episodes_for_instance("api-project")

        assert len(api_episodes) == 2

    def test_get_successful_episodes(self, episodic_store, task_for_episode):
        """Test getting successful episodes."""
        # Create success
        ep1 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )
        ep1.mark_success()

        # Create failure
        ep2 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="wrong-project",
        )
        ep2.mark_failure()

        # Create pending
        episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="new-project",
        )

        successful = episodic_store.get_successful_episodes()

        assert len(successful) == 1
        assert successful[0].outcome_success is True

    def test_get_failed_episodes(self, episodic_store, task_for_episode):
        """Test getting failed episodes."""
        ep1 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )
        ep1.mark_success()

        ep2 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="wrong-project",
        )
        ep2.mark_failure()

        failed = episodic_store.get_failed_episodes()

        assert len(failed) == 1
        assert failed[0].outcome_success is False

    def test_get_pending_episodes(self, episodic_store, task_for_episode):
        """Test getting pending episodes."""
        ep1 = episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="api-project",
        )
        ep1.mark_success()

        episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="pending-project",
        )

        pending = episodic_store.get_pending_episodes()

        assert len(pending) == 1
        assert pending[0].outcome_success is None

    def test_get_statistics(self, episodic_store, task_for_episode):
        """Test getting episode statistics."""
        # Create mixed episodes
        for _ in range(5):
            ep = episodic_store.record_episode(
                task=task_for_episode,
                chosen_instance="api-project",
                confidence=0.8,
            )
            ep.mark_success()

        for _ in range(2):
            ep = episodic_store.record_episode(
                task=task_for_episode,
                chosen_instance="wrong-project",
                confidence=0.4,
            )
            ep.mark_failure()

        episodic_store.record_episode(
            task=task_for_episode,
            chosen_instance="new-project",
            confidence=0.6,
        )

        stats = episodic_store.get_statistics()

        assert stats["total_episodes"] == 8
        assert stats["successful"] == 5
        assert stats["failed"] == 2
        assert stats["pending"] == 1
        # Success rate: 5 / (5+2) = 0.714...
        assert 0.71 < stats["success_rate"] < 0.72

    def test_find_similar_episodes(self, db_session, episodic_store):
        """Test finding episodes with similar tags."""
        # Create task with python tag
        task1 = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Python task",
            project="test",
            status=TaskStatus.PENDING,
            tags={"python": True, "api": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(task1)
        db_session.flush()

        ep1 = episodic_store.record_episode(
            task=task1,
            chosen_instance="python-project",
        )
        ep1.mark_success()

        # Create task with different tags
        task2 = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Frontend task",
            project="test",
            status=TaskStatus.PENDING,
            tags={"react": True, "frontend": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(task2)
        db_session.flush()

        ep2 = episodic_store.record_episode(
            task=task2,
            chosen_instance="frontend-project",
        )
        ep2.mark_success()

        # Find similar to python tasks
        similar = episodic_store.find_similar_episodes(["python", "backend"])

        assert len(similar) == 1
        assert similar[0].task_id == task1.id


class TestEpisodicStoreCleanup:
    """Tests for episodic store cleanup."""

    def test_cleanup_old_episodes(self, db_session, episodic_store):
        """Test cleaning up old episodes."""
        # Create old task
        old_task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Old task",
            project="test",
            status=TaskStatus.DONE,
            created_at=datetime.utcnow() - timedelta(days=100),
        )
        db_session.add(old_task)
        db_session.flush()

        # Create old episode
        old_episode = episodic_store.record_episode(
            task=old_task,
            chosen_instance="old-project",
        )
        # Manually set old date
        old_episode.routed_at = datetime.utcnow() - timedelta(days=100)
        db_session.flush()

        # Create recent task
        new_task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="New task",
            project="test",
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        db_session.add(new_task)
        db_session.flush()

        # Create recent episode
        episodic_store.record_episode(
            task=new_task,
            chosen_instance="new-project",
        )

        # Cleanup with 90 day retention
        deleted = episodic_store.cleanup_old_episodes(retention_days=90)

        assert deleted == 1

        # Verify old episode is gone
        assert episodic_store.get_episode(old_episode.id) is None
