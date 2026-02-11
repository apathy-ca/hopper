"""Learning system commands for feedback, patterns, and statistics."""

import click
from rich import box
from rich.prompt import Confirm, Prompt
from rich.table import Table

from hopper.cli.client import APIError, HopperClient
from hopper.cli.main import Context
from hopper.cli.output import (
    console,
    format_datetime,
    print_error,
    print_info,
    print_json,
    print_success,
)


@click.group(name="learning")
def learning() -> None:
    """Manage learning system - feedback, patterns, and statistics.

    The learning system improves task routing over time by collecting
    feedback and extracting patterns from successful routing decisions.
    """
    pass


# ============================================================================
# Feedback Commands
# ============================================================================


@learning.group(name="feedback")
def feedback() -> None:
    """Manage routing feedback.

    Feedback helps the learning system understand which routing
    decisions were correct and which need improvement.
    """
    pass


@feedback.command(name="submit")
@click.argument("task_id")
@click.option(
    "--good/--bad",
    "was_good_match",
    default=None,
    help="Was the routing decision correct?",
)
@click.option("--should-route-to", help="Instance that should have received the task")
@click.option("--comment", "-c", help="Feedback comment")
@click.option("--quality", type=float, help="Quality score (0.0-5.0)")
@click.option("--complexity", type=int, help="Complexity rating (1-5)")
@click.option("--rework/--no-rework", default=None, help="Required rework?")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode")
@click.pass_obj
def submit_feedback(
    ctx: Context,
    task_id: str,
    was_good_match: bool | None,
    should_route_to: str | None,
    comment: str | None,
    quality: float | None,
    complexity: int | None,
    rework: bool | None,
    interactive: bool,
) -> None:
    """Submit feedback for a task's routing decision.

    Examples:
        hopper learning feedback submit TASK-001 --good
        hopper learning feedback submit TASK-001 --bad --should-route-to api-instance
        hopper learning feedback submit TASK-001 --interactive
    """
    if interactive:
        console.print("\n[bold cyan]Submit Routing Feedback[/bold cyan]\n")

        was_good_match = Confirm.ask("Was the routing decision correct?", default=True)

        if not was_good_match:
            should_route_to = Prompt.ask(
                "Which instance should have received this task?",
                default="",
            )
            if not should_route_to:
                should_route_to = None

        comment = Prompt.ask("Any comments?", default="")
        if not comment:
            comment = None

        quality_input = Prompt.ask("Quality score (0.0-5.0, Enter to skip)", default="")
        quality = float(quality_input) if quality_input else None

        complexity_input = Prompt.ask("Complexity (1-5, Enter to skip)", default="")
        complexity = int(complexity_input) if complexity_input else None

        rework = Confirm.ask("Required rework?", default=False)

    if was_good_match is None:
        print_error("Must specify --good or --bad (or use --interactive)")
        raise click.Abort()

    feedback_data = {
        "was_good_match": was_good_match,
    }

    if should_route_to:
        feedback_data["should_have_routed_to"] = should_route_to
    if comment:
        feedback_data["routing_feedback"] = comment
    if quality is not None:
        feedback_data["quality_score"] = quality
    if complexity is not None:
        feedback_data["complexity_rating"] = complexity
    if rework is not None:
        feedback_data["required_rework"] = rework

    try:
        with HopperClient(ctx.config) as client:
            result = client.submit_feedback(task_id, feedback_data)

        if ctx.json_output:
            print_json(result)
        else:
            status = "positive" if was_good_match else "negative"
            print_success(f"Submitted {status} feedback for task {task_id}")

    except APIError as e:
        print_error(f"Failed to submit feedback: {e.message}")
        raise click.Abort()


@feedback.command(name="get")
@click.argument("task_id")
@click.pass_obj
def get_feedback(ctx: Context, task_id: str) -> None:
    """Get feedback for a specific task.

    Examples:
        hopper learning feedback get TASK-001
    """
    try:
        with HopperClient(ctx.config) as client:
            result = client.get_task_feedback(task_id)

        if ctx.json_output:
            print_json(result)
        else:
            _print_feedback_detail(result)

    except APIError as e:
        print_error(f"Failed to get feedback: {e.message}")
        raise click.Abort()


