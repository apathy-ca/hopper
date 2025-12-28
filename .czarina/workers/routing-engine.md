# Worker: Routing Engine

**Branch:** cz1/feat/routing-engine
**Dependencies:** api-core
**Duration:** 2 days

## Mission

Implement the rules-based routing intelligence that determines where tasks should go. This is Phase 1's routing system - simple, fast, and deterministic.

## Background

Phase 1 Week 2 includes rules-based routing that:
- Matches tasks to projects/destinations based on keywords, tags, and patterns
- Provides confidence scores for routing decisions
- Records all decisions for future learning
- Supports custom routing rules per project

This is the foundation for Phase 4's LLM and Sage routing systems.

## Tasks

### Task 1: Routing Engine Core

1. Create `src/hopper/intelligence/__init__.py`:
   - Intelligence layer package
   - Base intelligence interface

2. Create `src/hopper/intelligence/base.py`:
   - BaseIntelligence abstract class
   - Method signatures for routing
   - Decision recording interface
   - Confidence scoring interface

3. Create `src/hopper/intelligence/types.py`:
   - RoutingContext dataclass (task, available destinations, history)
   - RoutingDecision dataclass (destination, confidence, reasoning)
   - DecisionStrategy enum (RULES, LLM, SAGE)

4. Create `src/hopper/intelligence/rules/__init__.py`:
   - Rules engine package

**Checkpoint:** Commit routing engine core

### Task 2: Rules-Based Intelligence Implementation

