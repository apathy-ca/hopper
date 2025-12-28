# Worker: Delegation Protocol

**Branch:** cz2/feat/delegation-protocol
**Dependencies:** instance-registry
**Duration:** 2-3 days

## Mission

Implement task delegation protocol between parent and child instances, including routing tasks down the hierarchy and bubbling completions back up.

## Background

Phase 2 Week 3 requires:
- Task delegation from parent to child instances
- Completion notification from child to parent
- Delegation routing decisions
- Task lifecycle across instances
- Coordination protocol

## Tasks

### Task 1: Delegation Core Protocol

1. Create `src/hopper/instance/delegation.py`:
   - DelegationProtocol class
   - Delegate task to child instance
   - Accept delegation from parent
   - Routing logic for delegation
   - Delegation history tracking

2. Create delegation message types:
   - TaskDelegation (parent → child)
   - TaskCompletion (child → parent)
   - TaskUpdate (bidirectional)
   - DelegationRejection (child → parent)

3. Implement delegation decision logic:
   - When to delegate vs handle locally
   - Which child to delegate to
   - Fallback if delegation fails

**Checkpoint:** Commit delegation protocol

### Task 2: Task Routing Across Instances

1. Enhance routing engine for multi-instance:
   - Global routes to best Project
   - Project routes to Orchestration or handles locally
   - Orchestration queues for workers

2. Create `src/hopper/instance/routing.py`:
   - Multi-instance routing logic
   - Scope-specific routing strategies
   - Delegation routing decisions

3. Add delegation to task model:
   - `delegated_from_instance_id`
   - `delegated_to_instance_id`
   - `delegation_chain` (track full path)

**Checkpoint:** Commit multi-instance routing

### Task 3: Completion and Status Bubbling

1. Create `src/hopper/instance/completion.py`:
   - Task completion notification
   - Status update propagation
   - Completion bubbling up hierarchy
   - Success/failure handling

2. Implement completion flow:
   - Worker completes task in Orchestration
   - Orchestration notifies Project
   - Project notifies Global
   - Each level updates local state

3. Add completion hooks:
   - on_task_completed
   - on_task_failed
   - on_delegation_completed

**Checkpoint:** Commit completion protocol

### Task 4: Coordination and Synchronization

1. Create `src/hopper/instance/coordination.py`:
   - Instance coordination protocol
   - State synchronization
   - Conflict resolution
   - Transaction coordination

2. Implement coordination patterns:
   - Request-response
   - Publish-subscribe
   - Event streaming

3. Add coordination for:
   - Task state consistency
   - Instance status sync
   - Configuration updates

**Checkpoint:** Commit coordination system

### Task 5: API and Integration

1. Add delegation endpoints:
   - `POST /api/v1/tasks/{id}/delegate` - Delegate task
   - `POST /api/v1/tasks/{id}/complete` - Mark complete
   - `GET /api/v1/tasks/{id}/delegation-chain` - View delegation path

2. Update task endpoints to support delegation
3. Add WebSocket support for real-time updates
4. Integrate with instance lifecycle

**Checkpoint:** Commit API integration

### Task 6: Testing and Documentation

1. Create test suite:
   - `tests/instance/test_delegation.py`
   - `tests/instance/test_completion.py`
   - `tests/instance/test_coordination.py`
   - `tests/integration/test_multi_instance_flow.py`

2. Create `docs/delegation-protocol.md`:
   - Delegation overview
   - Message types
   - Routing logic
   - Completion flow
   - Examples

**Checkpoint:** Commit tests and docs

## Deliverables

- [ ] Delegation protocol implementation
- [ ] Multi-instance routing logic
- [ ] Completion notification system
- [ ] Coordination protocol
- [ ] Delegation API endpoints
- [ ] Comprehensive tests including e2e flows
- [ ] Documentation

## Success Criteria

- ✅ Tasks flow down hierarchy (Global → Project → Orchestration)
- ✅ Completion bubbles up (Orchestration → Project → Global)
- ✅ Delegation decisions are logged
- ✅ Failed delegations have fallback
- ✅ State stays consistent across instances
- ✅ Real-time status updates work
- ✅ All tests pass

## References

- Implementation Plan: Phase 2, Week 3
- Specification: Delegation protocol section

## Notes

- Delegation must be reliable (retry logic)
- Completion notification critical for workflow
- Consider message queue for async communication
- Transaction coordination prevents inconsistency
- Test extensively with concurrent delegations
