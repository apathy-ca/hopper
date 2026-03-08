# Hopper Project Instructions

Hopper is a universal task queue for human-AI collaborative workflows.

## Skills

### /hopper - Task Management

Quick task management from Claude Code.

**Commands:**
- `/hopper add "title"` - Create a task
- `/hopper list` - List tasks
- `/hopper done <id>` - Mark task complete
- `/hopper claim <id>` - Claim a task
- `/hopper get <id>` - View task details
- `/hopper ls` - List open tasks (shortcut)

See `.claude/skills/hopper.md` for full instructions.

## Development

- Run tests: `uv run pytest`
- Run specific tests: `uv run pytest tests/platforms/ -v`
- Start API server: `uv run hopper server start`

## Local Mode

Use `--local` flag or set `mode: local` in config for embedded storage:
```bash
hopper --local task add "My task"
hopper --local task list
```
