"""
Markdown file storage backend.

Human-readable, git-friendly storage using markdown with YAML frontmatter.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def _utc_now() -> datetime:
    """Get current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from .base import StorageBackend, StorageConfig


@dataclass
class MarkdownDocument:
    """Parsed markdown document with YAML frontmatter."""

    frontmatter: dict[str, Any]
    content: str

    @classmethod
    def parse(cls, text: str) -> "MarkdownDocument":
        """Parse markdown with YAML frontmatter."""
        pattern = r"^---\n(.*?)\n---\n?(.*)$"
        match = re.match(pattern, text, re.DOTALL)

        if match:
            try:
                frontmatter = yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                frontmatter = {}
            content = match.group(2).strip()
        else:
            frontmatter = {}
            content = text.strip()

        return cls(frontmatter=frontmatter, content=content)

    def render(self) -> str:
        """Render document to markdown string."""
        # Clean None values from frontmatter
        clean_fm = {k: v for k, v in self.frontmatter.items() if v is not None}
        frontmatter_str = yaml.dump(
            clean_fm,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
        return f"---\n{frontmatter_str}---\n\n{self.content}"


class MarkdownStorage(StorageBackend):
    """
    Markdown-based storage backend.

    Directory structure:
        base_path/
        ├── config.yaml
        ├── tasks/
        │   └── {task_id}.md
        ├── memory/
        │   ├── episodes/
        │   │   └── {date}.md
        │   └── patterns/
        │       └── {pattern_id}.md
        ├── feedback/
        │   └── {task_id}.md
        └── .index/
            └── tasks.json
    """

    def __init__(self, config: StorageConfig):
        """Initialize markdown storage."""
        if config.path is None:
            raise ValueError("Path required for markdown storage")

        self.config = config
        self.base_path = Path(config.path)

        # Directory paths
        self.tasks_path = self.base_path / "tasks"
        self.episodes_path = self.base_path / "memory" / "episodes"
        self.patterns_path = self.base_path / "memory" / "patterns"
        self.feedback_path = self.base_path / "feedback"
        self.index_path = self.base_path / ".index"

        # Index cache
        self._index: dict[str, Any] | None = None
        self._index_dirty = False

    def initialize(self) -> None:
        """Create directory structure."""
        for path in [
            self.tasks_path,
            self.episodes_path,
            self.patterns_path,
            self.feedback_path,
            self.index_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)

        # Create default config if not exists
        config_file = self.base_path / "config.yaml"
        if not config_file.exists():
            self._write_config(config_file)

        # Create .gitignore for index
        gitignore = self.index_path / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")

        # Build initial index
        self._rebuild_index()

    def get_config(self) -> StorageConfig:
        """Get storage configuration."""
        return self.config

    @property
    def is_local(self) -> bool:
        """Check if this is a local storage backend."""
        return True

    def _write_config(self, config_file: Path) -> None:
        """Write default config file."""
        default_config = {
            "instance": {
                "id": self.config.instance_id,
                "name": self.config.instance_name,
                "scope": "personal",
            },
            "storage": {
                "type": "markdown",
                "path": str(self.base_path),
            },
            "sync": {
                "enabled": self.config.sync_enabled,
                "server_url": self.config.server_url,
                "sync_patterns": self.config.sync_patterns,
                "sync_episodes": self.config.sync_episodes,
            },
            "defaults": {
                "priority": "medium",
                "status": "pending",
            },
        }
        config_file.write_text(yaml.dump(default_config, default_flow_style=False))

    # =========================================================================
    # File Operations
    # =========================================================================

    def read_document(self, file_path: Path) -> MarkdownDocument | None:
        """Read and parse a markdown document."""
        if not file_path.exists():
            return None
        return MarkdownDocument.parse(file_path.read_text(encoding="utf-8"))

    def write_document(self, file_path: Path, doc: MarkdownDocument) -> None:
        """Write a markdown document."""
        file_path.write_text(doc.render(), encoding="utf-8")

    def delete_file(self, file_path: Path) -> bool:
        """Delete a file. Returns True if deleted."""
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def list_files(self, directory: Path, pattern: str = "*.md") -> list[Path]:
        """List files matching pattern in directory."""
        if not directory.exists():
            return []
        return sorted(directory.glob(pattern))

    # =========================================================================
    # Index Management
    # =========================================================================

    def get_index(self) -> dict[str, Any]:
        """Get task index, loading from file if needed."""
        if self._index is None:
            self._load_index()
        return self._index or {}

    def _load_index(self) -> None:
        """Load index from file."""
        index_file = self.index_path / "tasks.json"
        if index_file.exists():
            try:
                self._index = json.loads(index_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._rebuild_index()
        else:
            self._rebuild_index()

    def _save_index(self) -> None:
        """Save index to file."""
        if self._index is None:
            return

        index_file = self.index_path / "tasks.json"
        self._index["generated_at"] = _utc_now().isoformat()
        index_file.write_text(
            json.dumps(self._index, indent=2, default=str),
            encoding="utf-8",
        )
        self._index_dirty = False

    def _rebuild_index(self) -> None:
        """Rebuild index from task files."""
        self._index = {
            "tasks": {},
            "by_status": {},
            "by_tag": {},
            "by_project": {},
            "generated_at": _utc_now().isoformat(),
        }

        for task_file in self.list_files(self.tasks_path):
            doc = self.read_document(task_file)
            if doc and "id" in doc.frontmatter:
                self._index_task(doc.frontmatter, task_file)

        self._save_index()

    def _index_task(self, frontmatter: dict[str, Any], file_path: Path) -> None:
        """Add task to index."""
        if self._index is None:
            return

        task_id = frontmatter["id"]

        # Main index
        self._index["tasks"][task_id] = {
            "title": frontmatter.get("title", ""),
            "status": frontmatter.get("status", "pending"),
            "priority": frontmatter.get("priority"),
            "tags": frontmatter.get("tags", []),
            "project": frontmatter.get("project"),
            "file": str(file_path.relative_to(self.base_path)),
            "updated_at": frontmatter.get("updated_at"),
        }

        # Status index
        status = frontmatter.get("status", "pending")
        if status not in self._index["by_status"]:
            self._index["by_status"][status] = []
        if task_id not in self._index["by_status"][status]:
            self._index["by_status"][status].append(task_id)

        # Tag index
        for tag in frontmatter.get("tags", []):
            if tag not in self._index["by_tag"]:
                self._index["by_tag"][tag] = []
            if task_id not in self._index["by_tag"][tag]:
                self._index["by_tag"][tag].append(task_id)

        # Project index
        project = frontmatter.get("project")
        if project:
            if project not in self._index["by_project"]:
                self._index["by_project"][project] = []
            if task_id not in self._index["by_project"][project]:
                self._index["by_project"][project].append(task_id)

        self._index_dirty = True

    def _remove_from_index(self, task_id: str) -> None:
        """Remove task from index."""
        if self._index is None:
            return

        # Remove from main index
        task_data = self._index["tasks"].pop(task_id, None)
        if not task_data:
            return

        # Remove from status index
        status = task_data.get("status")
        if status and status in self._index["by_status"]:
            self._index["by_status"][status] = [
                t for t in self._index["by_status"][status] if t != task_id
            ]

        # Remove from tag index
        for tag in task_data.get("tags", []):
            if tag in self._index["by_tag"]:
                self._index["by_tag"][tag] = [
                    t for t in self._index["by_tag"][tag] if t != task_id
                ]

        # Remove from project index
        project = task_data.get("project")
        if project and project in self._index["by_project"]:
            self._index["by_project"][project] = [
                t for t in self._index["by_project"][project] if t != task_id
            ]

        self._index_dirty = True

    def update_index(self, task_id: str, frontmatter: dict[str, Any], file_path: Path) -> None:
        """Update index for a task."""
        self._remove_from_index(task_id)
        self._index_task(frontmatter, file_path)
        if self._index_dirty:
            self._save_index()

    def reindex(self) -> int:
        """Rebuild entire index. Returns number of tasks indexed."""
        self._rebuild_index()
        return len(self._index.get("tasks", {})) if self._index else 0
