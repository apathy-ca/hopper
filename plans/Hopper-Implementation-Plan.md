# 🏗️ Hopper Implementation Plan

**Version:** 1.0.0  
**Created:** 2025-12-26  
**Based on:** Hopper Specification v1.0.0 + Addendums  
**Status:** Ready for Implementation

---

## 📋 Table of Contents

1. [Executive Summary](#executive-summary)
2. [Architecture Overview](#architecture-overview)
3. [Technology Stack](#technology-stack)
4. [Implementation Phases](#implementation-phases)
5. [Core Components Breakdown](#core-components-breakdown)
6. [Database Design](#database-design)
7. [API Specifications](#api-specifications)
8. [Testing Strategy](#testing-strategy)
9. [Deployment Strategy](#deployment-strategy)
10. [Integration Points](#integration-points)
11. [Success Criteria](#success-criteria)

---

## Executive Summary

### What We're Building

**Hopper** is a universal, multi-instance, hierarchical task queue designed for human-AI collaborative workflows. It provides:

- **Universal intake** from any source (MCP, CLI, HTTP, webhooks)
- **Intelligent routing** using rules, LLM, or Sage-managed strategies
- **Multi-instance architecture** (Global → Project → Orchestration)
- **3-tier memory system** (Working → Episodic → Consolidated)
- **Bidirectional sync** with GitHub/GitLab
- **Federation support** for multi-Hopper coordination

### Implementation Approach

We'll build Hopper in **6 phases** over approximately **12-16 weeks**:

1. **Phase 1: Core Foundation** (Weeks 1-2) - Basic task queue with MCP
2. **Phase 2: Multi-Instance Support** (Weeks 3-4) - Hierarchical architecture
3. **Phase 3: Memory & Learning** (Weeks 5-6) - 3-tier memory system
4. **Phase 4: Intelligence Layer** (Weeks 7-8) - LLM routing
5. **Phase 5: Platform Integration** (Weeks 9-10) - GitHub/GitLab sync
6. **Phase 6: Federation** (Weeks 11-12) - Multi-Hopper coordination

### Key Design Decisions

1. **Python-first** - FastAPI for API, SQLAlchemy for ORM
2. **PostgreSQL** for production, SQLite for development
3. **OpenSearch** for episodic memory (semantic search)
4. **GitLab** for consolidated memory (versioned, inspectable)
5. **Pluggable intelligence** - Start with rules, add LLM, enable Sage
6. **Docker-first deployment** - Easy local dev, production-ready

---

## Architecture Overview

### System Architecture

```
┌─────────────────── INPUT LAYER ─────────────────────┐
│  MCP Server    HTTP API    CLI    Webhooks          │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌─────────────────── HOPPER CORE ─────────────────────┐
│                                                      │
│  ┌─ Instance Manager ────────────────────────────┐  │
│  │  • Global Hopper (strategic routing)          │  │
│  │  • Project Hoppers (project management)       │  │
│  │  │  └─ Orchestration Hoppers (execution)      │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Intelligence Layer ──────────────────────────┐  │
│  │  • Rules Engine (fast, deterministic)         │  │
│  │  • LLM Router (nuanced, contextual)           │  │
│  │  • Sage Manager (strategic, learning)         │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Memory System ───────────────────────────────┐  │
│  │  • Working Memory (Redis/in-memory)           │  │
│  │  • Episodic Memory (OpenSearch)               │  │
│  │  • Consolidated Memory (GitLab)               │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
│  ┌─ Storage Layer ───────────────────────────────┐  │
│  │  • Task Store (PostgreSQL/SQLite)             │  │
│  │  • Project Registry                           │  │
│  │  • Routing Decisions                          │  │
│  └───────────────────────────────────────────────┘  │
│                                                      │
└──────────────────────┬───────────────────────────────┘
                       │
                       ▼
┌─────────────────── OUTPUT LAYER ────────────────────┐
│  GitHub/GitLab    Webhooks    Notifications         │
└──────────────────────────────────────────────────────┘
```

### Multi-Instance Hierarchy

```
Global Hopper (hopper-global)
├─ Project Hopper: czarina
│  └─ Orchestration Hopper: czarina-run-abc123
│     ├─ Phase Hopper: phase-1-design
│     └─ Phase Hopper: phase-2-implementation
├─ Project Hopper: sark
│  └─ Orchestration Hopper: sark-run-xyz789
└─ Project Hopper: symposium
```

---

## Technology Stack

### Core Technologies

```yaml
Language: Python 3.11+
  Rationale: Rich ecosystem, async support, type hints

Web Framework: FastAPI
  Rationale: Modern, async, auto-docs, type validation

Database (Production): PostgreSQL 15+
  Rationale: JSONB support, full-text search, reliability

Database (Development): SQLite
  Rationale: Zero-config, file-based, good for local dev

ORM: SQLAlchemy 2.0
  Rationale: Mature, supports both PostgreSQL and SQLite

Search Engine: OpenSearch
  Rationale: Semantic search, vector embeddings, open source

Memory Store: Redis (optional)
  Rationale: Fast working memory, pub/sub for events

Version Control: GitLab API
  Rationale: Consolidated memory storage, versioned patterns
```

### Supporting Technologies

```yaml
MCP: Model Context Protocol SDK
  Purpose: Claude/Cursor integration

HTTP Client: httpx
  Purpose: Async HTTP for webhooks, API calls

Task Queue: Celery (optional)
  Purpose: Background jobs, consolidation

Containerization: Docker + Docker Compose
  Purpose: Development and deployment

Testing: pytest + pytest-asyncio
  Purpose: Unit, integration, e2e tests

Monitoring: Prometheus + Grafana (optional)
  Purpose: Metrics and observability
```

### Python Dependencies

```toml
# pyproject.toml
[project]
name = "hopper"
version = "1.0.0"
requires-python = ">=3.11"

dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.12.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "httpx>=0.25.0",
    "redis>=5.0.0",
    "opensearch-py>=2.4.0",
    "python-gitlab>=4.2.0",
    "PyGithub>=2.1.0",
    "anthropic>=0.7.0",
    "mcp>=0.1.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-multipart>=0.0.6",
    "pyyaml>=6.0.1",
    "click>=8.1.7",
    "rich>=13.7.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.1.0",
    "black>=23.11.0",
    "ruff>=0.1.6",
    "mypy>=1.7.0",
]
```

---

## Implementation Phases

### Phase 1: Core Foundation (Weeks 1-2)

**Goal:** Working task queue with MCP integration

#### Week 1: Project Setup & Core Models

**Tasks:**
1. Initialize Python project structure
2. Set up development environment (Docker Compose)
3. Implement core data models (Task, Project, RoutingDecision)
4. Create database schema and migrations
5. Implement basic CRUD operations

**Deliverables:**
- Project structure with proper packaging
- SQLAlchemy models for all core entities
- Alembic migrations for database schema
- Docker Compose with PostgreSQL and Redis
- Basic unit tests for models

#### Week 2: API & MCP Integration

**Tasks:**
1. Implement FastAPI application with task endpoints
2. Create MCP server for Claude integration
3. Build CLI tool for task management
4. Implement rules-based routing intelligence
5. Add basic authentication and authorization

**Deliverables:**
- REST API with OpenAPI documentation
- MCP server that works with Claude Desktop
- CLI tool (`hopper add`, `hopper list`, etc.)
- Rules-based routing that matches keywords/tags
- Working end-to-end flow: MCP → API → Database

**Success Criteria:**
- ✅ Can create tasks via HTTP API
- ✅ Can create tasks via MCP (from Claude)
- ✅ Can create tasks via CLI
- ✅ Tasks stored in database with proper schema
- ✅ Basic rules-based routing works
- ✅ Can list and query tasks with filters
- ✅ Docker Compose setup for local development

---

### Phase 2: Multi-Instance Support (Weeks 3-4)

**Goal:** Hierarchical Hopper instances (Global → Project → Orchestration)

#### Week 3: Instance Architecture

**Tasks:**
1. Implement `HopperInstance` class with scope support
2. Create instance registry and discovery
3. Build parent-child coordination mechanisms
4. Implement task delegation between instances
5. Add instance lifecycle management

**Deliverables:**
- `HopperScope` enum (GLOBAL, PROJECT, ORCHESTRATION)
- Instance manager that creates/tracks child instances
- Delegation protocol for parent→child task routing
- Completion notification from child→parent
- Database schema for instance registry

#### Week 4: Scope-Specific Behavior

**Tasks:**
1. Implement Global Hopper routing logic
2. Implement Project Hopper task handling
3. Implement Orchestration Hopper queue management
4. Create configuration templates per scope
5. Build instance tree visualization

**Deliverables:**
- Global Hopper routes to best project
- Project Hopper decides orchestration vs manual
- Orchestration Hopper manages worker queues
- Scope-specific configuration files
- CLI command to view instance hierarchy

**Success Criteria:**
- ✅ Can create Global, Project, and Orchestration instances
- ✅ Tasks flow down hierarchy (Global → Project → Orchestration)
- ✅ Completion bubbles up hierarchy
- ✅ Each scope has appropriate configuration
- ✅ Can visualize instance tree
- ✅ Czarina can use Orchestration Hopper for runs

---

### Phase 3: Memory & Learning (Weeks 5-6)

**Goal:** 3-tier memory system that learns from outcomes

#### Week 5: Working & Episodic Memory

**Tasks:**
1. Implement Working Memory (Redis-backed)
2. Implement Episodic Memory (OpenSearch)
3. Create feedback collection system
4. Build routing decision recording
5. Add semantic search for similar tasks

**Deliverables:**
- Working Memory stores current routing context
- Episodic Memory records all routing decisions
- Feedback model and collection API
- OpenSearch integration with proper indexing
- Semantic search to find similar past routings

#### Week 6: Consolidated Memory & Learning

**Tasks:**
1. Implement Consolidated Memory (GitLab-backed)
2. Create nightly consolidation job
3. Build attention shaping mechanism
4. Implement pattern extraction from episodes
5. Add anti-pattern detection

**Deliverables:**
- GitLab repository for consolidated memory
- Consolidation job that extracts patterns
- Attention weights that improve over time
- YAML files for patterns, strengths, anti-patterns
- Learning feedback loop that adjusts routing

**Success Criteria:**
- ✅ Working Memory provides immediate context
- ✅ Episodic Memory records all routing decisions
- ✅ Can query "How did we route similar tasks?"
- ✅ Consolidated Memory learns patterns
- ✅ Routing accuracy improves over time
- ✅ Can detect and avoid anti-patterns
- ✅ Attention weights adjust based on feedback

---

### Phase 4: Intelligence Layer (Weeks 7-8)

**Goal:** LLM-based routing for complex decisions

#### Week 7: LLM Integration

**Tasks:**
1. Implement LLM Intelligence class
2. Create context-rich prompts for routing
3. Build task decomposition logic
4. Add effort estimation
5. Implement hybrid routing strategy

**Deliverables:**
- LLM Intelligence using Claude Sonnet
- Prompts that include task, projects, history
- Task decomposition for complex work
- Effort estimation based on task analysis
- Hybrid strategy (rules for simple, LLM for complex)

#### Week 8: Sage Integration (Optional)

**Tasks:**
1. Implement Sage Intelligence class
2. Create Symposium integration
3. Build Sage reflection mechanisms
4. Add strategic prioritization
5. Implement Sage performance reporting

**Deliverables:**
- Sage Intelligence that delegates to Symposium Sage
- Sage can route tasks with full context
- Sage reflects on routing outcomes
- Sage provides strategic prioritization
- Sage self-evaluates routing quality

**Success Criteria:**
- ✅ LLM routing handles nuanced decisions
- ✅ Complex tasks decomposed appropriately
- ✅ Effort estimates reasonably accurate
- ✅ Hybrid strategy uses right tool for job
- ✅ (Optional) Sage can manage routing
- ✅ (Optional) Sage learns from experience

---

### Phase 5: Platform Integration (Weeks 9-10)

**Goal:** Bidirectional sync with GitHub/GitLab

#### Week 9: GitHub Integration

**Tasks:**
1. Implement GitHub API client
2. Create issue creation from tasks
3. Build issue import to tasks
4. Add webhook handler for real-time sync
5. Implement bidirectional sync engine

**Deliverables:**
- GitHub integration class
- Tasks create GitHub issues automatically
- GitHub issues import as tasks
- Webhook endpoint for issue events
- Sync engine keeps both sides updated

#### Week 10: GitLab Integration & Sync

**Tasks:**
1. Implement GitLab API client
2. Create similar sync mechanisms
3. Build sync configuration per project
4. Add label/tag mapping
5. Implement sync conflict resolution

**Deliverables:**
- GitLab integration (similar to GitHub)
- Sync configuration in project registry
- Label↔tag and milestone↔priority mapping
- Conflict resolution strategies
- Sync status monitoring

**Success Criteria:**
- ✅ Tasks automatically create GitHub/GitLab issues
- ✅ GitHub/GitLab issues import as tasks
- ✅ Changes sync bidirectionally
- ✅ Webhooks provide real-time updates
- ✅ Conflicts handled gracefully
- ✅ Can configure sync per project

---

### Phase 6: Federation (Weeks 11-12)

**Goal:** Multi-Hopper coordination and federation

#### Week 11: Federation Protocol

**Tasks:**
1. Implement Hopper Federation Protocol (HFP)
2. Create peer discovery mechanisms
3. Build trust establishment
4. Add task delegation between peers
5. Implement completion notification

**Deliverables:**
- HFP specification and implementation
- mDNS/DNS-SD discovery
- Public key authentication
- Peer-to-peer task delegation
- Federation API endpoints

#### Week 12: Federation Features

**Tasks