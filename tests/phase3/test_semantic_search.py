"""
Tests for semantic search functionality.
"""

import pytest
from datetime import datetime
from uuid import uuid4

from hopper.memory.search import TaskSimilarity, SimilarityResult, TaskSearcher
from hopper.models import Task, TaskStatus


class TestTaskSimilarity:
    """Tests for TaskSimilarity class."""

    def test_tokenize_basic(self):
        """Test basic tokenization."""
        sim = TaskSimilarity()
        tokens = sim.tokenize("Hello world this is a test")

        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        # Stop words should be removed
        assert "this" not in tokens
        assert "is" not in tokens
        assert "a" not in tokens

    def test_tokenize_code_terms(self):
        """Test tokenization of code-like terms."""
        sim = TaskSimilarity()
        tokens = sim.tokenize("Fix bug in api-endpoint handler_function")

        assert "fix" in tokens
        assert "bug" in tokens
        assert "api-endpoint" in tokens
        assert "handler_function" in tokens

    def test_tokenize_empty_string(self):
        """Test tokenization of empty string."""
        sim = TaskSimilarity()
        tokens = sim.tokenize("")
        assert tokens == []

    def test_compute_tf(self):
        """Test term frequency calculation."""
        sim = TaskSimilarity()
        tokens = ["api", "test", "api", "endpoint"]

        tf = sim.compute_tf(tokens)

        assert tf["api"] > tf["test"]  # api appears twice
        assert tf["test"] == tf["endpoint"]  # both appear once

    def test_add_and_find_similar(self):
        """Test adding documents and finding similar."""
        sim = TaskSimilarity()

        # Add documents
        sim.add_document("task-1", "Fix API authentication bug", {"api": True, "auth": True})
        sim.add_document("task-2", "Add API rate limiting feature", {"api": True, "feature": True})
        sim.add_document("task-3", "Update frontend styling", {"frontend": True, "css": True})

        # Search for API-related
        results = sim.find_similar("API authentication issue", {"api": True})

        assert len(results) > 0
        assert results[0].task_id == "task-1"  # Most similar

    def test_find_similar_with_tags_only(self):
        """Test finding similar using only tags."""
        sim = TaskSimilarity(text_weight=0.0, tag_weight=1.0)

        sim.add_document("task-1", "Some text", {"python": True, "backend": True})
        sim.add_document("task-2", "Other text", {"python": True, "frontend": True})
        sim.add_document("task-3", "More text", {"javascript": True})

        results = sim.find_similar("query", {"python": True, "backend": True})

        assert len(results) > 0
        assert results[0].task_id == "task-1"

    def test_find_similar_with_text_only(self):
        """Test finding similar using only text."""
        sim = TaskSimilarity(text_weight=1.0, tag_weight=0.0)

        sim.add_document("task-1", "Python backend API development")
        sim.add_document("task-2", "JavaScript frontend development")
        sim.add_document("task-3", "Database optimization")

        results = sim.find_similar("Python API backend")

        assert len(results) > 0
        assert results[0].task_id == "task-1"

    def test_find_similar_min_score(self):
        """Test minimum score filter."""
        sim = TaskSimilarity()

        sim.add_document("task-1", "API authentication")
        sim.add_document("task-2", "Completely unrelated task")

        results = sim.find_similar("API auth", min_score=0.5)

        # Only high-scoring results
        for r in results:
            assert r.score >= 0.5

    def test_find_similar_exclude_ids(self):
        """Test excluding specific IDs."""
        sim = TaskSimilarity()

        sim.add_document("task-1", "API feature")
        sim.add_document("task-2", "API enhancement")

        results = sim.find_similar("API", exclude_ids={"task-1"})

        assert all(r.task_id != "task-1" for r in results)

    def test_remove_document(self):
        """Test removing a document."""
        sim = TaskSimilarity()

        sim.add_document("task-1", "API feature")
        sim.add_document("task-2", "API enhancement")

        assert sim.get_corpus_size() == 2

        removed = sim.remove_document("task-1")
        assert removed is True
        assert sim.get_corpus_size() == 1

        results = sim.find_similar("API")
        assert all(r.task_id != "task-1" for r in results)

    def test_remove_nonexistent_document(self):
        """Test removing nonexistent document."""
        sim = TaskSimilarity()

        removed = sim.remove_document("nonexistent")
        assert removed is False

    def test_clear(self):
        """Test clearing the corpus."""
        sim = TaskSimilarity()

        sim.add_document("task-1", "API feature")
        sim.add_document("task-2", "API enhancement")

        sim.clear()

        assert sim.get_corpus_size() == 0

    def test_cosine_similarity(self):
        """Test cosine similarity calculation."""
        sim = TaskSimilarity()

        vec1 = {"a": 1.0, "b": 1.0}
        vec2 = {"a": 1.0, "b": 1.0}
        vec3 = {"c": 1.0, "d": 1.0}

        # Identical vectors
        assert sim.cosine_similarity(vec1, vec2) == pytest.approx(1.0)

        # No overlap
        assert sim.cosine_similarity(vec1, vec3) == 0.0

    def test_jaccard_similarity(self):
        """Test Jaccard similarity calculation."""
        sim = TaskSimilarity()

        set1 = {"a", "b", "c"}
        set2 = {"a", "b", "d"}
        set3 = {"x", "y", "z"}

        # 2 common out of 4 unique
        assert sim.jaccard_similarity(set1, set2) == pytest.approx(0.5)

        # No overlap
        assert sim.jaccard_similarity(set1, set3) == 0.0

        # Identical
        assert sim.jaccard_similarity(set1, set1) == pytest.approx(1.0)

    def test_similarity_result_to_dict(self):
        """Test SimilarityResult serialization."""
        result = SimilarityResult(
            task_id="task-1",
            score=0.85,
            text_score=0.7,
            tag_score=0.9,
            metadata={"source": "test"},
        )

        data = result.to_dict()

        assert data["task_id"] == "task-1"
        assert data["score"] == 0.85
        assert data["text_score"] == 0.7
        assert data["tag_score"] == 0.9
        assert data["metadata"]["source"] == "test"