@feedback.command(name="list")
@click.option("--good-only", is_flag=True, help="Only show positive feedback")
@click.option("--bad-only", is_flag=True, help="Only show negative feedback")
@click.option("--limit", type=int, default=20, help="Maximum results")
@click.pass_obj
def list_feedback(
    ctx: Context,
    good_only: bool,
    bad_only: bool,
    limit: int,
) -> None:
    """List feedback records.

    Examples:
        hopper learning feedback list
        hopper learning feedback list --bad-only
    """
    params = {"limit": limit}

    if good_only:
        params["good_matches_only"] = True
    elif bad_only:
        params["good_matches_only"] = False

    try:
        with HopperClient(ctx.config) as client:
            result = client.list_feedback(**params)

        if ctx.json_output:
            print_json(result)
        else:
            items = result.get("items", [])
            if not items:
                print_info("No feedback records found")
                return

            _print_feedback_table(items)
            print_info(f"Showing {len(items)} of {result.get('total', len(items))} feedback records")

    except APIError as e:
        print_error(f"Failed to list feedback: {e.message}")
        raise click.Abort()


@feedback.command(name="accuracy")
@click.option("--days", type=int, default=30, help="Number of days to analyze")
@click.pass_obj
def routing_accuracy(ctx: Context, days: int) -> None:
    """Show routing accuracy statistics.

    Examples:
        hopper learning feedback accuracy
        hopper learning feedback accuracy --days 7
    """
    try:
        with HopperClient(ctx.config) as client:
            result = client.get_routing_accuracy(days=days)

        if ctx.json_output:
            print_json(result)
        else:
            _print_accuracy_stats(result, days)

    except APIError as e:
        print_error(f"Failed to get accuracy stats: {e.message}")
        raise click.Abort()


# ============================================================================
# Pattern Commands
# ============================================================================


@learning.group(name="pattern")
def pattern() -> None:
    """Manage routing patterns.

    Patterns are learned rules for routing tasks to instances based on
    tags, text, priority, and other criteria.
    """
    pass


