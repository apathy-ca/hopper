# 🔄 Hopper Multi-Instance Architecture

## Addendum to Hopper Specification v1.0.0

**Author:** James Henry (with Claude)  
**Date:** 2025-12-26  
**Purpose:** Clarify Hopper as multi-instance hierarchical system

---

## Executive Summary

**Hopper is not a single queue. Hopper is an architecture.**

The same Hopper codebase can be instantiated at multiple scopes with different configurations, forming a hierarchical task management system. A single Hopper installation can host multiple instances that coordinate through parent-child relationships.

**Key Insight:** It's Hoppers all the way down.

---

## The Multi-Instance Model

### Hopper Instances Are Hierarchical
```
┌─ Global Hopper Instance ─────────────────────────┐
│ Routes work across entire ecosystem              │
│ Intelligence: LLM or Sage                        │
│ Persistence: Permanent (PostgreSQL + OpenSearch) │
└───────────────────┬──────────────────────────────┘
                    │
         ┌──────────┼──────────┐
         │          │          │
    ┌────▼────┐ ┌──▼─────┐ ┌──▼────────┐
    │Project  │ │Project │ │Project    │
    │Hopper:  │ │Hopper: │ │Hopper:    │
    │czarina  │ │sark    │ │symposium  │
    └────┬────┘ └────────┘ └───────────┘
         │
    ┌────▼─────────────────────────────┐
    │Orchestration Hopper Instance     │
    │czarina-run-abc123                │
    │                                  │
    │ ┌─ Project Hopper ─────────────┐ │
    │ │ Overall run tasks            │ │
    │ └───────┬──────────────────────┘ │
    │         │                        │
    │ ┌───────▼──────────────────────┐ │
    │ │ Phase Hopper (Phase 1)      │ │
    │ │ Current phase tasks         │ │
    │ └─────────────────────────────┘ │
    └──────────────────────────────────┘
```

### Same Code, Different Scope

All instances run the same Hopper code with different configurations:
```python
from hopper import Hopper, HopperScope, HopperConfig

# Global instance
global_hopper = Hopper(
    scope=HopperScope.GLOBAL,
    instance_id="hopper-global",
    config=HopperConfig.for_global()
)

# Project instance (child of global)
project_hopper = Hopper(
    scope=HopperScope.PROJECT,
    instance_id="hopper-czarina",
    parent=global_hopper,
    config=HopperConfig.for_project()
)

# Orchestration instance (child of project)
orch_hopper = Hopper(
    scope=HopperScope.ORCHESTRATION,
    instance_id="hopper-czarina-run-xyz",
    parent=project_hopper,
    config=HopperConfig.for_orchestration()
)

# All use same API:
# - add_task()
# - get_next()
# - complete()
# - claim()
```

---

## Instance Types

### Type 1: Global Hopper

**Scope:** Cross-project strategic routing  
**Lifespan:** Permanent  
**Purpose:** Route work to the right project/executor  
**Intelligence:** LLM or Sage-managed  
**Persistence:** PostgreSQL + OpenSearch + GitLab  

**Characteristics:**
```yaml
Input Sources:
  - MCP (from Claude/Cursor conversations)
  - CLI (hopper add "task")
  - HTTP API
  - Webhooks (GitHub, GitLab, Slack, etc.)
  - Email gateway

Routing Targets:
  - Registered projects (czarina, sark, symposium, waypoint)
  - Human executors
  - External systems

Example Tasks:
  - "Add MCP integration to SARK" → Routes to: sark project
  - "Write blog post about Hopper" → Routes to: waypoint
  - "Fix urgent production bug" → Routes to: czarina (fast)

Configuration:
  intelligence: llm  # or sage
  memory:
    episodic: opensearch
    consolidated: gitlab
    learning: true
  persistence: postgresql
  retention: forever
```

**Deployment:**
```bash
# Run as primary service
hopper serve --config global_hopper.yaml --port 8080

# Or as Symposium component
symposium serve  # Hopper integrated
```

### Type 2: Project Hopper

