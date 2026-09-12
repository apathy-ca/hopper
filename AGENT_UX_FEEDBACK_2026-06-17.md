# Hopper — Agent/Programmatic UX Feedback

*Written: 2026-06-17 16:23 UTC*
*Source: a heavy multi-agent Rosetta session (claude) using the `hopper` CLI for task tracking/coordination.*
*Perspective: a programmatic consumer (an AI agent / scripts), NOT interactive human use. The Rich
table UX is great for humans; these gaps bite only when an agent or script drives the CLI — which,
per Hopper's multi-agent-coordination mission, is a primary use case.*

## TL;DR — priorities

1. **Add `--json` (machine-readable output) to `task list` and `task get`.** Highest leverage by far.
   Eliminates an entire class of agent errors (see #1). If only one thing is done, do this.
2. Don't truncate the task ID in `task list` (or document prefix-matching). (#2)
3. Add `--assignee` filter to `task list`. (#3)
4. Add `--id-only`/`--quiet` to `task add` for clean ID capture. (#4)

If #1 lands, #2 and #4 mostly dissolve (agents read structured fields instead of scraping/`tail`).

## Working correctly (credit — no change needed)

- **Bad ID fails loudly.** `hopper task update zzzznonexistent --priority high`
  → `✗ Failed to update task: Task not found: zzzznonexistent / Aborted!`, **exit 1.** Correct.
  (My own bug here was piping `2>/dev/null`, which hid this. Lesson on the caller, not Hopper.)
- **Prefix ID matching works.** `task get tee81ced` resolves the full `tee81ced8`. Nice — it mitigates #2.
- **STALE detection works.** An `in_progress` task with no heartbeat is flagged STALE in the list. Good.

## The genuine gaps

### 1. No machine-readable output (`task list` / `task get`) — the big one
`task list`/`task get` emit only a Rich box table. For an agent there is no `--json`/`--plain`/`--format`
(confirmed via `--help`). Consequences when scripting:
- The table **wraps long titles across multiple lines** and **truncates columns**, so `grep`/regex on the
  output is unreliable (a title like "RCP test-pattern generation…" renders as `RCP` / `test-pat…` /
  `generati…` on separate lines — no contiguous string to match).
- There is no robust way to get a task's ID/fields programmatically except scraping that table.

**Repro:** `hopper task list --tag amc` → try to extract a task's ID with `grep`/`awk` → fragile/empty.
**Impact:** agents resort to brittle table-scraping; this directly caused failed `task update` calls in-session.
**Fix:** `--json` (and/or `--plain` tab/newline-delimited) on `task list` and `task get`. Emitting full,
untruncated fields as JSON would make Hopper trivially scriptable and is the single biggest agent-UX win.

### 2. `task list` truncates the task ID
The list shows `tee81ced` (8 chars); the real ID is `tee81ced8` (9). The displayed value looks complete
but isn't, so copy-pasting an ID from the list view can be wrong/ambiguous.
**Fix:** show the full ID (widen the column), or make truncation visually obvious. Prefix-matching already
softens this, so it's lower priority — but a truncated-looking-complete ID is a footgun.

### 3. No `--assignee` filter on `task list`
`task list` supports `--status`, `--priority`, `--project`, `--tag`, `--sort-by`, `--limit` — but not
`--assignee`/`--assigned`. Given Hopper's assign-by-identity model (`platform:task-name`), "show *my*
tasks" is a natural, frequently-wanted filter.
**Repro:** `hopper task list --assignee claude:foo` → unknown option.
**Fix:** add `--assignee TEXT` (exact and/or prefix match).

### 4. No clean ID capture from `task add`
The new task ID appears only inside the prose line `✓ Created task: <id>`. Scripts capturing it via
`tail`/`grep` are fragile (and `| tail -1` cut it off in-session).
**Fix:** `--id-only` (print just the new ID) or `--quiet`, or include the ID in `--json` output.

## Note: caller-side mistakes (NOT Hopper bugs), recorded for completeness
- Used a placeholder/garbage ID (`tb`) by mistake.
- Invented a non-existent flag (`--assignee`) AND suppressed stderr (`2>/dev/null`), hiding the clear error
  Hopper *did* return. Don't swallow stderr on hopper calls.

## One-line asks
- `task list --json` / `task get --json`  ·  full IDs in `task list`  ·  `task list --assignee`  ·  `task add --id-only`

---

## Follow-up: 2026-09-12 16:00 UTC

*Source: same multi-agent Rosetta session (claude), returning to this repo after ~3 months to
diagnose a real multi-agent coordination incident on the ARC project's shared Hopper board.*

### Status of the four original asks (checked against current `master`, 7568802)

1. **Still open.** No `--json`/`--plain` on `task list` or `task get`. Partial mitigation landed:
   `task list --ids-only` (one ID per line) solves the ID-scraping half of this ask, but full
   structured fields (title, tags, assignee, description) are still Rich-table-only.
2. **Still open, unmitigated.** `task list` (including `--compact`) still shows `t2d3d516` for the
   real ID `t2d3d5164` — confirmed today. Prefix-matching on `task get`/`task update` still softens
   it, so still lower priority, but the footgun is unchanged.
3. **Still open.** `task list --help` has no `--assignee`/`--assigned` option.
4. **Still open.** `task add --help` has no `--id-only`/`--quiet`. (`--non-interactive` exists but
   doesn't change the output format.)

None of the four fully landed, but #1 got a real partial fix (`--ids-only`) worth crediting.

### 5. New: `pip show hopper` / `importlib.metadata` disagrees with `hopper --version`

On an editable install (`pip install -e .`) checked out at the `v0.3.0` tag: `hopper --version`
correctly prints `0.3.0` (reads the hardcoded `__version__` in `src/hopper/__init__.py`), but
`pip show hopper` and `importlib.metadata.version("hopper")` both report `0.2.0` — and this
persists across `pip install -e . --force-reinstall --no-deps` AND a full `pip uninstall` +
reinstall. `pyproject.toml` declares `dynamic = ["version"]`, presumably resolved via git tags
(setuptools-scm-style) at build time; on this checkout the packaging-side resolver seems to have
frozen on an earlier tag and doesn't re-resolve on editable reinstall.

**Impact:** genuinely confusing when auditing "what version is actually running" — the two answers
disagree, and a caller has no way to know `hopper --version` is the trustworthy one without reading
source. Not a correctness bug (the CLI *works* correctly), but a diagnostics/trust issue.
**Fix:** either make `hopper --version` also print the packaging-resolved version for comparison
(so a mismatch is visible), or make the dynamic version resolver re-run on every editable install/
reinstall rather than caching stale metadata.

### 6. New: no way to detect an editable install pinned to a stale/divergent branch

The actual root cause of today's incident: our local editable install of `hopper` was checked out
on a long-lived feature branch (`feat/memory-first-class`) that was 29 commits behind `master` —
fully merged, no unique work, just never switched back. Because the branch had its own (correct,
internally consistent) `__version__ = "0.3.0"`, `hopper --version` gave no signal anything was
wrong. This meant a real, already-shipped feature (`hopper task note`, documented in this project's
own `AGENTS.md`/`hopper-usage.md` since commit `43ef9bb`) appeared to a multi-agent session as "not
implemented" — `hopper task --help` genuinely had no `note` subcommand — and cost real
debugging time across two repos before the stale-branch checkout was found via manual `git
log`/`merge-base` archaeology.

**Fix idea:** on startup (or via a `hopper doctor`/`hopper env` command), if running from an
editable/source install, check whether the checked-out commit is an ancestor of the default
remote branch and warn if it's behind — e.g. "editable install on branch `feat/x`, 29 commits
behind `origin/master` — some documented features may be missing." This would have surfaced the
real problem in seconds instead of requiring cross-repo git archaeology.

### 7. Minor/ironic: this repo's own dogfood `CLAUDE.md`/`AGENTS.md` are stale

`~/Source/hopper/CLAUDE.md` (this repo) still carries `<!-- hopper-agent-files: v1 -->`, missing
the `task note`/creator-attribution content that `v2` (used downstream in Rosetta_Program's copies)
documents. `hopper knowledge update-agent-files` apparently hasn't been re-run against this repo's
own files since `v2` shipped. Low priority (doesn't affect anyone downstream), but worth a
reminder/CI check so the reference implementation doesn't drift behind its own generated docs.

### Credit where due

The design that already solves the CLAUDE.md/AGENTS.md drift problem we hit downstream — `CLAUDE.md`
here is a one-line pointer ("See AGENTS.md ... All conventions in AGENTS.md apply here") — is exactly
right, and exactly what our own Rosetta_Program copies were missing (we'd been hand-duplicating
content into both files instead of pointing one at the other; fixed downstream today by copying
this repo's own pattern). Worth highlighting this file as the reference example in your own
CONTRIBUTING docs for anyone setting up a new project's agent files.
