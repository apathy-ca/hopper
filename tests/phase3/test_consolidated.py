"""
Tests for consolidated memory (pattern extraction and learning).
"""

import pytest
from datetime import datetime
from uuid import uuid4

from hopper.memory.consolidated import (
    RoutingPattern,
    ConsolidatedStore,
    PatternExtractor,
)
from hopper.memory.consolidated.extractor import PatternCandidate
from hopper.memory.episodic import EpisodicStore
from hopper.models import Task, TaskStatus


@pytest.fixture
def consolidated_store(db_session) -> ConsolidatedStore:
    """Create consolidated store for testing."""
    return ConsolidatedStore(db_session)


@pytest.fixture
def episodic_store(db_session) -> EpisodicStore:
    """Create episodic store for testing."""
    return EpisodicStore(db_session)


@pytest.fixture
def pattern_extractor(db_session, episodic_store, consolidated_store) -> PatternExtractor:
    """Create pattern extractor for testing."""
    return PatternExtractor(
        db_session,
        episodic_store=episodic_store,
        consolidated_store=consolidated_store,
        min_episodes=2,  # Lower for testing
        min_success_rate=0.5,
    )


@pytest.fixture
def sample_pattern(consolidated_store) -> RoutingPattern:
    """Create a sample pattern."""
    return consolidated_store.create_pattern(
        name="api-python-tasks",
        target_instance="api-instance",
        tag_criteria={"required": ["api", "python"], "optional": ["backend"]},
        text_criteria={"keywords": ["api", "endpoint"]},
        priority_criteria="high",
        description="Routes API Python tasks",
        confidence=0.75,
    )


class TestRoutingPattern:
    """Tests for RoutingPattern model."""

    def test_matches_task_with_required_tags(self, db_session, sample_pattern):
        """Test matching with required tags."""
        # All required tags present
        matches, score = sample_pattern.matches_task(
            tags={"api": True, "python": True, "backend": True},
            priority="high",
        )
        assert matches is True
        assert score > 0

    def test_matches_task_missing_required_tags(self, db_session, sample_pattern):
        """Test non-match when required tags are missing."""
        # Missing 'python' tag
        matches, score = sample_pattern.matches_task(
            tags={"api": True, "frontend": True},
            priority="high",
        )
        assert matches is False
        assert score == 0.0

    def test_matches_task_with_optional_tags(self, db_session, sample_pattern):
        """Test matching considers optional tags."""
        # Has required + optional
        matches1, score1 = sample_pattern.matches_task(
            tags={"api": True, "python": True, "backend": True},
        )

        # Has required only
        matches2, score2 = sample_pattern.matches_task(
            tags={"api": True, "python": True},
        )

        assert matches1 is True
        assert matches2 is True
        # Score with optional should be higher
        assert score1 >= score2

    def test_matches_task_with_priority(self, db_session, sample_pattern):
        """Test matching with priority criteria."""
        matches1, score1 = sample_pattern.matches_task(
            tags={"api": True, "python": True},
            priority="high",
        )

        matches2, score2 = sample_pattern.matches_task(
            tags={"api": True, "python": True},
            priority="low",
        )

        assert matches1 is True
        assert matches2 is True  # Still matches on tags
        # High priority should score higher
        assert score1 >= score2

    def test_record_usage_success(self, db_session, sample_pattern):
        """Test recording successful usage."""
        initial_count = sample_pattern.usage_count

        sample_pattern.record_usage(success=True)

        assert sample_pattern.usage_count == initial_count + 1
        assert sample_pattern.success_count == 1
        assert sample_pattern.last_used_at is not None

    def test_record_usage_failure(self, db_session, sample_pattern):
        """Test recording failed usage."""
        sample_pattern.record_usage(success=False)

        assert sample_pattern.failure_count == 1

    def test_success_rate(self, db_session, sample_pattern):
        """Test success rate calculation."""
        sample_pattern.success_count = 7
        sample_pattern.failure_count = 3

        assert sample_pattern.success_rate == 0.7

    def test_success_rate_zero_usage(self, db_session, sample_pattern):
        """Test success rate with no usage."""
        assert sample_pattern.success_rate == 0.0

    def test_to_dict(self, db_session, sample_pattern):
        """Test pattern serialization."""
        data = sample_pattern.to_dict()

        assert data["name"] == "api-python-tasks"
        assert data["target_instance"] == "api-instance"
        assert data["tag_criteria"]["required"] == ["api", "python"]
        assert data["confidence"] == 0.75