**Scope:** Single project task management  
**Lifespan:** Permanent (as long as project exists)  
**Purpose:** Manage all work for one project  
**Intelligence:** Rules-based or simple LLM  
**Persistence:** SQLite or shared PostgreSQL  

**Characteristics:**
```yaml
Input Sources:
  - Parent hopper (receives routed tasks from global)
  - Local CLI
  - Project-specific webhooks

Routing Targets:
  - Orchestration runs (for multi-agent work)
  - Human assignees (for simple work)
  - CI/CD pipelines
  - Manual execution

Example Tasks:
  - "Implement structured logging" → Routes to: new orchestration run
  - "Fix typo in README" → Routes to: human (too simple for orchestration)
  - "Run integration tests" → Routes to: CI/CD pipeline

Configuration:
  intelligence: rules  # Simpler than global
  memory:
    episodic: sqlite  # Lighter weight
    consolidated: null
    learning: false
  persistence: sqlite
  retention: 1_year
```

**Creation:**
```python
# Created automatically when global routes to project
global_hopper = Hopper.global_instance()

# Route task to project
task = global_hopper.add_task(
    title="Add feature X",
    project="czarina"
)

# Project hopper auto-created if doesn't exist
project_hopper = global_hopper.get_child_hopper("czarina")
```

### Type 3: Orchestration Hopper

**Scope:** Single orchestration run  
**Lifespan:** Duration of run (hours)  
**Purpose:** Coordinate multi-agent work execution  
**Intelligence:** Simple priority queue  
**Persistence:** In-memory or ephemeral SQLite  

**Characteristics:**
```yaml
Input Sources:
  - Parent hopper (receives task from project)
  - Phase breakdown (tasks generated during orchestration)
  - Worker requests (dynamic task creation)

Routing Targets:
  - Worker agents (architect, coder, tester, etc.)
  - Sub-phases
  - Human review checkpoints

Example Tasks:
  - "Design API schema" → Worker: architect
  - "Implement endpoint" → Worker: coder  
  - "Write integration test" → Worker: tester

Hierarchy:
  - Project-level hopper: Overall orchestration goals
  - Phase-level hopper: Current phase tasks
  - Worker pulls from active phase hopper

Configuration:
  intelligence: simple_priority  # Just queue ordering
  memory:
    episodic: null
    consolidated: null
    learning: false
  persistence: memory  # Ephemeral
  retention: run_duration  # Deleted after run completes
```

**Usage in Czarina:**
```python
class CzarinaOrchestrator:
    def orchestrate(self, task: Task):
        # Create orchestration-scoped hopper
        run_hopper = Hopper(
            scope=HopperScope.ORCHESTRATION,
            instance_id=f"czarina-run-{self.run_id}",
            parent=self.project_hopper
        )
        
        # Break task into project-level goals
        run_hopper.add_task(Task(title="Design solution"))
        run_hopper.add_task(Task(title="Implement code"))
        run_hopper.add_task(Task(title="Write tests"))
        run_hopper.add_task(Task(title="Document changes"))
        
        # For each phase
        for phase in self.phases:
            phase_hopper = run_hopper.get_child_hopper(f"phase-{phase.id}")
            
            # Workers pull from phase hopper
            while not phase_hopper.is_empty():
                for worker in self.workers:
                    task = phase_hopper.get_next(executor=worker.name)
                    if task:
                        worker.execute(task)
                        phase_hopper.complete(task.id)
        
        return run_hopper.summary()
```

---

## Task Flow Through Hierarchy

### Example: "Add MCP Integration to SARK"

**Step 1: Task Creation (Global Hopper)**
```
User in Claude: "We should add MCP support to SARK"
Claude calls MCP: hopper.add_task(
    title="Add MCP server support to SARK",
    tags=["security", "mcp", "integration"]
)

Global Hopper receives task
├─ Analyzes: security + mcp keywords
├─ Queries memory: Past MCP tasks went to SARK
├─ Routes to: sark project
└─ Creates task in Project Hopper (SARK)
```

**Step 2: Project Decision (Project Hopper)**
```
Project Hopper (SARK) receives task
├─ Evaluates complexity
├─ Decision: Needs orchestration (multi-file changes)
├─ Triggers: Czarina orchestration
└─ Creates Orchestration Hopper instance
```

