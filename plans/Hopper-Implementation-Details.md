# 🔧 Hopper Implementation Details

**Companion to:** Hopper Implementation Plan v1.0.0  
**Created:** 2025-12-26  
**Purpose:** Detailed technical specifications for implementation

---

## Core Components Implementation

### 1. Database Schema

```sql
-- Instance registry
CREATE TABLE hopper_instances (
    instance_id VARCHAR(100) PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,
    parent_instance_id VARCHAR(100),
    config JSONB,
    status VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    FOREIGN KEY (parent_instance_id) 
        REFERENCES hopper_instances(instance_id)
);

-- Tasks table
CREATE TABLE tasks (
    id VARCHAR(50) PRIMARY KEY,
    instance_id VARCHAR(100) NOT NULL,
    parent_task_id VARCHAR(50),
    
    title VARCHAR(500) NOT NULL,
    description TEXT,
    project VARCHAR(100),
    status VARCHAR(50) DEFAULT 'pending',
    priority VARCHAR(20) DEFAULT 'medium',
    
    requester VARCHAR(100),
    owner VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    
    external_id VARCHAR(100),
    external_url VARCHAR(500),
    external_platform VARCHAR(50),
    
    source VARCHAR(50),
    conversation_id VARCHAR(100),
    context TEXT,
    
    tags JSONB DEFAULT '[]',
    required_capabilities JSONB DEFAULT '[]',
    depends_on JSONB DEFAULT '[]',
    blocks JSONB DEFAULT '[]',
    
    routing_confidence FLOAT,
    routing_reasoning TEXT,
    
    FOREIGN KEY (instance_id) 
        REFERENCES hopper_instances(instance_id)
);

-- Projects table
CREATE TABLE projects (
    name VARCHAR(100) PRIMARY KEY,
    slug VARCHAR(100) UNIQUE,
    repository VARCHAR(500),
    
    capabilities JSONB DEFAULT '[]',
    tags JSONB DEFAULT '[]',
    
    executor_type VARCHAR(50),
    executor_config JSONB,
    
    auto_claim BOOLEAN DEFAULT false,
    priority_boost JSONB,
    velocity VARCHAR(20),
    sla JSONB,
    
    webhook_url VARCHAR(500),
    api_endpoint VARCHAR(500),
    
    sync_config JSONB,
    
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100),
    last_sync TIMESTAMP
);

-- Routing decisions
CREATE TABLE routing_decisions (
    task_id VARCHAR(50) PRIMARY KEY REFERENCES tasks(id),
    project VARCHAR(100) REFERENCES projects(name),
    confidence FLOAT,
    reasoning TEXT,
    alternatives JSONB,
    decided_by VARCHAR(50),
    decided_at TIMESTAMP DEFAULT NOW(),
    decision_time_ms FLOAT,
    
    workload_snapshot JSONB,
    context JSONB
);

-- Task feedback
CREATE TABLE task_feedback (
    task_id VARCHAR(50) PRIMARY KEY REFERENCES tasks(id),
    
    estimated_duration VARCHAR(50),
    actual_duration VARCHAR(50),
    complexity_rating INT,
    
    quality_score FLOAT,
    required_rework BOOLEAN,
    rework_reason TEXT,
    
    was_good_match BOOLEAN,
    should_have_routed_to VARCHAR(100),
    routing_feedback TEXT,
    
    unexpected_blockers JSONB,
    required_skills_not_tagged JSONB,
    
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Task delegations (for multi-instance)
CREATE TABLE task_delegations (
    parent_instance_id VARCHAR(100),
    parent_task_id VARCHAR(50),
    child_instance_id VARCHAR(100),
    child_task_id VARCHAR(50),
    delegated_at TIMESTAMP DEFAULT NOW(),
    
    PRIMARY KEY (parent_instance_id, parent_task_id)
);

-- External mappings (for sync)
CREATE TABLE external_mappings (
    task_id VARCHAR(50) REFERENCES tasks(id),
    platform VARCHAR(50),
    external_id VARCHAR(100),
    external_url VARCHAR(500),
    
    PRIMARY KEY (task_id, platform)
);

-- Indexes for performance
CREATE INDEX idx_tasks_instance ON tasks(instance_id);
CREATE INDEX idx_tasks_project ON tasks(project);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);
CREATE INDEX idx_tasks_tags ON tasks USING gin(tags);
CREATE INDEX idx_feedback_was_good_match ON task_feedback(was_good_match);
CREATE INDEX idx_instances_parent ON hopper_instances(parent_instance_id);
CREATE INDEX idx_instances_scope ON hopper_instances(scope);
```

