# Worker Identity: scope-behaviors

**Role:** Code
**Agent:** claude
**Branch:** cz2/feat/scope-behaviors
**Phase:** 2
**Dependencies:** delegation-protocol

## Mission

Implement scope-specific routing and behavior logic for each instance type (Global, Project, Orchestration). Different scopes have different responsibilities - Global routes to projects, Project decides orchestration, and Orchestration executes. This worker creates the "personality" of each scope level.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/scope-behaviors-knowledge.md`

This includes:
- Design patterns for strategy/behavior patterns
- Integration patterns with existing routing engine
- Configuration patterns for pluggable behaviors
- Testing patterns for behavior-based systems

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Examine the existing routing engine and delegation protocol:**

```bash
# Read the routing engine to understand current intelligence
cat src/hopper/intelligence/rules/engine.py

# Check the delegation protocol implementation
cat src/hopper/delegation/router.py
cat src/hopper/delegation/policies.py

# Look at the HopperScope enum values
grep -A20 "class HopperScope" src/hopper/models/enums.py

# Check existing intelligence package structure
ls -la src/hopper/intelligence/
```

**Then:** Create the `src/hopper/intelligence/scopes/` package structure and start with `base.py` defining the abstract scope behavior interface.

## Objectives

1. **Create Scopes Package** (`src/hopper/intelligence/scopes/`)
   ```
   scopes/
   ├── __init__.py
   ├── base.py              # Base scope behavior interface
   ├── global_scope.py      # Global Hopper behavior
   ├── project_scope.py     # Project Hopper behavior
   └── orchestration_scope.py  # Orchestration behavior
   ```

2. **Define Base Scope Behavior** (`base.py`)
   ```python
   class BaseScopeBehavior(ABC):
       @abstractmethod
       async def handle_incoming_task(self, task, instance) -> TaskAction
       @abstractmethod
       async def should_delegate(self, task, instance) -> bool
       @abstractmethod
       async def find_delegation_target(self, task, instance) -> HopperInstance | None
       @abstractmethod
       async def on_task_completed(self, task, instance) -> None
       @abstractmethod
       async def get_task_queue(self, instance) -> list[Task]
   ```

3. **Implement GlobalScopeBehavior** (`global_scope.py`)
   - Route tasks to appropriate Project based on:
     - Task tags matching project capabilities
     - Task keywords matching project domains
     - Explicit project assignment in task metadata
   - Create new Project instances when needed
   - Balance load across projects
   - Never directly execute tasks (always delegate)

4. **Implement ProjectScopeBehavior** (`project_scope.py`)
   - Decide: manual handling vs orchestration delegation
   - Criteria for orchestration:
     - Task complexity (decomposable)
     - Task type (automatable)
     - Executor availability
   - Create Orchestration instances for czarina runs
   - Track project-level metrics
   - Can handle simple tasks directly

5. **Implement OrchestrationScopeBehavior** (`orchestration_scope.py`)
   - Manage worker queue
   - Track task execution status
   - Report completion to parent Project
   - Handle worker failures and retries
   - Never delegate further (execution level)

6. **Create Scope Behavior Factory**
   - `get_behavior_for_scope(scope)` - Returns appropriate behavior class
   - `get_behavior_for_instance(instance)` - Returns behavior for instance
   - Registry pattern for extensibility

7. **Integrate with Routing Engine**
   - Modify `src/hopper/intelligence/rules/engine.py` to use scope behaviors
   - Add scope context to routing decisions
   - Scope behavior influences routing priority

8. **Create Configuration System**
   - `config/scope_behaviors.yaml` - Scope-specific routing rules
   - Per-scope configuration options
   - Ability to customize behavior without code changes

9. **Write Tests**
   - Unit tests for each scope behavior
   - Integration tests for scope interactions
   - Test routing decisions

## Deliverables

- [ ] `src/hopper/intelligence/scopes/` package with all modules
- [ ] Scope behavior implementations for Global, Project, Orchestration
- [ ] Scope behavior factory
- [ ] Integration with routing engine
- [ ] `config/scope_behaviors.yaml` - Configuration file
- [ ] `tests/intelligence/scopes/test_global_scope.py`
- [ ] `tests/intelligence/scopes/test_project_scope.py`
- [ ] `tests/intelligence/scopes/test_orchestration_scope.py`

## Success Criteria

- [ ] Global Hopper correctly routes tasks to appropriate projects
- [ ] Project Hopper correctly decides orchestration vs manual handling
- [ ] Orchestration Hopper manages task queue effectively
- [ ] Scope behaviors are pluggable/configurable
- [ ] Routing engine integrates seamlessly with scope behaviors
- [ ] 90%+ test coverage on new code

## Context

### Scope Responsibilities

| Scope | Primary Role | Can Delegate To | Can Execute |
|-------|-------------|-----------------|-------------|
| GLOBAL | Strategic routing | PROJECT | No |
| PROJECT | Tactical decisions | ORCHESTRATION | Yes (simple) |
| ORCHESTRATION | Execution | None | Yes (all) |

### Routing Decision Factors

**Global → Project:**
- Task tags (e.g., "czarina" → czarina project)
- Content keywords (e.g., "security" → security project)
- Explicit assignment (task.metadata.project_id)
- Load balancing (prefer least busy project)

**Project → Orchestration:**
- Task complexity score
- Task type (routine vs. complex)
- Available orchestration instances
- Worker availability

### Example Configuration

```yaml
# config/scope_behaviors.yaml
global:
  routing_strategy: "tag_first"
  fallback_strategy: "round_robin"
  auto_create_projects: false

project:
  orchestration_threshold: 3  # Complexity score threshold
  auto_create_orchestrations: true
  max_orchestrations_per_project: 5

orchestration:
  max_concurrent_tasks: 10
  retry_on_failure: true
  max_retries: 3
```

### Integration Points

- **Delegation Protocol**: Scope behaviors trigger delegation
- **Routing Engine**: Provides intelligence for routing decisions
- **Task Model**: Provides task attributes for routing
- **Instance Model**: Provides hierarchy and status

## Notes

- Use Strategy pattern for scope behaviors - easy to extend
- Behaviors should be stateless (get state from instance/task)
- Log all routing decisions for debugging and optimization
- Consider adding metrics collection for routing effectiveness
- Make behaviors configurable without code changes where possible
