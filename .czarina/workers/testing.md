# Worker: Testing

**Branch:** cz1/feat/testing
**Dependencies:** mcp-integration, cli-tool, routing-engine
**Duration:** 2 days

## Mission

Create a comprehensive test suite for all Phase 1 features, ensuring quality and reliability before integration. This worker focuses on testing coverage, integration tests, and end-to-end workflows.

## Background

All previous workers created unit tests for their components. This worker:
- Ensures comprehensive test coverage across all components
- Creates integration tests that span multiple systems
- Implements end-to-end workflow tests
- Sets up test infrastructure and utilities
- Validates all Phase 1 success criteria

## Tasks

### Task 1: Test Infrastructure and Utilities

1. Create `tests/conftest.py` (enhance existing):
   - Comprehensive pytest fixtures
   - Database fixtures (PostgreSQL and SQLite)
   - API client fixtures
   - MCP client fixtures
   - CLI runner fixtures
   - Mock data factories
   - Test configuration

2. Create `tests/factories.py`:
   - Factory pattern for test data
   - TaskFactory for creating test tasks
   - ProjectFactory for test projects
   - InstanceFactory for test instances
   - UserFactory for test users
   - Realistic test data generation

3. Create `tests/utils.py`:
   - Common test utilities
   - Assertion helpers
   - Data validation helpers
   - Database cleanup utilities
   - Mock response builders

4. Create `tests/fixtures/` directory:
   - Sample YAML routing rules
   - Sample configuration files
   - Sample task data (JSON)
   - Sample project data

**Checkpoint:** Commit test infrastructure

### Task 2: Integration Tests - API Layer

1. Create `tests/integration/test_api_database.py`:
   - Test API endpoints with real database
   - Test task CRUD through API
   - Test project CRUD through API
   - Test instance CRUD through API
   - Test data persistence
   - Test transaction handling
   - Test concurrent requests

2. Create `tests/integration/test_api_routing.py`:
   - Test routing through API
   - Test rule evaluation via API
   - Test decision recording
   - Test feedback collection
   - Test routing analytics

3. Create `tests/integration/test_api_auth.py`:
   - Test full authentication flow
   - Test JWT token lifecycle
   - Test API key authentication
   - Test permission checks
   - Test unauthorized access

**Checkpoint:** Commit API integration tests

### Task 3: Integration Tests - MCP Layer

1. Create `tests/integration/test_mcp_api.py`:
   - Test MCP tools calling API
   - Test task creation via MCP
   - Test task listing via MCP
   - Test routing via MCP
   - Test error handling in MCP
   - Test context preservation

2. Create `tests/integration/test_mcp_context.py`:
   - Test context management across tool calls
   - Test session persistence
   - Test active project context
   - Test conversation state

3. Create `tests/integration/test_mcp_resources.py`:
   - Test resource access
   - Test resource URIs
   - Test resource updates

**Checkpoint:** Commit MCP integration tests

### Task 4: Integration Tests - CLI Layer

1. Create `tests/integration/test_cli_api.py`:
   - Test CLI commands calling API
   - Test task commands end-to-end
   - Test project commands end-to-end
   - Test instance commands end-to-end
   - Test configuration commands
   - Test authentication flow

2. Create `tests/integration/test_cli_output.py`:
   - Test table output formatting
   - Test JSON output
   - Test color output
   - Test error message formatting

**Checkpoint:** Commit CLI integration tests

### Task 5: End-to-End Workflow Tests

Reference: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (Success Criteria)

1. Create `tests/e2e/test_task_lifecycle.py`:
   - Test complete task lifecycle:
     1. Create task via MCP
     2. Task appears in database
     3. Task appears in CLI listing
     4. Update task via CLI
     5. Update appears in API
     6. Update appears in MCP
     7. Complete task
     8. Archive task

2. Create `tests/e2e/test_routing_workflow.py`:
   - Test routing workflow:
     1. Create task without destination
     2. Request routing suggestions via API
     3. Route task using rules engine
     4. Decision recorded in database
     5. Task assigned to destination
     6. Provide feedback on routing
     7. Feedback affects future routing

3. Create `tests/e2e/test_multi_interface.py`:
   - Test same task across all interfaces:
     1. Create via API
     2. View via CLI
     3. Update via MCP
     4. Delete via API
     5. Verify consistency

