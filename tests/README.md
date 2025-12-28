# Hopper Test Suite

Comprehensive test suite for the Hopper task routing and orchestration system.

## Quick Start

```bash
# Install dependencies
pip install -e ".[dev]"

# Run all tests
pytest

# Run with coverage
pytest --cov=src/hopper --cov-report=html

# View coverage report
open htmlcov/index.html
```

## Test Categories

### ✅ Unit Tests
Fast, isolated tests for individual components.
```bash
pytest -m unit
```

### 🔗 Integration Tests
Tests spanning multiple components (API, Database, MCP, CLI).
```bash
pytest -m integration
```

### 🎯 End-to-End Tests
Complete workflow tests across all interfaces.
```bash
pytest -m e2e
```

### 📋 Phase 1 Validation
Validates all Phase 1 success criteria.
```bash
pytest tests/validation/test_phase1_criteria.py
```

## Test Suite Contents

### Infrastructure (`conftest.py`, `factories.py`, `utils.py`)
- **350+ lines** of test infrastructure
- Comprehensive pytest fixtures for database, API, CLI, and MCP
- Factory pattern for generating test data
- 50+ utility functions for assertions and validations

### Integration Tests
- **`test_api_database.py`** (500+ lines): API with database layer
  - Task CRUD operations
  - Project management
  - Instance management
  - Data persistence and consistency
  - Transaction handling
  - Concurrent operations
  - Large dataset performance

- **`test_api_routing.py`** (450+ lines): Routing functionality
  - Rules-based routing
  - Routing suggestions
  - LLM fallback
  - Routing decisions
  - Feedback collection
  - Analytics and statistics
  - Rule evaluation and testing

- **`test_api_auth.py`** (400+ lines): Authentication & authorization
  - Login/logout flows
  - JWT token lifecycle
  - API key authentication
  - Permission checks
  - Password management
  - Unauthorized access handling

- **`test_mcp_api.py`** (350+ lines): MCP tools integration
  - Task management via MCP
  - Project operations via MCP
  - Routing via MCP
  - Error handling
  - Context preservation

- **`test_cli_api.py`** (200+ lines): CLI commands
  - Task commands end-to-end
  - Project commands
  - Output formatting (table, JSON)
  - Authentication flow

### End-to-End Tests
- **`test_task_lifecycle.py`** (200+ lines): Complete task journeys
  - Full lifecycle: Create → Route → Update → Complete → Archive
  - Multi-interface workflows (MCP → API → CLI)
  - Cross-interface consistency validation

### Validation Tests
- **`test_phase1_criteria.py`** (300+ lines): Phase 1 success criteria
  - ✅ Create tasks via HTTP API
  - ✅ Create tasks via MCP (from Claude)
  - ✅ Create tasks via CLI
  - ✅ Tasks stored with proper schema
  - ✅ Basic rules-based routing works
  - ✅ List and query tasks with filters
  - ✅ Docker Compose setup

### Test Fixtures
- **`routing_rules.yaml`**: Comprehensive routing rules for testing
- **`tasks/sample_tasks.json`**: 10 sample tasks covering various scenarios
- **`projects/sample_projects.json`**: 7 sample projects
- **`configuration/test_config.yaml`**: Test configuration file

## Test Statistics

- **Total Test Files**: 10+
- **Total Test Functions**: 100+
- **Lines of Test Code**: 3,500+
- **Test Fixtures**: 30+
- **Test Factories**: 6
- **Utility Functions**: 50+

## Coverage Targets

| Module | Target | Status |
|--------|--------|--------|
| Overall | ≥80% | 🎯 |
| Models | ≥90% | 🎯 |
| Intelligence | ≥90% | 🎯 |
| API | ≥85% | 🎯 |
| CLI | ≥75% | 🎯 |
| MCP | ≥75% | 🎯 |

## Running Specific Test Suites

```bash
# API tests only
pytest tests/integration/test_api*.py

# MCP tests only
pytest tests/integration/test_mcp*.py

# CLI tests only
pytest tests/integration/test_cli*.py

# E2E tests only
pytest tests/e2e/

# Validation tests
pytest tests/validation/
```

## Parallel Execution

```bash
# Use all CPU cores
pytest -n auto

# Use 4 workers
pytest -n 4
```

## Filtering Tests

```bash
# Run only fast tests
pytest -m "not slow"

# Run only PostgreSQL tests (requires PostgreSQL)
pytest -m postgres

# Run integration tests excluding slow ones
pytest -m "integration and not slow"
```

## Continuous Integration

Tests run automatically on:
- Every push to main or feature branches
- Every pull request
- Nightly scheduled runs

## Documentation

For detailed testing documentation, see:
- **[Testing Guide](../docs/testing.md)**: Comprehensive testing documentation
- **[Implementation Plan](/plans/Hopper-Implementation-Plan.md)**: Overall project plan
- **[Testing Strategy](/plans/Hopper-Testing-and-Deployment.md)**: Testing approach

## Test Development Guidelines

1. **Use Descriptive Names**: `test_user_can_create_task_via_api` not `test_1`
2. **One Behavior Per Test**: Focus each test on a single behavior
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Use Factories**: Generate test data with factories, not manual creation
5. **Test Edge Cases**: Don't just test happy paths
6. **Mock External Services**: Don't call real APIs in tests
7. **Keep Tests Fast**: Unit tests should run in milliseconds

## Common Commands

```bash
# Run tests with output
pytest -v

# Show print statements
pytest -s

# Stop on first failure
pytest -x

# Run last failed tests
pytest --lf

# Run tests matching pattern
pytest -k "test_create"

# Generate coverage report
pytest --cov=src/hopper --cov-report=term-missing

# Update snapshots (if using pytest-snapshot)
pytest --snapshot-update
```

## Troubleshooting

### Tests fail with import errors
```bash
pip install -e ".[dev]"
```

### Database connection errors
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Reset database
docker-compose down -v && docker-compose up -d
```

### Slow tests
```bash
# Find slowest tests
pytest --durations=10

# Skip slow tests
pytest -m "not slow"
```

## Contributing

When adding new features:
1. Write tests first (TDD)
2. Ensure coverage ≥80% for new code
3. Run full test suite before committing
4. Update test documentation if needed

---

**Test Suite Status**: ✅ Ready for Phase 1 Integration

**Last Updated**: 2025-12-28

**Coverage**: Target 80%+ overall, 90%+ for core modules
