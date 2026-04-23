# Phase 4 — Revisioned records, DID+location signal, agent as first-class actor

Status: proposed (2026-04-22)
Target host: ember (1 vCPU / 1.9 GB RAM / 49 GB disk, no GPU)
Primary storage: SQLite (remain single-file, portable)
Agent inference: Anthropic API only (no local LLM on ember)

## Motivation

Hopper is now used as a cross-context personal Swiss-army knife:
- Rosetta_Program: GPU task controller (status-tracked, high-volume).
- Waypoint: idea backlog, session notes, published-record log (no lifecycle, synthesis-oriented).
- Hopper itself: its own development tracking.

All three force records through one `task` shape. Tags paper over the mismatch. Triage load is growing and there is no attribution trail for agent edits.

Three capabilities we need:
1. **Revisioned records** — append-only history, non-destructive updates, safe agent proposals with rollback.
2. **DID + location signal** — attribute every write to a principal and the context of their action (me-from-phone vs audit-agent@ember).
3. **Agent as first-class actor** — agents have DIDs, default to `propose`, earn `apply` rights per record-type.

## Non-goals (for this phase)

- No move to Postgres. SQLite stays.
- No local LLM inference on ember.
- No breaking change to the markdown storage backend. Markdown remains a valid projection; revisions are authoritative only in the SQL backend.
- No record-type explosion. Start with `task`, `idea`, `note`, `log`. Others added when earned.

## Architecture

### Storage model (SQLite)

```
records
  id                TEXT PRIMARY KEY
  type              TEXT NOT NULL        -- 'task' | 'idea' | 'note' | 'log'
  current_revision  TEXT NOT NULL        -- FK revisions.id
  created_at        TIMESTAMP
  tombstoned_at     TIMESTAMP NULL

revisions
  id                TEXT PRIMARY KEY     -- ULID
  record_id         TEXT NOT NULL FK
  parent_revision   TEXT NULL FK         -- prior revision of this record
  action            TEXT NOT NULL        -- 'create' | 'update' | 'propose' | 'apply' | 'reject' | 'tombstone'
  author_did        TEXT NOT NULL        -- principal DID
  author_location   TEXT NOT NULL        -- context token: phone-claude | ember-cli | web-chat | rosetta-agent | audit-agent@ember
  payload           JSON NOT NULL        -- full record snapshot at this revision
  schema_version    INT NOT NULL
  created_at        TIMESTAMP

INDEX revisions(record_id, created_at DESC)
INDEX revisions(author_did)
INDEX revisions(action) WHERE action = 'propose'
```

**Rules:**
- Never UPDATE revisions. Only INSERT.
- `records.current_revision` points at the latest applied revision.
- Proposed revisions exist in `revisions` with `action='propose'`; they do NOT advance `current_revision` until followed by an `apply`.
- `tombstone` is an action, not a delete. Records never leave the database.

### DID + location

**DIDs already exist.** Server at `~/.hopper/upstream-data/` uses `did:key:...` (Ed25519-derived) with a namespace registry (admin DID, per-instance approvals, pending/approved states). Every incoming write already carries `from_did`. What's missing is revision-level persistence — today that DID survives only as the attribution of the *most recent* sync, not per-write history.

- **Principal DID** identifies *who*: existing `did:key:...` DIDs for me-from-various-places; agents get their own (`did:key:...` for `audit-agent@ember`, `rosetta-agent@rosetta-host`).
- **Location** identifies *context*: `phone-claude`, `ember-cli`, `web-chat`, `waypoint-skill`, `rosetta-gpu-controller`, `audit-agent@ember`. The existing `source` field on tasks is a proto-location (currently just `"cli"`) — we expand it and make it per-write.
- Every revision carries both. Queryable for signal: "ideas dropped from phone-claude after 22:00" is a real query.

**Key change from today:** the transport-layer `from_did` that exists at sync time must persist into every revision. Right now the CLI and markdown storage path erases it on the way down. Phase 4a ends that erasure.

### Agent as first-class actor

