# Hopper Database Schema

This document describes the database schema for the Hopper task routing and orchestration system.

## Overview

Hopper uses a relational database (PostgreSQL for production, SQLite for development) to store tasks, projects, routing decisions, and system state. The schema is managed using Alembic migrations and accessed through SQLAlchemy 2.0 ORM.

## Database Support

- **Production**: PostgreSQL 15+ (recommended)
- **Development**: SQLite 3.x
- **ORM**: SQLAlchemy 2.0
- **Migrations**: Alembic

## Tables

### tasks

Stores all tasks in the Hopper system.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | VARCHAR(50) | No | Primary key, unique task identifier |
| `title` | VARCHAR(500) | No | Task title/summary |
| `description` | TEXT | Yes | Detailed task description |
| `project` | VARCHAR(100) | Yes | Assigned project name |
| `status` | VARCHAR(50) | No | Task status (pending, in_progress, completed, etc.) |
| `priority` | VARCHAR(20) | No | Priority level (low, medium, high, urgent) |
| `requester` | VARCHAR(100) | Yes | User/system that created the task |
| `owner` | VARCHAR(100) | Yes | Current task owner/assignee |
| `external_id` | VARCHAR(100) | Yes | ID in external system (GitHub, GitLab, etc.) |
| `external_url` | VARCHAR(500) | Yes | URL to external task |
| `external_platform` | VARCHAR(50) | Yes | External platform name |
| `source` | VARCHAR(50) | Yes | How task was created (mcp, cli, http, webhook) |
| `conversation_id` | VARCHAR(100) | Yes | Associated conversation ID |
| `context` | TEXT | Yes | Additional context or notes |
| `tags` | JSONB/JSON | Yes | Array of tags |
| `required_capabilities` | JSONB/JSON | Yes | Capabilities needed to complete task |
| `depends_on` | JSONB/JSON | Yes | Task dependencies |
| `blocks` | JSONB/JSON | Yes | Tasks blocked by this task |
| `routing_confidence` | FLOAT | Yes | Routing confidence score (0-1) |
| `routing_reasoning` | TEXT | Yes | Explanation of routing decision |
| `feedback` | JSONB/JSON | Yes | Task completion feedback |
| `created_at` | TIMESTAMP | No | Creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Indexes:**
- `idx_tasks_project` on `project`
- `idx_tasks_status` on `status`
- `idx_tasks_created_at` on `created_at`

**Relationships:**
- One routing_decision (task_id → routing_decisions.task_id)
- One task_feedback (task_id → task_feedback.task_id)
- Many external_mappings (task_id → external_mappings.task_id)

### projects

Stores registered work destinations (projects that can receive tasks).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `name` | VARCHAR(100) | No | Primary key, unique project name |
| `slug` | VARCHAR(100) | No | URL-friendly identifier (unique) |
| `repository` | VARCHAR(500) | Yes | Source code repository URL |
| `capabilities` | JSONB/JSON | Yes | Project capabilities (languages, skills, etc.) |
| `tags` | JSONB/JSON | Yes | Project tags for filtering |
| `executor_type` | VARCHAR(50) | Yes | Executor type (human, agent, czarina, etc.) |
| `executor_config` | JSONB/JSON | Yes | Executor configuration |
| `auto_claim` | BOOLEAN | No | Whether project auto-claims matching tasks |
| `priority_boost` | JSONB/JSON | Yes | Priority boost rules |
| `velocity` | VARCHAR(20) | Yes | Project velocity (slow, medium, fast) |
| `sla` | JSONB/JSON | Yes | Service level agreement config |
| `webhook_url` | VARCHAR(500) | Yes | Webhook URL for notifications |
| `api_endpoint` | VARCHAR(500) | Yes | API endpoint for task updates |
| `sync_config` | JSONB/JSON | Yes | External sync configuration |
| `created_at` | TIMESTAMP | No | Creation timestamp |
| `created_by` | VARCHAR(100) | Yes | Creator identifier |
| `last_sync` | TIMESTAMP | Yes | Last external sync timestamp |

**Unique Constraints:**
- `slug` must be unique

