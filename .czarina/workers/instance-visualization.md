# Worker: Instance Visualization

**Branch:** cz2/feat/instance-visualization
**Dependencies:** scope-behaviors
**Duration:** 1-2 days

## Mission

Build CLI commands and visualization tools for viewing instance hierarchy, monitoring status, and understanding the multi-instance system.

## Background

Phase 2 Week 4 requires:
- CLI command to view instance hierarchy
- ASCII tree visualization
- Instance status dashboard
- Task flow visualization
- Monitoring tools

## Tasks

### Task 1: Instance Tree Visualization

1. Create `src/hopper/cli/commands/tree.py`:
   - `hopper instance tree` - Show full hierarchy
   - ASCII tree rendering
   - Color-coded by scope
   - Status indicators
   - Task count per instance

2. Implement tree rendering:
   - Recursive hierarchy traversal
   - Rich formatting for terminal
   - Collapsible branches
   - Interactive mode

3. Example output:
   ```
   Global Hopper (hopper-global) [ACTIVE]
   ├── Project: czarina [ACTIVE] (12 tasks)
   │   ├── Orchestration: czarina-run-abc123 [ACTIVE] (8 workers)
   │   └── Orchestration: czarina-run-xyz789 [STOPPED]
   └── Project: hopper [ACTIVE] (5 tasks)
   ```

**Checkpoint:** Commit tree visualization

### Task 2: Instance Status Dashboard

1. Create `src/hopper/cli/commands/dashboard.py`:
   - `hopper instance dashboard` - Live dashboard
   - Real-time status updates
   - Metrics per instance
   - Health indicators
   - Task queues

2. Implement dashboard features:
   - Rich Live display
   - Auto-refresh
   - Color-coded health
   - Key metrics
   - Alert notifications

3. Dashboard sections:
   - Instance overview
   - Active tasks
   - Queue depths
   - Recent activity
   - Health status

**Checkpoint:** Commit status dashboard

### Task 3: Task Flow Visualization

1. Create `src/hopper/cli/commands/flow.py`:
   - `hopper task flow <task-id>` - Show task journey
   - Delegation chain visualization
   - Timeline of events
   - Status transitions
   - Instance hops

2. Implement flow diagram:
   - ASCII flowchart
   - Timestamps
   - Status changes
   - Delegation points

3. Example output:
   ```
   Task #42: Implement feature X

   2025-01-15 10:00  Created at Global Hopper
                     ↓ (delegated)
   2025-01-15 10:01  Routed to Project: hopper
                     ↓ (delegated)
   2025-01-15 10:02  Assigned to Orchestration: hopper-run-123
                     ↓ (assigned)
   2025-01-15 10:03  Worker: database started
   2025-01-15 11:30  Worker: database completed
                     ↑ (completed)
   2025-01-15 11:31  Orchestration marked complete
   ```

**Checkpoint:** Commit flow visualization

### Task 4: Monitoring and Metrics

1. Enhance `hopper status` command:
   - Instance counts
   - Active tasks per instance
   - Health summary
   - Resource usage

2. Create `hopper instance metrics <instance-id>`:
   - Detailed metrics
   - Performance stats
   - Historical data
   - Graphs (using Rich)

3. Add export options:
   - JSON export
   - CSV export
   - Prometheus format

**Checkpoint:** Commit monitoring tools

### Task 5: Interactive Exploration

1. Create `hopper instance explore`:
   - Interactive instance explorer
   - Navigate hierarchy with arrows
   - Drill into instance details
   - View tasks for instance
   - Quick actions (start/stop)

2. Add keyboard shortcuts:
   - Arrow keys: navigate
   - Enter: drill down
   - Backspace: go up
   - s: start instance
   - t: stop instance
   - q: quit

**Checkpoint:** Commit interactive tools

### Task 6: Testing and Documentation

1. Create test suite:
   - `tests/cli/test_tree.py`
   - `tests/cli/test_dashboard.py`
   - `tests/cli/test_flow.py`
   - `tests/cli/test_monitoring.py`

2. Update `docs/cli-guide.md`:
   - Instance visualization commands
   - Dashboard usage
   - Flow visualization
   - Monitoring guide

**Checkpoint:** Commit tests and docs

## Deliverables

- [ ] Instance tree visualization
- [ ] Live status dashboard
- [ ] Task flow visualization
- [ ] Monitoring and metrics tools
- [ ] Interactive explorer
- [ ] Export capabilities
- [ ] Comprehensive tests
- [ ] Documentation updates

## Success Criteria

- ✅ Can visualize instance hierarchy clearly
- ✅ Dashboard shows real-time status
- ✅ Task flow shows complete journey
- ✅ Metrics help understand system health
- ✅ Interactive tools are intuitive
- ✅ Export formats work correctly
- ✅ All tests pass

## References

- Implementation Plan: Phase 2, Week 4
- Rich library: https://rich.readthedocs.io/

## Notes

- Use Rich library for beautiful terminal output
- Dashboard should be usable for monitoring
- Visualization helps understand complex hierarchies
- Export formats enable integration with monitoring tools
- Interactive explorer great for debugging
- Consider adding web dashboard (future phase)
