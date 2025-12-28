# Hopper Phase 2 Czarina Orchestration

This directory contains the Czarina orchestration configuration for Hopper Phase 2 (Multi-Instance Support).

## Overview

**Project:** Hopper - Universal Task Queue
**Version:** 2.0.0
**Phase:** 2 (Multi-Instance Support)
**Omnibus Branch:** `cz2/release/v2.0.0-phase2`

## Phase 2 Goals

Implement hierarchical Hopper instances with:
- Global → Project → Orchestration hierarchy
- Task delegation between instances
- Completion notification bubbling up
- Scope-specific routing behaviors
- Instance visualization and monitoring
- Czarina integration for orchestrations

## Workers

Phase 2 consists of 7 workers organized in dependency order:

### 1. instance-architecture
**Branch:** `cz2/feat/instance-architecture`
**Dependencies:** None
**Mission:** Enhance HopperInstance model with scope support, lifecycle management, and configuration

**Key Deliverables:**
- Enhanced HopperInstance model with status, lifecycle states
- Instance lifecycle manager with state machine
- Scope-specific configuration system
- Configuration templates for all scopes
- Enhanced repository with hierarchy queries

### 2. instance-registry
**Branch:** `cz2/feat/instance-registry`
**Dependencies:** instance-architecture
**Mission:** Create instance registry and discovery system

**Key Deliverables:**
- Central instance registry
- Discovery service
- Parent-child relationship management
- Health monitoring
- Registry API endpoints

### 3. delegation-protocol
**Branch:** `cz2/feat/delegation-protocol`
**Dependencies:** instance-registry
**Mission:** Implement task delegation and completion notification between instances

**Key Deliverables:**
- Delegation protocol implementation
- Multi-instance routing logic
- Completion notification system
- Coordination protocol
- Delegation API endpoints

### 4. scope-behaviors
**Branch:** `cz2/feat/scope-behaviors`
**Dependencies:** delegation-protocol
**Mission:** Implement Global, Project, and Orchestration specific routing logic

**Key Deliverables:**
- Global Hopper routing to projects
- Project Hopper orchestration decisions
- Orchestration Hopper worker queue management
- Scope-specific intelligence
- Czarina integration

### 5. instance-visualization
**Branch:** `cz2/feat/instance-visualization`
**Dependencies:** scope-behaviors
**Mission:** Build CLI commands and tools for viewing instance hierarchy

**Key Deliverables:**
- Instance tree visualization
- Live status dashboard
- Task flow visualization
- Monitoring and metrics tools
- Interactive explorer

### 6. testing
**Branch:** `cz2/feat/testing`
**Dependencies:** instance-visualization
**Mission:** Create comprehensive test suite for Phase 2 features

**Key Deliverables:**
- Instance architecture tests
- Registry and discovery tests
- Delegation protocol tests
- Scope behavior tests
- Integration and E2E tests
- Performance tests
- >90% code coverage

### 7. integration
**Branch:** `cz2/feat/integration`
**Dependencies:** testing
**Role:** integration
**Mission:** Merge all workers and prepare Phase 2 release

**Key Deliverables:**
- All workers merged
- Conflicts resolved
- Phase 2 documentation
- Release preparation
- Phase 2 validation

## Worker Dependency Graph

```
instance-architecture (foundation)
    └── instance-registry
        └── delegation-protocol
            └── scope-behaviors
                └── instance-visualization
                    └── testing
                        └── integration (merges all)
```

## Phase 2 Success Criteria

- ✅ Can create Global, Project, and Orchestration instances
- ✅ Tasks flow down hierarchy (Global → Project → Orchestration)
- ✅ Completion bubbles up hierarchy
- ✅ Each scope has appropriate configuration
- ✅ Can visualize instance tree
- ✅ Czarina can use Orchestration Hopper for runs

## Getting Started

1. **Launch Phase 2 orchestration:**
   ```bash
   czarina launch
   ```

2. **Monitor progress:**
   ```bash
   czarina status
   czarina dashboard
   ```

3. **View worker details:**
   ```bash
   cat .czarina/workers/<worker-id>.md
   ```

## Architecture

Phase 2 extends the Phase 1 foundation with:

**Multi-Instance Hierarchy:**
```
Global Hopper (hopper-global)
├── Project Hopper: czarina
│   ├── Orchestration Hopper: czarina-run-abc123
│   └── Orchestration Hopper: czarina-run-xyz789
└── Project Hopper: hopper
    └── Orchestration Hopper: hopper-dev-001
```

**Delegation Flow:**
```
1. Task created at Global Hopper
2. Global routes to best Project Hopper
3. Project decides: orchestration or manual
4. If orchestration: creates Orchestration Hopper
5. Orchestration distributes to workers
6. Workers complete tasks
7. Completion bubbles up to Global
```

## Technology Stack

Same as Phase 1, with additions:
- **Instance Management:** Lifecycle state machine
- **Delegation:** Event-driven coordination
- **Visualization:** Rich terminal dashboards
- **Monitoring:** Health checks and metrics

## References

- **Implementation Plan:** `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md` (Phase 2)
- **Specification:** `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- **Phase 1 Archive:** `.czarina/phases/phase-1-v1.0.0/`

## Notes

- Phase 2 builds on Phase 1 foundation
- Multi-instance architecture is core feature
- Czarina integration is primary use case
- Visualization helps understand hierarchy
- Testing is critical due to complexity
- Phase 3 will add 3-tier memory system

## Transition from Phase 1

Phase 1 completed:
- ✅ Core task queue with MCP, API, CLI
- ✅ Rules-based routing
- ✅ Database layer
- ✅ Basic instance model

Phase 2 extends:
- 🚀 Full instance hierarchy
- 🚀 Delegation protocol
- 🚀 Scope-specific behaviors
- 🚀 Visualization tools

---

**Czarina Orchestration:** v0.7.0
**Created:** 2025-12-28
**Status:** Ready for implementation
**Previous Phase:** phase-1-v1.0.0 (archived)
