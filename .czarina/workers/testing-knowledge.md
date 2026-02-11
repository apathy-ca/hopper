# Knowledge Base: testing

Custom knowledge for the Testing worker, extracted from agent-knowledge library.

## Testing Philosophy

### The Golden Rules

1. **Write tests** - Every feature needs tests
2. **Test behavior, not implementation** - Tests should survive refactoring
3. **Keep tests simple** - Tests should be easier to read than code
4. **Fast feedback** - Unit tests must be fast (<100ms each)
5. **Independent tests** - Tests should not depend on each other
6. **Mock external dependencies** - In unit tests only
7. **Use real services** - In integration tests

### Testing Pyramid

```
        /\
       /  \      E2E Tests (Few)
      /____\     - Full system integration
     /      \
    /________\   Integration Tests (Some)
   /          \  - Component interaction
  /____________\ - API contracts
 /              \
/______________\ Unit Tests (Many)
                 - Individual functions
                 - Business logic
```

## Pytest Patterns

### Async Test Structure

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_create_instance(db: AsyncSession):
    """Test creating a new instance."""
    # Arrange
    repo = HopperInstanceRepository()

    # Act
    instance = await repo.create(
        db,
        name="test-instance",
        scope=HopperScope.PROJECT,
    )

    # Assert
    assert instance.id is not None
    assert instance.name == "test-instance"
    assert instance.scope == HopperScope.PROJECT
    assert instance.status == InstanceStatus.CREATED

@pytest.mark.asyncio
async def test_delegate_task_invalid_target(db: AsyncSession):
    """Test delegation fails for invalid target."""
    delegator = Delegator(db)

    with pytest.raises(ValueError, match="Cannot delegate"):
        await delegator.delegate_task(
            task=mock_task,
            target_instance=invalid_instance,
        )
```

### Fixture Patterns

```python
# tests/phase2/conftest.py
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from hopper.models import HopperInstance, Task, TaskDelegation

