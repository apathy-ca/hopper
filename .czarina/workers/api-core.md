# Worker: API Core

**Branch:** cz1/feat/api-core
**Dependencies:** database
**Duration:** 3 days

## Mission

Build the FastAPI application with task endpoints, authentication, and core API functionality. This is the HTTP interface that MCP, CLI, and external tools will use.

## Background

Phase 1 Week 2 focuses on creating the REST API with:
- FastAPI application structure
- Task CRUD endpoints
- Project and instance management endpoints
- Authentication and authorization
- OpenAPI documentation
- Error handling and validation

## Tasks

### Task 1: FastAPI Application Setup

1. Create `src/hopper/api/app.py`:
   - FastAPI application factory
   - CORS configuration
   - Middleware setup (logging, error handling)
   - Health check endpoint
   - OpenAPI customization

2. Create `src/hopper/api/dependencies.py`:
   - Database session dependency
   - Authentication dependency
   - Pagination dependencies
   - Common query parameter dependencies

3. Create `src/hopper/api/exceptions.py`:
   - Custom exception classes
   - Exception handlers
   - Standardized error responses

4. Create `src/hopper/api/__init__.py`:
   - Export app factory
   - Version information

**Checkpoint:** Commit FastAPI application setup

### Task 2: Pydantic Schemas (Request/Response Models)

1. Create `src/hopper/api/schemas/task.py`:
   - TaskCreate (request)
   - TaskUpdate (request)
   - TaskResponse (response)
   - TaskList (paginated response)
   - Status and priority enums

2. Create `src/hopper/api/schemas/project.py`:
   - ProjectCreate
   - ProjectUpdate
   - ProjectResponse
   - ProjectList
   - Project configuration schema

3. Create `src/hopper/api/schemas/hopper_instance.py`:
   - InstanceCreate
   - InstanceUpdate
   - InstanceResponse
   - InstanceHierarchy (tree structure)

4. Create `src/hopper/api/schemas/routing_decision.py`:
   - DecisionCreate
   - DecisionResponse
   - DecisionList

5. Create `src/hopper/api/schemas/common.py`:
   - Pagination schemas
   - Filter schemas
   - Common response wrappers

6. Create `src/hopper/api/schemas/__init__.py`:
   - Export all schemas

**Checkpoint:** Commit Pydantic schemas

### Task 3: Task Management Endpoints

Reference: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (API Specifications section)

1. Create `src/hopper/api/routes/tasks.py`:
   - `POST /api/v1/tasks` - Create task
   - `GET /api/v1/tasks` - List tasks (with filters, pagination)
   - `GET /api/v1/tasks/{task_id}` - Get task by ID
   - `PUT /api/v1/tasks/{task_id}` - Update task
   - `DELETE /api/v1/tasks/{task_id}` - Delete task (soft delete)
   - `POST /api/v1/tasks/{task_id}/status` - Update task status
   - `GET /api/v1/tasks/search` - Search tasks

2. Add comprehensive validation:
   - Required fields
   - String length limits
   - Valid status transitions
   - Tag format validation

3. Add filtering and sorting:
   - Filter by status, priority, project, tags
   - Sort by created_at, priority, status
   - Full-text search (basic for Phase 1)

**Checkpoint:** Commit task endpoints

### Task 4: Project and Instance Management Endpoints

1. Create `src/hopper/api/routes/projects.py`:
   - `POST /api/v1/projects` - Create project
   - `GET /api/v1/projects` - List projects
   - `GET /api/v1/projects/{project_id}` - Get project
   - `PUT /api/v1/projects/{project_id}` - Update project
   - `DELETE /api/v1/projects/{project_id}` - Delete project
   - `GET /api/v1/projects/{project_id}/tasks` - Get project tasks

2. Create `src/hopper/api/routes/instances.py`:
   - `POST /api/v1/instances` - Create instance
   - `GET /api/v1/instances` - List instances
   - `GET /api/v1/instances/{instance_id}` - Get instance
   - `PUT /api/v1/instances/{instance_id}` - Update instance
   - `DELETE /api/v1/instances/{instance_id}` - Delete instance
   - `GET /api/v1/instances/{instance_id}/hierarchy` - Get instance tree
   - `GET /api/v1/instances/{instance_id}/tasks` - Get instance tasks