**Relationships:**
- Many tasks (name → tasks.project)
- Many routing_decisions (name → routing_decisions.project)

### hopper_instances

Stores Hopper instances for multi-instance hierarchical architecture.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | VARCHAR(100) | No | Primary key, unique instance identifier |
| `name` | VARCHAR(100) | No | Instance name |
| `scope` | VARCHAR(50) | No | Scope level (GLOBAL, PROJECT, ORCHESTRATION) |
| `parent_id` | VARCHAR(100) | Yes | Parent instance ID (FK to hopper_instances.id) |
| `config` | JSONB/JSON | Yes | Instance configuration |
| `status` | VARCHAR(50) | No | Instance status (active, paused, terminated) |
| `description` | TEXT | Yes | Instance description |
| `created_by` | VARCHAR(100) | Yes | Creator identifier |
| `terminated_at` | TIMESTAMP | Yes | Termination timestamp |
| `created_at` | TIMESTAMP | No | Creation timestamp |
| `updated_at` | TIMESTAMP | No | Last update timestamp |

**Foreign Keys:**
- `parent_id` → `hopper_instances.id` (self-referencing hierarchy)

**Relationships:**
- One parent instance (parent_id → hopper_instances.id)
- Many child instances (id → hopper_instances.parent_id)

### routing_decisions

Stores routing decision history for learning and analytics.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `task_id` | VARCHAR(50) | No | Primary key, task identifier (FK to tasks.id) |
| `project` | VARCHAR(100) | Yes | Routed project (FK to projects.name) |
| `confidence` | FLOAT | Yes | Decision confidence score (0-1) |
| `reasoning` | TEXT | Yes | Explanation of routing decision |
| `alternatives` | JSONB/JSON | Yes | Alternative routing options with scores |
| `decided_by` | VARCHAR(50) | Yes | Decision strategy (rules, llm, sage) |
| `decided_at` | TIMESTAMP | No | Decision timestamp |
| `decision_time_ms` | FLOAT | Yes | Time taken to make decision (ms) |
| `workload_snapshot` | JSONB/JSON | Yes | Workload state at decision time |
| `context` | JSONB/JSON | Yes | Additional decision context |

**Foreign Keys:**
- `task_id` → `tasks.id`
- `project` → `projects.name`

**Relationships:**
- One task (task_id → tasks.id)

### task_feedback

Stores feedback on task completion for learning and improvement.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `task_id` | VARCHAR(50) | No | Primary key, task identifier (FK to tasks.id) |
| `estimated_duration` | VARCHAR(50) | Yes | Estimated time to complete |
| `actual_duration` | VARCHAR(50) | Yes | Actual time taken |
| `complexity_rating` | INTEGER | Yes | Complexity rating (1-10) |
| `quality_score` | FLOAT | Yes | Quality score (0-1) |
| `required_rework` | BOOLEAN | Yes | Whether rework was required |
| `rework_reason` | TEXT | Yes | Reason for rework |
| `was_good_match` | BOOLEAN | Yes | Whether routing was correct |
| `should_have_routed_to` | VARCHAR(100) | Yes | Better project choice (if any) |
| `routing_feedback` | TEXT | Yes | Feedback on routing decision |
| `unexpected_blockers` | JSONB/JSON | Yes | Unexpected blocking issues |
| `required_skills_not_tagged` | JSONB/JSON | Yes | Missing capability tags |
| `notes` | TEXT | Yes | Additional notes |
| `created_at` | TIMESTAMP | No | Feedback creation timestamp |

**Foreign Keys:**
- `task_id` → `tasks.id`

**Relationships:**
- One task (task_id → tasks.id)

### external_mappings

Stores mappings between Hopper tasks and external platform issues.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `task_id` | VARCHAR(50) | No | Part of composite primary key (FK to tasks.id) |
| `platform` | VARCHAR(50) | No | Part of composite primary key (github, gitlab, etc.) |
| `external_id` | VARCHAR(100) | No | ID in external system |
| `external_url` | VARCHAR(500) | Yes | URL to external issue |

**Primary Key:**
- Composite: (`task_id`, `platform`)

