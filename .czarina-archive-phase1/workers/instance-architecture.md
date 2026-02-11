# Worker: Instance Architecture

**Branch:** cz2/feat/instance-architecture
**Dependencies:** None
**Duration:** 2-3 days

## Mission

Enhance the existing HopperInstance model to support full multi-instance hierarchy with scope support, lifecycle management, and proper state tracking. This worker builds on the Phase 1 foundation to enable Global, Project, and Orchestration instances.

## Background

Phase 1 created the basic `HopperInstance` model. Phase 2 Week 3 focuses on extending this to support:
- Full scope differentiation (GLOBAL, PROJECT, ORCHESTRATION)
- Instance lifecycle states (CREATED, ACTIVE, PAUSED, STOPPED, ARCHIVED)
- Parent-child relationships with proper cascading
- Instance configuration per scope
- State management and transitions

## Tasks

### Task 1: Enhance HopperInstance Model

1. Update `src/hopper/models/hopper_instance.py`:
   - Add `status` field (InstanceStatus enum: CREATED, ACTIVE, PAUSED, STOPPED, ARCHIVED)
   - Add `started_at`, `stopped_at` timestamps
   - Add `config` JSONB field for scope-specific configuration
   - Add `metadata` JSONB field for runtime data
   - Enhance `scope` field with proper validation
   - Add parent_id foreign key with CASCADE behavior
   - Add instance hierarchy helpers (`get_ancestors()`, `get_descendants()`)

2. Create `src/hopper/models/enums.py` updates:
   - Add `InstanceStatus` enum
   - Enhance `HopperScope` enum with descriptions
   - Add `InstanceType` enum (SINGLETON, PERSISTENT, EPHEMERAL)

3. Update migrations:
   - Create Alembic migration for new fields
   - Add indexes on parent_id, scope, status
   - Add database constraints

**Checkpoint:** Commit enhanced HopperInstance model

### Task 2: Instance Lifecycle Management

1. Create `src/hopper/instance/lifecycle.py`:
   - InstanceLifecycleManager class
   - State transition validation
   - Lifecycle events (on_create, on_start, on_stop, on_archive)
   - State machine implementation
   - Audit logging for state changes

2. Create `src/hopper/instance/manager.py`:
   - InstanceManager class
   - Create instance with validation
   - Start/stop/pause/resume operations
   - Archive instance
   - Get instance by scope and name
   - Health check per instance

3. Implement state transitions:
   ```
   CREATED → ACTIVE → PAUSED → ACTIVE
                   ↓
                 STOPPED → ARCHIVED
   ```

4. Add lifecycle event hooks:
   - Before/after state transitions
   - Resource allocation/cleanup
   - Notification system

**Checkpoint:** Commit lifecycle management

### Task 3: Scope-Specific Configuration

1. Create `src/hopper/instance/config.py`:
   - InstanceConfig base class
   - GlobalConfig (for Global Hopper)
   - ProjectConfig (for Project Hopper)
   - OrchestrationConfig (for Orchestration Hopper)
   - Configuration validation per scope
   - Configuration defaults

2. Create configuration templates in `config/instances/`:
   - `global-instance.yaml` - Global Hopper default config
   - `project-instance.yaml` - Project Hopper default config
   - `orchestration-instance.yaml` - Orchestration Hopper default config

3. Example configuration structure:
   ```yaml
   # global-instance.yaml
   scope: GLOBAL
   routing:
     strategy: intelligent  # Uses LLM/Sage for routing
     fallback: rules
   delegation:
     enabled: true
     auto_create_project_instances: true
   limits:
     max_child_instances: 100
   ```

**Checkpoint:** Commit scope configuration system

### Task 4: Instance Repository Enhancements

1. Update `src/hopper/database/repositories/hopper_instance_repository.py`:
   - Add lifecycle operation methods
   - Add hierarchy query methods:
     - `get_instance_tree(root_id)` - Full hierarchy
     - `get_children(parent_id)` - Direct children
     - `get_ancestors(instance_id)` - Parent chain
     - `get_descendants(instance_id)` - All children
   - Add scope-based queries:
     - `get_global_instance()` - Singleton global
     - `get_project_instances(project_id)`
     - `get_orchestration_instances(project_id)`
   - Add status-based queries:
     - `get_active_instances()`
     - `get_instances_by_status(status)`

