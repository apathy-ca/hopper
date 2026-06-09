# Hopper Phase 2: Multi-Instance Support

**Version:** 2.0.0-revised
**Created:** 2026-02-02
**Status:** Ready for Czarina Implementation
**Prerequisites:** Phase 1 Complete (verified)

---

## Executive Summary

Phase 2 implements hierarchical multi-instance support for Hopper, enabling:
- **Global → Project → Orchestration** instance hierarchy
- **Task delegation** flowing down the hierarchy
- **Completion bubbling** flowing up the hierarchy
- **Scope-specific routing** behaviors per instance type

### Key Insight: Foundation Already Exists

Phase 1 implemented more than originally planned. The following are **already complete**:

| Component | Location | Status |
|-----------|----------|--------|
| `HopperInstance` model | `src/hopper/models/hopper_instance.py` | ✅ Complete |
| `HopperScope` enum | `src/hopper/models/enums.py` | ✅ Complete |
| `InstanceStatus` enum | `src/hopper/models/enums.py` | ✅ Complete |
| `InstanceType` enum | `src/hopper/models/enums.py` | ✅ Complete |
| Instance Repository | `src/hopper/database/repositories/hopper_instance_repository.py` | ✅ Complete |
| Instance Pydantic Schemas | `src/hopper/api/schemas/hopper_instance.py` | ✅ Complete |
| Task→Instance FK | `src/hopper/models/task.py` (`instance_id`) | ✅ Complete |
| Hierarchy methods | `HopperInstance.get_ancestors()`, etc. | ✅ Complete |

**Phase 2 focuses on:** API endpoints, delegation protocol, scope behaviors, and visualization.

---

## Architecture

### Instance Hierarchy

```
Global Hopper (scope=GLOBAL)
├── Project Hopper: czarina (scope=PROJECT)
│   ├── Orchestration Hopper: czarina-run-001 (scope=ORCHESTRATION)
│   └── Orchestration Hopper: czarina-run-002 (scope=ORCHESTRATION)
├── Project Hopper: sark (scope=PROJECT)
│   └── Orchestration Hopper: sark-analysis-001 (scope=ORCHESTRATION)
└── Project Hopper: hopper-dev (scope=PROJECT)
```

### Task Flow

```
1. Task created at any instance
2. If instance is GLOBAL:
   - Route to appropriate PROJECT instance based on task content
3. If instance is PROJECT:
   - Decide: handle directly OR delegate to ORCHESTRATION
   - If orchestration needed: create/select ORCHESTRATION instance
4. If instance is ORCHESTRATION:
   - Add to worker queue for execution
5. On completion:
   - Bubble status up to parent instances
   - Update all ancestor task references
```

### Existing Model Reference

**HopperInstance Fields:**
```python
id: str                    # Primary key
name: str                  # Human-readable name
scope: HopperScope         # GLOBAL, PROJECT, ORCHESTRATION, etc.
instance_type: InstanceType # PERSISTENT, EPHEMERAL, TEMPORARY
parent_id: str | None      # FK to parent instance
config: dict               # Instance-specific config (JSONB)
runtime_metadata: dict     # Runtime data (JSONB)
status: InstanceStatus     # CREATED, STARTING, RUNNING, etc.
started_at: datetime       # Lifecycle timestamp
stopped_at: datetime       # Lifecycle timestamp
description: str           # Optional description
created_by: str            # Audit trail
```

**HopperScope Values:**
- `GLOBAL` - Strategic routing across all projects
- `PROJECT` - Project-level task management
- `ORCHESTRATION` - Execution-level queue management
- `PERSONAL` - Individual user scope
- `FAMILY` - Family/household scope
- `EVENT` - Event-specific scope
- `FEDERATED` - Cross-Hopper federation

**InstanceStatus Values:**
- `CREATED` → `STARTING` → `RUNNING` → `STOPPING` → `STOPPED`
- `RUNNING` → `PAUSED` → `RUNNING`
- Any → `ERROR` → `RUNNING` (recovery)
- Any → `TERMINATED` (final)

---

## Worker Breakdown

### Worker 1: instance-api

**Branch:** `cz2/feat/instance-api`
**Dependencies:** None
**Estimated Scope:** ~400-500 lines of code

**Mission:** Activate and implement instance API endpoints.

**Context:**
- Pydantic schemas already exist at `src/hopper/api/schemas/hopper_instance.py`
- Repository methods already exist at `src/hopper/database/repositories/hopper_instance_repository.py`
- App routes are commented out in `src/hopper/api/app.py`

