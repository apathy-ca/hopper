# Hopper Local Storage Specification

## Overview

Local mode uses markdown files with YAML frontmatter for human-readable, git-friendly storage. No database required.

## Directory Structure

```
~/.hopper/                          # Default location
├── config.yaml                     # Local configuration
├── tasks/
│   ├── task-abc123.md
│   └── task-def456.md
├── memory/
│   ├── episodes/
│   │   ├── 2024-01-15.md          # Daily episode log
│   │   └── 2024-01-16.md
│   └── patterns/
│       ├── api-python.md
│       └── frontend-react.md
├── feedback/
│   └── task-abc123.md              # Feedback per task
└── .index/                         # Generated indexes (gitignore)
    ├── tasks.json                  # Task index for fast lookup
    └── tags.json                   # Tag index
```

For embedded mode in a project:

```
myproject/
├── .hopper/                        # Project-local hopper
│   ├── tasks/
│   ├── memory/
│   └── config.yaml
└── src/
```

## File Formats

### Task File

`tasks/task-abc123.md`:

```markdown
---
id: task-abc123
title: Fix authentication bug
status: pending
priority: high
tags:
  - api
  - auth
  - bug
project: backend
instance: local
source: cli
depends_on: []
created_at: 2024-01-15T10:30:00Z
updated_at: 2024-01-15T14:20:00Z
---

## Description

Users are getting 401 errors when their JWT expires during an active session.

## Notes

- Checked the token refresh logic
- Issue might be in the middleware

## Checklist

- [ ] Reproduce the issue
- [x] Check token expiry handling
- [ ] Fix and test
```

### Episode File

`memory/episodes/2024-01-15.md`:

```markdown
---
date: 2024-01-15
total_episodes: 5
successful: 4
failed: 1
---

## Episodes

### 10:30 - task-abc123

- **Chosen:** local
- **Confidence:** 0.75
- **Strategy:** rules
- **Outcome:** pending
- **Factors:**
  - tags: api, auth
  - priority: high

### 11:45 - task-def456

- **Chosen:** local
- **Confidence:** 0.85
- **Strategy:** pattern
- **Pattern:** api-python
- **Outcome:** success
- **Duration:** 45m
```

### Pattern File

`memory/patterns/api-python.md`:

```markdown
---
id: pat-abc123
name: api-python
description: Routes Python API tasks locally
pattern_type: tag
target_instance: local
confidence: 0.82
usage_count: 15
success_count: 13
failure_count: 2
is_active: true
created_at: 2024-01-10T00:00:00Z
last_used_at: 2024-01-15T11:45:00Z
---

## Criteria

### Required Tags
- api
- python

### Optional Tags
- backend
- rest

### Keywords
- endpoint
- route
- handler

## History

| Date | Task | Outcome |
|------|------|---------|
| 2024-01-15 | task-def456 | success |
| 2024-01-14 | task-xyz789 | success |
| 2024-01-13 | task-uvw012 | failure |
```

### Feedback File

`feedback/task-abc123.md`:

```markdown
---
task_id: task-abc123
was_good_match: true
quality_score: 4.5
complexity_rating: 3
required_rework: false
created_at: 2024-01-15T16:00:00Z
---

## Routing Feedback

Good routing decision. Task was appropriate for local handling.

## Notes

Took longer than expected due to unclear requirements initially.
```

### Config File

`config.yaml`:

```yaml
# Hopper local configuration
instance:
  id: local-macbook-dev
  name: Local Development
  scope: personal

storage:
  type: markdown
  path: ~/.hopper  # or .hopper for project-local

sync:
  enabled: false
  server_url: null
  # When enabled:
  # server_url: https://hopper.example.com
  # api_key: xxx
  # sync_patterns: true
  # sync_episodes: false  # Privacy: don't sync task details

defaults:
  priority: medium
  status: pending

ui:
  editor: $EDITOR
  date_format: "%Y-%m-%d"
```

## Index Files

Generated indexes for fast lookups (in `.index/`, gitignored):

`tasks.json`:

```json
{
  "tasks": {
    "task-abc123": {
      "title": "Fix authentication bug",
      "status": "pending",
      "priority": "high",
      "tags": ["api", "auth", "bug"],
      "file": "tasks/task-abc123.md",
      "updated_at": "2024-01-15T14:20:00Z"
    }
  },
  "by_status": {
    "pending": ["task-abc123"],
    "done": ["task-def456"]
  },
  "by_tag": {
    "api": ["task-abc123", "task-def456"],
    "auth": ["task-abc123"]
  },
  "generated_at": "2024-01-15T16:00:00Z"
}
```

## Implementation

### Storage Interface

```python
from abc import ABC, abstractmethod
from pathlib import Path

class StorageBackend(ABC):
    """Abstract storage backend."""

    @abstractmethod
    def get_task(self, task_id: str) -> Task | None: ...

    @abstractmethod
    def save_task(self, task: Task) -> None: ...

    @abstractmethod
    def delete_task(self, task_id: str) -> None: ...

    @abstractmethod
    def list_tasks(self, **filters) -> list[Task]: ...

    @abstractmethod
    def search_tasks(self, query: str) -> list[Task]: ...


class MarkdownStorage(StorageBackend):
    """Markdown file storage backend."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.tasks_path = base_path / "tasks"
        self.memory_path = base_path / "memory"
        self.feedback_path = base_path / "feedback"
        self.index_path = base_path / ".index"

        # Ensure directories exist
        for path in [self.tasks_path, self.memory_path,
                     self.feedback_path, self.index_path]:
            path.mkdir(parents=True, exist_ok=True)

        # Load or build index
        self._index = self._load_index()
```

