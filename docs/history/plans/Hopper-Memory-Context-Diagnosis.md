# Hopper Memory & Context — Diagnosis and Plan

Status: **COMPLETE.** All Phases shipped and running in production.
Date: 2026-06-15 (Phases 4–6 + dead-code sweep)

Done:
- Client: kind/type first-class (markdown+sqlite), memory structured fields,
  JOB kind, context shows Memory, view segmentation, dry-run migration (0.1/0.2/1/2).
- Server MCP (both SSE + stdio): first-class kinds, subject/scope/provenance,
  kind segmentation, kind-based memory retrieval; legacy tag guidance replaced.
- Upstream sync protocol: kind/subject/scope/provenance now survive every hop
  (were silently dropped at all of them); backward-compatible.
- REST API: records/revisions-backed behind `HOPPER_API_RECORDS_BACKEND` (default
  ON), kind-segmented; legacy `tasks` table retired (see Phase 4–5 below).
- **MCP instance-scope bug FIXED** (see §7): `_get_client()` recovers instance
  from durable DID affinity on session-cache miss and refuses silent wrong-scope
  fallback for authenticated multi-instance DIDs.
- Bug fix: `shadow.py::_ensure_instance` raw INSERT omitted NOT-NULL
  `instance_type` and stored enum values instead of names — every records write on
  a fresh DB would have crashed / been ORM-unreadable. Fixed + regression test.
- **Phase 4 (2026-06-15):** Re-pointed `task_feedback`, `routing_decisions`,
  `task_delegations`, `external_mappings` FKs from `tasks.id` → `records.id`
  (migration `c3d4e5f6a7b8`). Required removing dead ORM relationships between
  Task and its child models.
- **Phase 5 (2026-06-15):** Dropped the `tasks` table (migration `d5e6f7a8b9c0`).
  Table had 0 rows in production; backup taken before drop.
- **Phase 6 / shadow backfill (2026-06-15):** Ran `scripts/backfill_revisions.py`
  against production `shadow.db`: 332 records created, 9 retyped, 1559 skipped,
  0 errors. Shadow DB now at 1902 records / 16700 revisions.
- **Shadow writer bug fixed (commit 56bb657):** `RevisionShadowWriter` hardcoded
  `Record.type = "task"` regardless of payload `kind`. Fixed to derive type from
  `task_payload.get("kind", "task")` via the `RecordType` enum. Regression test
  added in `tests/storage/test_shadow_writer_kind.py`.
- **Dead code sweep (2026-06-16):** Removed `Task` ORM model, `TaskRepository`,
  `sqlite_tasks.py`, and all server-side callers. Intelligence/memory layer type
  signatures updated to `Any`; Task-table queries stubbed to return empty (no data
  exists). Production routes (delegations, learning, instances) updated to query
  `Record` instead of `Task`.

§5 decision (recorded 2026-06-15): **SQLite = server-side canonical memory home.
Local/markdown instances remain task-only.** No markdown memory migration required.
The tasks table is the only table dropped; the records/revisions/shadow pipeline is
the durable path for cross-agent memory.

The 4 OAuth failures are pre-existing and (per server-side notes) may relate to
HOPPER_PUBLIC_URL audience validation behind nginx — worth a separate look.
Date: 2026-05-31 (original diagnosis)
Triggered by: heavy real-world use in `~/Source/Rosetta_Program` (RP), which holds
~1253 records and ~50 "memories", syncs to a server, and where
`hopper context` reports "No learnings captured yet."

---

## 1. What's actually wrong

### Finding A — `hopper context` can never show memories (display bug, but worse than it looks)

`context show` builds its "Recent Learnings" section from
`list_tasks(tags="auto-learned")` (`cli/commands/context.py:90`). Grepping all of
`src/`: **`auto-learned` is only ever read, never written** — not by `task add`,
not by `memory add`, not by the learning engine. So that section is structurally
guaranteed to print "No learnings captured yet" forever.

In the *same* command, the "Open Tasks" section explicitly filters out anything
tagged `memory` **or** `auto-learned` (`context.py:96-101`). Net effect: memory
records are absent from **both** sections. The one command `CLAUDE.md` tells every
agent to run at session start is the one command that hides the stored knowledge.

`context` was clearly written around an `auto-learned` auto-extraction feature
that was never built, and was never revisited when `hopper memory` shipped as the
real knowledge path. The "filter `memory` out of tasks" line is the fingerprint:
someone saw memories polluting the task list and suppressed them instead of giving
them a home.

### Finding B — memory is a tag on a task, even though the schema already has a first-class type

The data model already supports memory as a first-class citizen:

- `RecordType.MEMORY = "memory"` (`models/enums.py:132`) — documented as
  "agent knowledge, first-class across agents (attributed by author DID)."
