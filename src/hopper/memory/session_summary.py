"""Tier 3 session memory — LLM-generated narrative over a single instance.

Answers: "what does this instance know and what is it working on?"
Fast context-load for an agent starting or resuming a session.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_RECENT_COMPLETED_DAYS = 7


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _call_llm(
    memories: list[dict[str, Any]],
    open_tasks: list[dict[str, Any]],
    recent_done: list[dict[str, Any]],
    model: str,
    api_key: str,
    subject: str | None,
) -> str:
    """Single LLM call returning a markdown session summary narrative."""
    import anthropic

    def _fmt_records(records: list[dict[str, Any]], max_content: int = 300) -> str:
        if not records:
            return "  (none)"
        lines = []
        for r in records:
            title = r.get("title", "(untitled)")
            subj = f" [{r['subject']}]" if r.get("subject") else ""
            desc = (r.get("description") or "").strip()[:max_content]
            desc_line = f"\n    {desc}" if desc else ""
            lines.append(f"  - {title}{subj}{desc_line}")
        return "\n".join(lines)

    subject_line = f"Subject filter: {subject}\n" if subject else ""

    prompt = (
        "You are generating a session summary for a Hopper instance — a persistent "
        "memory and task management tool used by AI agents and their human collaborators.\n\n"
        f"{subject_line}"
        "Your output is a concise markdown narrative that an agent reads at the start of "
        "a session to orient itself. Write in a direct, informative tone — no filler, "
        "no preamble. Structure it under these headings:\n\n"
        "## What this instance knows\n"
        "Synthesise the memory records into a coherent summary grouped by subject. "
        "Highlight durable facts and flag anything marked consolidated.\n\n"
        "## In flight\n"
        "Summarise open tasks. Note priority and who owns what if known.\n\n"
        "## Recently completed\n"
        "Brief summary of what was finished recently. Omit if empty.\n\n"
        "Keep the whole summary under 400 words. Prefer bullets over prose.\n\n"
        "---\n\n"
        f"Memory records ({len(memories)}):\n{_fmt_records(memories)}\n\n"
        f"Open tasks ({len(open_tasks)}):\n{_fmt_records(open_tasks)}\n\n"
        f"Recently completed ({len(recent_done)}):\n{_fmt_records(recent_done)}"
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def run_session_summary(
    client: Any,
    subject: str | None = None,
    since: datetime | None = None,
    save: bool = False,
    model: str | None = None,
) -> dict[str, Any]:
    """Generate a Tier 3 session summary for the current instance.

    Args:
        client: LocalClient instance.
        subject: Limit memory records to this subject.
        since: Only include memory records created/updated after this datetime.
        save: Write the summary as a memory record (memory_class=session_summary)
            so it syncs upstream and is visible to other agents. Replaces any
            existing session_summary record for this subject.
        model: Anthropic model (default: claude-sonnet-4-6).

    Returns:
        Dict with 'summary' (markdown text) and optionally 'saved_id'.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set"}

    model = model or os.getenv("HOPPER_CONSOLIDATION_MODEL", _DEFAULT_MODEL)
    now = datetime.now(UTC)

    # 1. Memory records — exclude noise and already-superseded
    all_memories = client.list_tasks(kind="memory")
    memories = [
        m
        for m in all_memories
        if m.get("memory_class") != "noise"
        and not m.get("superseded_by")
        and m.get("memory_class") != "session_summary"
    ]
    if subject:
        memories = [m for m in memories if m.get("subject") == subject]
    if since:
        since_aware = since if since.tzinfo else since.replace(tzinfo=UTC)
        memories = [
            m
            for m in memories
            if (_parse_dt(m.get("updated_at")) or datetime.min.replace(tzinfo=UTC)) >= since_aware
        ]

    # 2. Open tasks
    open_tasks = client.list_tasks(kind="task", status="open")

    # 3. Recently completed/done tasks (last N days)
    cutoff = now.timestamp() - (_RECENT_COMPLETED_DAYS * 86400)
    completed_raw = client.list_tasks(kind="task", status="completed")
    done_raw = client.list_tasks(kind="task", status="done")
    recent_done = [
        t
        for t in completed_raw + done_raw
        if (_parse_dt(t.get("updated_at")) or datetime.min.replace(tzinfo=UTC)).timestamp()
        >= cutoff
    ]

    if not memories and not open_tasks and not recent_done:
        return {"skipped": True, "reason": "No content found to summarise"}

    logger.info(
        "Generating session summary: %d memories, %d open tasks, %d recent done",
        len(memories),
        len(open_tasks),
        len(recent_done),
    )

    try:
        summary_text = _call_llm(memories, open_tasks, recent_done, model, api_key, subject)
    except Exception as exc:
        logger.exception("LLM call failed during session summary")
        return {"error": f"LLM call failed: {exc}"}

    result: dict[str, Any] = {"summary": summary_text}

    if save:
        # Replace existing session_summary for this subject
        existing = [
            m
            for m in all_memories
            if m.get("memory_class") == "session_summary" and m.get("subject") == subject
        ]
        for old in existing:
            try:
                client.update_task(old["id"], {"superseded_by": "__replaced__"})
            except Exception:
                pass

        title = f"Session summary{f': {subject}' if subject else ''}"
        try:
            saved = client.create_task(
                {
                    "title": title,
                    "description": summary_text,
                    "kind": "memory",
                    "subject": subject,
                    "memory_class": "session_summary",
                    "provenance": f"session-summary:{now.date().isoformat()}",
                    "tags": ["memory", "session_summary"],
                }
            )
            result["saved_id"] = saved["id"]
        except Exception as exc:
            result["save_error"] = str(exc)

    return result
