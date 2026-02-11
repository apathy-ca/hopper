# Worker: Integration

**Branch:** cz2/feat/integration
**Dependencies:** testing
**Duration:** 2-3 days

## Mission

Merge all Phase 2 worker branches, resolve conflicts, ensure everything works together, validate Phase 2 success criteria, and prepare the Phase 2 release.

## Background

This integration worker merges:
- instance-architecture
- instance-registry
- delegation-protocol
- scope-behaviors
- instance-visualization
- testing

And ensures Phase 2 multi-instance support is production-ready.

## Tasks

### Task 1: Review All Worker Branches

1. Check status of Phase 2 worker branches:
   ```bash
   git branch --list 'cz2/feat/*'
   ```

2. Review each worker's deliverables:
   - instance-architecture: Enhanced model, lifecycle
   - instance-registry: Registry, discovery, health
   - delegation-protocol: Delegation, completion, coordination
   - scope-behaviors: Global, Project, Orchestration logic
   - instance-visualization: CLI tools, dashboards
   - testing: Comprehensive test suite

3. Create integration checklist and plan merge order

**Checkpoint:** Document integration plan

### Task 2: Merge Worker Branches in Dependency Order

1. Merge in order:
   ```
   1. instance-architecture (foundation)
   2. instance-registry (depends on architecture)
   3. delegation-protocol (depends on registry)
   4. scope-behaviors (depends on delegation)
   5. instance-visualization (depends on behaviors)
   6. testing (depends on all)
   ```

2. For each merge:
   - Run tests before merge
   - Merge with `git merge --no-ff cz2/feat/<worker-id>`
   - Resolve conflicts carefully
   - Test after merge
   - Fix integration issues

3. Document conflict resolutions

**Checkpoint:** All workers merged

### Task 3: Integration Testing and Bug Fixes

1. Run full test suite:
   ```bash
   pytest tests/ -v --cov=src/hopper
   ```

2. Verify all Phase 2 success criteria:
   - ✅ Can create Global, Project, and Orchestration instances
   - ✅ Tasks flow down hierarchy
   - ✅ Completion bubbles up hierarchy
   - ✅ Each scope has appropriate configuration
   - ✅ Can visualize instance tree
   - ✅ Czarina can use Orchestration Hopper

3. Test multi-instance workflows end-to-end
4. Fix integration bugs
5. Performance testing
6. Load testing

**Checkpoint:** All tests passing, bugs fixed

### Task 4: Code Quality and Consistency

1. Run quality checks:
   ```bash
   black src/ tests/
   ruff check src/ tests/
   mypy src/
   ```

2. Fix issues and ensure consistency
3. Add missing docstrings
4. Update type hints

**Checkpoint:** Code quality passing

### Task 5: Documentation Integration

1. Create comprehensive Phase 2 documentation:
   - Update README with Phase 2 features
   - Create ARCHITECTURE_PHASE2.md
   - Document multi-instance hierarchy
   - Add configuration examples
   - Update API reference

2. Create `docs/multi-instance-guide.md`:
   - Overview of multi-instance system
   - How to use each scope
   - Delegation workflows
   - Configuration guide
   - Troubleshooting

3. Update CHANGELOG for Phase 2

**Checkpoint:** Documentation complete

### Task 6: Czarina Integration Validation

1. Test Hopper with real Czarina orchestration:
   - Create Orchestration Hopper
   - Feed tasks to Czarina workers
   - Validate coordination
   - Test status updates

2. Document Czarina-Hopper integration:
   - How to set up
   - Configuration
   - Workflows
   - Examples

**Checkpoint:** Czarina integration validated

### Task 7: Release Preparation

1. Update version numbers:
   - pyproject.toml: version = "2.0.0"
   - __init__.py: __version__ = "2.0.0"

2. Create release notes `RELEASE_NOTES_PHASE2.md`:
   - Phase 2 overview
   - New features
   - Breaking changes
   - Migration guide from Phase 1
   - Known issues

3. Tag release:
   ```bash
   git tag -a v2.0.0-phase2 -m "Phase 2 Complete: Multi-Instance Support"
   ```

**Checkpoint:** Release ready

### Task 8: Final Validation and Handoff

1. Complete validation:
   - Fresh installation test
   - All features work
   - Documentation accurate
   - No critical bugs

2. Create `INTEGRATION_SUMMARY_PHASE2.md`:
   - What was integrated
   - Conflicts resolved
   - Integration challenges
   - Test results
   - Code coverage
   - Performance metrics
   - Recommendations for Phase 3

3. Prepare for Phase 3 (Memory & Learning)

**Checkpoint:** Integration complete

## Deliverables

- [ ] All Phase 2 workers merged
- [ ] All conflicts resolved
- [ ] Full test suite passing
- [ ] Code quality checks passing
- [ ] Comprehensive Phase 2 documentation
- [ ] Czarina integration validated
- [ ] CHANGELOG and release notes
- [ ] Version tagged (v2.0.0-phase2)
- [ ] Integration summary
- [ ] Ready for Phase 3

## Success Criteria

- ✅ All 6 worker branches merged successfully
- ✅ Zero merge conflicts remaining
- ✅ All tests passing (unit, integration, e2e)
- ✅ Code coverage >90% for Phase 2 features
- ✅ All Phase 2 success criteria met
- ✅ Czarina integration works
- ✅ Multi-instance hierarchy functional
- ✅ CLI visualization tools work
- ✅ Documentation complete
- ✅ Ready for production use

## References

- Implementation Plan: Phase 2
- All worker branches: cz2/feat/*
- Phase 2 Success Criteria

## Notes

- Integration is critical - take time for quality
- Test multi-instance scenarios thoroughly
- Czarina integration is key use case
- Document integration issues for learning
- Prepare handoff notes for Phase 3
- Consider creating regression tests
- Performance metrics important for production
