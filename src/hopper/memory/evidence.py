"""Evidence references on memory records.

A memory record may carry an ``evidence`` list: references to the things that
back it up. Each reference is a plain string, classified as:

  * a **task id** -- ``t`` + 8 hex chars (e.g. ``t1a2b3c4d``), or ``task:<id>``;
  * a **commit sha** -- 7-40 hex chars, or ``commit:<sha>``;
  * a **file path** -- anything with a path separator or file extension, or
    ``file:<path>``. A trailing ``:<line>`` / ``:<start>-<end>`` is ignored.
    Relative paths resolve against the project root;
  * a **URL** (``scheme://...``) or anything else -- recorded but never
    verified.

``find_missing_evidence`` is what ``hopper doctor`` uses to flag memories whose
evidence no longer exists. It is conservative: anything it cannot cheaply
verify is skipped, never reported missing.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

TASK = "task"
COMMIT = "commit"
FILE = "file"
URL = "url"
UNKNOWN = "unknown"

_TASK_ID_RE = re.compile(r"^t[0-9a-f]{8}$")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")
_LINE_SUFFIX_RE = re.compile(r":\d+(?:-\d+)?$")
_EXTENSION_RE = re.compile(r"\.[A-Za-z0-9]+$")
_PREFIXES = (TASK, COMMIT, FILE)


@dataclass(frozen=True)
class EvidenceRef:
    """A classified evidence reference."""

    kind: str  # task | commit | file | url | unknown
    value: str  # normalized value (prefix and line suffix stripped)
    raw: str  # the string as stored on the record


def classify_evidence(ref: str) -> EvidenceRef:
    """Classify one evidence string. Never raises."""
    raw = ref
    ref = (ref or "").strip()
    if not ref:
        return EvidenceRef(UNKNOWN, ref, raw)

    head, sep, rest = ref.partition(":")
    if sep and head.lower() in _PREFIXES and rest.strip() and not rest.startswith("//"):
        kind, value = head.lower(), rest.strip()
        if kind == FILE:
            value = _LINE_SUFFIX_RE.sub("", value)
        return EvidenceRef(kind, value, raw)

    if "://" in ref:
        return EvidenceRef(URL, ref, raw)
    if _TASK_ID_RE.match(ref):
        return EvidenceRef(TASK, ref, raw)
    if _SHA_RE.match(ref):
        return EvidenceRef(COMMIT, ref, raw)

    path = _LINE_SUFFIX_RE.sub("", ref)
    if " " not in path and ("/" in path or "\\" in path or _EXTENSION_RE.search(path)):
        return EvidenceRef(FILE, path, raw)
    return EvidenceRef(UNKNOWN, ref, raw)


def cited_task_ids(evidence: Iterable[str]) -> list[str]:
    """Task-id references (possibly prefixes) in ``evidence``, in order, deduplicated."""
    refs = (classify_evidence(raw) for raw in evidence or [])
    return list(dict.fromkeys(r.value for r in refs if r.kind == TASK))


def find_missing_evidence(
    evidence: Iterable[str],
    *,
    known_ids: Iterable[str],
    project_root: Path | None,
    commit_exists: Callable[[str], bool | None] | None = None,
) -> list[str]:
    """Return the raw evidence strings that demonstrably no longer exist.

    Args:
        evidence: The record's evidence list.
        known_ids: Every record id in the store. A ``task:`` reference may be a
            unique-or-not id prefix; any match counts as present.
        project_root: Directory relative file paths resolve against. ``None``
            (e.g. the global store) skips relative paths; absolute paths are
            still checked.
        commit_exists: Returns True/False for a sha, or None when it cannot
            tell (no git repo). Omitted -> commits are not checked.
    """
    ids = set(known_ids)
    missing: list[str] = []
    for raw in evidence or []:
        ref = classify_evidence(raw)
        if ref.kind == TASK:
            if ref.value not in ids and not any(i.startswith(ref.value) for i in ids):
                missing.append(raw)
        elif ref.kind == FILE:
            path = Path(ref.value).expanduser()
            if not path.is_absolute():
                if project_root is None:
                    continue
                path = project_root / path
            if not path.exists():
                missing.append(raw)
        elif ref.kind == COMMIT and commit_exists is not None:
            if commit_exists(ref.value) is False:
                missing.append(raw)
    return missing