**Step 3: Orchestration Execution (Orchestration Hopper)**
```
Orchestration Hopper (czarina-run-abc123)
├─ Project Hopper tasks:
│  ├─ "Design MCP server API"
│  ├─ "Implement server"
│  ├─ "Add authentication"
│  └─ "Write tests"
│
├─ Phase 1 Hopper (Design):
│  ├─ "Research MCP protocol" → architect
│  ├─ "Design API schema" → architect
│  └─ "Create implementation plan" → architect
│
├─ Phase 2 Hopper (Implementation):
│  ├─ "Implement MCP server class" → coder
│  ├─ "Add tool registration" → coder
│  └─ "Implement authentication" → coder
│
└─ Phase 3 Hopper (Testing):
   ├─ "Write unit tests" → tester
   ├─ "Write integration tests" → tester
   └─ "Test with real MCP client" → tester
```

**Step 4: Completion Bubbles Up**
```
Phase 3 complete → Orchestration Hopper
Orchestration complete → Project Hopper (SARK)
Project task complete → Global Hopper
Global task marked DONE ✓

Feedback recorded at each level:
├─ Orchestration: "4 hours, high quality"
├─ Project: "MCP integration successful"
└─ Global: "SARK routing was correct"
```

---

## Unified API Across Scopes

### Core Interface (Works at Any Level)
```python
class Hopper:
    """Universal task queue - same API at all scopes"""
    
    def add_task(self, task: Task) -> str:
        """Add task - behavior varies by scope"""
        
    def get_next(self, executor: str) -> Optional[Task]:
        """Get next task - pulls from appropriate queue"""
        
    def complete(self, task_id: str, feedback: TaskFeedback = None):
        """Mark complete - bubbles up to parent if exists"""
        
    def claim(self, task_id: str, executor: str):
        """Claim task for execution"""
        
    def get_child_hopper(self, child_id: str) -> 'Hopper':
        """Get or create child hopper instance"""
        
    def notify_parent(self, event: HopperEvent):
        """Notify parent hopper of significant events"""
```

### Scope-Specific Behavior

**Same method, different implementation:**
```python
# add_task() behavior varies by scope

# Global Hopper
global_hopper.add_task(task)
→ Routes to best project
→ Creates task in Project Hopper
→ Returns: task routed to {project}

# Project Hopper  
project_hopper.add_task(task)
→ Decides: orchestration vs manual
→ Creates Orchestration Hopper OR assigns to human
→ Returns: task assigned to {executor}

# Orchestration Hopper
orch_hopper.add_task(task)
→ Adds to project/phase queue
→ Workers pull when ready
→ Returns: task queued for {worker}
```

---

## Configuration Per Scope

### Global Hopper Configuration
```yaml
# global_hopper.yaml

scope: global
instance_id: hopper-global

intelligence:
  provider: llm
  model: claude-sonnet-4
  temperature: 0.3

memory:
  episodic:
    backend: opensearch
    url: http://localhost:9200
    index: hopper-global-history
  
  consolidated:
    backend: gitlab
    url: https://gitlab.yourdomain.com
    repository: hopper/global-memory
    consolidation_schedule: "0 2 * * *"

persistence:
  storage: postgresql
  url: postgresql://localhost/hopper_global
  retention: forever

integrations:
  mcp:
    enabled: true
    port: 8081
  
  github:
    enabled: true
    token: ${GITHUB_TOKEN}
  
  gitlab:
    enabled: true
    url: https://gitlab.yourdomain.com
    token: ${GITLAB_TOKEN}

child_instances:
  auto_create: true
  default_config: project_hopper_template.yaml
```

### Project Hopper Configuration
```yaml
# project_hopper_template.yaml

scope: project
instance_id: hopper-{project_name}
parent: hopper-global

intelligence:
  provider: rules
  config_file: project_routing_rules.yaml

memory:
  episodic:
    backend: sqlite
    path: .hopper/{project_name}/history.db
  
  consolidated: null

persistence:
  storage: sqlite
  path: .hopper/{project_name}/tasks.db
  retention: 1_year

integrations:
  parent_hopper: true
  local_cli: true

child_instances:
  auto_create: true
  default_config: orchestration_hopper_template.yaml
```

