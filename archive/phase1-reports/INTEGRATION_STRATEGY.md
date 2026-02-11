# Integration Strategy for Phase 1

**Created:** 2025-12-28
**Worker:** integration
**Branch:** cz1/feat/integration

## Overview

This document outlines the detailed strategy for integrating all Phase 1 worker branches into a unified, tested, and production-ready codebase.

## Integration Philosophy

**Key Principles:**
1. **Test after every merge** - Catch integration issues early
2. **Preserve history** - Use `--no-ff` to maintain worker context
3. **Document conflicts** - Record all resolution decisions
4. **Maintain quality** - Never merge broken code
5. **Incremental progress** - Small, tested steps

## Pre-Integration Checklist

Before starting integration, verify:

- [ ] All 7 worker branches have commits beyond initialization
- [ ] Testing worker has completed (confirms all dependencies done)
- [ ] Integration branch is clean (no uncommitted changes)
- [ ] Logging system is available (czarina-core/logging.sh)

## Detailed Integration Steps

### Step 1: Merge project-setup

**Why First:** Foundation for everything else - models, structure, dependencies

**Commands:**
```bash
# Log start
source $(git rev-parse --show-toplevel)/czarina-core/logging.sh
czarina_log_task_start "Merge: project-setup"

# Review deliverables
git log cz1/feat/project-setup --oneline
git diff cz1/feat/integration...cz1/feat/project-setup --name-only

# Merge
git merge --no-ff cz1/feat/project-setup -m "Merge project-setup: Python structure, models, Docker setup"

# Test
pytest tests/ -v || echo "Tests may not exist yet"

# Verify deliverables
ls -la src/hopper/
cat pyproject.toml
cat docker-compose.yml

# Log completion
czarina_log_checkpoint "project-setup_merged"
```

**Expected Conflicts:** None (first merge)

**Expected Deliverables:**
- `src/hopper/` directory structure
- `pyproject.toml` with dependencies
- SQLAlchemy models
- `docker-compose.yml`
- Alembic setup

**Verification:**
```bash
# Check project structure
test -d src/hopper/models
test -f pyproject.toml
test -f docker-compose.yml

# Try installing dependencies
pip install -e .
```

---

### Step 2: Merge database

**Why Second:** Builds on models from project-setup

**Commands:**
```bash
czarina_log_task_start "Merge: database"

# Review changes
git log cz1/feat/database --oneline
git diff cz1/feat/integration...cz1/feat/database --name-only

# Merge
git merge --no-ff cz1/feat/database -m "Merge database: Repositories, migrations, CRUD operations"

# Test database setup
pytest tests/test_database*.py -v
pytest tests/test_repositories*.py -v

# Verify migrations
alembic history
alembic upgrade head

# Log completion
czarina_log_checkpoint "database_merged"
```

**Potential Conflicts:**
- Model definitions (if database modified models from project-setup)
- Alembic migration file ordering

**Resolution Strategy:**
- For model conflicts: Use database version (more complete implementation)
- For migrations: Ensure proper ordering, may need to create merge migration

**Expected Deliverables:**
- Repository classes (TaskRepository, ProjectRepository, etc.)
- Alembic migration files
- Database session management
- CRUD operation implementations

**Verification:**
```bash
# Test database connectivity
python -c "from src.hopper.database import get_db; print('DB OK')"

# Verify repositories exist
python -c "from src.hopper.repositories import TaskRepository; print('Repos OK')"
```

---

### Step 3: Merge api-core

**Why Third:** Needs database repositories to implement endpoints

**Commands:**
```bash
czarina_log_task_start "Merge: api-core"

# Review changes
git log cz1/feat/api-core --oneline
git diff cz1/feat/integration...cz1/feat/api-core --name-only

# Merge
git merge --no-ff cz1/feat/api-core -m "Merge api-core: FastAPI application, endpoints, authentication"

# Test API
pytest tests/test_api*.py -v
pytest tests/test_endpoints*.py -v

# Start API and verify
uvicorn src.hopper.main:app --reload &
sleep 5
curl http://localhost:8000/docs
kill %1

# Log completion
czarina_log_checkpoint "api-core_merged"
```

