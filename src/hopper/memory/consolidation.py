"""Memory consolidation — LLM-driven curation of type=memory records.

Reads memory records for a subject/scope, classifies them, merges episodic
duplicates into consolidated summaries, and writes results back as normal
record updates (direct apply by default; --propose for a review gate).

Results sync through the normal upstream path like any other record change.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"

_MEMORY_SHAPED_TAGS = {
    "learning",
    "decision",
    "preference",
    "idea",
    "session-memory",
    "observation",
}


def _rekind_memory_shaped_tasks(client: Any, extra_tags: set[str] | None = None) -> int:
    """Re-kind task records with memory-shaped tags to kind=memory.

    The normal update path blocks kind changes (records.type is immutable via
    revision merge). This reaches through the client to update records.type
    directly, then writes a revision to keep the payload consistent.

    Returns the number of records re-kinded.
    """
    match_tags = _MEMORY_SHAPED_TAGS | (extra_tags or set())
    all_tasks = client.list_tasks(kind="task")
    rekinds = 0
    for task in all_tasks:
        tags = set(task.get("tags") or [])
        if not tags & match_tags:
            continue
        tid = task["id"]
        try:
            client.rekind_record(tid, "memory")
            rekinds += 1
            logger.info("Re-kinded task %s to memory (tags: %s)", tid, tags & match_tags)
        except Exception:
            logger.exception("Failed to re-kind task %s", tid)
    return rekinds


def _format_episode(r: dict[str, Any]) -> str:
    return "ID: {id}\nTitle: {title}{subject}{content}".format(
        id=r["id"],
        title=r.get("title", "(untitled)"),
        subject=f"\nSubject: {r['subject']}" if r.get("subject") else "",
        content=(f"\nContent: {r.get('description', '')[:400]}" if r.get("description") else ""),
    )


def _format_existing(r: dict[str, Any]) -> str:
    # Existing summaries are shown (nearly) in full: when the LLM extends one it
    # rewrites the whole summary, so truncating here would silently drop content.
    return "ID: {id}\nTitle: {title}{subject}\nSummary: {summary}".format(
        id=r["id"],
        title=r.get("title", "(untitled)"),
        subject=f"\nSubject: {r['subject']}" if r.get("subject") else "",
        summary=(r.get("description") or "")[:_EXISTING_SUMMARY_CHARS],
    )


def _call_llm(
    records: list[dict[str, Any]],
    model: str,
    api_key: str,
    existing: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Single LLM call: classify records and produce consolidation clusters.

    Args:
        records: Episode records to classify and cluster.
        model: Anthropic model id.
        api_key: Anthropic API key.
        existing: Existing consolidated records for the same subject/scope,
            supplied as read-only context. The LLM may fold new records into
            one of these by setting ``extends_id`` on a cluster.

    Returns a dict with:
      classifications: [{id, memory_class}]
      clusters: [{source_ids, title, summary, extends_id?}]
    """
    import anthropic

    existing = existing or []
    records_text = "\n\n".join(_format_episode(r) for r in records)

    existing_instructions = ""
    existing_section = ""
    if existing:
        existing_instructions = (
            "4. Existing consolidated summaries are listed separately below as READ-ONLY "
            "context. Never classify them and never put their IDs in source_ids. If new "
            'records belong in one of those summaries, set that cluster\'s "extends_id" '
            'to the existing summary\'s ID and write "summary" as the full updated '
            "summary (existing content plus the new information, losing nothing). A "
            "cluster that extends an existing summary may contain a single new record. "
            'Otherwise set "extends_id" to null.\n\n'
        )
        existing_section = (
            "Existing consolidated summaries (read-only context):\n\n"
            + "\n\n".join(_format_existing(r) for r in existing)
            + "\n\n"
        )

    prompt = (
        "You are consolidating memory records stored in Hopper, a task and knowledge "
        "management tool for AI agents. The records below were written by agents across "
        "multiple sessions.\n\n"
        f"There are {len(records)} memory records to process. Your job:\n\n"
        "1. Classify each record as one of:\n"
        "   - episodic: a point-in-time observation, event, or decision "
        "(may overlap with others)\n"
        "   - durable_fact: a standing project convention, architecture decision, "
        "or persistent fact\n"
        "   - noise: low-value, redundant with another record, or no longer relevant\n\n"
        "2. Group episodic records into clusters of near-duplicates or closely related "
        "records that should be merged into one. Only create a cluster when 2 or more "
        "records genuinely overlap — do not cluster unrelated records.\n\n"
        "3. For each cluster, write a consolidated title and summary that captures all "
        "key information from the source records without losing specifics.\n\n"
        f"{existing_instructions}"
        "Return ONLY valid JSON with this exact structure (no other text):\n"
        "{\n"
        '  "classifications": [\n'
        '    {"id": "record-id", "memory_class": "episodic|durable_fact|noise"}\n'
        "  ],\n"
        '  "clusters": [\n'
        "    {\n"
        '      "source_ids": ["id1", "id2"],\n'
        '      "title": "Brief title for the consolidated record",\n'
        '      "summary": "Consolidated content capturing all source records",\n'
        '      "extends_id": null\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"{existing_section}"
        "Records:\n\n"
        f"{records_text}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    # Strip markdown fences if the model wrapped the JSON
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)