class TestConsolidatedStore:
    """Tests for ConsolidatedStore."""

    def test_create_pattern(self, consolidated_store):
        """Test creating a pattern."""
        pattern = consolidated_store.create_pattern(
            name="test-pattern",
            target_instance="test-instance",
            tag_criteria={"required": ["test"]},
            confidence=0.8,
        )

        assert pattern.id is not None
        assert pattern.name == "test-pattern"
        assert pattern.target_instance == "test-instance"
        assert pattern.confidence == 0.8
        assert pattern.is_active is True

    def test_get_pattern(self, consolidated_store, sample_pattern):
        """Test getting a pattern by ID."""
        retrieved = consolidated_store.get_pattern(sample_pattern.id)

        assert retrieved is not None
        assert retrieved.id == sample_pattern.id

    def test_get_pattern_not_found(self, consolidated_store):
        """Test getting nonexistent pattern."""
        result = consolidated_store.get_pattern("nonexistent")
        assert result is None

    def test_get_pattern_by_name(self, consolidated_store, sample_pattern):
        """Test getting pattern by name."""
        retrieved = consolidated_store.get_pattern_by_name("api-python-tasks")

        assert retrieved is not None
        assert retrieved.id == sample_pattern.id

    def test_get_patterns_for_instance(self, consolidated_store):
        """Test getting patterns for an instance."""
        # Create multiple patterns
        consolidated_store.create_pattern(
            name="pattern-1",
            target_instance="api-instance",
            confidence=0.9,
        )
        consolidated_store.create_pattern(
            name="pattern-2",
            target_instance="api-instance",
            confidence=0.8,
        )
        consolidated_store.create_pattern(
            name="pattern-3",
            target_instance="web-instance",
            confidence=0.7,
        )

        api_patterns = consolidated_store.get_patterns_for_instance("api-instance")

        assert len(api_patterns) == 2
        # Should be sorted by confidence
        assert api_patterns[0].confidence >= api_patterns[1].confidence

    def test_get_all_patterns(self, consolidated_store, sample_pattern):
        """Test getting all patterns."""
        patterns = consolidated_store.get_all_patterns()

        assert len(patterns) >= 1

    def test_find_matching_patterns(self, consolidated_store, sample_pattern):
        """Test finding matching patterns."""
        matches = consolidated_store.find_matching_patterns(
            tags={"api": True, "python": True},
            priority="high",
        )

        assert len(matches) >= 1
        pattern, score = matches[0]
        assert pattern.id == sample_pattern.id
        assert score > 0

    def test_find_matching_patterns_min_confidence(self, consolidated_store):
        """Test min_confidence filter."""
        # Create low confidence pattern
        consolidated_store.create_pattern(
            name="low-conf",
            target_instance="test",
            tag_criteria={"required": ["test"]},
            confidence=0.2,
        )

        matches = consolidated_store.find_matching_patterns(
            tags={"test": True},
            min_confidence=0.5,
        )

        # Low confidence pattern should be excluded
        assert all(p.confidence >= 0.5 for p, _ in matches)

    def test_update_pattern_confidence(self, consolidated_store, sample_pattern):
        """Test updating pattern confidence."""
        initial_usage = sample_pattern.usage_count

        updated = consolidated_store.update_pattern_confidence(
            sample_pattern.id,
            success=True,
        )

        assert updated.usage_count == initial_usage + 1

    def test_deactivate_pattern(self, consolidated_store, sample_pattern):
        """Test deactivating a pattern."""
        result = consolidated_store.deactivate_pattern(sample_pattern.id)

        assert result is True
        pattern = consolidated_store.get_pattern(sample_pattern.id)
        assert pattern.is_active is False

    def test_activate_pattern(self, consolidated_store, sample_pattern):
        """Test activating a pattern."""
        # First deactivate
        consolidated_store.deactivate_pattern(sample_pattern.id)

        # Then activate
        result = consolidated_store.activate_pattern(sample_pattern.id)

        assert result is True
        pattern = consolidated_store.get_pattern(sample_pattern.id)
        assert pattern.is_active is True

    def test_delete_pattern(self, consolidated_store, sample_pattern):
        """Test deleting a pattern."""
        pattern_id = sample_pattern.id

        result = consolidated_store.delete_pattern(pattern_id)

        assert result is True
        assert consolidated_store.get_pattern(pattern_id) is None

    def test_refine_pattern(self, consolidated_store, sample_pattern):
        """Test refining a pattern."""
        new_tags = {"required": ["api", "python", "async"]}

        updated = consolidated_store.refine_pattern(
            sample_pattern.id,
            new_tag_criteria=new_tags,
            new_confidence=0.85,
        )

        assert updated.tag_criteria == new_tags
        assert updated.confidence == 0.85
        assert updated.last_refined_at is not None

    def test_get_statistics(self, consolidated_store, sample_pattern):
        """Test getting statistics."""
        stats = consolidated_store.get_statistics()

        assert "total_patterns" in stats
        assert "active_patterns" in stats
        assert "by_type" in stats
        assert stats["total_patterns"] >= 1


