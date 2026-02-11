# Hopper Server Storage Architecture

## Overview

The server deployment of Hopper uses a multi-database architecture optimized for different data access patterns:

- **PostgreSQL** - Structured data, ACID transactions
- **pgvector** - Vector embeddings for semantic search
- **Neo4j** - Graph relationships for traversal queries

This architecture supports the "northbound sync" model where local/embedded Hopper instances consolidate learned patterns up to a central server.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Hopper Server                                │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                      API Layer (FastAPI)                     │    │
│  └─────────────────────────────────────────────────────────────┘    │
│              │                    │                    │             │
│              ▼                    ▼                    ▼             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │   PostgreSQL    │  │    pgvector     │  │     Neo4j       │      │
│  │                 │  │                 │  │                 │      │
│  │ - Tasks         │  │ - Task vectors  │  │ - Instance tree │      │
│  │ - Instances     │  │ - Pattern vecs  │  │ - Delegations   │      │
│  │ - Feedback      │  │ - Episode vecs  │  │ - Dependencies  │      │
│  │ - Patterns      │  │                 │  │ - Tag relations │      │
│  │ - Episodes      │  │                 │  │                 │      │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘      │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ northbound sync
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐
              │  Local    │  │ Embedded  │  │ Embedded  │
              │ ~/.hopper │  │ Project A │  │ Project B │
              │ (markdown)│  │ (markdown)│  │ (markdown)│
              └───────────┘  └───────────┘  └───────────┘