2. Add database indexes for performance:
   - Index on (scope, status)
   - Index on (parent_id, scope)
   - Index on (name, scope) unique

3. Add instance validation:
   - Validate scope hierarchy rules
   - Ensure only one global instance
   - Validate parent-child scope relationships

**Checkpoint:** Commit repository enhancements

### Task 5: API Endpoints for Instance Management

1. Update `src/hopper/api/routes/instances.py`:
   - Add lifecycle endpoints:
     - `POST /api/v1/instances/{id}/start` - Start instance
     - `POST /api/v1/instances/{id}/stop` - Stop instance
     - `POST /api/v1/instances/{id}/pause` - Pause instance
     - `POST /api/v1/instances/{id}/resume` - Resume instance
     - `POST /api/v1/instances/{id}/archive` - Archive instance

   - Add hierarchy endpoints:
     - `GET /api/v1/instances/{id}/children` - Get child instances
     - `GET /api/v1/instances/{id}/ancestors` - Get parent chain
     - `GET /api/v1/instances/{id}/tree` - Get full hierarchy

   - Add scope-specific endpoints:
     - `GET /api/v1/instances/global` - Get global instance
     - `GET /api/v1/instances/projects/{project_id}` - Get project instances

2. Update Pydantic schemas:
   - InstanceCreate with scope validation
   - InstanceUpdate with state transitions
   - InstanceLifecycleResponse
   - InstanceTreeResponse (nested structure)

**Checkpoint:** Commit API endpoints

### Task 6: Testing and Documentation

1. Create `tests/instance/test_lifecycle.py`:
   - Test state transitions
   - Test lifecycle events
   - Test invalid transitions
   - Test cascade behavior

2. Create `tests/instance/test_manager.py`:
   - Test instance creation
   - Test lifecycle operations
   - Test configuration validation

3. Create `tests/database/test_instance_repository_enhanced.py`:
   - Test hierarchy queries
   - Test scope queries
   - Test status queries
   - Test performance with deep hierarchies

4. Create `tests/api/test_instance_lifecycle.py`:
   - Test lifecycle API endpoints
   - Test hierarchy endpoints
   - Test validation

5. Create `docs/instance-architecture.md`:
   - Instance hierarchy overview
   - Scope descriptions
   - Lifecycle states and transitions
   - Configuration guide
   - API reference

**Checkpoint:** Commit tests and documentation

## Deliverables

- [ ] Enhanced HopperInstance model with status, lifecycle, config
- [ ] InstanceStatus and updated enums
- [ ] Instance lifecycle manager with state machine
- [ ] Scope-specific configuration system
- [ ] Configuration templates for all scopes
- [ ] Enhanced repository with hierarchy queries
- [ ] Lifecycle and hierarchy API endpoints
- [ ] Comprehensive test suite
- [ ] Instance architecture documentation

## Success Criteria

- ✅ HopperInstance supports all three scopes properly
- ✅ Lifecycle state machine works correctly
- ✅ Can create instances with scope-specific configs
- ✅ Hierarchy queries are performant
- ✅ State transitions are validated and logged
- ✅ API endpoints for lifecycle management work
- ✅ Only one global instance can exist
- ✅ Parent-child relationships enforce scope rules
- ✅ All tests pass

## References

- Implementation Plan: `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (Phase 2, Week 3)
- Specification: `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- Phase 1 HopperInstance: `src/hopper/models/hopper_instance.py`

## Notes

- Build on Phase 1 foundation - don't break existing functionality
- Lifecycle management is critical for resource cleanup
- Configuration system should be extensible for future scopes
- Hierarchy queries must be efficient (consider recursive CTEs)
- State transitions should be atomic and logged
- Each scope has different behavior - config system must support this
- Consider using database triggers for cascade operations
- Instance health checks important for monitoring
