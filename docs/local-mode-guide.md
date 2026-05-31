# Local Mode Guide

Hopper supports a fully local mode that stores all data as human-readable markdown files. This is ideal for personal use, embedded project configurations, and offline workflows.

## Quick Start

```bash
# Use local mode explicitly
hopper task add "Fix the login bug"
hopper task list

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
hopper init  # Initialize the directory structure
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
hopper task add "New task" -p high -t bug
hopper task list --status pending
hopper task get task-abc123
hopper task update task-abc123 --add-tag urgent
hopper task status task-abc123 completed
hopper task delete task-abc123

# Search
hopper task search "login"

# Learning system
hopper learning feedback submit task-abc123 --good
hopper learning pattern list
hopper learning stats
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
hopper -v task list
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

## Server Sync (Upstream)

Local instances sync tasks (and other records) to a Hopper server through the
**upstream** subsystem — a DID-authenticated record/revision exchange. This is
configured via the `upstream:` mechanism, **not** any `sync:` block in
`config.yaml`:

```bash
hopper upstream init --server https://hopper.example.com  # generate DID + set server
hopper sync                                               # push/pull with the server
hopper sync status                                        # show the REAL sync state
```

`hopper sync status` is the source of truth: it reports the configured upstream
server, your DID, and the last-sync time read from
`.hopper/.sync_state_<instance_id>`.

> **Note:** older configs may contain a legacy `sync:` block
> (`enabled`/`server_url`/`sync_patterns`/`sync_episodes`). That block configured
> the old learning-engine and **never** controlled server sync — it is no longer
> written on `hopper init` and can be ignored or removed. Use `hopper sync status`
> to see whether server sync is actually configured.

Upstream sync enables:
- Task/record sharing across instances and agents
- DID-attributed, cross-agent knowledge
- Backup of your task and memory records

## Git Integration

The `.index/` directory is automatically gitignored. Task and pattern files are designed to be git-friendly:

- Human-readable diffs
- Merge-friendly YAML frontmatter
- Meaningful filenames (task IDs)

Add `.hopper` to your project's `.gitignore` if you don't want to track tasks in version control, or commit it to share project-specific patterns and configurations.

---

## Czarina Integration

[Czarina](https://github.com/apathy-ca/czarina) uses Hopper local mode as its
persistent instruction store and lesson system for multi-agent orchestrations.

### How Czarina uses local mode

Czarina uses local mode (the default). It uses project-embedded `.hopper/` when
available (auto-detected), falling back to `~/.hopper/` globally.

**Full brief storage:**

Czarina stores each worker's complete task brief as the Hopper task body using
the `--brief-file` flag:

```bash
hopper task add "[backend] Build the REST API" \
  --brief-file .czarina/workers/backend.md \
  --tag czarina --tag my-project --tag worker-backend --tag role-code \
  --priority high \
  --non-interactive
```

**Brief retrieval with lessons:**

Workers retrieve their full brief (with any relevant lessons prepended) using:

```bash
hopper task get task-abc12345 --with-lessons
```

The `--with-lessons` flag queries the lesson store for high-confidence lessons
matching the task's project and domain, and appends a `## Relevant Lessons`
section to the output.

**Lesson filing:**

Workers file lessons on completion:

```bash
hopper lesson add \
  --task task-abc12345 \
  --title "SQLAlchemy async sessions are not thread-safe" \
  --domain python \
  --confidence high \
  --non-interactive \
  --body "..."
```

**Non-interactive mode:**

Czarina always passes `--non-interactive` to suppress prompts for scripted use.
All required fields are passed as flags.

### Czarina tag conventions

| Tag | Meaning |
|-----|---------|
| `czarina` | All Czarina-managed tasks |
| `<project-slug>` | Project identifier (e.g., `my-api`) |
| `worker-<id>` | Worker identifier (e.g., `worker-backend`) |
| `role-<role>` | Worker role (e.g., `role-code`, `role-qa`) |
| `phase-<n>` | Phase number (on project task) |

These tags allow querying at any granularity:

```bash
hopper task list --tag czarina               # All Czarina tasks
hopper task list --tag my-api                # All tasks for a project
hopper task list --tag worker-backend        # One worker's tasks
hopper lesson list --project my-api          # All lessons for a project
```

### Task ID persistence

Czarina persists all Hopper task IDs in `.czarina/hopper-tasks.json`:

```json
{
  "project_task_id": "task-abc12345",
  "workers": {
    "backend": "task-def67890",
    "qa": "task-ghi11121"
  }
}
```

This allows `czarina status` and `czarina closeout` to look up task IDs without
querying Hopper by tag.

See [Czarina docs/HOPPER.md](https://github.com/apathy-ca/czarina/docs/HOPPER.md)
for the complete integration guide.
