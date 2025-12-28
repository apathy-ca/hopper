"""
Rule configuration system.

Loads and validates routing rules from YAML configuration files.
Provides default rules and rule management utilities.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import yaml

from hopper.intelligence.rules.rule import (
    CompositeOperator,
    CompositeRule,
    KeywordRule,
    PriorityRule,
    Rule,
    TagRule,
)

logger = logging.getLogger(__name__)


class RuleConfigError(Exception):
    """Raised when rule configuration is invalid."""

    pass


class RuleConfigLoader:
    """
    Loads and manages routing rule configurations.

    Supports loading rules from YAML files, validating rule definitions,
    and creating Rule objects from configuration.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize the rule configuration loader.

        Args:
            config_path: Path to configuration file. If None, uses default.
        """
        self.config_path = config_path
        self._rules_cache: Dict[str, Rule] = {}

    def load_rules_from_file(self, file_path: Path) -> List[Rule]:
        """
        Load rules from a YAML configuration file.

        Args:
            file_path: Path to YAML file.

        Returns:
            List of Rule objects.

        Raises:
            RuleConfigError: If configuration is invalid.
        """
        logger.info(f"Loading rules from {file_path}")

        try:
            with open(file_path, "r") as f:
                config = yaml.safe_load(f)

        except FileNotFoundError:
            raise RuleConfigError(f"Configuration file not found: {file_path}")

        except yaml.YAMLError as e:
            raise RuleConfigError(f"Invalid YAML in {file_path}: {e}")

        return self.load_rules_from_dict(config)

    def load_rules_from_dict(self, config: Dict[str, Any]) -> List[Rule]:
        """
        Load rules from a configuration dictionary.

        Args:
            config: Configuration dictionary with 'rules' key.

        Returns:
            List of Rule objects.

        Raises:
            RuleConfigError: If configuration is invalid.
        """
        if not isinstance(config, dict):
            raise RuleConfigError("Configuration must be a dictionary")

        if "rules" not in config:
            raise RuleConfigError("Configuration must have 'rules' key")

        rules_config = config["rules"]

        if not isinstance(rules_config, list):
            raise RuleConfigError("'rules' must be a list")

        rules = []

        for i, rule_config in enumerate(rules_config):
            try:
                rule = self._create_rule_from_config(rule_config)
                rules.append(rule)
                logger.debug(f"Loaded rule: {rule.name}")

            except Exception as e:
                raise RuleConfigError(f"Error loading rule {i}: {e}")

        logger.info(f"Loaded {len(rules)} rules from configuration")

        return rules

    def _create_rule_from_config(self, config: Dict[str, Any]) -> Rule:
        """
        Create a Rule object from configuration dictionary.

        Args:
            config: Rule configuration.

        Returns:
            Rule object.

        Raises:
            RuleConfigError: If configuration is invalid.
        """
        # Validate required fields
        required_fields = ["type", "name", "destination"]
        for field in required_fields:
            if field not in config:
                raise RuleConfigError(f"Rule missing required field: {field}")

        rule_type = config["type"]
        rule_id = config.get("id", str(uuid4()))

        # Common fields
        common_args = {
            "rule_id": rule_id,
            "name": config["name"],
            "description": config.get("description", ""),
            "destination": config["destination"],
            "weight": config.get("weight", 1.0),
            "enabled": config.get("enabled", True),
            "priority": config.get("priority", 0),
            "created_by": config.get("created_by"),
        }

        # Create specific rule type
        if rule_type == "keyword":
            return self._create_keyword_rule(config, common_args)

        elif rule_type == "tag":
            return self._create_tag_rule(config, common_args)

        elif rule_type == "priority":
            return self._create_priority_rule(config, common_args)

        elif rule_type == "composite":
            return self._create_composite_rule(config, common_args)

        else:
            raise RuleConfigError(f"Unknown rule type: {rule_type}")

    def _create_keyword_rule(
        self, config: Dict[str, Any], common_args: Dict[str, Any]
    ) -> KeywordRule:
        """Create a KeywordRule from configuration."""
        if "keywords" not in config:
            raise RuleConfigError("KeywordRule requires 'keywords' field")

        keywords = config["keywords"]
        if not isinstance(keywords, list):
            raise RuleConfigError("'keywords' must be a list")

        return KeywordRule(
            keywords=keywords,
            case_sensitive=config.get("case_sensitive", False),
            whole_word=config.get("whole_word", False),
            keyword_weights=config.get("keyword_weights"),
            **common_args,
        )

    def _create_tag_rule(
        self, config: Dict[str, Any], common_args: Dict[str, Any]
    ) -> TagRule:
        """Create a TagRule from configuration."""
        return TagRule(
            required_tags=config.get("required_tags"),
            optional_tags=config.get("optional_tags"),
            tag_patterns=config.get("tag_patterns"),
            **common_args,
        )

    def _create_priority_rule(
        self, config: Dict[str, Any], common_args: Dict[str, Any]
    ) -> PriorityRule:
        """Create a PriorityRule from configuration."""
        return PriorityRule(
            min_priority=config.get("min_priority"),
            max_priority=config.get("max_priority"),
            priorities=config.get("priorities"),
            **common_args,
        )

    def _create_composite_rule(
        self, config: Dict[str, Any], common_args: Dict[str, Any]
    ) -> CompositeRule:
        """Create a CompositeRule from configuration."""
        if "operator" not in config:
            raise RuleConfigError("CompositeRule requires 'operator' field")

        if "sub_rules" not in config:
            raise RuleConfigError("CompositeRule requires 'sub_rules' field")

        # Parse operator
        operator_str = config["operator"].upper()
        try:
            operator = CompositeOperator[operator_str]
        except KeyError:
            raise RuleConfigError(f"Unknown operator: {config['operator']}")

        # Create sub-rules recursively
        sub_rules = []
        for sub_config in config["sub_rules"]:
            sub_rule = self._create_rule_from_config(sub_config)
            sub_rules.append(sub_rule)

        return CompositeRule(
            operator=operator,
            sub_rules=sub_rules,
            **common_args,
        )

    def save_rules_to_file(self, rules: List[Rule], file_path: Path) -> None:
        """
        Save rules to a YAML configuration file.

        Args:
            rules: List of rules to save.
            file_path: Path to save to.

        Raises:
            RuleConfigError: If save fails.
        """
        logger.info(f"Saving {len(rules)} rules to {file_path}")

        # Convert rules to configuration format
        rules_config = []

        for rule in rules:
            rule_dict = self._rule_to_config_dict(rule)
            rules_config.append(rule_dict)

        config = {"rules": rules_config}

        try:
            with open(file_path, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Successfully saved rules to {file_path}")

        except Exception as e:
            raise RuleConfigError(f"Failed to save rules: {e}")

    def _rule_to_config_dict(self, rule: Rule) -> Dict[str, Any]:
        """
        Convert a Rule object to configuration dictionary.

        Args:
            rule: Rule to convert.

        Returns:
            Configuration dictionary.
        """
        config = {
            "id": rule.rule_id,
            "name": rule.name,
            "description": rule.description,
            "destination": rule.destination,
            "weight": rule.weight,
            "enabled": rule.enabled,
            "priority": rule.priority,
        }

        if rule.created_by:
            config["created_by"] = rule.created_by

        # Add type-specific fields
        if isinstance(rule, KeywordRule):
            config["type"] = "keyword"
            config["keywords"] = rule.keywords
            config["case_sensitive"] = rule.case_sensitive
            config["whole_word"] = rule.whole_word

            if rule.keyword_weights:
                config["keyword_weights"] = rule.keyword_weights

        elif isinstance(rule, TagRule):
            config["type"] = "tag"

            if rule.required_tags:
                config["required_tags"] = rule.required_tags
            if rule.optional_tags:
                config["optional_tags"] = rule.optional_tags
            if rule.tag_patterns:
                config["tag_patterns"] = rule.tag_patterns

        elif isinstance(rule, PriorityRule):
            config["type"] = "priority"

            if rule.min_priority:
                config["min_priority"] = rule.min_priority
            if rule.max_priority:
                config["max_priority"] = rule.max_priority
            if rule.priorities:
                config["priorities"] = rule.priorities

        elif isinstance(rule, CompositeRule):
            config["type"] = "composite"
            config["operator"] = rule.operator.value

            sub_rules_config = [
                self._rule_to_config_dict(sub_rule) for sub_rule in rule.sub_rules
            ]
            config["sub_rules"] = sub_rules_config

        return config

    def validate_rule_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate a rule configuration and return any errors.

        Args:
            config: Rule configuration to validate.

        Returns:
            List of error messages (empty if valid).
        """
        errors = []

        # Check required fields
        if "type" not in config:
            errors.append("Missing required field: type")

        if "name" not in config:
            errors.append("Missing required field: name")

        if "destination" not in config:
            errors.append("Missing required field: destination")

        if errors:
            return errors

        # Validate type-specific fields
        rule_type = config["type"]

        if rule_type == "keyword":
            if "keywords" not in config:
                errors.append("KeywordRule requires 'keywords' field")
            elif not isinstance(config["keywords"], list):
                errors.append("'keywords' must be a list")

        elif rule_type == "priority":
            # At least one of these must be specified
            if (
                "min_priority" not in config
                and "max_priority" not in config
                and "priorities" not in config
            ):
                errors.append(
                    "PriorityRule requires at least one of: "
                    "min_priority, max_priority, priorities"
                )

        elif rule_type == "composite":
            if "operator" not in config:
                errors.append("CompositeRule requires 'operator' field")

            if "sub_rules" not in config:
                errors.append("CompositeRule requires 'sub_rules' field")
            elif not isinstance(config["sub_rules"], list):
                errors.append("'sub_rules' must be a list")

        # Validate weight
        if "weight" in config:
            weight = config["weight"]
            if not isinstance(weight, (int, float)) or weight < 0 or weight > 1:
                errors.append("'weight' must be a number between 0 and 1")

        # Validate priority
        if "priority" in config:
            priority = config["priority"]
            if not isinstance(priority, int):
                errors.append("'priority' must be an integer")

        return errors