- Agent DIDs are recorded, visible in `hopper task history`.
- Default action for agent writes: `propose`.
- Promotion to `apply`:
  - Manual: user issues `hopper revision apply <revision-id>`.
  - Rule-based: deterministic rules in config promote matching proposals directly (tag normalization, obvious duplicates, stale-session close).
  - Trust-based (later): per-(agent, record-type) accept rates earn auto-apply.
- Rollback: `hopper revision reject --author did:hopper:audit-agent@ember --since 2026-04-22` inserts `reject` revisions across the scoped set; `current_revision` reverts to the last non-rejected applied revision per record. No data loss.

## Phasing

Each phase is independently mergeable and reversible.

### Phase 4a — Turn on SQLite with revisions native from day one

**Context:** SQLAlchemy models and alembic exist in the repo but have never been used in production. Current reality is markdown-only. This phase is not "add revisions to an existing SQL backend" — it is "finally activate the SQL backend, and have revisions be there on arrival."

Scope:
- Revise the existing `tasks` model alongside the new `records` + `revisions` tables (or collapse `tasks` into `records` — decide during design).
- Alembic migration: create `records` + `revisions` (plus whatever survives of `tasks`, or drop it entirely since no live data depends on it).
- Backfill one-shot: walk the server store at `~/.hopper/upstream-data/tasks/<instance>/*.json` (the authoritative source on ember; markdown files downstream are caches). Produce one `records` row + one `create` revision per task file. `author_did` backfills from the JSON's `from_did` field; `author_location` backfills from `task.source` (typically `"cli"` → normalized to `ember-cli` for existing rows).
- Storage config: add `storage.type: sqlite` alongside existing `markdown`. Default stays `markdown` for existing users. New instances (and ember's service) can opt into `sqlite`.
- Read/write path: if `storage.type: sqlite`, all reads/writes go through the SQL repository and generate revisions natively. Markdown backend remains untouched.
- **Blast radius: zero on existing users** who stay on markdown. Ember's running instance switches to SQLite as part of this phase's rollout.

Exit criteria:
- Ember's Hopper service runs on SQLite with revisions populated on every write.
- Backfill from ember's existing markdown produces revisions indistinguishable from native writes.
- Markdown users are unaffected.

### Phase 4b — DID + location on writes

Scope:
- `revisions.author_did` and `author_location` populated on every write.
- CLI: `hopper` commands infer location from the invocation context (env var, sub-flag); agent callers must pass `--author-did` / `--author-location` or their request is rejected.
- MCP: pass caller identity through from the client.
- `hopper task history <id>` surfaces author+location per revision.

Exit criteria: no revision row with null DID or location in the prior 24h.

### Phase 4c — Record types beyond `task`

Scope:
- `type` column already exists on records; populated as `task` for all backfilled rows.
- Add CLI: `hopper idea add`, `hopper note add`, `hopper log add` — thin wrappers that set type correctly.
- Add CLI: `hopper ls --type idea`.
- Per-type default rendering in the list view (ideas don't show status, logs are reverse-chron, etc.).
- No schema change; types are a column value.

Exit criteria: Waypoint `idea`-tagged tasks migrated to `type=idea` via a one-shot script. Rosetta's GPU tasks stay `type=task`.

### Phase 4d — Proposal workflow

Scope:
- Introduce `action='propose'` writes via a flag: `hopper task update <id> --propose`.
- `hopper revision list --pending` surfaces unresolved proposals.
- `hopper revision apply|reject <revision-id>` commands.
- Rule engine (YAML config): match on (author_did, record_type, payload_diff) → auto-apply.

Exit criteria: an agent can be pointed at the store, propose changes, and have them surfaced for human review without touching current state.

### Phase 4e — Audit agent v0 (ember)

Scope:
- Minimal Python service, single-threaded, calls Anthropic API.
- Subscribes to new revisions (poll SQLite or SQLite file watcher).
- Two jobs only for v0:
  1. Tag normalization (cheap, rule-based, auto-apply).
  2. Idea synthesis digest — weekly, looks at all `type=idea` revisions in the past 7 days, proposes a markdown summary as a `type=note` record. Writes as proposals only.
- Memory budget: <200 MB. Latency budget: single API call per job.
- Explicit DID: `did:hopper:audit-agent@ember`, location: `audit-agent@ember`.

Exit criteria: agent runs for one week without pegging ember, produces at least one accepted synthesis digest.

## Reconciliation with `t606a17a0` — inbox + on-demand triage

Task `t606a17a0` (captured 2026-04-18) sketched the *lifecycle* side of
this same problem: how items get classified into terminal kinds without
forcing users to decide at capture time. It is complementary to Phase 4,
not a competitor. Phase 4 owns storage and attribution; t606a17a0 owns
classification and staleness. They fit together as follows.

**Kind set.** The combined set, superseding both earlier drafts:
`inbox` (default for untriaged captures), `task`, `idea`, `note`,
`memory`, `reference`, `log`. `inbox` is the bootstrap kind the triage
agent moves items *out of*; the others are terminal. Phase 4c adds these
values to `RecordType`.

**`memory` is first-class, not an afterthought.** Claude has its own
auto-memory system today; other agents (Rosetta, audit-agent, future
agents) have no comparable infrastructure. Locking agent knowledge into
vendor-specific stores fragments the surface — you cannot query "what
do my agents collectively know about this topic" and you cannot let a
new agent inherit learned context from its predecessors. `type=memory`
in Hopper fixes this: every agent writes memories under its DID, the
same store serves all agents, revisions track how memories evolve,
triage handles staleness. The existing routing-memory system at
`src/hopper/memory/` is orthogonal — it solves "which instance should
this task go to," not "what does this agent know."

Expected memory payload shape (Phase 4c documents, Phase 4e starts
using):
- `subject`: what the memory is about (`user:preferences`,
  `project:waypoint`, `agent:rosetta-agent`, `self`).
- `scope`: `private` (author DID only), `shared-with-user`,
  `shared-across-agents`.
- `content`: prose, structured JSON fact, or both.
- `provenance`: how it was learned (conversation, observation,
  inference from other memories).
- `confidence`: 0.0–1.0 (optional; not all memories carry this).
- `last_used`, `last_triage`, `taxonomy_version`: staleness tracking
  from the t606a17a0 convention.

Claude's existing `.claude/projects/.../memory/MEMORY.md` format stays
untouched in Phase 4. A later integration (out of scope here) can
bridge Claude memories into Hopper `type=memory` records via an MCP
tool or hook, giving other agents read access to what Claude knows
without forcing Claude to change its storage.

**Capture vs. triage.** Both styles coexist:
- `hopper note "..."` captures to `type=inbox`. Triage moves it later.
- `hopper idea add "..."`, `hopper task add "..."`, etc. set the kind at
  capture for cases where the user already knows. Pre-typed items are
  not re-triaged unless explicitly requested.

**Triage as a revision.** Re-classification by a triage agent is just a
revision — `action='update'` (or `action='triage'` if we want the
semantic distinction) carrying the new `type` and fresh `last_triage`
and `taxonomy_version` in the payload. Attribution survives naturally:
the revision records who triaged, from where, and when.

**Agent convergence.** Multiple agents can triage the same item; the
propose/apply model (Phase 4d) handles conflicts without last-write-
wins racing. Agents read the same versioned rubric at
`.hopper/knowledge/triage-rubric.md` and propose; a trust-earning
agent auto-applies, others surface proposals for review.

**Staleness query.** t606a17a0's `last_triage IS NULL OR updated_at >
last_triage OR taxonomy_version < current` becomes a straightforward
query over the current revision's payload. No new columns needed at
the storage level; the triage metadata lives in the JSON payload of the
latest revision.

**Bootstrap.** `inbox` must be in `RecordType` before any capture-side
CLI wrappers ship, or the default for `hopper note` has nowhere to
land. Phase 4c lands the enum change and the `inbox` default together.

## What this phase explicitly does NOT do

- No knowledge graph, no embeddings, no RAG. Those can come later; they are independent of the revision/DID/agent foundation. Starting them before the foundation means ripping them up when the foundation lands.
- No Rosetta-specific agent. Rosetta runs its own classification where its GPU tasks run.
- No schema migration from markdown → SQL for existing local-only instances. Users opt in via config.

## First concrete step

Implement Phase 4a (revisions schema + backfill) as a single alembic migration + one code path change (double-write on task create/update). Everything else builds on it.