### Orchestration Hopper Configuration
```yaml
# orchestration_hopper_template.yaml

scope: orchestration
instance_id: hopper-{project_name}-run-{run_id}
parent: hopper-{project_name}

intelligence:
  provider: simple_priority

memory:
  episodic: null
  consolidated: null

persistence:
  storage: memory
  retention: run_duration

integrations:
  parent_hopper: true
  worker_api: true

child_instances:
  auto_create: true
  max_depth: 2  # project + phase hoppers only
```

---

## Parent-Child Coordination

### Task Delegation (Parent → Child)
```python
# Global hopper delegates to project hopper
class Hopper:
    def add_task(self, task: Task) -> str:
        if self.scope == HopperScope.GLOBAL:
            # Route to project
            project = self.intelligence.decide_routing(task)
            
            # Get or create project hopper
            project_hopper = self.get_child_hopper(project)
            
            # Delegate task
            child_task_id = project_hopper.add_task(task)
            
            # Track delegation
            self.delegations[task.id] = {
                "child_instance": project,
                "child_task_id": child_task_id
            }
            
            return task.id
```

### Completion Notification (Child → Parent)
```python
class Hopper:
    def complete(self, task_id: str, feedback: TaskFeedback = None):
        # Mark complete locally
        self.storage.update(task_id, status="done")
        
        # Record feedback
        if feedback:
            self.feedback.record(task_id, feedback)
            
            # Learn from feedback if enabled
            if self.config.learning_enabled:
                self.intelligence.learn_from_outcome(task_id, feedback)
        
        # Notify parent if exists
        if self.parent:
            self.parent.notify_child_completion(
                child_instance=self.instance_id,
                task_id=task_id,
                feedback=feedback
            )
```

### Status Propagation
```python
# Task status flows up the hierarchy

Orchestration Hopper: Task XYZ → DONE
├─ Notifies: Project Hopper
│  └─ Checks: All orchestration tasks complete?
│     └─ If yes: Mark orchestration DONE
│        └─ Notifies: Global Hopper
│           └─ Marks: Original task DONE

# Feedback aggregates up hierarchy
Orchestration feedback: "4 hours, high quality"
Project feedback: "Orchestration successful, SARK MCP working"  
Global feedback: "Routing to SARK was correct decision"
```

---

## Instance Lifecycle Management

### Creation

**Automatic Creation (Recommended):**
```python
# Global hopper auto-creates project hoppers when routing
global_hopper.add_task(Task(project="new-project"))
→ Creates project hopper automatically if doesn't exist

# Project hopper auto-creates orchestration hoppers
project_hopper.add_task(Task(needs_orchestration=True))
→ Creates orchestration hopper for the run
```

**Manual Creation:**
```python
# Explicitly create child instance
project_hopper = Hopper(
    scope=HopperScope.PROJECT,
    instance_id="hopper-special-project",
    parent=global_hopper,
    config=custom_config
)

# Register with parent
global_hopper.register_child(project_hopper)
```

### Persistence

**Global & Project Hoppers:**
- Persist indefinitely
- Survive restarts
- Stored in database

**Orchestration Hoppers:**
- Ephemeral (in-memory)
- Deleted after run completes
- Optional: Archive to parent for history
```python
class Hopper:
    def archive_and_delete(self):
        """Orchestration hopper cleanup"""
        
        if self.scope == HopperScope.ORCHESTRATION:
            # Archive summary to parent
            summary = self.generate_summary()
            self.parent.archive_child_run(self.instance_id, summary)
            
            # Delete ephemeral data
            self.storage.delete_all()
            
            # Unregister from parent
            self.parent.unregister_child(self.instance_id)
```