**Tasks:**
1. Create `src/hopper/api/routes/instances.py` with endpoints:
   - `POST /api/v1/instances` - Create instance
   - `GET /api/v1/instances` - List instances (with filters: scope, status, parent_id)
   - `GET /api/v1/instances/{id}` - Get instance details
   - `PUT /api/v1/instances/{id}` - Update instance
   - `DELETE /api/v1/instances/{id}` - Delete instance (soft delete → TERMINATED)
   - `GET /api/v1/instances/{id}/children` - Get child instances
   - `GET /api/v1/instances/{id}/hierarchy` - Get full hierarchy tree
   - `GET /api/v1/instances/{id}/tasks` - Get tasks for instance

2. Add lifecycle endpoints:
   - `POST /api/v1/instances/{id}/start` - Start instance
   - `POST /api/v1/instances/{id}/stop` - Stop instance
   - `POST /api/v1/instances/{id}/restart` - Restart instance
   - `POST /api/v1/instances/{id}/pause` - Pause instance
   - `POST /api/v1/instances/{id}/resume` - Resume instance

3. Uncomment and wire up router in `src/hopper/api/app.py`

4. Align schema enums with model enums (note: schemas have slightly different enum values)

**Deliverables:**
- [ ] `src/hopper/api/routes/instances.py` - All instance endpoints
- [ ] Updated `src/hopper/api/app.py` - Router wired up
- [ ] Updated `src/hopper/api/schemas/hopper_instance.py` - Enum alignment
- [ ] Unit tests in `tests/api/test_instances.py`

**Success Criteria:**
- All instance CRUD operations work via API
- Can retrieve instance hierarchy as tree structure
- Lifecycle operations transition status correctly
- 90%+ test coverage for new code

---

### Worker 2: task-delegation

**Branch:** `cz2/feat/task-delegation`
**Dependencies:** instance-api
**Estimated Scope:** ~300-400 lines of code

**Mission:** Create the TaskDelegation model and delegation tracking.

**Context:**
- Tasks already have `instance_id` FK to HopperInstance
- Need to track when tasks are delegated between instances
- Need to track delegation chain for completion bubbling

**Tasks:**
1. Create `src/hopper/models/task_delegation.py`:
   ```python
   class TaskDelegation(Base, TimestampMixin):
       id: str                    # Primary key
       task_id: str               # FK to Task
       source_instance_id: str    # Where task came from
       target_instance_id: str    # Where task was delegated to
       delegation_type: str       # "route", "decompose", "escalate"
       status: str                # "pending", "accepted", "rejected", "completed"
       delegated_at: datetime
       completed_at: datetime | None
       result: dict | None        # Completion result (JSONB)
       notes: str | None
   ```

2. Create delegation repository with methods:
   - `create_delegation(task_id, source_id, target_id, type)`
   - `get_delegations_for_task(task_id)`
   - `get_delegation_chain(task_id)` - Full path from origin
   - `mark_completed(delegation_id, result)`
   - `get_pending_delegations(instance_id)`

3. Add Alembic migration for new table

4. Add delegation relationship to Task model

5. Create Pydantic schemas for delegation

**Deliverables:**
- [ ] `src/hopper/models/task_delegation.py` - Delegation model
- [ ] `src/hopper/database/repositories/task_delegation_repository.py`
- [ ] `alembic/versions/xxx_add_task_delegation.py` - Migration
- [ ] `src/hopper/api/schemas/task_delegation.py` - Pydantic schemas
- [ ] Updated `src/hopper/models/__init__.py` - Export new model
- [ ] Unit tests in `tests/models/test_task_delegation.py`

**Success Criteria:**
- Can create delegation records when tasks move between instances
- Can trace full delegation chain for any task
- Delegation status properly tracks lifecycle
- Migration runs cleanly on fresh and existing databases

---

### Worker 3: delegation-protocol

**Branch:** `cz2/feat/delegation-protocol`
**Dependencies:** task-delegation
**Estimated Scope:** ~500-600 lines of code

**Mission:** Implement the logic for routing tasks down and bubbling completion up.

**Context:**
- Delegation model tracks the "what"
- This worker implements the "how"
- Must integrate with existing routing intelligence

