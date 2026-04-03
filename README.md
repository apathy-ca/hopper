# Hopper

**Persistent Memory for AI Agents**

Hopper gives AI agents long-term memory. Track tasks, store notes, record feedback, and maintain context across sessions.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/apathy-ca/hopper/master/install.sh | bash
```

Then initialize in your project:

```bash
cd /path/to/your/project
hopper init
```

That's it. You now have a `.hopper/` directory for persistent storage.

<details>
<summary>Manual install</summary>

```bash
git clone https://github.com/apathy-ca/hopper.git
cd hopper
pip install -e .
```
</details>

## For AI Agents (Claude Code)

Add Hopper to any project and AI agents can use `/hopper` to remember things:

```
/hopper add "User prefers TypeScript over JavaScript"
/hopper add "TODO: Refactor auth module" --priority high
/hopper add "FEEDBACK: Small PRs worked well" --tag feedback
/hopper list
```

See [CLAUDE.md](CLAUDE.md) for full agent instructions.

## Usage

### CLI Commands

```bash
# Add tasks
hopper task add "Fix bug" --priority high --tag backend
hopper task add "GPU sweep" --assign "claude:deep-dive" --status in_progress
hopper task add "Subtask" --parent <parent-id>

# List and filter (sorted by status then priority)
hopper task list
hopper task list --status open --priority high
hopper task list --tag gpu --compact

# Update status
hopper task status <task-id> in_progress -f
hopper task status <task-id> completed -f
hopper task status <task-id> in_progress --assign "claude:my-task" -f

# View details (shows child rollup if parent)
hopper task get <task-id>

# Update tasks
hopper task update <task-id> --assign "opencode:refactor"
hopper task update <task-id> --parent <parent-id>
hopper task update <task-id> --unassign --unparent
```

### Multi-Agent Coordination

Hopper tracks which agent is working on what, and whether they're still alive:

```bash
# Assign work with identity (platform:task-name)
hopper task status <id> in_progress --assign "claude:acm-rewrite" -f

# Signal you're still alive (agents should call every 10-15 min)
hopper task heartbeat <task-id>

# Before a long-running job (GPU, data gen), set expected duration
hopper task heartbeat <task-id> --expect 4h

# Find tasks where the agent has gone silent
hopper task stale
hopper task stale --minutes 60
```

The list view shows staleness as a per-character color gradient on the status text — green fading to red as the heartbeat ages. At a glance you can see which agents are healthy and which have gone silent.

### Parent-Child Tasks

```bash
# Create child tasks
hopper task add "Subtask A" --parent <parent-id>
hopper task add "Subtask B" --parent <parent-id>

# View rollup (shows done/total)
hopper task get <parent-id>
hopper task children <parent-id>
```

Parent tasks show `[done/total]` rollup in the list view, and children are grouped under their parent with `└` indentation.

**Task ID prefix matching**: IDs are truncated to 8 chars in display. All commands accept prefix matches — `hopper task get t7232` resolves to the full ID if unambiguous.

### GitHub Integration

```bash
# Authenticate
hopper github auth --token <your-github-token>

# Import issues as tasks
hopper github import owner/repo --all
hopper github import owner/repo --issue 42

# Export task as issue
hopper github export <task-id> --repo owner/repo
```

## Configuration

### Project-Embedded Mode (Recommended)

Run `hopper init` in your project root. Creates `.hopper/` directory:

```
your-project/
├── .hopper/           # Hopper storage (add to .gitignore or commit)
│   ├── tasks/         # Task markdown files
│   └── config.yaml    # Project config
├── CLAUDE.md          # AI agent instructions (copy from hopper repo)
└── ...
```

### Global Mode

Tasks stored in `~/.hopper/` for cross-project use:

```bash
hopper task add "Global task"  # Uses ~/.hopper/
```

### Config File

`~/.hopper/config.yaml` or `.hopper/config.yaml`:

```yaml
active_profile: default
profiles:
  default:
    mode: local  # or "server" for API mode
    github:
      token: ${GITHUB_TOKEN}  # Or hardcode your token
      default_owner: your-org
```

## Adding to Your Project

1. **Initialize Hopper:**
   ```bash
   cd your-project
   hopper init
   ```

2. **Copy AI instructions:**
   ```bash
   cp /path/to/hopper/CLAUDE.md .
   cp -r /path/to/hopper/.claude/skills .claude/
   ```

3. **Start using:**
   ```bash
   hopper task add "First task"
   ```

AI agents working in your project will see CLAUDE.md and know to use `/hopper`.

## How It Works

- Tasks stored as **markdown files** in `.hopper/tasks/`
- Human-readable, git-friendly, version controllable
- No server required for local mode
- Optional API server for multi-user setups

---

## Advanced: Full Feature Set

### Multi-Instance Orchestration

Hierarchical task routing for complex workflows:

```bash
hopper instance create "My Project" --scope project
hopper instance tree
hopper task delegate <task-id> --to <instance-id>
```

### Memory & Learning

AI-powered pattern learning from feedback:

```bash
hopper learning stats
hopper learning feedback submit <task-id> --good
hopper learning suggest
```

### API Server

For multi-user or programmatic access:

```bash
hopper server start
# Visit http://localhost:8000/docs
```

### MCP Server

For Claude Desktop integration:

```json
{
  "mcpServers": {
    "hopper": {
      "command": "hopper",
      "args": ["mcp-server"]
    }
  }
}
```

### Czarina Integration

Hopper is the persistent instruction store and lesson system for
[Czarina](https://github.com/apathy-ca/czarina), a multi-agent orchestration
framework. When a Czarina orchestration launches:

- Each worker's full task brief is stored as a Hopper task body
- Workers retrieve their brief with `hopper task get <id> --with-lessons`
- Workers recover from session crashes with two commands — no orchestrator needed
- Lessons filed by workers are automatically injected into subsequent workers' briefs

Czarina uses local mode (the default). No server required.

**Czarina-specific CLI additions:**

```bash
# Store a full markdown brief as a task body
hopper task add "[worker-id] Title" \
  --brief-file .czarina/workers/backend.md \
  --tag czarina --tag my-project --tag worker-backend \
  --non-interactive

# Retrieve brief with relevant lessons prepended
hopper task get task-abc12345 --with-lessons

# File a lesson for future workers
hopper lesson add \
  --task task-abc12345 \
  --title "What I learned" \
  --domain python \
  --confidence high \
  --non-interactive \
  --body "..."
```

See the [Czarina repository](https://github.com/apathy-ca/czarina) for the full
integration guide.

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=hopper
```

## Project Status

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | ✓ Complete | Core Task Management |
| Phase 2 | ✓ Complete | Multi-Instance Delegation |
| Phase 3 | ✓ Complete | Memory & Learning |
| Phase 5 | ✓ Complete | GitHub Integration |
| Phase 4 | Planned | LLM Routing |
| Phase 6 | Planned | Federation |

**494 tests passing, 60% coverage**

## License

MIT License
