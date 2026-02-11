# Worker: Instance Registry

**Branch:** cz2/feat/instance-registry
**Dependencies:** instance-architecture
**Duration:** 2 days

## Mission

Create instance registry and discovery system that tracks all Hopper instances, manages parent-child relationships, and provides efficient instance lookup and monitoring.

## Background

Phase 2 Week 3 requires:
- Central registry for all instances
- Discovery mechanism for finding instances
- Parent-child relationship management
- Instance health monitoring
- Registration/deregistration

## Tasks

### Task 1: Instance Registry Core

1. Create `src/hopper/instance/registry.py`:
   - InstanceRegistry class (singleton)
   - Register/unregister instances
   - Instance lookup by ID, name, scope
   - Parent-child relationship tracking
   - Instance health tracking

2. Create `src/hopper/instance/discovery.py`:
   - Instance discovery service
   - Find instances by criteria
   - Discover available parent instances
   - Discover child instances
   - Auto-discovery on startup

**Checkpoint:** Commit registry core

### Task 2: Parent-Child Relationship Management

1. Create `src/hopper/instance/relationships.py`:
   - Relationship validation (scope rules)
   - Add child to parent
   - Remove child from parent
   - Orphan detection
   - Cascade operations

2. Implement hierarchy rules:
   - Global can have Project children
   - Project can have Orchestration children
   - Orchestration cannot have children
   - Only one Global instance allowed

3. Add relationship events:
   - on_child_added
   - on_child_removed
   - on_parent_changed

**Checkpoint:** Commit relationship management

### Task 3: Health Monitoring

1. Create `src/hopper/instance/health.py`:
   - Health check system
   - Instance heartbeat
   - Status reporting
   - Failure detection
   - Auto-restart policies

2. Add health metrics:
   - Active task count
   - Queue depth
   - Response time
   - Error rate
   - Uptime

**Checkpoint:** Commit health monitoring

### Task 4: Registry API and Integration

1. Create API endpoints in `src/hopper/api/routes/registry.py`:
   - `GET /api/v1/registry/instances` - List all instances
   - `GET /api/v1/registry/discover` - Discover instances
   - `GET /api/v1/registry/health` - Health status
   - `GET /api/v1/registry/topology` - Instance topology

2. Integrate registry with instance lifecycle
3. Auto-register instances on creation
4. Auto-deregister on deletion

**Checkpoint:** Commit API integration

### Task 5: Testing and Documentation

1. Create test suite:
   - `tests/instance/test_registry.py`
   - `tests/instance/test_discovery.py`
   - `tests/instance/test_relationships.py`
   - `tests/instance/test_health.py`

2. Create `docs/instance-registry.md`:
   - Registry architecture
   - Discovery mechanisms
   - Relationship rules
   - Health monitoring

**Checkpoint:** Commit tests and docs

## Deliverables

- [ ] Instance registry system
- [ ] Discovery service
- [ ] Parent-child relationship management
- [ ] Health monitoring
- [ ] Registry API endpoints
- [ ] Comprehensive tests
- [ ] Documentation

## Success Criteria

- ✅ All instances are tracked in registry
- ✅ Can discover instances by criteria
- ✅ Parent-child relationships validated
- ✅ Health monitoring detects failures
- ✅ Registry integrates with lifecycle
- ✅ All tests pass

## References

- Implementation Plan: Phase 2, Week 3
- Specification: Instance hierarchy section

## Notes

- Registry must be fast (in-memory cache + database)
- Health monitoring critical for production
- Relationship rules must be enforced strictly
- Discovery should support multiple criteria
