"""Auto-apply rule engine for Phase 4d.

Evaluates pending proposals against YAML rules and auto-applies matching ones.
Rules live at ``~/.hopper/auto-apply-rules.yaml`` (or the active hopper dir).

Rule format::

    rules:
      - name: "Trust audit-agent tag normalization"
        author_did: "did:key:..."          # exact match or "*" wildcard
        record_type: "task"                # or "*"
        action: apply                      # apply (default) or reject

Run with: ``hopper revision auto-apply``
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_RULES_FILE = "auto-apply-rules.yaml"


@dataclass
class AutoApplyRule:
    name: str
    author_did: str = "*"       # exact DID or "*" for any
    record_type: str = "*"      # RecordType value or "*" for any
    action: str = "apply"       # "apply" or "reject"
    reason: str | None = None   # optional rejection reason


def _load_rules(hopper_path: Path) -> list[AutoApplyRule]:
    rules_file = hopper_path / _DEFAULT_RULES_FILE
    if not rules_file.exists():
        return []
    try:
        import yaml
        with open(rules_file) as f:
            data = yaml.safe_load(f) or {}
        raw = data.get("rules") or []
        result = []
        for r in raw:
            result.append(AutoApplyRule(
                name=r.get("name", "unnamed"),
                author_did=r.get("author_did", "*"),
                record_type=r.get("record_type", "*"),
                action=r.get("action", "apply"),
                reason=r.get("reason"),
            ))
        return result
    except Exception:
        logger.exception("Failed to load auto-apply rules from %s", rules_file)
        return []


def _rule_matches(rule: AutoApplyRule, proposal: dict[str, Any],
                  record_type: str) -> bool:
    """Return True if this rule applies to this proposal."""
    if rule.author_did != "*" and proposal.get("author_did") != rule.author_did:
        return False
    if rule.record_type != "*" and record_type != rule.record_type:
        return False
    return True


def run_auto_apply(hopper_path: Path, client: Any) -> dict[str, Any]:
    """Run the auto-apply rule engine against all pending proposals.

    Args:
        hopper_path: Path to the active .hopper directory.
        client: A LocalClient instance.

    Returns:
        Summary dict: {applied: int, rejected: int, skipped: int}.
    """
    from hopper.storage.sqlite import SQLiteStorage
    from sqlalchemy import select, text
    from hopper.models import Record, Revision

    if not isinstance(client.storage, SQLiteStorage):
        return {"applied": 0, "rejected": 0, "skipped": 0,
                "error": "auto-apply requires SQLite backend"}

    rules = _load_rules(hopper_path)
    if not rules:
        return {"applied": 0, "rejected": 0, "skipped": 0,
                "message": "No auto-apply rules configured"}

    pending = client.list_pending_revisions(limit=500)
    applied = rejected = skipped = 0

    for proposal in pending:
        rev_id = proposal["id"]
        record_id = proposal["record_id"]

        # Look up record type
        with client.storage.session() as session:
            record = session.get(Record, record_id)
            record_type = record.type if record else "task"

        matched = False
        for rule in rules:
            if _rule_matches(rule, proposal, record_type):
                logger.info("Rule %r matches proposal %s", rule.name, rev_id[:10])
                try:
                    if rule.action == "apply":
                        client.apply_revision(rev_id)
                        applied += 1
                    elif rule.action == "reject":
                        client.reject_revision(rev_id, reason=rule.reason or rule.name)
                        rejected += 1
                except Exception:
                    logger.exception("auto-apply failed for %s", rev_id[:10])
                    skipped += 1
                matched = True
                break

        if not matched:
            skipped += 1

    return {"applied": applied, "rejected": rejected, "skipped": skipped}
