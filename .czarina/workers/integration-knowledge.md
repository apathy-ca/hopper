# Knowledge Base: integration

Custom knowledge for the Integration worker, extracted from agent-knowledge library.

## Git Merge Workflow

### Merge Strategy

```bash
# Always use --no-ff to preserve branch history
git merge --no-ff cz2/feat/instance-api -m "Merge instance-api into release"

# DO NOT use fast-forward merges
# git merge cz2/feat/instance-api  # Bad - loses branch history
```

### Merge Order (Dependency-Based)

```bash
# Phase 2 merge order:
# 1. instance-api (no dependencies)
# 2. task-delegation (depends on instance-api)
# 3. delegation-protocol (depends on task-delegation)
# 4. scope-behaviors (depends on delegation-protocol)
# 5. instance-cli (depends on scope-behaviors)
# 6. testing (depends on instance-cli)

# Example workflow
git checkout cz2/release/v2.0.0

# Merge each in order
for branch in instance-api task-delegation delegation-protocol scope-behaviors instance-cli testing; do
  echo "=== Merging cz2/feat/$branch ==="
  git merge --no-ff origin/cz2/feat/$branch -m "Merge $branch into release"

  # Run tests after each merge
  pytest tests/phase2/ -x

  if [ $? -ne 0 ]; then
    echo "Tests failed after merging $branch"
    exit 1
  fi
done
```

## Conflict Resolution

### Common Conflict Patterns

```bash
# Check for conflicts before merge
git merge --no-commit --no-ff origin/cz2/feat/branch-name

# If conflicts:
git status  # Shows conflicted files

# Resolve conflicts manually, then:
git add <resolved-files>
git commit -m "Merge branch-name into release

Resolved conflicts in:
- path/to/file1.py: Description of resolution
- path/to/file2.py: Description of resolution"
```

### Resolution Priority Rules

1. **Later workers have priority** for implementation logic
2. **Merge all test cases** from both branches
3. **Config changes** should combine settings from both
4. **Documentation** should include all changes
5. **Model changes** - careful review for schema compatibility

### Import Conflict Example

```python
# CONFLICT in __init__.py
<<<<<<< HEAD
from .task import Task
from .hopper_instance import HopperInstance
=======
from .task import Task
from .task_delegation import TaskDelegation
>>>>>>> cz2/feat/task-delegation

# RESOLUTION - include all imports
from .task import Task
from .hopper_instance import HopperInstance
from .task_delegation import TaskDelegation
```

## Verification Checklist

### After Each Merge

```bash
# 1. Run tests
pytest tests/phase2/ -v

# 2. Check for import errors
python -c "from hopper.models import *"
python -c "from hopper.api.routes import *"

# 3. Run type checking
mypy src/hopper/

# 4. Run linting
ruff check src/hopper/
```

### After All Merges

```bash
# 1. Run full test suite
pytest --cov=src/hopper --cov-report=term-missing

# 2. Check coverage meets 90%
pytest --cov=src/hopper --cov-report=xml
coverage report --fail-under=90

# 3. Test migrations
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# 4. Test CLI
hopper instance list
hopper instance tree

# 5. Test API (start server)
uvicorn hopper.api.app:app &
curl http://localhost:8000/api/v1/instances
```

## Documentation Updates

### README.md Template Addition

```markdown
## Multi-Instance Support (v2.0.0)

Hopper v2.0.0 introduces hierarchical multi-instance support:

- **Global Hopper**: Strategic routing across all projects
- **Project Hopper**: Tactical decisions per project
- **Orchestration Hopper**: Task execution and worker management

### Quick Start

```bash
# List instances
hopper instance list

# View hierarchy
hopper instance tree

# Create project instance
hopper instance create --name "my-project" --scope PROJECT --parent global-001
```

### API Endpoints

- `POST /api/v1/instances` - Create instance
- `GET /api/v1/instances` - List instances
- `GET /api/v1/instances/{id}/hierarchy` - Get hierarchy tree
- `POST /api/v1/tasks/{id}/delegate` - Delegate task

See [Multi-Instance Guide](docs/multi-instance-guide.md) for details.
```

### Architecture Doc Updates

```markdown
## Instance Hierarchy

```
Global Hopper (scope=GLOBAL)
├── Project Hopper: project-a (scope=PROJECT)
│   ├── Orchestration: orch-001 (scope=ORCHESTRATION)
│   └── Orchestration: orch-002 (scope=ORCHESTRATION)
└── Project Hopper: project-b (scope=PROJECT)
    └── Orchestration: orch-003 (scope=ORCHESTRATION)