- `Record.type` is a real, indexed column (`models/record.py:23,39`).

But the CLI write path takes a shortcut. `hopper memory add` (`cli/commands/kinds.py`)
is a thin wrapper over `hopper task add` that just prepends a `memory` tag and a
text preamble. The file says so out loud: *"intentionally storage-layer-free…
until Phase 4a's live write path is wired, kind is encoded as a tag on the
underlying task record."* That wiring never happened.

Neither storage backend can actually **query** by kind:

- **markdown backend** (`storage/tasks.py`): `kind` is written to frontmatter
  (`tasks.py:165`) but `TaskStore.list()` filters only by status/priority/tags/
  project — there is no `by_kind` index and no `kind` filter. The only handle that
  makes a memory findable is the `memory` *tag*.
- **sqlite backend** (`storage/sqlite_tasks.py:63-65`): the tasks table doesn't
  even read kind back — it's hardcoded `kind = "task"`, with a comment that the
  real type "lives in records.type … via the revision payload," which the task
  store never joins.

So `RecordType.MEMORY` is real in the schema and dead in every query path. Memories
*are* tasks today. That's the thing to undo.

### Finding C — `config.yaml`'s `sync:` block lies about sync

RP's `config.yaml` says:

```yaml
sync:
  enabled: false
  server_url: null
  sync_episodes: false
  sync_patterns: true
```

…yet `hopper sync` pulls tasks from a server every time. The reason: this `sync`
block configures the **legacy learning-engine sync** (note the `sync_episodes` /
`sync_patterns` siblings — those are routing-ML knobs). The real sync runs through
the **`upstream`** subsystem (the `.sync_state_*` files, DID-signed record/revision
exchange) and ignores this block entirely. A user reading `config.yaml` concludes
sync is off when it is fully operational. The two sync systems share a name and
nothing else.

### Finding D (context for the above) — "learning" ≠ "memory" ≠ "auto-learned"

Three overlapping names, three different things:

| Surface | Backed by | Populated? |
|---|---|---|
| `hopper memory` | tasks tagged `memory` | yes (~50 in RP) |
| `hopper context` "Recent Learnings" | tasks tagged `auto-learned` | never (dead tag) |
| `hopper learning` | routing ML: episodic memory, patterns, semantic search, routing-accuracy feedback (Phase 2/3) | empty — it optimizes delegation routing; not a knowledge store |

`hopper learning` being empty is **not** a bug and not about single-instance — it's
a routing optimizer that only fills up when routing feedback is submitted. It has
nothing to do with the memories.

---

## 2. Target model

A **memory** is a first-class `RecordType.MEMORY` record. It is **not a task**:

- no status lifecycle (no open/in_progress/done), no priority semantics;
- queryable by `type`, not by a magic tag;
- DID-attributed (author identity), so it is meaningful "across agents";
- syncs through the `upstream` record/revision path like any other record;
- surfaced by `hopper context` as the knowledge layer for anyone asking for context.

`hopper context` = "give me the relevant memory for this project," plus (separately)
open tasks. Memory is the headline; tasks are secondary.

---

## 3. Plan (phased; each phase independently shippable)

### Phase 0 — truth in display & config (small, high-value, low-risk)

0.1 `cli/commands/context.py`
- Rename/repoint the top section from "Recent Learnings" (`tags="auto-learned"`)
  to **"Memory"**, sourced from memory records. In the interim (before Phase 2's
  query path) source it from `tags="memory"` so it works on today's data; swap to
  the type query once Phase 1 lands. Keep the JSON output key stable or version it.
- Stop suppressing memory from view. Memory gets its own section; the Open Tasks
  filter for `memory`/`auto-learned` becomes unnecessary once memories aren't tasks,
  but keep filtering `memory`-tagged tasks out of Open Tasks during the transition.
- Add a regression test in `tests/cli/` asserting a stored memory appears in
  `hopper context` output (the test that would have caught this originally).

0.2 `config.yaml` sync block
- Decide: either (a) remove the legacy `sync:` block from the local config schema
  and templates and let `upstream` own sync, or (b) make `hopper sync`/status read
  and reflect it. Recommend (a) + a one-line `upstream:` stanza that mirrors actual
  state, so `config.yaml` stops contradicting `hopper sync`. Update
  `.env.template` / `config/` defaults and `docs/` accordingly.
- Add `hopper sync status` (or extend existing) to print the real upstream target
  and last-sync time from `.sync_state_*`, so the source of truth is a command, not
  a stale file.

### Phase 1 — make `kind`/`type` queryable (unblocks everything)

1.1 markdown backend (`storage/tasks.py`, `storage/markdown.py`)
- Add a `by_kind` bucket to the index; index `kind` on write.
- Add a `kind` filter to `TaskStore.list()` and thread it through
  `local_client.list_tasks`.

