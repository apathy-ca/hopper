"""End-to-end CLI tests for kind-based segmentation.

Covers:
  - `hopper memory add` round-trips subject/scope/provenance via frontmatter
  - `hopper context` shows a memory under Memory, never under Open Tasks
  - a kind=job record is absent from `hopper task list` but present in
    `hopper job list`
  - `hopper maintenance reclassify` (dry-run) reports counts and mutates nothing
"""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hopper.cli.main import cli


@pytest.fixture
def isolated_runner():
    runner = CliRunner()
    with runner.isolated_filesystem() as tmpdir:
        hopper_dir = Path(tmpdir) / ".hopper"
        hopper_dir.mkdir()
        (hopper_dir / "tasks").mkdir()
        yield runner, hopper_dir


class TestMemoryAdd:
    def test_memory_add_round_trips_structured_fields(self, isolated_runner):
        runner, _ = isolated_runner

        result = runner.invoke(
            cli,
            [
                "--json", "memory", "add", "User prefers terse responses",
                "--subject", "user:preferences",
                "--scope", "shared-across-agents",
                "--provenance", "conversation 2026-05-30",
                "--non-interactive",
            ],
        )
        assert result.exit_code == 0, f"Failed: {result.output}"
        created = json.loads(result.output.strip())
        mem_id = created["id"]

        # Read it back via task get (full record dict)
        result = runner.invoke(cli, ["--json", "task", "get", mem_id])
        assert result.exit_code == 0, f"Failed: {result.output}"
        rec = json.loads(result.output.strip())

        assert rec["kind"] == "memory"
        assert rec["subject"] == "user:preferences"
        assert rec["scope"] == "shared-across-agents"
        assert rec["provenance"] == "conversation 2026-05-30"
        # The structured data is NOT jammed into the description preamble.
        assert "Subject:" not in (rec.get("description") or "")

    def test_memory_list_filters_by_kind(self, isolated_runner):
        runner, _ = isolated_runner

        runner.invoke(cli, ["--json", "memory", "add", "A memory", "--non-interactive"])
        runner.invoke(cli, ["--json", "task", "add", "A task", "--tag", "x"])

        result = runner.invoke(cli, ["--json", "memory", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        items = json.loads(result.output.strip())
        titles = {i["title"] for i in items}
        assert "A memory" in titles
        assert "A task" not in titles


class TestContextSegmentation:
    def test_memory_shown_under_memory_not_tasks(self, isolated_runner):
        runner, _ = isolated_runner

        runner.invoke(
            cli,
            ["--json", "memory", "add", "Remember the API key rotates monthly",
             "--non-interactive"],
        )
        runner.invoke(cli, ["--json", "task", "add", "Ship the release", "--tag", "rel"])

        result = runner.invoke(cli, ["--json", "context", "show"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        ctx = json.loads(result.output.strip())

        mem_titles = {m["title"] for m in ctx["memory"]}
        task_titles = {t["title"] for t in ctx["tasks"]}

        assert "Remember the API key rotates monthly" in mem_titles
        assert "Remember the API key rotates monthly" not in task_titles
        assert "Ship the release" in task_titles
        assert "Ship the release" not in mem_titles


class TestJobSegmentation:
    def test_job_absent_from_task_list_present_in_job_list(self, isolated_runner):
        runner, _ = isolated_runner

        runner.invoke(cli, ["--json", "job", "add", "Train model run-42", "--non-interactive"])
        runner.invoke(cli, ["--json", "task", "add", "Review PR", "--tag", "review"])

        # task list — default kind=task, job excluded
        result = runner.invoke(cli, ["--json", "task", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        task_titles = {t["title"] for t in json.loads(result.output.strip())}
        assert "Review PR" in task_titles
        assert "Train model run-42" not in task_titles

        # job list — shows the job
        result = runner.invoke(cli, ["--json", "job", "list"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        job_titles = {t["title"] for t in json.loads(result.output.strip())}
        assert "Train model run-42" in job_titles
        assert "Review PR" not in job_titles

    def test_all_kinds_escape_hatch_shows_job(self, isolated_runner):
        runner, _ = isolated_runner

        runner.invoke(cli, ["--json", "job", "add", "GPU job alpha", "--non-interactive"])

        result = runner.invoke(cli, ["--json", "task", "list", "--all-kinds"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        titles = {t["title"] for t in json.loads(result.output.strip())}
        assert "GPU job alpha" in titles


class TestReclassifyDryRun:
    def test_dry_run_reports_counts_and_mutates_nothing(self, isolated_runner):
        runner, _ = isolated_runner

        # Legacy tag-encoded records (kind defaults to task).
        runner.invoke(cli, ["--json", "task", "add", "old gpu thing", "--tag", "gpu-job"])
        runner.invoke(cli, ["--json", "task", "add", "old memory thing", "--tag", "claude-import"])
        runner.invoke(cli, ["--json", "task", "add", "a real task", "--tag", "keep"])

        # Dry-run
        result = runner.invoke(cli, ["--json", "maintenance", "reclassify"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        report = json.loads(result.output.strip())
        assert report["dry_run"] is True
        assert report["would_change"] == 2
        assert report["by_kind"]["job"] == 1
        assert report["by_kind"]["memory"] == 1

        # Nothing changed: the gpu-job record is still kind=task and still in
        # the default task list.
        result = runner.invoke(cli, ["--json", "task", "list"])
        titles = {t["title"] for t in json.loads(result.output.strip())}
        assert "old gpu thing" in titles
        assert "old memory thing" in titles

    def test_apply_reclassifies(self, isolated_runner):
        runner, _ = isolated_runner

        runner.invoke(cli, ["--json", "task", "add", "old gpu thing", "--tag", "gpu-job"])
        runner.invoke(cli, ["--json", "task", "add", "old memory thing", "--tag", "memory"])

        result = runner.invoke(cli, ["--json", "maintenance", "reclassify", "--apply"])
        assert result.exit_code == 0, f"Failed: {result.output}"
        report = json.loads(result.output.strip())
        assert report["dry_run"] is False
        assert report["applied"] == 2

        # The gpu record now lives under jobs, the memory under memory; neither
        # pollutes the default task list.
        task_titles = {
            t["title"]
            for t in json.loads(runner.invoke(cli, ["--json", "task", "list"]).output.strip())
        }
        assert "old gpu thing" not in task_titles
        assert "old memory thing" not in task_titles

        job_titles = {
            t["title"]
            for t in json.loads(runner.invoke(cli, ["--json", "job", "list"]).output.strip())
        }
        assert "old gpu thing" in job_titles