**Potential Conflicts:**
- Configuration management (if both database and api-core added config)
- Import statements
- Dependency injection patterns

**Resolution Strategy:**
- Prefer api-core's configuration approach (it's the main application)
- Ensure imports are consistent with final structure
- Use FastAPI's dependency injection system

**Expected Deliverables:**
- FastAPI application (`main.py` or `app.py`)
- Task CRUD endpoints
- Authentication system (JWT tokens)
- OpenAPI documentation
- Request/response models

**Verification:**
```bash
# Check API starts
timeout 10 uvicorn src.hopper.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -f http://localhost:8000/health || curl -f http://localhost:8000/
kill %1

# Verify OpenAPI docs exist
python -c "from src.hopper.main import app; print(len(app.routes))"
```

---

### Step 4: Merge routing-engine

**Why Fourth:** Integrates with API for intelligent task routing

**Commands:**
```bash
czarina_log_task_start "Merge: routing-engine"

# Review changes
git log cz1/feat/routing-engine --oneline
git diff cz1/feat/integration...cz1/feat/routing-engine --name-only

# Merge
git merge --no-ff cz1/feat/routing-engine -m "Merge routing-engine: Rules-based intelligence, decision recording"

# Test routing
pytest tests/test_routing*.py -v
pytest tests/test_intelligence*.py -v

# Verify routing works
python -c "from src.hopper.intelligence import RulesIntelligence; ri = RulesIntelligence(); print('Routing OK')"

# Log completion
czarina_log_checkpoint "routing-engine_merged"
```

**Potential Conflicts:**
- API endpoint modifications (if routing-engine added routing endpoints)
- Database schema (if routing decisions table added)
- Configuration (routing rules configuration)

**Resolution Strategy:**
- Merge endpoint definitions carefully
- Ensure RoutingDecision model is properly integrated
- Combine configuration files

**Expected Deliverables:**
- RulesIntelligence class
- BaseIntelligence interface
- Routing decision recording
- Rule configuration system
- Integration with task creation

**Verification:**
```bash
# Test routing decision
python <<EOF
from src.hopper.intelligence import RulesIntelligence
from src.hopper.models import Task

ri = RulesIntelligence()
task = Task(title="Test task", description="Test routing")
decision = ri.route(task)
print(f"Routing decision: {decision}")
EOF
```

---

### Step 5: Merge mcp-integration

**Why Fifth:** Depends on API being available

**Commands:**
```bash
czarina_log_task_start "Merge: mcp-integration"

# Review changes
git log cz1/feat/mcp-integration --oneline
git diff cz1/feat/integration...cz1/feat/mcp-integration --name-only

# Merge
git merge --no-ff cz1/feat/mcp-integration -m "Merge mcp-integration: MCP server, Claude integration"

# Test MCP
pytest tests/test_mcp*.py -v

# Verify MCP server can start
python src/hopper/mcp_server.py --help

# Log completion
czarina_log_checkpoint "mcp-integration_merged"
```

**Potential Conflicts:**
- API client configuration
- Authentication handling
- Server startup scripts

**Resolution Strategy:**
- Use consistent API client configuration
- Ensure MCP uses same auth as API
- Combine startup scripts if needed

**Expected Deliverables:**
- MCP server implementation
- MCP tools (create_task, list_tasks, etc.)
- MCP resources
- Claude Desktop configuration
- API client integration

**Verification:**
```bash
# Test MCP tools exist
python <<EOF
from src.hopper.mcp_server import server
tools = server.list_tools()
print(f"MCP tools: {[t.name for t in tools]}")
EOF
```

---

### Step 6: Merge cli-tool

**Why Sixth:** Depends on API being available

**Commands:**
```bash
czarina_log_task_start "Merge: cli-tool"

# Review changes
git log cz1/feat/cli-tool --oneline
git diff cz1/feat/integration...cz1/feat/cli-tool --name-only

# Merge
git merge --no-ff cz1/feat/cli-tool -m "Merge cli-tool: CLI commands, configuration management"

# Test CLI
pytest tests/test_cli*.py -v

# Verify CLI works
hopper --help
hopper list --help

# Log completion
czarina_log_checkpoint "cli-tool_merged"
```

