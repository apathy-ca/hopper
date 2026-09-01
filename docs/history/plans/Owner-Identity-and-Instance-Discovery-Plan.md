# Owner identity — grouping DIDs under a person, and instance-aware `hopper init`

Status: **IMPLEMENTED** 2026-08-31 (Phases A–E, same session as this doc's
first draft). Not yet deployed to `hopper.henrynet.ca` or
`~/.hopper-install` — implementation lives in this source tree only,
verified against a local throwaway server instance. See "Implementation
notes" at the end for what shipped, what got fixed along the way, and how
the open questions below actually resolved.
Date: 2026-08-31

## Motivation

Hopper's authorization model has no concept above the DID. Every device key
is a fully independent principal: approval is per-(DID, namespace), or
per-DID via the `"*"` global sentinel. Nothing in the server knows "these
five DIDs are all the same person."

In practice, one person accumulates many DIDs — one per machine, sometimes
more than one per machine over time (key rotation, a fresh `hopper upstream
init` run by an agent that didn't know a key already existed). Today that
means:

- **New devices fork silently.** `hopper init` defaults the instance name to
  `Path.cwd().name` (`config.py`). A fresh checkout, a differently-named
  directory, or an agent working in a scratch worktree produces a brand new
  instance name with no signal that an existing instance already holds the
  relevant work. The DID then either fails outright (`"DID not approved for
  namespace '...'"`) — the *good* outcome, at least it's loud — or, if
  someone has granted that DID `"*"`, it silently starts writing into a
  namespace nobody is watching.
- **No cross-DID visibility.** There is no query for "show me every
  namespace any of my devices can reach." `hopper upstream admin list` and
  `admin pending` are namespace/global admin operations, not owner-scoped —
  and the DID actually used day-to-day may not even *be* the registered
  `admin_did` (whichever key first bootstrapped a given server instance),
  in which case those commands are unavailable entirely from the machine
  where most work happens.
- **People have more than one email identity.** The server this design
  targets (`hopper.henrynet.ca`) was bootstrapped under a `henrynet.ca`
  identity; the owner now primarily operates under `eigan.ai`. Any "owner =
  one email" model breaks on day one for its own author.

### Concrete incident (motivating case study)

Rosetta_Program's own `CLAUDE.md` has claimed since inception that
`.hopper/` lives "in this directory." It never has — every RP-flavored task
(157 of 266 on the `eigan` instance, by rough keyword match) has actually
lived one directory up, in the shared `Games2/Eigan/.hopper` instance,
because everyone doing RP work has always been `cd`'d there when running
`hopper` commands. A June 2026 planning doc (`Tier3-Tier5-Memory-Plan.md`)
even names `rosetta_program` as a distinct instance from `eigan` — the
design anticipated the split; the split just never actually happened,
because nothing at `hopper init` time ever surfaced "eigan already has this
work, did you mean that one?"

Tested directly against `hopper.henrynet.ca` under the owner's real
production DID: both `rosetta_program` and `Rosetta_Program` namespaces
exist as *possible* default names (case-sensitive, `Path.cwd().name`) and
both are correctly rejected today (`"DID not approved for namespace"`).
That's the system working as designed — but "working as designed" here
means "any agent that ever runs `hopper init` from a directory named either
of those strings gets a hard failure with no indication that `eigan` was
almost certainly what was wanted." The failure mode this plan targets is
the case where that DID *does* have blanket (`"*"`) access — nothing stops
the silent fork in that case.

## Non-goals

- No multi-tenant SaaS user model. `Org` (Phase E) is a lightweight
  grouping principal for shared grants — closer to a Unix group than a
  tenant — not isolated accounts, billing, or data-plane separation.
- No SSO/OAuth/magic-link email verification. Owner↔email linking is
  admin-asserted, matching the trust level of every other write in the
  current `DIDRegistry` (a JSON file an admin/approver edits via CLI calls
  — nothing here is cryptographically stronger than that today, and this
  plan doesn't change that).
- No cryptographic delegation chain (DID-controller documents, verifiable
  credentials). The existing registry authorizes by checking "is this DID
  string present in this JSON," not by verifying a signed claim of
  ownership. Owner grants extend that same pragmatic model rather than
  introducing a second, stronger one inconsistently.
- No change to the existing per-DID / per-namespace grant path. A DID that
  isn't linked to any owner behaves exactly as it does today — this matters
  for actual external collaborators who should *not* inherit blanket owner
  access.
- No automatic backfill/relabeling of existing namespace history. Linking
  today's already-active DIDs to an owner is a one-time manual step
  (`owner link-did`), not something this plan infers from `source` fields
  or task content.

## Architecture

This plan introduces principal kinds that sit above the DID: **Owner** (a
person) first, then **Org** (a group of owners) as a sibling kind that
reuses the identical storage and grant-resolution pattern. Owner is
Phases A–D below; Org extends the same mechanism in Phase E.

### Storage: new `Owner` record, parallel to the existing per-DID file store

`storage.py`'s `DIDRegistry` already persists one JSON file per DID, keyed
by a hash of the DID string (`_did_path`). `Owner` follows the identical
pattern — a new `owners/` directory, one JSON file per owner, keyed by a
hash of the owner id:

```
Owner
  id            TEXT PRIMARY KEY   -- stable slug, e.g. "james"
  primary_email TEXT               -- display default; NOT the primary key
  emails        list[str]          -- all linked addresses, primary included
  linked_dids   list[str]          -- DIDs currently linked to this owner
  created_at    int
```

Reverse index, `email -> owner_id`, rebuilt from the `emails` list on load
(same "load everything into memory, save-on-write" pattern `DIDRegistry`
already uses — no new database, no new dependency).

**Why `id` and not `primary_email` as the key:** email addresses change —
this design exists *because* one already did (`henrynet.ca` →
`eigan.ai`). Keying every downstream reference (`DIDRecord.owner_id`,
namespace grants) on a string that's expected to change means a rename
cascades through every linked record. A stable internal id sidesteps that;
`primary_email` is a display field, `emails` is an append-only list, and
adding an address is `owner add-email`, never a rename of the id.

### `DIDRecord` gains an optional `owner_id`

One new field on the existing dataclass. A DID with no `owner_id` behaves
exactly as today — this is additive, not a migration.

### Grant resolution falls through to the owner

The cleanest integration avoids a second grants table entirely. `DIDStatus`
lookups (`_registry[namespace][key]`) already treat the registry as a flat
`namespace -> {key: status}` map where `key` is currently always a DID
string. Extend `key` to also accept `owner:<id>` as a first-class entry —
structurally identical to how `GLOBAL_NS = "*"` is already just a special
namespace key, not a separate code path.

`is_authorized(did, namespace)` becomes:
1. Check `did` directly against `namespace` (today's behavior, unchanged).
2. Check `did` against `GLOBAL_NS` (today's behavior, unchanged).
3. **New:** if `did` has a linked `owner_id`, check `owner:<owner_id>`
   against `namespace`, then against `GLOBAL_NS`.

`approve()`/`revoke()` gain an `owner:<id>` target alongside a `did`
target, going through the same admin/approver authority checks that
already exist. Approving `owner:james` for a namespace means every DID
linked to `james` — present and future — inherits it. No per-device
re-approval step.

### Multi-owner instances — already supported, worth stating explicitly

The flat `namespace -> {key: status}` registry already allows multiple
different keys to hold independent grants on the same namespace. Two
owners (`owner:james`, `owner:sarah`) can both be approved for the same
instance with zero new mechanism — this was true before this plan and
remains true after it. Worth stating outright so "owner" is never
misread as "an instance has exactly one owner." It doesn't, and nothing
here makes it so.

### Org — a second principal kind, for instances that aren't any one person's

Not every instance belongs to an individual. A project or team instance —
`eigan` genuinely shared by multiple people working under an "Eigan" org,
say, not just one person's own devices — needs a grant-holder that isn't a
person at all.

`Org` follows the exact same storage/resolution pattern as `Owner` — a
sibling principal kind, not a special case bolted onto Owner:

```
Org
  id                TEXT PRIMARY KEY   -- stable slug, e.g. "eigan"
  name              TEXT               -- display name
  member_owner_ids  list[str]          -- owners who are members
  created_at        int
```

Registry keys extend one more step: `org:<id>` alongside `did:...`,
`owner:<id>`, and `"*"`. Grant resolution's owner fallthrough (step 3
above) gains a step 4: if the DID's owner is a member of one or more orgs,
check `org:<id>` for each. A namespace approved for `org:eigan` is
reachable by every current *and future* member of that org without the
namespace grant ever being touched again as membership changes — the same
"approve once, inherit forever" property owner grants already give a
person's individual devices, one level up the chain.

**Membership authority, by analogy with the owner/device split just
settled:** creating a new org (a new top-level principal on the server) is
the same admin-only gate as owner-creation — a new grant-holding entity
coming into existence stays with the admin, consistently with everything
else in this plan. Adding or removing *members* of an *already-existing*
org is the more interesting question: self-service by existing members
would mirror the device-invite pattern, but org membership changes who
inherits access far more broadly than one person adding their own laptop
does. Whether *any* member can add other members, or an org needs its own
internal "org-admin" role independent of the server admin, isn't decided
here — see Open questions.

### Two invite kinds, two authority levels

`invite/create` today mints a token scoped to one namespace + role. This
plan splits the owner-facing case into two distinct operations with
different authority requirements — conflating them was the mistake in the
first draft of this section.

**Device invite — add a DID to an *existing* owner.** Full self-service:
mintable by *any* DID already linked to that owner, no admin involvement.
On redemption the new DID links to the same owner and inherits that
owner's grants. This is the common case — a person getting a new laptop
doesn't need to go through anyone. `hopper upstream invite create --owner
james` (run from any of James's already-linked devices).

**Owner-creation invite — admit a *new* owner (person) to this server at
all.** Admin-only, full stop. This is the actual gate: who gets to exist as
a recognized owner on this Hopper server in the first place is a decision
that doesn't get delegated, even once there are multiple existing owners.
`hopper upstream invite create --new-owner --email <addr>` — on redemption,
creates the `Owner` record and links the redeeming DID as its first
device. Everything that owner does afterward (adding their own further
devices) falls under the device-invite rule above and needs no further
admin involvement.

This is the answer to the chicken-and-egg problem at `hopper init` time: a
brand-new machine has no DID until `init` generates one locally, and no way
to prove "I'm James's new laptop" (device invite) or "I'm a legitimate new
person" (owner-creation invite) to the server without *some* credential.
The invite token is that credential, and which kind was redeemed
determines what happens next.

### New endpoint: instance discovery

`GET /admin/instances?owner=<id>` — every namespace reachable by the owner
directly or by any linked DID, via the same registry the sync path already
authorizes against. This is the single new read path everything else in
this plan (the CLI audit command, `hopper init`'s picker) calls into.

### `hopper init` — discover before creating

Today: generate (or reuse) a local DID, default instance name to
`Path.cwd().name`, done — no network round-trip, no visibility into what
already exists.

New flow, when an upstream server is configured:
1. Resolve an owner credential — either an existing linked DID on this
   machine, or an owner-invite token supplied via `--claim <token>` for a
   genuinely new machine.
2. Call the new instance-discovery endpoint.
3. **Interactive:** present existing instances (ideally with last-activity
   and task-count context so `eigan` and `waypoint` don't look identical in
   a bare list) plus an explicit "create new — `<cwd-name>`" option. The
   directory-name default still exists; it's just no longer silent.
4. **Non-interactive** (the common case in practice — most `init` calls
   observed in this codebase's history come from agent sessions, not a
   human at a prompt): **refuse and print the candidate list** rather than
   falling back to `Path.cwd().name`. Require an explicit `--instance <id>`
   (or `--instance new:<name>` to deliberately create one). A loud refusal
   that lists what already exists is a cheap failure; a silent fork that
   surfaces six weeks later is not — this is the exact mechanism that
   produced the Rosetta_Program/eigan split.

### New CLI surface

```
hopper upstream admin owner create <id> --email <primary>       # admin only
hopper upstream admin owner add-email <id> --email <addr>
hopper upstream admin owner link-did <did> --owner <id>
hopper upstream admin owner instances <id>        # what the incident-response
                                                    # investigation in this
                                                    # conversation had to do
                                                    # by brute-force guessing

hopper upstream admin org create <id> --name <name>              # admin only
hopper upstream admin org add-member <org-id> --owner <owner-id> # see Open questions
hopper upstream admin org remove-member <org-id> --owner <owner-id>
hopper upstream admin org instances <id>

# device invite — self-service, any DID already linked to <id>
hopper upstream invite create --owner <id> [--expires-in] [--max-uses]

# owner-creation invite — admin only
hopper upstream invite create --new-owner --email <addr> [--expires-in]

hopper init --claim <invite-token>                 # either invite kind
hopper init --instance <id>                        # explicit, skips picker
```

## Open questions — how they actually resolved during implementation

None of these blocked shipping; each got a concrete, conservative default
rather than sitting open, since all are cheaply reversible later.

- **Conflicting owner claims.** Resolved as leaned: `OwnerRegistry.link_did`
  rejects linking a DID already linked to a *different* owner — error, not
  silent reassignment. Locked down in
  `tests/storage/test_owner_registry.py::TestDidLinking::test_link_did_rejects_conflicting_owner`.
- **Reassigning a DID to a different owner later.** Resolved: mechanically
  `unlink-did` then `link-did`, both admin-only endpoints (Phase A,
  unchanged) — so reassignment authority is admin authority, no separate
  role needed. Tested end-to-end
  (`test_after_unlink_did_can_be_relinked_to_a_different_owner`).
- **What an invite grants by default.** Resolved by the kind split itself:
  a **device** invite inherits the owner's grants immediately on redemption
  (that's the entire point — self-service, no further approval step,
  verified live: a device synced successfully into a namespace while still
  individually PENDING, purely through its owner's grant). A **new-owner**
  invite grants nothing beyond creating the owner and linking the first
  device — a fresh owner starts with zero namespace access until an admin
  explicitly grants some, same as if `owner create` had been run directly.
- **Org membership authority.** Resolved conservatively, as flagged:
  *both* org creation and membership changes (add/remove member) are
  admin-only for v1. Verified live — a plain member device attempting
  `org add-member` was rejected regardless of which auth flag it used to
  present its key. Loosening this to self-service-within-the-org later is
  additive (an `is_approver`-style per-org role), not a breaking change.

## Phasing

Each phase is independently mergeable and reversible, following the same
discipline as `Phase-4-Revisions-DID-Agent-Plan.md`.

### Phase A — Owner registry (storage only)

Scope:
- `Owner` dataclass + `owners/` JSON store, `_owner_path` hashing, load/save
  following the exact pattern already used for `DIDRecord`.
- Email reverse index (in-memory, rebuilt on load).
- `DIDRecord.owner_id` field added (nullable, no migration needed for
  existing records — absent means unlinked, same as today).
- CLI: `owner create`, `owner add-email`, `owner link-did`, `owner
  unlink-did`.
- **No behavior change yet** — nothing reads `owner_id` for authorization.
  Pure data-model groundwork.

Exit criteria: an owner can be created, linked to multiple emails and
multiple existing DIDs, and inspected — with zero change to what any
existing DID can currently do.

### Phase B — Grant resolution falls through to owner

Scope:
- `is_authorized` / `is_approver` extended per "Grant resolution" above.
- `approve()` / `revoke()` accept an `owner:<id>` target.
- `GET /admin/instances?owner=<id>` endpoint.
- CLI: `owner instances <id>`.

Exit criteria: approving an owner for a namespace grants every currently-
linked DID access without touching them individually; the audit command
answers "what can this owner reach" in one call — the thing this
conversation's investigation had to do by hand, one guessed namespace name
at a time.

### Phase C — Device and owner-creation invites

Scope:
- `invite/create --owner <id>` (device invite): mintable by any DID
  already linked to `<id>`, no admin check. Redemption links the new DID
  to that owner and inherits its grants, per the "what an invite grants by
  default" open question below (needs a decision before this phase
  starts).
- `invite/create --new-owner --email <addr>` (owner-creation invite):
  admin-only. Redemption creates the `Owner` record and links the
  redeeming DID as its first device.

Exit criteria: any DID already linked to an owner can mint a device invite
that brings in a new DID for that same owner with no admin involvement.
Minting a *new-owner* invite from a non-admin DID is rejected regardless of
whether that DID is linked to an existing owner — owner-creation stays
admin-gated even for owners who already have full self-service device
invites within their own scope.

### Phase D — `hopper init` instance discovery

Scope:
- Interactive picker flow.
- Non-interactive refuse-and-list behavior, explicit `--instance` /
  `--claim` flags.
- `Path.cwd().name` default demoted from silent fallback to an explicit,
  named choice in the picker.

Exit criteria: `hopper init` run from a directory whose name doesn't match
any existing instance, by an owner who already has one or more instances,
either shows a picker (interactive) or refuses with a candidate list
(non-interactive) — it never silently creates a new namespace next to ones
that already hold the relevant work.

### Phase E — Organizations

Scope:
- `Org` dataclass + `orgs/` JSON store, same pattern as Phase A's `Owner`.
- Grant resolution step 4 (org fallthrough) per "Org — a second principal
  kind" above.
- CLI: `org create` (admin-only), `org add-member` / `org remove-member`
  (authority per the org-membership open question — must be decided before
  this phase starts), `org instances`.
- Instance-discovery endpoint extended to include org-derived reachability
  alongside owner-derived, so `hopper init`'s picker (Phase D) shows
  instances reached via org membership too, not just direct/owner grants.

Exit criteria: approving `org:eigan` for a namespace makes it reachable by
every member owner's every linked DID; adding a new member to an existing
org extends that reach immediately with no further namespace-level action.

Depends on Phase B (registry key extension pattern) and benefits from
Phase D existing (so org-reachable instances actually surface in the
picker), but is otherwise independent — can ship whenever the membership-
authority question is settled, no earlier deadline.

## What this plan explicitly does NOT do

- Does not verify email ownership (no magic links, no OTP).
- Does not add a second, cryptographically stronger authorization path
  alongside the existing DID-registry trust model.
- Does not touch per-DID grants for DIDs with no owner link — external
  collaborators are unaffected.
- Does not retroactively relabel or migrate any existing namespace's
  history; `eigan`, `waypoint`, and any other already-active instance keep
  their current DIDs' grants exactly as they are until someone explicitly
  runs `owner link-did` against them.
- Does not resolve the open questions above — implementation of Phase
  B/C/E should not proceed past the ones that block them without an
  explicit decision.

## Future work (deferred, not designed here)

- **Admin management surface.** Every operation in this plan is a CLI call
  against a hand-editable JSON registry — fine for a single admin (James)
  operating alone. If a second admin, or an approver-of-approvers, ever
  becomes real, ad hoc CLI calls stop being enough: you want a place to
  *see* the current owner/DID/namespace graph at a glance, not reconstruct
  it by chaining `list`/`instances` calls. Worth its own design pass
  (web UI, or at minimum a `hopper upstream admin dashboard`-style TUI)
  when that need actually arrives — not scoped here, and not a prerequisite
  for Phases A–D, which are all single-admin-safe as written.

## First concrete step

Phase A: `Owner` dataclass, `owners/` JSON store mirroring the existing
per-DID file pattern in `storage.py`, and the three `owner` CLI subcommands
that only create/inspect data. Nothing else in this plan can be built,
tested, or even meaningfully discussed against real data until owner
records exist to link against.

## Implementation notes (added post-implementation, 2026-08-31)

All five phases shipped in one session, each verified with unit tests plus
a live smoke test against a real (throwaway, local) server instance driven
through the actual signed CLI — not just mocked. 778 tests passing,
zero skips introduced, `ruff check` clean across the touched files and the
full `src/`/`tests/` tree.

**One addition beyond the original design:** a `GET /me` endpoint
(`server.py`) and `UpstreamClient.me()`. The picker (Phase D) needs a
device to discover its *own* linked owner before it can call
`GET /admin/instances?owner=<id>` — nothing in the original design gave a
DID a way to ask "who am I" without already knowing the answer. `/me`
needs no special authority beyond holding the key, since it only ever
returns information about the caller itself.

**Two real bugs found and fixed, not routed around, because they sat
directly on this plan's critical path:**

- `verify_did_auth` verified request signatures against `request.url.path`,
  which Starlette strips of the query string, while the client always
  signs path+query as one string. This silently broke auth on *every*
  pre-existing GET endpoint that takes a filter
  (`list_dids`/`list_pending`/`invite_list`'s `?namespace=...`), not just
  the new `/admin/instances?owner=...`. Found because Phase B's `owner
  instances` command hit the same wall Phase A never needed to.
- `OwnerRegistry.list_all()` sorted purely by millisecond `created_at`,
  which ties under fast back-to-back creates and is genuinely
  nondeterministic in that case — caught by a full-suite run, not the
  targeted one, exactly the kind of flake that "passes on my machine."
  Fixed with `id` as a deterministic tiebreaker; the test that had been
  over-asserting a creation-order guarantee the code never actually
  promised was rewritten to assert determinism instead.

**One near-miss caught by tests before it ever ran live:** `set_status`
and `revoke` originally only guarded the per-DID-file bookkeeping against
`is_owner_key(target)`, not `is_org_key(target)` — so approving an org
would have written a bogus DID-record file under `dids/`, hashing
`"org:eigan"` as if it were a real DID. `test_org_approve_creates_no_did_record_file`
failed immediately after the Phase E tests were written, before any live
testing; both `set_status` and `revoke` now check `is_owner_key(target) or
is_org_key(target)`.

**Deliberately not done in this pass:** nothing was committed to git,
deployed to `hopper.henrynet.ca`, or synced to `~/.hopper-install` (the
directory the live `hopper` CLI actually runs from). Everything above
lives in `~/Source/hopper` only, tested against disposable local server
instances created and destroyed within this session. Rollout — committing,
and separately deciding when/how to deploy to the real server and the
installed CLI — is a distinct decision from implementation and hasn't been
made yet.
