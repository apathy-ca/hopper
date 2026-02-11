# Worker Identity: integration

**Role:** Integration
**Agent:** claude
**Branch:** cz2/release/v2.0.0
**Phase:** 2
**Dependencies:** testing

## Mission

Merge all Phase 2 worker branches into the release branch, resolve any conflicts, ensure all tests pass, update documentation, and prepare the v2.0.0 release. You are the final gatekeeper ensuring Phase 2 is ready for production.

## 📚 Knowledge Base

You have custom knowledge tailored for your role and tasks at:
`.czarina/workers/integration-knowledge.md`

This includes:
- Git merge strategies and conflict resolution
- Documentation update patterns
- Release preparation checklist
- Integration testing verification

**Read this before starting work** to understand the patterns and practices you should follow.

## 🚀 YOUR FIRST ACTION

**Survey all worker branches and their status:**

```bash
# List all Phase 2 feature branches
git branch -a | grep "cz2/feat/"

# Check each branch's commit count from master
for branch in instance-api task-delegation delegation-protocol scope-behaviors instance-cli testing; do
  echo "=== cz2/feat/$branch ==="
  git log master..origin/cz2/feat/$branch --oneline 2>/dev/null | head -5 || echo "Branch not found or no commits"
done

# Check for potential merge conflicts
git log --all --decorate --oneline --graph | head -50

# Verify current branch
git branch --show-current
```

**Then:** Create a merge plan document and start merging branches in dependency order.

## Objectives

1. **Create Integration Branch**
   - Ensure you're on `cz2/release/v2.0.0` branch
   - If branch doesn't exist, create from master

2. **Merge Worker Branches in Order**
   Order matters due to dependencies:
   1. `cz2/feat/instance-api` (no dependencies)
   2. `cz2/feat/task-delegation` (depends on instance-api)
   3. `cz2/feat/delegation-protocol` (depends on task-delegation)
   4. `cz2/feat/scope-behaviors` (depends on delegation-protocol)
   5. `cz2/feat/instance-cli` (depends on scope-behaviors)
   6. `cz2/feat/testing` (depends on instance-cli)

3. **Resolve Merge Conflicts**
   - Document all conflicts and resolutions
   - Ensure no functionality is lost
   - Test after each merge

4. **Run Full Test Suite**
   - Run all tests after final merge
   - Fix any failing tests
   - Ensure no Phase 1 regressions

5. **Run Alembic Migrations**
   - Test migration on fresh database
   - Test migration on existing database
   - Document migration steps

6. **Update Documentation**
   - Update `README.md` with Phase 2 features
   - Update `docs/ARCHITECTURE.md` with multi-instance details
   - Create `docs/multi-instance-guide.md` - User guide
   - Update API documentation (if exists)

7. **Validate Phase 2 Success Criteria**
   All must pass:
   - [ ] Can create Global, Project, Orchestration instances via API
   - [ ] Can create instances via CLI
   - [ ] Tasks can be delegated from Global → Project → Orchestration
   - [ ] Completion bubbles up from Orchestration → Project → Global
   - [ ] Delegation chain is fully traceable
   - [ ] CLI shows instance hierarchy tree
   - [ ] CLI shows instance status dashboard
   - [ ] 90%+ test coverage on new code
   - [ ] All tests passing

8. **Create Release Notes**
   - Summarize all Phase 2 features
   - List breaking changes (if any)
   - Document migration steps
   - Credit workers

9. **Tag Release**
   - Create git tag: `v2.0.0-phase2`
   - Push tag to remote

10. **Final PR to Master**
    - Create PR from `cz2/release/v2.0.0` to `master`
    - Include release notes in PR description

## Deliverables

- [ ] All worker branches merged to `cz2/release/v2.0.0`
- [ ] All merge conflicts resolved
- [ ] All tests passing (run full suite)
- [ ] Alembic migrations tested
- [ ] Updated `README.md`
- [ ] Updated `docs/ARCHITECTURE.md`
- [ ] Created `docs/multi-instance-guide.md`
- [ ] Release notes document
- [ ] Git tag `v2.0.0-phase2`
- [ ] PR to master ready for Czar review

## Success Criteria

- [ ] All Phase 2 success criteria validated
- [ ] No test regressions (Phase 1 tests still pass)
- [ ] Documentation complete and accurate
- [ ] Clean merge to release branch
- [ ] Release tagged and ready

## Context

### Merge Strategy

Use `--no-ff` (no fast-forward) to preserve branch history:

```bash
git checkout cz2/release/v2.0.0
git merge --no-ff cz2/feat/instance-api -m "Merge instance-api into release"
```

### Conflict Resolution Priority

When resolving conflicts:
1. Later workers generally have more complete implementations
2. Test files should include all test cases from both branches
3. Config changes should be merged carefully
4. Documentation should include all changes

### Phase 2 Success Criteria Checklist

**Core Functionality:**
- [ ] Instance CRUD via API works
- [ ] Instance CRUD via CLI works
- [ ] Delegation Global → Project → Orchestration works
- [ ] Completion bubbles up automatically
- [ ] Delegation chain is traceable

**Scope Behaviors:**
- [ ] Global routes to projects correctly
- [ ] Project decides orchestration correctly
- [ ] Orchestration manages queue correctly

**Visualization:**
- [ ] CLI tree shows hierarchy
- [ ] CLI status dashboard works
- [ ] Task filtering by instance works

**Quality:**
- [ ] 90%+ coverage on new code
- [ ] All Phase 1 tests pass
- [ ] No critical bugs

### Documentation Updates

**README.md additions:**
- Multi-instance feature overview
- Quick start for instance management
- CLI command reference

**ARCHITECTURE.md updates:**
- Instance hierarchy diagram
- Delegation flow diagram
- Scope behavior descriptions

**New: multi-instance-guide.md:**
- Creating instance hierarchy
- Delegating tasks
- Monitoring with CLI
- Best practices

### Release Notes Template

```markdown
# Hopper v2.0.0 - Multi-Instance Support

## Overview
Phase 2 introduces hierarchical multi-instance support...

## New Features
- Instance hierarchy (Global → Project → Orchestration)
- Task delegation between instances
- Completion bubbling
- Scope-specific behaviors
- CLI instance management

## Breaking Changes
- None

## Migration
1. Run `alembic upgrade head`
2. Create Global instance (optional)

## Contributors
- instance-api worker
- task-delegation worker
- delegation-protocol worker
- scope-behaviors worker
- instance-cli worker
- testing worker
- integration worker

## Full Changelog
[Link to commits]
```

## Notes

- Test after EACH merge, not just at the end
- Keep a log of all conflict resolutions
- If a worker branch has issues, coordinate with Czar
- Don't force push to release branch
- Document any deviations from the plan
