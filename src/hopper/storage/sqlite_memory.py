"""
SQLite-backed memory stores for Hopper (episode, pattern, feedback).

Episode and Pattern stores delegate to their Markdown counterparts — those
tables don't yet have SQL equivalents.  FeedbackSQLiteStore is a real
implementation against the existing ``task_feedback`` table.

This module exists so LocalClient can construct a consistent set of stores
regardless of which backend is active.  Episode/Pattern will move to SQL
in a later phase once the tables are defined.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from .memory import (
    EpisodeMarkdownStore,
    LocalFeedback,
    PatternMarkdownStore,
)

if TYPE_CHECKING:
    from .sqlite import SQLiteStorage

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Episode — delegates to markdown (no SQL table yet)
# ---------------------------------------------------------------------------


class EpisodeSQLiteStore(EpisodeMarkdownStore):
    """Episode store that uses the markdown implementation for now.

    SQL-backed episodes will be added when the episodes table lands.
    The markdown delegate needs a MarkdownStorage instance passed in.
    """

    # Inherits everything from EpisodeMarkdownStore unchanged.
    pass


# ---------------------------------------------------------------------------
# Pattern — delegates to markdown (no SQL table yet)
# ---------------------------------------------------------------------------


class PatternSQLiteStore(PatternMarkdownStore):
    """Pattern store that uses the markdown implementation for now.

    SQL-backed patterns will be added when the patterns table lands.
    """

    pass


# ---------------------------------------------------------------------------
# Feedback — real SQL implementation
# ---------------------------------------------------------------------------


class FeedbackSQLiteStore:
    """Feedback store backed by the ``task_feedback`` SQL table.

    The ``task_feedback`` table (created in migration 233e207e2773) maps
    one-to-one with LocalFeedback.  This store reads and writes it directly
    via raw SQL to avoid importing the full ORM stack here.
    """

    def __init__(self, storage: SQLiteStorage):
        self._storage = storage

    # ------------------------------------------------------------------
    # FeedbackStore protocol
    # ------------------------------------------------------------------

    def save(
        self,
        task_id: str,
        was_good_match: bool,
        routing_feedback: str | None = None,
        should_have_routed_to: str | None = None,
        quality_score: float | None = None,
        complexity_rating: int | None = None,
        required_rework: bool | None = None,
        notes: str | None = None,
    ) -> LocalFeedback:
        """Upsert feedback for a task."""
        from sqlalchemy import text

        now = _utc_now()
        fb_id = f"f{task_id}"

        upsert_sql = text("""
            INSERT INTO task_feedback (
                task_id, was_good_match, routing_feedback, should_have_routed_to,
                quality_score, complexity_rating, required_rework, notes, created_at
            ) VALUES (
                :task_id, :was_good_match, :routing_feedback, :should_have_routed_to,
                :quality_score, :complexity_rating, :required_rework, :notes, :created_at
            )
            ON CONFLICT(task_id) DO UPDATE SET
                was_good_match = excluded.was_good_match,
                routing_feedback = excluded.routing_feedback,
                should_have_routed_to = excluded.should_have_routed_to,
                quality_score = excluded.quality_score,
                complexity_rating = excluded.complexity_rating,
                required_rework = excluded.required_rework,
                notes = excluded.notes
        """)

        with self._storage.session() as session:
            session.execute(
                upsert_sql,
                {
                    "task_id": task_id,
                    "was_good_match": was_good_match,
                    "routing_feedback": routing_feedback,
                    "should_have_routed_to": should_have_routed_to,
                    "quality_score": quality_score,
                    "complexity_rating": complexity_rating,
                    "required_rework": required_rework,
                    "notes": notes,
                    "created_at": now,
                },
            )
            session.commit()

        return LocalFeedback(
            id=fb_id,
            task_id=task_id,
            was_good_match=was_good_match,
            routing_feedback=routing_feedback,
            should_have_routed_to=should_have_routed_to,
            quality_score=quality_score,
            complexity_rating=complexity_rating,
            required_rework=required_rework,
            notes=notes,
            created_at=now,
        )

    def get(self, task_id: str) -> LocalFeedback | None:
        """Retrieve feedback for a task."""
        from sqlalchemy import text

        sql = text("""
            SELECT task_id, was_good_match, routing_feedback, should_have_routed_to,
                   quality_score, complexity_rating, required_rework, notes, created_at
            FROM task_feedback WHERE task_id = :task_id
        """)

        with self._storage.session() as session:
            row = session.execute(sql, {"task_id": task_id}).mappings().first()

        if row is None:
            return None

        return self._row_to_feedback(row)

    def list(self, good_only: bool | None = None, limit: int = 100) -> list[LocalFeedback]:
        """List feedback records."""
        from sqlalchemy import text

        where = ""
        if good_only is True:
            where = "WHERE was_good_match = 1"
        elif good_only is False:
            where = "WHERE was_good_match = 0"

        # `where` is one of three string literals above, never user input
        sql = text(f"""
            SELECT task_id, was_good_match, routing_feedback, should_have_routed_to,
                   quality_score, complexity_rating, required_rework, notes, created_at
            FROM task_feedback {where}
            ORDER BY created_at DESC LIMIT :limit
        """)  # nosec B608

        with self._storage.session() as session:
            rows = session.execute(sql, {"limit": limit}).mappings().all()

        return [self._row_to_feedback(r) for r in rows]

    def get_accuracy_stats(self, days: int = 30) -> dict[str, Any]:
        """Summarise routing accuracy over the given window."""
        from sqlalchemy import text

        cutoff = _utc_now() - timedelta(days=days)

        sql = text("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN was_good_match = 1 THEN 1 ELSE 0 END) AS good,
                AVG(quality_score) AS avg_quality,
                SUM(CASE WHEN required_rework = 1 THEN 1 ELSE 0 END) AS rework_count
            FROM task_feedback
            WHERE created_at >= :cutoff
        """)

        with self._storage.session() as session:
            row = session.execute(sql, {"cutoff": cutoff}).mappings().first()

        if row is None or row["total"] == 0:
            return {"total": 0, "accuracy": 0.0, "avg_quality": None, "rework_rate": 0.0}

        total = row["total"]
        good = row["good"] or 0
        return {
            "total": total,
            "accuracy": good / total,
            "avg_quality": row["avg_quality"],
            "rework_rate": (row["rework_count"] or 0) / total,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _row_to_feedback(self, row: Any) -> LocalFeedback:
        created = row["created_at"]
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        if isinstance(created, datetime) and created.tzinfo is None:
            created = created.replace(tzinfo=UTC)

        return LocalFeedback(
            id=f"f{row['task_id']}",
            task_id=row["task_id"],
            was_good_match=bool(row["was_good_match"]),
            routing_feedback=row["routing_feedback"],
            should_have_routed_to=row["should_have_routed_to"],
            quality_score=row["quality_score"],
            complexity_rating=row["complexity_rating"],
            required_rework=row["required_rework"],
            notes=row["notes"],
            created_at=created,
        )