Reference: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md` (Routing Intelligence section)

1. Create `src/hopper/intelligence/rules/engine.py`:
   - RulesIntelligence class implementing BaseIntelligence
   - Rule evaluation engine
   - Confidence scoring
   - Decision recording

2. Create `src/hopper/intelligence/rules/rule.py`:
   - Rule class definition
   - Rule types:
     - KeywordRule - Match based on keywords in title/description
     - TagRule - Match based on tags
     - PriorityRule - Match based on priority
     - ProjectRule - Match based on project attributes
     - CompositeRule - Combine multiple rules (AND, OR, NOT)
   - Rule evaluation logic
   - Rule serialization (to/from YAML)

3. Create `src/hopper/intelligence/rules/matchers.py`:
   - Keyword matching utilities
   - Tag matching utilities
   - Pattern matching (regex support)
   - Fuzzy matching for flexibility

4. Create `src/hopper/intelligence/rules/scoring.py`:
   - Confidence score calculation
   - Multiple match aggregation
   - Rule weight support
   - Threshold-based decisions

**Checkpoint:** Commit rules-based intelligence

### Task 3: Rule Configuration System

1. Create `src/hopper/intelligence/rules/config.py`:
   - Rule configuration loading
   - YAML-based rule definitions
   - Rule validation
   - Default rules

2. Create default rule sets in `config/routing-rules.yaml`:
   - Example rules for common scenarios
   - Czarina project rules (keywords: orchestration, worker, phase)
   - Hopper project rules (keywords: task, queue, routing)
   - Default fallback rules

3. Create rule configuration schema:
   ```yaml
   rules:
     - id: czarina-detection
       type: keyword
       keywords: [czarina, orchestration, worker, phase]
       destination: project:czarina
       weight: 1.0

     - id: hopper-detection
       type: keyword
       keywords: [hopper, task, queue, routing]
       destination: project:hopper
       weight: 1.0

     - id: high-priority-escalation
       type: priority
       min_priority: high
       destination: instance:global
       weight: 0.8
   ```

4. Add rule management API:
   - Create rule
   - Update rule
   - Delete rule
   - List rules
   - Test rule against task

**Checkpoint:** Commit rule configuration system

### Task 4: Decision Recording and Feedback

1. Create `src/hopper/intelligence/decision_recorder.py`:
   - Record routing decisions to database
   - Link decisions to tasks
   - Store routing context
   - Store confidence and reasoning

2. Create `src/hopper/intelligence/feedback.py`:
   - Feedback collection system
   - Feedback types (correct, incorrect, partially_correct)
   - Feedback impact on future routing
   - Feedback analytics

3. Add decision history queries:
   - Get decisions for task
   - Get decisions by strategy
   - Get decisions by destination
   - Get decision success rate
   - Get recent decisions

4. Create feedback API endpoints:
   - `POST /api/v1/decisions/{decision_id}/feedback` - Provide feedback
   - `GET /api/v1/decisions/analytics` - Get decision analytics

**Checkpoint:** Commit decision recording and feedback

### Task 5: Routing API Endpoints

1. Create `src/hopper/api/routes/routing.py`:
   - `POST /api/v1/routing/route-task` - Route a task
     - Parameters: task_id, context (optional)
     - Returns: RoutingDecision

   - `POST /api/v1/routing/suggest` - Get routing suggestions
     - Parameters: task_description, task_tags
     - Returns: List of suggested destinations with confidence

   - `GET /api/v1/routing/rules` - List routing rules
   - `POST /api/v1/routing/rules` - Create routing rule
   - `PUT /api/v1/routing/rules/{rule_id}` - Update rule
   - `DELETE /api/v1/routing/rules/{rule_id}` - Delete rule
   - `POST /api/v1/routing/rules/{rule_id}/test` - Test rule

   - `GET /api/v1/routing/decisions` - List routing decisions
   - `GET /api/v1/routing/decisions/{decision_id}` - Get decision details
   - `POST /api/v1/routing/decisions/{decision_id}/feedback` - Provide feedback

2. Add routing to task creation:
   - Optional auto-routing on task creation
   - Parameter: `auto_route=true`
   - Automatically assign to suggested destination

**Checkpoint:** Commit routing API endpoints

### Task 6: Testing and Documentation

1. Create `tests/intelligence/test_rules_engine.py`:
   - Test rule evaluation
   - Test keyword matching
   - Test tag matching
   - Test confidence scoring
   - Test composite rules

2. Create `tests/intelligence/test_rule_config.py`:
   - Test rule loading from YAML
   - Test rule validation
   - Test rule serialization

3. Create `tests/intelligence/test_decision_recorder.py`:
   - Test decision recording
   - Test decision history
   - Test feedback collection

4. Create `tests/api/test_routing.py`:
   - Test routing endpoints
   - Test rule management
   - Test decision feedback
   - Test auto-routing

5. Create test fixtures with sample rules and tasks:
   - Various task types
   - Different rule configurations
   - Expected routing outcomes

6. Create `docs/routing-guide.md`:
   - Routing system overview
   - How rules work
   - Creating custom rules
   - Rule syntax and examples
   - Confidence scoring explained
   - Providing feedback
   - Decision analytics

7. Create rule examples and tutorials:
   - Simple keyword rules
   - Complex composite rules
   - Project-specific rules
   - Priority-based routing

**Checkpoint:** Commit tests and documentation

## Deliverables

- [ ] Base intelligence interface
- [ ] Rules-based intelligence implementation
- [ ] Rule types (keyword, tag, priority, composite)
- [ ] Rule configuration system (YAML-based)
- [ ] Default rule sets for common scenarios
- [ ] Decision recording to database
- [ ] Feedback collection system
- [ ] Routing API endpoints
- [ ] Rule management endpoints
- [ ] Comprehensive test suite
- [ ] Routing guide documentation

## Success Criteria

- ✅ Can create rules from YAML configuration
- ✅ Rules correctly match tasks to destinations
- ✅ Confidence scores are reasonable (0.0-1.0)
- ✅ Can route tasks via API: `POST /api/v1/routing/route-task`
- ✅ Can get routing suggestions for new tasks
- ✅ Routing decisions are recorded in database
- ✅ Can provide feedback on routing decisions
- ✅ Composite rules work correctly (AND, OR, NOT)
- ✅ Auto-routing works on task creation
- ✅ All tests pass with good coverage
- ✅ Documentation explains how to create custom rules

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md`
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md` (Routing Intelligence)
- Phase 4 will extend this with LLM and Sage routing

## Notes

- Keep rules simple and fast for Phase 1
- Rules should be human-readable and editable
- YAML format for rules allows version control
- Confidence scoring helps with decision quality
- Decision recording is critical for Phase 3 (learning)
- Feedback loop enables continuous improvement
- Consider rule priorities when multiple rules match
- Composite rules enable complex routing logic
- Rules can be project-specific or global
- Future phases will add LLM and Sage intelligence alongside rules
- Rules engine should be extensible (plugin architecture)
- Consider caching frequently used rules
- Log all routing decisions for debugging
