"""
Knowledge management for Hopper.

Handles built-in hopper-usage knowledge and syncing from external
agent-knowledge repositories.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Any

# Default agent-knowledge source (GitHub repo)
DEFAULT_KNOWLEDGE_SOURCE = "https://github.com/apathy-ca/agent-knowledge.git"

# Cache directory for cloned repos
KNOWLEDGE_CACHE_DIR = Path.home() / ".cache" / "hopper" / "knowledge"

# Built-in hopper usage documentation
HOPPER_USAGE_CONTENT = """---
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
hopper task list                      # All open tasks
hopper task list --status completed   # Completed items
hopper task list --tag learning       # Filter by tag
hopper task list --priority high      # Filter by priority
```

### Context View

```bash
hopper context    # Show recent learnings + open tasks
```

### Completing Tasks

```bash
hopper task status <task-id> completed -f     # Mark as completed
hopper task status <task-id> in_progress -f   # Claim a task
hopper task status <task-id> open -f          # Release a task
hopper task status <task-id> blocked -f       # Mark as blocked
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
"""


AGENTS_MD_VERSION = 2

AGENTS_MD_SECTION = f"""## Hopper - Persistent Memory
<!-- hopper-agent-files: v{AGENTS_MD_VERSION} -->

This project uses [Hopper](https://github.com/apathy-ca/hopper) for persistent memory across AI agent sessions.

**Storage:** `.hopper/` in this directory (tasks, knowledge, memory).

### Quick commands

```bash
hopper task add "Note or task"              # Store something
hopper task list                            # See open tasks
hopper task status <id> in_progress -f     # Claim a task
hopper task status <id> completed -f       # Complete a task
hopper task heartbeat <id>                  # Signal still working
hopper task note <id> "finding: ..."        # Leave an attributed note on any task
hopper context                              # Recent learnings + open tasks
hopper sync                                 # Push/pull with the shared server
```

### Agent identity

Identify yourself with `platform:task-name` when claiming work:
- `opencode:my-task`, `claude:acm-rewrite`, `kilocode:prh-transfer`, `human:james`
- Never use generic names like `main`.
- Set `HOPPER_IDENTITY=platform:you` (or pass `--by`) so records you create are
  attributed to you (`created_by`), not just your machine.

### Notes & attribution

- Leave a finding on a task another agent owns with `hopper task note <id> "..."`.
  Notes are append-only and never overwrite the description, so hand-offs are
  safe; they render in `hopper task get`.
- Every record stamps an immutable `created_by`. Notes and creator both travel
  with the task through `hopper sync` to the shared board.

### Session lifecycle

On start: `hopper sync` → `hopper task list` → check `in_progress` tasks → claim or create your task.
During work: heartbeat every 10-15 min; `hopper sync` periodically (task writes stay local until you sync).
On end: mark `completed` or release to `open`, then `hopper sync` to push your work.

### Knowledge base

Agent knowledge is available in `.hopper/knowledge/` — coding standards, design
patterns, agent roles, and workflows relevant to this project type.

```bash
hopper knowledge list                       # See what\'s available
hopper knowledge show                       # View hopper usage guide
hopper knowledge update-agent-files        # Re-sync AGENTS.md/CLAUDE.md to latest
```
"""


HOPPER_SKILL_CONTENT = """\
---
name: hopper
description: Interact with Hopper — the cross-agent persistent memory and task management CLI. Use this to read context, add tasks, claim work, record learnings, and manage session state.
---

## What I do

Hopper is a CLI-based persistent memory system. It stores tasks, learnings, decisions, and session state in `.hopper/` as markdown files — no server required. All agents (opencode, claude, kilocode, human) share the same board.

## When to use me

- At session start — to load context and check what's in flight
- When you discover something worth remembering
- When claiming, updating, or completing a task
- Before ending a session — to record state for the next agent

## Core commands

```bash
# Session start
hopper context                                # Recent learnings + open tasks
hopper task list                              # Full task board
hopper task get <id>                          # Details on a specific task

# Claim work
hopper task status <id> in_progress --assign "opencode:my-task" -f

# Heartbeat (every 10-15 min of active work)
hopper task heartbeat <id>
hopper task heartbeat <id> --expect 2h        # Before long-running work

# Leave an attributed, append-only note on any task (never overwrites the description)
hopper task note <id> "finding: ..."          # author defaults to $HOPPER_IDENTITY
hopper task notes <id>                         # list a task's note stream

# Complete or release
hopper task status <id> completed -f
hopper task update <id> --unassign && hopper task status <id> open -f

# Add a task or learning (always use --non-interactive to avoid prompts)
hopper task add "Title" --priority high --non-interactive
hopper task add "Learning: X works better than Y" --tag learning --non-interactive
hopper task add "Decision: chose approach A because..." --tag decision --non-interactive

# Find stale tasks from dead agents
hopper task stale

# Sync with upstream server
hopper sync
```

## Agent identity format

Always use `platform:task-name` when assigning:
- `opencode:my-task`, `claude:acm-rewrite`, `kilocode:prh-transfer`, `human:james`
- Never use generic names like `main`
- Set `HOPPER_IDENTITY=platform:you` (or pass `--by`) so records you create are
  stamped with `created_by`, attributing them to you rather than just the machine.

## Status values

`open` | `in_progress` | `blocked` | `completed` | `cancelled`

## Useful tags

`learning`, `decision`, `preference`, `pattern`, `feedback`, `session`, `gpu-job`
"""

GLOBAL_AGENTS_MD_SECTION = """\
## Hopper — Cross-Agent Memory

Hopper is the persistent memory system used across all agents. It is available as a CLI (`hopper`) and stores tasks, learnings, and decisions in `.hopper/` as markdown files.

**On every session start:**
1. `hopper sync` to pull the latest shared board, then `hopper context` for recent learnings and open tasks
2. Check `in_progress` tasks before starting new work — another agent may already own it
3. Claim your task: `hopper task status <id> in_progress --assign "platform:short-task-name" -f`

**During work:**
- Heartbeat every 10-15 min: `hopper task heartbeat <id>`
- Record learnings as you go: `hopper task add "Learning: ..." --tag learning`
- Leave a finding on another agent's task with `hopper task note <id> "..."` — append-only, never overwrites its description
- `hopper sync` periodically — task writes stay local until you sync

**On session end:**
- Mark completed: `hopper task status <id> completed -f`
- Or release: `hopper task update <id> --unassign && hopper task status <id> open -f`
- `hopper sync` to push your work to the shared board

**Agent identity:** always `platform:task-name` — e.g. `opencode:hopper-fixes`, never `opencode:main`. Set `HOPPER_IDENTITY=platform:you` so records you create are stamped with `created_by`.

Load the `hopper` skill for the full CLI reference.
"""

GLOBAL_AGENTS_MD_MARKER = "## Hopper — Cross-Agent Memory"


def write_global_agent_files() -> dict[str, Any]:
    """Install Hopper skill and session protocol into global agent config dirs.

    Writes to:
    - ~/.config/opencode/skills/hopper/SKILL.md  (opencode native)
    - ~/.claude/skills/hopper/SKILL.md            (Claude-compatible, also read by opencode)
    - ~/.config/opencode/AGENTS.md               (appends Hopper section if missing)

    Safe to call repeatedly — idempotent on all targets.

    Returns:
        Dict describing actions taken per file.
    """
    result: dict[str, Any] = {}
    home = Path.home()

    # Skill file locations
    skill_locations = [
        home / ".config" / "opencode" / "skills" / "hopper" / "SKILL.md",
        home / ".claude" / "skills" / "hopper" / "SKILL.md",
    ]

    for skill_path in skill_locations:
        skill_path.parent.mkdir(parents=True, exist_ok=True)
        if skill_path.exists():
            existing = skill_path.read_text()
            if existing.strip() == HOPPER_SKILL_CONTENT.strip():
                result[str(skill_path)] = {"action": "skipped", "reason": "already current"}
            else:
                skill_path.write_text(HOPPER_SKILL_CONTENT)
                result[str(skill_path)] = {"action": "updated"}
        else:
            skill_path.write_text(HOPPER_SKILL_CONTENT)
            result[str(skill_path)] = {"action": "created"}

    # Global AGENTS.md — opencode reads ~/.config/opencode/AGENTS.md
    global_agents = home / ".config" / "opencode" / "AGENTS.md"
    global_agents.parent.mkdir(parents=True, exist_ok=True)

    if global_agents.exists():
        content = global_agents.read_text()
        if GLOBAL_AGENTS_MD_MARKER in content:
            result[str(global_agents)] = {"action": "skipped", "reason": "section already present"}
        else:
            with open(global_agents, "a") as f:
                f.write(f"\n---\n\n{GLOBAL_AGENTS_MD_SECTION}")
            result[str(global_agents)] = {"action": "appended"}
    else:
        global_agents.write_text(f"# Agent Rules\n\n{GLOBAL_AGENTS_MD_SECTION}")
        result[str(global_agents)] = {"action": "created"}

    return result


def _is_git_url(source: str) -> bool:
    """Check if source is a Git URL."""
    return source.startswith(("https://", "git@", "ssh://", "git://"))


def _resolve_source(source: str, update: bool = True) -> tuple[Path, dict[str, Any]]:
    """Resolve source to a local path, cloning if necessary.

    Args:
        source: Local path or Git URL
        update: If True, pull latest changes for cached repos

    Returns:
        Tuple of (local_path, info_dict)
    """
    info: dict[str, Any] = {"source": source, "type": "local"}

    if not _is_git_url(source):
        # Local path
        return Path(source), info

    # Git URL - clone or update cache
    info["type"] = "git"

    # Create cache directory
    KNOWLEDGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Generate cache path from URL
    # e.g., https://github.com/exedev/agent-knowledge -> exedev-agent-knowledge
    repo_name = source.rstrip("/").split("/")[-1]
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]
    owner = source.rstrip("/").split("/")[-2]
    cache_name = f"{owner}-{repo_name}"
    cache_path = KNOWLEDGE_CACHE_DIR / cache_name

    try:
        if cache_path.exists():
            if update:
                # Pull latest
                result = subprocess.run(
                    ["git", "-C", str(cache_path), "pull", "--ff-only"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    info["action"] = "updated"
                else:
                    info["action"] = "cached"
                    info["warning"] = "Failed to update, using cached version"
            else:
                info["action"] = "cached"
        else:
            # Clone
            result = subprocess.run(
                ["git", "clone", "--depth", "1", source, str(cache_path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                info["error"] = f"Clone failed: {result.stderr}"
                return cache_path, info
            info["action"] = "cloned"

    except subprocess.TimeoutExpired:
        info["error"] = "Git operation timed out"
    except FileNotFoundError:
        info["error"] = "Git not found - install git to use GitHub sources"

    return cache_path, info


def get_hopper_usage_path(knowledge_path: Path) -> Path:
    """Get the path for hopper-usage.md."""
    return knowledge_path / "hopper-usage.md"


def write_hopper_usage(knowledge_path: Path) -> Path:
    """Write the built-in hopper-usage.md file.

    Args:
        knowledge_path: Path to .hopper/knowledge/ directory

    Returns:
        Path to the written file
    """
    knowledge_path.mkdir(parents=True, exist_ok=True)
    usage_file = get_hopper_usage_path(knowledge_path)
    usage_file.write_text(HOPPER_USAGE_CONTENT, encoding="utf-8")
    return usage_file


def sync_agent_knowledge(
    knowledge_path: Path,
    source: str | Path | None = None,
    patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Sync agent-knowledge from source to knowledge directory.

    Args:
        knowledge_path: Destination .hopper/knowledge/ directory
        source: Path or Git URL to agent-knowledge repo (default: GitHub)
        patterns: Optional list of subdirectories to sync (e.g., ["core-rules/python-standards"])
                  If None, syncs entire repo

    Returns:
        Dict with sync results: {"synced": [...], "skipped": [...], "errors": [...]}
    """
    source_str = str(source) if source else DEFAULT_KNOWLEDGE_SOURCE

    result: dict[str, Any] = {
        "synced": [],
        "skipped": [],
        "errors": [],
        "source": source_str,
    }

    # Resolve source (clone if Git URL)
    source_path, resolve_info = _resolve_source(source_str)
    result["resolve"] = resolve_info

    if resolve_info.get("error"):
        result["errors"].append(resolve_info["error"])
        return result

    if not source_path.exists():
        result["errors"].append(f"Source not found: {source_path}")
        return result

    knowledge_path.mkdir(parents=True, exist_ok=True)

    # Determine what to sync
    if patterns:
        # Sync specific subdirectories
        for pattern in patterns:
            src = source_path / pattern
            if not src.exists():
                result["skipped"].append(f"{pattern} (not found)")
                continue

            # Create destination maintaining structure
            dest = knowledge_path / "agent-knowledge" / pattern
            try:
                if src.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(src, dest)
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                result["synced"].append(pattern)
            except Exception as e:
                result["errors"].append(f"{pattern}: {e}")
    else:
        # Sync entire repo (excluding certain files)
        dest = knowledge_path / "agent-knowledge"
        try:
            if dest.exists():
                shutil.rmtree(dest)

            # Copy with ignore patterns
            def ignore_patterns(directory: str, files: list[str]) -> list[str]:
                ignore = []
                for f in files:
                    if f.startswith(".git") or f == "__pycache__":
                        ignore.append(f)
                return ignore

            shutil.copytree(source_path, dest, ignore=ignore_patterns)
            result["synced"].append("(full repo)")
        except Exception as e:
            result["errors"].append(f"Full sync failed: {e}")

    return result


def detect_project_type(project_path: Path) -> list[str]:
    """Detect project type and return relevant knowledge patterns.

    Args:
        project_path: Path to project root

    Returns:
        List of relevant agent-knowledge subdirectories
    """
    patterns = []

    # Always include core agent guidance
    patterns.append("core-rules/agent-roles")

    # Python projects
    if (project_path / "pyproject.toml").exists() or (project_path / "setup.py").exists():
        patterns.extend(
            [
                "core-rules/python-standards",
                "core-rules/testing",
            ]
        )

    # TypeScript/JavaScript projects
    if (project_path / "package.json").exists():
        patterns.append("core-rules/testing")

    # MCP server projects
    if (project_path / "mcp.json").exists() or _has_mcp_config(project_path):
        patterns.append("core-rules/mcp")

    # Czarina orchestration projects
    if (project_path / ".czarina").exists():
        patterns.append("core-rules/orchestration")

    # Claude Code skills
    if (project_path / ".claude" / "skills").exists():
        patterns.append("core-rules/skills")

    # Git workflow (always useful for repos)
    if (project_path / ".git").exists():
        patterns.append("core-rules/workflows")

    # Security (always relevant)
    patterns.append("core-rules/security")

    # Design patterns (useful for most projects)
    patterns.append("core-rules/design-patterns")

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique


def _has_mcp_config(project_path: Path) -> bool:
    """Check if project has MCP configuration."""
    # Check pyproject.toml for mcp references
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            if "mcp" in content.lower():
                return True
        except Exception:
            pass

    # Check for mcp in package.json
    package_json = project_path / "package.json"
    if package_json.exists():
        try:
            content = package_json.read_text()
            if '"mcp"' in content or "'mcp'" in content:
                return True
        except Exception:
            pass

    return False


def _extract_agent_files_version(content: str) -> int | None:
    """Extract the hopper-agent-files version from file content.

    Looks for: <!-- hopper-agent-files: vN -->

    Returns:
        Version integer, or None if not present.
    """
    import re

    match = re.search(r"<!--\s*hopper-agent-files:\s*v(\d+)\s*-->", content)
    return int(match.group(1)) if match else None


def write_agent_files(project_path: Path, force: bool = False) -> dict[str, Any]:
    """Write AGENTS.md and CLAUDE.md into the project root.

    If either file already exists:
    - Without force: appends if no Hopper section; skips if already at current version;
      updates if an older version is detected.
    - With force: always replaces the existing Hopper section.

    If neither exists, creates both.

    Args:
        project_path: Project root directory (where .hopper lives).
        force: If True, update the Hopper section even if already at current version.

    Returns:
        Dict with keys "AGENTS.md" and "CLAUDE.md", each containing
        "action": one of "created", "appended", "updated", "skipped",
        and optional "from_version" / "to_version" keys.
    """
    section_marker = "## Hopper - Persistent Memory"
    result: dict[str, Any] = {}

    for filename in ("AGENTS.md", "CLAUDE.md"):
        target = project_path / filename
        if target.exists():
            content = target.read_text()
            if section_marker in content:
                existing_version = _extract_agent_files_version(content)
                needs_update = (
                    force or (existing_version is None) or (existing_version < AGENTS_MD_VERSION)
                )

                if needs_update:
                    pre_section = content[: content.index(section_marker)]
                    pre_section = pre_section.rstrip().rstrip("-").rstrip()
                    updated = f"{pre_section}\n\n---\n\n{AGENTS_MD_SECTION}"
                    target.write_text(updated)
                    result[filename] = {
                        "action": "updated",
                        "from_version": existing_version,
                        "to_version": AGENTS_MD_VERSION,
                    }
                else:
                    result[filename] = {
                        "action": "skipped",
                        "reason": f"already at v{AGENTS_MD_VERSION}",
                        "version": existing_version,
                    }
            else:
                with open(target, "a") as f:
                    f.write(f"\n---\n\n{AGENTS_MD_SECTION}")
                result[filename] = {"action": "appended", "to_version": AGENTS_MD_VERSION}
        else:
            target.write_text(f"# {project_path.name}\n\n{AGENTS_MD_SECTION}")
            result[filename] = {"action": "created", "to_version": AGENTS_MD_VERSION}

    return result


def initialize_knowledge(
    knowledge_path: Path,
    source: str | Path | None = None,
    auto_detect: bool = True,
    project_path: Path | None = None,
    skip_agent_knowledge: bool = False,
) -> dict[str, Any]:
    """Initialize knowledge directory with hopper-usage and optional agent-knowledge.

    Args:
        knowledge_path: Path to .hopper/knowledge/ directory
        source: Agent-knowledge source (default: exe.dev standard)
        auto_detect: Auto-detect project type and sync relevant patterns only
        project_path: Project root for auto-detection (default: knowledge_path parent)
        skip_agent_knowledge: If True, only write hopper-usage.md

    Returns:
        Dict with initialization results
    """
    result = {
        "hopper_usage": None,
        "agent_knowledge": None,
    }

    # Always write hopper-usage.md
    usage_file = write_hopper_usage(knowledge_path)
    result["hopper_usage"] = str(usage_file)

    if skip_agent_knowledge:
        return result

    # Sync agent-knowledge
    if auto_detect:
        proj_path = project_path or knowledge_path.parent.parent
        patterns = detect_project_type(proj_path)
        if patterns:
            result["agent_knowledge"] = sync_agent_knowledge(knowledge_path, source, patterns)
    else:
        # Full sync
        result["agent_knowledge"] = sync_agent_knowledge(knowledge_path, source)

    return result
