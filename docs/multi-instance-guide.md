# Multi-Instance Guide

This guide covers Hopper's hierarchical multi-instance architecture introduced in Phase 2.

## Overview

Hopper uses a hierarchical instance architecture where tasks flow down through levels of specialization:

```
Global Hopper (GLOBAL)
├── Strategic routing across all projects
│
├── Project Hopper: webapp (PROJECT)
│   ├── Project-level task management
│   │
│   └── Orchestration: webapp-worker-1 (ORCHESTRATION)
│       └── Task execution
│
└── Project Hopper: api-backend (PROJECT)
    ├── Orchestration: api-worker-1 (ORCHESTRATION)
    └── Orchestration: api-worker-2 (ORCHESTRATION)
```

## Instance Scopes

### GLOBAL Scope
- **Purpose**: Strategic routing across all projects
- **Behavior**: Routes tasks to appropriate PROJECT instances
- **Never**: Executes tasks directly
- **Typical Count**: 1 per Hopper deployment

### PROJECT Scope
- **Purpose**: Project-level task management
- **Behavior**: Decides whether to handle tasks directly or delegate to ORCHESTRATION
- **Can**: Execute simple tasks, delegate complex ones
- **Typical Count**: 1 per project/domain

### ORCHESTRATION Scope
- **Purpose**: Task execution and worker queue management
- **Behavior**: Queues and executes tasks, reports completion
- **Never**: Delegates further
- **Typical Count**: 1+ per project (scales with workload)

## Task Flow

### 1. Task Creation
Tasks can enter the system at any level:

```bash
# Create at global level (will be routed)
hopper task add "Build user dashboard" --instance global-hopper

# Create at project level (may delegate to orchestration)
hopper task add "Fix login bug" --instance webapp-project

# Create at orchestration level (will execute directly)
hopper task add "Run tests" --instance webapp-worker-1
```

### 2. Routing Down
Tasks flow down based on scope behaviors:

```
Task: "Implement OAuth"
    │
    ▼
GLOBAL: "This is a webapp task" → delegate to webapp-project
    │
    ▼
PROJECT: "Complex task, needs orchestration" → delegate to webapp-worker-1
    │
    ▼
ORCHESTRATION: Queue for execution
```

### 3. Execution
At the ORCHESTRATION level:
- Tasks enter the execution queue
- Queue is ordered by priority (urgent > high > medium > low)
- Workers claim and execute tasks
- Capacity limits prevent overload

### 4. Completion Bubbling
When a task completes, status bubbles back up:

```
ORCHESTRATION: Task completed ✓
    │
    ▼
PROJECT: Delegation completed ✓
    │
    ▼
GLOBAL: Delegation completed ✓
```

## API Reference

### Instance Endpoints

```bash
# List all instances
GET /api/v1/instances

# Get instance details
GET /api/v1/instances/{id}

# Create instance
POST /api/v1/instances
{
  "name": "webapp-project",
  "scope": "PROJECT",
  "parent_id": "global-hopper-id",
  "config": {
    "capabilities": ["python", "fastapi"],
    "max_concurrent_tasks": 5
  }
}

# Get children
GET /api/v1/instances/{id}/children

# Get full hierarchy
GET /api/v1/instances/{id}/hierarchy

# Lifecycle operations
POST /api/v1/instances/{id}/start
POST /api/v1/instances/{id}/stop
POST /api/v1/instances/{id}/pause
POST /api/v1/instances/{id}/resume
```

### Delegation Endpoints

```bash
# Delegate a task
POST /api/v1/tasks/{task_id}/delegate
{
  "target_instance_id": "webapp-worker-1",
  "delegation_type": "route",
  "notes": "Routing to worker for execution"
}

# Accept delegation
POST /api/v1/delegations/{id}/accept

# Reject delegation
POST /api/v1/delegations/{id}/reject
{
  "reason": "Instance at capacity"
}

# Complete delegation
POST /api/v1/delegations/{id}/complete
{
  "result": {"output": "Task completed successfully"}
}

# Get delegation chain
GET /api/v1/tasks/{task_id}/delegations
```

## CLI Reference

### Instance Commands

```bash
# List instances
hopper instance list
hopper instance list --scope project
hopper instance list --status running

# Show hierarchy tree
hopper instance tree

# Create instance
hopper instance create "my-project" \
  --scope project \
  --parent global-id \
  --config '{"capabilities": ["python"]}'

# Show instance details
hopper instance show <instance-id>

# Lifecycle
hopper instance start <instance-id>
hopper instance stop <instance-id>
hopper instance pause <instance-id>
hopper instance resume <instance-id>
```

