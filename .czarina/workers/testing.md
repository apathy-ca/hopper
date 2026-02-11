# Worker Identity: testing

**Role:** Test
**Agent:** claude
**Branch:** cz2/feat/testing
**Phase:** 2
**Dependencies:** instance-cli

## Mission

Create a comprehensive test suite for all Phase 2 features. Ensure 90%+ test coverage on new code, write integration tests that verify the full delegation flow, and fix any test regressions. Quality is the gatekeeper for the release.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/testing-knowledge.md`

This includes:
- pytest patterns for async testing
- Fixture design patterns
- Mocking strategies for database and API tests
- Integration testing best practices
- Coverage requirements and tools

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Assess the current test infrastructure and coverage:**

```bash
# Check existing test structure
ls -la tests/
ls -la tests/*/ 2>/dev/null

# Read the main conftest for existing fixtures
cat tests/conftest.py

# Check current test count and pass rate
pytest --collect-only 2>/dev/null | tail -20

# Look at existing test patterns
cat $(ls tests/test_*.py tests/*/test_*.py 2>/dev/null | head -1)

# Check for any pytest configuration
cat pyproject.toml | grep -A30 "\[tool.pytest"
```

**Then:** Create the Phase 2 test structure at `tests/phase2/` and start with `conftest.py` for Phase 2 specific fixtures.

## Objectives

1. **Create Phase 2 Test Structure**
   ```
   tests/
   ├── phase2/
   │   ├── __init__.py
   │   ├── conftest.py              # Phase 2 fixtures
   │   ├── test_instance_api.py     # Instance API tests
   │   ├── test_delegation.py       # Delegation tests
   │   ├── test_scope_behaviors.py  # Scope behavior tests
   │   ├── test_instance_cli.py     # CLI tests
   │   └── test_integration.py      # End-to-end flows
   ```

2. **Create Phase 2 Fixtures** (`conftest.py`)
   - `global_instance` - A Global Hopper instance
   - `project_instance` - A Project instance (child of global)
   - `orchestration_instance` - An Orchestration instance (child of project)
   - `instance_hierarchy` - Complete 3-level hierarchy
   - `task_with_delegation` - Task with delegation records
   - `mock_scope_behaviors` - Mocked scope behaviors for unit tests

3. **Instance API Tests** (`test_instance_api.py`)
   - CRUD operations (create, read, update, delete)
   - List with filters (scope, status, parent_id)
   - Hierarchy queries (children, full tree)
   - Lifecycle transitions (start, stop, pause, resume)
   - Error handling (404, validation errors)

4. **Delegation Tests** (`test_delegation.py`)
   - Create delegation record
   - Accept/reject delegation flow
   - Completion bubbling
   - Delegation chain tracing
   - Edge cases (orphaned delegations, circular prevention)

5. **Scope Behavior Tests** (`test_scope_behaviors.py`)
   - Global scope routing decisions
   - Project scope orchestration decisions
   - Orchestration scope queue management
   - Behavior configuration
   - Routing engine integration

6. **CLI Tests** (`test_instance_cli.py`)
   - All instance commands (list, create, show, tree, status)
   - Tree visualization output
   - Status dashboard output
   - Task filtering by instance
   - Delegation CLI commands

7. **Integration Tests** (`test_integration.py`)
   - **Full delegation flow**:
     - Task created at Global → routed to Project → delegated to Orchestration → completed → bubbled up
   - Multi-instance coordination
   - Failure recovery scenarios
   - Concurrent operations

8. **Fix Existing Failing Tests**
   - Review Phase 1 test failures
   - Fix tests broken by Phase 2 changes
   - Ensure no regressions

9. **Coverage Report**
   - Generate coverage report for Phase 2 code
   - Identify and fill coverage gaps
   - Document test scenarios

## Deliverables

- [ ] `tests/phase2/` test package with all files
- [ ] Phase 2 fixtures in `conftest.py`
- [ ] 90%+ coverage on all Phase 2 modules:
  - [ ] `src/hopper/api/routes/instances.py`
  - [ ] `src/hopper/api/routes/delegations.py`
  - [ ] `src/hopper/models/task_delegation.py`
  - [ ] `src/hopper/delegation/*`
  - [ ] `src/hopper/intelligence/scopes/*`
  - [ ] `src/hopper/cli/commands/instances.py`
- [ ] Integration test for full delegation flow
- [ ] All Phase 1 tests still passing
- [ ] Test documentation (describe test scenarios)

## Success Criteria

- [ ] 90%+ test coverage on new Phase 2 code
- [ ] All Phase 2 tests passing
- [ ] All Phase 1 tests still passing (no regressions)
- [ ] Integration tests pass for full delegation flow
- [ ] Coverage report generated and reviewed
- [ ] Edge cases and error conditions tested

## Context

### Test Categories

| Category | Focus | Speed | Dependencies |
|----------|-------|-------|--------------|
| Unit | Single component | Fast (<100ms) | Mocked |
| Integration | Multi-component | Medium (<10s) | Real DB |
| E2E | Full flow | Slow (>10s) | Full system |

### Key Test Scenarios

**Instance API:**
- Create Global, Project, Orchestration instances
- Validate parent-child relationships
- Test lifecycle state machine
- Verify hierarchy queries return correct tree

**Delegation:**
- Delegate from Global → Project → Orchestration
- Verify delegation records created at each step
- Test completion bubbling up the chain
- Test rejection handling

**Scope Behaviors:**
- Global routes to correct Project based on tags
- Project decides orchestration vs manual correctly
- Orchestration manages task queue properly

**Integration:**
```python
async def test_full_delegation_flow():
    # Create hierarchy
    global_instance = await create_global_instance()
    project = await create_project_instance(parent=global_instance)
    orchestration = await create_orchestration(parent=project)

    # Create task at global
    task = await create_task(instance=global_instance)

    # Trigger delegation
    await delegate_task(task)

    # Verify delegation chain
    chain = await get_delegation_chain(task)
    assert len(chain) == 2  # Global→Project, Project→Orchestration

    # Complete at orchestration level
    await complete_task(task)

    # Verify completion bubbled up
    assert task.status == "completed"
    for delegation in chain:
        assert delegation.status == "completed"
```

### Testing Tools

- **pytest** - Test framework
- **pytest-asyncio** - Async test support
- **pytest-cov** - Coverage reporting
- **httpx** - Async HTTP client for API tests
- **unittest.mock** - Mocking

### Phase 1 Test Status

Phase 1 tests at ~49% pass rate (131/267). Review failures and fix if related to Phase 2 changes, but don't spend excessive time on unrelated Phase 1 issues.

## Notes

- Use `@pytest.mark.asyncio` for all async tests
- Use fixtures extensively for test setup
- Mock external dependencies in unit tests
- Use real database for integration tests (consider test DB)
- Add test markers: `@pytest.mark.unit`, `@pytest.mark.integration`
- Consider parallel test execution with `pytest-xdist`