_DEFAULT_BATCH_SIZE = 15
# Cap on how many existing consolidated records are shown per batch, and how
# much of each summary is included.
_MAX_EXISTING_CONTEXT = 10
_EXISTING_SUMMARY_CHARS = 4000


# Lower tier = consolidated first. Unclassified records have never been looked
# at; episodic ones are the raw material for merging; noise is low value but
# may still be redundant with something; durable facts are already settled.
_CLASS_TIER: dict[str | None, int] = {
    None: 0,
    "episodic": 1,
    "noise": 2,
    "durable_fact": 3,
}
_UNKNOWN_CLASS_TIER = 4


def _timestamp(value: Any) -> float:
    """Epoch seconds for a datetime or ISO string; 0.0 if missing/unparseable.

    Naive values are treated as UTC (that is how the storage layers persist
    them). Missing timestamps map to 0.0 so they sort as the oldest.
    """
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return 0.0
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.timestamp()
    return 0.0


def _key_class_tier(r: dict[str, Any]) -> int:
    return _CLASS_TIER.get(r.get("memory_class"), _UNKNOWN_CLASS_TIER)


def _key_reinforcement(r: dict[str, Any]) -> int:
    return len(r.get("notes") or [])


def _key_last_touched(r: dict[str, Any]) -> float:
    return _timestamp(r.get("updated_at") or r.get("created_at"))


def _key_id(r: dict[str, Any]) -> str:
    return str(r.get("id", ""))


# Ordered sort-key components; each maps a record to an ascending sort value
# (smaller = consolidate sooner). To add a new signal (e.g. a ``salience``
# field, lower = weaker = sooner, absent = neutral), insert one function here
# at the desired precedence — nothing else needs to change.
_PRIORITY_KEYS = (
    _key_class_tier,
    _key_reinforcement,
    _key_last_touched,
    _key_id,
)