### Delegation Commands

```bash
# Delegate a task
hopper task delegate <task-id> --to <instance-id>
hopper task delegate <task-id> --to <instance-id> --type decompose

# View delegation chain
hopper task delegations <task-id>
```

## Delegation Types

| Type | Description | Use Case |
|------|-------------|----------|
| `route` | Standard routing to child instance | Normal task flow |
| `decompose` | Break into subtasks | Complex tasks |
| `escalate` | Return to parent instance | Task too complex |
| `reassign` | Move to sibling instance | Load balancing |

## Scope Behaviors

### Global Scope Behavior
- Always delegates (never handles directly)
- Routes based on:
  - Explicit project assignment in task
  - Task tags matching project capabilities
  - Task content matching project domains
  - Load balancing among projects

### Project Scope Behavior
- Decides: handle directly OR delegate to orchestration
- Criteria for delegation:
  - Task complexity (description length, tags, dependencies)
  - Priority level
  - Available orchestration instances
- Can handle simple tasks directly

### Orchestration Scope Behavior
- Queues tasks for execution
- Manages worker capacity
- Never delegates further
- Reports completion to parent

## Configuration

### Instance Configuration

```python
# In instance.config (JSONB field)
{
    # Capabilities (for routing decisions)
    "capabilities": ["python", "fastapi", "testing"],

    # Capacity limits
    "max_concurrent_tasks": 10,

    # Routing behavior
    "auto_delegate": true,
    "orchestration_threshold": 3,  # Complexity threshold

    # Routing engine
    "routing_engine": "rules",
    "llm_fallback": true
}
```

### Instance Status Lifecycle

```
CREATED → STARTING → RUNNING → STOPPING → STOPPED
                  ↓         ↑
               PAUSED ──────┘

Any state → ERROR → RUNNING (recovery)
Any state → TERMINATED (final)
```

## Best Practices

### 1. Start Simple
Begin with a single Global + Project setup. Add orchestration instances as workload grows.

### 2. Use Capabilities for Routing
Define clear capabilities on PROJECT instances to enable automatic routing:

```python
# webapp-project config
{"capabilities": ["python", "fastapi", "frontend", "react"]}

# api-project config
{"capabilities": ["python", "fastapi", "database", "postgresql"]}
```

### 3. Set Appropriate Capacity
Limit concurrent tasks to prevent overload:

```python
# High-throughput worker
{"max_concurrent_tasks": 20}

# Resource-intensive worker
{"max_concurrent_tasks": 3}
```

### 4. Monitor Delegation Chains
Use `hopper task delegations <id>` to trace task routing and identify bottlenecks.

### 5. Handle Rejections Gracefully
When an instance rejects a delegation, the task returns to the source. Design routing to have fallback options.

## Troubleshooting

### Task Stuck at Global
- Check if PROJECT instances exist and are running
- Verify PROJECT capabilities match task tags
- Check delegation rejection logs

### Delegation Rejected
- Instance may be at capacity
- Instance may be stopped/paused
- Task type may not match instance capabilities

### Completion Not Bubbling
- Check all delegations in chain are accepted
- Verify task status is actually DONE
- Check for errors in delegation chain

## Example: Full Workflow

```bash
# 1. Create hierarchy
hopper instance create "global" --scope global
hopper instance create "webapp" --scope project --parent global-id
hopper instance create "worker-1" --scope orchestration --parent webapp-id

# 2. Start instances
hopper instance start global-id
hopper instance start webapp-id
hopper instance start worker-1-id

# 3. Create task at global level
hopper task add "Build login page" -t frontend -t react --instance global-id

# 4. Watch it flow down
hopper instance tree
# global (GLOBAL) [running]
# └── webapp (PROJECT) [running]
#     └── worker-1 (ORCHESTRATION) [running] - 1 task

# 5. Check delegation chain
hopper task delegations <task-id>
# 1. global → webapp (route) [accepted]
# 2. webapp → worker-1 (route) [accepted]

# 6. Complete the task
hopper task status <task-id> completed

# 7. Verify completion bubbled
hopper task delegations <task-id>
# 1. global → webapp (route) [completed]
# 2. webapp → worker-1 (route) [completed]
```