**Tasks:**
1. Create `src/hopper/delegation/` package:
   ```
   delegation/
   ├── __init__.py
   ├── delegator.py      # Main delegation logic
   ├── router.py         # Instance-to-instance routing
   ├── completion.py     # Completion bubbling
   └── policies.py       # Delegation policies per scope
   ```

2. Implement `Delegator` class:
   - `delegate_task(task, target_instance)` - Delegate task down
   - `accept_delegation(delegation_id)` - Accept incoming delegation
   - `reject_delegation(delegation_id, reason)` - Reject with reason
   - `complete_delegation(delegation_id, result)` - Mark complete

3. Implement `CompletionBubbler`:
   - `bubble_completion(task)` - Notify ancestors of completion
   - `aggregate_child_completions(parent_task)` - Check if all children done
   - `propagate_status_change(task, new_status)` - Status change notifications

4. Implement `InstanceRouter`:
   - `find_target_instance(task, source_instance)` - Determine delegation target
   - `can_delegate_to(source, target)` - Check delegation validity
   - `get_available_instances(scope)` - Get instances accepting tasks

5. Add delegation API endpoints:
   - `POST /api/v1/tasks/{id}/delegate` - Delegate task to instance
   - `POST /api/v1/delegations/{id}/accept` - Accept delegation
   - `POST /api/v1/delegations/{id}/reject` - Reject delegation
   - `POST /api/v1/delegations/{id}/complete` - Mark delegation complete
   - `GET /api/v1/instances/{id}/delegations` - Get delegations for instance

**Deliverables:**
- [ ] `src/hopper/delegation/` package with all modules
- [ ] Delegation API endpoints in `src/hopper/api/routes/delegations.py`
- [ ] Integration with existing routing intelligence
- [ ] Unit tests in `tests/delegation/`
- [ ] Integration tests for delegation flows

**Success Criteria:**
- Tasks can be delegated from Global → Project → Orchestration
- Completion bubbles up the chain automatically
- Rejected delegations are handled gracefully
- Delegation chain is fully traceable

---

### Worker 4: scope-behaviors

**Branch:** `cz2/feat/scope-behaviors`
**Dependencies:** delegation-protocol
**Estimated Scope:** ~400-500 lines of code

**Mission:** Implement scope-specific routing and behavior logic.

**Context:**
- Different scopes have different responsibilities
- GLOBAL routes to projects, PROJECT decides orchestration, ORCHESTRATION executes
- Must integrate with existing rules engine

**Tasks:**
1. Create `src/hopper/intelligence/scopes/` package:
   ```
   scopes/
   ├── __init__.py
   ├── base.py           # Base scope behavior
   ├── global_scope.py   # Global Hopper behavior
   ├── project_scope.py  # Project Hopper behavior
   └── orchestration_scope.py  # Orchestration behavior
   ```

2. Implement `GlobalScopeBehavior`:
   - Route tasks to appropriate project based on:
     - Task tags matching project capabilities
     - Task keywords matching project domains
     - Explicit project assignment
   - Create new Project instances when needed
   - Balance load across projects

3. Implement `ProjectScopeBehavior`:
   - Decide: manual handling vs orchestration
   - Criteria for orchestration:
     - Task complexity (decomposable)
     - Task type (automatable)
     - Executor availability
   - Create Orchestration instances for czarina runs
   - Track project-level metrics

4. Implement `OrchestrationScopeBehavior`:
   - Manage worker queue
   - Track task execution
   - Report completion to parent
   - Handle worker failures

5. Create scope behavior factory:
   - `get_behavior_for_scope(scope)` - Returns appropriate behavior class
   - `get_behavior_for_instance(instance)` - Returns behavior for instance

6. Integrate with routing engine:
   - Modify `src/hopper/intelligence/rules/engine.py` to use scope behaviors
   - Add scope context to routing decisions

**Deliverables:**
- [ ] `src/hopper/intelligence/scopes/` package
- [ ] Scope behavior implementations
- [ ] Integration with routing engine
- [ ] Configuration options per scope
- [ ] Unit tests in `tests/intelligence/scopes/`

**Success Criteria:**
- Global Hopper correctly routes to projects
- Project Hopper correctly decides orchestration vs manual
- Orchestration Hopper manages task queue
- Scope behaviors are pluggable/configurable

---

### Worker 5: instance-cli

**Branch:** `cz2/feat/instance-cli`
**Dependencies:** scope-behaviors
**Estimated Scope:** ~350-450 lines of code

**Mission:** Build CLI commands for instance management and visualization.