@pattern.command(name="create")
@click.option("--name", "-n", required=True, help="Pattern name")
@click.option("--target", "-t", required=True, help="Target instance ID")
@click.option("--type", "pattern_type", type=click.Choice(["tag", "text", "combined", "priority"]), default="tag")
@click.option("--description", "-d", help="Pattern description")
@click.option("--required-tag", multiple=True, help="Required tags (can specify multiple)")
@click.option("--optional-tag", multiple=True, help="Optional tags (can specify multiple)")
@click.option("--keyword", multiple=True, help="Text keywords (can specify multiple)")
@click.option("--priority-match", help="Priority to match")
@click.option("--confidence", type=float, default=0.5, help="Initial confidence (0.0-1.0)")
@click.pass_obj
def create_pattern(
    ctx: Context,
    name: str,
    target: str,
    pattern_type: str,
    description: str | None,
    required_tag: tuple[str, ...],
    optional_tag: tuple[str, ...],
    keyword: tuple[str, ...],
    priority_match: str | None,
    confidence: float,
) -> None:
    """Create a new routing pattern.

    Examples:
        hopper learning pattern create --name api-tasks --target api-instance --required-tag api --required-tag python
        hopper learning pattern create --name urgent-tasks --target fast-instance --type priority --priority-match urgent
    """
    pattern_data = {
        "name": name,
        "target_instance": target,
        "pattern_type": pattern_type,
        "confidence": confidence,
    }

    if description:
        pattern_data["description"] = description

    if required_tag or optional_tag:
        pattern_data["tag_criteria"] = {}
        if required_tag:
            pattern_data["tag_criteria"]["required"] = list(required_tag)
        if optional_tag:
            pattern_data["tag_criteria"]["optional"] = list(optional_tag)

    if keyword:
        pattern_data["text_criteria"] = {"keywords": list(keyword)}

    if priority_match:
        pattern_data["priority_criteria"] = priority_match

    try:
        with HopperClient(ctx.config) as client:
            result = client.create_pattern(pattern_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Created pattern: {result.get('name', '')} (ID: {result.get('id', '')})")

    except APIError as e:
        print_error(f"Failed to create pattern: {e.message}")
        raise click.Abort()


@pattern.command(name="list")
@click.option("--all", "show_all", is_flag=True, help="Include inactive patterns")
@click.option("--instance", help="Filter by target instance")
@click.option("--limit", type=int, default=20, help="Maximum results")
@click.pass_obj
def list_patterns(
    ctx: Context,
    show_all: bool,
    instance: str | None,
    limit: int,
) -> None:
    """List routing patterns.

    Examples:
        hopper learning pattern list
        hopper learning pattern list --all
        hopper learning pattern list --instance api-instance
    """
    params = {"limit": limit, "active_only": not show_all}

    if instance:
        params["instance_id"] = instance

    try:
        with HopperClient(ctx.config) as client:
            result = client.list_patterns(**params)

        if ctx.json_output:
            print_json(result)
        else:
            items = result.get("items", [])
            if not items:
                print_info("No patterns found")
                return

            _print_pattern_table(items)
            print_info(f"Showing {len(items)} of {result.get('total', len(items))} patterns")

    except APIError as e:
        print_error(f"Failed to list patterns: {e.message}")
        raise click.Abort()


@pattern.command(name="get")
@click.argument("pattern_id")
@click.pass_obj
def get_pattern(ctx: Context, pattern_id: str) -> None:
    """Get pattern details.

    Examples:
        hopper learning pattern get pat-abc123
    """
    try:
        with HopperClient(ctx.config) as client:
            result = client.get_pattern(pattern_id)

        if ctx.json_output:
            print_json(result)
        else:
            _print_pattern_detail(result)

    except APIError as e:
        print_error(f"Failed to get pattern: {e.message}")
        raise click.Abort()


@pattern.command(name="update")
@click.argument("pattern_id")
@click.option("--name", help="New name")
@click.option("--description", help="New description")
@click.option("--confidence", type=float, help="New confidence (0.0-1.0)")
@click.option("--activate/--deactivate", default=None, help="Activate or deactivate pattern")
@click.pass_obj
def update_pattern(
    ctx: Context,
    pattern_id: str,
    name: str | None,
    description: str | None,
    confidence: float | None,
    activate: bool | None,
) -> None:
    """Update a pattern.

    Examples:
        hopper learning pattern update pat-abc123 --name "new-name"
        hopper learning pattern update pat-abc123 --deactivate
        hopper learning pattern update pat-abc123 --confidence 0.9
    """
    update_data = {}

    if name:
        update_data["name"] = name
    if description:
        update_data["description"] = description
    if confidence is not None:
        update_data["confidence"] = confidence
    if activate is not None:
        update_data["is_active"] = activate

    if not update_data:
        print_error("No updates specified")
        raise click.Abort()

    try:
        with HopperClient(ctx.config) as client:
            result = client.update_pattern(pattern_id, update_data)

        if ctx.json_output:
            print_json(result)
        else:
            print_success(f"Updated pattern: {result.get('name', '')}")

    except APIError as e:
        print_error(f"Failed to update pattern: {e.message}")
        raise click.Abort()


@pattern.command(name="delete")
@click.argument("pattern_id")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def delete_pattern(ctx: Context, pattern_id: str, force: bool) -> None:
    """Delete a pattern.

    Examples:
        hopper learning pattern delete pat-abc123
        hopper learning pattern delete pat-abc123 --force
    """
    if not force:
        if not Confirm.ask(f"[bold red]Delete pattern {pattern_id}?[/bold red]", default=False):
            print_info("Cancelled")
            return

    try:
        with HopperClient(ctx.config) as client:
            client.delete_pattern(pattern_id)

        print_success(f"Deleted pattern: {pattern_id}")

    except APIError as e:
        print_error(f"Failed to delete pattern: {e.message}")
        raise click.Abort()


# ============================================================================
# Statistics Commands
# ============================================================================


@learning.command(name="stats")
@click.pass_obj
def learning_stats(ctx: Context) -> None:
    """Show overall learning statistics.

    Displays statistics about episodic memory, patterns, and the
    semantic search system.

    Examples:
        hopper learning stats
    """
    try:
        with HopperClient(ctx.config) as client:
            result = client.get_learning_statistics()

        if ctx.json_output:
            print_json(result)
        else:
            _print_learning_stats(result)

    except APIError as e:
        print_error(f"Failed to get statistics: {e.message}")
        raise click.Abort()


@learning.command(name="consolidate")
@click.option("--days", type=int, default=7, help="Days of data to analyze")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation")
@click.pass_obj
def consolidate(ctx: Context, days: int, force: bool) -> None:
    """Run pattern consolidation.

    Extracts new patterns from successful routing decisions in
    episodic memory.

    Examples:
        hopper learning consolidate
        hopper learning consolidate --days 14
    """
    if not force:
        if not Confirm.ask(f"Run consolidation on last {days} days of data?", default=True):
            print_info("Cancelled")
            return

    try:
        with HopperClient(ctx.config) as client:
            result = client.run_consolidation(days=days)

        if ctx.json_output:
            print_json(result)
        else:
            console.print("\n[bold cyan]Consolidation Complete[/bold cyan]\n")
            console.print(f"  Patterns created: {result.get('patterns_created', 0)}")
            console.print(f"  Period analyzed: last {days} days")
            console.print(f"  Ran at: {result.get('ran_at', 'unknown')}")
            console.print()

    except APIError as e:
        print_error(f"Failed to run consolidation: {e.message}")
        raise click.Abort()


# ============================================================================
# Output Helpers
# ============================================================================


def _print_feedback_detail(feedback: dict) -> None:
    """Print detailed feedback information."""
    console.print("\n[bold cyan]Feedback Details[/bold cyan]\n")

    console.print(f"  [bold]Task ID:[/bold] {feedback.get('task_id', '')}")

    match = feedback.get("was_good_match")
    if match is True:
        console.print("  [bold]Match:[/bold] [green]Good[/green]")
    elif match is False:
        console.print("  [bold]Match:[/bold] [red]Bad[/red]")
    else:
        console.print("  [bold]Match:[/bold] [dim]Unknown[/dim]")

    if feedback.get("should_have_routed_to"):
        console.print(f"  [bold]Should Route To:[/bold] {feedback['should_have_routed_to']}")

    if feedback.get("routing_feedback"):
        console.print(f"  [bold]Comment:[/bold] {feedback['routing_feedback']}")

    if feedback.get("quality_score") is not None:
        console.print(f"  [bold]Quality:[/bold] {feedback['quality_score']:.1f}/5.0")

    if feedback.get("complexity_rating") is not None:
        console.print(f"  [bold]Complexity:[/bold] {feedback['complexity_rating']}/5")

    if feedback.get("required_rework") is not None:
        rework = "Yes" if feedback["required_rework"] else "No"
        console.print(f"  [bold]Required Rework:[/bold] {rework}")

    if feedback.get("created_at"):
        console.print(f"  [bold]Created:[/bold] {format_datetime(feedback['created_at'])}")

    console.print()


def _print_feedback_table(items: list[dict]) -> None:
    """Print feedback list as table."""
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("Task ID", style="dim")
    table.add_column("Match", justify="center")
    table.add_column("Quality", justify="center")
    table.add_column("Should Route To")
    table.add_column("Created", style="dim")

    for fb in items:
        match = fb.get("was_good_match")
        if match is True:
            match_str = "[green]Good[/green]"
        elif match is False:
            match_str = "[red]Bad[/red]"
        else:
            match_str = "[dim]—[/dim]"

        quality = fb.get("quality_score")
        quality_str = f"{quality:.1f}" if quality is not None else "—"

        should_route = fb.get("should_have_routed_to") or "—"
        created = format_datetime(fb.get("created_at"))

        table.add_row(
            fb.get("task_id", "")[:12],
            match_str,
            quality_str,
            should_route[:20] if should_route != "—" else should_route,
            created,
        )

    console.print()
    console.print(table)
    console.print()


def _print_accuracy_stats(stats: dict, days: int) -> None:
    """Print routing accuracy statistics."""
    console.print(f"\n[bold cyan]Routing Accuracy (Last {days} Days)[/bold cyan]\n")

    total = stats.get("total_feedback", 0)
    good = stats.get("good_matches", 0)
    bad = stats.get("bad_matches", 0)
    rate = stats.get("accuracy_rate", 0)

    console.print(f"  [bold]Total Feedback:[/bold] {total}")
    console.print(f"  [bold]Good Matches:[/bold] [green]{good}[/green]")
    console.print(f"  [bold]Bad Matches:[/bold] [red]{bad}[/red]")
    console.print(f"  [bold]Accuracy Rate:[/bold] {rate:.1%}")

    misroutes = stats.get("common_misrouting_targets", [])
    if misroutes:
        console.print("\n  [bold]Common Misrouting Targets:[/bold]")
        for target in misroutes[:5]:
            console.print(f"    - {target.get('target', '')}: {target.get('count', 0)} times")

    by_instance = stats.get("by_instance", {})
    if by_instance:
        console.print("\n  [bold]By Instance:[/bold]")
        for inst_id, inst_stats in list(by_instance.items())[:5]:
            rate = inst_stats.get("accuracy", 0)
            console.print(f"    - {inst_id[:20]}: {rate:.1%}")

    console.print()


def _print_pattern_table(items: list[dict]) -> None:
    """Print pattern list as table."""
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=12)
    table.add_column("Name")
    table.add_column("Type", justify="center")
    table.add_column("Target")
    table.add_column("Conf", justify="center")
    table.add_column("Success", justify="center")
    table.add_column("Active", justify="center")

    for p in items:
        conf = p.get("confidence", 0)
        success_rate = p.get("success_rate", 0)
        active = "[green]Yes[/green]" if p.get("is_active") else "[red]No[/red]"

        table.add_row(
            p.get("id", "")[:12],
            p.get("name", "")[:20],
            p.get("pattern_type", "tag"),
            p.get("target_instance", "")[:15],
            f"{conf:.0%}",
            f"{success_rate:.0%}",
            active,
        )

    console.print()
    console.print(table)
    console.print()


