"""
Rule definitions for the rules-based routing engine.

Supports multiple rule types:
- KeywordRule: Match based on keywords in title/description
- TagRule: Match based on tags
- PriorityRule: Match based on task priority
- ProjectRule: Match based on project attributes
- CompositeRule: Combine multiple rules (AND, OR, NOT)
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from hopper.intelligence.types import RoutingContext


class RuleType(Enum):
    """Types of routing rules."""

    KEYWORD = "keyword"
    TAG = "tag"
    PRIORITY = "priority"
    PROJECT = "project"
    COMPOSITE = "composite"
    PATTERN = "pattern"


class CompositeOperator(Enum):
    """Operators for composite rules."""

    AND = "and"  # All sub-rules must match
    OR = "or"  # At least one sub-rule must match
    NOT = "not"  # Sub-rule must NOT match


@dataclass
class RuleMatch:
    """
    Result of evaluating a rule against a task.

    Contains information about whether the rule matched and why.
    """

    rule_id: str
    matched: bool
    score: float = 0.0  # Match strength (0.0 to 1.0)
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class Rule(ABC):
    """
    Abstract base class for all routing rules.

    All rule types must implement the evaluate() method.
    """

    def __init__(
        self,
        rule_id: str,
        name: str,
        description: str,
        destination: str,
        weight: float = 1.0,
        enabled: bool = True,
        priority: int = 0,
        created_by: str | None = None,
    ):
        """
        Initialize a rule.

        Args:
            rule_id: Unique identifier for the rule.
            name: Human-readable name.
            description: Description of what the rule does.
            destination: Where to route if this rule matches.
            weight: Rule importance (0.0 to 1.0, default 1.0).
            enabled: Whether the rule is active.
            priority: Rule priority (higher evaluated first).
            created_by: Who created the rule.
        """
        self.rule_id = rule_id
        self.name = name
        self.description = description
        self.destination = destination
        self.weight = weight
        self.enabled = enabled
        self.priority = priority
        self.created_by = created_by

        # Timestamps
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()

        # Statistics
        self.times_matched = 0
        self.times_correct = 0
        self.times_incorrect = 0

    @abstractmethod
    async def evaluate(self, context: RoutingContext) -> RuleMatch:
        """
        Evaluate this rule against a routing context.

        Args:
            context: The routing context to evaluate.

        Returns:
            RuleMatch indicating if and how well the rule matched.
        """
        pass

    def success_rate(self) -> float | None:
        """
        Calculate the success rate of this rule based on feedback.

        Returns:
            Success rate (0.0 to 1.0) or None if no feedback yet.
        """
        total_feedback = self.times_correct + self.times_incorrect
        if total_feedback == 0:
            return None
        return self.times_correct / total_feedback

    def to_dict(self) -> dict[str, Any]:
        """
        Convert rule to dictionary for serialization.

        Returns:
            Dictionary representation of the rule.
        """
        return {
            "rule_id": self.rule_id,
            "rule_type": self.__class__.__name__,
            "name": self.name,
            "description": self.description,
            "destination": self.destination,
            "weight": self.weight,
            "enabled": self.enabled,
            "priority": self.priority,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "statistics": {
                "times_matched": self.times_matched,
                "times_correct": self.times_correct,
                "times_incorrect": self.times_incorrect,
                "success_rate": self.success_rate(),
            },
        }


class KeywordRule(Rule):
    """
    Rule that matches based on keywords in task title/description.

    Supports:
    - Case-insensitive matching
    - Multiple keywords (any match counts)
    - Whole word or substring matching
    - Weighted keywords
    """

    def __init__(
        self,
        keywords: list[str],
        case_sensitive: bool = False,
        whole_word: bool = False,
        keyword_weights: dict[str, float] | None = None,
        **kwargs,
    ):
        """
        Initialize a keyword rule.

        Args:
            keywords: List of keywords to match.
            case_sensitive: Whether matching is case-sensitive.
            whole_word: Whether to match whole words only.
            keyword_weights: Optional weights for specific keywords.
            **kwargs: Arguments for parent Rule class.
        """
        super().__init__(**kwargs)
        self.keywords = keywords
        self.case_sensitive = case_sensitive
        self.whole_word = whole_word
        self.keyword_weights = keyword_weights or {}

    async def evaluate(self, context: RoutingContext) -> RuleMatch:
        """Evaluate keyword matching."""
        text = f"{context.task_title} {context.task_description}"

        if not self.case_sensitive:
            text = text.lower()
            keywords = [k.lower() for k in self.keywords]
        else:
            keywords = self.keywords

        matched_keywords = []
        total_score = 0.0

        for keyword in keywords:
            if self.whole_word:
                # Match whole word using regex
                pattern = r"\b" + re.escape(keyword) + r"\b"
                if re.search(pattern, text):
                    matched_keywords.append(keyword)
                    weight = self.keyword_weights.get(keyword, 1.0)
                    total_score += weight
            else:
                # Substring match
                if keyword in text:
                    matched_keywords.append(keyword)
                    weight = self.keyword_weights.get(keyword, 1.0)
                    total_score += weight

        if matched_keywords:
            # Normalize score based on number of keywords
            score = min(total_score / len(self.keywords), 1.0) * self.weight

            return RuleMatch(
                rule_id=self.rule_id,
                matched=True,
                score=score,
                reason=f"Matched keywords: {', '.join(matched_keywords)}",
                metadata={"matched_keywords": matched_keywords},
            )

        return RuleMatch(
            rule_id=self.rule_id,
            matched=False,
            score=0.0,
            reason="No keywords matched",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result.update(
            {
                "keywords": self.keywords,
                "case_sensitive": self.case_sensitive,
                "whole_word": self.whole_word,
                "keyword_weights": self.keyword_weights,
            }
        )
        return result


class TagRule(Rule):
    """
    Rule that matches based on task tags.

    Supports:
    - Exact tag matching
    - Tag patterns (wildcards)
    - Required vs optional tags
    """

    def __init__(
        self,
        required_tags: list[str] | None = None,
        optional_tags: list[str] | None = None,
        tag_patterns: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize a tag rule.

        Args:
            required_tags: Tags that must all be present.
            optional_tags: Tags that boost score if present.
            tag_patterns: Regex patterns for tag matching.
            **kwargs: Arguments for parent Rule class.
        """
        super().__init__(**kwargs)
        self.required_tags = required_tags or []
        self.optional_tags = optional_tags or []
        self.tag_patterns = tag_patterns or []

    async def evaluate(self, context: RoutingContext) -> RuleMatch:
        """Evaluate tag matching."""
        task_tags = set(context.task_tags)

        # Check required tags
        required_set = set(self.required_tags)
        if required_set and not required_set.issubset(task_tags):
            return RuleMatch(
                rule_id=self.rule_id,
                matched=False,
                score=0.0,
                reason=f"Missing required tags: {required_set - task_tags}",
            )

        # Calculate score based on matched tags
        matched_tags = []
        score = 0.0

        # Required tags matched (if any)
        if required_set:
            matched_tags.extend(self.required_tags)
            score += 0.5  # Base score for meeting requirements

        # Optional tags
        optional_matched = task_tags.intersection(self.optional_tags)
        if optional_matched:
            matched_tags.extend(optional_matched)
            score += 0.3 * (len(optional_matched) / len(self.optional_tags))

        # Pattern matching
        for pattern in self.tag_patterns:
            regex = re.compile(pattern)
            pattern_matches = [tag for tag in task_tags if regex.match(tag)]
            if pattern_matches:
                matched_tags.extend(pattern_matches)
                score += 0.2

        # Normalize and apply weight
        score = min(score, 1.0) * self.weight

        if matched_tags or (not self.required_tags and not self.optional_tags):
            return RuleMatch(
                rule_id=self.rule_id,
                matched=True,
                score=score,
                reason=f"Matched tags: {', '.join(matched_tags)}",
                metadata={"matched_tags": matched_tags},
            )

        return RuleMatch(
            rule_id=self.rule_id,
            matched=False,
            score=0.0,
            reason="No tags matched",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result.update(
            {
                "required_tags": self.required_tags,
                "optional_tags": self.optional_tags,
                "tag_patterns": self.tag_patterns,
            }
        )
        return result


class PriorityRule(Rule):
    """
    Rule that matches based on task priority.

    Routes high-priority tasks to specific destinations.
    """

    def __init__(
        self,
        min_priority: str | None = None,
        max_priority: str | None = None,
        priorities: list[str] | None = None,
        **kwargs,
    ):
        """
        Initialize a priority rule.

        Args:
            min_priority: Minimum priority level (inclusive).
            max_priority: Maximum priority level (inclusive).
            priorities: Exact priority values to match.
            **kwargs: Arguments for parent Rule class.
        """
        super().__init__(**kwargs)
        self.min_priority = min_priority
        self.max_priority = max_priority
        self.priorities = priorities or []

        # Priority ordering (lower index = higher priority)
        self._priority_order = ["critical", "high", "medium", "low"]

    async def evaluate(self, context: RoutingContext) -> RuleMatch:
        """Evaluate priority matching."""
        task_priority = context.task_priority

        if not task_priority:
            return RuleMatch(
                rule_id=self.rule_id,
                matched=False,
                score=0.0,
                reason="Task has no priority set",
            )

        # Check exact matches first
        if self.priorities and task_priority in self.priorities:
            return RuleMatch(
                rule_id=self.rule_id,
                matched=True,
                score=1.0 * self.weight,
                reason=f"Exact priority match: {task_priority}",
                metadata={"priority": task_priority},
            )

        # Check range
        if self.min_priority or self.max_priority:
            try:
                task_idx = self._priority_order.index(task_priority)

                min_ok = True
                max_ok = True

                if self.min_priority:
                    min_idx = self._priority_order.index(self.min_priority)
                    min_ok = task_idx <= min_idx  # Lower index = higher priority

                if self.max_priority:
                    max_idx = self._priority_order.index(self.max_priority)
                    max_ok = task_idx >= max_idx

                if min_ok and max_ok:
                    return RuleMatch(
                        rule_id=self.rule_id,
                        matched=True,
                        score=0.8 * self.weight,
                        reason=f"Priority {task_priority} in range",
                        metadata={"priority": task_priority},
                    )

            except ValueError:
                # Unknown priority value
                pass

        return RuleMatch(
            rule_id=self.rule_id,
            matched=False,
            score=0.0,
            reason=f"Priority {task_priority} not matched",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result.update(
            {
                "min_priority": self.min_priority,
                "max_priority": self.max_priority,
                "priorities": self.priorities,
            }
        )
        return result


class CompositeRule(Rule):
    """
    Rule that combines multiple rules with logical operators.

    Supports AND, OR, and NOT operations on sub-rules.
    """

    def __init__(
        self,
        operator: CompositeOperator,
        sub_rules: list[Rule],
        **kwargs,
    ):
        """
        Initialize a composite rule.

        Args:
            operator: Logical operator (AND, OR, NOT).
            sub_rules: List of rules to combine.
            **kwargs: Arguments for parent Rule class.
        """
        super().__init__(**kwargs)
        self.operator = operator
        self.sub_rules = sub_rules

        if operator == CompositeOperator.NOT and len(sub_rules) != 1:
            raise ValueError("NOT operator requires exactly one sub-rule")

    async def evaluate(self, context: RoutingContext) -> RuleMatch:
        """Evaluate composite rule."""
        # Evaluate all sub-rules
        sub_matches = []
        for rule in self.sub_rules:
            match = await rule.evaluate(context)
            sub_matches.append(match)

        # Apply operator
        if self.operator == CompositeOperator.AND:
            # All must match
            if all(m.matched for m in sub_matches):
                avg_score = sum(m.score for m in sub_matches) / len(sub_matches)
                reasons = [m.reason for m in sub_matches]

                return RuleMatch(
                    rule_id=self.rule_id,
                    matched=True,
                    score=avg_score * self.weight,
                    reason=f"All conditions met: {'; '.join(reasons)}",
                    metadata={"sub_matches": [m.metadata for m in sub_matches]},
                )

            return RuleMatch(
                rule_id=self.rule_id,
                matched=False,
                score=0.0,
                reason="Not all AND conditions met",
            )

        elif self.operator == CompositeOperator.OR:
            # At least one must match
            matched = [m for m in sub_matches if m.matched]

            if matched:
                max_score = max(m.score for m in matched)
                reasons = [m.reason for m in matched]

                return RuleMatch(
                    rule_id=self.rule_id,
                    matched=True,
                    score=max_score * self.weight,
                    reason=f"Matched: {reasons[0]}",  # Show best match
                    metadata={"sub_matches": [m.metadata for m in matched]},
                )

            return RuleMatch(
                rule_id=self.rule_id,
                matched=False,
                score=0.0,
                reason="No OR conditions met",
            )

        elif self.operator == CompositeOperator.NOT:
            # Sub-rule must NOT match
            sub_match = sub_matches[0]

            if not sub_match.matched:
                return RuleMatch(
                    rule_id=self.rule_id,
                    matched=True,
                    score=self.weight,
                    reason=f"NOT condition met: {sub_match.reason}",
                    metadata={"negated": sub_match.metadata},
                )

            return RuleMatch(
                rule_id=self.rule_id,
                matched=False,
                score=0.0,
                reason=f"NOT condition failed: rule matched ({sub_match.reason})",
            )

        return RuleMatch(
            rule_id=self.rule_id,
            matched=False,
            score=0.0,
            reason="Unknown operator",
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = super().to_dict()
        result.update(
            {
                "operator": self.operator.value,
                "sub_rules": [r.to_dict() for r in self.sub_rules],
            }
        )
        return result
