# Memory Consolidation — Design Sketch

Status: **IMPLEMENTED** — Phase 1 (single-instance) complete 2026-06-16.
Phase 2 (cross-instance) deferred indefinitely: the write-destination
problem is unresolved (which instance owns the consolidated record?). Do
not implement until instance hierarchy conventions are clearer.
Date: 2026-06-15, updated 2026-06-16

---

## 1. Motivation

`type=memory` records are now first-class, queryable, DID-attributed, and
sync across instances — but they are **append-only with no curation**. Left
alone, a heavily-used instance accumulates duplicates, superseded facts, and
one-off episodic notes with no mechanism to merge, retire, or surface the
durable signal (cf. RP's ~50 memory-tagged records split across four
fragmented tag families, noted in the diagnosis doc).

This sketch proposes an **agentic consolidation pass**: an LLM periodically
reviews accumulated memory records for a subject/scope, classifies them,
merges/dedupes episodic ones into summaries, and flags durable facts for
human promotion into project docs (AGENTS.md/CLAUDE.md). It is framed as a
**data-quality/curation job for a shared knowledge store**, not as
memory-sovereignty or agent-identity machinery — that framing (drawn from
The Symposium's Sage memory architecture, see §6) was explicitly considered
and set aside for Hopper's operational use case.

---

## 2. Data model — first-class fields on LocalTask / SyncTask

The core insight: consolidation output must **sync like any other record
change**. This means `memory_class`, `superseded_by`, and `source_record_ids`
must be explicit `LocalTask` and `SyncTask` fields — not payload-only
conventions — following the same pattern used for `subject`, `scope`, and
`provenance` in the memory/kind first-class work (8e11e65).

Fields to add to `LocalTask`, `SyncTask`, markdown frontmatter, and SQLite
schema:

- `memory_class: str | None` — `episodic | durable_fact | consolidated | noise`
  — output of the classification step. Indexed in `by_memory_class` bucket
  (markdown) / queryable column (SQLite) so the select step is cheap.
- `superseded_by: str | None` — ID of the `consolidated` record that
  replaced this one. Set on source records when a consolidation is applied.
  Supersede, never delete.
- `source_record_ids: list[str]` — for `memory_class=consolidated` records,
  the IDs of the memory records summarized. Stored as a list field.
- `consolidation_run_id: str | None`, `consolidated_at: datetime | None`
  — provenance on consolidated records.
- `drift_checked_at: datetime | None`, `drift_score: float | None`
  — set by the drift-check job (§4).

Once these are first-class fields they survive every hop: markdown
frontmatter → sync wire → server → other instances. No special handling
needed.

---

## 3. The consolidation job

Runs as a normal Hopper task claimed by an agent — no MCP dependency, works
from CLI or any client. No new scheduler required initially; cron or
`/loop` can wrap it later.

**Default mode: direct apply.** Consolidation writes changes as normal
`apply` revisions. They sync on the next upstream cycle like any other
record change. `--dry-run` previews without writing; `--propose` uses the
propose/apply gate for cautious review (optional, not the default path).

**Phase 1: single-instance** — operates on one instance's memory records.
**Phase 2: cross-instance** — operates on a named subset of instances,
pulling records across them before the LLM pass (see §3b).

### 3a. Single-instance consolidation

1. **Select** — pull `type=memory` records for a subject/scope where
   `superseded_by` is null and `memory_class != consolidated`. Cheap once
   `memory_class` is an indexed first-class field (§2).
2. **Classify** — LLM tags each record:
   - `durable_fact` — standing project convention. Flagged in output for
     human promotion into AGENTS.md/CLAUDE.md; the job never edits those
     docs itself.
   - `episodic` — point-in-time event/decision. Eligible for merging.
   - `noise` — low-value. Superseded with no replacement record.
3. **Cluster + merge** — LLM groups near-duplicate/related `episodic`
   records and drafts a `consolidated` summary record per cluster.
4. **Write** (default: `apply` directly; `--propose` for review gate):
   - new `memory_class=consolidated` record with `source_record_ids`,
     `consolidation_run_id`, `consolidated_at` populated.
   - update each source record: set `superseded_by` → consolidated record
     id, `memory_class` → original class (preserved) or `noise`.
   - All writes go through normal `write_revision` / `propose_revision`
     — full revision history, DID-attributed, sync-ready.

### 3b. Cross-instance consolidation (Phase 2)

Same steps, but `--instances instance-a,instance-b` scopes the select to
records from multiple instances. Requires those instances to be reachable
(synced local copies, or direct server access). The LLM pass is identical;
the consolidated record is written back to the coordinating instance and
syncs out from there.

---

## 4. Drift check (separate, lighter, ongoing job)

For each `consolidated` record past some age/recall threshold:

1. Re-fetch the current revisions of all `source_record_ids`.
2. Ask the LLM: does the consolidated summary still accurately represent
   these sources?
3. Score drift (0–1). Above threshold → propose a refreshed summary via the
   same `propose`/`apply` flow as §3.4–5.

This is the main ongoing-maintenance loop once a corpus has been consolidated
once — it catches the "summary of a summary of a summary" degradation that
repeated consolidation would otherwise introduce.

---

## 5. CLI surface

```
hopper memory consolidate --subject <x> [--scope <y>]            # classify + merge, direct apply
hopper memory consolidate --subject <x> --dry-run                # preview only, no writes
hopper memory consolidate --subject <x> --propose                # write proposals for manual review
hopper memory consolidate --subject <x> --instances a,b          # cross-instance (Phase 2)
hopper memory drift-check [--id <consolidated-id>]               # re-verify summary vs sources

# Proposal review (only relevant when --propose used):
hopper revision list --pending --kind memory
hopper revision apply <revision-id>
hopper revision reject <revision-id>
```

No MCP-specific surface needed — the CLI commands work from any location
and the results sync through the normal upstream path.

---

## 6. Relationship to The Symposium's Sage memory architecture

Several concepts from `../thesymposium/docs/ideas/archive/2025-11/2025-11-17_Sage_Memory_Architecture.md`
and related Symposium memory docs informed this sketch, with framing adapted
for Hopper's operational (multi-agent task/knowledge store) context rather
than Sage consciousness/continuity:

- **"Dreaming" / consolidation as active reflection** (Sage Memory
  Architecture, Tier 3 + consolidation process) → §3: an authored
  consolidation pass, not silent background compression. The consolidated
  record itself is the "authored artifact" explaining what was merged and
  why.
- **Memory drift / reality checks**
  (`thesymposium/docs/guides/USER_GUIDE_MEMORY_DRIFT.md`) → §4: Hopper's
  revision history *is* the ground truth; drift-check re-derives summaries
  against it rather than against other summaries.
- **Graceful forgetting / non-destructive edits**
  (`thesymposium/docs/user-guides/MEMORY_EDITING_GUIDE.md`) → `superseded_by`
  via revision, never delete. Reframed from "agent's right to forget" to
  "provenance and reversibility in a shared, multi-author store."
- **Layer -1 (core identity) vs. situational memory**
  (`thesymposium/docs/ideas/Memory layer -1, core identity.md`) → the
  `episodic` vs `durable_fact` classification in §3.2. Reframed from
  "identity vs memory" to "does this belong in always-loaded project docs
  vs. the queryable memory store."

**Explicitly NOT adopted for Hopper**: Sage-specific identity/self-narrative
machinery (Layer -1 as a Sage's editable sense-of-self) and
memory-sovereignty-as-personhood framing. If a Sage later adopts Hopper as a
memory backend, that layer would sit *on top* as Sage-specific policy — it
is not something Hopper's consolidation feature needs to model.

---

## 7. Open questions — resolved 2026-06-16

### 7.1 Do `propose` revisions round-trip through upstream sync?

**Proposals do not sync; applied changes do — and the design works around
this by making direct apply the default.**

`propose_revision` (`storage/revision_writer.py`) deliberately does not
advance `Record.current_revision_id`. The sync path (`upstream/sync.py`) is
record-state-based and picks up records by `updated_at`, which only changes
on `apply`. Pending proposals are invisible to sync.

**Resolution:** the consolidation job defaults to `apply` directly, so
results sync like any other record change. The `--propose` flag is available
for cautious review but scopes the review to whoever has access to that
SQLite instance — not a centralized cross-instance capability. For the
common case (direct apply, results sync), any instance can run consolidation
and any other instance sees the results after the next sync cycle.

### 7.2 Can `memory list` filter on payload fields (`memory_class`, `superseded_by`)?

**Not via existing paths — but Python-side filtering is sufficient for now.**

Both backends support `kind` filtering:
- Markdown: `by_kind` index bucket (`storage/tasks.py:368`)
- SQLite: `_resolve_kinds` join + Python filter (`storage/sqlite_tasks.py:319`)

Neither has paths for arbitrary payload fields. `memory_class` and
`superseded_by` will need to be added as explicit `LocalTask` and `SyncTask`
fields — the same pattern used for `subject`, `scope`, and `provenance` in
the memory/kind first-class work. Until those fields exist, the consolidation
select step can query `kind=memory` (cheap, indexed) and filter in Python
(`getattr(task, 'memory_class', None)`, etc.) — viable for typical memory
corpora (tens to low hundreds of records).

**Resolution:** add `memory_class`, `superseded_by`, `source_record_ids`,
`consolidation_run_id`, `consolidated_at`, `drift_checked_at`, and
`drift_score` as explicit fields on `LocalTask` and `SyncTask` before
writing the consolidation job — same pattern as `subject/scope/provenance`.
This is the primary pre-implementation work item. Once these fields are
first-class, filtering, syncing, and cross-instance visibility all come
for free.

### 7.3 Schema drift from in-flight memory/kind work

Confirmed clean. The three commits that landed (56bb657 shadow kind-type
fix; c417100 FK repoint; 207d6ed tasks table drop) are additive/structural
and do not change `type=memory` payload conventions. The payload fields
proposed in §2 remain valid.