```

### Task Delegation Flow

1. Task created at any instance level
2. Scope behavior determines routing
3. Delegation records track movement
4. Completion bubbles up hierarchy

### Scope Responsibilities

| Scope | Primary Role | Can Execute |
|-------|-------------|-------------|
| GLOBAL | Route to projects | No |
| PROJECT | Decide orchestration | Yes (simple) |
| ORCHESTRATION | Execute tasks | Yes (all) |
```

## Release Notes Template

```markdown
# Hopper v2.0.0 Release Notes

## Overview

Phase 2 implements multi-instance support for Hopper, enabling:
- Hierarchical instance management (Global → Project → Orchestration)
- Task delegation between instances
- Completion bubbling up the hierarchy
- Scope-specific routing behaviors

## New Features

### Instance Management
- Create, list, and manage instances via API and CLI
- View instance hierarchy as tree visualization
- Instance lifecycle management (start, stop, pause, resume)

### Task Delegation
- Delegate tasks from higher to lower scope levels
- Track delegation chain for any task
- Automatic completion bubbling when tasks finish

### Scope Behaviors
- Global: Routes tasks to appropriate projects
- Project: Decides between direct handling and orchestration
- Orchestration: Manages worker queue and execution

### CLI Enhancements
- `hopper instance tree` - View hierarchy
- `hopper instance status` - Status dashboard
- `hopper task delegate` - Delegate tasks
- Task filtering by instance

## Breaking Changes

None. All Phase 1 APIs remain unchanged.

## Migration Guide

1. Update to v2.0.0:
   ```bash
   pip install hopper==2.0.0
   ```

2. Run migrations:
   ```bash
   alembic upgrade head
   ```

3. (Optional) Create Global instance:
   ```bash
   hopper instance create --name "my-global" --scope GLOBAL
   ```

## API Reference

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | /api/v1/instances | Create instance |
| GET | /api/v1/instances | List instances |
| GET | /api/v1/instances/{id} | Get instance |
| PUT | /api/v1/instances/{id} | Update instance |
| DELETE | /api/v1/instances/{id} | Delete instance |
| GET | /api/v1/instances/{id}/hierarchy | Get hierarchy |
| POST | /api/v1/instances/{id}/start | Start instance |
| POST | /api/v1/instances/{id}/stop | Stop instance |
| POST | /api/v1/tasks/{id}/delegate | Delegate task |
| GET | /api/v1/tasks/{id}/delegation-chain | Get chain |

## Contributors

This release was built by the Czarina orchestration:
- instance-api: API endpoints
- task-delegation: Delegation model
- delegation-protocol: Delegation logic
- scope-behaviors: Scope implementations
- instance-cli: CLI commands
- testing: Test suite
- integration: Release coordination

## Known Issues

None.

## Full Changelog

See commit history: `git log v1.0.0..v2.0.0`
```

## Release Tagging

```bash
# Create annotated tag
git tag -a v2.0.0-phase2 -m "Release v2.0.0: Multi-Instance Support

Features:
- Instance hierarchy (Global/Project/Orchestration)
- Task delegation between instances
- Completion bubbling
- Scope-specific behaviors
- CLI instance management

See RELEASE_NOTES.md for details."

# Push tag
git push origin v2.0.0-phase2
```

## PR to Master

```markdown
## Summary

Phase 2: Multi-Instance Support for Hopper

## Changes

- Instance hierarchy (Global → Project → Orchestration)
- Task delegation protocol
- Completion bubbling
- Scope-specific behaviors
- CLI instance management
- 90%+ test coverage on new code

## Test Results

- All Phase 2 tests passing
- All Phase 1 tests passing (no regressions)
- Coverage: 92% on Phase 2 modules

## Documentation

- ✅ README.md updated
- ✅ ARCHITECTURE.md updated
- ✅ multi-instance-guide.md created
- ✅ Release notes

## Validation

All Phase 2 success criteria met:
- [x] Instance CRUD via API and CLI
- [x] Delegation Global → Project → Orchestration
- [x] Completion bubbling works
- [x] CLI tree and status dashboard
- [x] 90%+ coverage

## Merge Strategy

Squash merge to main recommended.
```

## Best Practices

### DO
- Test after EVERY merge
- Keep log of conflict resolutions
- Document all deviations from plan
- Verify migrations on fresh and existing DBs
- Run full test suite before tagging

### DON'T
- Force push to release branch
- Skip testing between merges
- Merge without reviewing changes
- Tag before all tests pass

## References

- Git workflow: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/workflows/GIT_WORKFLOW.md`
- PR requirements: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/workflows/PR_REQUIREMENTS.md`
- Documentation workflow: `/home/exedev/czarina/czarina-core/patterns/agent-knowledge/core-rules/workflows/DOCUMENTATION_WORKFLOW.md`
