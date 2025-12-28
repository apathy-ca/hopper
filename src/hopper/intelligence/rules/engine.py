"""
Rules-based routing intelligence implementation.

Fast, deterministic routing using keyword matching, tag matching,
and pattern-based rules.
"""

import logging
from typing import Any
from uuid import uuid4

from hopper.intelligence.base import BaseIntelligence, RoutingError
from hopper.intelligence.rules.rule import Rule, RuleMatch
from hopper.intelligence.rules.scoring import (
    aggregate_scores,
)
from hopper.intelligence.types import (
    DecisionStrategy,
    RoutingContext,
    RoutingDecision,
)

logger = logging.getLogger(__name__)


class RulesIntelligence(BaseIntelligence):
    """
    Rules-based routing intelligence.

    Fast, deterministic routing using configurable rules for keyword matching,
    tag matching, priority routing, and composite rule logic.

    Characteristics:
    - Fast (< 10ms decisions)
    - Deterministic and reproducible
    - No external dependencies
    - Easy to debug and understand
    - Human-readable rule configuration
    """

    def __init__(
        self,
        rules: list[Rule] | None = None,
        default_destination: str | None = None,
        confidence_threshold: float = 0.7,
    ):
        """
        Initialize the rules-based intelligence.

        Args:
            rules: List of routing rules to evaluate.
            default_destination: Fallback destination if no rules match.
            confidence_threshold: Minimum confidence for automatic routing (0.0-1.0).
        """
        self.rules = rules or []
        self.default_destination = default_destination
        self._confidence_threshold = confidence_threshold
        self._decision_history: dict[str, dict[str, Any]] = {}

        # Sort rules by priority (higher priority first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

        logger.info(
            f"Initialized RulesIntelligence with {len(self.rules)} rules, "
            f"threshold={confidence_threshold}"
        )

    async def route_task(self, context: RoutingContext) -> RoutingDecision:
        """
        Route a task using rules-based matching.

        Evaluates all enabled rules against the task context and selects
        the best match based on confidence scores.

        Args:
            context: Routing context with task details and available destinations.

        Returns:
            Routing decision with destination and confidence.

        Raises:
            RoutingError: If no suitable destination is found.
        """
        logger.debug(f"Routing task {context.task_id}: {context.task_title}")

        # Evaluate all rules
        matches: list[RuleMatch] = []
        for rule in self.rules:
            if not rule.enabled:
                continue

            match = await rule.evaluate(context)
            if match.matched:
                matches.append(match)
                logger.debug(f"Rule '{rule.name}' matched with score {match.score:.2f}")

        # If we have matches, aggregate them
        if matches:
            decision = self._create_decision_from_matches(context, matches)
            logger.info(
                f"Routed task {context.task_id} to {decision.destination} "
                f"(confidence: {decision.confidence:.2f})"
            )
            return decision

        # No matches - use default destination if available
        if self.default_destination:
            decision = RoutingDecision(
                destination=self.default_destination,
                confidence=0.5,
                strategy=DecisionStrategy.RULES,
                reasoning="No rules matched, using default destination",
                decision_factors={"used_default": True},
            )
            logger.info(
                f"No rules matched for task {context.task_id}, "
                f"using default destination: {self.default_destination}"
            )
            return decision

        # No matches and no default - cannot route
        raise RoutingError(
            f"No routing rules matched task {context.task_id} "
            "and no default destination configured",
            context=context,
        )

    async def suggest_destinations(
        self,
        context: RoutingContext,
        limit: int = 5,
    ) -> list[RoutingDecision]:
        """
        Suggest multiple possible destinations with confidence scores.

        Args:
            context: Routing context.
            limit: Maximum number of suggestions to return.

        Returns:
            List of routing decisions, ordered by confidence (highest first).
        """
        logger.debug(f"Suggesting destinations for task {context.task_id}")

        # Evaluate all rules and collect matches by destination
        destination_matches: dict[str, list[RuleMatch]] = {}

        for rule in self.rules:
            if not rule.enabled:
                continue

            match = await rule.evaluate(context)
            if match.matched:
                dest = rule.destination
                if dest not in destination_matches:
                    destination_matches[dest] = []
                destination_matches[dest].append(match)

        # Create a decision for each destination
        decisions: list[RoutingDecision] = []

        for destination, matches in destination_matches.items():
            decision = self._create_decision_from_matches(context, matches, destination)
            decisions.append(decision)

        # Sort by confidence (highest first) and limit
        decisions.sort(key=lambda d: d.confidence, reverse=True)
        decisions = decisions[:limit]

        logger.debug(f"Generated {len(decisions)} suggestions for task {context.task_id}")

        return decisions

    async def record_decision(
        self,
        decision: RoutingDecision,
        context: RoutingContext,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Record a routing decision for future learning and analysis.

        Args:
            decision: The routing decision that was made.
            context: The context in which the decision was made.
            metadata: Additional metadata to store.

        Returns:
            Decision ID for future reference.
        """
        decision_id = str(uuid4())

        self._decision_history[decision_id] = {
            "decision": decision,
            "context": context,
            "metadata": metadata or {},
        }

        logger.info(f"Recorded decision {decision_id} for task {context.task_id}")

        return decision_id

    async def provide_feedback(
        self,
        decision_id: str,
        correct: bool,
        actual_destination: str | None = None,
        notes: str | None = None,
    ) -> None:
        """
        Provide feedback on a routing decision.

        This feedback can be used to adjust rule weights or create new rules.

        Args:
            decision_id: The ID of the decision to provide feedback on.
            correct: Whether the routing decision was correct.
            actual_destination: If incorrect, the correct destination.
            notes: Additional notes about the feedback.
        """
        if decision_id not in self._decision_history:
            logger.warning(f"Unknown decision ID: {decision_id}")
            return

        record = self._decision_history[decision_id]
        record["feedback"] = {
            "correct": correct,
            "actual_destination": actual_destination,
            "notes": notes,
        }

        decision: RoutingDecision = record["decision"]

        # Update rule statistics
        for rule_id in decision.matched_rules:
            rule = self._find_rule_by_id(rule_id)
            if rule:
                rule.times_matched += 1
                if correct:
                    rule.times_correct += 1
                else:
                    rule.times_incorrect += 1

        logger.info(
            f"Recorded feedback for decision {decision_id}: "
            f"correct={correct}, actual={actual_destination}"
        )

    async def get_confidence_threshold(self) -> float:
        """
        Get the minimum confidence threshold for automatic routing.

        Returns:
            Confidence threshold (0.0 to 1.0).
        """
        return self._confidence_threshold

    async def explain_decision(self, decision: RoutingDecision) -> str:
        """
        Generate a human-readable explanation of a routing decision.

        Args:
            decision: The routing decision to explain.

        Returns:
            Human-readable explanation.
        """
        explanation_parts = [
            f"Task routed to: {decision.destination}",
            f"Confidence: {decision.confidence:.0%}",
            f"Strategy: {decision.strategy.value}",
            "",
            f"Reasoning: {decision.reasoning}",
        ]

        if decision.matched_rules:
            explanation_parts.append("")
            explanation_parts.append("Matched rules:")
            for rule_id in decision.matched_rules:
                rule = self._find_rule_by_id(rule_id)
                if rule:
                    explanation_parts.append(f"  - {rule.name}: {rule.description}")

        if decision.decision_factors:
            explanation_parts.append("")
            explanation_parts.append("Decision factors:")
            for key, value in decision.decision_factors.items():
                explanation_parts.append(f"  - {key}: {value}")

        return "\n".join(explanation_parts)

    def _create_decision_from_matches(
        self,
        context: RoutingContext,
        matches: list[RuleMatch],
        destination: str | None = None,
    ) -> RoutingDecision:
        """
        Create a routing decision from rule matches.

        Args:
            context: The routing context.
            matches: List of rule matches.
            destination: Override destination (for suggestions).

        Returns:
            Routing decision.
        """
        # Aggregate scores to get final confidence
        confidence = aggregate_scores([m.score for m in matches])

        # Determine destination (from matches or override)
        if destination is None:
            # Use the destination from the highest-scoring match
            best_match = max(matches, key=lambda m: m.score)
            destination = self._find_rule_by_id(best_match.rule_id).destination

        # Collect matched rule IDs
        matched_rule_ids = [m.rule_id for m in matches]

        # Build reasoning
        reasoning_parts = []
        for match in matches:
            rule = self._find_rule_by_id(match.rule_id)
            if rule:
                reasoning_parts.append(f"{rule.name} (score: {match.score:.2f}): {match.reason}")

        reasoning = "; ".join(reasoning_parts)

        # Collect decision factors
        decision_factors = {
            "num_rules_matched": len(matches),
            "total_score": sum(m.score for m in matches),
            "best_score": max(m.score for m in matches),
        }

        return RoutingDecision(
            destination=destination,
            confidence=confidence,
            strategy=DecisionStrategy.RULES,
            reasoning=reasoning,
            matched_rules=matched_rule_ids,
            decision_factors=decision_factors,
        )

    def _find_rule_by_id(self, rule_id: str) -> Rule | None:
        """Find a rule by its ID."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def add_rule(self, rule: Rule) -> None:
        """
        Add a new rule to the engine.

        Args:
            rule: The rule to add.
        """
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added rule: {rule.name}")

    def remove_rule(self, rule_id: str) -> bool:
        """
        Remove a rule from the engine.

        Args:
            rule_id: ID of the rule to remove.

        Returns:
            True if rule was removed, False if not found.
        """
        for i, rule in enumerate(self.rules):
            if rule.rule_id == rule_id:
                del self.rules[i]
                logger.info(f"Removed rule: {rule.name}")
                return True
        return False

    def get_rule(self, rule_id: str) -> Rule | None:
        """
        Get a rule by ID.

        Args:
            rule_id: The rule ID.

        Returns:
            The rule, or None if not found.
        """
        return self._find_rule_by_id(rule_id)

    def list_rules(self, enabled_only: bool = False) -> list[Rule]:
        """
        List all rules.

        Args:
            enabled_only: If True, only return enabled rules.

        Returns:
            List of rules.
        """
        if enabled_only:
            return [r for r in self.rules if r.enabled]
        return self.rules.copy()
