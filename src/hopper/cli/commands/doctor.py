"""``hopper doctor`` -- one-shot health check for a Hopper project.

Read-only by default. Exit code 0 = all OK, 1 = warnings, 2 = errors, so it is
usable from cron, CI, and agent session-start hooks. Everything runs offline;
the only network touch is a short TCP connect to the upstream (failure degrades
to a warning). ``--fix`` performs a small set of mechanical, reversible repairs
and never closes, deletes, or re-prioritizes tasks.
"""

from __future__ import annotations

import json
import socket
import subprocess
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import click
import yaml

from hopper.cli.main import Context

OK, WARN, ERROR = "ok", "warn", "error"
_EXIT = {OK: 0, WARN: 1, ERROR: 2}

GROUPS = ("config", "sync", "tasks", "environment")
GROUP_TITLES = {
    "config": "Config",
    "sync": "Sync",
    "tasks": "Tasks",
    "environment": "Environment",
}

BLOCKED_DAYS = 30
OPEN_ROT_DAYS = 90
SYNC_AGE_HOURS = 24
GENERIC_ASSIGNEES = {"", "main", "agent", "ai", "claude", "user", "unknown", "default"}
DOCTOR_IDENTITY = "hopper:doctor"
LEGACY_SYNC_MARKER = "deprecated"
_GIT_TIMEOUT = 2


@dataclass
class Check:
    """Result of a single health check."""

    id: str
    status: str
    message: str
    remedy: str = ""

    @property
    def group(self) -> str:
        return self.id.split(".", 1)[0]

    def to_json(self) -> dict[str, str]:
        d = asdict(self)
        return {k: d[k] for k in ("id", "status", "message", "remedy")}


@dataclass
class Env:
    """Resolved inputs shared by all checks."""

    storage: Path | None
    config: Any  # hopper.cli.config.Config
    stale_days: float
    now: datetime

    @property
    def project_dir(self) -> Path | None:
        if self.storage is None:
            return None
        return self.storage.parent if self.storage.name == ".hopper" else self.storage

    @property
    def project_config_path(self) -> Path | None:
        return self.storage / "config.yaml" if self.storage else None

    @property
    def is_global_store(self) -> bool:
        return self.storage is not None and self.storage == Path.home() / ".hopper"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _age_days(dt: datetime | None, now: datetime) -> float | None:
    dt = _aware(dt)
    return None if dt is None else (now - dt).total_seconds() / 86400


