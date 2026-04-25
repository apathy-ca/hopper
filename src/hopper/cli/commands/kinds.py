"""Per-kind CLI wrappers.

Phase 4c (client-side). Adds ``hopper idea``, ``hopper note``,
``hopper memory``, ``hopper log``, ``hopper reference``, and
``hopper inbox`` command groups as thin wrappers over ``hopper task``
that prefill the kind as a tag.

This is intentionally storage-layer-free. Until Phase 4a's live write
path is wired, kind is encoded as a tag on the underlying task record.
Once records.type is populated at write time, these wrappers can set
it directly without behavior change for users.

Memory ergonomics: ``hopper memory add`` accepts ``--subject`` and
``--scope`` to capture agent-knowledge structure up front; these are
written as a structured preamble on the description so they survive
the markdown round-trip and are easy to read both by humans and by
future triage agents. See plans/Phase-4-Revisions-DID-Agent-Plan.md
for the full payload shape.
"""

from __future__ import annotations

from typing import Any

import click

from hopper.cli.commands.task import add_task, list_tasks

_KINDS = ("idea", "note", "memory", "log", "reference", "inbox")


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
        tags = (kind,) + tuple(t for t in tag if t != kind)
        ctx.invoke(
            list_tasks,
            status=status,
            priority=priority,
            project=project,
            tag=tags,
            sort_by="status",
            limit=limit,
            compact=compact,
            ids_only=ids_only,
        )

    return group


# Memory gets extra structured fields that bleed into the description as
# a preamble. This keeps the storage layer untouched while preserving the
# agent-knowledge shape (subject, scope, provenance) for triage agents and
# the eventual type=memory SQL representation to parse.
def _make_memory_group() -> click.Group:
    base = _make_group("memory")

    # Replace the generic 'add' with a memory-aware one
    for name, cmd in list(base.commands.items()):
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
        preamble_lines: list[str] = []
        if subject:
            preamble_lines.append(f"Subject: {subject}")
        preamble_lines.append(f"Scope: {scope}")
        if provenance:
            preamble_lines.append(f"Provenance: {provenance}")
        preamble = "\n".join(preamble_lines)

        if description:
            full_desc = f"{preamble}\n\n{description}"
        else:
            full_desc = preamble

        tags = ("memory",) + tuple(t for t in tag if t != "memory")
        ctx.invoke(
            add_task,
            title=title,
            description=full_desc,
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
        )

    return base


def register(cli: click.Group) -> None:
    """Mount kind groups on the root CLI."""
    for kind in _KINDS:
        if kind == "memory":
            cli.add_command(_make_memory_group())
        else:
            cli.add_command(_make_group(kind))
