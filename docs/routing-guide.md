# Hopper Routing System Guide

**Version:** 1.0.0
**Last Updated:** 2025-12-28

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Rules-Based Routing](#rules-based-routing)
4. [Creating Custom Rules](#creating-custom-rules)
5. [Rule Syntax Reference](#rule-syntax-reference)
6. [Confidence Scoring](#confidence-scoring)
7. [Decision Recording](#decision-recording)
8. [Providing Feedback](#providing-feedback)
9. [Analytics and Monitoring](#analytics-and-monitoring)
10. [Best Practices](#best-practices)
11. [Examples](#examples)

---

## Overview

The Hopper routing system intelligently routes tasks to the most appropriate destination based on configurable rules. It supports multiple routing strategies:

- **Rules-based** (Phase 1): Fast, deterministic routing using keyword/tag matching
- **LLM-based** (Phase 4): Nuanced routing using language models
- **Sage-based** (Phase 4): Advanced routing with AI consciousness

This guide focuses on **Phase 1 rules-based routing**, which is production-ready and suitable for most use cases.

### Key Features

- ⚡ **Fast**: < 10ms routing decisions
- 📋 **Deterministic**: Reproducible and debuggable
- 🎯 **Configurable**: YAML-based rule definitions
- 📊 **Learning**: Records decisions and feedback for improvement
- 🔄 **Flexible**: Multiple rule types and composite logic
- 📈 **Analytics**: Built-in performance monitoring

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────┐
│          Intelligence Layer                     │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────┐     ┌──────────────┐        │
│  │ Rules Engine │     │ LLM Engine   │        │
│  │  (Phase 1)   │     │  (Phase 4)   │        │
│  └──────────────┘     └──────────────┘        │
│                                                 │
│  ┌──────────────────────────────────┐         │
│  │   Decision Recorder              │         │
│  │   - History tracking             │         │
│  │   - Feedback collection          │         │
│  │   - Analytics                    │         │
│  └──────────────────────────────────┘         │
└─────────────────────────────────────────────────┘
```

### Data Flow

```
Task → Routing Context → Rules Engine → Routing Decision
                              ↓
                       Decision Recorder
                              ↓
                       Feedback System
                              ↓
                    Analytics & Learning
```

---

## Rules-Based Routing

### How It Works

1. **Task arrives** with title, description, tags, priority
2. **Rules are evaluated** in priority order (highest first)
3. **Matching rules** generate confidence scores
4. **Best match** is selected as routing destination
5. **Decision is recorded** for tracking and learning
6. **Feedback can be provided** to improve future routing

### Rule Types

| Rule Type | Description | Use Case |
|-----------|-------------|----------|
| **KeywordRule** | Match keywords in title/description | General routing by topic |
| **TagRule** | Match task tags | Routing by category |
| **PriorityRule** | Match task priority level | Escalation routing |
| **CompositeRule** | Combine rules with AND/OR/NOT | Complex logic |

---

## Creating Custom Rules

### Basic Rule Structure

```yaml
rules:
  - id: my-custom-rule
    type: keyword
    name: My Custom Rule
    description: Route tasks about feature X to team Y
    destination: project:team-y
    keywords:
      - feature-x
      - new-feature
    weight: 1.0
    priority: 10
    enabled: true
```

### Field Reference

- **id**: Unique identifier (auto-generated if omitted)
- **type**: Rule type (keyword, tag, priority, composite)
- **name**: Human-readable name
- **description**: What the rule does
- **destination**: Where to route (format: `project:name`, `instance:name`, `user:name`)
- **weight**: Rule importance (0.0-1.0, default 1.0)
- **priority**: Evaluation order (higher = first, default 0)
- **enabled**: Whether rule is active (default true)

### Keyword Rule Example

```yaml
- type: keyword
  name: Documentation Tasks
  description: Route documentation tasks to docs team
  destination: team:documentation
  keywords:
    - documentation
    - docs
    - readme
    - guide
    - tutorial
  case_sensitive: false
  whole_word: false
  keyword_weights:
    documentation: 2.0  # Higher weight for exact match
    docs: 1.5
  weight: 1.0
  priority: 10
```

### Tag Rule Example

```yaml
- type: tag
  name: Bug Priority Routing
  description: Route bugs to bug-tracking instance
  destination: instance:bug-tracker
  required_tags:
    - bug
  optional_tags:
    - critical
    - high-priority
    - regression
  tag_patterns:
    - "^severity:.*"  # Match any severity tag
  weight: 1.0
  priority: 15
```

### Priority Rule Example

```yaml
- type: priority
  name: Critical Escalation
  description: Route critical tasks to on-call team
  destination: team:on-call
  priorities:
    - critical
  weight: 0.9
  priority: 20
```

### Composite Rule Example

```yaml
- type: composite
  name: Urgent Backend Bug
  description: Route urgent backend bugs to specialized team
  destination: team:backend-urgent
  operator: and
  priority: 25
  weight: 1.0
  sub_rules:
    - type: keyword
      name: Backend Keywords
      destination: temp
      keywords:
        - backend
        - api
        - database
        - server
      weight: 1.0

    - type: tag
      name: Bug Tag
      destination: temp
      required_tags:
        - bug
      weight: 1.0

    - type: priority
      name: High Priority
      destination: temp
      min_priority: high
      weight: 1.0
```

---

## Rule Syntax Reference

### KeywordRule Options

```yaml
type: keyword
keywords: [list, of, keywords]
case_sensitive: false          # Default: false
whole_word: false              # Default: false
keyword_weights:               # Optional: weight specific keywords
  important: 2.0
  relevant: 1.5
```

### TagRule Options

```yaml
type: tag
required_tags: [must, have, all]  # All must be present
optional_tags: [boost, if, present]  # Increase score if present
tag_patterns:                    # Regex patterns
  - "^lang:.*"
  - "^category:.*"
```

### PriorityRule Options

```yaml
type: priority
min_priority: high              # Minimum priority (inclusive)
max_priority: medium            # Maximum priority (inclusive)
priorities: [critical, high]    # Exact matches

# Priority order (highest to lowest):
# critical > high > medium > low
```

### CompositeRule Options

```yaml
type: composite
operator: and  # or, not
sub_rules:
  - # First sub-rule
  - # Second sub-rule
  # etc.

# Operators:
# - and: All sub-rules must match
# - or: At least one sub-rule must match
# - not: Sub-rule must NOT match (requires exactly one sub-rule)
```

---

## Confidence Scoring

### How Confidence Works

Confidence scores range from **0.0 to 1.0**, representing how certain the routing engine is about the decision.

- **1.0**: Perfect match (explicit assignment)
- **0.8-0.9**: Very high confidence
- **0.7-0.8**: High confidence (default threshold)
- **0.5-0.7**: Moderate confidence
- **< 0.5**: Low confidence

### Score Calculation

1. **Each rule** generates a base score (0.0-1.0)
2. **Rule weight** is applied to the score
3. **Multiple rules** are aggregated using:
   - Maximum score
   - Average score
   - Weighted average
   - Noisy OR (probabilistic)

### Example Score Calculation

```python
# Two rules match for destination "project:backend"
Rule 1: base_score=0.8, weight=1.0 → 0.8
Rule 2: base_score=0.6, weight=0.7 → 0.42

# Aggregation (using max method):
final_confidence = max(0.8, 0.42) = 0.8
```

### Adjusting Thresholds

```python
from hopper.intelligence.rules import RulesIntelligence

# Create engine with custom threshold
engine = RulesIntelligence(
    rules=rules,
    confidence_threshold=0.75,  # Require 75% confidence
)

# Decisions below threshold should be escalated to humans
decision = await engine.route_task(context)
if not decision.is_confident(threshold=0.75):
    # Escalate to human
    pass
```

---

## Decision Recording

All routing decisions are automatically recorded with:

- Full decision details (destination, confidence, reasoning)
- Task context (title, description, tags, priority)
- Matched rules and decision factors
- Timestamp

### Querying Decisions

```python
from hopper.intelligence import get_decision_recorder

recorder = get_decision_recorder()

# Get decisions for a specific task
decisions = await recorder.get_decisions_for_task("task-123")

# Get decisions by strategy
decisions = await recorder.get_decisions_by_strategy(
    DecisionStrategy.RULES
)

# Get decisions by destination
decisions = await recorder.get_decisions_by_destination(
    "project:backend"
)

# Get recent decisions
decisions = await recorder.get_recent_decisions(limit=100)

# Get statistics
stats = await recorder.get_statistics()
print(f"Total decisions: {stats['total_decisions']}")
print(f"Average confidence: {stats['average_confidence']:.2f}")
print(f"Accuracy: {stats['overall_accuracy']}")
```

---

## Providing Feedback

Feedback helps the routing system learn and improve over time.

### Simple Feedback

```python
from hopper.intelligence import provide_feedback
from hopper.intelligence.types import DecisionFeedback

# Mark a decision as correct
await provide_feedback(
    decision_id="dec-123",
    correct=True,
)

# Mark a decision as incorrect
await provide_feedback(
    decision_id="dec-456",
    correct=False,
    actual_destination="project:correct-team",
    notes="This was actually a backend issue, not frontend",
)
```

### Detailed Feedback

```python
# Provide rating-based feedback
await provide_feedback(
    decision_id="dec-789",
    correct=True,
    rating=0.9,  # 90% correct (partially correct)
    notes="Mostly right, but could have gone to specialized team",
    feedback_by="user-123",
)
```

### Feedback Types

| Type | Description | Use Case |
|------|-------------|----------|
| **Binary** | Correct or incorrect | Simple validation |
| **Rating** | 0.0-1.0 score | Nuanced feedback |
| **Detailed** | With notes | Learning from mistakes |

---

## Analytics and Monitoring

### Performance Metrics

```python
from hopper.intelligence import get_feedback_collector

collector = get_feedback_collector()

# Get overall summary
summary = await collector.get_feedback_summary()
print(f"Accuracy: {summary['accuracy']:.1%}")
print(f"Feedback coverage: {summary['feedback_coverage']:.1%}")

# Get summary for specific strategy
summary = await collector.get_feedback_summary(
    strategy=DecisionStrategy.RULES,
    days=30,
)

# Get summary for specific destination
summary = await collector.get_feedback_summary(
    destination="project:backend",
)
```

### Identifying Problems

```python
# Find routes with low accuracy
problematic = await collector.get_problematic_routes(
    min_samples=5,
    max_accuracy=0.7,
)

for destination, accuracy, count in problematic:
    print(f"{destination}: {accuracy:.1%} ({count} samples)")

# Find high-performing routes
high_performing = await collector.get_high_performing_routes(
    min_samples=5,
    min_accuracy=0.9,
)
```

### Confidence Calibration

```python
# Check if confidence scores are well-calibrated
calibration = await collector.get_confidence_calibration(bins=10)

for bin_range, data in calibration.items():
    print(f"{bin_range}: "
          f"expected={data['expected_accuracy']:.1%}, "
          f"actual={data['actual_accuracy']:.1%}, "
          f"error={data['calibration_error']:.2f}")
```

### Trend Analysis

```python
# Get feedback trends over time
trends = await collector.get_feedback_trends(
    days=30,
    interval_days=7,
)

for period in trends['intervals']:
    print(f"{period['period_start']}: "
          f"accuracy={period['accuracy']:.1%}")
```

### Improvement Suggestions

```python
# Get automated suggestions for rule improvements
suggestions = await collector.suggest_rule_improvements(
    min_samples=10,
)

for suggestion in suggestions:
    print(f"Destination: {suggestion['destination']}")
    print(f"Current accuracy: {suggestion['current_accuracy']:.1%}")
    print(f"Recommendation: {suggestion['details']['recommendation']}")
```

---

## Best Practices

### Rule Organization

1. **Use descriptive names**: Make rules self-documenting
2. **Set appropriate priorities**: Higher priority for more specific rules
3. **Group related rules**: Organize by project or category
4. **Document reasoning**: Use description field
5. **Version control**: Keep rules in git

### Rule Design

1. **Start specific, then general**: Specific rules should have higher priority
2. **Avoid overlap**: Minimize conflicts between rules
3. **Use composite rules**: For complex routing logic
4. **Test before deploying**: Validate rules against sample tasks
5. **Monitor performance**: Check accuracy regularly

### Confidence Thresholds

```
Critical tasks:     0.9+ (very high confidence required)
Important tasks:    0.7+ (high confidence required)
Normal tasks:       0.5+ (moderate confidence acceptable)
Low priority:       0.3+ (low confidence acceptable)
```

### Feedback Collection

1. **Provide feedback regularly**: Helps system learn
2. **Be specific**: Include notes about why a decision was wrong
3. **Track patterns**: Look for repeated errors
4. **Adjust rules**: Update based on feedback trends
5. **Monitor calibration**: Ensure confidence scores are accurate

---

## Examples

### Example 1: Simple Project Routing

```yaml
rules:
  - type: keyword
    name: Frontend Tasks
    description: Route frontend tasks to frontend team
    destination: project:frontend
    keywords:
      - react
      - vue
      - angular
      - css
      - html
      - ui
      - ux
    weight: 1.0
    priority: 10

  - type: keyword
    name: Backend Tasks
    description: Route backend tasks to backend team
    destination: project:backend
    keywords:
      - api
      - database
      - server
      - backend
      - postgres
      - redis
    weight: 1.0
    priority: 10
```

### Example 2: Priority-Based Escalation

```yaml
rules:
  - type: composite
    name: Critical Bug Escalation
    description: Route critical bugs to incident response team
    destination: team:incident-response
    operator: and
    priority: 30
    sub_rules:
      - type: priority
        name: Critical Priority
        destination: temp
        priorities: [critical]
        weight: 1.0

      - type: keyword
        name: Bug Keywords
        destination: temp
        keywords: [bug, error, crash, down, outage]
        weight: 1.0
```

### Example 3: Multi-Project Organization

```yaml
rules:
  # Czarina orchestration
  - type: keyword
    name: Czarina Tasks
    destination: project:czarina
    keywords: [czarina, orchestration, worker, swarm]
    priority: 15

  # Hopper queue
  - type: keyword
    name: Hopper Tasks
    destination: project:hopper
    keywords: [hopper, queue, routing, mcp]
    priority: 15

  # SARK policy
  - type: keyword
    name: SARK Tasks
    destination: project:sark
    keywords: [sark, policy, governance, compliance]
    priority: 15

  # Default fallback
  - type: keyword
    name: General Tasks
    destination: instance:inbox
    keywords: []  # Matches everything
    weight: 0.3
    priority: 0
```

### Example 4: Tag-Based Routing

```yaml
rules:
  - type: tag
    name: Language-Specific Routing
    destination: team:specialized
    tag_patterns:
      - "^lang:rust$"
      - "^lang:go$"
    required_tags:
      - specialized
    priority: 20

  - type: tag
    name: Security Tasks
    destination: team:security
    required_tags:
      - security
    optional_tags:
      - audit
      - vulnerability
      - compliance
    priority: 25
```

### Example 5: Testing Rules

```python
from hopper.intelligence.rules import (
    RulesIntelligence,
    load_rules_or_defaults,
)
from hopper.intelligence.types import RoutingContext

# Load rules from configuration
rules = load_rules_or_defaults(Path("config/routing-rules.yaml"))

# Create engine
engine = RulesIntelligence(
    rules=rules,
    confidence_threshold=0.7,
)

# Test with sample task
context = RoutingContext(
    task_id="test-1",
    task_title="Fix critical API bug",
    task_description="The /users endpoint is returning 500 errors",
    task_tags=["bug", "backend", "api"],
    task_priority="critical",
)

# Get routing decision
decision = await engine.route_task(context)

print(f"Destination: {decision.destination}")
print(f"Confidence: {decision.confidence:.2%}")
print(f"Reasoning: {decision.reasoning}")

# Get explanation
explanation = await engine.explain_decision(decision)
print(explanation)
```

---

## Next Steps

- **Phase 2**: Database persistence for decisions
- **Phase 3**: Machine learning from feedback
- **Phase 4**: LLM and Sage routing strategies
- **Integration**: API endpoints for routing
- **UI**: Visual rule editor and analytics dashboard

---

## Support

For questions, issues, or feature requests:
- Documentation: `/docs/Hopper.Specification.md`
- Implementation Plan: `/plans/Hopper-Implementation-Plan.md`
- GitHub Issues: TBD

---

**Happy Routing! 🚀**
