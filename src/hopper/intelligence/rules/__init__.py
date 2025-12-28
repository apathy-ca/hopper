"""
Rules-based routing intelligence.

Phase 1 routing implementation using keyword matching, tag matching,
and pattern-based rules for fast, deterministic task routing.
"""

from hopper.intelligence.rules.config import (
    RuleConfigError,
    RuleConfigLoader,
    get_default_rules,
    load_rules_or_defaults,
)
from hopper.intelligence.rules.engine import RulesIntelligence
from hopper.intelligence.rules.rule import (
    CompositeOperator,
    CompositeRule,
    KeywordRule,
    PriorityRule,
    Rule,
    RuleMatch,
    RuleType,
    TagRule,
)

__all__ = [
    "RulesIntelligence",
    "RuleConfigLoader",
    "RuleConfigError",
    "get_default_rules",
    "load_rules_or_defaults",
    "Rule",
    "RuleMatch",
    "RuleType",
    "KeywordRule",
    "TagRule",
    "PriorityRule",
    "CompositeRule",
    "CompositeOperator",
]