3. Add instance lifecycle operations:
   - Start instance
   - Stop instance
   - Get instance status

**Checkpoint:** Commit project and instance endpoints

### Task 5: Authentication and Authorization

1. Create `src/hopper/api/auth/security.py`:
   - Password hashing utilities
   - JWT token creation and validation
   - API key support (for MCP/CLI)
   - Authentication dependency

2. Create `src/hopper/api/auth/models.py`:
   - User model (simple for Phase 1)
   - API key model
   - Permission model (basic)

3. Create `src/hopper/api/routes/auth.py`:
   - `POST /api/v1/auth/token` - Get JWT token
   - `POST /api/v1/auth/refresh` - Refresh token
   - `POST /api/v1/auth/api-keys` - Create API key
   - `GET /api/v1/auth/me` - Get current user

4. Add authentication to protected endpoints:
   - Use dependency injection
   - Support both JWT and API keys
   - Optional authentication for development mode

5. Add basic authorization:
   - Admin vs regular user
   - Project-level permissions (future-proofing)

**Checkpoint:** Commit authentication and authorization

### Task 6: Testing and Documentation

1. Create `tests/api/conftest.py`:
   - Test client fixture
   - Authenticated client fixture
   - Test database fixture
   - Mock data fixtures

2. Create `tests/api/test_tasks.py`:
   - Test all task endpoints
   - Test validation
   - Test filtering and pagination
   - Test error cases
   - Test authentication

3. Create `tests/api/test_projects.py`:
   - Test all project endpoints
   - Test project-task relationships

4. Create `tests/api/test_instances.py`:
   - Test all instance endpoints
   - Test instance hierarchy

5. Create `tests/api/test_auth.py`:
   - Test authentication flow
   - Test JWT tokens
   - Test API keys
   - Test unauthorized access

6. Update OpenAPI documentation:
   - Add descriptions to all endpoints
   - Add request/response examples
   - Add tags and grouping
   - Add authentication documentation

7. Create `docs/api-guide.md`:
   - API overview
   - Authentication guide
   - Common workflows
   - Error handling
   - Rate limiting (if implemented)

**Checkpoint:** Commit tests and documentation

## Deliverables

- [ ] FastAPI application with proper structure
- [ ] Complete Pydantic schemas for all entities
- [ ] Task management endpoints (CRUD + search)
- [ ] Project management endpoints
- [ ] Instance management endpoints
- [ ] Authentication and authorization (JWT + API keys)
- [ ] Comprehensive test suite (>90% coverage)
- [ ] OpenAPI documentation with examples
- [ ] API guide documentation

## Success Criteria

- ✅ `uvicorn hopper.api.app:app --reload` starts the API server
- ✅ OpenAPI docs accessible at `/docs`
- ✅ Can create tasks via `POST /api/v1/tasks`
- ✅ Can list tasks with filters and pagination
- ✅ Can search tasks
- ✅ All endpoints return proper status codes
- ✅ Validation errors return 422 with details
- ✅ Authentication works with JWT and API keys
- ✅ Unauthorized requests return 401
- ✅ All tests pass with >90% coverage
- ✅ API is ready for MCP and CLI integration

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (API Specifications)
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- FastAPI docs: https://fastapi.tiangolo.com/
- Pydantic docs: https://docs.pydantic.dev/

## Notes

- Use FastAPI dependency injection for database sessions and auth
- Async endpoints for all database operations
- Proper HTTP status codes (200, 201, 204, 400, 401, 404, 422, 500)
- Standardized error response format
- OpenAPI docs should be comprehensive and accurate
- Consider rate limiting for production (optional for Phase 1)
- CORS should be configurable for different environments
- Health check endpoint should verify database connectivity
- Use Pydantic v2 for better performance and validation
