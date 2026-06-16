# Tier 3 & Tier 5 Memory — Session Summaries and genmem

Status: **TIER 3 IMPLEMENTED** 2026-06-16. Tier 5 (genmem) pending server endpoint.
Date: 2026-06-16

References the 8-tier Sage Memory Architecture
(thesymposium/docs/ideas/archive/2025-11/2025-11-17_Sage_Memory_Architecture.md),
adapted for Hopper's operational context (tool for humans and agents, not
Sage consciousness).

See also: Memory-Consolidation-Plan.md (Tier 8 — implemented).

---

## Where Hopper sits today

| Tier | Description | Status |
|------|-------------|--------|
| 1–2 | Active attention / conversational context | Agent's context window — not Hopper's domain |
| 3 | Session memory — per-instance summary | **Gap** — `hopper context` gives recents but no LLM narrative |
| 4 | Relationship memory | Per-subject records (`subject=user:james`) — exists |
| 5 | Cross-instance patterns — genmem | **Gap** — not built |
| 6 | Self-narrative | AGENTS.md, knowledge base — partial |
| 7 | Semantic archive — full record corpus | Keyword search only (no embeddings; SQLite server rules out pgvector) |
| 8 | Deep storage — consolidated/superseded | Implemented (Memory-Consolidation-Plan.md) |

This plan covers Tiers 3 and 5. Tier 7 stays keyword for now; the LLM
summary layer at Tiers 3/5 provides the semantic lift without requiring a
vector index.

---

## Tier 3: Session Memory (per-instance summary)

### What it is

An LLM-generated narrative over the recent memory records and activity of a
single Hopper instance. Answers: "what has this instance learned and been
working on recently?" Fast context-load for an agent starting a session in
a known instance.

This is the thing that would have let the agent pick up a compacted
conversation without being pointed back at the raw source doc.

### Generation

1. Pull `kind=memory` records for the instance (last N records or since a
   date, excluding `memory_class=noise` and already-superseded records).
2. Pull recent task activity (open + recently completed tasks).
3. Single LLM call (Sonnet) → structured narrative:
   - What this instance knows (memory summary by subject)
   - What's currently in flight (open tasks)
   - What has recently completed
   - Any high-drift consolidated records worth flagging

### Storage

Optional `--save` flag writes the summary as a `kind=memory` record with
`memory_class=session_summary`. This lets it sync upstream and be
discoverable by other agents entering the instance. Without `--save` it
prints and discards — useful for one-off context loads.

### CLI surface

```bash
# Generate and print session summary for current instance
hopper memory session-summary

# Filter to a specific subject
hopper memory session-summary --subject project:waypoint

# Save as a memory record (syncs upstream)
hopper memory session-summary --save

# Look back further
hopper memory session-summary --since 2026-06-01
```

### Integration with `hopper context`

`hopper context` currently prints recent learnings + open tasks as raw
records. After Tier 3 is built, add an optional `--summary` flag that
runs the LLM pass instead of raw output:

```bash
hopper context --summary
```

---

## Tier 5: genmem (cross-instance summary)

### What it is

A named, on-demand summary spanning multiple Hopper instances. `genmem`
is the default name for the all-instances view. Other named subsets can
be defined (e.g. `rp-waypoint` for just those two).

Primary use case: writing in Waypoint about RP activity, where knowledge
is split across instances and the agent needs a coherent cross-cutting
view before querying specific instances for detail.

### The two-tier access pattern

```
Agent needs context
    → Load genmem (or named subset) → Tier 5 narrative
    → "I need more detail about the RP auth work"
    → Query rosetta_program instance directly → Tier 7 (keyword search)
```

### Cross-instance query — the key open problem

The server's `/tasks` endpoint currently serves a single instance's
records. To build genmem, we need memory records from all (or a named
subset of) instances in a single query.

**Option A — server-side endpoint** (preferred):
Add `GET /memory/cross-instance?instances=a,b&kind=memory` that queries
the records table across multiple `instance_id` values. The server already
holds all instances' records in one SQLite database — it's a filter change,
not an architectural one.

**Option B — client-side aggregation**:
Client queries each instance sequentially via the upstream API (once per
instance), aggregates locally, then runs the LLM pass. Slower, more
fragile, but requires no server changes.

Option A is cleaner and should be the target. Option B can ship as an
interim measure.

### Named memory sets

A named set is a lightweight config record stored in the local `.hopper`:

```yaml
# .hopper/memory-sets.yaml
genmem:
  instances: "*"          # all known instances
  subject_filter: null    # no subject filter
rp-waypoint:
  instances:
    - rosetta_program
    - waypoint
  subject_filter: null
```

If no `memory-sets.yaml` exists, `genmem` defaults to all known instances
(discovered from the server's instance list).

### Storage

genmem is a **local cached artifact**, not a synced record. Generated on
demand, stored in `.hopper/genmem-cache/<name>.md` with a timestamp. Stale
if older than a configurable threshold (default: 24h). Re-generated on
next access or on explicit `--refresh`.

The write-destination problem (where does a cross-instance consolidated
record live?) is deliberately avoided: genmem is a read-only view, not a
write operation.

### CLI surface

```bash
# Generate (or load cached) genmem for all instances
hopper memory genmem

# Force refresh
hopper memory genmem --refresh

# Named subset
hopper memory genmem --name rp-waypoint

# Ad-hoc instance selection (no saved set needed)
hopper memory genmem --instances rosetta_program,waypoint

# Filter by subject across instances
hopper memory genmem --subject project:rp

# Show cache age without regenerating
hopper memory genmem --status
```

---

## Tier 7 note

Keyword search (`hopper task search`) remains the Tier 7 drill-down
mechanism. SQLite on the server rules out pgvector. No embeddings planned.

This is acceptable because:
- Tier 3/5 LLM summaries handle the semantic retrieval problem for context loading
- Drill-down queries are typically specific (agent knows what it's looking for)
- Keyword search on `subject=`, `scope=`, and text is sufficient for precise retrieval

Revisit if/when the memory corpus grows to a point where keyword breaks down
(many records with similar text, poor subject/scope discipline, etc.).

---

## Implementation order

1. **Tier 3: `hopper memory session-summary`** — self-contained, no new
   server capability needed. Ships first. Add `--summary` to `hopper context`.

2. **Server cross-instance endpoint** — prerequisite for Tier 5. Small
   change: filter records table by a list of instance_ids.

3. **Tier 5: `hopper memory genmem`** — builds on the endpoint + named
   sets config. `memory-sets.yaml` is simple enough to be hand-edited
   initially; no UI needed yet.

---

## Open questions

- **Named set discovery**: how does an agent in Waypoint know that
  `rp-waypoint` is a defined set? Needs either a `hopper memory sets list`
  command or convention that agents check `memory-sets.yaml` on start.

- **Cache invalidation**: 24h default reasonable? Or should genmem refresh
  automatically after any upstream sync that pulled new memory records?

- **Session summary frequency**: should `hopper memory session-summary
  --save` replace the previous session summary, or accumulate them?
  Accumulation gives history but adds noise. Replacement is simpler.
  Suggested default: replace (keep only the latest per instance per subject).