### Markdown Parsing

```python
import yaml
import re
from dataclasses import dataclass

@dataclass
class MarkdownDocument:
    """Parsed markdown with frontmatter."""
    frontmatter: dict
    content: str

def parse_markdown(text: str) -> MarkdownDocument:
    """Parse markdown with YAML frontmatter."""
    pattern = r'^---\n(.*?)\n---\n(.*)$'
    match = re.match(pattern, text, re.DOTALL)

    if match:
        frontmatter = yaml.safe_load(match.group(1))
        content = match.group(2).strip()
    else:
        frontmatter = {}
        content = text.strip()

    return MarkdownDocument(frontmatter=frontmatter, content=content)

def render_markdown(doc: MarkdownDocument) -> str:
    """Render document to markdown string."""
    frontmatter_str = yaml.dump(doc.frontmatter, default_flow_style=False)
    return f"---\n{frontmatter_str}---\n\n{doc.content}"
```

### Task Operations

```python
class TaskMarkdownStore:
    """Task storage using markdown files."""

    def __init__(self, storage: MarkdownStorage):
        self.storage = storage

    def get(self, task_id: str) -> Task | None:
        """Load task from markdown file."""
        file_path = self.storage.tasks_path / f"{task_id}.md"

        if not file_path.exists():
            return None

        doc = parse_markdown(file_path.read_text())

        return Task(
            id=doc.frontmatter["id"],
            title=doc.frontmatter["title"],
            description=doc.content,
            status=TaskStatus(doc.frontmatter["status"]),
            priority=doc.frontmatter.get("priority"),
            tags={t: True for t in doc.frontmatter.get("tags", [])},
            project=doc.frontmatter.get("project"),
            created_at=doc.frontmatter.get("created_at"),
            updated_at=doc.frontmatter.get("updated_at"),
        )

    def save(self, task: Task) -> None:
        """Save task to markdown file."""
        doc = MarkdownDocument(
            frontmatter={
                "id": task.id,
                "title": task.title,
                "status": task.status.value,
                "priority": task.priority,
                "tags": list(task.tags.keys()) if task.tags else [],
                "project": task.project,
                "instance": "local",
                "source": task.source or "cli",
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": datetime.utcnow().isoformat(),
            },
            content=task.description or "",
        )

        file_path = self.storage.tasks_path / f"{task.id}.md"
        file_path.write_text(render_markdown(doc))

        # Update index
        self.storage.update_index(task)

    def list(self, **filters) -> list[Task]:
        """List tasks using index."""
        index = self.storage.get_index()

        task_ids = set(index["tasks"].keys())

        # Apply filters using index
        if "status" in filters:
            task_ids &= set(index["by_status"].get(filters["status"], []))

        if "tags" in filters:
            for tag in filters["tags"]:
                task_ids &= set(index["by_tag"].get(tag, []))

        # Load matching tasks
        return [self.get(tid) for tid in task_ids if self.get(tid)]

    def search(self, query: str) -> list[Task]:
        """Full-text search across tasks."""
        query_lower = query.lower()
        results = []

        for task_file in self.storage.tasks_path.glob("*.md"):
            content = task_file.read_text().lower()
            if query_lower in content:
                task = self.get(task_file.stem)
                if task:
                    results.append(task)

        return results
```

## CLI Integration

```python
# hopper/cli/storage.py

from pathlib import Path
from hopper.storage.markdown import MarkdownStorage

def get_storage() -> StorageBackend:
    """Get appropriate storage backend."""

    # Check for project-local .hopper
    project_local = Path.cwd() / ".hopper"
    if project_local.exists():
        return MarkdownStorage(project_local)

    # Check for user-local ~/.hopper
    user_local = Path.home() / ".hopper"
    if user_local.exists():
        return MarkdownStorage(user_local)

    # Check for server mode (config has server_url)
    config = load_config()
    if config.server_url:
        return ServerStorage(config.server_url, config.api_key)

    # Default: create ~/.hopper
    user_local.mkdir(parents=True, exist_ok=True)
    return MarkdownStorage(user_local)
```

```python
# hopper/cli/main.py

@cli.command()
@click.option("--local", is_flag=True, help="Force local storage mode")
@click.pass_context
def task_add(ctx, local: bool, ...):
    """Add a task."""
    if local or ctx.obj.storage_mode == "local":
        storage = get_local_storage()
        store = TaskMarkdownStore(storage)
        store.save(task)
    else:
        # Use HTTP client
        client.create_task(task_data)
```

## Features

### Human-Editable

Tasks can be edited directly:

```bash
$EDITOR ~/.hopper/tasks/task-abc123.md
```

### Git-Friendly

```bash
cd ~/.hopper
git init
git add -A
git commit -m "Add task: Fix auth bug"
```

### Portable

```bash
# Copy hopper data to new machine
rsync -av ~/.hopper/ newmachine:~/.hopper/
```

### Project-Local

```bash
cd myproject
hopper init  # Creates .hopper/
hopper add "Implement feature X"  # Stored in .hopper/tasks/
```

## Migration

### From Server to Local

```bash
hopper export --format markdown --output ~/.hopper/
```

### From Local to Server

```bash
hopper sync --to-server
# Or one-time push:
hopper push --all
```

## Limitations

- **No concurrent access** - Single user assumed
- **No ACID transactions** - File operations aren't atomic
- **Limited query performance** - Full scan for complex queries
- **Index staleness** - External edits need `hopper reindex`

These are acceptable for local/embedded use cases.