### Discovery
```python
# List all hopper instances
hopper_instances = Hopper.list_all_instances()

# Output:
[
    {
        "instance_id": "hopper-global",
        "scope": "global",
        "status": "running",
        "tasks": 47,
        "children": ["hopper-czarina", "hopper-sark", "hopper-symposium"]
    },
    {
        "instance_id": "hopper-czarina",
        "scope": "project",
        "parent": "hopper-global",
        "status": "running",
        "tasks": 12,
        "children": ["hopper-czarina-run-abc123"]
    },
    {
        "instance_id": "hopper-czarina-run-abc123",
        "scope": "orchestration",
        "parent": "hopper-czarina",
        "status": "running",
        "tasks": 5,
        "children": ["hopper-czarina-run-abc123-phase-1"]
    }
]
```

---

## CLI for Multi-Instance Management

### Global Operations
```bash
# Add task to global hopper (routes automatically)
hopper add "Implement feature X" --tags security,mcp

# Add task to specific project
hopper add "Fix bug" --project czarina

# List all instances
hopper instances list

# View instance tree
hopper instances tree
```

### Project Operations
```bash
# Add task to project hopper
hopper add "Task" --instance hopper-czarina

# View project tasks
hopper list --instance hopper-czarina

# View project stats
hopper stats --instance hopper-czarina
```

### Orchestration Operations
```bash
# View running orchestrations
hopper instances list --scope orchestration

# View orchestration progress
hopper status --instance hopper-czarina-run-abc123

# View phase breakdown
hopper tasks --instance hopper-czarina-run-abc123 --hierarchy
```

---

## Integration with Czarina

### Czarina v0.6.0: Uses Orchestration Hopper
```python
# Czarina imports and uses hopper package
from hopper import Hopper, HopperScope

class CzarinaOrchestrator:
    def __init__(self):
        # Project hopper (optional)
        self.project_hopper = Hopper(
            scope=HopperScope.PROJECT,
            instance_id="hopper-czarina"
        )
    
    def orchestrate(self, task: Task):
        # Create orchestration hopper for this run
        self.run_hopper = Hopper(
            scope=HopperScope.ORCHESTRATION,
            instance_id=f"hopper-czarina-run-{self.run_id}",
            parent=self.project_hopper
        )
        
        # Use hopper for task management
        self.run_hopper.add_task(task)
        
        # Workers pull from hopper
        while not self.run_hopper.is_empty():
            task = self.run_hopper.get_next(executor=worker.name)
            worker.execute(task)
            self.run_hopper.complete(task.id)
```

### Czarina v0.7.0: Integrates with Global Hopper
```python
# Czarina registers with global hopper
class CzarinaHopperIntegration:
    def __init__(self, global_hopper_url: str):
        self.global_hopper = HopperClient(global_hopper_url)
        
        # Register Czarina as project executor
        self.global_hopper.register_project(
            name="czarina",
            capabilities=["orchestration", "multi-agent", "code-generation"],
            webhook_url="http://localhost:5001/hopper/task"
        )
        
        # Create project hopper as child of global
        self.project_hopper = self.global_hopper.get_child_hopper("czarina")
    
    def handle_task_from_global(self, task: Task):
        """Receive task from global hopper"""
        
        # Add to project hopper
        self.project_hopper.add_task(task)
        
        # Decide how to handle
        if self._needs_orchestration(task):
            self.orchestrate(task)
        else:
            self.assign_to_human(task)
```

---

## Benefits of Multi-Instance Architecture

### 1. Separation of Concerns
```
Global Hopper:     "What should be worked on?"
Project Hopper:    "How should we execute this?"
Orchestration:     "Who does which part?"

Each level handles appropriate abstraction
No single queue doing everything
Clean boundaries and responsibilities
```

### 2. Appropriate Configuration Per Scope
```
Global:           Expensive LLM routing, full learning
Project:          Simple rules, minimal overhead
Orchestration:    Just priority queue, ephemeral

Right tool for the job at each level
No over-engineering where simple works
No under-engineering where complexity needed
```

### 3. Scalability
```
Global Hopper:        1 instance
Project Hoppers:      N instances (one per project)
Orchestration:        M instances (active runs)
Total:                1 + N + M instances

Each instance:
- Independent configuration
- Isolated data
- Can scale separately
- Can be distributed
```