1.2 sqlite backend (`storage/sqlite_tasks.py`)
- Stop hardcoding `kind="task"`; read the record's `type` (join `records.type` /
  revision payload as the comment anticipates).

1.3 No behavior change for users yet — this is plumbing so kind is a real query
dimension on both backends.

### Phase 2 — memory as a first-class record (not a task)

2.1 Write path
- `hopper memory add` writes a `type=memory` record directly (via the
  records/revisions path on sqlite; via a memory-aware store on markdown) instead
  of `add_task(..., tag=memory)`. Keep the `--subject/--scope/--provenance`
  structured fields — promote them from a text preamble into real payload fields.

2.2 Read path
- A dedicated retrieval API (e.g. `list_memory()` / filter by `type=memory`)
  decoupled from the task list. `hopper memory list` and `hopper context` both use it.
- `hopper context` Memory section now reads via this API (drop the tag fallback
  from 0.1).

2.3 Migration
- One-time migration for existing `memory`-tagged tasks → `type=memory` records
  (RP has ~50; do it idempotently, keep IDs/timestamps, attribute to the original
  author DID where present). Provide `hopper memory migrate --dry-run`.

### Phase 3 — cross-agent / sync correctness for memory

3.1 DID attribution
- RP currently has **no `did.key`** yet writes succeed and sync runs. Memories
  written without a DID can't be attributed "across agents." Decide policy: require
  a DID for memory writes (consistent with recent `enforce DID on every write`
  commits) or auto-provision one on `hopper init`. Surface a clear error/onboarding
  path rather than silent unattributed memory.

3.2 Sync coverage
- Confirm `type=memory` records flow through the `upstream` record/revision sync
  the same as tasks, and that conflict/merge semantics make sense for append-mostly
  knowledge. Add an integration test under `tests/integration/` or `tests/api/`.

---

## 4. Suggested order & sizing

| Phase | Effort | Risk | User-visible win |
|---|---|---|---|
| 0.1 context fix + test | S | low | memories show up at session start immediately |
| 0.2 config/sync truth | S | low | `config.yaml` stops lying |
| 1 kind queryable | M | low | plumbing; no UX change |
| 2 memory first-class + migrate | M–L | med | memory stops being a task |
| 3 DID + sync | M | med | cross-agent memory actually works |

Phase 0 alone resolves the reported symptom and is safe to ship on its own.
Phases 1–3 deliver the "memories aren't tasks" model you asked for.

## 5. Open questions for review

- **Markdown vs SQLite for the memory home.** First-class records/revisions/DID
  live on the SQLite backend; RP is markdown. Do we (a) bring first-class memory to
  the markdown backend too, or (b) treat SQLite as the path for anyone who wants
  real cross-agent memory and document markdown as task-only? This is the biggest
  fork in the plan.
- Should `hopper context` show memory scoped to the current project only, or all
  shared-across-agents memory regardless of project?
- Retire the `auto-learned` tag entirely, or keep it as a hook for a future
  auto-extraction feature (and actually populate it)?

---

## 6. Legacy cruft inventory (RP + local `Source/hopper/.hopper`)

