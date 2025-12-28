# Worker: Project Setup

**Branch:** cz1/feat/project-setup
**Dependencies:** None
**Duration:** 2-3 days

## Mission

Initialize the Python project structure, development environment, and core data models for Hopper. This worker establishes the foundation that all other Phase 1 workers will build upon.

## Background

From the Hopper Implementation Plan, Phase 1 Week 1 focuses on:
- Python project structure with proper packaging
- Development environment using Docker Compose
- Core data models (Task, Project, RoutingDecision, HopperInstance)
- Basic project configuration and dependencies

This is the critical foundation - everything else depends on getting this right.

## Tasks

### Task 1: Initialize Python Project Structure

1. Create standard Python project layout:
   ```
   hopper/
   ├── src/hopper/
   │   ├── __init__.py
   │   ├── models/
   │   ├── api/
   │   ├── mcp/
   │   ├── cli/
   │   ├── intelligence/
   │   ├── memory/
   │   └── config/
   ├── tests/
   ├── docs/
   ├── pyproject.toml
   ├── README.md
   └── .gitignore
   ```

2. Create `pyproject.toml` with:
   - Project metadata (name, version, description)
   - Python version requirement (>=3.11)
   - Core dependencies from Implementation Plan
   - Development dependencies (pytest, black, ruff, mypy)
   - Entry points for CLI tool

3. Set up proper Python packaging (PEP 517/518)

**Checkpoint:** Commit initial project structure

### Task 2: Configure Development Environment

1. Create `docker-compose.yml` with services:
   - PostgreSQL 15+ (production database)
   - Redis (working memory, optional for Phase 1)
   - Development volumes and networking

2. Create `.env.template` with configuration variables:
   - Database connection strings
   - Redis connection (if used)
   - API settings
   - Development mode flags

3. Create `Dockerfile` for Hopper application:
   - Python 3.11+ base image
   - Install dependencies
   - Set up development mode

4. Add development scripts:
   - `scripts/dev-setup.sh` - Initial setup
   - `scripts/db-reset.sh` - Database reset for testing
   - `scripts/run-tests.sh` - Test runner

**Checkpoint:** Commit Docker and development environment configuration

### Task 3: Implement Core Data Models

Reference: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (Database Design section)

1. Create `src/hopper/models/base.py`:
   - SQLAlchemy declarative base
   - Common mixins (timestamps, soft delete)
   - Base model utilities

2. Create `src/hopper/models/task.py`:
   - Task model with all fields from spec
   - TaskStatus enum
   - TaskPriority enum
   - Relationships to Project and RoutingDecision

3. Create `src/hopper/models/project.py`:
   - Project model
   - Project configuration (JSONB field)
   - Relationships to tasks

4. Create `src/hopper/models/hopper_instance.py`:
   - HopperInstance model
   - HopperScope enum (GLOBAL, PROJECT, ORCHESTRATION)
   - Parent-child relationships
   - Instance configuration

5. Create `src/hopper/models/routing_decision.py`:
   - RoutingDecision model
   - DecisionStrategy enum
   - Confidence tracking
   - Feedback support

6. Create `src/hopper/models/__init__.py`:
   - Export all models
   - Proper imports for type checking

**Checkpoint:** Commit core data models

### Task 4: Set Up Configuration Management

1. Create `src/hopper/config/settings.py`:
   - Use pydantic-settings
   - Load from environment variables
   - Database configuration
   - API configuration
   - Development vs production settings

2. Create `src/hopper/config/__init__.py`:
   - Export settings singleton
   - Configuration validation

3. Add configuration validation tests

**Checkpoint:** Commit configuration management

### Task 5: Create Initial Tests

1. Create `tests/conftest.py`:
   - Pytest fixtures for database
   - Test client fixtures
   - Mock data factories

2. Create `tests/models/test_task.py`:
   - Test Task model creation
   - Test relationships
   - Test constraints

3. Create `tests/models/test_project.py`:
   - Test Project model
   - Test configuration handling

4. Create `tests/models/test_hopper_instance.py`:
   - Test instance hierarchy
   - Test scope relationships

5. Ensure all tests pass with `pytest`

**Checkpoint:** Commit initial test suite

### Task 6: Documentation and CI Setup

1. Create `README.md` with:
   - Project overview
   - Installation instructions
   - Development setup
   - Running tests
   - Project structure explanation

2. Create `CONTRIBUTING.md`:
   - Development workflow
   - Code style guidelines
   - Testing requirements

3. Set up basic CI (if desired):
   - GitHub Actions or GitLab CI
   - Run tests on push
   - Code quality checks (black, ruff, mypy)

**Checkpoint:** Commit documentation and CI configuration

## Deliverables

- [ ] Python project structure with proper packaging
- [ ] `pyproject.toml` with all dependencies
- [ ] Docker Compose setup with PostgreSQL and Redis
- [ ] All core data models implemented (Task, Project, HopperInstance, RoutingDecision)
- [ ] Configuration management with pydantic-settings
- [ ] Initial test suite with >80% model coverage
- [ ] Development documentation (README, CONTRIBUTING)
- [ ] All code passes type checking (mypy) and linting (ruff)

## Success Criteria

- ✅ `docker-compose up` starts all services successfully
- ✅ Python package installs with `pip install -e .`
- ✅ All models can be imported: `from hopper.models import Task, Project, ...`
- ✅ Tests pass: `pytest tests/`
- ✅ Type checking passes: `mypy src/`
- ✅ Linting passes: `ruff check src/`
- ✅ Code formatting is consistent: `black --check src/`
- ✅ Other workers can build on this foundation

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md`
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- Database Design: See Implementation Plan, Database Design section
- Technology Stack: See Implementation Plan, Technology Stack section

## Notes

- Use SQLAlchemy 2.0 syntax (not legacy)
- Ensure PostgreSQL and SQLite compatibility (for dev/test)
- Follow PEP 8 and modern Python best practices
- Type hints are mandatory for all public APIs
- JSONB fields for flexible configuration (PostgreSQL feature, JSON for SQLite)