class TestTaskSearcher:
    """Tests for TaskSearcher class."""

    @pytest.fixture
    def sample_tasks(self, db_session):
        """Create sample tasks for testing."""
        tasks = [
            Task(
                id=f"task-{uuid4().hex[:8]}",
                title="Fix API authentication bug",
                description="Users cannot login",
                project="backend",
                status=TaskStatus.PENDING,
                tags={"api": True, "auth": True, "bug": True},
                created_at=datetime.utcnow(),
            ),
            Task(
                id=f"task-{uuid4().hex[:8]}",
                title="Add API rate limiting",
                description="Implement rate limiting for API endpoints",
                project="backend",
                status=TaskStatus.DONE,
                tags={"api": True, "feature": True},
                created_at=datetime.utcnow(),
            ),
            Task(
                id=f"task-{uuid4().hex[:8]}",
                title="Update homepage styling",
                description="Redesign the homepage layout",
                project="frontend",
                status=TaskStatus.PENDING,
                tags={"frontend": True, "css": True, "ui": True},
                created_at=datetime.utcnow(),
            ),
            Task(
                id=f"task-{uuid4().hex[:8]}",
                title="Database query optimization",
                description="Optimize slow database queries",
                project="backend",
                status=TaskStatus.IN_PROGRESS,
                tags={"database": True, "performance": True},
                created_at=datetime.utcnow(),
            ),
        ]

        for task in tasks:
            db_session.add(task)
        db_session.flush()

        return tasks

    def test_index_tasks(self, db_session, sample_tasks):
        """Test indexing tasks from database."""
        searcher = TaskSearcher(db_session)

        count = searcher.index_tasks()

        assert count == len(sample_tasks)
        assert searcher.get_index_size() == len(sample_tasks)

    def test_search_by_text(self, db_session, sample_tasks):
        """Test searching by text."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        results = searcher.search("API authentication")

        assert len(results) > 0
        # First result should be the auth bug task
        assert "auth" in results[0].tags or "api" in results[0].tags

    def test_search_by_tags(self, db_session, sample_tasks):
        """Test searching by tags."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        results = searcher.search("", tags={"frontend": True, "css": True})

        assert len(results) > 0
        # First result should be frontend task
        assert results[0].tags.get("frontend") or results[0].tags.get("css")

    def test_search_by_task(self, db_session, sample_tasks):
        """Test searching by similar task."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        # Search for tasks similar to the first one
        results = searcher.search_by_task(sample_tasks[0])

        assert len(results) > 0
        # Should not include itself
        assert all(r.task_id != sample_tasks[0].id for r in results)

    def test_search_with_status_filter(self, db_session, sample_tasks):
        """Test search with status filter."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        results = searcher.search(
            "API",
            status_filter=[TaskStatus.PENDING],
        )

        for r in results:
            assert r.status == "pending"

    def test_search_exclude_ids(self, db_session, sample_tasks):
        """Test search excluding specific IDs."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        exclude = {sample_tasks[0].id, sample_tasks[1].id}
        results = searcher.search("API", exclude_ids=exclude)

        for r in results:
            assert r.task_id not in exclude

    def test_add_task_to_index(self, db_session, sample_tasks):
        """Test adding a single task to index."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        initial_size = searcher.get_index_size()

        # Create new task
        new_task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="New feature request",
            description="A brand new feature",
            project="backend",
            status=TaskStatus.PENDING,
            tags={"feature": True},
            created_at=datetime.utcnow(),
        )
        db_session.add(new_task)
        db_session.flush()

        searcher.add_task(new_task)

        assert searcher.get_index_size() == initial_size + 1

    def test_remove_task_from_index(self, db_session, sample_tasks):
        """Test removing a task from index."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        initial_size = searcher.get_index_size()

        removed = searcher.remove_task(sample_tasks[0].id)

        assert removed is True
        assert searcher.get_index_size() == initial_size - 1

    def test_clear_index(self, db_session, sample_tasks):
        """Test clearing the index."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        searcher.clear_index()

        assert searcher.get_index_size() == 0

    def test_get_statistics(self, db_session, sample_tasks):
        """Test getting searcher statistics."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        stats = searcher.get_statistics()

        assert stats["indexed"] is True
        assert stats["corpus_size"] == len(sample_tasks)
        assert "text_weight" in stats
        assert "tag_weight" in stats
        assert "unique_terms" in stats

    def test_search_result_to_dict(self, db_session, sample_tasks):
        """Test SearchResult serialization."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        results = searcher.search("API")
        if results:
            data = results[0].to_dict()

            assert "task_id" in data
            assert "title" in data
            assert "similarity_score" in data
            assert "text_score" in data
            assert "tag_score" in data

    def test_lazy_indexing(self, db_session, sample_tasks):
        """Test that search triggers indexing if needed."""
        searcher = TaskSearcher(db_session)

        # Search without explicit indexing
        results = searcher.search("API")

        # Should have indexed automatically
        assert searcher.get_index_size() > 0

    def test_force_reindex(self, db_session, sample_tasks):
        """Test force re-indexing."""
        searcher = TaskSearcher(db_session)
        searcher.index_tasks()

        # Add a task directly to DB without adding to index
        new_task = Task(
            id=f"task-{uuid4().hex[:8]}",
            title="Unindexed task",
            description="This task was added after indexing",
            project="backend",
            status=TaskStatus.PENDING,
            created_at=datetime.utcnow(),
        )
        db_session.add(new_task)
        db_session.flush()

        # Normal index should not pick it up
        count1 = searcher.index_tasks()
        assert count1 == len(sample_tasks)

        # Force reindex should
        count2 = searcher.index_tasks(force=True)
        assert count2 == len(sample_tasks) + 1