RP is one of the first Hopper instances; the local repo instance is also early.
Both were inspected. Findings split into convention drift (affects everyone),
stray files (instance-local), and data hygiene (RP's heavy real-world use).

### 6a. Schema / convention drift — systemic, both instances

- **Status vocabulary is forked.** On-disk markdown uses
  `open / completed / cancelled / in_progress / blocked`. The SQLAlchemy
  `TaskStatus` enum (`models/enums.py:8`) uses
  `pending / claimed / in_progress / blocked / done / cancelled`.
  So `completed`≠`done`, `open`≠`pending`, `claimed` is unused on disk. The
  `config.yaml` default `status: pending` yields a value the markdown vocab never
  otherwise produces. Two layers, two vocabularies. → Pick one canonical set and
  map the other at the boundary; fix the config default.
- **`sync:` block is legacy learning-engine config** (Finding C) — present in both
  instances, contradicts real `upstream` sync.
- **Dead directories.** `.hopper/memory/` and `.hopper/feedback/` exist and are
  **empty in both instances** — scaffolding for a layout that was never used
  (memory became a tag; feedback lives elsewhere). → remove from `init` scaffolding
  or actually wire them up.
- **`by_project` is empty** in both indexes — the projects feature has never been
  used in these instances.

### 6b. Stray files — local `Source/hopper/.hopper`

- **Orphaned `.sync_state`** (no instance suffix, last_sync ~2026-04-16),
  superseded by `.sync_state_hopper` (~2026-04-24). Pre-dates the
  `.sync_state_<instance_id>` convention; current code never reads it. → delete.
- **Stray root `hopper.db`** — full schema + `alembic_version`, but **0 records /
  0 tasks / 0 revisions**. Gitignored, untracked, unused (configured backend is
  markdown). Leftover from a server run or migration at repo root. → delete.
- **Stale index** — local `.index/tasks.json` `generated_at` is 2026-05-10 (~3
  weeks stale); RP's regenerates. → index should rebuild on read or on a hook.

### 6c. Data hygiene — RP (the 1254-record instance)

- **GPU jobs are a first-class use case, not pollution.** 997 / 1254 records
  (79%) are tagged `gpu-job` (1073 terminal). Hopper is deliberately used as a job
  engine (`rosetta_tools/bin/gpu_queue.sh` etc.) and that is valued — **the fix is
  not to purge them.** The problem is only that they share the `task` namespace and
  so swamp `task list` / `context` / memory views. → **Decision (2026-05-30): give
  jobs a dedicated `RecordType.JOB` (or formalize `gpu-job`) and exclude that type
  from the default task/context/memory reports, with a dedicated `hopper job`
  view.** No deletion. Terminal-job archival can be offered as an opt-in later, but
  is not required.
- **Fragmented memory tags.** Knowledge is spread across four conventions from
  different import passes: `memory` (86), `claude-import` (46),
  `claude-memory-project` (31), `claude-memory-feedback` (12). → consolidate under
  the first-class `type=memory` record in Phase 2; the migration there should fold
  all four.
- **Tag sprawl + malformed tags.** 133 distinct tags. `research,tooling` (×3) is a
  single comma-joined tag — a CLI quoting bug (`--tag "research,tooling"` instead of
  two `--tag` flags); the wrapper should split-or-reject commas in tag values.
  `reconciled-2026-05-30` (×23) is a dated housekeeping marker left in the live set.
  → normalize tags, split comma tags, consider a light taxonomy / `tag` lint.

### 6d. Proposed cleanup, by safety tier

| Tier | Action | Reversible? | Needs confirm |
|---|---|---|---|
| Safe | Delete local orphan `.sync_state` and empty root `hopper.db` | yes (regenerable) | low |
| Safe | Drop empty `memory/` + `feedback/` dirs from scaffolding | yes | low |
| Safe | Fix `config.yaml` `status` default + sync block (Phase 0.2) | yes | low |
| Care | Split/clean malformed + dated tags across RP | yes (data edit) | **yes** |
| Care | Reconcile status vocabulary (code + one-time data pass) | yes | **yes** |
| Feature | Add `RecordType.JOB`, exclude from default reports, `hopper job` view; reclassify existing `gpu-job` records | yes (non-lossy) | **yes** |
| Feature | Consolidate 4 memory tag families → `type=memory` (Phase 2 migration) | yes (idempotent) | **yes** |

Nothing in the "Care" or "Feature" tiers will be touched without explicit sign-off.

### Decisions recorded (2026-05-30)
- **Keep GPU jobs in Hopper** — it is a valued job engine. Solve the noise with a
  dedicated job type excluded from default views, **not** by deleting records.
- **Plan only this session** — no code or data changes executed. This document is
  the deliverable; sequencing of fixes comes next.

---

## 7. MCP instance-scope bug (trust-critical) — diagnosis & fix

Symptom (reported from live use): after `hopper_switch_instance("Rosetta_Program")`,
later `list_tasks` calls silently returned a different instance's data
(`"instance": "local"`), gpu-job filters returned 0, known tasks returned
"Task not found" — with no error signalling scope loss.

Root cause: `mcp_sse.py` holds session→instance in a module-level in-memory dict
`_session_instances` (per-process). `_get_client()` read only that dict and, on a
miss, **silently returned `LocalClient()`** — the server's own `~/.hopper`
("local"). Misses occur (a) cross-worker (`hopper server start --workers N`: the
dict is per-process), and (b) on the stale-session reroute through the stateless
StreamableHTTP manager (a reconnect with an unknown session id has no dict entry).
The durable DID→instance affinity (`did_registry.get_last_instance`) existed but
`_get_client()` never consulted it on a miss.

Fix (`mcp_sse.py`): on a session-cache miss, resolve the instance from the durable
DID affinity (shared across workers/restarts) and repopulate the cache; if an
authenticated DID associated with upstream instances still can't resolve one,
return a clear "call switch_instance" error instead of silent local data; preserve
the legitimate local/anonymous `LocalClient` path; log fallbacks. Sibling misreport
in `hopper_instructions` (line ~1033) fixed too. Regression tests in
`tests/api/test_mcp_instance_scope.py`.

Related, NOT yet fixed (noted in server-side overview): `_session_instances` is
never cleaned up for Streamable HTTP sessions — it accumulates for the process
lifetime (a slow leak). Candidate follow-up.
