"""
Memory storage implementations for episodes, patterns, and feedback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from .markdown import MarkdownDocument, MarkdownStorage


# =============================================================================
# Episode Storage
# =============================================================================


@dataclass
class LocalEpisode:
    """Episode representation for local storage."""

    id: str
    task_id: str
    chosen_instance: str
    confidence: float
    strategy: str = "rules"
    pattern_id: str | None = None
    factors: dict[str, Any] = field(default_factory=dict)
    outcome_success: bool | None = None
    outcome_duration: str | None = None
    routed_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "chosen_instance": self.chosen_instance,
            "confidence": self.confidence,
            "strategy": self.strategy,
            "pattern_id": self.pattern_id,
            "factors": self.factors,
            "outcome_success": self.outcome_success,
            "outcome_duration": self.outcome_duration,
            "routed_at": self.routed_at.isoformat() if self.routed_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalEpisode":
        """Create from dict."""
        routed = data.get("routed_at")
        completed = data.get("completed_at")

        return cls(
            id=data["id"],
            task_id=data["task_id"],
            chosen_instance=data["chosen_instance"],
            confidence=data.get("confidence", 0.5),
            strategy=data.get("strategy", "rules"),
            pattern_id=data.get("pattern_id"),
            factors=data.get("factors", {}),
            outcome_success=data.get("outcome_success"),
            outcome_duration=data.get("outcome_duration"),
            routed_at=datetime.fromisoformat(routed) if isinstance(routed, str) else routed,
            completed_at=datetime.fromisoformat(completed) if isinstance(completed, str) else completed,
        )


class EpisodeMarkdownStore:
    """Episode storage using daily markdown files."""

    def __init__(self, storage: MarkdownStorage):
        """Initialize episode store."""
        self.storage = storage

    def _episode_path(self, date: datetime) -> Path:
        """Get path for episode file by date."""
        return self.storage.episodes_path / f"{date.strftime('%Y-%m-%d')}.md"

    def _load_day(self, date: datetime) -> tuple[dict[str, Any], list[LocalEpisode]]:
        """Load episodes for a day."""
        doc = self.storage.read_document(self._episode_path(date))
        if doc is None:
            return {}, []

        episodes = []
        for ep_data in doc.frontmatter.get("episodes", []):
            episodes.append(LocalEpisode.from_dict(ep_data))

        return doc.frontmatter, episodes

    def _save_day(
        self,
        date: datetime,
        meta: dict[str, Any],
        episodes: list[LocalEpisode],
    ) -> None:
        """Save episodes for a day."""
        # Update metadata
        meta["date"] = date.strftime("%Y-%m-%d")
        meta["total_episodes"] = len(episodes)
        meta["successful"] = len([e for e in episodes if e.outcome_success is True])
        meta["failed"] = len([e for e in episodes if e.outcome_success is False])
        meta["pending"] = len([e for e in episodes if e.outcome_success is None])
        meta["episodes"] = [e.to_dict() for e in episodes]

        # Build content summary
        content_lines = ["## Episodes\n"]
        for ep in episodes:
            time_str = ep.routed_at.strftime("%H:%M") if ep.routed_at else "??:??"
            outcome = "pending"
            if ep.outcome_success is True:
                outcome = "success"
            elif ep.outcome_success is False:
                outcome = "failure"

            content_lines.append(f"### {time_str} - {ep.task_id}\n")
            content_lines.append(f"- **Chosen:** {ep.chosen_instance}")
            content_lines.append(f"- **Confidence:** {ep.confidence:.2f}")
            content_lines.append(f"- **Strategy:** {ep.strategy}")
            if ep.pattern_id:
                content_lines.append(f"- **Pattern:** {ep.pattern_id}")
            content_lines.append(f"- **Outcome:** {outcome}")
            if ep.outcome_duration:
                content_lines.append(f"- **Duration:** {ep.outcome_duration}")
            content_lines.append("")

        doc = MarkdownDocument(
            frontmatter=meta,
            content="\n".join(content_lines),
        )
        self.storage.write_document(self._episode_path(date), doc)

    def record(
        self,
        task_id: str,
        chosen_instance: str,
        confidence: float,
        strategy: str = "rules",
        pattern_id: str | None = None,
        factors: dict[str, Any] | None = None,
    ) -> LocalEpisode:
        """Record a routing episode."""
        now = _utc_now()
        episode = LocalEpisode(
            id=f"ep-{uuid4().hex[:8]}",
            task_id=task_id,
            chosen_instance=chosen_instance,
            confidence=confidence,
            strategy=strategy,
            pattern_id=pattern_id,
            factors=factors or {},
            routed_at=now,
        )

        # Load existing episodes for today
        meta, episodes = self._load_day(now)
        episodes.append(episode)
        self._save_day(now, meta, episodes)

        return episode

    def get_for_task(self, task_id: str) -> LocalEpisode | None:
        """Get episode for a task (searches recent days)."""
        # Search last 30 days
        for days_ago in range(30):
            date = _utc_now() - timedelta(days=days_ago)
            _, episodes = self._load_day(date)
            for ep in episodes:
                if ep.task_id == task_id:
                    return ep
        return None

    def mark_outcome(
        self,
        task_id: str,
        success: bool,
        duration: str | None = None,
    ) -> LocalEpisode | None:
        """Mark episode outcome."""
        # Find and update the episode
        for days_ago in range(30):
            date = _utc_now() - timedelta(days=days_ago)
            meta, episodes = self._load_day(date)

            for i, ep in enumerate(episodes):
                if ep.task_id == task_id:
                    ep.outcome_success = success
                    ep.outcome_duration = duration
                    ep.completed_at = _utc_now()
                    episodes[i] = ep
                    self._save_day(date, meta, episodes)
                    return ep

        return None

    def list_recent(self, days: int = 7, limit: int = 100) -> list[LocalEpisode]:
        """List recent episodes."""
        all_episodes = []

        for days_ago in range(days):
            date = _utc_now() - timedelta(days=days_ago)
            _, episodes = self._load_day(date)
            all_episodes.extend(episodes)

            if len(all_episodes) >= limit:
                break

        # Sort by routed_at descending
        all_episodes.sort(key=lambda e: e.routed_at or datetime.min, reverse=True)
        return all_episodes[:limit]

    def get_statistics(self) -> dict[str, Any]:
        """Get episode statistics."""
        episodes = self.list_recent(days=30, limit=1000)

        total = len(episodes)
        successful = len([e for e in episodes if e.outcome_success is True])
        failed = len([e for e in episodes if e.outcome_success is False])
        pending = len([e for e in episodes if e.outcome_success is None])

        avg_confidence = 0.0
        if episodes:
            avg_confidence = sum(e.confidence for e in episodes) / len(episodes)

        return {
            "total_episodes": total,
            "successful": successful,
            "failed": failed,
            "pending": pending,
            "success_rate": successful / total if total > 0 else 0.0,
            "average_confidence": avg_confidence,
        }


# =============================================================================
# Pattern Storage
# =============================================================================


@dataclass
class LocalPattern:
    """Pattern representation for local storage."""

    id: str
    name: str
    pattern_type: str = "tag"  # tag, text, combined, priority
    target_instance: str = "local"
    description: str | None = None
    tag_criteria: dict[str, Any] = field(default_factory=dict)
    text_criteria: dict[str, Any] = field(default_factory=dict)
    priority_criteria: str | None = None
    confidence: float = 0.5
    usage_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    is_active: bool = True
    created_at: datetime | None = None
    last_used_at: datetime | None = None

    @classmethod
    def create(
        cls,
        name: str,
        target_instance: str = "local",
        pattern_type: str = "tag",
        description: str | None = None,
        tag_criteria: dict[str, Any] | None = None,
        text_criteria: dict[str, Any] | None = None,
        priority_criteria: str | None = None,
        confidence: float = 0.5,
    ) -> "LocalPattern":
        """Create a new pattern with generated ID."""
        return cls(
            id=f"pat-{uuid4().hex[:8]}",
            name=name,
            pattern_type=pattern_type,
            target_instance=target_instance,
            description=description,
            tag_criteria=tag_criteria or {},
            text_criteria=text_criteria or {},
            priority_criteria=priority_criteria,
            confidence=confidence,
            created_at=_utc_now(),
        )

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.usage_count == 0:
            return 0.0
        return self.success_count / self.usage_count

    def to_frontmatter(self) -> dict[str, Any]:
        """Convert to frontmatter dict."""
        return {
            "id": self.id,
            "name": self.name,
            "pattern_type": self.pattern_type,
            "target_instance": self.target_instance,
            "description": self.description,
            "tag_criteria": self.tag_criteria if self.tag_criteria else None,
            "text_criteria": self.text_criteria if self.text_criteria else None,
            "priority_criteria": self.priority_criteria,
            "confidence": self.confidence,
            "usage_count": self.usage_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
        }

    @classmethod
    def from_frontmatter(cls, fm: dict[str, Any], content: str = "") -> "LocalPattern":
        """Create from frontmatter dict."""
        created = fm.get("created_at")
        last_used = fm.get("last_used_at")

        return cls(
            id=fm["id"],
            name=fm.get("name", "Unnamed"),
            pattern_type=fm.get("pattern_type", "tag"),
            target_instance=fm.get("target_instance", "local"),
            description=fm.get("description") or content or None,
            tag_criteria=fm.get("tag_criteria", {}),
            text_criteria=fm.get("text_criteria", {}),
            priority_criteria=fm.get("priority_criteria"),
            confidence=fm.get("confidence", 0.5),
            usage_count=fm.get("usage_count", 0),
            success_count=fm.get("success_count", 0),
            failure_count=fm.get("failure_count", 0),
            is_active=fm.get("is_active", True),
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else created,
            last_used_at=datetime.fromisoformat(last_used) if isinstance(last_used, str) else last_used,
        )


class PatternMarkdownStore:
    """Pattern storage using markdown files."""

    def __init__(self, storage: MarkdownStorage):
        """Initialize pattern store."""
        self.storage = storage

    def _pattern_path(self, pattern_id: str) -> Path:
        """Get path for a pattern file."""
        return self.storage.patterns_path / f"{pattern_id}.md"

    def get(self, pattern_id: str) -> LocalPattern | None:
        """Get pattern by ID."""
        doc = self.storage.read_document(self._pattern_path(pattern_id))
        if doc is None:
            return None
        return LocalPattern.from_frontmatter(doc.frontmatter, doc.content)

    def save(self, pattern: LocalPattern) -> None:
        """Save pattern to markdown file."""
        # Build content with criteria details
        content_lines = []

        if pattern.tag_criteria:
            content_lines.append("## Tag Criteria\n")
            if pattern.tag_criteria.get("required"):
                content_lines.append("### Required")
                for tag in pattern.tag_criteria["required"]:
                    content_lines.append(f"- {tag}")
                content_lines.append("")
            if pattern.tag_criteria.get("optional"):
                content_lines.append("### Optional")
                for tag in pattern.tag_criteria["optional"]:
                    content_lines.append(f"- {tag}")
                content_lines.append("")

        if pattern.text_criteria:
            content_lines.append("## Text Criteria\n")
            if pattern.text_criteria.get("keywords"):
                content_lines.append("### Keywords")
                for kw in pattern.text_criteria["keywords"]:
                    content_lines.append(f"- {kw}")
                content_lines.append("")

        doc = MarkdownDocument(
            frontmatter=pattern.to_frontmatter(),
            content="\n".join(content_lines),
        )
        self.storage.write_document(self._pattern_path(pattern.id), doc)

    def delete(self, pattern_id: str) -> bool:
        """Delete pattern."""
        return self.storage.delete_file(self._pattern_path(pattern_id))

    def list(self, active_only: bool = True) -> list[LocalPattern]:
        """List patterns."""
        patterns = []

        for pattern_file in self.storage.list_files(self.storage.patterns_path):
            doc = self.storage.read_document(pattern_file)
            if doc is None:
                continue

            pattern = LocalPattern.from_frontmatter(doc.frontmatter, doc.content)

            if active_only and not pattern.is_active:
                continue

            patterns.append(pattern)

        # Sort by confidence descending
        patterns.sort(key=lambda p: p.confidence, reverse=True)
        return patterns

    def find_matching(
        self,
        tags: list[str] | None = None,
        text: str | None = None,
        priority: str | None = None,
    ) -> list[tuple[LocalPattern, float]]:
        """Find patterns matching criteria."""
        matches = []

        for pattern in self.list(active_only=True):
            score = self._calculate_match_score(pattern, tags, text, priority)
            if score > 0:
                matches.append((pattern, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def _calculate_match_score(
        self,
        pattern: LocalPattern,
        tags: list[str] | None,
        text: str | None,
        priority: str | None,
    ) -> float:
        """Calculate match score for a pattern."""
        score = 0.0

        # Tag matching
        if tags and pattern.tag_criteria:
            required = set(pattern.tag_criteria.get("required", []))
            optional = set(pattern.tag_criteria.get("optional", []))
            input_tags = set(tags)

            # All required must match
            if required and not required.issubset(input_tags):
                return 0.0  # Required tags missing

            # Score based on matches
            if required:
                score += 0.5  # Base score for required match
            if optional:
                optional_matches = len(optional & input_tags)
                score += 0.3 * (optional_matches / len(optional))

        # Text matching
        if text and pattern.text_criteria:
            keywords = pattern.text_criteria.get("keywords", [])
            text_lower = text.lower()
            keyword_matches = sum(1 for kw in keywords if kw.lower() in text_lower)
            if keywords:
                score += 0.2 * (keyword_matches / len(keywords))

        # Priority matching
        if priority and pattern.priority_criteria:
            if pattern.priority_criteria == priority:
                score += 0.2

        # Boost by pattern confidence
        score *= pattern.confidence

        return score

    def record_usage(self, pattern_id: str, success: bool) -> None:
        """Record pattern usage."""
        pattern = self.get(pattern_id)
        if pattern is None:
            return

        pattern.usage_count += 1
        if success:
            pattern.success_count += 1
        else:
            pattern.failure_count += 1

        pattern.last_used_at = _utc_now()

        # Adjust confidence based on outcome
        if pattern.usage_count >= 5:
            pattern.confidence = 0.3 + (0.7 * pattern.success_rate)

        self.save(pattern)

    def create(
        self,
        name: str,
        target_instance: str = "local",
        pattern_type: str = "tag",
        tag_criteria: dict[str, Any] | None = None,
        text_criteria: dict[str, Any] | None = None,
        priority_criteria: str | None = None,
        confidence: float = 0.5,
    ) -> LocalPattern:
        """Create a new pattern."""
        pattern = LocalPattern(
            id=f"pat-{uuid4().hex[:8]}",
            name=name,
            pattern_type=pattern_type,
            target_instance=target_instance,
            tag_criteria=tag_criteria or {},
            text_criteria=text_criteria or {},
            priority_criteria=priority_criteria,
            confidence=confidence,
            created_at=_utc_now(),
        )
        self.save(pattern)
        return pattern


# =============================================================================
# Feedback Storage
# =============================================================================


@dataclass
class LocalFeedback:
    """Feedback representation for local storage."""

    task_id: str
    was_good_match: bool
    id: str | None = None  # defaults to fb-{task_id}
    routing_feedback: str | None = None
    should_have_routed_to: str | None = None
    quality_score: float | None = None
    complexity_rating: int | None = None
    required_rework: bool | None = None
    notes: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        """Set default id if not provided."""
        if self.id is None:
            self.id = f"fb-{self.task_id}"

    def to_frontmatter(self) -> dict[str, Any]:
        """Convert to frontmatter dict."""
        return {
            "task_id": self.task_id,
            "was_good_match": self.was_good_match,
            "should_have_routed_to": self.should_have_routed_to,
            "quality_score": self.quality_score,
            "complexity_rating": self.complexity_rating,
            "required_rework": self.required_rework,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_frontmatter(cls, fm: dict[str, Any], content: str = "") -> "LocalFeedback":
        """Create from frontmatter dict."""
        created = fm.get("created_at")

        # Parse content for feedback and notes
        routing_feedback = None
        notes = None

        if content:
            sections = content.split("## Notes")
            if sections:
                routing_feedback = sections[0].replace("## Routing Feedback", "").strip()
                if len(sections) > 1:
                    notes = sections[1].strip()

        return cls(
            task_id=fm["task_id"],
            was_good_match=fm.get("was_good_match", True),
            routing_feedback=routing_feedback or fm.get("routing_feedback"),
            should_have_routed_to=fm.get("should_have_routed_to"),
            quality_score=fm.get("quality_score"),
            complexity_rating=fm.get("complexity_rating"),
            required_rework=fm.get("required_rework"),
            notes=notes or fm.get("notes"),
            created_at=datetime.fromisoformat(created) if isinstance(created, str) else created,
        )


class FeedbackMarkdownStore:
    """Feedback storage using markdown files."""

    def __init__(self, storage: MarkdownStorage):
        """Initialize feedback store."""
        self.storage = storage

    def _feedback_path(self, task_id: str) -> Path:
        """Get path for a feedback file."""
        return self.storage.feedback_path / f"{task_id}.md"

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
        """Save feedback for a task."""
        feedback = LocalFeedback(
            task_id=task_id,
            was_good_match=was_good_match,
            routing_feedback=routing_feedback,
            should_have_routed_to=should_have_routed_to,
            quality_score=quality_score,
            complexity_rating=complexity_rating,
            required_rework=required_rework,
            notes=notes,
            created_at=_utc_now(),
        )

        # Build content
        content_lines = []
        if routing_feedback:
            content_lines.append("## Routing Feedback\n")
            content_lines.append(routing_feedback)
            content_lines.append("")
        if notes:
            content_lines.append("## Notes\n")
            content_lines.append(notes)

        doc = MarkdownDocument(
            frontmatter=feedback.to_frontmatter(),
            content="\n".join(content_lines),
        )
        self.storage.write_document(self._feedback_path(task_id), doc)

        return feedback

    def get(self, task_id: str) -> LocalFeedback | None:
        """Get feedback for a task."""
        doc = self.storage.read_document(self._feedback_path(task_id))
        if doc is None:
            return None
        return LocalFeedback.from_frontmatter(doc.frontmatter, doc.content)

    def list(self, good_only: bool | None = None, limit: int = 100) -> list[LocalFeedback]:
        """List feedback records."""
        feedbacks = []

        for feedback_file in self.storage.list_files(self.storage.feedback_path):
            doc = self.storage.read_document(feedback_file)
            if doc is None:
                continue

            feedback = LocalFeedback.from_frontmatter(doc.frontmatter, doc.content)

            # Filter by good_only
            if good_only is True and not feedback.was_good_match:
                continue
            if good_only is False and feedback.was_good_match:
                continue

            feedbacks.append(feedback)

        # Sort by created_at descending
        feedbacks.sort(key=lambda f: f.created_at or datetime.min, reverse=True)
        return feedbacks[:limit]

    def get_accuracy_stats(self, days: int = 30) -> dict[str, Any]:
        """Get routing accuracy statistics."""
        cutoff = _utc_now() - timedelta(days=days)
        feedbacks = self.list(limit=1000)

        # Filter to recent
        recent = [f for f in feedbacks if f.created_at and f.created_at > cutoff]

        total = len(recent)
        good = len([f for f in recent if f.was_good_match])
        bad = len([f for f in recent if not f.was_good_match])

        # Quality stats
        quality_scores = [f.quality_score for f in recent if f.quality_score is not None]
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0.0

        # Misrouting targets
        misroutes: dict[str, int] = {}
        for f in recent:
            if not f.was_good_match and f.should_have_routed_to:
                target = f.should_have_routed_to
                misroutes[target] = misroutes.get(target, 0) + 1

        return {
            "total_feedback": total,
            "good_matches": good,
            "bad_matches": bad,
            "accuracy_rate": good / total if total > 0 else 0.0,
            "average_quality": avg_quality,
            "common_misrouting_targets": sorted(
                misroutes.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }


# Convenience aliases
EpisodeStore = EpisodeMarkdownStore
PatternStore = PatternMarkdownStore
FeedbackStore = FeedbackMarkdownStore
