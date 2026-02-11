# Worker Identity: task-delegation

**Role:** Code
**Agent:** claude
**Branch:** cz2/feat/task-delegation
**Phase:** 2
**Dependencies:** instance-api

## Mission

Create the TaskDelegation model and supporting infrastructure to track when tasks are delegated between Hopper instances. This enables the delegation chain tracking needed for completion bubbling - when a task completes at an Orchestration instance, the completion status must bubble up to Project and Global instances.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/task-delegation-knowledge.md`

This includes:
- SQLAlchemy model patterns for async usage
- Alembic migration best practices
- Repository pattern implementation
- Pydantic schema design patterns

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Examine the existing Task model and database patterns:**

```bash
# Read the existing Task model to understand the instance_id relationship
cat src/hopper/models/task.py

# Read an existing repository for the pattern to follow
cat src/hopper/database/repositories/task_repository.py

# Check the existing model base classes and mixins
cat src/hopper/models/base.py

# Look at how Alembic migrations are structured
ls -la alembic/versions/ | head -10
cat alembic/versions/*_initial*.py 2>/dev/null || cat $(ls alembic/versions/*.py | head -1)
```

**Then:** Design the TaskDelegation model schema and create the model file at `src/hopper/models/task_delegation.py`.

## Objectives

1. **Create TaskDelegation Model** (`src/hopper/models/task_delegation.py`)
   ```python
   class TaskDelegation(Base, TimestampMixin):
       id: str                    # Primary key (UUID)
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

2. **Create Delegation Repository** (`src/hopper/database/repositories/task_delegation_repository.py`)
   - `create_delegation(task_id, source_id, target_id, type)`
   - `get_delegations_for_task(task_id)`
   - `get_delegation_chain(task_id)` - Full path from origin
   - `mark_completed(delegation_id, result)`
   - `get_pending_delegations(instance_id)`
   - `accept_delegation(delegation_id)`
   - `reject_delegation(delegation_id, reason)`

3. **Create Alembic Migration**
   - `alembic/versions/xxx_add_task_delegation.py`
   - Create `task_delegations` table
   - Add proper foreign key constraints
   - Add indexes for common queries (task_id, source_instance_id, target_instance_id, status)

4. **Create Pydantic Schemas** (`src/hopper/api/schemas/task_delegation.py`)
   - `TaskDelegationCreate` - Request schema for creating delegation
   - `TaskDelegationUpdate` - Request schema for updates
   - `TaskDelegationResponse` - Response schema
   - `DelegationChainResponse` - For chain queries

5. **Update Task Model** (`src/hopper/models/task.py`)
   - Add `delegations` relationship to TaskDelegation

6. **Update Model Exports** (`src/hopper/models/__init__.py`)
   - Export TaskDelegation model

7. **Write Unit Tests** (`tests/models/test_task_delegation.py`)
   - Test model creation
   - Test repository methods
   - Test delegation chain traversal

## Deliverables

- [ ] `src/hopper/models/task_delegation.py` - Delegation model
- [ ] `src/hopper/database/repositories/task_delegation_repository.py` - Repository
- [ ] `alembic/versions/xxx_add_task_delegation.py` - Migration
- [ ] `src/hopper/api/schemas/task_delegation.py` - Pydantic schemas
- [ ] Updated `src/hopper/models/task.py` - Delegation relationship
- [ ] Updated `src/hopper/models/__init__.py` - Export new model
- [ ] `tests/models/test_task_delegation.py` - Unit tests

## Success Criteria

- [ ] Can create delegation records when tasks move between instances
- [ ] Can trace full delegation chain for any task
- [ ] Delegation status properly tracks lifecycle (pending → accepted/rejected → completed)
- [ ] Migration runs cleanly on fresh and existing databases
- [ ] All foreign key constraints are properly defined
- [ ] 90%+ test coverage on new code

## Context

### Delegation Types

- **route** - Task routed from Global → Project or Project → Orchestration
- **decompose** - Task decomposed into subtasks at lower level
- **escalate** - Task escalated back up the hierarchy (rare, for errors/exceptions)

### Delegation Status Lifecycle

```
[created] → pending → accepted → completed
                   ↘ rejected
```

### Example Delegation Chain

```
Task T1 at Global
  ↓ route
Task T1-delegated to Project-A
  ↓ route
Task T1-delegated to Orchestration-001
  ↓ [work happens]
Completed at Orchestration-001
  ↑ bubble completion
Project-A marked complete
  ↑ bubble completion
Global Task T1 marked complete
```

### Key Files to Reference

- `src/hopper/models/task.py` - Existing Task model with instance_id
- `src/hopper/models/hopper_instance.py` - HopperInstance model
- `src/hopper/database/repositories/task_repository.py` - Repository pattern example
- `src/hopper/models/base.py` - Base classes and mixins

## Notes

- Use UUID strings for all IDs (matches existing pattern)
- JSONB for `result` field to store arbitrary completion data
- Consider adding `delegated_by` field for audit trail
- Index on `status` for efficient pending delegation queries
- The delegation chain query should be efficient - consider recursive CTE or application-level traversal
