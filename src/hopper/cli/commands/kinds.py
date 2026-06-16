"""Per-kind CLI wrappers.

Adds ``hopper idea``, ``hopper note``, ``hopper memory``, ``hopper log``,
``hopper reference``, ``hopper inbox``, and ``hopper job`` command groups
as thin wrappers over ``hopper task`` that set the record ``kind``.

Now that the storage layer supports a queryable ``kind`` (Phase 1), these
wrappers write ``kind=<kind>`` on the underlying record and ``list``
filters by ``kind=`` — they are type-based, not tag-based. The kind is
still added as a tag on write for backwards-compatible discovery, but
queries no longer depend on the tag.

Memory ergonomics: ``hopper memory add`` accepts ``--subject``,
``--scope``, and ``--provenance`` to capture agent-knowledge structure up
front; these are now promoted to real frontmatter fields on the record
(round-tripping cleanly) rather than jammed into a text preamble.
"""

from __future__ import annotations

import click

from hopper.cli.commands.task import add_task, list_tasks

_KINDS = ("idea", "note", "memory", "log", "reference", "inbox", "job")


def _make_group(kind: str) -> click.Group:
    """Build a click group with ``add`` and ``list`` subcommands for a kind."""

    @click.group(name=kind, help=f"Work with {kind} records.")
    def group() -> None:
        pass

    @group.command(name="add")
    @click.argument("title", required=False)
    @click.option("--description", "-d", help="Description")
    @click.option(
        "--priority",
        "-p",
        type=click.Choice(["low", "medium", "high", "urgent"]),
        default="medium",
    )
    @click.option(
        "--tag",
        "-t",
        multiple=True,
        help="Additional tags (the kind itself is always added)",
    )
    @click.option("--project", help="Project ID or name")
    @click.option("--parent", help="Parent record ID")
    @click.option("--non-interactive", is_flag=True)
    @click.option("--author-did", envvar="HOPPER_DID", hidden=True)
    @click.option("--author-location", envvar="HOPPER_LOCATION", hidden=True)
    @click.pass_context
    def add_cmd(
        ctx: click.Context,
        title: str | None,
        description: str | None,
        priority: str,
        tag: tuple[str, ...],
        project: str | None,
        parent: str | None,
        non_interactive: bool,
        author_did: str | None,
        author_location: str | None,
    ) -> None:
        tags = (kind,) + tuple(t for t in tag if t != kind)
        ctx.invoke(
            add_task,
            title=title,
            description=description,
            brief_file=None,
            priority=priority,
            tag=tags,
            project=project,
            status="open",
            non_interactive=non_interactive,
            assign=None,
            parent=parent,
            author_did=author_did,
            author_location=author_location,
            kind=kind,
        )

    @group.command(name="list")
    @click.option("--status", help="Filter by status")
    @click.option("--priority", help="Filter by priority")
    @click.option("--project", help="Filter by project")
    @click.option("--tag", multiple=True, help="Additional tag filters")
    @click.option("--compact", is_flag=True)
    @click.option("--ids-only", is_flag=True)
    @click.option("--limit", type=int, default=50)
    @click.pass_context
    def list_cmd(
        ctx: click.Context,
        status: str | None,
        priority: str | None,
        project: str | None,
        tag: tuple[str, ...],
        compact: bool,
        ids_only: bool,
        limit: int,
    ) -> None:
        # Type-based: filter by kind=, not by tag. Extra --tag flags still
        # narrow within the kind.
        ctx.invoke(
            list_tasks,
            status=status,
            priority=priority,
            project=project,
            tag=tuple(tag),
            sort_by="status",
            limit=limit,
            compact=compact,
            ids_only=ids_only,
            kind=kind,
        )

    return group


