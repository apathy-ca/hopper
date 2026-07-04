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
    "learning", "decision", "preference",
    "idea", "session-memory", "observation",
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


def _call_llm(records: list[dict[str, Any]], model: str, api_key: str) -> dict[str, Any]:
    """Single LLM call: classify records and produce consolidation clusters.

    Returns a dict with:
      classifications: [{id, memory_class}]
      clusters: [{source_ids, title, summary}]
    """
    import anthropic

    records_text = "\n\n".join(
        "ID: {id}\nTitle: {title}{subject}{content}".format(
            id=r["id"],
            title=r.get("title", "(untitled)"),
            subject=f"\nSubject: {r['subject']}" if r.get("subject") else "",
            content=(
                f"\nContent: {r.get('description', '')[:400]}" if r.get("description") else ""
            ),
        )
        for r in records
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
        "Return ONLY valid JSON with this exact structure (no other text):\n"
        "{\n"
        '  "classifications": [\n'
        '    {"id": "record-id", "memory_class": "episodic|durable_fact|noise"}\n'
        "  ],\n"
        '  "clusters": [\n'
        "    {\n"
        '      "source_ids": ["id1", "id2"],\n'
        '      "title": "Brief title for the consolidated record",\n'
        '      "summary": "Consolidated content capturing all source records"\n'
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
    # Strip markdown fences if the model wrapped the JSON
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)


_DEFAULT_BATCH_SIZE = 15


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
        max_records: Cap the number of records sent to the LLM per call.

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

    if only_unclassified:
        eligible = [t for t in eligible if not t.get("memory_class")]

    if subject:
        eligible = [t for t in eligible if t.get("subject") == subject]
    if scope:
        eligible = [t for t in eligible if t.get("scope") == scope]

    if not eligible:
        return {"skipped": True, "reason": "No eligible memory records found", "eligible": 0}

    if len(eligible) < min_batch:
        return {"skipped": True, "reason": "below min_batch", "eligible": len(eligible)}

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

    for batch_idx, batch in enumerate(batches):
        logger.info("Consolidation batch %d/%d (%d records)", batch_idx + 1, len(batches), len(batch))
        try:
            llm_result = _call_llm(batch, model, api_key)
            all_classifications.extend(llm_result.get("classifications", []))
            all_clusters.extend(llm_result.get("clusters", []))
        except Exception as exc:
            logger.exception("LLM call failed for batch %d", batch_idx + 1)
            batch_errors.append(f"Batch {batch_idx + 1} failed: {exc}")

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

    classifications: dict[str, str] = {
        c["id"]: c["memory_class"]
        for c in all_classifications
        if c.get("id") and c.get("memory_class")
    }
    clusters = all_clusters

    clustered_ids: set[str] = set()
    for cluster in clusters:
        clustered_ids.update(cluster.get("source_ids", []))

    created_consolidated: list[str] = []
    updated_source: list[str] = []
    classified_only: list[str] = []
    errors: list[str] = list(batch_errors)

    # 3a. Create consolidated records for each cluster
    cluster_id_map: dict[str, str] = {}
    for cluster in clusters:
        source_ids = cluster.get("source_ids", [])
        if len(source_ids) < 2:
            continue
        title = cluster.get("title", "Consolidated memory")
        summary = cluster.get("summary", "")

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

    # 3b. Update source records: set memory_class and superseded_by
    for task in eligible:
        tid = task["id"]
        mc = classifications.get(tid)
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
        "source_records_superseded": len(updated_source),
        "records_classified_only": len(classified_only),
        "errors": errors,
        "durable_facts_flagged": sum(1 for mc in classifications.values() if mc == "durable_fact"),
    }


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