def _print_pattern_detail(pattern: dict) -> None:
    """Print detailed pattern information."""
    console.print("\n[bold cyan]Pattern Details[/bold cyan]\n")

    console.print(f"  [bold]ID:[/bold] {pattern.get('id', '')}")
    console.print(f"  [bold]Name:[/bold] {pattern.get('name', '')}")
    console.print(f"  [bold]Type:[/bold] {pattern.get('pattern_type', 'tag')}")
    console.print(f"  [bold]Target:[/bold] {pattern.get('target_instance', '')}")

    if pattern.get("description"):
        console.print(f"  [bold]Description:[/bold] {pattern['description']}")

    console.print(f"\n  [bold]Confidence:[/bold] {pattern.get('confidence', 0):.0%}")
    console.print(f"  [bold]Usage Count:[/bold] {pattern.get('usage_count', 0)}")
    console.print(f"  [bold]Success Count:[/bold] {pattern.get('success_count', 0)}")
    console.print(f"  [bold]Failure Count:[/bold] {pattern.get('failure_count', 0)}")
    console.print(f"  [bold]Success Rate:[/bold] {pattern.get('success_rate', 0):.0%}")

    active = "Yes" if pattern.get("is_active") else "No"
    console.print(f"  [bold]Active:[/bold] {active}")

    if pattern.get("tag_criteria"):
        console.print(f"\n  [bold]Tag Criteria:[/bold]")
        tc = pattern["tag_criteria"]
        if tc.get("required"):
            console.print(f"    Required: {', '.join(tc['required'])}")
        if tc.get("optional"):
            console.print(f"    Optional: {', '.join(tc['optional'])}")

    if pattern.get("text_criteria"):
        console.print(f"\n  [bold]Text Criteria:[/bold]")
        tc = pattern["text_criteria"]
        if tc.get("keywords"):
            console.print(f"    Keywords: {', '.join(tc['keywords'])}")

    if pattern.get("priority_criteria"):
        console.print(f"  [bold]Priority Match:[/bold] {pattern['priority_criteria']}")

    if pattern.get("created_at"):
        console.print(f"\n  [bold]Created:[/bold] {format_datetime(pattern['created_at'])}")
    if pattern.get("last_used_at"):
        console.print(f"  [bold]Last Used:[/bold] {format_datetime(pattern['last_used_at'])}")

    console.print()


