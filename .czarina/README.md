# Hopper Phase 1 Czarina Orchestration

This directory contains the Czarina orchestration configuration for Hopper Phase 1 (Core Foundation).

## Overview

**Project:** Hopper - Universal Task Queue
**Version:** 1.0.0
**Phase:** 1 (Core Foundation)
**Omnibus Branch:** `cz1/release/v1.0.0-phase1`

## Workers

Phase 1 consists of 8 workers organized in dependency order:

### 1. project-setup
**Branch:** `cz1/feat/project-setup`
**Dependencies:** None
**Mission:** Initialize Python project structure, development environment, and core data models

**Key Deliverables:**
- Python project structure with proper packaging
- Docker Compose setup (PostgreSQL, Redis)
- Core data models (Task, Project, HopperInstance, RoutingDecision)
- Configuration management
- Initial test suite

### 2. database
**Branch:** `cz1/feat/database`
**Dependencies:** project-setup
**Mission:** Implement database schema, migrations, and CRUD operations

**Key Deliverables:**
- Alembic migrations
- Database connection management
- Repository pattern with CRUD operations
- Database utilities and seed data
- Comprehensive repository tests

### 3. api-core
**Branch:** `cz1/feat/api-core`
**Dependencies:** database
**Mission:** Build FastAPI application with task endpoints and authentication

**Key Deliverables:**
- FastAPI application with proper structure
- Task, Project, and Instance management endpoints
- Authentication and authorization (JWT + API keys)
- Pydantic schemas for all entities
- OpenAPI documentation

### 4. mcp-integration
**Branch:** `cz1/feat/mcp-integration`
**Dependencies:** api-core
**Mission:** Create MCP server for Claude integration

**Key Deliverables:**
- MCP server implementation
- Task management tools for Claude
- Project and routing tools
- MCP resources
- Context management
- Claude Desktop configuration

### 5. cli-tool
**Branch:** `cz1/feat/cli-tool`
**Dependencies:** api-core
**Mission:** Build CLI tool for task management

**Key Deliverables:**
- Click-based CLI framework
- Task management commands (add, list, get, update, status, delete, search)
- Project and instance management commands
- Configuration and authentication commands
- Rich terminal output
- Shell completion scripts

### 6. routing-engine
**Branch:** `cz1/feat/routing-engine`
**Dependencies:** api-core
**Mission:** Implement rules-based routing intelligence

**Key Deliverables:**
- Base intelligence interface
- Rules-based intelligence implementation
- Rule configuration system (YAML)
- Decision recording and feedback
- Routing API endpoints
- Rule management interface

### 7. testing
**Branch:** `cz1/feat/testing`
**Dependencies:** mcp-integration, cli-tool, routing-engine
**Mission:** Create comprehensive test suite for Phase 1 features

**Key Deliverables:**
- Enhanced test infrastructure
- API integration tests
- MCP integration tests
- CLI integration tests
- End-to-end workflow tests
- >90% code coverage for core modules
- Phase 1 success criteria validation

### 8. integration
**Branch:** `cz1/feat/integration`
**Dependencies:** testing
**Role:** integration
**Mission:** Merge all workers, resolve conflicts, and prepare for release

**Key Deliverables:**
- All worker branches merged
- Conflicts resolved
- Full test suite passing
- Code quality validation
- Comprehensive documentation
- Release preparation
- Integration summary

## Worker Dependency Graph

```
project-setup (foundation)
    └── database
        └── api-core
            ├── mcp-integration ──┐
            ├── cli-tool ─────────┤
            └── routing-engine ───┤
                                  │
                            testing
                                  │
                            integration (merges all)
```

## Phase 1 Success Criteria

- ✅ Can create tasks via HTTP API
- ✅ Can create tasks via MCP (from Claude)
- ✅ Can create tasks via CLI
- ✅ Tasks stored in database with proper schema
- ✅ Basic rules-based routing works
- ✅ Can list and query tasks with filters
- ✅ Docker Compose setup for local development

## Getting Started

1. **Initialize orchestration:**
   ```bash
   czarina init
   ```

2. **Start workers:**
   ```bash
   czarina start
   ```

3. **Monitor progress:**
   ```bash
   czarina status
   ```

4. **View worker details:**
   ```bash
   cat .czarina/workers/<worker-id>.md
   ```

## Architecture

Hopper Phase 1 implements the core foundation:

- **Input Layer:** MCP Server, HTTP API, CLI
- **Hopper Core:** Task queue, routing engine, instance management
- **Intelligence Layer:** Rules-based routing (Phase 1)
- **Storage Layer:** PostgreSQL/SQLite with SQLAlchemy
- **Memory System:** Basic working memory (full 3-tier in Phase 3)

## Technology Stack

- **Language:** Python 3.11+
- **Web Framework:** FastAPI
- **Database:** PostgreSQL (production), SQLite (development)
- **ORM:** SQLAlchemy 2.0
- **MCP:** Model Context Protocol SDK
- **CLI:** Click + Rich
- **Testing:** pytest + pytest-asyncio
- **Containerization:** Docker + Docker Compose

## References

- **Implementation Plan:** `/home/jhenry/Source/hopper/plans/Hopper-Implementation-Plan.md`
- **Specification:** `/home/jhenry/Source/hopper/docs/Hopper.Specification.md`
- **Worker Definitions:** `.czarina/workers/*.md`

## Notes

- Workers follow dependency order
- Each worker has comprehensive test requirements
- Integration worker merges all branches
- Phase 1 focuses on core functionality
- Future phases will add multi-instance (Phase 2), memory (Phase 3), LLM routing (Phase 4), GitHub/GitLab sync (Phase 5), and federation (Phase 6)

## Next Steps After Phase 1

Phase 2 will implement:
- Multi-instance support (Global → Project → Orchestration)
- Instance hierarchy and delegation
- Scope-specific behavior
- Czarina integration with Orchestration Hopper

---

**Czarina Orchestration:** v0.6.1+
**Created:** 2025-12-28
**Status:** Ready for implementation
