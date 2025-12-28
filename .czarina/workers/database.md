# Worker: Database

**Branch:** cz1/feat/database
**Dependencies:** project-setup
**Duration:** 2 days

## Mission

Implement database schema, migrations, and CRUD operations for all Hopper core entities. Build the persistence layer that the API will use.

## Background

Building on the models created in `project-setup`, this worker:
- Creates Alembic migrations for schema management
- Implements database initialization and migrations
- Builds CRUD operations and repository pattern
- Ensures PostgreSQL (production) and SQLite (dev) compatibility

## Tasks

### Task 1: Set Up Alembic Migrations

1. Initialize Alembic in the project:
   ```bash
   alembic init alembic
   ```

2. Configure `alembic.ini`:
   - Set SQLAlchemy URL from environment
   - Configure logging
   - Set up migration file template

3. Update `alembic/env.py`:
   - Import all models
   - Configure target metadata
   - Support both sync and async migrations
   - Handle PostgreSQL and SQLite differences

4. Create initial migration:
   ```bash
   alembic revision --autogenerate -m "Initial schema"
   ```

5. Verify migration creates all tables:
   - tasks
   - projects
   - hopper_instances
   - routing_decisions
   - All relationships and indexes

**Checkpoint:** Commit Alembic configuration and initial migration

### Task 2: Database Initialization and Connection

1. Create `src/hopper/database/connection.py`:
   - Database engine creation
   - Session factory
   - Async session support (for FastAPI)
   - Connection pooling configuration
   - PostgreSQL vs SQLite setup

2. Create `src/hopper/database/init.py`:
   - Database initialization function
   - Schema creation for development
   - Migration runner
   - Database health check

3. Create `src/hopper/database/__init__.py`:
   - Export session management utilities
   - Export database initialization functions

4. Add database connection tests:
   - Test connection to PostgreSQL
   - Test connection to SQLite
   - Test session creation and cleanup

**Checkpoint:** Commit database connection management

### Task 3: Implement Repository Pattern (CRUD Operations)

Reference: Clean architecture patterns for testable, maintainable code

1. Create `src/hopper/database/repositories/base.py`:
   - BaseRepository with common CRUD operations
   - Generic type support
   - Async operations
   - Pagination support
   - Filtering and sorting utilities

2. Create `src/hopper/database/repositories/task_repository.py`:
   - TaskRepository extending BaseRepository
   - Custom queries:
     - `get_tasks_by_project(project_id)`
     - `get_tasks_by_status(status)`
     - `get_tasks_by_tag(tag)`
     - `search_tasks(query)`
   - Bulk operations
   - Task state transitions

3. Create `src/hopper/database/repositories/project_repository.py`:
   - ProjectRepository extending BaseRepository
   - Custom queries:
     - `get_project_by_slug(slug)`
     - `get_projects_with_active_tasks()`
   - Project statistics

4. Create `src/hopper/database/repositories/hopper_instance_repository.py`:
   - HopperInstanceRepository extending BaseRepository
   - Custom queries:
     - `get_instance_by_scope_and_name(scope, name)`
     - `get_child_instances(parent_id)`
     - `get_instance_hierarchy(instance_id)`
   - Instance lifecycle operations

5. Create `src/hopper/database/repositories/routing_decision_repository.py`:
   - RoutingDecisionRepository extending BaseRepository
   - Custom queries:
     - `get_decisions_by_task(task_id)`
     - `get_decisions_by_strategy(strategy)`
     - `get_recent_decisions(limit)`
   - Decision analytics

6. Create `src/hopper/database/repositories/__init__.py`:
   - Export all repositories
   - Repository factory pattern

**Checkpoint:** Commit repository implementations

### Task 4: Database Utilities and Helpers

1. Create `src/hopper/database/utils.py`:
   - Database URL builder
   - Migration runner
   - Schema dumper for debugging
   - Database reset utility (dev only)
   - Seed data generator for testing

2. Create seed data script `scripts/seed-db.py`:
   - Create sample projects
   - Create sample tasks
   - Create sample routing decisions
   - Useful for development and demos

3. Add database utility tests:
   - Test migration runner
   - Test seed data generation
   - Test database reset

**Checkpoint:** Commit database utilities

### Task 5: Comprehensive Testing

1. Create `tests/database/test_migrations.py`:
   - Test migrations run successfully
   - Test migration rollback
   - Test schema matches models

2. Create `tests/database/test_task_repository.py`:
   - Test all CRUD operations
   - Test custom queries
   - Test pagination
   - Test filtering and sorting
   - Test concurrent access

3. Create `tests/database/test_project_repository.py`:
   - Test project CRUD
   - Test project queries
   - Test project-task relationships

4. Create `tests/database/test_hopper_instance_repository.py`:
   - Test instance CRUD
   - Test hierarchy queries
   - Test parent-child relationships

5. Create `tests/database/test_routing_decision_repository.py`:
   - Test decision CRUD
   - Test decision queries
   - Test analytics functions

6. Ensure all tests pass with both PostgreSQL and SQLite

**Checkpoint:** Commit comprehensive test suite

### Task 6: Documentation and Performance

1. Create `docs/database-schema.md`:
   - Document all tables and columns
   - Document relationships
   - Document indexes
   - Include ERD diagram (text-based or Mermaid)

2. Add database performance optimizations:
   - Add appropriate indexes
   - Configure connection pooling
   - Add query performance logging
   - Document slow query optimization

3. Update main README with database section:
   - How to run migrations
   - How to seed the database
   - How to reset the database
   - Troubleshooting common issues

**Checkpoint:** Commit documentation and optimizations

## Deliverables

- [ ] Alembic configured with initial migration
- [ ] Database connection management (PostgreSQL and SQLite)
- [ ] Repository pattern with all CRUD operations
- [ ] Task, Project, HopperInstance, RoutingDecision repositories
- [ ] Database utilities (seed data, reset, migrations)
- [ ] Comprehensive test suite for all repositories
- [ ] Database schema documentation
- [ ] Performance optimizations (indexes, pooling)

## Success Criteria

- ✅ `alembic upgrade head` creates all tables successfully
- ✅ Can connect to both PostgreSQL and SQLite
- ✅ All CRUD operations work for all entities
- ✅ Custom queries return correct results
- ✅ Tests pass with both PostgreSQL and SQLite
- ✅ Database operations are performant (queries <100ms for simple operations)
- ✅ Seed data script populates database successfully
- ✅ Can reset database and re-run migrations
- ✅ Repository pattern is clean and testable

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (Database Design section)
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- SQLAlchemy 2.0 docs: https://docs.sqlalchemy.org/en/20/
- Alembic docs: https://alembic.sqlalchemy.org/

## Notes

- Use SQLAlchemy 2.0 syntax throughout
- Ensure all queries work with both PostgreSQL and SQLite
- Use async sessions for FastAPI compatibility
- Add appropriate indexes for common queries
- Consider using JSONB for PostgreSQL, JSON for SQLite
- Repository pattern keeps business logic separate from ORM
- All database operations should be testable without a real database (use in-memory SQLite)
