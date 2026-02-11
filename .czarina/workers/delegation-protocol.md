# Worker Identity: delegation-protocol

**Role:** Code
**Agent:** claude
**Branch:** cz2/feat/delegation-protocol
**Phase:** 2
**Dependencies:** task-delegation

## Mission

Implement the core delegation protocol - the logic that actually moves tasks between instances and bubbles completion status back up the hierarchy. This is the "how" of delegation, building on the TaskDelegation model created by the task-delegation worker.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/delegation-protocol-knowledge.md`

This includes:
- Async patterns for service layer implementation
- Error handling and recovery patterns
- API endpoint design patterns
- Testing patterns for complex workflows

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Examine the existing routing intelligence and delegation model:**

```bash
# Read the routing engine to understand existing intelligence
cat src/hopper/intelligence/rules/engine.py

# Check the TaskDelegation model (created by task-delegation worker)
cat src/hopper/models/task_delegation.py

# Read the task delegation repository
cat src/hopper/database/repositories/task_delegation_repository.py

# Look at existing service patterns
ls -la src/hopper/services/
cat src/hopper/services/*.py | head -100
```

**Then:** Create the `src/hopper/delegation/` package structure and start with `delegator.py` implementing the core delegation logic.

## Objectives

1. **Create Delegation Package** (`src/hopper/delegation/`)
   ```
   delegation/
   ├── __init__.py
   ├── delegator.py      # Main delegation logic
   ├── router.py         # Instance-to-instance routing
   ├── completion.py     # Completion bubbling
   └── policies.py       # Delegation policies per scope
   ```

2. **Implement Delegator Class** (`delegator.py`)
   - `delegate_task(task, target_instance)` - Delegate task down hierarchy
   - `accept_delegation(delegation_id)` - Accept incoming delegation
   - `reject_delegation(delegation_id, reason)` - Reject with reason
   - `complete_delegation(delegation_id, result)` - Mark complete and trigger bubbling

3. **Implement CompletionBubbler** (`completion.py`)
   - `bubble_completion(task)` - Notify ancestors of completion
   - `aggregate_child_completions(parent_task)` - Check if all children done
   - `propagate_status_change(task, new_status)` - Status change notifications

4. **Implement InstanceRouter** (`router.py`)
   - `find_target_instance(task, source_instance)` - Determine delegation target
   - `can_delegate_to(source, target)` - Check delegation validity
   - `get_available_instances(scope)` - Get instances accepting tasks

5. **Implement DelegationPolicies** (`policies.py`)
   - `get_policy_for_scope(scope)` - Get delegation rules for scope
   - Policies define: auto-accept, require-approval, routing-rules

6. **Create Delegation API Endpoints** (`src/hopper/api/routes/delegations.py`)
   - `POST /api/v1/tasks/{id}/delegate` - Delegate task to instance
   - `POST /api/v1/delegations/{id}/accept` - Accept delegation
   - `POST /api/v1/delegations/{id}/reject` - Reject delegation
   - `POST /api/v1/delegations/{id}/complete` - Mark delegation complete
   - `GET /api/v1/instances/{id}/delegations` - Get delegations for instance
   - `GET /api/v1/tasks/{id}/delegation-chain` - Get full delegation chain

7. **Wire Up Router in app.py**
   - Add delegation router registration

8. **Write Tests**
   - Unit tests for each module in `tests/delegation/`
   - Integration tests for delegation flows

## Deliverables

- [ ] `src/hopper/delegation/` package with all modules
- [ ] `src/hopper/api/routes/delegations.py` - Delegation API endpoints
- [ ] Updated `src/hopper/api/app.py` - Router wired up
- [ ] `tests/delegation/test_delegator.py` - Delegator tests
- [ ] `tests/delegation/test_completion.py` - Completion bubbling tests
- [ ] `tests/delegation/test_router.py` - Router tests
- [ ] Integration tests for delegation flows

## Success Criteria

- [ ] Tasks can be delegated from Global → Project → Orchestration
- [ ] Completion bubbles up the chain automatically
- [ ] Rejected delegations are handled gracefully (task stays at source)
- [ ] Delegation chain is fully traceable for any task
- [ ] Policies control delegation behavior per scope
- [ ] 90%+ test coverage on new code

## Context

### Delegation Flow

```
1. Task created at Global Instance
2. Delegator.delegate_task() called
3. InstanceRouter.find_target_instance() determines Project
4. TaskDelegation record created (status=pending)
5. If auto-accept policy, delegation accepted immediately
6. Task's instance_id updated to target
7. Repeat for Project → Orchestration

On completion:
1. Task marked complete at Orchestration
2. CompletionBubbler.bubble_completion() called
3. Delegation record marked complete with result
4. Parent delegation's task status updated
5. Repeat up to Global
```

### Routing Intelligence Integration

The existing routing engine (`src/hopper/intelligence/rules/engine.py`) provides:
- Tag-based routing
- Content analysis
- Priority handling

The InstanceRouter should use this intelligence to determine which Project instance should receive a task from Global.

### Policies Example

```python
GLOBAL_POLICY = DelegationPolicy(
    auto_accept=False,  # Projects must accept
    routing_strategy="tag_match",
    fallback_instance=None,  # Error if no match
)

PROJECT_POLICY = DelegationPolicy(
    auto_accept=True,  # Orchestrations auto-accept
    routing_strategy="load_balance",
    fallback_instance="default-orchestration",
)
```

### Key Integration Points

- **Task Model**: Already has `instance_id` FK
- **TaskDelegation Model**: Created by task-delegation worker
- **HopperInstance Model**: Has hierarchy methods
- **Routing Engine**: Provides intelligence for routing decisions

## Notes

- Use async/await throughout - all database operations are async
- Handle edge cases: circular delegation, deleted instances, error recovery
- Consider using database transactions for multi-step operations
- Log all delegation events for debugging
- The completion bubbler should be idempotent (safe to call multiple times)