def _priority_key(r: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(f(r) for f in _PRIORITY_KEYS)


def rank_for_consolidation(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order records so the weakest / least-settled are consolidated first.

    Deterministic and LLM-free; applied before ``max_records`` and batching so
    the cap drops the strongest records, not an arbitrary tail. Ordering, by
    precedence (each level breaks ties in the previous one):

    1. memory_class tier: unclassified, then episodic, then noise, then
       durable_fact, then anything else.
    2. Reinforcement: fewer attributed notes first (notes are the only
       per-record signal today that other agents revisited the record).
    3. Least recently touched first: ``updated_at``, falling back to
       ``created_at``; records with neither sort as oldest.
    4. Record id, so the order is total and stable across runs.

    No confidence/contradiction field exists on memory records yet; new
    signals slot into ``_PRIORITY_KEYS``.

    Returns a new list; the input is not modified.
    """
    return sorted(records, key=_priority_key)


def _related_consolidated(
    batch: list[dict[str, Any]], pool: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Existing consolidated records sharing a (subject, scope) with the batch.

    Most recently consolidated first, capped at ``_MAX_EXISTING_CONTEXT``.
    """
    keys = {(r.get("subject"), r.get("scope")) for r in batch}
    related = [c for c in pool if (c.get("subject"), c.get("scope")) in keys]
    related.sort(key=lambda c: str(c.get("consolidated_at") or ""), reverse=True)
    return related[:_MAX_EXISTING_CONTEXT]


def _normalize_batch_result(
    llm_result: dict[str, Any],
    batch_ids: set[str],
    context_ids: set[str],
    claimed: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Validate one batch's LLM output against the ids actually supplied.

    - Classifications for ids outside the batch are dropped (this is what keeps
      read-only consolidated context from being reclassified).
    - Cluster source_ids are restricted to batch ids not already claimed by an
      earlier cluster; consolidated ids can therefore never become sources.
    - ``extends_id`` is kept only if it names a supplied consolidated record.
    - A new cluster needs >= 2 sources; an extension needs >= 1.

    ``claimed`` is updated in place.
    """
    classifications = [
        c
        for c in llm_result.get("classifications") or []
        if isinstance(c, dict) and c.get("id") in batch_ids and c.get("memory_class")
    ]

    clusters: list[dict[str, Any]] = []
    for raw in llm_result.get("clusters") or []:
        if not isinstance(raw, dict):
            continue
        src = [
            i
            for i in dict.fromkeys(raw.get("source_ids") or [])
            if isinstance(i, str) and i in batch_ids and i not in claimed
        ]
        extends_id = raw.get("extends_id")
        if extends_id is not None and extends_id not in context_ids:
            logger.warning("Ignoring unknown extends_id %r from LLM", extends_id)
            extends_id = None
        if len(src) < (1 if extends_id else 2):
            continue
        claimed.update(src)
        clusters.append(
            {
                "source_ids": src,
                "title": raw.get("title"),
                "summary": raw.get("summary") or "",
                "extends_id": extends_id,
            }
        )
    return classifications, clusters


def run_consolidation(
    client: Any,
    subject: str | None = None,
    scope: str | None = None,
    dry_run: bool = False,
    propose: bool = False,
    model: str | None = None,
    only_unclassified: bool = False,
    min_batch: int = 1,
    max_records: int | None = None,
    batch_size: int | None = None,
) -> dict[str, Any]:
    """Run a consolidation pass over memory records.

    Existing consolidated records with the same subject/scope as a batch are
    supplied to the LLM as read-only context. A cluster may name one of them in
    ``extends_id``; that record is then updated in place (new summary, extended
    source_record_ids, bumped consolidated_at / consolidation_run_id, and a note
    recording the previous summary) instead of a parallel record being created.
    Consolidated records are never themselves eligible for clustering.

    Args:
        client: LocalClient instance.
        subject: Filter to records with this subject value.
        scope: Filter to records with this scope value.
        dry_run: If True, return LLM output without writing anything.
        propose: If True, write propose revisions instead of applying directly.
            Only meaningful on the SQLite backend; markdown backend always
            applies directly.
        model: Anthropic model to use (default: claude-haiku-4-5-20251001).
        only_unclassified: Only process records with no memory_class set yet.
        min_batch: Skip the LLM call if fewer than this many records are eligible.
        max_records: Cap the number of records processed in this run. Eligible
            records are ordered by :func:`rank_for_consolidation` first, so the
            weakest records are kept.

    Returns:
        Summary dict describing what was done (or would be done for --dry-run).
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set — cannot run consolidation"}

    model = model or os.getenv("HOPPER_CONSOLIDATION_MODEL", _DEFAULT_MODEL)

    # 0. Re-kind memory-shaped tasks (learning/decision/preference) to kind=memory
    if not dry_run:
        _rekind_memory_shaped_tasks(client)

    # 1. Select eligible records: kind=memory, not already consolidated or superseded
    all_memories = client.list_tasks(kind="memory")
    eligible = [
        t
        for t in all_memories
        if not t.get("superseded_by")
        and t.get("memory_class") not in ("consolidated", "northbound")
    ]
    # Live consolidated records: read-only context the LLM may extend.
    consolidated_pool = [
        t
        for t in all_memories
        if t.get("memory_class") == "consolidated" and not t.get("superseded_by")
    ]

    if only_unclassified:
        eligible = [t for t in eligible if not t.get("memory_class")]

    if subject:
        eligible = [t for t in eligible if t.get("subject") == subject]
        consolidated_pool = [t for t in consolidated_pool if t.get("subject") == subject]
    if scope:
        eligible = [t for t in eligible if t.get("scope") == scope]
        consolidated_pool = [t for t in consolidated_pool if t.get("scope") == scope]

    if not eligible:
        return {"skipped": True, "reason": "No eligible memory records found", "eligible": 0}

    if len(eligible) < min_batch:
        return {"skipped": True, "reason": "below min_batch", "eligible": len(eligible)}

    # Weakest records first, so max_records drops the most settled ones.
    eligible = rank_for_consolidation(eligible)
    if max_records is not None and len(eligible) > max_records:
        eligible = eligible[:max_records]

    bs = batch_size or int(os.getenv("HOPPER_CONSOLIDATION_BATCH_SIZE", str(_DEFAULT_BATCH_SIZE)))

    logger.info(
        "Running consolidation on %d memory records (subject=%s scope=%s batch_size=%d)",
        len(eligible),
        subject,
        scope,
        bs,
    )

    # 2. LLM classification + clustering — process in batches
    batches = [eligible[i : i + bs] for i in range(0, len(eligible), bs)]
    all_classifications: list[dict[str, Any]] = []
    all_clusters: list[dict[str, Any]] = []
    batch_errors: list[str] = []

    # Working copies of consolidated records: an extension proposed in one
    # batch is visible to later batches, so two batches extending the same
    # record compose instead of the second overwriting the first.
    originals = {c["id"]: c for c in consolidated_pool}
    working = {cid: dict(c) for cid, c in originals.items()}
    claimed: set[str] = set()

    for batch_idx, batch in enumerate(batches):
        logger.info(
            "Consolidation batch %d/%d (%d records)", batch_idx + 1, len(batches), len(batch)
        )
        context = _related_consolidated(batch, list(working.values()))
        try:
            llm_result = _call_llm(batch, model, api_key, existing=context)
        except Exception as exc:
            logger.exception("LLM call failed for batch %d", batch_idx + 1)
            batch_errors.append(f"Batch {batch_idx + 1} failed: {exc}")
            continue

        classifications, clusters = _normalize_batch_result(
            llm_result,
            batch_ids={r["id"] for r in batch},
            context_ids={c["id"] for c in context},
            claimed=claimed,
        )
        all_classifications.extend(classifications)
        all_clusters.extend(clusters)

        for cluster in clusters:
            ext = cluster["extends_id"]
            if not ext:
                continue
            w = working[ext]
            if cluster["title"]:
                w["title"] = cluster["title"]
            if cluster["summary"]:
                w["description"] = cluster["summary"]
            w["source_record_ids"] = list(
                dict.fromkeys([*(w.get("source_record_ids") or []), *cluster["source_ids"]])
            )

    if dry_run:
        return {
            "dry_run": True,
            "eligible": len(eligible),
            "batches": len(batches),
            "batch_errors": batch_errors,
            "classifications": all_classifications,
            "clusters": all_clusters,
        }

    # 3. Apply results
    run_id = f"consolidate-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)

    classifications_by_id: dict[str, str] = {
        c["id"]: c["memory_class"] for c in all_classifications
    }

    created_consolidated: list[str] = []
    updated_consolidated: list[str] = []
    updated_source: list[str] = []
    classified_only: list[str] = []
    errors: list[str] = list(batch_errors)

    # 3a. Create consolidated records for new clusters
    cluster_id_map: dict[str, str] = {}
    for cluster in all_clusters:
        if cluster["extends_id"]:
            continue
        source_ids = cluster["source_ids"]
        title = cluster["title"] or "Consolidated memory"
        summary = cluster["summary"]

        source_tasks = [t for t in eligible if t["id"] in source_ids]
        inferred_subject = next(
            (t.get("subject") for t in source_tasks if t.get("subject")), subject
        )
        inferred_scope = next((t.get("scope") for t in source_tasks if t.get("scope")), scope)

        try:
            result = client.create_task(
                {
                    "title": title,
                    "description": summary,
                    "kind": "memory",
                    "subject": inferred_subject,
                    "scope": inferred_scope,
                    "provenance": f"consolidation-run:{run_id}",
                    "memory_class": "consolidated",
                    "source_record_ids": source_ids,
                    "consolidation_run_id": run_id,
                    "consolidated_at": now.isoformat(),
                    "tags": ["memory", "consolidated"],
                }
            )
            new_id = result["id"]
            for src_id in source_ids:
                cluster_id_map[src_id] = new_id
            created_consolidated.append(new_id)
        except Exception as exc:
            errors.append(f"Failed to create consolidated record for cluster {source_ids}: {exc}")
            logger.exception("Failed to create consolidated record")

    # 3b. Update extended consolidated records in place
    extended_ids = list(dict.fromkeys(c["extends_id"] for c in all_clusters if c["extends_id"]))
    for cid in extended_ids:
        orig = originals[cid]
        final = working[cid]
        prior_sources = list(orig.get("source_record_ids") or [])
        added = [s for s in final["source_record_ids"] if s not in prior_sources]
        try:
            client.update_task(
                cid,
                {
                    "title": final.get("title"),
                    "description": final.get("description"),
                    "source_record_ids": final["source_record_ids"],
                    "consolidation_run_id": run_id,
                    "consolidated_at": now.isoformat(),
                },
            )
        except Exception as exc:
            errors.append(f"Failed to update consolidated record {cid}: {exc}")
            logger.exception("Failed to update consolidated record %s", cid)
            continue
        for src_id in added:
            cluster_id_map[src_id] = cid
        updated_consolidated.append(cid)
        _record_extension_note(client, cid, run_id, orig, added)

    # 3c. Update source records: set memory_class and superseded_by
    for task in eligible:
        tid = task["id"]
        mc = classifications_by_id.get(tid)
        superseded_by = cluster_id_map.get(tid)

        update: dict[str, Any] = {}
        if mc:
            update["memory_class"] = mc
        if superseded_by:
            update["superseded_by"] = superseded_by

        if not update:
            continue

        try:
            client.update_task(tid, update)
            if superseded_by:
                updated_source.append(tid)
            else:
                classified_only.append(tid)
        except Exception as exc:
            errors.append(f"Failed to update {tid}: {exc}")
            logger.exception("Failed to update source record %s", tid)

    return {
        "run_id": run_id,
        "eligible": len(eligible),
        "batches": len(batches),
        "consolidated_records_created": len(created_consolidated),
        "consolidated_records_updated": len(updated_consolidated),
        "source_records_superseded": len(updated_source),
        "records_classified_only": len(classified_only),
        "errors": errors,
        "durable_facts_flagged": sum(
            1 for mc in classifications_by_id.values() if mc == "durable_fact"
        ),
    }


def _record_extension_note(
    client: Any, cid: str, run_id: str, orig: dict[str, Any], added: list[str]
) -> None:
    """Leave an append-only note on an extended consolidated record.

    Preserves provenance of what changed: which run touched it, which sources
    were folded in, and the summary as it stood before the update. Clients
    without note support (e.g. the audit agent's shadow client) skip this.
    """
    add_note = getattr(client, "add_task_note", None)
    if add_note is None:
        return
    body = (
        f"Consolidation {run_id} extended this summary with sources: "
        f"{', '.join(added) or '(none)'}. "
        f"Previous run: {orig.get('consolidation_run_id') or 'unknown'}. "
        f"Previous title: {orig.get('title') or '(untitled)'}. "
        f"Previous summary: {orig.get('description') or ''}"
    )
    try:
        add_note(cid, body)
    except Exception:
        logger.exception("Failed to record extension note on %s", cid)


def run_drift_check(
    client: Any,
    record_id: str | None = None,
    subject: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Re-verify consolidated records against their source records.

    For each consolidated record (optionally filtered by record_id or subject),
    asks the LLM whether the summary still accurately represents its sources.
    Sets drift_score and drift_checked_at; if drift is high, proposes a refresh.

    Args:
        client: LocalClient instance.
        record_id: Check a single consolidated record by ID.
        subject: Check all consolidated records for this subject.
        model: Anthropic model to use.

    Returns:
        Summary dict of checked records and any high-drift records found.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    model = model or os.getenv("HOPPER_CONSOLIDATION_MODEL", _DEFAULT_MODEL)

    # Select consolidated records to check
    if record_id:
        task_dict = client.get_task(record_id)
        if not task_dict:
            return {"error": f"Record {record_id!r} not found"}
        consolidated = [task_dict]
    else:
        all_memories = client.list_tasks(kind="memory", memory_class="consolidated")
        consolidated = all_memories
        if subject:
            consolidated = [t for t in consolidated if t.get("subject") == subject]

    if not consolidated:
        return {"skipped": True, "reason": "No consolidated records to check"}

    import anthropic

    anth = anthropic.Anthropic(api_key=api_key)
    now = datetime.now(UTC)
    checked = 0
    high_drift: list[dict[str, Any]] = []
    errors: list[str] = []

    for consolidated_task in consolidated:
        cid = consolidated_task["id"]
        source_ids = consolidated_task.get("source_record_ids") or []
        if not source_ids:
            continue

        # Fetch current source records
        sources = []
        for sid in source_ids:
            try:
                t = client.get_task(sid)
                if t:
                    sources.append(t)
            except Exception:
                pass

        if not sources:
            continue

        sources_text = "\n\n".join(
            "ID: {id}\nTitle: {title}\nContent: {content}".format(
                id=s["id"],
                title=s.get("title", "(untitled)"),
                content=s.get("description", "")[:400],
            )
            for s in sources
        )

        summary = consolidated_task.get("description", "")
        prompt = (
            "You are checking whether a consolidated memory summary still accurately "
            "represents its source records.\n\n"
            f"Consolidated summary:\n{summary}\n\n"
            f"Source records:\n{sources_text}\n\n"
            "Rate the drift from 0.0 (no drift, summary is accurate) to 1.0 (major drift, "
            "summary is inaccurate or missing key information). "
            "Return ONLY valid JSON:\n"
            '{"drift_score": 0.0, "explanation": "one sentence"}'
        )

        try:
            message = anth.messages.create(
                model=model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            text = message.content[0].text.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            result = json.loads(text)
            drift_score = float(result.get("drift_score", 0.0))
        except Exception as exc:
            errors.append(f"Drift check failed for {cid}: {exc}")
            continue

        # Update drift fields
        try:
            client.update_task(
                cid,
                {
                    "drift_score": drift_score,
                    "drift_checked_at": now.isoformat(),
                },
            )
        except Exception as exc:
            errors.append(f"Failed to update drift fields for {cid}: {exc}")

        checked += 1
        if drift_score > 0.1:
            high_drift.append(
                {
                    "id": cid,
                    "title": consolidated_task.get("title"),
                    "drift_score": drift_score,
                    "explanation": result.get("explanation", ""),
                }
            )

    return {
        "checked": checked,
        "high_drift_count": len(high_drift),
        "high_drift": high_drift,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Northbound consolidation — cross-instance genmem for overseer instances
# ---------------------------------------------------------------------------


def _call_northbound_llm(
    records: list[dict[str, Any]],
    child_instance_ids: list[str],
    model: str,
    api_key: str,
) -> dict[str, Any]:
    """LLM call: synthesize cross-cutting summaries from sub-instance memories.

    Returns ``{"summaries": [{"title", "summary", "source_ids", "source_instances"}]}``.
    """
    import anthropic

    records_text = "\n\n".join(
        "Instance: {inst}\nID: {id}\nTitle: {title}{content}".format(
            inst=r.get("source_instance_id", "unknown"),
            id=r["id"],
            title=r.get("title", "(untitled)"),
            content=(
                f"\nContent: {r.get('description', '')[:500]}" if r.get("description") else ""
            ),
        )
        for r in records
    )

    prompt = (
        "You are synthesizing cross-cutting summaries for a Hopper overseer instance. "
        "Hopper is a task and knowledge management tool for AI agents. An overseer "
        "instance coordinates across multiple sub-instances.\n\n"
        f"Sub-instances: {', '.join(child_instance_ids)}\n\n"
        f"Below are {len(records)} consolidated/durable memory records from these "
        "sub-instances. Your job:\n\n"
        "1. Identify cross-cutting themes, overlaps, tensions, or synergies that "
        "span multiple sub-instances.\n"
        "2. For each theme, write a concise northbound summary that synthesizes the "
        "relevant records. Do NOT copy content verbatim — distill and point.\n"
        "3. Reference which sub-instances and source record IDs are relevant to "
        "each summary.\n"
        "4. Only create summaries for genuine cross-instance insights — skip themes "
        "that live entirely within one sub-instance.\n\n"
        "Return ONLY valid JSON with this exact structure (no other text):\n"
        "{\n"
        '  "summaries": [\n'
        "    {\n"
        '      "title": "Brief title for the cross-cutting theme",\n'
        '      "summary": "Synthesized insight spanning sub-instances",\n'
        '      "source_ids": ["record-id-1", "record-id-2"],\n'
        '      "source_instances": ["instance-a", "instance-b"]\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Records:\n\n"
        f"{records_text}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = message.content[0].text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)


def run_northbound(
    client: Any,
    parent_instance_id: str,
    child_instance_ids: list[str],
    model: str | None = None,
    dry_run: bool = False,
    min_batch: int = 2,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Run a northbound consolidation pass for an overseer instance.

    Reads sub-instances' consolidated and durable_fact memories (via the
    client's read scope), synthesizes cross-cutting summaries, and writes
    them as the overseer's own ``memory_class="northbound"`` records.

    The client must be configured to read from child instances and write
    to the parent instance.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set — cannot run northbound"}

    model = model or os.getenv("HOPPER_CONSOLIDATION_MODEL", _DEFAULT_MODEL)

    all_memories = client.list_tasks(kind="memory")
    eligible = [
        t
        for t in all_memories
        if t.get("memory_class") in ("consolidated", "durable_fact")
        and t.get("memory_class") != "northbound"
    ]

    if not eligible:
        return {"skipped": True, "reason": "No consolidated/durable_fact records in sub-instances"}

    if len(eligible) < min_batch:
        return {"skipped": True, "reason": "below min_batch", "eligible": len(eligible)}

    if max_records is not None and len(eligible) > max_records:
        eligible = eligible[:max_records]

    # Tag each record with its source instance for the LLM prompt.
    # The client reads across child instances but record payloads don't always
    # carry instance info, so we enrich from the client's knowledge.
    for rec in eligible:
        if not rec.get("source_instance_id"):
            rec["source_instance_id"] = rec.get("instance", "unknown")

    logger.info(
        "Running northbound consolidation for %s (%d records from %s)",
        parent_instance_id,
        len(eligible),
        child_instance_ids,
    )

    try:
        llm_result = _call_northbound_llm(eligible, child_instance_ids, model, api_key)
    except Exception:
        logger.exception("Northbound LLM call failed")
        return {"error": "LLM call failed", "eligible": len(eligible)}

    summaries = llm_result.get("summaries", [])

    if dry_run:
        return {
            "dry_run": True,
            "eligible": len(eligible),
            "summaries": summaries,
        }

    run_id = f"northbound-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC)
    created: list[str] = []
    errors: list[str] = []

    for summary in summaries:
        try:
            result = client.create_task(
                {
                    "title": summary.get("title", "Northbound summary"),
                    "description": summary.get("summary", ""),
                    "kind": "memory",
                    "memory_class": "northbound",
                    "source_record_ids": summary.get("source_ids", []),
                    "source_instance": summary.get("source_instances", child_instance_ids),
                    "provenance": f"northbound-run:{run_id}",
                    "consolidation_run_id": run_id,
                    "consolidated_at": now.isoformat(),
                    "tags": ["memory", "northbound", "overseer"],
                }
            )
            created.append(result["id"])
        except Exception as exc:
            errors.append(f"Failed to create northbound record: {exc}")
            logger.exception("Failed to create northbound record")

    return {
        "run_id": run_id,
        "parent_instance": parent_instance_id,
        "eligible": len(eligible),
        "northbound_records_created": len(created),
        "errors": errors,
    }
