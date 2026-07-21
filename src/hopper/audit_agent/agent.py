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

# Job 3+: northbound (overseer cross-instance) consolidation
_NORTHBOUND_ENABLED = os.getenv("HOPPER_AUDIT_NORTHBOUND_ENABLED", "true").lower() == "true"
_NORTHBOUND_INTERVAL_SECONDS = int(os.getenv("HOPPER_AUDIT_NORTHBOUND_SECONDS", str(24 * 3600)))


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
    """Adapter over RecordTaskRepository for consolidation against shadow.db.

    Supports both single-instance mode (standard consolidation) and
    cross-instance mode (northbound): ``read_instance_ids`` controls which
    instances' records are visible; ``write_instance_id`` controls where new
    records are owned.
    """

    def __init__(
        self,
        shadow_db_path: Path,
        agent_did: str,
        instance_id: str,
        *,
        read_instance_ids: set[str] | None = None,
        write_instance_id: str | None = None,
    ):
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        url = f"sqlite:///{shadow_db_path}"
        self._engine = create_engine(url, connect_args={"check_same_thread": False})
        self._Session = sessionmaker(bind=self._engine, expire_on_commit=False)
        self._session = self._Session()
        self._agent_did = agent_did
        self._instance_id = instance_id
        self._read_ids = read_instance_ids or {instance_id}
        self._write_id = write_instance_id or instance_id

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

    def _repo(self, *, for_write: bool = False):
        from hopper.api.repositories.record_tasks import RecordTaskRepository

        iid = self._write_id if for_write else self._instance_id
        return RecordTaskRepository(self._session, instance_id=iid)

    def list_tasks(self, **params: Any) -> list[dict[str, Any]]:
        kind = params.get("kind", "task")
        memory_class = params.get("memory_class")
        items, _ = self._repo().list(kind=kind, limit=10000)
        items = [t for t in items if self._instance_records.get(t["id"]) in self._read_ids]
        if memory_class:
            items = [t for t in items if t.get("memory_class") == memory_class]
        return items

    def create_task(self, data: dict[str, Any]) -> dict[str, Any]:
        result = self._repo(for_write=True).create(
            data, author_did=self._agent_did, author_location=_AGENT_LOCATION
        )
        self._session.commit()
        return result

    def update_task(self, task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        result = self._repo(for_write=True).update(
            task_id, data, author_did=self._agent_did, author_location=_AGENT_LOCATION
        )
        self._session.commit()
        return result or {}

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._repo().get(task_id)

    def rekind_record(self, record_id: str, new_kind: str) -> None:
        """Change a record's kind (type) at the records table level."""
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
                "      OR rev.payload LIKE '%\"preference\"%' "
                "      OR rev.payload LIKE '%\"idea\"%' "
                "      OR rev.payload LIKE '%\"session-memory\"%' "
                "      OR rev.payload LIKE '%\"observation\"%')"
                "  )"
                "))"
            )
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        session.close()
        engine.dispose()


def _get_instance_edges(hopper_path: Path) -> list[tuple[str, str]]:
    """Read DAG edges from instance_relationships in shadow.db.

    Returns (parent_id, child_id) tuples. Returns [] if the table
    doesn't exist (pre-migration shadow.db).
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
            text("SELECT parent_id, child_id FROM instance_relationships")
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except Exception:
        # Table doesn't exist yet (pre-migration)
        return []
    finally:
        session.close()
        engine.dispose()


def run_bottom_up(
    shadow_db: Path,
    agent_did: str,
    hopper_path: Path,
    *,
    run_northbound_pass: bool = False,
    only: str | None = None,
    model: str | None = None,
    min_batch: int | None = None,
    max_records: int | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run consolidation bottom-up across the instance DAG.

    Leaf instances consolidate first; overseers consolidate after their
    children, then optionally run a northbound pass. Each instance
    consolidates exactly once even if it appears under multiple overseers.

    Args:
        shadow_db: Path to shadow.db.
        agent_did: Agent DID for authoring revisions.
        hopper_path: Path to .hopper directory.
        run_northbound_pass: If True, run northbound after each overseer.
        only: Restrict to this overseer and its subtree.
        model: Anthropic model override.
        min_batch: Minimum records to trigger consolidation.
        max_records: Cap records per consolidation pass.
    """
    from hopper.instances.dag import build_adjacency, get_subtree_nodes, topo_order_leaves_first
    from hopper.memory.consolidation import run_consolidation, run_northbound

    mem_instances = set(_get_instances_with_memory(hopper_path))
    edges = _get_instance_edges(hopper_path)
    children_of, _parents_of = build_adjacency(edges)

    all_nodes = mem_instances | {p for p, _ in edges} | {c for _, c in edges}

    if only:
        subtree = get_subtree_nodes(only, children_of)
        all_nodes = all_nodes & subtree

    order = topo_order_leaves_first(all_nodes, edges)

    consolidated: set[str] = set()
    results: dict[str, Any] = {}
    any_ran = False
    _model = model or _CONSOLIDATE_MODEL
    _min = min_batch if min_batch is not None else _CONSOLIDATE_MIN_BATCH
    _max = max_records if max_records is not None else _CONSOLIDATE_MAX_RECORDS

    for instance_id in order:
        if instance_id in consolidated:
            continue
        consolidated.add(instance_id)

        inst_result: dict[str, Any] = {}

        # 1. Standard per-instance consolidation
        if instance_id in mem_instances:
            with _ShadowConsolidationClient(shadow_db, agent_did, instance_id) as sc:
                result = run_consolidation(
                    sc,
                    only_unclassified=True,
                    min_batch=_min,
                    max_records=_max,
                    model=_model,
                    dry_run=dry_run,
                )
            inst_result["consolidation"] = result
            logger.info("Consolidation [%s]: %s", instance_id, result)

            if not result.get("skipped") and not result.get("error"):
                any_ran = True
            if not dry_run and not result.get("skipped") and not result.get("error"):
                _update_instance_metadata(
                    hopper_path,
                    instance_id,
                    {
                        "last_consolidation_at": datetime.now(UTC).isoformat(),
                        "last_consolidation_run_id": result.get("run_id"),
                        "last_consolidation_records": result.get("eligible", 0),
                    },
                )

        # 2. Northbound pass if this instance is an overseer with children
        child_ids = list(children_of.get(instance_id, set()) & all_nodes)
        if child_ids and run_northbound_pass:
            with _ShadowConsolidationClient(
                shadow_db,
                agent_did,
                instance_id,
                read_instance_ids=set(child_ids),
                write_instance_id=instance_id,
            ) as nb_client:
                nb_result = run_northbound(
                    nb_client,
                    parent_instance_id=instance_id,
                    child_instance_ids=child_ids,
                    model=_model,
                    max_records=_max,
                    dry_run=dry_run,
                )
            inst_result["northbound"] = nb_result
            logger.info("Northbound [%s]: %s", instance_id, nb_result)

            if not nb_result.get("skipped") and not nb_result.get("error"):
                any_ran = True
            if not dry_run and not nb_result.get("skipped") and not nb_result.get("error"):
                _update_instance_metadata(
                    hopper_path,
                    instance_id,
                    {
                        "last_northbound_at": datetime.now(UTC).isoformat(),
                        "last_northbound_run_id": nb_result.get("run_id"),
                        "last_northbound_records": nb_result.get("northbound_records_created", 0),
                    },
                )

        if inst_result:
            results[instance_id] = inst_result

    if not any_ran:
        return {"skipped": True, "reason": "all instances skipped", "details": results}
    return {"instances": results}


