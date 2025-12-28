# Hopper Testing Guide

Comprehensive testing documentation for the Hopper task routing system.

## Table of Contents

1. [Overview](#overview)
2. [Test Structure](#test-structure)
3. [Running Tests](#running-tests)
4. [Test Categories](#test-categories)
5. [Writing New Tests](#writing-new-tests)
6. [Test Fixtures and Factories](#test-fixtures-and-factories)
7. [Coverage Requirements](#coverage-requirements)
8. [CI/CD Integration](#cicd-integration)

## Overview

Hopper uses a comprehensive testing strategy with three levels of tests:

- **Unit Tests (60%)**: Fast, isolated tests for individual components
- **Integration Tests (30%)**: Tests spanning multiple components (API, Database, MCP, CLI)
- **End-to-End Tests (10%)**: Complete workflow tests across all interfaces

### Testing Stack

- **pytest**: Test runner and framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage tracking
- **pytest-xdist**: Parallel test execution
- **FastAPI TestClient**: API testing
- **Click CliRunner**: CLI testing
- **SQLAlchemy**: Database testing with in-memory SQLite

## Test Structure

```
tests/
├── conftest.py              # Pytest configuration and shared fixtures
├── factories.py             # Test data factories
├── utils.py                 # Common test utilities
├── fixtures/                # Sample test data
│   ├── routing_rules.yaml
│   ├── tasks/
│   ├── projects/
│   └── configuration/
├── unit/                    # Unit tests (fast, isolated)
│   ├── test_models.py
│   ├── test_config.py
│   └── test_intelligence_rules.py
├── integration/             # Integration tests (multiple components)
│   ├── test_api_database.py
│   ├── test_api_routing.py
│   ├── test_api_auth.py
│   ├── test_mcp_api.py
│   ├── test_mcp_context.py
│   ├── test_mcp_resources.py
│   ├── test_cli_api.py
│   └── test_cli_output.py
├── e2e/                     # End-to-end tests (full workflows)
│   ├── test_task_lifecycle.py
│   ├── test_routing_workflow.py
│   ├── test_multi_interface.py
│   ├── test_project_workflow.py
│   └── test_docker_deployment.py
└── validation/              # Success criteria validation
    └── test_phase1_criteria.py
```

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test Categories

```bash
# Unit tests only (fast)
pytest -m unit

# Integration tests
pytest -m integration

# End-to-end tests
pytest -m e2e

# Skip slow tests
pytest -m "not slow"
```

### Run Specific Test Files

```bash
# Run API integration tests
pytest tests/integration/test_api_database.py

# Run task lifecycle tests
pytest tests/e2e/test_task_lifecycle.py

# Run Phase 1 validation
pytest tests/validation/test_phase1_criteria.py
```

### Run Tests in Parallel

```bash
# Use all CPU cores
pytest -n auto

# Use specific number of workers
pytest -n 4
```

### Run with Coverage

```bash
# Generate coverage report
pytest --cov=src/hopper --cov-report=html --cov-report=term

# View HTML coverage report
open htmlcov/index.html
```

### Run Tests with Verbose Output

```bash
# Show all test names
pytest -v

# Show print statements
pytest -s

# Show local variables on failure
pytest -l
```

## Test Categories

### Unit Tests

Fast, isolated tests for individual components. Mock external dependencies.

**Markers**: `@pytest.mark.unit`

**Examples**:
- Model validation
- Configuration parsing
- Rule matching logic
- Utility functions

**Characteristics**:
- Run in < 1 second
- No database connections
- No API calls
- Heavy use of mocks

### Integration Tests

Tests spanning multiple components with real dependencies.

**Markers**: `@pytest.mark.integration`

**Examples**:
- API endpoints with database
- MCP tools calling API
- CLI commands with API backend
- Authentication flows

**Characteristics**:
- Use in-memory SQLite or PostgreSQL
- Real HTTP requests (via TestClient)
- Test component interactions
- May require setup/teardown

### End-to-End Tests

Complete workflow tests simulating real user scenarios.

**Markers**: `@pytest.mark.e2e`

**Examples**:
- Complete task lifecycle (create → route → complete → archive)
- Multi-interface consistency (MCP → API → CLI)
- Project workflows
- Docker deployment

**Characteristics**:
- Longest running tests
- Test entire feature flows
- Use all system components
- Validate business requirements

### PostgreSQL Tests

Tests requiring PostgreSQL database.

**Markers**: `@pytest.mark.postgres`

**Setup**:
```bash
# Start PostgreSQL via Docker
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=hopper postgres:15

# Set environment variable
export TEST_DATABASE_URL="postgresql://hopper:hopper@localhost:5432/hopper_test"

# Run PostgreSQL tests
pytest -m postgres
```

### Slow Tests

Tests that take > 5 seconds to run.

**Markers**: `@pytest.mark.slow`

**Skip in development**:
```bash
pytest -m "not slow"
```

## Writing New Tests

### Test Structure

```python
import pytest
from tests.factories import TaskFactory
from tests.utils import assert_response_success


@pytest.mark.integration
class TestMyFeature:
    """Test description."""

    def test_specific_behavior(self, api_client, db_session):
        """Test that specific behavior works correctly."""
        # Arrange
        task = TaskFactory.create(session=db_session, title="Test")

        # Act
        response = api_client.get(f"/api/v1/tasks/{task.id}")

        # Assert
        assert_response_success(response)
        assert response.json()["title"] == "Test"
```

### Best Practices

1. **Use Descriptive Names**: Test names should describe what is being tested
2. **One Assertion Per Test**: Focus each test on a single behavior
3. **Arrange-Act-Assert**: Structure tests clearly
4. **Use Factories**: Generate test data with factories, not manual creation
5. **Clean Up**: Use fixtures for automatic cleanup
6. **Avoid Hardcoded Values**: Use constants or configuration
7. **Test Edge Cases**: Don't just test happy paths
8. **Mock External Services**: Don't call real GitHub/GitLab in tests

### Common Patterns

**Testing API Endpoints**:
```python
def test_create_task(self, api_client, db_session):
    response = api_client.post("/api/v1/tasks", json={"title": "Test"})
    assert_response_success(response, 201)

    task_id = response.json()["id"]

    # Verify in database
    task = db_session.query(Task).filter(Task.id == task_id).first()
    assert task is not None
```

**Testing CLI Commands**:
```python
def test_task_add(self, cli_runner):
    from hopper.cli.main import cli

    result = cli_runner.invoke(cli, ['task', 'add', '--title', 'Test'])
    assert_cli_success(result)
```

**Testing MCP Tools**:
```python
def test_mcp_create_task(self, mcp_client, db_session):
    tool_call = build_mcp_tool_call(
        "hopper_create_task",
        {"title": "Test"}
    )

    response = {"result": {"id": "task-1", "title": "Test"}}
    assert_mcp_tool_response_valid(response)
```

## Test Fixtures and Factories

### Available Fixtures

See `tests/conftest.py` for complete list.

**Database Fixtures**:
- `sqlite_engine`: In-memory SQLite engine
- `db_session`: SQLAlchemy session with auto-rollback
- `postgres_engine`: PostgreSQL engine (requires PostgreSQL)
- `postgres_session`: PostgreSQL session with auto-rollback

**API Fixtures**:
- `api_client`: FastAPI TestClient
- `authenticated_api_client`: TestClient with JWT token

**CLI Fixtures**:
- `cli_runner`: Click CliRunner
- `cli_config_dir`: Temporary config directory
- `cli_runner_with_config`: CliRunner with isolated config

**MCP Fixtures**:
- `mcp_client`: Mock MCP client
- `mcp_context`: MCP conversation context

**Data Fixtures**:
- `sample_task_data`: Sample task dictionary
- `sample_project_data`: Sample project dictionary
- `sample_instance_data`: Sample instance dictionary

### Using Factories

```python
from tests.factories import TaskFactory, ProjectFactory

# Create single instance
task = TaskFactory.create(session=db_session, title="Custom Title")

# Create batch
tasks = TaskFactory.create_batch(5, session=db_session, project="hopper")

# Create with specific status
task = TaskFactory.create_pending(session=db_session)
task = TaskFactory.create_completed(session=db_session)

# Create related objects
task, decision = create_task_with_routing(session=db_session)
task, feedback = create_task_with_feedback(session=db_session)

# Create complete workflow
workflow = create_complete_task_workflow(session=db_session)
# Returns: {"task": task, "decision": decision, "feedback": feedback, "mapping": mapping}
```

### Available Factories

- `TaskFactory`: Create tasks
- `ProjectFactory`: Create projects
- `HopperInstanceFactory`: Create instances
- `RoutingDecisionFactory`: Create routing decisions
- `TaskFeedbackFactory`: Create feedback
- `ExternalMappingFactory`: Create external mappings

## Coverage Requirements

### Target Coverage

- **Overall**: ≥ 80%
- **Models** (`src/hopper/models/`): ≥ 90%
- **Intelligence** (`src/hopper/intelligence/`): ≥ 90%
- **API** (`src/hopper/api/`): ≥ 85%
- **CLI** (`src/hopper/cli/`): ≥ 75%
- **MCP** (`src/hopper/mcp/`): ≥ 75%

### Check Coverage

```bash
# Generate coverage report
pytest --cov=src/hopper --cov-report=term-missing

# Generate HTML report
pytest --cov=src/hopper --cov-report=html
open htmlcov/index.html

# Fail if coverage below threshold
pytest --cov=src/hopper --cov-fail-under=80
```

### Coverage Configuration

See `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = [
    "--cov=hopper",
    "--cov-report=term-missing",
]
```

## CI/CD Integration

### GitHub Actions

Tests run automatically on:
- Push to `main` or feature branches
- Pull requests
- Nightly builds

### Test Workflow

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: hopper
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run tests
        run: |
          pytest --cov=src/hopper --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Docker Testing

### Running Tests in Docker

```bash
# Build test image
docker build -t hopper-test -f Dockerfile.test .

# Run all tests
docker run hopper-test pytest

# Run with coverage
docker run hopper-test pytest --cov=src/hopper

# Run specific tests
docker run hopper-test pytest tests/integration/
```

### Docker Compose Testing

```bash
# Start services
docker-compose -f docker-compose.test.yml up -d

# Run tests
docker-compose -f docker-compose.test.yml run test pytest

# Cleanup
docker-compose -f docker-compose.test.yml down
```

## Troubleshooting

### Tests Fail Locally But Pass in CI

- Check Python version matches CI
- Ensure database is clean (migrations applied)
- Check environment variables
- Run with same pytest options as CI

### Slow Tests

```bash
# Find slowest tests
pytest --durations=10

# Run tests in parallel
pytest -n auto

# Skip slow tests during development
pytest -m "not slow"
```

### Database Issues

```bash
# Reset database
docker-compose down -v
docker-compose up -d

# Check database connection
python -c "from hopper.database import engine; engine.connect()"
```

### Import Errors

```bash
# Reinstall in development mode
pip install -e ".[dev]"

# Check PYTHONPATH
echo $PYTHONPATH
```

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Click Testing](https://click.palletsprojects.com/en/latest/testing/)
- [SQLAlchemy Testing](https://docs.sqlalchemy.org/en/latest/core/testing.html)
- [Hopper Implementation Plan](/plans/Hopper-Implementation-Plan.md)
- [Hopper Testing Strategy](/plans/Hopper-Testing-and-Deployment.md)