**Context:**
- CLI structure exists at `src/hopper/cli/`
- Uses Click framework with Rich for output
- Need instance tree visualization

**Tasks:**
1. Create `src/hopper/cli/commands/instances.py`:
   ```python
   @click.group()
   def instance():
       """Manage Hopper instances."""

   @instance.command()
   def list(): ...      # List instances

   @instance.command()
   def create(): ...    # Create instance

   @instance.command()
   def show(): ...      # Show instance details

   @instance.command()
   def tree(): ...      # Show hierarchy tree

   @instance.command()
   def start(): ...     # Start instance

   @instance.command()
   def stop(): ...      # Stop instance
   ```

2. Implement tree visualization using Rich:
   ```
   $ hopper instance tree

   hopper-global (GLOBAL) [running]
   ├── czarina (PROJECT) [running]
   │   ├── czarina-run-001 (ORCHESTRATION) [running] - 5 tasks
   │   └── czarina-run-002 (ORCHESTRATION) [stopped]
   └── sark (PROJECT) [running]
       └── sark-analysis (ORCHESTRATION) [running] - 2 tasks
   ```

3. Implement status dashboard:
   ```
   $ hopper instance status

   ┌─────────────────────────────────────────────────────┐
   │ Hopper Instance Status                              │
   ├─────────────────────────────────────────────────────┤
   │ Global: hopper-global                    [running]  │
   │ Projects: 3 active, 1 stopped                       │
   │ Orchestrations: 4 active, 2 stopped                 │
   │ Total Tasks: 127 (42 in progress)                   │
   └─────────────────────────────────────────────────────┘
   ```

4. Add instance filtering to task commands:
   - `hopper task list --instance=czarina-run-001`
   - `hopper task add "..." --instance=czarina`

5. Add delegation commands:
   - `hopper task delegate <task-id> --to=<instance-id>`
   - `hopper task delegations <task-id>` - Show delegation chain

**Deliverables:**
- [ ] `src/hopper/cli/commands/instances.py` - Instance commands
- [ ] Tree visualization with Rich
- [ ] Status dashboard
- [ ] Updated task commands with instance filtering
- [ ] Delegation CLI commands
- [ ] Tests in `tests/cli/test_instance_commands.py`

**Success Criteria:**
- Can manage instances entirely from CLI
- Tree visualization clearly shows hierarchy
- Status dashboard provides quick overview
- Instance filtering works on all relevant commands

---

### Worker 6: testing

**Branch:** `cz2/feat/testing`
**Dependencies:** instance-cli
**Estimated Scope:** ~600-800 lines of tests

**Mission:** Comprehensive test suite for all Phase 2 features.

**Context:**
- Existing test infrastructure in `tests/`
- Uses pytest with async support
- Phase 1 tests at 49% pass rate (131/267)

**Tasks:**
1. Create Phase 2 test structure:
   ```
   tests/
   ├── phase2/
   │   ├── __init__.py
   │   ├── conftest.py          # Phase 2 fixtures
   │   ├── test_instance_api.py
   │   ├── test_delegation.py
   │   ├── test_scope_behaviors.py
   │   ├── test_instance_cli.py
   │   └── test_integration.py   # End-to-end flows
   ```

2. Instance API tests:
   - CRUD operations
   - Hierarchy queries
   - Lifecycle transitions
   - Error handling

3. Delegation tests:
   - Create delegation
   - Accept/reject flow
   - Completion bubbling
   - Chain tracing

4. Scope behavior tests:
   - Global routing decisions
   - Project orchestration decisions
   - Orchestration queue management

5. Integration tests:
   - Full flow: task created at Global → routed to Project → delegated to Orchestration → completed → bubbled up
   - Multi-instance coordination
   - Failure recovery scenarios

6. Fix existing failing tests where related to Phase 2 changes

**Deliverables:**
- [ ] `tests/phase2/` test package
- [ ] Fixtures for multi-instance testing
- [ ] 90%+ coverage on new Phase 2 code
- [ ] Integration test for full delegation flow
- [ ] Documentation of test scenarios

**Success Criteria:**
- All new Phase 2 code has tests
- Integration tests pass for full delegation flow
- No regressions in Phase 1 functionality
- Coverage report shows 90%+ on Phase 2 modules

---

### Worker 7: integration

**Branch:** `cz2/feat/integration`
**Dependencies:** testing
**Role:** Integration Worker
**Estimated Scope:** Merge coordination + documentation

