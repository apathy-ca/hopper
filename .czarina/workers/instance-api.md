# Worker Identity: instance-api

**Role:** Code
**Agent:** claude
**Branch:** cz2/feat/instance-api
**Phase:** 2
**Dependencies:** None

## Mission

Activate and implement the instance API endpoints for Hopper's multi-instance support. Create a complete REST API for instance CRUD operations, hierarchy traversal, and lifecycle management, building on the existing models and repository that were completed in Phase 1.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/instance-api-knowledge.md`

This includes:
- FastAPI async patterns for endpoint implementation
- Error handling patterns for API responses
- Pydantic schema patterns
- Testing patterns for API endpoints

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Examine the existing instance infrastructure to understand what's already built:**

```bash
# Read the existing HopperInstance model
cat src/hopper/models/hopper_instance.py

# Read the existing repository methods
cat src/hopper/database/repositories/hopper_instance_repository.py

# Read the existing Pydantic schemas
cat src/hopper/api/schemas/hopper_instance.py

# Check the app.py for commented routes
grep -A5 -B5 "instance" src/hopper/api/app.py
```

**Then:** Create a task list based on what you find and start implementing `src/hopper/api/routes/instances.py` with the CRUD endpoints.

## Objectives

1. **Create Instance Routes File** (`src/hopper/api/routes/instances.py`)
   - `POST /api/v1/instances` - Create instance
   - `GET /api/v1/instances` - List instances (with filters: scope, status, parent_id)
   - `GET /api/v1/instances/{id}` - Get instance details
   - `PUT /api/v1/instances/{id}` - Update instance
   - `DELETE /api/v1/instances/{id}` - Delete instance (soft delete → TERMINATED)

2. **Add Hierarchy Endpoints**
   - `GET /api/v1/instances/{id}/children` - Get child instances
   - `GET /api/v1/instances/{id}/hierarchy` - Get full hierarchy tree
   - `GET /api/v1/instances/{id}/tasks` - Get tasks for instance

3. **Add Lifecycle Endpoints**
   - `POST /api/v1/instances/{id}/start` - Start instance
   - `POST /api/v1/instances/{id}/stop` - Stop instance
   - `POST /api/v1/instances/{id}/restart` - Restart instance
   - `POST /api/v1/instances/{id}/pause` - Pause instance
   - `POST /api/v1/instances/{id}/resume` - Resume instance

4. **Wire Up Router in app.py**
   - Uncomment/add instance router registration
   - Ensure proper prefix and tags

5. **Align Schema Enums**
   - Ensure Pydantic schema enums match model enums exactly
   - Fix any discrepancies between schemas and models

6. **Write Unit Tests**
   - Create `tests/api/test_instances.py`
   - Test all CRUD operations
   - Test hierarchy queries
   - Test lifecycle transitions
   - Test error handling

## Deliverables

- [ ] `src/hopper/api/routes/instances.py` - All instance endpoints
- [ ] Updated `src/hopper/api/app.py` - Router wired up
- [ ] Updated `src/hopper/api/schemas/hopper_instance.py` - Enum alignment if needed
- [ ] `tests/api/test_instances.py` - Unit tests with 90%+ coverage

## Success Criteria

- [ ] All instance CRUD operations work via API
- [ ] Can retrieve instance hierarchy as tree structure
- [ ] Lifecycle operations transition status correctly (CREATED → STARTING → RUNNING, etc.)
- [ ] Proper HTTP status codes returned (201 for create, 404 for not found, etc.)
- [ ] Validation errors return 422 with detailed messages
- [ ] 90%+ test coverage on new code
- [ ] All tests passing

## Context

### Existing Infrastructure (From Phase 1)

The following are already complete and you should use them:

**HopperInstance Model** (`src/hopper/models/hopper_instance.py`):
- Fields: id, name, scope, instance_type, parent_id, config, runtime_metadata, status, etc.
- Methods: `get_ancestors()`, `get_children()`, etc.

**HopperScope Enum** (`src/hopper/models/enums.py`):
- GLOBAL, PROJECT, ORCHESTRATION, PERSONAL, FAMILY, EVENT, FEDERATED

**InstanceStatus Enum** (`src/hopper/models/enums.py`):
- CREATED, STARTING, RUNNING, STOPPING, STOPPED, PAUSED, ERROR, TERMINATED

**Repository** (`src/hopper/database/repositories/hopper_instance_repository.py`):
- Already has methods for CRUD operations - use these!

**Pydantic Schemas** (`src/hopper/api/schemas/hopper_instance.py`):
- Request/response schemas exist - may need enum alignment

### API Patterns to Follow

Look at existing routes in `src/hopper/api/routes/` for patterns:
- Dependency injection for database sessions
- Async endpoint handlers
- Proper exception handling
- Response model typing

## Notes

- Use FastAPI's `Depends()` for database session injection
- Follow existing code style and patterns in the project
- All endpoints should be async
- Use proper HTTP status codes (201 for create, 204 for delete, etc.)
- Include OpenAPI documentation via docstrings and response_model