```

## Component Specifications

### 1. PostgreSQL (Primary Data Store)

**Purpose:** Authoritative source for structured entities and transactional data.

**Schema:**

```sql
-- Core entities (existing)
CREATE TABLE tasks (
    id VARCHAR(36) PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    status VARCHAR(50) NOT NULL,
    priority VARCHAR(50),
    project VARCHAR(200),
    instance_id VARCHAR(36) REFERENCES hopper_instances(id),
    tags JSONB DEFAULT '{}',
    source VARCHAR(50),  -- 'local', 'api', 'northbound'
    source_instance_id VARCHAR(36),  -- originating local instance
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE hopper_instances (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    scope VARCHAR(50) NOT NULL,  -- GLOBAL, PROJECT, ORCHESTRATION
    instance_type VARCHAR(50) NOT NULL,
    status VARCHAR(50) NOT NULL,
    parent_id VARCHAR(36) REFERENCES hopper_instances(id),
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE task_delegations (
    id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) REFERENCES tasks(id),
    source_instance_id VARCHAR(36) REFERENCES hopper_instances(id),
    target_instance_id VARCHAR(36) REFERENCES hopper_instances(id),
    delegation_type VARCHAR(50),
    status VARCHAR(50),
    delegated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Memory/Learning entities
CREATE TABLE routing_episodes (
    id VARCHAR(36) PRIMARY KEY,
    task_id VARCHAR(36) REFERENCES tasks(id),
    chosen_instance VARCHAR(36),
    confidence FLOAT,
    strategy VARCHAR(50),
    decision_factors JSONB,
    outcome_success BOOLEAN,
    outcome_duration VARCHAR(50),
    source VARCHAR(50),  -- 'local', 'server', 'northbound'
    source_instance_id VARCHAR(36),
    routed_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE routing_patterns (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    pattern_type VARCHAR(50),  -- tag, text, combined, priority
    target_instance VARCHAR(36),
    tag_criteria JSONB,
    text_criteria JSONB,
    priority_criteria VARCHAR(50),
    confidence FLOAT DEFAULT 0.5,
    usage_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    failure_count INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    source VARCHAR(50),  -- 'learned', 'manual', 'northbound'
    source_instance_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    last_refined_at TIMESTAMP
);

CREATE TABLE task_feedback (
    task_id VARCHAR(36) PRIMARY KEY REFERENCES tasks(id),
    was_good_match BOOLEAN,
    routing_feedback TEXT,
    should_have_routed_to VARCHAR(36),
    quality_score FLOAT,
    complexity_rating INT,
    required_rework BOOLEAN,
    source VARCHAR(50),
    source_instance_id VARCHAR(36),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Northbound sync tracking
CREATE TABLE sync_log (
    id VARCHAR(36) PRIMARY KEY,
    source_instance_id VARCHAR(36) NOT NULL,
    sync_type VARCHAR(50),  -- 'patterns', 'episodes', 'feedback'
    items_synced INT,
    synced_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_instance ON tasks(instance_id);
CREATE INDEX idx_tasks_source ON tasks(source, source_instance_id);
CREATE INDEX idx_episodes_task ON routing_episodes(task_id);
CREATE INDEX idx_episodes_outcome ON routing_episodes(outcome_success);
CREATE INDEX idx_patterns_target ON routing_patterns(target_instance);
CREATE INDEX idx_patterns_active ON routing_patterns(is_active);
```

### 2. pgvector (Vector Embeddings)

**Purpose:** Semantic similarity search for tasks, patterns, and routing decisions.

**Setup:**

```sql
-- Enable extension
CREATE EXTENSION vector;

-- Task embeddings
CREATE TABLE task_embeddings (
    task_id VARCHAR(36) PRIMARY KEY REFERENCES tasks(id),
    embedding vector(1536),  -- OpenAI ada-002 dimension
    model VARCHAR(100),      -- embedding model used
    created_at TIMESTAMP DEFAULT NOW()
);

-- Pattern embeddings (for matching new tasks to patterns)
CREATE TABLE pattern_embeddings (
    pattern_id VARCHAR(36) PRIMARY KEY REFERENCES routing_patterns(id),
    embedding vector(1536),
    model VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Episode embeddings (for finding similar historical decisions)
CREATE TABLE episode_embeddings (
    episode_id VARCHAR(36) PRIMARY KEY REFERENCES routing_episodes(id),
    embedding vector(1536),
    model VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for similarity search
CREATE INDEX idx_task_embedding ON task_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_pattern_embedding ON pattern_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_episode_embedding ON episode_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**Query Examples:**

```sql
-- Find similar tasks
SELECT t.id, t.title,
       1 - (te.embedding <=> $1) as similarity
FROM tasks t
JOIN task_embeddings te ON t.id = te.task_id
ORDER BY te.embedding <=> $1
LIMIT 10;

-- Find matching patterns for a task
SELECT p.id, p.name, p.target_instance,
       1 - (pe.embedding <=> $1) as similarity
FROM routing_patterns p
JOIN pattern_embeddings pe ON p.id = pe.pattern_id
WHERE p.is_active = TRUE
ORDER BY pe.embedding <=> $1
LIMIT 5;
```

**Embedding Generation:**

```python
from openai import OpenAI

client = OpenAI()

def generate_task_embedding(task: Task) -> list[float]:
    """Generate embedding for a task."""
    text = f"{task.title}\n{task.description or ''}\nTags: {', '.join(task.tags.keys())}"

    response = client.embeddings.create(
        model="text-embedding-ada-002",
        input=text
    )

    return response.data[0].embedding
```

### 3. Neo4j (Graph Database)

**Purpose:** Relationship traversal for instance hierarchies, delegation chains, and dependency graphs.

**Node Types:**

```cypher
// Instance hierarchy
(:Instance {
    id: string,
    name: string,
    scope: string,  // GLOBAL, PROJECT, ORCHESTRATION
    status: string
})

// Tasks
(:Task {
    id: string,
    title: string,
    status: string,
    priority: string
})

// Patterns
(:Pattern {
    id: string,
    name: string,
    confidence: float
})

// Tags (for tag co-occurrence analysis)
(:Tag {
    name: string
})
```

**Relationship Types:**

```cypher
// Instance hierarchy
(:Instance)-[:CHILD_OF]->(:Instance)
(:Instance)-[:MANAGES]->(:Task)

// Delegation chain
(:Task)-[:DELEGATED_TO {
    delegation_id: string,
    type: string,
    status: string,
    delegated_at: datetime
}]->(:Instance)

// Task dependencies
(:Task)-[:DEPENDS_ON]->(:Task)
(:Task)-[:BLOCKS]->(:Task)
(:Task)-[:SUBTASK_OF]->(:Task)

// Pattern relationships
(:Pattern)-[:ROUTES_TO]->(:Instance)
(:Pattern)-[:DERIVED_FROM]->(:Pattern)

// Tag relationships
(:Task)-[:HAS_TAG]->(:Tag)
(:Tag)-[:CO_OCCURS_WITH {weight: float}]->(:Tag)
(:Pattern)-[:MATCHES_TAG]->(:Tag)
```

**Example Queries:**

```cypher
// Get full delegation chain for a task
MATCH path = (t:Task {id: $taskId})-[:DELEGATED_TO*]->(i:Instance)
RETURN path;

// Find all tasks blocked by a specific task
MATCH (blocker:Task {id: $taskId})<-[:DEPENDS_ON*]-(blocked:Task)
RETURN blocked;

// Get instance hierarchy from a leaf node
MATCH path = (leaf:Instance {id: $instanceId})-[:CHILD_OF*]->(root:Instance)
WHERE NOT (root)-[:CHILD_OF]->()
RETURN path;

// Find commonly co-occurring tags
MATCH (t1:Tag)<-[:HAS_TAG]-(task:Task)-[:HAS_TAG]->(t2:Tag)
WHERE t1.name < t2.name
WITH t1, t2, COUNT(task) as co_occurrences
WHERE co_occurrences > 5
RETURN t1.name, t2.name, co_occurrences
ORDER BY co_occurrences DESC;

// Find patterns that successfully route to an instance
MATCH (p:Pattern)-[:ROUTES_TO]->(i:Instance {id: $instanceId})
WHERE p.confidence > 0.7
RETURN p
ORDER BY p.confidence DESC;

// Trace task lineage (subtasks and delegations)
MATCH path = (root:Task)-[:SUBTASK_OF|DELEGATED_TO*]->(t:Task {id: $taskId})
RETURN path;
```

**Sync from PostgreSQL:**

```python
from neo4j import GraphDatabase

class GraphSync:
    """Sync relevant data from Postgres to Neo4j."""

    def __init__(self, neo4j_uri: str, neo4j_auth: tuple):
        self.driver = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    def sync_instance(self, instance: HopperInstance):
        """Sync an instance and its parent relationship."""
        with self.driver.session() as session:
            session.run("""
                MERGE (i:Instance {id: $id})
                SET i.name = $name, i.scope = $scope, i.status = $status
            """, id=instance.id, name=instance.name,
                scope=instance.scope.value, status=instance.status.value)

            if instance.parent_id:
                session.run("""
                    MATCH (child:Instance {id: $childId})
                    MATCH (parent:Instance {id: $parentId})
                    MERGE (child)-[:CHILD_OF]->(parent)
                """, childId=instance.id, parentId=instance.parent_id)

    def sync_delegation(self, delegation: TaskDelegation):
        """Sync a delegation relationship."""
        with self.driver.session() as session:
            session.run("""
                MATCH (t:Task {id: $taskId})
                MATCH (i:Instance {id: $targetId})
                MERGE (t)-[d:DELEGATED_TO {delegation_id: $delegationId}]->(i)
                SET d.type = $type, d.status = $status,
                    d.delegated_at = datetime($delegatedAt)
            """, taskId=delegation.task_id,
                targetId=delegation.target_instance_id,
                delegationId=delegation.id,
                type=delegation.delegation_type.value,
                status=delegation.status.value,
                delegatedAt=delegation.delegated_at.isoformat())

    def sync_task_tags(self, task: Task):
        """Sync task-tag relationships."""
        with self.driver.session() as session:
            # Ensure task exists
            session.run("""
                MERGE (t:Task {id: $id})
                SET t.title = $title, t.status = $status
            """, id=task.id, title=task.title, status=task.status.value)

            # Create tag relationships
            for tag in task.tags.keys():
                session.run("""
                    MERGE (tag:Tag {name: $tagName})
                    WITH tag
                    MATCH (t:Task {id: $taskId})
                    MERGE (t)-[:HAS_TAG]->(tag)
                """, tagName=tag, taskId=task.id)
```

## Northbound Sync Protocol

Local/embedded instances can sync learned data to the server:

### Sync Payload

```python
@dataclass
class NorthboundSyncPayload:
    """Data synced from local to server."""

    source_instance_id: str
    source_instance_name: str

    # Learned patterns (anonymized)
    patterns: list[PatternSync]

    # Episode summaries (no task content)
    episode_summaries: list[EpisodeSummary]

    # Aggregated feedback stats
    feedback_stats: FeedbackStats

@dataclass
class PatternSync:
    """Pattern data for sync."""
    name: str
    pattern_type: str
    tag_criteria: dict
    text_criteria: dict  # keywords only, no content
    confidence: float
    usage_count: int
    success_count: int

@dataclass
class EpisodeSummary:
    """Anonymized episode summary."""
    tags: list[str]
    chosen_instance_scope: str  # scope, not ID
    confidence: float
    outcome_success: bool
    strategy: str

@dataclass
class FeedbackStats:
    """Aggregated feedback statistics."""
    total_feedback: int
    good_matches: int
    bad_matches: int
    avg_quality_score: float
    avg_complexity: float
```

### Sync Endpoint

```python
@router.post("/sync/northbound")
async def receive_northbound_sync(
    payload: NorthboundSyncPayload,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Receive sync data from local/embedded instances.

    Merges patterns, updates statistics, logs sync.
    """
    # Merge patterns
    for pattern in payload.patterns:
        await merge_pattern(db, pattern, payload.source_instance_id)

    # Record episode summaries for aggregate learning
    for episode in payload.episode_summaries:
        await record_episode_summary(db, episode, payload.source_instance_id)

    # Update global statistics
    await update_global_stats(db, payload.feedback_stats)

    # Log sync
    await log_sync(db, payload.source_instance_id, payload)

    return {"status": "synced", "patterns_merged": len(payload.patterns)}
```

## Repository Abstraction

The repository layer abstracts storage backend:

```python
from abc import ABC, abstractmethod
from typing import Protocol

class TaskRepository(Protocol):
    """Task repository interface."""

    def create(self, task: Task) -> Task: ...
    def get(self, task_id: str) -> Task | None: ...
    def update(self, task_id: str, updates: dict) -> Task: ...
    def delete(self, task_id: str) -> None: ...
    def search(self, query: str, **filters) -> list[Task]: ...
    def find_similar(self, task: Task, limit: int = 10) -> list[Task]: ...

class PostgresTaskRepository:
    """PostgreSQL implementation."""

    def __init__(self, session: Session, vector_session: Session = None):
        self.session = session
        self.vector_session = vector_session

    def find_similar(self, task: Task, limit: int = 10) -> list[Task]:
        """Use pgvector for similarity search."""
        embedding = generate_task_embedding(task)

        results = self.vector_session.execute("""
            SELECT t.* FROM tasks t
            JOIN task_embeddings te ON t.id = te.task_id
            ORDER BY te.embedding <=> :embedding
            LIMIT :limit
        """, {"embedding": embedding, "limit": limit})

        return [Task(**row) for row in results]

class GraphQueryService:
    """Service for graph-based queries."""

    def __init__(self, neo4j_driver):
        self.driver = neo4j_driver

    def get_delegation_chain(self, task_id: str) -> list[dict]:
        """Get full delegation history via graph traversal."""
        with self.driver.session() as session:
            result = session.run("""
                MATCH path = (t:Task {id: $taskId})-[:DELEGATED_TO*]->(i:Instance)
                RETURN [node in nodes(path) |
                    CASE WHEN node:Task THEN {type: 'task', id: node.id}
                         ELSE {type: 'instance', id: node.id, name: node.name}
                    END
                ] as chain
            """, taskId=task_id)

            return [record["chain"] for record in result]
```

## Configuration

```yaml
# config/server.yaml

database:
  postgres:
    url: postgresql://hopper:password@localhost:5432/hopper
    pool_size: 20

  pgvector:
    enabled: true
    embedding_model: text-embedding-ada-002
    embedding_dimension: 1536

  neo4j:
    enabled: true
    url: bolt://localhost:7687
    username: neo4j
    password: password

sync:
  northbound:
    enabled: true
    endpoint: /api/v1/sync/northbound
    auth_required: true

embeddings:
  provider: openai
  model: text-embedding-ada-002
  batch_size: 100

graph:
  sync_on_write: true  # Sync to Neo4j on every write
  async_sync: false    # Or batch sync periodically
```

## Deployment

### Docker Compose

```yaml
version: '3.8'

services:
  hopper-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://hopper:password@postgres:5432/hopper
      - NEO4J_URL=bolt://neo4j:7687
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
      - neo4j

  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: hopper
      POSTGRES_PASSWORD: password
      POSTGRES_DB: hopper
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  neo4j:
    image: neo4j:5
    environment:
      NEO4J_AUTH: neo4j/password
    volumes:
      - neo4j_data:/data
    ports:
      - "7474:7474"  # Browser
      - "7687:7687"  # Bolt

volumes:
  postgres_data:
  neo4j_data:
```

## Migration Path

1. **Current state:** PostgreSQL only (SQLAlchemy models)
2. **Add pgvector:**
   - Install extension
   - Add embedding tables
   - Background job to generate embeddings
3. **Add Neo4j:**
   - Deploy Neo4j
   - Add GraphSync service
   - Sync existing relationships
4. **Enable northbound:**
   - Add sync endpoint
   - Local instances can opt-in to sync

## Future Considerations

- **Sharding:** Partition by instance scope for scale
- **Read replicas:** pgvector queries on replicas
- **Graph caching:** Cache frequent traversals
- **Embedding updates:** Re-embed on task updates
- **Privacy controls:** Opt-out of northbound sync
