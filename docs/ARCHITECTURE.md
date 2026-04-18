# Hopper Architecture

This document provides an overview of Hopper's architecture and design decisions.

## System Overview

Hopper is a multi-instance, hierarchical task routing and orchestration system. It intelligently routes tasks to appropriate executors based on capabilities, workload, and learned patterns.

## Core Components

### 1. Data Models

Located in `src/hopper/models/`

- **Task**: Core entity representing a unit of work
- **Project**: Registered executor that can receive tasks
- **HopperInstance**: Node in the instance hierarchy
- **RoutingDecision**: Records routing decisions for learning
- **TaskFeedback**: Captures execution feedback for improvement

### 2. Configuration Management

Located in `src/hopper/config/`

- Uses pydantic-settings for type-safe configuration
- Loads from environment variables and .env file
- Provides validation and sensible defaults

### 3. Multi-Instance Hierarchy

Hopper supports multiple instance scopes:

```
Global Hopper
├─ Project Hopper (czarina)
│  └─ Orchestration Hopper (run-123)
└─ Project Hopper (sark)
   └─ Orchestration Hopper (run-456)
```

Each scope has different responsibilities:

- **GLOBAL**: Strategic routing across all projects
- **PROJECT**: Project-specific task management
- **ORCHESTRATION**: Single orchestration run management
- **PERSONAL**: Personal task queue
- **FAMILY**: Family coordination
- **EVENT**: Event-specific planning
- **FEDERATED**: Federation coordination

## Database Schema

### Core Tables

1. **tasks**: All task data and metadata
2. **projects**: Project registry with capabilities
3. **hopper_instances**: Instance hierarchy
4. **routing_decisions**: Decision history with confidence
5. **task_feedback**: Execution feedback for learning
6. **task_delegations**: Parent-child task delegation

### Design Principles

- PostgreSQL for production (JSONB support)
- SQLite for development and testing
- Comprehensive indexes for performance
- Foreign keys for referential integrity
- Timestamps on all tables

## Future Architecture

### Phase 2: Multi-Instance Support
- Instance lifecycle management
- Task delegation protocols
- Completion notification chains

### Phase 3: Memory System
- Working Memory (Redis)
- Episodic Memory (OpenSearch)
- Consolidated Memory (GitLab)

### Phase 4: Intelligence Layer
- Rules-based routing
- LLM-based routing
- Sage-managed routing
- Hybrid strategies

### Phase 5: Platform Integration
- GitHub/GitLab sync
- Webhook handlers
- Bidirectional updates

### Phase 6: Federation
- Multi-Hopper coordination
- Peer discovery
- Trust establishment
- Cross-Hopper delegation

## Design Decisions

### Why SQLAlchemy 2.0?

- Modern async support
- Type safety with mapped_column
- Excellent PostgreSQL and SQLite support
- Mature ecosystem

### Why Pydantic Settings?

- Type validation
- Environment variable integration
- Clear error messages
- Developer-friendly API

### Why Multi-Instance?

- Separation of concerns (strategy vs execution)
- Scalability (multiple orchestrations in parallel)
- Flexibility (different scopes for different needs)

### Why Three-Tier Memory?

- Working: Fast context for current decisions
- Episodic: Search similar past decisions
- Consolidated: Learn patterns over time

## Performance Considerations

### Database Indexes

All frequently-queried fields have indexes:
- `tasks.instance_id`
- `tasks.project`
- `tasks.status`
- `tasks.created_at`

### Caching Strategy

- Settings cached with @lru_cache
- Redis for working memory (Phase 3)
- Database connection pooling

### Scalability

- Stateless API design
- Horizontal scaling of API servers
- Database read replicas (future)
- Background job processing (Celery, future)

## Server Deployment

The unified server runs all services on a single port:

| Path prefix | Service |
|-------------|---------|
| `/api/v1/` | REST task/instance/learning API |
| `/mcp/` | MCP SSE endpoint + token registration |
| `/upstream/` | DID-authenticated peer sync |
| `/docs` | OpenAPI docs |

**Systemd**: `~/.config/systemd/user/hopper-upstream.service` starts the unified server on boot.

**Upstream storage**: configured via `HOPPER_UPSTREAM_STORAGE` env var (default `~/.hopper/upstream-data`).

## Security Considerations

### Authentication

Three layers are in use:

- **DID (Decentralized Identifier)**: Cryptographic identity for upstream sync and MCP token registration. Keys stored in `~/.hopper/did.key`.
- **Bearer tokens (`hpr_`)**: Session tokens registered via `hopper mcp init-token`, stored in `~/.hopper/mcp_tokens.json`. Used by Claude Web.
- **Simple token**: `HOPPER_MCP_TOKEN` env var for dev/legacy clients.

### Data Protection

- No sensitive data in logs
- Token files have 0o600 permissions
- Secrets in environment variables

## Testing Strategy

### Unit Tests

- All models have comprehensive tests
- Configuration validation tests
- Mock external dependencies

### Integration Tests

- API endpoint tests (future)
- Database migration tests
- End-to-end workflows

### Test Database

- In-memory SQLite for speed
- Fixtures for clean state
- Test data factories

## Development Practices

### Code Organization

```
src/hopper/
├── models/          # Data models
├── api/             # FastAPI app (unified server)
│   ├── app.py       # App factory — mounts MCP SSE + upstream
│   ├── mcp_sse.py   # MCP SSE server (Claude Web)
│   ├── mcp_tokens.py# hpr_ Bearer token store
│   └── routes/      # REST API routes
├── mcp/             # MCP stdio server (Claude Desktop)
├── upstream/        # DID-authenticated sync server + client
├── cli/             # CLI commands
├── intelligence/    # Routing strategies
├── memory/          # Memory systems
└── config/          # Configuration
```

### Type Safety

- Type hints mandatory
- mypy for static type checking
- Pydantic for runtime validation

### Code Quality

- Black for formatting
- Ruff for linting
- pytest for testing
- >80% test coverage goal

---

For more details, see:
- [Specification](Hopper.Specification.md)
- [Implementation Plan](../plans/Hopper-Implementation-Plan.md)
- [Contributing Guide](../CONTRIBUTING.md)