def _print_learning_stats(stats: dict) -> None:
    """Print overall learning statistics."""
    console.print("\n[bold cyan]Learning System Statistics[/bold cyan]\n")

    # Episodic stats
    episodic = stats.get("episodic", {})
    console.print("  [bold]Episodic Memory:[/bold]")
    console.print(f"    Total Episodes: {episodic.get('total_episodes', 0)}")
    console.print(f"    Successful: [green]{episodic.get('successful', 0)}[/green]")
    console.print(f"    Failed: [red]{episodic.get('failed', 0)}[/red]")
    console.print(f"    Pending: {episodic.get('pending', 0)}")
    console.print(f"    Success Rate: {episodic.get('success_rate', 0):.1%}")
    console.print(f"    Avg Confidence: {episodic.get('average_confidence', 0):.0%}")

    # Pattern stats
    patterns = stats.get("patterns", {})
    console.print("\n  [bold]Patterns:[/bold]")
    console.print(f"    Total: {patterns.get('total_patterns', 0)}")
    console.print(f"    Active: [green]{patterns.get('active_patterns', 0)}[/green]")
    console.print(f"    Inactive: [dim]{patterns.get('inactive_patterns', 0)}[/dim]")
    console.print(f"    Total Usage: {patterns.get('total_usage', 0)}")
    console.print(f"    Avg Confidence: {patterns.get('average_confidence', 0):.0%}")

    by_type = patterns.get("by_type", {})
    if by_type:
        console.print("    By Type:", end="")
        type_strs = [f" {t}={c}" for t, c in by_type.items()]
        console.print(",".join(type_strs))

    # Searcher stats
    searcher = stats.get("searcher", {})
    console.print("\n  [bold]Semantic Search:[/bold]")
    console.print(f"    Index Size: {searcher.get('index_size', 0)}")
    console.print(f"    Backend: {searcher.get('backend', 'unknown')}")

    console.print()
