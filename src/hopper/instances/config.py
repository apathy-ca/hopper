"""Read sub_instances declarations from config.yaml."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def read_sub_instances(hopper_path: Path) -> list[dict[str, Any]]:
    """Read the top-level ``sub_instances`` list from config.yaml.

    Returns a list of dicts, each with at least ``id``. Other optional
    keys: ``name``, ``scope``, ``path``, ``remote_only``, ``server``,
    ``description``. Returns ``[]`` if not declared.
    """
    import yaml

    config_file = hopper_path / "config.yaml"
    if not config_file.exists():
        return []

    try:
        data = yaml.safe_load(config_file.read_text()) or {}
    except Exception:
        logger.warning("Failed to parse %s", config_file)
        return []

    raw = data.get("sub_instances", [])
    if not isinstance(raw, list):
        return []

    result = []
    for entry in raw:
        if isinstance(entry, dict) and "id" in entry:
            result.append(entry)
        elif isinstance(entry, str):
            result.append({"id": entry})
    return result