@pytest.fixture(scope="function")
async def db() -> AsyncSession:
    """Database session for tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

@pytest.fixture
async def global_instance(db: AsyncSession) -> HopperInstance:
    """Create a Global Hopper instance."""
    instance = HopperInstance(
        id="global-test-001",
        name="test-global",
        scope=HopperScope.GLOBAL,
        status=InstanceStatus.RUNNING,
    )
    db.add(instance)
    await db.commit()
    return instance

@pytest.fixture
async def project_instance(db: AsyncSession, global_instance) -> HopperInstance:
    """Create a Project instance under Global."""
    instance = HopperInstance(
        id="project-test-001",
        name="test-project",
        scope=HopperScope.PROJECT,
        parent_id=global_instance.id,
        status=InstanceStatus.RUNNING,
    )
    db.add(instance)
    await db.commit()
    return instance

@pytest.fixture
async def orchestration_instance(db: AsyncSession, project_instance) -> HopperInstance:
    """Create an Orchestration instance under Project."""
    instance = HopperInstance(
        id="orch-test-001",
        name="test-orchestration",
        scope=HopperScope.ORCHESTRATION,
        parent_id=project_instance.id,
        status=InstanceStatus.RUNNING,
    )
    db.add(instance)
    await db.commit()
    return instance

@pytest.fixture
async def instance_hierarchy(db, global_instance, project_instance, orchestration_instance):
    """Complete 3-level instance hierarchy."""
    return (global_instance, project_instance, orchestration_instance)

@pytest.fixture
async def task_with_delegation(db, instance_hierarchy):
    """Task with delegation records through hierarchy."""
    global_inst, project_inst, orch_inst = instance_hierarchy

    task = Task(
        id="task-test-001",
        title="Test Task",
        instance_id=orch_inst.id,  # Currently at orchestration
    )
    db.add(task)

    # Delegation chain
    d1 = TaskDelegation(
        task_id=task.id,
        source_instance_id=global_inst.id,
        target_instance_id=project_inst.id,
        status=DelegationStatus.COMPLETED,
    )
    d2 = TaskDelegation(
        task_id=task.id,
        source_instance_id=project_inst.id,
        target_instance_id=orch_inst.id,
        status=DelegationStatus.ACCEPTED,
    )
    db.add_all([d1, d2])
    await db.commit()

    return task, [d1, d2]
```

## Mocking Patterns

### AsyncMock for Async Functions

```python
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.fixture
def mock_instance_repo():
    """Mock instance repository."""
    repo = MagicMock()
    repo.get_by_id = AsyncMock()
    repo.create = AsyncMock()
    repo.get_children = AsyncMock(return_value=[])
    return repo

@pytest.mark.asyncio
async def test_with_mocked_repo(mock_instance_repo):
    """Test using mocked repository."""
    mock_instance_repo.get_by_id.return_value = HopperInstance(
        id="mock-id",
        name="mock-instance",
        scope=HopperScope.PROJECT,
    )

    result = await mock_instance_repo.get_by_id("mock-id")

    assert result.name == "mock-instance"
    mock_instance_repo.get_by_id.assert_called_once_with("mock-id")
```

### Patching External Services

```python
@pytest.mark.asyncio
async def test_api_endpoint_with_mock_db(client):
    """Test API endpoint with mocked database."""
    with patch("hopper.api.routes.instances.get_db") as mock_get_db:
        mock_session = AsyncMock()
        mock_get_db.return_value = mock_session

        response = await client.get("/api/v1/instances")

        assert response.status_code == 200
```

## Integration Test Patterns

### Full Flow Integration Test

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_delegation_flow(db: AsyncSession):
    """Test complete delegation flow from Global to Orchestration.

    This is the critical integration test for Phase 2:
    1. Task created at Global
    2. Task delegated to Project
    3. Task delegated to Orchestration
    4. Task completed at Orchestration
    5. Completion bubbles up to Global
    """
    # Setup: Create instance hierarchy
    global_inst = await create_instance(db, scope=HopperScope.GLOBAL)
    project_inst = await create_instance(
        db, scope=HopperScope.PROJECT, parent_id=global_inst.id
    )
    orch_inst = await create_instance(
        db, scope=HopperScope.ORCHESTRATION, parent_id=project_inst.id
    )

    # Step 1: Create task at Global
    task = await create_task(db, instance_id=global_inst.id)

    # Step 2: Delegate Global -> Project
    delegator = Delegator(db)
    d1 = await delegator.delegate_task(task, project_inst)
    await delegator.accept_delegation(d1.id)

    # Verify task moved to Project
    await db.refresh(task)
    assert task.instance_id == project_inst.id

    # Step 3: Delegate Project -> Orchestration
    d2 = await delegator.delegate_task(task, orch_inst)
    await delegator.accept_delegation(d2.id)

    # Verify task moved to Orchestration
    await db.refresh(task)
    assert task.instance_id == orch_inst.id

    # Step 4: Complete task at Orchestration
    task.status = TaskStatus.COMPLETED
    await db.commit()

    # Step 5: Bubble completion
    bubbler = CompletionBubbler(db)
    await bubbler.bubble_completion(task)

    # Verify delegation chain is complete
    repo = TaskDelegationRepository()
    chain = await repo.get_delegation_chain(db, task.id)

    assert len(chain) == 2
    assert all(d.status == DelegationStatus.COMPLETED for d in chain)

    # Verify chain order
    assert chain[0].source_instance_id == global_inst.id
    assert chain[0].target_instance_id == project_inst.id
    assert chain[1].source_instance_id == project_inst.id
    assert chain[1].target_instance_id == orch_inst.id
```

### API Integration Test

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_instance_api_crud(client: AsyncClient, db: AsyncSession):
    """Test Instance API CRUD operations."""
    # Create
    response = await client.post(
        "/api/v1/instances",
        json={
            "name": "api-test-instance",
            "scope": "PROJECT",
            "description": "Test instance from API"
        }
    )
    assert response.status_code == 201
    instance_id = response.json()["id"]

    # Read
    response = await client.get(f"/api/v1/instances/{instance_id}")
    assert response.status_code == 200
    assert response.json()["name"] == "api-test-instance"

    # Update
    response = await client.put(
        f"/api/v1/instances/{instance_id}",
        json={"description": "Updated description"}
    )
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description"

    # Delete (soft delete)
    response = await client.delete(f"/api/v1/instances/{instance_id}")
    assert response.status_code == 204

    # Verify soft deleted
    response = await client.get(f"/api/v1/instances/{instance_id}")
    assert response.json()["status"] == "terminated"
```

## Coverage Configuration

### pyproject.toml

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "slow: Slow tests",
]

[tool.coverage.run]
source = ["src/hopper"]
omit = [
    "*/tests/*",
    "*/__pycache__/*",
]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if TYPE_CHECKING:",
    "@abstractmethod",
]
show_missing = true
fail_under = 90  # Phase 2 requirement
```

### Running Coverage

```bash
# Run all tests with coverage
pytest --cov=src/hopper --cov-report=html --cov-report=term-missing

# Run only Phase 2 tests
pytest tests/phase2/ --cov=src/hopper --cov-report=html

# Check specific modules
pytest tests/phase2/test_delegation.py --cov=src/hopper/delegation

# Generate XML for CI
pytest --cov=src/hopper --cov-report=xml
```

## Test Organization

### Directory Structure

```
tests/
├── conftest.py              # Shared fixtures
├── phase2/
│   ├── __init__.py
│   ├── conftest.py          # Phase 2 specific fixtures
│   ├── test_instance_api.py # Instance API tests
│   ├── test_delegation.py   # Delegation model tests
│   ├── test_scope_behaviors.py
│   ├── test_instance_cli.py
│   └── test_integration.py  # Full flow tests
├── unit/                    # Existing unit tests
└── integration/             # Existing integration tests
```

### Test Naming

```python
# Function names describe behavior
def test_create_instance_with_parent():
    """Test creating instance with parent relationship."""
    pass

def test_create_instance_fails_with_invalid_scope():
    """Test that invalid scope raises validation error."""
    pass

def test_delegation_chain_returns_ordered_list():
    """Test delegation chain is ordered by delegation time."""
    pass
```

## Best Practices

### DO
- Use AAA pattern (Arrange-Act-Assert)
- Write descriptive test names
- Test edge cases and error conditions
- Use fixtures for common setup
- Mock external dependencies in unit tests
- Use real database for integration tests
- Run tests before every commit

### DON'T
- Skip tests ("I'll add them later")
- Test implementation details
- Write flaky tests
- Share state between tests
- Use production data
- Write tests without assertions
- Ignore failing tests

## References

- Testing README: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/README.md`
- Integration testing: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/INTEGRATION_TESTING.md`
- Mocking strategies: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/MOCKING_STRATEGIES.md`
- Coverage standards: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/testing/COVERAGE_STANDARDS.md`
