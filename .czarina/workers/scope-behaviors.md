# Worker: Scope Behaviors

**Branch:** cz2/feat/scope-behaviors
**Dependencies:** delegation-protocol
**Duration:** 2-3 days

## Mission

Implement scope-specific behavior for Global, Project, and Orchestration Hoppers. Each scope has unique routing logic, task handling, and operational characteristics.

## Background

Phase 2 Week 4 focuses on:
- Global Hopper: Strategic routing to projects
- Project Hopper: Decides orchestration vs manual handling
- Orchestration Hopper: Manages worker queues
- Configuration templates per scope
- Scope-specific intelligence

## Tasks

### Task 1: Global Hopper Behavior

1. Create `src/hopper/instance/scopes/global_hopper.py`:
   - GlobalHopper class
   - Strategic routing to best project
   - Project selection algorithm
   - Load balancing across projects
   - Fallback project handling

2. Implement Global routing logic:
   - Analyze task characteristics
   - Match to project capabilities
   - Consider project load
   - Route to appropriate Project Hopper
   - Handle unknown tasks

3. Add Global-specific features:
   - Cross-project insights
   - System-wide metrics
   - Strategic prioritization
   - Resource allocation

**Checkpoint:** Commit Global Hopper

### Task 2: Project Hopper Behavior

1. Create `src/hopper/instance/scopes/project_hopper.py`:
   - ProjectHopper class
   - Orchestration vs manual decision
   - Task complexity analysis
   - Orchestration triggering
   - Manual task queueing

2. Implement Project routing logic:
   - Analyze task requirements
   - Determine if orchestration needed
   - Create Orchestration instance if needed
   - Delegate to Orchestration or handle manually
   - Manage multiple orchestrations

3. Add Project-specific features:
   - Project-specific routing rules
   - Team capacity tracking
   - Project metrics
   - Orchestration history

**Checkpoint:** Commit Project Hopper

### Task 3: Orchestration Hopper Behavior

1. Create `src/hopper/instance/scopes/orchestration_hopper.py`:
   - OrchestrationHopper class
   - Worker queue management
   - Task distribution to workers
   - Worker dependency handling
   - Completion tracking

2. Implement Orchestration queue logic:
   - Maintain worker queues
   - Respect dependencies
   - Distribute tasks fairly
   - Track worker progress
   - Handle worker failures

3. Add Orchestration-specific features:
   - Czarina integration
   - Worker health monitoring
   - Progress reporting
   - Checkpoint management

4. Create Czarina integration:
   - Bridge to Czarina orchestration
   - Worker status reporting
   - Task assignment coordination

**Checkpoint:** Commit Orchestration Hopper

### Task 4: Scope Intelligence Layer

1. Create `src/hopper/intelligence/scope_intelligence.py`:
   - Scope-specific intelligence adapters
   - GlobalIntelligence
   - ProjectIntelligence
   - OrchestrationIntelligence

2. Enhance routing for each scope:
   - Global: Use LLM for project matching
   - Project: Rules + heuristics for orchestration decision
   - Orchestration: Dependency-aware scheduling

3. Add intelligence configuration per scope

**Checkpoint:** Commit scope intelligence

### Task 5: Configuration Templates

1. Enhance configuration templates:
   - `config/instances/global-instance.yaml`
   - `config/instances/project-instance.yaml`
   - `config/instances/orchestration-instance.yaml`

2. Add scope-specific settings:
   - Routing strategies
   - Thresholds
   - Limits
   - Behaviors

3. Create example configurations:
   - Different project types
   - Different orchestration patterns

**Checkpoint:** Commit configuration templates

### Task 6: Testing and Documentation

1. Create test suite:
   - `tests/instance/scopes/test_global_hopper.py`
   - `tests/instance/scopes/test_project_hopper.py`
   - `tests/instance/scopes/test_orchestration_hopper.py`
   - `tests/instance/test_scope_intelligence.py`
   - `tests/integration/test_scope_behaviors.py`

2. Create `docs/scope-behaviors.md`:
   - Overview of each scope
   - Behavior descriptions
   - Configuration options
   - Examples and workflows

**Checkpoint:** Commit tests and docs

## Deliverables

- [ ] Global Hopper implementation
- [ ] Project Hopper implementation
- [ ] Orchestration Hopper implementation
- [ ] Scope-specific intelligence
- [ ] Configuration templates for all scopes
- [ ] Czarina integration
- [ ] Comprehensive tests
- [ ] Documentation

## Success Criteria

- ✅ Global routes to best project accurately
- ✅ Project decides orchestration vs manual correctly
- ✅ Orchestration manages worker queues effectively
- ✅ Each scope has appropriate configuration
- ✅ Czarina integration works for orchestrations
- ✅ Scope-specific intelligence improves routing
- ✅ All tests pass

## References

- Implementation Plan: Phase 2, Week 4
- Specification: Multi-instance hierarchy

## Notes

- Each scope has very different behavior
- Global should use intelligent routing (LLM/Sage)
- Project needs good heuristics for orchestration decision
- Orchestration must integrate seamlessly with Czarina
- Configuration should be easily customizable
- Test with real Czarina orchestration scenarios