# Memory carries extra structured fields (subject, scope, provenance).
# These are promoted to real frontmatter fields on the record so they
# round-trip cleanly and are queryable, rather than being jammed into a
# text preamble on the description.
def _make_memory_group() -> click.Group:
    base = _make_group("memory")

    # Replace the generic 'add' with a memory-aware one
    for name, _cmd in list(base.commands.items()):
        if name == "add":
            base.commands.pop(name)

    @base.command(name="add")
    @click.argument("title", required=False)
    @click.option("--description", "-d", help="Memory content")
    @click.option(
        "--subject",
        help="What this memory is about (e.g. 'user:preferences', "
        "'project:waypoint', 'agent:rosetta-agent', 'self')",
    )
    @click.option(
        "--scope",
        type=click.Choice(["private", "shared-with-user", "shared-across-agents"]),
        default="shared-with-user",
        help="Who can read this memory (default: shared-with-user)",
    )
    @click.option(
        "--provenance",
        help="How this memory was learned (e.g. 'conversation 2026-04-22', "
        "'observation', 'inferred from memory-id abc123')",
    )
    @click.option(
        "--priority",
        "-p",
        type=click.Choice(["low", "medium", "high", "urgent"]),
        default="medium",
    )
    @click.option("--tag", "-t", multiple=True)
    @click.option("--non-interactive", is_flag=True)
    @click.pass_context
    def memory_add(
        ctx: click.Context,
        title: str | None,
        description: str | None,
        subject: str | None,
        scope: str,
        provenance: str | None,
        priority: str,
        tag: tuple[str, ...],
        non_interactive: bool,
    ) -> None:
        """Add a memory record (agent-authored knowledge).

        Examples:
            hopper memory add "User prefers terse responses" --subject user:preferences
            hopper memory add "Rosetta queues peak at 03:00 UTC" \\
                --subject agent:rosetta-agent --scope shared-across-agents
        """
        # Promote subject/scope/provenance to real record fields (frontmatter)
        # instead of a text preamble on the description.
        tags = ("memory",) + tuple(t for t in tag if t != "memory")
        ctx.invoke(
            add_task,
            title=title,
            description=description,
            brief_file=None,
            priority=priority,
            tag=tags,
            project=None,
            status="open",
            non_interactive=non_interactive,
            assign=None,
            parent=None,
            author_did=None,
            author_location=None,
            kind="memory",
            subject=subject,
            scope=scope,
            provenance=provenance,
        )

    @base.command(name="session-summary")
    @click.option("--subject", help="Limit to memory records for this subject")
    @click.option(
        "--since",
        help="Only include records updated after this date (ISO format, e.g. 2026-06-01)",
    )
    @click.option("--save", is_flag=True, help="Save summary as a memory record (syncs upstream)")
    @click.option("--model", envvar="HOPPER_CONSOLIDATION_MODEL", hidden=True)
    @click.pass_obj
    def memory_session_summary(
        ctx: click.Context,
        subject: str | None,
        since: str | None,
        save: bool,
        model: str | None,
    ) -> None:
        """Generate a session summary for the current instance.

        Produces a concise LLM narrative covering what this instance knows
        (memory records), what is currently in flight (open tasks), and what
        was recently completed. Useful for context-loading at the start of a
        session or after a gap.

        Use --save to write the summary as a memory record so it syncs
        upstream and is visible to other agents entering this instance.

        Requires ANTHROPIC_API_KEY to be set.

        Examples:
            hopper memory session-summary
            hopper memory session-summary --subject project:waypoint
            hopper memory session-summary --save
            hopper memory session-summary --since 2026-06-01
        """
        from datetime import datetime

        from rich.console import Console
        from rich.markdown import Markdown

        from hopper.memory.session_summary import run_session_summary

        console = Console()

        since_dt = None
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
            except ValueError:
                console.print(f"[red]Invalid --since date:[/red] {since!r} (use ISO format)")
                raise SystemExit(1)

        with ctx.get_client() as client:
            result = run_session_summary(
                client,
                subject=subject,
                since=since_dt,
                save=save,
                model=model,
            )

        if "error" in result:
            console.print(f"[red]Error:[/red] {result['error']}")
            raise SystemExit(1)

        if result.get("skipped"):
            console.print(f"[yellow]Skipped:[/yellow] {result.get('reason')}")
            return

        console.print(Markdown(result["summary"]))

        if result.get("saved_id"):
            console.print(f"\n[dim]Saved as {result['saved_id']}[/dim]")
        if result.get("save_error"):
            console.print(f"\n[yellow]Warning:[/yellow] could not save — {result['save_error']}")

    @base.command(name="consolidate")
    @click.option("--subject", help="Only consolidate records for this subject")
    @click.option("--scope", help="Only consolidate records for this scope")
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Show what would be done without writing anything",
    )
    @click.option(
        "--propose",
        is_flag=True,
        help="Write propose revisions instead of applying directly",
    )
    @click.option("--model", envvar="HOPPER_CONSOLIDATION_MODEL", hidden=True)
    @click.pass_obj
    def memory_consolidate(
        ctx: click.Context,
        subject: str | None,
        scope: str | None,
        dry_run: bool,
        propose: bool,
        model: str | None,
    ) -> None:
        """Run LLM-driven consolidation over memory records.

        Classifies episodic/durable_fact/noise, merges overlapping episodic
        records into consolidated summaries, and updates source records with
        superseded_by. Results sync upstream via the normal record-update path.

        Requires ANTHROPIC_API_KEY to be set.

        Examples:
            hopper memory consolidate --subject project:waypoint --dry-run
            hopper memory consolidate --subject project:waypoint
        """
        from rich.console import Console

        from hopper.memory.consolidation import run_consolidation

        console = Console()

        with ctx.get_client() as client:
            result = run_consolidation(
                client,
                subject=subject,
                scope=scope,
                dry_run=dry_run,
                propose=propose,
                model=model,
            )

        if "error" in result:
            console.print(f"[red]Error:[/red] {result['error']}")
            raise SystemExit(1)

        if result.get("skipped"):
            console.print(f"[yellow]Skipped:[/yellow] {result.get('reason', 'no records')}")
            return

        if result.get("dry_run"):
            console.print(
                f"[bold]Dry run[/bold] — {result['eligible']} eligible records\n"
                f"  Classifications: {len(result.get('classifications', []))}\n"
                f"  Clusters to merge: {len(result.get('clusters', []))}"
            )
            for cluster in result.get("clusters", []):
                src = ", ".join(cluster.get("source_ids", []))
                console.print(f"  [dim]•[/dim] {cluster.get('title')} ← [{src}]")
            return

        console.print(
            f"[green]Consolidation complete[/green] (run {result.get('run_id')})\n"
            f"  Eligible records: {result['eligible']}\n"
            f"  Consolidated records created: {result['consolidated_records_created']}\n"
            f"  Source records superseded: {result['source_records_superseded']}\n"
            f"  Classified only: {result['records_classified_only']}\n"
            f"  Durable facts flagged: {result['durable_facts_flagged']}"
        )
        if result.get("errors"):
            console.print("[yellow]Errors:[/yellow]")
            for err in result["errors"]:
                console.print(f"  [red]•[/red] {err}")

    @base.command(name="drift-check")
    @click.argument("record_id", required=False)
    @click.option("--subject", help="Check all consolidated records for this subject")
    @click.option("--model", envvar="HOPPER_CONSOLIDATION_MODEL", hidden=True)
    @click.pass_obj
    def memory_drift_check(
        ctx: click.Context,
        record_id: str | None,
        subject: str | None,
        model: str | None,
    ) -> None:
        """Check consolidated memory records for drift against their sources.

        Re-derives each consolidated summary from its source records and scores
        how accurately the summary still represents them. Sets drift_score and
        drift_checked_at on the consolidated record.

        Requires ANTHROPIC_API_KEY to be set.

        Examples:
            hopper memory drift-check
            hopper memory drift-check --subject project:waypoint
            hopper memory drift-check <record-id>
        """
        from rich.console import Console

        from hopper.memory.consolidation import run_drift_check

        console = Console()

        with ctx.get_client() as client:
            result = run_drift_check(
                client,
                record_id=record_id,
                subject=subject,
                model=model,
            )

        if "error" in result:
            console.print(f"[red]Error:[/red] {result['error']}")
            raise SystemExit(1)

        if result.get("skipped"):
            console.print(f"[yellow]Skipped:[/yellow] {result.get('reason', 'no records')}")
            return

        console.print(
            f"[green]Drift check complete[/green]\n"
            f"  Checked: {result['checked']}\n"
            f"  High drift (>0.1): {result['high_drift_count']}"
        )
        for rec in result.get("high_drift", []):
            console.print(
                f"  [yellow]•[/yellow] {rec['id']} [{rec['drift_score']:.2f}] "
                f"{rec.get('title', '')} — {rec.get('explanation', '')}"
            )
        if result.get("errors"):
            console.print("[yellow]Errors:[/yellow]")
            for err in result["errors"]:
                console.print(f"  [red]•[/red] {err}")

    return base


def register(cli: click.Group) -> None:
    """Mount kind groups on the root CLI."""
    for kind in _KINDS:
        if kind == "memory":
            cli.add_command(_make_memory_group())
        else:
            cli.add_command(_make_group(kind))
