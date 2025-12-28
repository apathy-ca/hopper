
# Hopper Database Usage Guide

This guide covers common database operations and best practices for working with the Hopper database.

## Table of Contents

1. [Setup](#setup)
2. [Connection Management](#connection-management)
3. [Running Migrations](#running-migrations)
4. [Using Repositories](#using-repositories)
5. [Database Utilities](#database-utilities)
6. [Testing](#testing)
7. [Best Practices](#best-practices)

## Setup

### Environment Configuration

Set the `DATABASE_URL` environment variable:

```bash
# Development (SQLite)
export DATABASE_URL="sqlite:///./hopper.db"

# Production (PostgreSQL)
export DATABASE_URL="postgresql://user:password@localhost/hopper"
```

### Initialize Database

```python
from hopper.database import init_database, run_migrations

# Option 1: Run Alembic migrations (recommended)
run_migrations("head")

# Option 2: Create tables directly (development only)
init_database(create_tables=True)
```

## Connection Management

### Synchronous Sessions

```python
from hopper.database import get_sync_session

# Using context manager (recommended)
with get_sync_session() as session:
    # Your database operations here
    task = session.query(Task).first()
    # Automatically commits on success, rolls back on error

# Manual session management
from hopper.database import get_sync_session_factory

SessionLocal = get_sync_session_factory()
session = SessionLocal()
try:
    # Your operations
    session.commit()
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

### Asynchronous Sessions (for FastAPI)

```python
from hopper.database import get_async_session

async def get_tasks():
    async with get_async_session() as session:
        result = await session.execute(select(Task))
        return result.scalars().all()
```

### Custom Engine

```python
from hopper.database import create_sync_engine

# Custom SQLite database
engine = create_sync_engine("sqlite:///./custom.db")

# PostgreSQL with custom settings
engine = create_sync_engine(
    "postgresql://user:pass@localhost/hopper",
    echo=True  # Log all SQL queries
)
```

## Running Migrations

### Command Line

```bash
# Upgrade to latest
alembic upgrade head

# Downgrade one version
alembic downgrade -1

# View current version
alembic current

# View migration history
alembic history
```

### Programmatic

```python
from hopper.database import run_migrations

# Upgrade to latest
exit_code = run_migrations("head")

# Upgrade to specific revision
exit_code = run_migrations("abc123")
```

### Creating Migrations

```bash
# Auto-generate migration from model changes
alembic revision --autogenerate -m "Add user_preferences table"

# Create empty migration
alembic revision -m "Custom migration"
```

## Using Repositories

### TaskRepository

```python
from hopper.database import get_sync_session
from hopper.database.repositories import TaskRepository

with get_sync_session() as session:
    repo = TaskRepository(session)

    # Create a task
    task = repo.create(
        id="task-123",
        title="Implement feature X",
        description="Add new feature to the API",
        status="pending",
        priority="high",
        tags=["backend", "api"],
    )

    # Get a task
    task = repo.get("task-123")

    # Update a task
    task = repo.update("task-123", status="in_progress")

    # Delete a task
    repo.delete("task-123")

    # Filter tasks
    pending_tasks = repo.get_tasks_by_status("pending")
    project_tasks = repo.get_tasks_by_project("my-project")

    # Search tasks
    results = repo.search_tasks("bug fix")

    # Pagination
    tasks = repo.get_all(skip=0, limit=10, order_by="-created_at")

    # Count tasks
    count = repo.count(filters={"status": "pending"})
```

### ProjectRepository

```python
from hopper.database.repositories import ProjectRepository

with get_sync_session() as session:
    repo = ProjectRepository(session)

    # Create a project
    project = repo.create(
        name="my-project",
        slug="my-proj",
        repository="https://github.com/user/project",
        capabilities={"languages": ["python"], "skills": ["api"]},
        executor_type="agent",
        auto_claim=True,
    )

    # Get by slug
    project = repo.get_by_slug("my-proj")

    # Get project statistics
    stats = repo.get_project_statistics("my-project")
    # Returns: {
    #     "total_tasks": 10,
    #     "pending": 5,
    #     "in_progress": 3,
    #     "completed": 2
    # }

    # Get projects with active tasks
    active_projects = repo.get_projects_with_active_tasks()
```

### HopperInstanceRepository

```python
from hopper.database.repositories import HopperInstanceRepository

with get_sync_session() as session:
    repo = HopperInstanceRepository(session)

    # Create instance
    instance = repo.create(
        id="global-hopper",
        name="Global Hopper",
        scope="GLOBAL",
        status="active",
    )

    # Create child instance
    child = repo.create(
        id="project-hopper-1",
        name="Project Hopper",
        scope="PROJECT",
        parent_id="global-hopper",
        status="active",
    )

    # Get hierarchy
    hierarchy = repo.get_instance_hierarchy("project-hopper-1")

    # Terminate instance
    repo.terminate_instance("project-hopper-1")
```

### RoutingDecisionRepository

```python
from hopper.database.repositories import RoutingDecisionRepository

with get_sync_session() as session:
    repo = RoutingDecisionRepository(session)

    # Record routing decision
    decision = repo.create(
        task_id="task-123",
        project="my-project",
        confidence=0.95,
        reasoning="Best match based on capabilities",
        decided_by="llm",
        decision_time_ms=250.5,
    )

    # Get recent decisions
    recent = repo.get_recent_decisions(limit=10)

    # Get decisions with low confidence
    uncertain = repo.get_decisions_with_low_confidence(threshold=0.7)

    # Get analytics
    analytics = repo.get_decision_analytics()
    # Returns comprehensive routing analytics
```

### Bulk Operations

```python
with get_sync_session() as session:
    repo = TaskRepository(session)

    # Bulk create
    tasks_data = [
        {"id": "task-1", "title": "Task 1", "status": "pending", "priority": "low"},
        {"id": "task-2", "title": "Task 2", "status": "pending", "priority": "medium"},
        {"id": "task-3", "title": "Task 3", "status": "pending", "priority": "high"},
    ]
    tasks = repo.bulk_create(tasks_data)

    # Bulk update
    updates = [
        {"id": "task-1", "status": "completed"},
        {"id": "task-2", "status": "in_progress"},
    ]
    count = repo.bulk_update(updates)

    # Bulk delete
    ids = ["task-1", "task-2", "task-3"]
    count = repo.bulk_delete(ids)
```

## Database Utilities

### Reset Database (Development Only)

```python
from hopper.database import reset_database

# WARNING: This deletes all data!
reset_database(confirm=True)
```

### Seed Sample Data

```bash
# Reset and seed
python scripts/seed-db.py --reset

# Seed without reset
python scripts/seed-db.py
```

### Check Database Health

```python
from hopper.database import check_database_health

is_healthy = check_database_health()
if not is_healthy:
    print("Database connection failed!")
```

### Get Database Info

```python
from hopper.database import get_database_info

info = get_database_info()
# Returns: {
#     "url": "sqlite:///./hopper.db",
#     "type": "sqlite",
#     "async_url": "sqlite+aiosqlite:///./hopper.db"
# }
```

### Dump Schema

```python
from hopper.database.utils import dump_schema

schema = dump_schema()
# Returns detailed schema information for all tables
```

### Analyze Statistics

```python
from hopper.database.utils import analyze_database_statistics

stats = analyze_database_statistics()
# Returns: {
#     "database_type": "sqlite",
#     "table_count": 6,
#     "tables": ["tasks", "projects", ...],
#     "row_counts": {"tasks": 10, "projects": 3, ...},
#     "total_rows": 25
# }
```

### Vacuum SQLite Database

```python
from hopper.database.utils import vacuum_database

vacuum_database()  # Reclaims unused space in SQLite
```

## Testing

### Test Fixture

```python
import pytest
from hopper.database import create_sync_engine, init_database, reset_session_factories

@pytest.fixture
def test_session():
    """Create a test database session."""
    import os
    reset_session_factories()
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

    engine = create_sync_engine()
    init_database(engine, create_tables=True)

    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        os.environ.pop("DATABASE_URL", None)
        reset_session_factories()

def test_create_task(test_session):
    from hopper.database.repositories import TaskRepository

    repo = TaskRepository(test_session)
    task = repo.create(id="test-1", title="Test", status="pending", priority="low")

    assert task.id == "test-1"
    assert task.title == "Test"
```

## Best Practices

### 1. Always Use Context Managers

```python
# Good
with get_sync_session() as session:
    repo = TaskRepository(session)
    task = repo.create(...)

# Avoid
session = SessionLocal()
repo = TaskRepository(session)
task = repo.create(...)
session.commit()
session.close()
```

### 2. Use Repositories, Not Raw Queries

```python
# Good
with get_sync_session() as session:
    repo = TaskRepository(session)
    tasks = repo.get_tasks_by_status("pending")

# Avoid
with get_sync_session() as session:
    tasks = session.query(Task).filter(Task.status == "pending").all()
```

### 3. Handle Transactions Properly

```python
with get_sync_session() as session:
    repo = TaskRepository(session)

    try:
        task = repo.create(...)
        # More operations...
        # Automatically commits on success
    except Exception:
        # Automatically rolls back on error
        raise
```

### 4. Use Pagination for Large Datasets

```python
# Good
tasks = repo.get_all(skip=0, limit=100, order_by="-created_at")

# Avoid
tasks = repo.get_all()  # Could return millions of rows
```

### 5. Use Filters Efficiently

```python
# Good - Database does the filtering
tasks = repo.filter(
    filters={"status": "pending", "priority": "high"},
    limit=10
)

# Avoid - Python does the filtering
all_tasks = repo.get_all()
filtered = [t for t in all_tasks if t.status == "pending" and t.priority == "high"]
```

### 6. Clean Up Test Data

```python
@pytest.fixture
def test_session():
    # Setup
    session = create_test_session()

    yield session

    # Cleanup - important for tests!
    session.rollback()
    session.close()
```

### 7. Use Environment Variables for Configuration

```python
# Good
import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./hopper.db")

# Avoid
DATABASE_URL = "postgresql://user:password@localhost/hopper"  # Hardcoded!
```

### 8. Run Migrations, Don't Create Tables

```python
# Good (Production)
run_migrations("head")

# Only for development/testing
init_database(create_tables=True)
```

## Troubleshooting

### Connection Errors

```python
from hopper.database import check_database_health

if not check_database_health():
    print("Database connection failed!")
    # Check DATABASE_URL
    # Check database server is running
    # Check credentials
```

### Migration Issues

```bash
# Check current migration
alembic current

# View pending migrations
alembic heads

# Force to specific version
alembic stamp head
```

### Performance Issues

```python
# Enable SQL logging to see queries
engine = create_sync_engine(echo=True)

# Use EXPLAIN to analyze queries
from sqlalchemy import text
with get_sync_session() as session:
    result = session.execute(text("EXPLAIN SELECT * FROM tasks"))
```

### SQLite Lock Errors

```python
# SQLite doesn't handle concurrent writes well
# Use PostgreSQL for production with multiple writers
# Or use serialized access for SQLite
```

## Additional Resources

- [Database Schema Documentation](./database-schema.md)
- [SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