def _load_yaml(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _git(args: list[str], cwd: Path) -> str | None:
    """Run a local git command; return stdout or None on any failure."""
    try:
        res = subprocess.run(  # noqa: S603
            ["git", *args],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None


def _tcp_reachable(url: str, timeout: float = 1.0) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _open_store(storage: Path):
    """Open the task store without going through the CLI context."""
    from hopper.cli.local_client import LocalClient

    return LocalClient(storage)


def _legacy_sync_block(env: Env) -> dict[str, Any] | None:
    block = _load_yaml(env.project_config_path).get("sync")
    return block if isinstance(block, dict) else None


def _effective_sync(env: Env) -> tuple[bool, str | None]:
    up = env.config.current_profile.upstream
    return bool(up.enabled and up.server), up.server


# --------------------------------------------------------------------------
# checks: config
# --------------------------------------------------------------------------


def check_config(env: Env) -> list[Check]:
    out: list[Check] = []
    effective, server = _effective_sync(env)
    src = env.config.config_path
    if effective:
        target = f"{server} (from {src})"
    else:
        target = f"none (upstream disabled in {src})"

    block = _legacy_sync_block(env)
    if block is None:
        out.append(Check("config.sync_target", OK, f"Effective sync target: {target}"))
    elif LEGACY_SYNC_MARKER in block:
        out.append(
            Check(
                "config.sync_target",
                OK,
                f"Effective sync target: {target}; legacy sync: block annotated as inert",
            )
        )
    else:
        block_on = bool(block.get("enabled") and block.get("server_url"))
        if block_on != effective:
            claim = "on" if block_on else "off"
            out.append(
                Check(
                    "config.sync_target",
                    WARN,
                    f"Split-brain: project sync: block says {claim} but effective sync is "
                    f"{target}; the sync: block is inert legacy config",
                    "hopper doctor --fix (annotates the block) or remove `sync:` from "
                    f"{env.project_config_path}",
                )
            )
        else:
            out.append(
                Check(
                    "config.sync_target",
                    OK,
                    f"Effective sync target: {target}; legacy sync: block present (inert)",
                )
            )

    problems: list[str] = []
    project_cfg = _load_yaml(env.project_config_path)
    spath = (project_cfg.get("storage") or {}).get("path")
    if spath and not Path(str(spath)).expanduser().exists():
        problems.append(f"storage.path {spath} does not exist")
    key = env.config.current_profile.upstream.did_key_path
    if key and not Path(key).expanduser().exists():
        problems.append(f"did_key_path {key} does not exist")
    if problems:
        out.append(
            Check(
                "config.paths",
                ERROR,
                "; ".join(problems),
                "fix the path in config.yaml, or run `hopper upstream init --force`",
            )
        )
    else:
        out.append(Check("config.paths", OK, "Configured paths exist"))
    out.extend(_check_instance_name(env))
    return out


def _check_instance_name(env: Env) -> list[Check]:
    """Project instance id should match the project directory it lives in."""
    if env.storage is None or env.is_global_store or env.project_dir is None:
        return []
    cfg = _load_yaml(env.project_config_path).get("instance")
    inst = cfg.get("id") if isinstance(cfg, dict) else None
    if not inst:
        return []
    dirname = env.project_dir.name
    if str(inst).lower() == dirname.lower():
        return [Check("config.instance", OK, f"Instance '{inst}' matches directory")]
    return [
        Check(
            "config.instance",
            WARN,
            f"Instance id '{inst}' differs from project directory '{dirname}' "
            "(sync state and shared-board namespace follow the id)",
            "if unintended: edit instance.id in .hopper/config.yaml",
        )
    ]


# --------------------------------------------------------------------------
# checks: sync
# --------------------------------------------------------------------------


def _check_server_version(server: str) -> Check:
    """Compare CLI and server versions via /health (older servers omit it)."""
    from hopper import __version__

    try:
        import httpx

        data = httpx.get(server.rstrip("/") + "/health", timeout=2.0).json()
        remote = data.get("version") if isinstance(data, dict) else None
    except Exception:  # noqa: BLE001
        return Check("sync.server_version", OK, "Server version unavailable")
    if not remote or remote == "0.1.0":
        return Check(
            "sync.server_version",
            WARN,
            f"Server does not report a hopper version (CLI is {__version__}); "
            "it is likely older than 0.4 and won't page large pulls",
            "upgrade the server to the same hopper version",
        )
    if remote != __version__:
        return Check(
            "sync.server_version",
            WARN,
            f"CLI {__version__} vs server {remote}",
            "upgrade whichever side is older",
        )
    return Check("sync.server_version", OK, f"CLI and server both {__version__}")


def check_sync(env: Env, store: Any | None) -> list[Check]:
    up = env.config.current_profile.upstream
    if not (up.enabled and up.server):
        msg = "Upstream sync not configured (local-only)"
        return [
            Check("sync.did_key", OK, msg),
            Check("sync.last_sync", OK, msg),
            Check("sync.pending", OK, msg),
        ]

    out: list[Check] = []
    # DID key
    key_path = Path(up.did_key_path).expanduser() if up.did_key_path else None
    if key_path is None or not key_path.exists():
        out.append(
            Check(
                "sync.did_key",
                ERROR,
                "DID key missing" + (f": {key_path}" if key_path else " (no did_key_path set)"),
                "hopper upstream init --server " + str(up.server),
            )
        )
    else:
        try:
            from hopper.upstream.did import load_did_key

            did = load_did_key(key_path).did
            out.append(Check("sync.did_key", OK, f"DID key valid ({did[:24]}...)"))
        except Exception as e:  # noqa: BLE001
            out.append(
                Check(
                    "sync.did_key",
                    ERROR,
                    f"DID key unreadable: {e}",
                    "hopper upstream init --force",
                )
            )

    # reachability (fast, failure-tolerant)
    if _tcp_reachable(str(up.server)):
        out.append(Check("sync.reachable", OK, f"Upstream reachable: {up.server}"))
        out.append(_check_server_version(str(up.server)))
    else:
        out.append(
            Check(
                "sync.reachable",
                WARN,
                f"Upstream not reachable (offline?): {up.server}",
                "check network; local work is unaffected",
            )
        )

    if env.storage is None or store is None:
        out.append(Check("sync.last_sync", WARN, "No local storage; cannot read sync state"))
        return out

    from hopper.storage.base import StorageConfig
    from hopper.upstream.sync import SyncState, pending_changes

    instance = StorageConfig.local(env.storage).instance_id
    state_file = env.storage / f".sync_state_{instance}"
    state = SyncState.load(state_file)
    if not state.last_sync:
        out.append(Check("sync.last_sync", WARN, "Never synced", "hopper sync"))
    else:
        hours = (env.now.timestamp() * 1000 - state.last_sync) / 3_600_000
        if hours > SYNC_AGE_HOURS:
            out.append(
                Check(
                    "sync.last_sync",
                    WARN,
                    f"Last sync {hours / 24:.1f} days ago (threshold {SYNC_AGE_HOURS}h)",
                    "hopper sync",
                )
            )
        else:
            out.append(Check("sync.last_sync", OK, f"Last sync {hours:.1f}h ago"))

    try:
        pending, pending_bytes = pending_changes(store, env.storage / ".sync_state", instance)
    except Exception as e:  # noqa: BLE001
        out.append(Check("sync.pending", WARN, f"Could not compute pending changes: {e}"))
    else:
        if pending:
            out.append(
                Check(
                    "sync.pending",
                    WARN,
                    f"{_plural(pending, 'local change')} not yet pushed (~{pending_bytes / 1024:.0f} KiB)",
                    "hopper sync",
                )
            )
        else:
            out.append(Check("sync.pending", OK, "No local changes pending push"))
    return out


# --------------------------------------------------------------------------
# checks: tasks
# --------------------------------------------------------------------------


def stale_in_progress(tasks: list[Any], env: Env) -> list[tuple[Any, str]]:
    """In-progress tasks that are ownerless or have no recent heartbeat."""
    found = []
    for t in tasks:
        if t.status != "in_progress":
            continue
        age = _age_days(t.last_heartbeat or t.updated_at, env.now)
        if not t.assigned_to:
            reason = "no assignee"
            if age is not None:
                reason += f", idle {age:.0f}d"
            found.append((t, reason))
        elif age is not None and age > env.stale_days:
            found.append((t, f"no heartbeat for {age:.0f}d"))
    return found


def _oldest(items: list[tuple[Any, float]], n: int = 3) -> str:
    items = sorted(items, key=lambda p: p[1], reverse=True)[:n]
    return ", ".join(f"{t.id} {d:.0f}d" for t, d in items)


def check_tasks(env: Env, all_records: list[Any]) -> list[Check]:
    out: list[Check] = []
    tasks = [t for t in all_records if getattr(t, "kind", "task") == "task"]
    ids = {t.id for t in all_records}

    stale = stale_in_progress(tasks, env)
    if stale:
        detail = ", ".join(f"{t.id} ({why})" for t, why in stale[:3])
        out.append(
            Check(
                "tasks.in_progress",
                WARN,
                f"{_plural(len(stale), 'in_progress task')} ownerless or stale: {detail}",
                "hopper doctor --fix (releases to open with a note) or "
                "hopper task status <id> in_progress --assign platform:name -f",
            )
        )
    else:
        out.append(Check("tasks.in_progress", OK, "No ownerless or stale in_progress tasks"))

    blocked = []
    for t in tasks:
        if t.status == "blocked":
            age = _age_days(t.updated_at, env.now)
            if age is not None and age > BLOCKED_DAYS:
                blocked.append((t, age))
    if blocked:
        why = "; ".join(
            f"{t.id} {d:.0f}d" + (f" [{', '.join(t.tags[:3])}]" if t.tags else "")
            for t, d in sorted(blocked, key=lambda p: p[1], reverse=True)[:3]
        )
        out.append(
            Check(
                "tasks.blocked",
                WARN,
                f"{_plural(len(blocked), 'task')} blocked > {BLOCKED_DAYS}d: {why}",
                "unblock, or close if obsolete: hopper task status <id> <status> -f",
            )
        )
    else:
        out.append(Check("tasks.blocked", OK, f"No tasks blocked > {BLOCKED_DAYS}d"))

    rot = []
    for t in tasks:
        if t.status in ("open", "pending"):
            age = _age_days(t.updated_at, env.now)
            if age is not None and age > OPEN_ROT_DAYS:
                rot.append((t, age))
    if rot:
        out.append(
            Check(
                "tasks.open_rot",
                WARN,
                f"{_plural(len(rot), 'open task')} untouched > {OPEN_ROT_DAYS}d "
                f"(oldest: {_oldest(rot)})",
                "triage: hopper task list --status open",
            )
        )
    else:
        out.append(Check("tasks.open_rot", OK, f"No open tasks untouched > {OPEN_ROT_DAYS}d"))

    generic = [
        t
        for t in tasks
        if t.status in ("in_progress", "blocked", "open", "pending")
        and t.assigned_to is not None
        and (t.assigned_to.strip().lower() in GENERIC_ASSIGNEES or ":" not in t.assigned_to)
    ]
    if generic:
        sample = ", ".join(f"{t.id}={t.assigned_to!r}" for t in generic[:3])
        out.append(
            Check(
                "tasks.generic_assignee",
                WARN,
                f"{_plural(len(generic), 'task')} with a generic assignee: {sample}",
                "reassign using platform:task-name (e.g. claude:my-task)",
            )
        )
    else:
        out.append(Check("tasks.generic_assignee", OK, "Assignees use platform:task-name"))

    dangling = [(t, d) for t in tasks for d in t.depends_on if d not in ids]
    if dangling:
        sample = ", ".join(f"{t.id}->{d}" for t, d in dangling[:3])
        out.append(
            Check(
                "tasks.dangling_depends",
                WARN,
                f"{_plural(len(dangling), 'dangling dependency reference')}: {sample}",
                "remove the missing id from the task's depends list",
            )
        )
    else:
        out.append(Check("tasks.dangling_depends", OK, "All depends references resolve"))

    counts = Counter(t.status for t in tasks)
    summary = ", ".join(f"{s}={n}" for s, n in sorted(counts.items())) or "no tasks"
    out.append(Check("tasks.summary", OK, f"{len(tasks)} tasks: {summary}"))
    return out


# --------------------------------------------------------------------------
# checks: environment
# --------------------------------------------------------------------------


def check_environment(env: Env, all_records: list[Any]) -> list[Check]:
    out: list[Check] = []
    pdir = env.project_dir

    # gitignore
    if pdir is None or env.is_global_store:
        out.append(Check("environment.gitignore", OK, "Global store; no project gitignore check"))
    elif _git(["rev-parse", "--is-inside-work-tree"], pdir) != "true":
        out.append(Check("environment.gitignore", OK, "Not inside a git repository"))
    elif _git(["check-ignore", "-q", ".hopper"], pdir) is not None:
        out.append(Check("environment.gitignore", OK, ".hopper/ is gitignored"))
    elif _git(["ls-files", ".hopper"], pdir):
        out.append(Check("environment.gitignore", OK, ".hopper/ is tracked in git (deliberate)"))
    else:
        out.append(
            Check(
                "environment.gitignore",
                WARN,
                ".hopper/ is neither gitignored nor tracked",
                "echo .hopper/ >> .gitignore  (or git add .hopper to track it)",
            )
        )

    # agent files drift
    from hopper.storage.knowledge import AGENTS_MD_VERSION, _extract_agent_files_version

    if pdir is None or env.is_global_store:
        out.append(Check("environment.agent_files", OK, "Global store; no project agent files"))
    else:
        marker = "## Hopper - Persistent Memory"
        issues = []
        for name in ("AGENTS.md", "CLAUDE.md"):
            f = pdir / name
            if not f.exists():
                issues.append(f"{name} missing")
                continue
            text = f.read_text(errors="replace")
            if marker not in text:
                issues.append(f"{name} has no Hopper section")
                continue
            ver = _extract_agent_files_version(text)
            if ver is None or ver < AGENTS_MD_VERSION:
                issues.append(f"{name} at v{ver if ver else '?'} (current v{AGENTS_MD_VERSION})")
        if issues:
            out.append(
                Check(
                    "environment.agent_files",
                    WARN,
                    "Agent files drift: " + "; ".join(issues),
                    "hopper knowledge update-agent-files",
                )
            )
        else:
            out.append(Check("environment.agent_files", OK, f"Agent files at v{AGENTS_MD_VERSION}"))

    # editable install behind origin's default branch
    from hopper.utils.install import editable_install_status

    st = editable_install_status()
    if st is None:
        out.append(Check("environment.install", OK, "Not an editable git install"))
    else:
        branch = st.get("branch") or "(detached)"
        behind = st.get("behind")
        ref = st.get("default_ref") or "origin default branch"
        if behind is None:
            out.append(Check("environment.install", OK, "Editable install; branch state unknown"))
        elif behind > 0:
            out.append(
                Check(
                    "environment.install",
                    WARN,
                    f"Editable install on '{branch}' is {behind} commit(s) behind {ref} "
                    "(per last fetch); documented features may be missing",
                    f"git -C {st['repo']} fetch && git -C {st['repo']} merge {ref}",
                )
            )
        else:
            out.append(
                Check("environment.install", OK, f"Editable install on '{branch}' is up to date")
            )

    # legacy records
    from hopper.storage.base import StorageConfig

    own = StorageConfig.local(env.storage).instance_id if env.storage else None
    legacy = legacy_records(all_records, own)
    if legacy:
        out.append(
            Check(
                "environment.legacy_records",
                WARN,
                f"{_plural(len(legacy), 'legacy tag-encoded record')} would be reclassified",
                "hopper maintenance reclassify --apply  (or hopper doctor --fix)",
            )
        )
    else:
        out.append(Check("environment.legacy_records", OK, "No legacy tag-encoded records"))
    return out


def legacy_records(records: list[Any], own_instance: str | None = None) -> list[tuple[Any, str]]:
    """Legacy tag-encoded records this store may migrate (its own instance only)."""
    from hopper.cli.commands.maintenance import _target_kind, is_foreign_record

    found = []
    for r in records:
        if is_foreign_record(getattr(r, "instance", None), own_instance):
            continue
        target = _target_kind(list(r.tags or []), getattr(r, "kind", "task"))
        if target:
            found.append((r, target))
    return found


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------


def run_checks(env: Env) -> list[Check]:
    checks = check_config(env)
    store = None
    records: list[Any] = []
    load_err: str | None = None
    if env.storage is not None and env.storage.exists():
        try:
            client = _open_store(env.storage)
            store = client.task_store
            records = store.list()
            client.close()
        except Exception as e:  # noqa: BLE001
            load_err = str(e)
    else:
        load_err = "no local storage found (server mode or not initialized)"

    checks += check_sync(env, store)
    if load_err:
        checks.append(Check("tasks.load", ERROR, f"Cannot read tasks: {load_err}", "hopper init"))
    else:
        checks += check_tasks(env, records)
    checks += check_environment(env, records)

    order = {g: i for i, g in enumerate(GROUPS)}
    return sorted(checks, key=lambda c: order.get(c.group, 99))  # stable within group


def _emit(msg: str, json_mode: bool) -> None:
    click.echo(msg, err=json_mode)


def apply_fixes(env: Env, checks: list[Check], json_mode: bool) -> int:
    """Run conservative fixes, printing each before it runs. Returns count."""
    done = 0
    ids = {c.id: c for c in checks}

    if ids.get("config.sync_target") and ids["config.sync_target"].status != OK:
        path = env.project_config_path
        data = _load_yaml(path)
        block = data.get("sync")
        if isinstance(block, dict) and LEGACY_SYNC_MARKER not in block:
            _emit(f"FIX: annotating legacy sync: block in {path} as inert", json_mode)
            block[LEGACY_SYNC_MARKER] = (
                "inert legacy block; server sync is configured under upstream: "
                "(see `hopper sync status`)"
            )
            path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
            done += 1

    if env.storage is None or not env.storage.exists():
        return done
    client = _open_store(env.storage)
    try:
        store = client.task_store
        records = store.list()
        tasks = [t for t in records if getattr(t, "kind", "task") == "task"]
        for t, why in stale_in_progress(tasks, env):
            _emit(
                f"FIX: releasing {t.id} to open ({why}; was {t.assigned_to or 'unassigned'})",
                json_mode,
            )
            prev = t.assigned_to or "unassigned"
            t.status = "open"
            t.assigned_to = None
            t.last_heartbeat = None
            store.save(t)
            store.add_note(
                t.id,
                f"Released to open by `hopper doctor --fix`: {why} (was {prev}).",
                author=DOCTOR_IDENTITY,
            )
            done += 1

        legacy = legacy_records(records, client.config.instance_id)
        if legacy:
            _emit(
                f"FIX: reclassifying {_plural(len(legacy), 'legacy record')} "
                "(hopper maintenance reclassify --apply)",
                json_mode,
            )
            for r, target in legacy:
                r.kind = target
                store.save(r)
            done += 1
    finally:
        client.close()
    return done


def exit_code(checks: list[Check]) -> int:
    return max((_EXIT[c.status] for c in checks), default=0)


def render_text(checks: list[Check]) -> str:
    lines: list[str] = []
    for group in GROUPS:
        group_checks = [c for c in checks if c.group == group]
        if not group_checks:
            continue
        lines.append(GROUP_TITLES[group])
        for c in group_checks:
            line = f"  [{c.status.upper():<5}] {c.id}: {c.message}"
            if c.remedy and c.status != OK:
                line += f"  -> {c.remedy}"
            lines.append(line)
        lines.append("")
    counts = Counter(c.status for c in checks)
    lines.append(f"{counts[OK]} ok, {counts[WARN]} warning(s), {counts[ERROR]} error(s)")
    return "\n".join(lines)


@click.command(name="doctor")
@click.option("--json", "json_flag", is_flag=True, help="Emit one JSON object per check.")
@click.option("--fix", is_flag=True, help="Apply conservative, reversible fixes.")
@click.option(
    "--stale-days",
    type=float,
    default=2.0,
    show_default=True,
    help="Days without heartbeat before an in_progress task is stale.",
)
@click.pass_obj
def doctor(ctx: Context, json_flag: bool, fix: bool, stale_days: float) -> None:
    """Check the health of Hopper in this project.

    Exit codes: 0 = ok, 1 = warnings, 2 = errors. Works offline.

    \b
    --fix only: releases ownerless/stale in_progress tasks to open (with a
    note), annotates the inert legacy sync: block, and runs reclassify. It
    never closes, deletes, or re-prioritizes tasks.
    """
    json_mode = json_flag or ctx.json_output
    env = Env(
        storage=ctx.get_storage_path(),
        config=ctx.config,
        stale_days=stale_days,
        now=datetime.now(UTC),
    )
    checks = run_checks(env)
    if fix:
        if apply_fixes(env, checks, json_mode):
            env.now = datetime.now(UTC)
            checks = run_checks(env)
        else:
            _emit("Nothing to fix.", json_mode)

    if json_mode:
        click.echo(json.dumps([c.to_json() for c in checks], indent=2))
    else:
        click.echo(render_text(checks))
    code = exit_code(checks)
    if code:
        raise SystemExit(code)
