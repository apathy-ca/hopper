# Worker: Testing

**Branch:** cz2/feat/testing
**Dependencies:** instance-visualization
**Duration:** 2 days

## Mission

Create comprehensive test suite for Phase 2 multi-instance features, ensuring quality and reliability of the hierarchical architecture.

## Background

Phase 2 introduces significant complexity with multi-instance hierarchy. Testing must cover:
- Instance lifecycle and state management
- Parent-child relationships
- Task delegation flows
- Scope-specific behaviors
- Visualization tools
- End-to-end multi-instance workflows

## Tasks

### Task 1: Instance Architecture Tests

1. Enhance `tests/instance/`:
   - test_lifecycle_advanced.py - Complex state transitions
   - test_manager_advanced.py - Multi-instance management
   - test_configuration.py - Scope-specific configs

2. Test scenarios:
   - Concurrent instance operations
   - State transition edge cases
   - Configuration validation
   - Resource cleanup

**Checkpoint:** Commit architecture tests

### Task 2: Registry and Discovery Tests

1. Create registry test suite:
   - test_registry_concurrent.py - Concurrent registration
   - test_discovery_performance.py - Discovery at scale
   - test_relationships_complex.py - Deep hierarchies
   - test_health_monitoring.py - Health checks

2. Test scenarios:
   - Large number of instances (100+)
   - Deep hierarchies (5+ levels)
   - Rapid registration/deregistration
   - Network partitions

**Checkpoint:** Commit registry tests

### Task 3: Delegation Protocol Tests

1. Create delegation test suite:
   - test_delegation_flows.py - Various delegation patterns
   - test_completion_bubbling.py - Status propagation
   - test_delegation_failures.py - Error handling
   - test_coordination.py - State consistency

2. Test scenarios:
   - Task delegation chain (Global→Project→Orchestration)
   - Completion bubbling back up
   - Delegation rejections
   - Concurrent delegations
   - Delegation failures and retries

**Checkpoint:** Commit delegation tests

### Task 4: Scope Behavior Tests

1. Create scope-specific tests:
   - test_global_routing.py - Global routing decisions
   - test_project_orchestration_decision.py - Orchestration triggers
   - test_orchestration_queue_management.py - Worker queues
   - test_scope_intelligence.py - Intelligence layer

2. Test scenarios:
   - Global routes to correct project
   - Project correctly decides orchestration vs manual
   - Orchestration manages dependencies
   - Intelligence improves routing

**Checkpoint:** Commit scope tests

### Task 5: Integration and E2E Tests

1. Create `tests/e2e/test_multi_instance_workflows.py`:
   - Complete task lifecycle across all scopes
   - Real delegation and completion flow
   - Czarina integration scenario
   - Instance hierarchy operations

2. Test complete workflows:
   ```
   1. Create Global instance
   2. Create task at Global
   3. Global routes to Project
   4. Project creates Orchestration
   5. Orchestration manages workers
   6. Task completes
   7. Completion bubbles up
   8. Verify state at all levels
   ```

3. Create `tests/e2e/test_czarina_integration.py`:
   - Hopper provides tasks to Czarina orchestration
   - Czarina workers execute
   - Status updates flow back
   - Integration points work correctly

**Checkpoint:** Commit integration tests

### Task 6: Visualization and CLI Tests

1. Create CLI test suite:
   - test_tree_command.py - Tree visualization
   - test_dashboard_command.py - Dashboard rendering
   - test_flow_visualization.py - Task flow
   - test_interactive_explorer.py - Interactive mode

2. Test output formatting:
   - ASCII tree structure correct
   - Dashboard updates properly
   - Flow visualization accurate
   - Interactive navigation works

**Checkpoint:** Commit CLI tests

### Task 7: Performance and Load Tests

1. Create `tests/performance/`:
   - test_hierarchy_performance.py - Query performance
   - test_delegation_throughput.py - Delegation rate
   - test_concurrent_instances.py - Concurrent operations
   - test_memory_usage.py - Resource consumption

2. Performance benchmarks:
   - Hierarchy query < 100ms
   - Delegation < 50ms
   - 1000+ instances supported
   - Memory usage reasonable

**Checkpoint:** Commit performance tests

### Task 8: Phase 2 Success Criteria Validation

Create `tests/validation/test_phase2_criteria.py`:

1. ✅ Can create Global, Project, and Orchestration instances
2. ✅ Tasks flow down hierarchy (Global → Project → Orchestration)
3. ✅ Completion bubbles up hierarchy
4. ✅ Each scope has appropriate configuration
5. ✅ Can visualize instance tree
6. ✅ Czarina can use Orchestration Hopper for runs

Validate each criterion with comprehensive tests.

**Checkpoint:** Commit criteria validation

### Task 9: Test Coverage and Quality

1. Run coverage analysis:
   ```bash
   pytest --cov=src/hopper/instance --cov-report=html
   ```

2. Coverage targets:
   - instance/ module: >95%
   - delegation protocol: >95%
   - scope behaviors: >90%
   - Overall Phase 2 code: >90%

3. Add missing tests for uncovered code

4. Update `docs/testing.md` with Phase 2 testing guide

**Checkpoint:** Commit coverage improvements

## Deliverables

- [ ] Instance architecture tests (lifecycle, manager, config)
- [ ] Registry and discovery tests
- [ ] Delegation protocol tests
- [ ] Scope behavior tests
- [ ] Integration and E2E tests
- [ ] Czarina integration tests
- [ ] CLI and visualization tests
- [ ] Performance and load tests
- [ ] Phase 2 success criteria validation
- [ ] >90% code coverage for Phase 2 features
- [ ] Updated testing documentation

## Success Criteria

- ✅ All Phase 2 features have comprehensive tests
- ✅ Integration tests cover complete workflows
- ✅ E2E tests validate multi-instance behavior
- ✅ Performance tests ensure scalability
- ✅ All Phase 2 success criteria validated
- ✅ Code coverage >90% for new features
- ✅ All tests pass consistently
- ✅ CI pipeline includes Phase 2 tests

## References

- Implementation Plan: Phase 2 success criteria
- Phase 1 testing patterns
- pytest best practices

## Notes

- Test multi-instance complexity thoroughly
- Integration tests critical for Phase 2
- Performance tests ensure production readiness
- E2E tests validate complete user workflows
- Consider chaos testing for resilience
- Test with realistic orchestration scenarios
- Mock external Czarina when needed
- Ensure tests are deterministic and fast
