# Local Mode Guide

Hopper supports a fully local mode that stores all data as human-readable markdown files. This is ideal for personal use, embedded project configurations, and offline workflows.

## Quick Start

```bash
# Use local mode explicitly
hopper --local task add "Fix the login bug"
hopper --local task list

# Or set your profile to local mode
hopper config set mode local
```

## Storage Locations

Local mode supports two storage locations:

### 1. Global Local Storage (~/.hopper)

Default location for personal task management:

```
~/.hopper/
├── config.yaml          # Instance configuration
├── tasks/               # Task markdown files
│   └── task-abc123.md
├── memory/
│   ├── episodes/        # Routing decision history
│   │   └── 2024-01-15.md
│   └── patterns/        # Learned routing patterns
│       └── pat-xyz789.md
├── feedback/            # Routing feedback
│   └── task-abc123.md
└── .index/              # JSON index (gitignored)
    └── tasks.json
```

### 2. Embedded Project Storage (.hopper)

For project-specific task management, create a `.hopper` directory in your project root:

```bash
mkdir .hopper
hopper --local init  # Initialize the directory structure
```

Hopper auto-detects embedded storage when you run commands from within the project.

## File Formats

### Task Files

Tasks are stored as markdown with YAML frontmatter:

```markdown
---
id: task-abc12345
title: Fix login bug
status: pending
priority: high
tags:
  - bug
  - auth
project: hopper
instance: local
source: cli
created_at: '2024-01-15T10:30:00'
updated_at: '2024-01-15T10:30:00'
---

The login form throws an error when the password contains special characters.

## Steps to reproduce
1. Go to /login
2. Enter email: test@example.com
3. Enter password: p@ss!word
4. Click submit

## Expected
User should be logged in

## Actual
Error: "Invalid credentials"
```

### Pattern Files

Routing patterns are also markdown:

```markdown
---
id: pat-xyz78901
name: API Tasks
pattern_type: tag
target_instance: api-worker
tag_criteria:
  required:
    - api
    - python
confidence: 0.85
usage_count: 42
success_count: 38
is_active: true
---

Routes tasks tagged with 'api' and 'python' to the API worker instance.
```

### Episode Files

Episodes are grouped by day:

```markdown
---
date: '2024-01-15'
episodes:
  - id: ep-001
    task_id: task-abc123
    chosen_instance: api-worker
    confidence: 0.85
    strategy: pattern
    pattern_id: pat-xyz789
    outcome_success: true
    routed_at: '2024-01-15T10:30:00'
    completed_at: '2024-01-15T11:45:00'
---
```

## CLI Commands

All standard Hopper commands work in local mode:

```bash
# Task management
hopper --local task add "New task" -p high -t bug
hopper --local task list --status pending
hopper --local task get task-abc123
hopper --local task update task-abc123 --add-tag urgent
hopper --local task status task-abc123 completed
hopper --local task delete task-abc123

# Search
hopper --local task search "login"

# Learning system
hopper --local learning feedback submit task-abc123 --good
hopper --local learning pattern list
hopper --local learning stats
```

## Configuration

### Setting Default Mode

Edit `~/.hopper/config.yaml`:

```yaml
active_profile: default
profiles:
  default:
    mode: local  # or 'server'
    api:
      endpoint: http://localhost:8000
      timeout: 30
    local:
      path: /home/user/.hopper
      auto_detect_embedded: true
```

### Auto-Detection

When `auto_detect_embedded` is true (default), Hopper searches for a `.hopper` directory in the current directory and parent directories (up to 10 levels). If found, it uses that for storage.

## Verbose Mode

See which storage is being used:

```bash
hopper --local -v task list
# Output:
# Hopper v0.1.0
# Config: /home/user/.hopper/config.yaml
# Mode: local (/home/user/.hopper)
# ...
```

## Limitations

Local mode has some limitations compared to server mode:

- **No delegation**: Task delegation between instances is not supported
- **No real-time sync**: Changes are local only
- **No multi-user**: Single-user access only
- **No vector search**: Pattern matching uses keyword-based search

## Northbound Sync (Future)

Local instances can optionally sync patterns and anonymized statistics to a server instance:

```yaml
sync:
  enabled: true
  server_url: https://hopper.example.com
  sync_patterns: true
  sync_episodes: false  # Privacy: off by default
```

This enables:
- Pattern aggregation across instances
- Global learning improvements
- Backup of routing intelligence

## Git Integration

The `.index/` directory is automatically gitignored. Task and pattern files are designed to be git-friendly:

- Human-readable diffs
- Merge-friendly YAML frontmatter
- Meaningful filenames (task IDs)

Add `.hopper` to your project's `.gitignore` if you don't want to track tasks in version control, or commit it to share project-specific patterns and configurations.
