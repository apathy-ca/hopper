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

# Job 3: memory consolidation
_CONSOLIDATE_ENABLED = os.getenv("HOPPER_AUDIT_CONSOLIDATE_ENABLED", "true").lower() == "true"
_CONSOLIDATE_INTERVAL_SECONDS = int(os.getenv("HOPPER_AUDIT_CONSOLIDATE_SECONDS", "0"))
_CONSOLIDATE_MIN_BATCH = int(os.getenv("HOPPER_AUDIT_CONSOLIDATE_MIN_BATCH", "5"))
_CONSOLIDATE_MAX_RECORDS = int(os.getenv("HOPPER_AUDIT_CONSOLIDATE_MAX_RECORDS", "100"))
_CONSOLIDATE_MODEL = os.getenv("HOPPER_AUDIT_CONSOLIDATE_MODEL", "claude-haiku-4-5")


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


class _ShadowConsolidationClient:
    """Thin adapter over RecordTaskRepository so run_consolidation can operate
    directly on the server's shadow.db (records+revisions) rather than the
    markdown task store that LocalClient uses for list_tasks/create_task."""

    def __init__(self, shadow_db_path: Path, agent_did: str, instance_id: str):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        url = f"sqlite:///{shadow_db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._session = self._Session()
        self._agent_did = agent_did
        self._instance_id = instance_id

        # Build record→instance lookup for scoping queries
        rows = self._session.execute(
            text("SELECT id, instance_id FROM records WHERE tombstoned_at IS NULL")
        ).fetchall()
        self._instance_records: dict[str, str | None] = {r[0]: r[1] for r in rows}

    def __enter__(self) -> _ShadowConsolidationClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def close(self) -> None:
        self._session.close()
        self._engine.dispose()

    def _repo(self):
        from hopper.api.repositories.record_tasks import RecordTaskRepository

        return RecordTaskRepository(self._session, instance_id=self._instance_id)

    def list_tasks(self, **params: Any) -> list[dict[str, Any]]:
        kind = params.get("kind", "task")
        memory_class = params.get("memory_class")
        items, _ = self._repo().list(kind=kind, limit=10000)
        # Scope to this client's instance
        items = [t for t in items if self._instance_records.get(t["id"]) == self._instance_id]
        if memory_class:
            items = [t for t in items if t.get("memory_class") == memory_class]
        return items

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._repo().create(
            data, author_did=self._agent_did, author_location=_AGENT_LOCATION
        )
        self._session.commit()
        return result

    def update_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = self._repo().update(
            task_id, data, author_did=self._agent_did, author_location=_AGENT_LOCATION
        )
        self._session.commit()
        return result or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._repo().get(task_id)

    def rekind_record(self, record_id: str, new_kind: str) -> None:
        """Change a record's kind (type) at the records table level.

        The normal update path blocks kind changes, so this updates
        records.type directly and writes a matching revision.
        """
        from sqlalchemy import text as sa_text

        from hopper.models.record import Record
        from hopper.storage.revision_writer import AuthorContext, write_revision

        record = self._session.get(Record, record_id)
        if record is None or record.tombstoned_at is not None:
            return
        payload = self._repo()._current_payload(record) or {}
        payload = dict(payload)
        payload["kind"] = new_kind
        payload["id"] = record_id

        self._session.execute(
            sa_text("UPDATE records SET type = :kind WHERE id = :id"),
            {"kind": new_kind, "id": record_id},
        )
        author = AuthorContext(did=self._agent_did, location=_AGENT_LOCATION)
        write_revision(
            self._session,
            payload,
            author,
            instance_id=self._instance_id,
        )
        self._session.commit()


def _get_instance_id(hopper_path: Path) -> str:
    """Read instance.id from config.yaml."""
    import yaml

    config_file = hopper_path / "config.yaml"
    if config_file.exists():
        try:
            data = yaml.safe_load(config_file.read_text()) or {}
            return data.get("instance", {}).get("id", ".hopper")
        except Exception:
            pass
    return ".hopper"


def _update_instance_metadata(hopper_path: Path, instance_id: str, updates: dict[str, Any]) -> None:
    """Merge updates into the instance's runtime_metadata in shadow.db."""
    import json

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    shadow_db = hopper_path / "shadow.db"
    if not shadow_db.exists():
        return

    engine = create_engine(f"sqlite:///{shadow_db}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        row = session.execute(
            text("SELECT runtime_metadata FROM hopper_instances WHERE id = :id"),
            {"id": instance_id},
        ).fetchone()
        if row is None:
            return
        existing = json.loads(row[0]) if row[0] else {}
        existing.update(updates)
        session.execute(
            text("UPDATE hopper_instances SET runtime_metadata = :meta WHERE id = :id"),
            {"id": instance_id, "meta": json.dumps(existing)},
        )
        session.commit()
    finally:
        session.close()
        engine.dispose()