**Potential Conflicts:**
- Configuration file format
- API client configuration
- Entry point definitions

**Resolution Strategy:**
- Standardize on one configuration format
- Use shared API client configuration
- Ensure entry points are properly defined

**Expected Deliverables:**
- CLI application using Click
- Commands: add, list, get, update, delete, config
- Rich terminal output
- Configuration file support
- API client integration

**Verification:**
```bash
# Test CLI commands exist
hopper --help | grep -E "add|list|get|update|delete"

# Test CLI can connect to API
# (May fail if API not running, that's ok)
hopper list 2>/dev/null || echo "API not running (expected)"
```

---

### Step 7: Merge testing

**Why Last:** Tests everything that came before

**Commands:**
```bash
czarina_log_task_start "Merge: testing"

# Review changes
git log cz1/feat/testing --oneline
git diff cz1/feat/integration...cz1/feat/testing --name-only

# Merge
git merge --no-ff cz1/feat/testing -m "Merge testing: Comprehensive test suite, fixtures, coverage"

# Run FULL test suite
pytest tests/ -v --cov=src/hopper --cov-report=html --cov-report=term-missing

# Verify coverage
coverage report --fail-under=80

# Log completion
czarina_log_checkpoint "testing_merged"
czarina_log_task_complete "Merge: testing - All merges complete"
```

**Potential Conflicts:**
- Test configuration
- Fixture definitions
- Mock strategies
- Coverage configuration

**Resolution Strategy:**
- Use testing branch's test configuration (most complete)
- Merge fixtures carefully to avoid duplicates
- Ensure coverage targets are met

**Expected Deliverables:**
- Comprehensive test suite
- Unit tests for all components
- Integration tests
- End-to-end tests
- Test fixtures and factories
- Coverage configuration (>90% target)

**Verification:**
```bash
# Run all tests
pytest tests/ -v

# Check coverage
pytest tests/ --cov=src/hopper --cov-report=term

# Verify test organization
ls -la tests/
```

---

## Post-Merge Integration Testing

After all merges complete, run comprehensive integration tests:

### 1. Docker Deployment Test

```bash
# Build and start all services
docker-compose build
docker-compose up -d

# Wait for services to be ready
sleep 10

# Run tests inside container
docker-compose exec hopper pytest tests/ -v

# Test API endpoints
curl http://localhost:8000/docs
curl http://localhost:8000/tasks

# Clean up
docker-compose down
```

### 2. End-to-End Workflow Test

```bash
# Start API
uvicorn src.hopper.main:app --reload &
API_PID=$!
sleep 5

# Test CLI workflow
hopper add "Test task from CLI" --priority high
TASK_ID=$(hopper list --format json | jq -r '.[0].id')
hopper get $TASK_ID
hopper update $TASK_ID --status in_progress
hopper delete $TASK_ID

# Stop API
kill $API_PID

# Start MCP server
python src/hopper/mcp_server.py &
MCP_PID=$!
sleep 5

# Test MCP (would need Claude Desktop running)
# Manual verification required

# Stop MCP
kill $MCP_PID
```

### 3. Database Integration Test

```bash
# Run migrations
alembic upgrade head

# Test database operations
python <<EOF
from src.hopper.database import get_db
from src.hopper.repositories import TaskRepository
from src.hopper.models import Task

# Create task
repo = TaskRepository(next(get_db()))
task = repo.create(Task(title="Integration test", description="Test"))
print(f"Created task: {task.id}")

# Query task
fetched = repo.get(task.id)
assert fetched.title == "Integration test"

# List tasks
tasks = repo.list()
assert len(tasks) > 0

print("✅ Database integration OK")
EOF
```

### 4. Phase 1 Success Criteria Validation

Test each success criterion:

