---
title: Hopper Usage Guide
type: built-in
scope: tool-usage
---

# Hopper - Persistent Memory for AI Agents

Hopper is your long-term memory system. Use it to persist notes, track tasks, record feedback, and maintain context across sessions.

## Quick Reference

### Adding Items

```bash
# Add a task
hopper task add "Implement feature X" --priority high

# Add a learning/note
hopper task add "Architecture: Using event sourcing" --tag learning

# Add feedback
hopper task add "Test-first approach worked well" --tag feedback
```

### Using the /hopper Skill (Claude Code)

```
/hopper add "Remember: user prefers TypeScript"
/hopper add "TODO: Refactor auth module" --priority high
/hopper list
/hopper done <task-id>
```

### Listing & Filtering

```bash
hopper task list                    # All open tasks
hopper task list --status completed # Completed items
hopper task list --tag learning     # Filter by tag
hopper task list --priority high    # Filter by priority
```

### Context View

```bash
hopper context          # Show recent learnings + open tasks
hopper context --tasks  # Just open tasks
```

### Completing Tasks

```bash
hopper task done <task-id>      # Mark as completed
hopper task update <id> --status in_progress
```

## Best Practices for Agents

### What to Store

1. **Decisions & Rationale**
   - "Architecture: Using Redis for caching because..."
   - "Chose Jest over Vitest due to existing config"

2. **User Preferences**
   - "User prefers: concise responses"
   - "User prefers: TypeScript over JavaScript"

3. **Project Patterns**
   - "Pattern: All API routes use /api/v1 prefix"
   - "Pattern: Tests colocated with source files"

4. **Feedback & Learnings**
   - "What worked: Small incremental PRs"
   - "Issue: CI pipeline is slow, parallelize tests"

5. **Session State**
   - "SESSION: Completed auth refactor, next: testing"
   - "BLOCKED: Waiting for API key from user"

### When to Store

- After making architectural decisions
- When learning user preferences
- After completing significant work
- Before ending a session (handoff notes)
- When discovering project patterns

### Tags to Use

| Tag | Purpose |
|-----|---------|
| `learning` | Knowledge gained |
| `feedback` | What worked/didn't |
| `decision` | Architectural choices |
| `preference` | User preferences |
| `pattern` | Code/project patterns |
| `session` | Session handoff notes |
| `northbound` | Flag for upstream sharing |

## Storage Location

Tasks are stored in `.hopper/tasks/` as markdown files with YAML frontmatter.
Git-friendly and human-readable.

## Adding Hopper to a Project

```bash
cd /path/to/project
hopper init
```

This creates `.hopper/` with:
- `tasks/` - Your tasks and learnings (markdown, commit these)
- `knowledge/` - Agent knowledge synced from GitHub
- `memory/` - Patterns and episodes
- `.index/` - Cache (gitignored, regenerated)

Knowledge is auto-synced from https://github.com/apathy-ca/agent-knowledge based on detected project type.

## Knowledge Commands

```bash
hopper knowledge list      # Show available knowledge
hopper knowledge sync      # Re-sync from GitHub
hopper knowledge show      # Display this file
```

## MCP Server

Hopper can run as an MCP server for direct tool integration:

```bash
hopper mcp serve              # Start MCP server
hopper mcp config --stdout    # Show MCP config for claude_desktop_config.json
```