class TestPatternExtractor:
    """Tests for PatternExtractor."""

    @pytest.fixture
    def tasks_with_episodes(self, db_session, episodic_store):
        """Create tasks with successful episodes."""
        tasks = []
        for i in range(5):
            task = Task(
                id=f"task-{uuid4().hex[:8]}",
                title=f"API endpoint task {i}",
                description=f"Implement API endpoint {i}",
                project="backend",
                status=TaskStatus.DONE,
                tags={"api": True, "python": True, "backend": True},
                created_at=datetime.utcnow(),
            )
            db_session.add(task)
            db_session.flush()
            tasks.append(task)

            # Create successful episode
            episode = episodic_store.record_episode(
                task=task,
                chosen_instance="api-instance",
                confidence=0.8,
            )
            episode.mark_success()

        return tasks

    def test_extract_patterns(self, pattern_extractor, tasks_with_episodes):
        """Test extracting patterns from episodes."""
        candidates = pattern_extractor.extract_patterns()

        assert len(candidates) >= 1
        candidate = candidates[0]
        assert candidate.target_instance == "api-instance"
        assert candidate.episode_count >= 2

    def test_extract_patterns_finds_common_tags(self, pattern_extractor, tasks_with_episodes):
        """Test that extracted patterns find common tags."""
        candidates = pattern_extractor.extract_patterns()

        # Should find api, python, backend as common tags
        candidate = candidates[0]
        required = candidate.tag_criteria.get("required", [])
        assert any(tag in required for tag in ["api", "python", "backend"])

    def test_create_patterns_from_candidates(self, pattern_extractor, consolidated_store):
        """Test creating patterns from candidates."""
        candidate = PatternCandidate(
            target_instance="test-instance",
            tag_criteria={"required": ["api", "python"]},
            text_criteria={"keywords": ["endpoint"]},
            priority_criteria="high",
            episode_count=5,
            success_rate=1.0,
            confidence=0.75,
            episode_ids=["ep-1", "ep-2"],
        )

        created = pattern_extractor.create_patterns_from_candidates([candidate])

        assert len(created) == 1
        pattern = created[0]
        assert pattern.target_instance == "test-instance"
        assert pattern.confidence == 0.75

    def test_run_consolidation(self, pattern_extractor, tasks_with_episodes):
        """Test running full consolidation."""
        result = pattern_extractor.run_consolidation()

        assert "candidates_found" in result
        assert "patterns_created" in result
        assert result["candidates_found"] >= 1

    def test_pattern_candidate_to_dict(self):
        """Test PatternCandidate serialization."""
        candidate = PatternCandidate(
            target_instance="test",
            tag_criteria={"required": ["api"]},
            text_criteria={},
            priority_criteria=None,
            episode_count=3,
            success_rate=0.9,
            confidence=0.7,
        )

        data = candidate.to_dict()

        assert data["target_instance"] == "test"
        assert data["episode_count"] == 3
        assert data["confidence"] == 0.7


class TestPatternMatching:
    """Tests for pattern matching scenarios."""

    def test_tag_pattern_matching(self, consolidated_store):
        """Test pure tag-based pattern matching."""
        pattern = consolidated_store.create_pattern(
            name="tag-only",
            target_instance="backend",
            tag_criteria={"required": ["database"], "optional": ["postgres", "mysql"]},
            pattern_type="tag",
            confidence=0.8,
        )

        # Perfect match
        matches1, score1 = pattern.matches_task(tags={"database": True, "postgres": True})
        assert matches1 is True

        # Missing required
        matches2, score2 = pattern.matches_task(tags={"api": True})
        assert matches2 is False

    def test_text_pattern_matching(self, consolidated_store):
        """Test pure text-based pattern matching."""
        pattern = consolidated_store.create_pattern(
            name="text-only",
            target_instance="backend",
            text_criteria={"keywords": ["database", "query", "optimize"]},
            pattern_type="text",
            confidence=0.7,
        )

        # Has keywords
        matches1, score1 = pattern.matches_task(title="Optimize database query performance")
        assert matches1 is True

        # No keywords
        matches2, score2 = pattern.matches_task(title="Build new frontend component")
        assert matches2 is False

    def test_combined_pattern_matching(self, consolidated_store):
        """Test combined tag and text pattern matching."""
        pattern = consolidated_store.create_pattern(
            name="combined",
            target_instance="backend",
            tag_criteria={"required": ["api"]},
            text_criteria={"keywords": ["endpoint"]},
            priority_criteria="high",
            pattern_type="combined",
            confidence=0.85,
        )

        # All criteria match
        matches, score = pattern.matches_task(
            tags={"api": True},
            title="Create new API endpoint",
            priority="high",
        )
        assert matches is True
        assert score > 0.5