### 4. Unified Tooling
```
Same code:            hopper package
Same API:             add_task(), get_next(), complete()
Same CLI:             hopper [command] --instance [id]
Same monitoring:      Same metrics, logs, dashboards
Same deployment:      Same containers, configs

Learn once, use everywhere
Reduces maintenance burden
Consistent behavior across scopes
```

### 5. Natural Hierarchy
```
Work flows naturally through hierarchy:
├─ Strategic (global) → Tactical (project) → Execution (orchestration)
├─ Parent delegates to children
├─ Children notify parents on completion
├─ Feedback aggregates up hierarchy
└─ Learning happens at appropriate level

Mirrors how humans organize work
Intuitive mental model
Self-documenting structure
```

---

## Implementation Notes

### Database Schema for Multi-Instance
```sql
-- Instance registry
CREATE TABLE hopper_instances (
    instance_id VARCHAR(100) PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,
    parent_instance_id VARCHAR(100),
    config JSONB,
    status VARCHAR(50),
    created_at TIMESTAMP,
    
    FOREIGN KEY (parent_instance_id) 
        REFERENCES hopper_instances(instance_id)
);

-- Tasks reference instance
CREATE TABLE tasks (
    id VARCHAR(50) PRIMARY KEY,
    instance_id VARCHAR(100) NOT NULL,
    parent_task_id VARCHAR(50),  -- If delegated from parent
    -- ... other task fields
    
    FOREIGN KEY (instance_id) 
        REFERENCES hopper_instances(instance_id)
);

-- Delegations track parent→child task relationships
CREATE TABLE task_delegations (
    parent_instance_id VARCHAR(100),
    parent_task_id VARCHAR(50),
    child_instance_id VARCHAR(100),
    child_task_id VARCHAR(50),
    delegated_at TIMESTAMP,
    
    PRIMARY KEY (parent_instance_id, parent_task_id)
);
```

### Instance Discovery
```python
class Hopper:
    @classmethod
    def global_instance(cls) -> 'Hopper':
        """Get the global hopper instance"""
        return cls.get_instance("hopper-global")
    
    @classmethod
    def get_instance(cls, instance_id: str) -> 'Hopper':
        """Get any hopper instance by ID"""
        # Load from registry
        config = cls._load_instance_config(instance_id)
        return cls(**config)
    
    @classmethod
    def list_instances(
        cls,
        scope: Optional[HopperScope] = None,
        parent: Optional[str] = None
    ) -> List['Hopper']:
        """List all hopper instances"""
        # Query registry
        return cls._query_instances(scope=scope, parent=parent)
```

---

## Migration Path

### Phase 1: Build Core Multi-Instance Support (Week 1-2)
```python
# Core hopper with instance support
from hopper import Hopper, HopperScope

# Works at any scope
hopper = Hopper(scope=HopperScope.ORCHESTRATION)
```

### Phase 2: Czarina v0.6.0 Uses Orchestration Hopper (Week 3)
```python
# Czarina uses hopper for orchestration
run_hopper = Hopper(
    scope=HopperScope.ORCHESTRATION,
    instance_id=f"czarina-run-{run_id}"
)
```

### Phase 3: Deploy Global Hopper (Week 4-5)
```bash
# Deploy global hopper as service
hopper serve --config global_hopper.yaml
```

### Phase 4: Czarina v0.7.0 Integrates (Week 6)
```python
# Czarina registers with global hopper
czarina.register_with_hopper("http://localhost:8080")
```

---

## Summary

**Hopper is a multi-instance hierarchical task queue:**

- ✅ Same codebase works at multiple scopes
- ✅ Instances form parent-child hierarchies
- ✅ Tasks flow down, feedback flows up
- ✅ Configuration varies by scope
- ✅ Unified API across all levels
- ✅ Natural separation of concerns
- ✅ Scales from single orchestration to global routing

**It's Hoppers all the way down.**

From strategic cross-project routing at the top, through project task management in the middle, down to tactical worker coordination at the bottom, the same Hopper architecture provides consistent task management at every level.

**This is not awkward. This is elegant.**

---

**END OF ADDENDUM**