4. Create `tests/e2e/test_project_workflow.py`:
   - Test project-based workflow:
     1. Create project
     2. Configure routing rules
     3. Create tasks for project
     4. Verify auto-routing
     5. Get project statistics
     6. Archive project

5. Create `tests/e2e/test_docker_deployment.py`:
   - Test Docker-based deployment:
     1. Start services via docker-compose
     2. Run migrations
     3. Seed database
     4. Test API health
     5. Test MCP connection
     6. Test CLI commands
     7. Shutdown cleanly

**Checkpoint:** Commit end-to-end workflow tests

### Task 6: Test Coverage and Quality Assurance

1. Run coverage analysis:
   ```bash
   pytest --cov=src/hopper --cov-report=html --cov-report=term
   ```

2. Create `tests/coverage_check.py`:
   - Script to verify coverage thresholds
   - Minimum 90% coverage for core modules
   - Minimum 80% coverage overall
   - Report uncovered critical paths

3. Identify and fill coverage gaps:
   - Review coverage report
   - Add tests for uncovered code
   - Focus on critical paths
   - Add edge case tests

4. Create test documentation in `docs/testing.md`:
   - Test strategy overview
   - Running tests locally
   - Running tests in Docker
   - Coverage requirements
   - Writing new tests
   - Test fixtures and factories
   - Mock data guidelines

5. Add test commands to `Makefile` or `scripts/`:
   - `make test` - Run all tests
   - `make test-unit` - Run unit tests only
   - `make test-integration` - Run integration tests
   - `make test-e2e` - Run end-to-end tests
   - `make coverage` - Generate coverage report
   - `make test-watch` - Run tests on file changes

**Checkpoint:** Commit coverage improvements and documentation

### Task 7: Phase 1 Success Criteria Validation

Reference: Phase 1 success criteria from Implementation Plan

Create `tests/validation/test_phase1_criteria.py`:

1. ✅ Can create tasks via HTTP API
2. ✅ Can create tasks via MCP (from Claude)
3. ✅ Can create tasks via CLI
4. ✅ Tasks stored in database with proper schema
5. ✅ Basic rules-based routing works
6. ✅ Can list and query tasks with filters
7. ✅ Docker Compose setup for local development

For each criterion, create a test that validates it works end-to-end.

**Checkpoint:** Commit success criteria validation tests

## Deliverables

- [ ] Enhanced test infrastructure and utilities
- [ ] Test factories for all entities
- [ ] API integration tests
- [ ] MCP integration tests
- [ ] CLI integration tests
- [ ] End-to-end workflow tests (task lifecycle, routing, multi-interface, project)
- [ ] Docker deployment test
- [ ] >90% code coverage for core modules
- [ ] >80% overall code coverage
- [ ] Phase 1 success criteria validation tests
- [ ] Testing documentation

## Success Criteria

- ✅ All existing tests pass
- ✅ Code coverage >90% for src/hopper/models/
- ✅ Code coverage >90% for src/hopper/intelligence/
- ✅ Code coverage >85% for src/hopper/api/
- ✅ Code coverage >80% overall
- ✅ Integration tests cover all major workflows
- ✅ End-to-end tests validate Phase 1 requirements
- ✅ Docker deployment test passes
- ✅ All Phase 1 success criteria validated
- ✅ Tests run in CI successfully
- ✅ Testing documentation is comprehensive

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md`
- Testing Strategy: `/home/jhenry/Source/hopper/plans/Hopper-Testing-and-Deployment.md`
- pytest documentation: https://docs.pytest.org/
- pytest-cov: https://pytest-cov.readthedocs.io/

## Notes

- Use pytest for all testing (standard Python testing framework)
- Use pytest-asyncio for async tests
- Use pytest-cov for coverage tracking
- Factory pattern makes test data generation easier
- Fixtures should be reusable across test modules
- Integration tests use real database (Docker or in-memory SQLite)
- End-to-end tests should be realistic workflows
- Mock external services (don't call real GitHub/GitLab in tests)
- Test both success and error cases
- Test edge cases and boundary conditions
- Keep tests fast (use SQLite in-memory for unit tests)
- Integration tests can use PostgreSQL Docker container
- Parallel test execution for speed (pytest-xdist)
- Test isolation is critical (each test should be independent)
- Clean up test data between tests
- Consider property-based testing for complex logic (hypothesis)