### 2. API Endpoints Specification

```yaml
# REST API Specification

Base URL: /api/v1

Authentication:
  Type: Bearer Token
  Header: Authorization: Bearer <token>

Endpoints:

# Tasks
POST /tasks
  Description: Create a new task
  Request Body:
    title: string (required)
    description: string
    project: string (optional, will auto-route if null)
    tags: array[string]
    priority: enum[low, medium, high, urgent]
    executor_preference: string
    required_capabilities: array[string]
    context: string
    conversation_id: string
  Response:
    task_id: string
    routed_to: string
    routing_confidence: float
    external_url: string (if synced)

GET /tasks
  Description: List tasks with filters
  Query Parameters:
    instance_id: string
    project: string
    status: enum[pending, claimed, in_progress, blocked, done]
    tags: array[string]
    priority: enum[low, medium, high, urgent]
    limit: int (default: 50)
    offset: int (default: 0)
  Response:
    tasks: array[Task]
    total: int
    page: int

GET /tasks/{task_id}
  Description: Get specific task
  Response: Task object

PUT /tasks/{task_id}
  Description: Update task
  Request Body: Partial Task object
  Response: Updated Task object

DELETE /tasks/{task_id}
  Description: Delete task
  Response: 204 No Content

POST /tasks/{task_id}/claim
  Description: Claim task for execution
  Request Body:
    executor: string
  Response: Task object

POST /tasks/{task_id}/complete
  Description: Mark task as complete
  Request Body:
    feedback: TaskFeedback object (optional)
  Response: Task object

GET /tasks/next
  Description: Get next task for executor
  Query Parameters:
    executor: string
    capabilities: array[string]
  Response: Task object or null

# Projects
POST /projects/register
  Description: Register a new project
  Request Body: ProjectRegistration object
  Response: Project object

GET /projects
  Description: List registered projects
  Response: array[Project]

GET /projects/{name}
  Description: Get project details
  Response: Project object

PUT /projects/{name}
  Description: Update project
  Request Body: Partial Project object
  Response: Updated Project object

DELETE /projects/{name}
  Description: Unregister project
  Response: 204 No Content

# Instances
GET /instances
  Description: List all Hopper instances
  Query Parameters:
    scope: enum[global, project, orchestration]
    parent: string (instance_id)
  Response: array[HopperInstance]

GET /instances/tree
  Description: Get instance hierarchy tree
  Response: Tree structure of instances

GET /instances/{instance_id}
  Description: Get instance details
  Response: HopperInstance object

# Memory
GET /memory/similar/{task_id}
  Description: Find similar past routings
  Query Parameters:
    limit: int (default: 10)
  Response: array[RoutingEpisode]

GET /memory/patterns
  Description: Get learned routing patterns
  Response: array[RoutingPattern]

GET /memory/stats/{project}
  Description: Get project performance statistics
  Response: ProjectStats object

POST /memory/consolidate
  Description: Trigger memory consolidation
  Response: ConsolidationJob object

# Federation (Phase 6)
GET /federation/discover
  Description: Announce this Hopper for discovery
  Response: HopperPeer object

POST /federation/delegate
  Description: Receive delegated task from peer
  Request Body: DelegatedTask object
  Response: Acceptance or rejection

POST /federation/notify_completion
  Description: Receive completion notification
  Request Body: CompletionNotification object
  Response: Acknowledgment

# Health & Monitoring
GET /health
  Description: Health check endpoint
  Response:
    status: enum[healthy, degraded, unhealthy]
    checks:
      database: bool
      redis: bool
      opensearch: bool
    version: string

GET /metrics
  Description: Prometheus metrics endpoint
  Response: Prometheus format metrics
```

### 3. Configuration Files