**Foreign Keys:**
- `task_id` → `tasks.id`

**Relationships:**
- One task (task_id → tasks.id)

## Entity Relationship Diagram

```
┌──────────────┐
│   projects   │
│              │
│ PK: name     │
│    slug      │
└──────┬───────┘
       │
       │ 1:N
       ▼
┌──────────────┐       1:1      ┌─────────────────────┐
│    tasks     │◄───────────────│ routing_decisions   │
│              │                 │                     │
│ PK: id       │                 │ PK,FK: task_id      │
│ FK: project  │                 │ FK: project         │
└──────┬───────┘                 └─────────────────────┘
       │
       │ 1:1
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌──────────────┐  ┌────────────────────┐
│task_feedback │  │external_mappings   │
│              │  │                    │
│PK,FK:task_id │  │PK,FK: task_id      │
└──────────────┘  │PK: platform        │
                  └────────────────────┘

┌──────────────────┐
│hopper_instances  │
│                  │
│ PK: id           │
│ FK: parent_id ───┼───┐
└──────────────────┘   │
       ▲               │
       │               │
       └───────────────┘
     (self-referencing)
```

## Data Types

### JSONB vs JSON

- **PostgreSQL**: Uses JSONB (binary JSON) for better performance and indexing
- **SQLite**: Uses JSON (text-based)
- SQLAlchemy handles the conversion automatically with `JSONB().with_variant(JSON(), 'sqlite')`

### Timestamps

All timestamps use UTC timezone and are stored as `TIMESTAMP` type:
- `created_at`: Automatically set on record creation
- `updated_at`: Automatically updated on record modification

## Migrations

Migrations are managed using Alembic:

```bash
# Create a new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# View current migration
alembic current
```

## Common Queries

### Get pending tasks for a project

```python
from hopper.database.repositories import TaskRepository

with get_sync_session() as session:
    repo = TaskRepository(session)
    tasks = repo.filter(
        filters={"project": "my-project", "status": "pending"},
        order_by="-created_at"
    )
```

### Get project statistics

```python
from hopper.database.repositories import ProjectRepository

with get_sync_session() as session:
    repo = ProjectRepository(session)
    stats = repo.get_project_statistics("my-project")
    # Returns: {"total_tasks": 10, "pending": 5, "in_progress": 3, "completed": 2}
```

### Analyze routing decisions

```python
from hopper.database.repositories import RoutingDecisionRepository

with get_sync_session() as session:
    repo = RoutingDecisionRepository(session)
    analytics = repo.get_decision_analytics()
    # Returns comprehensive routing analytics
```

## Performance Considerations

### Indexes

The schema includes indexes on frequently queried columns:
- Task project and status for filtering
- Task created_at for sorting
- (Future) GIN indexes on JSONB fields for PostgreSQL

### Connection Pooling

- **PostgreSQL**: Pool size of 5, max overflow of 10
- **SQLite**: Single connection with StaticPool
- Connections are recycled after 1 hour

### Query Optimization

- Use pagination (`skip`/`limit`) for large result sets
- Use specific filters instead of scanning all rows
- Repository methods use efficient SQLAlchemy queries

## Backup and Recovery

### SQLite

```bash
# Backup
sqlite3 hopper.db ".backup hopper_backup.db"

# Restore
cp hopper_backup.db hopper.db
```

### PostgreSQL

```bash
# Backup
pg_dump -U username hopper > hopper_backup.sql

# Restore
psql -U username hopper < hopper_backup.sql
```

## Development Tools

### Reset Database

```python
from hopper.database import reset_database
reset_database(confirm=True)  # Drops and recreates all tables
```

### Seed Sample Data

```bash
python scripts/seed-db.py --reset
```

### Dump Schema

```python
from hopper.database.utils import dump_schema
schema = dump_schema()
print(schema)
```

## Security

- Use environment variables for database credentials
- Never commit database URLs or passwords to version control
- Use connection pooling to prevent connection exhaustion
- Validate and sanitize all user inputs before database operations
- Use parameterized queries (SQLAlchemy handles this automatically)