```bash
# ✅ Can create tasks via HTTP API
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title": "API test", "description": "Test"}'

# ✅ Can create tasks via CLI
hopper add "CLI test task"

# ✅ Can create tasks via MCP
# (Manual test with Claude Desktop)

# ✅ Tasks stored in database
sqlite3 hopper.db "SELECT * FROM tasks;"

# ✅ Basic rules-based routing works
# (Test via API or CLI with routing rules)

# ✅ Can list and query tasks with filters
hopper list --status pending
hopper list --priority high

# ✅ Docker Compose setup works
docker-compose up -d
docker-compose ps
docker-compose down
```

## Conflict Resolution Guidelines

### General Strategy

1. **Understand before resolving** - Read both versions carefully
2. **Test after resolution** - Always verify the merge still works
3. **Document decisions** - Note why you chose a particular resolution
4. **Ask for clarification** - If truly unclear, document and flag

### Common Conflict Scenarios

#### Scenario 1: Model Definition Conflicts

**Situation:** Both project-setup and database modified the same model

**Resolution:**
- Use the database version (more complete)
- Verify no features lost from project-setup version
- Test model creation and queries

#### Scenario 2: Configuration File Conflicts

**Situation:** Multiple workers added different config sections

**Resolution:**
- Merge all sections
- Ensure no duplicate keys
- Validate configuration loads properly

#### Scenario 3: Dependency Conflicts

**Situation:** Different version requirements in pyproject.toml

**Resolution:**
- Use most recent compatible version
- Test that all features work
- Document any version constraints

#### Scenario 4: Import Path Conflicts

**Situation:** Different import patterns used

**Resolution:**
- Standardize on absolute imports from src.hopper
- Update all files to use consistent pattern
- Run tests to catch any import errors

#### Scenario 5: Test Conflicts

**Situation:** Similar tests in different worker branches

**Resolution:**
- Keep most comprehensive version
- Merge unique test cases
- Remove duplicates
- Ensure all coverage is maintained

## Risk Mitigation During Integration

### Risk 1: Breaking Changes During Merge

**Mitigation:**
- Test after EVERY merge
- Don't proceed if tests fail
- Fix integration issues before next merge

### Risk 2: Lost Functionality

**Mitigation:**
- Review each worker's deliverables before merging
- Create checklist of expected features
- Verify all features present after merge

### Risk 3: Configuration Inconsistencies

**Mitigation:**
- Establish configuration standards early
- Document all configuration options
- Validate configuration loads properly

### Risk 4: Authentication Incompatibilities

**Mitigation:**
- Review auth implementation from api-core first
- Ensure MCP and CLI use same auth
- Test authentication flow end-to-end

### Risk 5: Docker Issues

**Mitigation:**
- Test Docker build after project-setup merge
- Verify services start properly
- Test inter-service communication

## Success Indicators

After integration completes, verify:

- [ ] All 7 worker branches merged
- [ ] Zero merge conflicts remaining
- [ ] All tests passing (unit, integration, e2e)
- [ ] Test coverage >90% for core, >80% overall
- [ ] All Phase 1 success criteria met
- [ ] Docker deployment works end-to-end
- [ ] MCP works with Claude Desktop
- [ ] CLI works for all commands
- [ ] API fully functional
- [ ] Database migrations successful
- [ ] No critical bugs or errors

## Rollback Strategy

If integration fails catastrophically:

```bash
# Reset to pre-merge state
git reset --hard <commit-before-merge>

# Or reset to specific merge
git reset --hard <last-good-merge-commit>

# Review what went wrong
git log --oneline --graph

# Try merge again with fixes
```

## Next Steps After Integration

Once all merges complete successfully:

1. **Code Quality** (Task 5)
   - Run black, ruff, mypy
   - Fix any issues

2. **Documentation** (Task 6)
   - Create comprehensive docs
   - Update all READMEs

3. **Release Preparation** (Task 7)
   - Update version numbers
   - Create release notes
   - Tag release

4. **Final Validation** (Task 8)
   - Fresh installation test
   - Create integration summary
   - Handoff to stakeholders

---

This strategy ensures systematic, tested, and documented integration of all Phase 1 components.
