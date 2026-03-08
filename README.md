# Hopper

**Persistent Memory for AI Agents**

Hopper gives AI agents long-term memory. Track tasks, store notes, record feedback, and maintain context across sessions.

## Quick Install

```bash
# Clone and install
git clone https://github.com/apathy-ca/hopper.git
cd hopper
pip install -e .

# Initialize in your project
cd /path/to/your/project
hopper init
```

That's it. You now have a `.hopper/` directory for persistent storage.

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
# Add tasks/notes
hopper --local task add "Remember this for later"
hopper --local task add "Fix bug" --priority high --tag backend

# List and filter
hopper --local task list
hopper --local task list --status open --priority high

# Update status
hopper --local task status <task-id> done
hopper --local task status <task-id> claimed

# View details
hopper --local task get <task-id>
```

### GitHub Integration

```bash
# Authenticate
hopper github auth --token <your-github-token>

# Import issues as tasks
hopper --local github import owner/repo --all
hopper --local github import owner/repo --issue 42

# Export task as issue
hopper --local github export <task-id> --repo owner/repo
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
   hopper --local task add "First task"
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
