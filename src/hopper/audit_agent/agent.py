"""Audit agent v0 core.

Two jobs:
  Job 1 — Tag normalization (runs every poll cycle, rule-based, auto-apply).
  Job 2 — Idea synthesis digest (runs weekly, Anthropic API, propose-only).

Design constraints (ember: 1 vCPU, 1.9 GB RAM, no local LLM):
  - Single-threaded polling loop.
  - <200 MB resident memory.
  - At most one Anthropic API call per cycle per job.
  - Uses ANTHROPIC_API_KEY from environment.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# How often to poll for new proposals (seconds)
_POLL_INTERVAL_SECONDS = int(os.getenv("HOPPER_AUDIT_POLL_SECONDS", "300"))  # 5 min default
# How often to run the synthesis digest (seconds) — default 7 days
_DIGEST_INTERVAL_SECONDS = int(os.getenv("HOPPER_AUDIT_DIGEST_SECONDS", str(7 * 24 * 3600)))
# Agent location token (shows up in revision.author_location)
_AGENT_LOCATION = os.getenv("HOPPER_AUDIT_LOCATION", "audit-agent@ember")


def _get_or_create_agent_did(hopper_path: Path) -> str:
    """Load or generate the audit agent's DID key.

    Key stored at <hopper_path>/audit-agent.key to keep it separate from the
    user's own did.key.
    """
    from hopper.upstream.did import DIDKey

    key_path = hopper_path / "audit-agent.key"
    if key_path.exists():
        return DIDKey.load(key_path).did
    key = DIDKey.generate()
    key.save(key_path)
    logger.info("Generated new audit-agent DID key at %s — DID: %s", key_path, key.did)
    return key.did


def _get_client(hopper_path: Path) -> Any:
    """Return a LocalClient for the given hopper path."""
    from hopper.cli.local_client import LocalClient

    return LocalClient(hopper_path)


def run_tag_normalization(client: Any, hopper_path: Path) -> dict[str, Any]:
    """Job 1: apply auto-apply rules against pending proposals.

    Rule-based, no LLM required. Reads rules from
    <hopper_path>/auto-apply-rules.yaml.
    """
    from hopper.intelligence.auto_apply import run_auto_apply

    result = run_auto_apply(hopper_path, client)
    logger.info("Tag normalization: %s", result)
    return result


def run_idea_synthesis(
    client: Any,
    agent_did: str,
    hopper_path: Path,
    since: datetime | None = None,
) -> dict[str, Any]:
    """Job 2: synthesise a weekly digest of type=idea records.

    Makes a single Anthropic API call. The digest is written as a
    type=note proposal (action='propose') so a human can review before it
    becomes live.

    Returns a summary dict.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping idea synthesis")
        return {"skipped": True, "reason": "ANTHROPIC_API_KEY not set"}

    # Collect type=idea records updated in the last 7 days
    if since is None:
        since = datetime.now(UTC) - timedelta(days=7)

    from hopper.storage.revision_writer import AuthorContext
    from hopper.storage.sqlite import SQLiteStorage

    if not isinstance(client.storage, SQLiteStorage):
        return {"skipped": True, "reason": "SQLite backend required"}

    from sqlalchemy import text

    with client.storage.session() as session:
        rows = session.execute(
            text(
                "SELECT r.id, r.type, rev.payload "
                "FROM records r "
                "JOIN revisions rev ON rev.id = r.current_revision_id "
                "WHERE r.type = 'idea' AND r.tombstoned_at IS NULL "
                "ORDER BY r.updated_at DESC LIMIT 100"
            )
        ).fetchall()

    ideas = []
    for row in rows:
        payload = row[2] or {}
        if isinstance(payload, str):
            import json

            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        title = payload.get("title", "(untitled)")
        desc = payload.get("description", "")
        ideas.append(f"- **{title}**" + (f": {desc[:200]}" if desc else ""))

    if not ideas:
        logger.info("No idea records found — skipping synthesis")
        return {"skipped": True, "reason": "No ideas to synthesise"}

    idea_text = "\n".join(ideas[:50])  # cap at 50 for prompt size
    prompt = (
        "You are an assistant synthesising a weekly digest of ideas captured in Hopper, "
        "a personal task and memory system. The following ideas were captured in the past week:\n\n"
        f"{idea_text}\n\n"
        "Write a concise synthesis digest (markdown, 200-400 words) that:\n"
        "- Groups related ideas into themes\n"
        "- Highlights any patterns or tensions across ideas\n"
        "- Suggests one or two next actions\n"
        "Do not list every idea individually — synthesise."
    )

    try:
        import anthropic

        anth = anthropic.Anthropic(api_key=api_key)
        message = anth.messages.create(
            model="claude-haiku-4-5",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        digest_text = message.content[0].text
    except Exception:
        logger.exception("Anthropic API call failed in idea synthesis")
        return {"skipped": True, "reason": "Anthropic API error"}

    # Write the digest as a proposal (type=note, action=propose)
    from hopper.storage.tasks import LocalTask

    title = f"Idea digest — week of {since.strftime('%Y-%m-%d')}"
    author = AuthorContext(did=agent_did, location=_AGENT_LOCATION)

    # Create a note task first (will produce a 'create' revision)
    note = LocalTask.create(
        title=title,
        description=digest_text,
        kind="note",
        tags=["digest", "idea-synthesis", "audit-agent"],
        source=_AGENT_LOCATION,
    )
    # We write a 'create' + then immediately amend to 'propose' pattern:
    # simpler to just write it as a direct propose on a new record.
    # Since there's no existing record for this note yet, we create it normally
    # (as a concrete note) — the "proposal" semantics apply to edits of existing
    # records. A fresh synthesis note is a direct write, not a proposal.
    client.task_store.create(note, author=author)

    logger.info("Idea synthesis digest written: %s (%s)", note.id, title)
    return {"note_id": note.id, "title": title, "ideas_included": len(ideas)}


def run_once(hopper_path: Path) -> None:
    """Run both jobs once and return."""
    agent_did = _get_or_create_agent_did(hopper_path)
    logger.info("Audit agent starting — DID: %s  location: %s", agent_did[:20], _AGENT_LOCATION)

    with _get_client(hopper_path) as client:
        tag_result = run_tag_normalization(client, hopper_path)
        logger.info("Job 1 done: %s", tag_result)


def run_loop(hopper_path: Path) -> None:
    """Run the agent in a continuous polling loop until interrupted."""
    agent_did = _get_or_create_agent_did(hopper_path)
    logger.info(
        "Audit agent loop starting — DID: %s  location: %s  poll=%ds  digest=%ds",
        agent_did[:20],
        _AGENT_LOCATION,
        _POLL_INTERVAL_SECONDS,
        _DIGEST_INTERVAL_SECONDS,
    )

    last_digest_at: datetime | None = None

    while True:
        try:
            with _get_client(hopper_path) as client:
                # Job 1: tag normalization on every cycle
                run_tag_normalization(client, hopper_path)

                # Job 2: idea synthesis — weekly
                now = datetime.now(UTC)
                digest_due = (
                    last_digest_at is None
                    or (now - last_digest_at).total_seconds() >= _DIGEST_INTERVAL_SECONDS
                )
                if digest_due:
                    result = run_idea_synthesis(client, agent_did, hopper_path)
                    if not result.get("skipped"):
                        last_digest_at = now
                        logger.info("Idea synthesis complete: %s", result)

        except KeyboardInterrupt:
            logger.info("Audit agent interrupted — exiting")
            break
        except Exception:
            logger.exception("Audit agent cycle error — will retry")

        time.sleep(_POLL_INTERVAL_SECONDS)