**Mission:** Merge all Phase 2 workers and validate the release.

**Tasks:**
1. Merge worker branches in order:
   - instance-api → task-delegation → delegation-protocol → scope-behaviors → instance-cli → testing

2. Resolve merge conflicts

3. Run full test suite and fix any failures

4. Update documentation:
   - Update `README.md` with Phase 2 features
   - Update `docs/ARCHITECTURE.md` with multi-instance details
   - Create `docs/multi-instance-guide.md`
   - Update API documentation

5. Validate Phase 2 success criteria (see below)

6. Create release notes

7. Tag release: `v2.0.0-phase2`

**Deliverables:**
- [ ] All workers merged to omnibus branch
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Release notes
- [ ] Git tag

**Success Criteria:**
- All Phase 2 success criteria met
- No test regressions
- Documentation complete
- Clean merge to master

---

## Phase 2 Success Criteria

All must pass for Phase 2 completion:

### Core Functionality
- [ ] Can create Global, Project, and Orchestration instances via API
- [ ] Can create instances via CLI
- [ ] Tasks can be delegated from Global → Project → Orchestration
- [ ] Completion bubbles up from Orchestration → Project → Global
- [ ] Delegation chain is fully traceable for any task

### Scope Behaviors
- [ ] Global Hopper routes tasks to appropriate projects
- [ ] Project Hopper decides orchestration vs manual handling
- [ ] Orchestration Hopper manages worker queue

### Visualization
- [ ] CLI shows instance hierarchy tree
- [ ] CLI shows instance status dashboard
- [ ] Can filter tasks by instance

### Integration
- [ ] Czarina can create Orchestration instances for runs
- [ ] Full end-to-end flow works: create task → delegate → execute → complete → bubble up

### Quality
- [ ] 90%+ test coverage on new code
- [ ] All Phase 1 tests still pass
- [ ] No critical bugs
- [ ] Documentation updated

---

## Technical Notes

### Database Migrations

Phase 2 adds one new table:
- `task_delegations` - Tracks task delegation between instances

Existing tables modified:
- None (Task already has `instance_id`)

### API Versioning

All new endpoints under `/api/v1/`:
- `/api/v1/instances/*`
- `/api/v1/delegations/*`

### Configuration

New configuration options in `config/`:
- `scope_behaviors.yaml` - Scope-specific routing rules
- `delegation_policies.yaml` - Delegation policies

### Backward Compatibility

- All Phase 1 APIs remain unchanged
- Tasks without `instance_id` continue to work (null = unassigned)
- Existing routing rules still function

---

## File Reference

### Key Files to Read
```
src/hopper/models/hopper_instance.py    # Instance model (complete)
src/hopper/models/enums.py              # All enums (complete)
src/hopper/models/task.py               # Task model with instance_id
src/hopper/database/repositories/hopper_instance_repository.py  # Repository
src/hopper/api/schemas/hopper_instance.py  # Pydantic schemas
src/hopper/api/app.py                   # API app (has commented routes)
src/hopper/intelligence/rules/engine.py # Routing engine to extend
```

### Key Files to Create
```
src/hopper/api/routes/instances.py      # Instance endpoints
src/hopper/api/routes/delegations.py    # Delegation endpoints
src/hopper/models/task_delegation.py    # Delegation model
src/hopper/delegation/                  # Delegation package
src/hopper/intelligence/scopes/         # Scope behaviors
src/hopper/cli/commands/instances.py    # Instance CLI
tests/phase2/                           # Phase 2 tests
```

---

## Appendix: Enum Reference

### HopperScope (from enums.py)
```python
GLOBAL = "GLOBAL"
PROJECT = "PROJECT"
ORCHESTRATION = "ORCHESTRATION"
PERSONAL = "PERSONAL"
FAMILY = "FAMILY"
EVENT = "EVENT"
FEDERATED = "FEDERATED"
```

### InstanceStatus (from enums.py)
```python
CREATED = "created"
STARTING = "starting"
RUNNING = "running"
STOPPING = "stopping"
STOPPED = "stopped"
PAUSED = "paused"
ERROR = "error"
TERMINATED = "terminated"
```

### InstanceType (from enums.py)
```python
PERSISTENT = "persistent"
EPHEMERAL = "ephemeral"
TEMPORARY = "temporary"
```

---

**Document Version:** 2.0.0-revised
**Last Updated:** 2026-02-02
**Ready for:** Czarina orchestration
