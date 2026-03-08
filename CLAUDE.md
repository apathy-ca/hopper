# Hopper - Persistent Memory for AI Agents

Hopper is your **long-term memory system**. Use it to persist notes, track tasks, record feedback, and maintain context across sessions.

## Why Use Hopper?

As an AI agent, your context resets between sessions. Hopper solves this:

- **Remember things** - Store notes, decisions, and learnings
- **Track work** - Tasks persist across conversations
- **Record feedback** - Capture what worked, what didn't
- **Project context** - Maintain project-specific knowledge

## Quick Start: /hopper Skill

Use the `/hopper` skill for fast access:

```
/hopper add "Remember: user prefers TypeScript over JavaScript"
/hopper add "TODO: Refactor auth module" --priority high
/hopper add "FEEDBACK: Test coverage approach worked well" --tag feedback
/hopper list
/hopper done <task-id>
```

See `.claude/skills/hopper.md` for full command reference.

## Use Cases

### Long-term Notes
```
/hopper add "Architecture decision: Using event sourcing for audit trail"
/hopper add "User preference: Always run tests before committing"
```

### Project Feedback
```
/hopper add "What worked: Breaking changes into small PRs" --tag feedback
/hopper add "Issue: CI takes too long, consider parallelization" --tag feedback
```

### Task Tracking
```
/hopper add "Implement caching layer" --priority high --tag backend
/hopper add "Write API documentation" --tag docs
/hopper list --status open
```

### Session Handoff
Before ending a session, record state:
```
/hopper add "SESSION: Completed auth refactor, next step is testing"
```

## Storage

Tasks are stored locally in `.hopper/` as markdown files. They persist across sessions and can be version controlled.

## Full CLI

For advanced usage:
```bash
hopper --local task list
hopper --local task add "Task" --priority high
hopper --local learning suggest  # AI-powered suggestions
hopper --local github import owner/repo --all  # Sync GitHub issues
```

---

**Bottom line**: Whenever you learn something worth remembering, need to track work, or want to leave notes for future sessions - use `/hopper`.