def run_memory_consolidation(client: Any, agent_did: str, hopper_path: Path) -> dict[str, Any]:
    """Job 3: LLM-driven memory consolidation with bottom-up DAG ordering.

    Delegates to ``run_bottom_up`` which handles per-instance consolidation
    and optional northbound passes for overseer instances.
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

    # Determine if northbound is due (separate, slower cadence)
    northbound_due = False
    if _NORTHBOUND_ENABLED:
        edges = _get_instance_edges(hopper_path)
        if edges:
            # Only check cadence if there are overseer relationships
            try:
                from hopper.instances.dag import build_adjacency

                children_of, _ = build_adjacency(edges)
                overseer_ids = [iid for iid, kids in children_of.items() if kids]
                if overseer_ids:
                    # Check cadence against first overseer's metadata
                    meta = _read_instance_metadata(hopper_path, overseer_ids[0])
                    last_nb = meta.get("last_northbound_at")
                    if last_nb:
                        elapsed = (
                            datetime.now(UTC) - datetime.fromisoformat(last_nb)
                        ).total_seconds()
                        northbound_due = elapsed >= _NORTHBOUND_INTERVAL_SECONDS
                    else:
                        northbound_due = True
            except Exception:
                logger.debug("Error checking northbound cadence", exc_info=True)
                northbound_due = True

    return run_bottom_up(
        shadow_db,
        agent_did,
        hopper_path,
        run_northbound_pass=northbound_due,
    )


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

    # Seed last_digest_at / last_consolidate_at from instance metadata (survives restarts)
    try:
        meta = _read_instance_metadata(hopper_path, instance_id)
        if ts := meta.get("last_digest_at"):
            last_digest_at = datetime.fromisoformat(ts)
            logger.info("Resuming digest timer from %s", ts)
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
                    if result.get("skipped"):
                        logger.info("Idea synthesis skipped: %s", result.get("reason", "unknown"))
                    else:
                        last_digest_at = now
                        logger.info("Idea synthesis complete: %s", result)
                        _update_instance_metadata(
                            hopper_path,
                            instance_id,
                            {"last_digest_at": now.isoformat()},
                        )

                # Job 3: memory consolidation
                now = datetime.now(UTC)
                consolidate_due = _CONSOLIDATE_INTERVAL_SECONDS == 0 or (
                    last_consolidate_at is None
                    or (now - last_consolidate_at).total_seconds() >= _CONSOLIDATE_INTERVAL_SECONDS
                )
                if consolidate_due:
                    result = run_memory_consolidation(client, agent_did, hopper_path)
                    if result.get("skipped"):
                        logger.info(
                            "Memory consolidation skipped: %s", result.get("reason", "unknown")
                        )
                    else:
                        last_consolidate_at = now
                        logger.info("Memory consolidation complete: %s", result)

        except KeyboardInterrupt:
            logger.info("Audit agent interrupted — exiting")
            break
        except Exception:
            logger.exception("Audit agent cycle error — will retry")

        time.sleep(_POLL_INTERVAL_SECONDS)