```yaml
# config/global_hopper.yaml
# Configuration for Global Hopper instance

scope: global
instance_id: hopper-global

server:
  host: "0.0.0.0"
  port: 8080
  workers: 4

storage:
  type: postgresql
  url: ${DATABASE_URL}
  pool_size: 10

memory:
  working:
    backend: redis
    url: ${REDIS_URL}
    ttl: 3600
  
  episodic:
    backend: opensearch
    url: ${OPENSEARCH_URL}
    index: hopper-global-history
    retention_days: 365
  
  consolidated:
    backend: gitlab
    url: ${GITLAB_URL}
    token: ${GITLAB_TOKEN}
    repository: hopper/global-memory
    branch: main
    consolidation_schedule: "0 2 * * *"

intelligence:
  provider: hybrid
  
  rules:
    config_file: config/routing_rules.yaml
    default_project: hopper
  
  llm:
    model: claude-sonnet-4
    api_key: ${ANTHROPIC_API_KEY}
    temperature: 0.3
    max_tokens: 2000
  
  hybrid:
    simple_threshold: 0.8
    use_llm_for_complex: true

integrations:
  mcp:
    enabled: true
    port: 8081
  
  github:
    enabled: true
    token: ${GITHUB_TOKEN}
  
  gitlab:
    enabled: true
    url: ${GITLAB_URL}
    token: ${GITLAB_TOKEN}

child_instances:
  auto_create: true
  default_config: config/project_hopper_template.yaml

logging:
  level: INFO
  format: json
  file: /var/log/hopper/hopper.log

---

# config/routing_rules.yaml
# Rules-based routing configuration

routing_rules:
  czarina:
    keywords:
      - orchestration
      - worker
      - daemon
      - multi-agent
      - code generation
    tags:
      - orchestration
      - ai-agents
      - automation
    capabilities:
      - orchestration
      - multi-file-editing
      - test-generation
    priority_boost:
      infrastructure: 1.3
      automation: 1.2
  
  sark:
    keywords:
      - security
      - policy
      - mcp server
      - governance
      - access control
    tags:
      - security
      - governance
      - mcp
    capabilities:
      - security
      - policy-enforcement
      - mcp-wrapping
    priority_boost:
      security: 2.0
      urgent: 1.5
  
  symposium:
    keywords:
      - consciousness
      - sage
      - philosophy
      - research
    tags:
      - consciousness
      - research
      - philosophy
    capabilities:
      - consciousness-research
      - sage-coordination
      - distributed-compute
    priority_boost:
      research: 1.4
  
  waypoint:
    keywords:
      - deep thought
      - architecture
      - design
      - strategy
    tags:
      - architecture
      - design
      - strategy
    capabilities:
      - architectural-design
      - strategic-planning
    priority_boost:
      architecture: 1.5

default_project: hopper
```

### 4. Docker Compose Setup

```yaml
# docker-compose.yml
version: '3.8'

services:
  hopper:
    build:
      context: .
      dockerfile: docker/Dockerfile
    ports:
      - "8080:8080"
      - "8081:8081"  # MCP server
    volumes:
      - ./config:/app/config:ro
      - hopper-data:/data
    environment:
      - DATABASE_URL=postgresql://hopper:${DB_PASSWORD}@postgres:5432/hopper
      - REDIS_URL=redis://redis:6379
      - OPENSEARCH_URL=http://opensearch:9200
      - GITLAB_URL=${GITLAB_URL}
      - GITLAB_TOKEN=${GITLAB_TOKEN}
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
    depends_on:
      - postgres
      - redis
      - opensearch
    restart: unless-stopped

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: hopper
      POSTGRES_USER: hopper
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    restart: unless-stopped

  opensearch:
    image: opensearchproject/opensearch:2.11.0
    environment:
      - discovery.type=single-node
      - OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m
      - DISABLE_SECURITY_PLUGIN=true
    ports:
      - "9200:9200"
    volumes:
      - opensearch-data:/usr/share/opensearch/data
    restart: unless-stopped

  opensearch-dashboards:
    image: opensearchproject/opensearch-dashboards:2.11.0
    ports:
      - "5601:5601"
    environment:
      OPENSEARCH_HOSTS: '["http://opensearch:9200"]'
      DISABLE_SECURITY_DASHBOARDS_PLUGIN: "true"
    depends_on:
      - opensearch
    restart: unless-stopped

volumes:
  hopper-data:
  postgres-data:
  redis-data:
  opensearch-data:
```

```dockerfile
# docker/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml .
COPY README.md .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Copy application code
COPY hopper/ ./hopper/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create data directory
RUN mkdir -p /data

# Expose ports
EXPOSE 8080 8081

# Run database migrations and start server
CMD ["sh", "-c", "alembic upgrade head && hopper serve --config /app/config/global_hopper.yaml"]
```

---

## Testing Strategy

### Unit Tests

```python
# tests/test_models.py
import pytest
from hopper.core.models import Task, TaskCreate, Priority, Status

def test_task_creation():
    task_data = TaskCreate(
        title="Test task",
        description="Test description",
        tags=["test"],
        priority=Priority.HIGH
    )
    assert task_data.title == "Test task"
    assert task_data.priority == Priority.HIGH

def test_task_validation():
    with pytest