def get_default_rules() -> List[Rule]:
    """
    Get default routing rules for common scenarios.

    Returns:
        List of default Rule objects.
    """
    rules = [
        # Czarina orchestration rules
        KeywordRule(
            rule_id="default-czarina-keyword",
            name="Czarina Keyword Detection",
            description="Route tasks with Czarina-related keywords",
            destination="project:czarina",
            keywords=["czarina", "orchestration", "worker", "phase", "swarm"],
            weight=1.0,
            priority=10,
        ),
        TagRule(
            rule_id="default-czarina-tag",
            name="Czarina Tag Detection",
            description="Route tasks tagged with czarina",
            destination="project:czarina",
            optional_tags=["czarina", "orchestration", "automation"],
            weight=1.0,
            priority=10,
        ),
        # Hopper task queue rules
        KeywordRule(
            rule_id="default-hopper-keyword",
            name="Hopper Keyword Detection",
            description="Route tasks with Hopper-related keywords",
            destination="project:hopper",
            keywords=["hopper", "task", "queue", "routing", "intelligence"],
            weight=1.0,
            priority=10,
        ),
        TagRule(
            rule_id="default-hopper-tag",
            name="Hopper Tag Detection",
            description="Route tasks tagged with hopper",
            destination="project:hopper",
            optional_tags=["hopper", "task-queue", "routing"],
            weight=1.0,
            priority=10,
        ),
        # Priority escalation
        PriorityRule(
            rule_id="default-high-priority",
            name="High Priority Escalation",
            description="Route critical/high priority tasks to global instance",
            destination="instance:global",
            min_priority="high",
            weight=0.8,
            priority=20,
        ),
    ]

    return rules


def load_rules_or_defaults(config_path: Optional[Path] = None) -> List[Rule]:
    """
    Load rules from configuration file, or use defaults if file doesn't exist.

    Args:
        config_path: Path to configuration file.

    Returns:
        List of rules.
    """
    if config_path and config_path.exists():
        loader = RuleConfigLoader(config_path)
        try:
            return loader.load_rules_from_file(config_path)
        except RuleConfigError as e:
            logger.warning(f"Failed to load rules from {config_path}: {e}")
            logger.info("Using default rules instead")

    logger.info("Using default routing rules")
    return get_default_rules()
