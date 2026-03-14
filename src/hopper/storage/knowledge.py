"""
Knowledge management for Hopper.

Handles built-in hopper-usage knowledge and syncing from external
agent-knowledge repositories.
"""

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

# Default agent-knowledge source (GitHub repo)
DEFAULT_KNOWLEDGE_SOURCE = "https://github.com/apathy-ca/agent-knowledge.git"

# Cache directory for cloned repos
KNOWLEDGE_CACHE_DIR = Path.home() / ".cache" / "hopper" / "knowledge"

# Built-in hopper usage documentation
HOPPER_USAGE_CONTENT = '''---
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

## MCP Server

Hopper can run as an MCP server for direct tool integration:

```bash
hopper mcp serve              # Start MCP server
hopper mcp config --stdout    # Show MCP config for claude_desktop_config.json
```
'''


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
        patterns.extend([
            "core-rules/python-standards",
            "core-rules/testing",
        ])

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
            result["agent_knowledge"] = sync_agent_knowledge(
                knowledge_path, source, patterns
            )
    else:
        # Full sync
        result["agent_knowledge"] = sync_agent_knowledge(knowledge_path, source)

    return result