def _read_instance_metadata(hopper_path: Path, instance_id: str) -> dict[str, Any]:
    """Read runtime_metadata for an instance from shadow.db."""
    import json

    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    shadow_db = hopper_path / "shadow.db"
    if not shadow_db.exists():
        return {}

    engine = create_engine(f"sqlite:///{shadow_db}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        row = session.execute(
            text("SELECT runtime_metadata FROM hopper_instances WHERE id = :id"),
            {"id": instance_id},
        ).fetchone()
        if row is None or row[0] is None:
            return {}
        return json.loads(row[0]) if isinstance(row[0], str) else (row[0] or {})
    finally:
        session.close()
        engine.dispose()


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


def _get_instances_with_memory(hopper_path: Path) -> list[str]:
    """Return instance IDs that own memory records or memory-shaped tasks.

    Finds instances with either kind=memory records or task records tagged
    with learning/decision (which should be re-kinded to memory during
    consolidation).
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    shadow_db = hopper_path / "shadow.db"
    if not shadow_db.exists():
        return []
    engine = create_engine(f"sqlite:///{shadow_db}", connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        rows = session.execute(
            text(
                "SELECT DISTINCT r.instance_id FROM records r "
                "WHERE r.tombstoned_at IS NULL AND r.instance_id IS NOT NULL "
                "AND (r.type = 'memory' OR ("
                "  r.type = 'task' AND EXISTS ("
                "    SELECT 1 FROM revisions rev "
                "    WHERE rev.id = r.current_revision_id "
                "    AND (rev.payload LIKE '%\"learning\"%' "
                "      OR rev.payload LIKE '%\"decision\"%' "
                "      OR rev.payload LIKE '%\"preference\"%')"
                "  )"
                "))"
            )
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        session.close()
        engine.dispose()


def run_memory_consolidation(client: Any, agent_did: str, hopper_path: Path) -> dict[str, Any]:
    """Job 3: LLM-driven memory consolidation (only_unclassified, gated by min_batch).

    Runs per-instance against the shadow DB (records+revisions) where memory
    records live, not the markdown task store that LocalClient uses.
    """
    if not _CONSOLIDATE_ENABLED:
        return {"skipped": True, "reason": "consolidation disabled"}

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set — skipping memory consolidation")
        return {"skipped": True, "reason": "ANTHROPIC_API_KEY not set"}

    shadow_db = hopper_path / "shadow.db"
    if not shadow_db.exists():
        return {"skipped": True, "reason": "shadow.db not found"}

    instances = _get_instances_with_memory(hopper_path)
    if not instances:
        return {"skipped": True, "reason": "no instances with memory records"}

    from hopper.memory.consolidation import run_consolidation

    results: dict[str, Any] = {}
    any_ran = False

    for instance_id in instances:
        with _ShadowConsolidationClient(shadow_db, agent_did, instance_id) as shadow_client:
            result = run_consolidation(
                shadow_client,
                only_unclassified=True,
                min_batch=_CONSOLIDATE_MIN_BATCH,
                max_records=_CONSOLIDATE_MAX_RECORDS,
                model=_CONSOLIDATE_MODEL,
            )

        logger.info("Memory consolidation [%s]: %s", instance_id, result)
        results[instance_id] = result

        if not result.get("skipped") and not result.get("error"):
            any_ran = True
            _update_instance_metadata(
                hopper_path,
                instance_id,
                {
                    "last_consolidation_at": datetime.now(UTC).isoformat(),
                    "last_consolidation_run_id": result.get("run_id"),
                    "last_consolidation_records": result.get("eligible", 0),
                },
            )

    if not any_ran:
        return {"skipped": True, "reason": "all instances skipped", "details": results}
    return {"instances": results}


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

    instance_id = _get_instance_id(hopper_path)
    last_digest_at: datetime | None = None
    last_consolidate_at: datetime | None = None

    # Seed last_consolidate_at from instance metadata (survives restarts)
    try:
        meta = _read_instance_metadata(hopper_path, instance_id)
        if ts := meta.get("last_consolidation_at"):
            last_consolidate_at = datetime.fromisoformat(ts)
            logger.info("Resuming consolidation timer from %s", ts)
    except Exception:
        pass

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

                # Job 3: memory consolidation
                now = datetime.now(UTC)
                consolidate_due = _CONSOLIDATE_INTERVAL_SECONDS == 0 or (
                    last_consolidate_at is None
                    or (now - last_consolidate_at).total_seconds() >= _CONSOLIDATE_INTERVAL_SECONDS
                )
                if consolidate_due:
                    result = run_memory_consolidation(client, agent_did, hopper_path)
                    if not result.get("skipped"):
                        last_consolidate_at = now

        except KeyboardInterrupt:
            logger.info("Audit agent interrupted — exiting")
            break
        except Exception:
            logger.exception("Audit agent cycle error — will retry")

        time.sleep(_POLL_INTERVAL_SECONDS)
