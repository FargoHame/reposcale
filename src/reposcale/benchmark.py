from __future__ import annotations

import csv
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from reposcale.artifacts import load_evaluation, load_task, load_run, write_artifact
from reposcale.diagnostics import collect_run_diagnostics
from reposcale.evaluation import create_evaluation_artifact
from reposcale.runs import AgentName, create_run_artifact
from reposcale.schemas import CommandResult, EvaluationResult, ModelConfig, RunArtifact


class BenchmarkBudgets(BaseModel):
    max_steps: int = Field(default=35, gt=0)
    recursion_limit: int | None = Field(default=300, gt=0)


class BenchmarkTask(BaseModel):
    task_path: Path
    repo_commit: str
    source_base_commit: str | None = None
    source_issue: str | None = None
    difficulty: str | None = None
    domain: str | None = None


class BenchmarkSuite(BaseModel):
    suite_id: str = Field(min_length=1)
    harness_ref: str = Field(min_length=1)
    agents: list[Literal["baseline", "engineered"]] = Field(default_factory=lambda: ["baseline", "engineered"])
    model: ModelConfig
    budgets: BenchmarkBudgets = Field(default_factory=BenchmarkBudgets)
    tasks: list[BenchmarkTask]


class BenchmarkRow(BaseModel):
    suite_id: str
    harness_ref: str
    task_id: str
    task_path: str
    repo_path: str
    repo_commit: str
    source_base_commit: str | None = None
    source_issue: str | None = None
    difficulty: str | None = None
    domain: str | None = None
    agent: str
    run_id: str
    eval_id: str
    run_status: str
    eval_status: str
    semantic_status: str
    quality_status: str
    clean_pass: bool
    test_exit_code: int | None = None
    semantic_exit_code: int | None = None
    model_calls: int
    tool_calls: int
    invalid_responses: int
    tool_errors: int
    repeated_tool_calls: int
    repeated_tool_errors: int
    context_stall_tool_calls: int
    edit_attempts: int
    no_op_edits: int
    repeated_edit_attempts: int
    validations_after_edit: int
    files_read: int
    commands_run: int
    changed_files: int
    lines_added: int
    lines_removed: int
    run_duration_seconds: float
    test_duration_seconds: float | None = None
    semantic_duration_seconds: float | None = None
    patch_quality_warnings: list[str] = Field(default_factory=list)
    behaviorally_wrong_pass: bool = False


class BenchmarkReport(BaseModel):
    report_id: str
    suite_id: str
    harness_ref: str
    generated_at: datetime
    model: ModelConfig
    budgets: BenchmarkBudgets
    rows: list[BenchmarkRow]


def load_benchmark_suite(path: Path) -> BenchmarkSuite:
    with path.open("r", encoding="utf-8") as file:
        raw_suite = yaml.safe_load(file)
    if not isinstance(raw_suite, dict):
        raise ValueError("benchmark suite YAML must contain a mapping/object at the top level")
    return BenchmarkSuite.model_validate(raw_suite)


def run_benchmark_suite(
    suite_path: Path,
    runs_dir: Path,
    evals_dir: Path,
    reports_dir: Path,
    execute_agent: bool = False,
) -> Path:
    suite = load_benchmark_suite(suite_path)
    rows: list[BenchmarkRow] = []
    for task_entry in suite.tasks:
        task = load_task(task_entry.task_path)
        for agent in suite.agents:
            restore_repo(task.repo_path, task_entry.repo_commit)
            run_path = create_run_artifact(
                task_entry.task_path,
                agent=agent,
                runs_dir=runs_dir,
                execute_agent=execute_agent,
                model=suite.model,
                max_steps=suite.budgets.max_steps,
                recursion_limit=suite.budgets.recursion_limit,
            )
            eval_path = create_evaluation_artifact(run_path, evals_dir)
            rows.append(
                build_benchmark_row(
                    suite=suite,
                    task_entry=task_entry,
                    run=load_run(run_path),
                    evaluation=load_evaluation(eval_path),
                    task_path=task_entry.task_path,
                )
            )
            restore_repo(task.repo_path, task_entry.repo_commit)

    generated_at = datetime.now(timezone.utc)
    report_id = f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}-{suite.suite_id}"
    report = BenchmarkReport(
        report_id=report_id,
        suite_id=suite.suite_id,
        harness_ref=suite.harness_ref,
        generated_at=generated_at,
        model=suite.model,
        budgets=suite.budgets,
        rows=rows,
    )
    output_path = reports_dir / f"{report_id}.json"
    write_artifact(output_path, report)
    write_csv_report(reports_dir / f"{report_id}.csv", rows)
    write_markdown_report(reports_dir / f"{report_id}.md", report)
    return output_path


def restore_repo(repo_path: Path, commit: str) -> None:
    if not commit.strip():
        raise ValueError("benchmark task repo_commit cannot be empty")
    for args in (["reset", "--hard", commit], ["clean", "-fd"]):
        result = subprocess.run(["git", *args], cwd=repo_path, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"failed to restore {repo_path} to {commit}: {detail}")


def build_benchmark_row(
    suite: BenchmarkSuite,
    task_entry: BenchmarkTask,
    run: RunArtifact,
    evaluation: EvaluationResult,
    task_path: Path,
) -> BenchmarkRow:
    diagnostics = collect_run_diagnostics(run)
    patch = run.patch
    test_command = evaluation.test_command
    semantic_command = evaluation.semantic_command
    semantic_status = command_status(semantic_command)
    patch_warnings = evaluation.patch_quality.warnings if evaluation.patch_quality else []
    behaviorally_wrong_pass = evaluation.status == "failed" and bool(semantic_command and semantic_command.exit_code != 0)
    return BenchmarkRow(
        suite_id=suite.suite_id,
        harness_ref=suite.harness_ref,
        task_id=run.task.task_id,
        task_path=task_path.as_posix(),
        repo_path=run.task.repo_path.as_posix(),
        repo_commit=task_entry.repo_commit,
        source_issue=task_entry.source_issue,
        source_base_commit=task_entry.source_base_commit,
        difficulty=task_entry.difficulty,
        domain=task_entry.domain,
        agent=run.agent,
        run_id=run.run_id,
        eval_id=evaluation.eval_id,
        run_status=run.status,
        eval_status=evaluation.status,
        semantic_status=semantic_status,
        quality_status=evaluation.quality_status,
        clean_pass=evaluation.clean_pass,
        test_exit_code=test_command.exit_code if test_command else None,
        semantic_exit_code=semantic_command.exit_code if semantic_command else None,
        model_calls=diagnostics.model_calls,
        tool_calls=diagnostics.tool_calls,
        invalid_responses=diagnostics.invalid_responses,
        tool_errors=diagnostics.tool_errors,
        repeated_tool_calls=diagnostics.repeated_tool_calls,
        repeated_tool_errors=diagnostics.repeated_tool_errors,
        context_stall_tool_calls=diagnostics.context_stall_tool_calls,
        edit_attempts=diagnostics.edit_attempts,
        no_op_edits=diagnostics.no_op_edits,
        repeated_edit_attempts=diagnostics.repeated_edit_attempts,
        validations_after_edit=diagnostics.validations_after_edit,
        files_read=diagnostics.files_read,
        commands_run=diagnostics.commands_run,
        changed_files=diagnostics.changed_files,
        lines_added=patch.lines_added if patch else 0,
        lines_removed=patch.lines_removed if patch else 0,
        run_duration_seconds=diagnostics.run_duration_seconds,
        test_duration_seconds=test_command.duration_seconds if test_command else None,
        semantic_duration_seconds=semantic_command.duration_seconds if semantic_command else None,
        patch_quality_warnings=patch_warnings,
        behaviorally_wrong_pass=behaviorally_wrong_pass,
    )


def command_status(command: CommandResult | None) -> str:
    if command is None:
        return "not_evaluated"
    if command.timed_out:
        return "failed"
    return "passed" if command.exit_code == 0 else "failed"


def write_csv_report(path: Path, rows: list[BenchmarkRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(BenchmarkRow.model_fields))
        writer.writeheader()
        for row in rows:
            payload = row.model_dump(mode="json")
            payload["patch_quality_warnings"] = " | ".join(row.patch_quality_warnings)
            writer.writerow(payload)


def write_markdown_report(path: Path, report: BenchmarkReport) -> None:
    lines = [
        f"# RepoScale {report.suite_id} Report",
        "",
        f"- Harness ref: `{report.harness_ref}`",
        f"- Model: `{report.model.provider}/{report.model.model}`",
        f"- Max steps: `{report.budgets.max_steps}`",
        f"- Recursion limit: `{report.budgets.recursion_limit}`",
        "",
        "## Summary",
        "",
        render_aggregate_table(report.rows),
        "",
        "## Results",
        "",
        render_results_table(report.rows),
        "",
        "## Failure Cases",
        "",
        render_failure_cases(report.rows),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def render_aggregate_table(rows: list[BenchmarkRow]) -> str:
    headers = ["agent", "runs", "pass_rate", "semantic_pass_rate", "clean_pass_rate", "avg_tools", "avg_model"]
    table = [headers]
    for agent in sorted({row.agent for row in rows}):
        agent_rows = [row for row in rows if row.agent == agent]
        table.append(
            [
                agent,
                str(len(agent_rows)),
                format_rate(count(agent_rows, lambda row: row.eval_status == "passed"), len(agent_rows)),
                format_rate(count(agent_rows, lambda row: row.semantic_status == "passed"), len(agent_rows)),
                format_rate(count(agent_rows, lambda row: row.clean_pass), len(agent_rows)),
                format_average(row.tool_calls for row in agent_rows),
                format_average(row.model_calls for row in agent_rows),
            ]
        )
    return render_table(table)


def render_results_table(rows: list[BenchmarkRow]) -> str:
    table = [
        [
            "task",
            "agent",
            "eval",
            "semantic",
            "quality",
            "clean",
            "model",
            "tools",
            "tool_err",
            "edits",
            "files",
            "+",
            "-",
        ]
    ]
    for row in rows:
        table.append(
            [
                row.task_id,
                row.agent,
                row.eval_status,
                row.semantic_status,
                row.quality_status,
                str(row.clean_pass),
                str(row.model_calls),
                str(row.tool_calls),
                str(row.tool_errors),
                str(row.edit_attempts),
                str(row.changed_files),
                str(row.lines_added),
                str(row.lines_removed),
            ]
        )
    return render_table(table)


def render_failure_cases(rows: list[BenchmarkRow]) -> str:
    failures = [
        row
        for row in rows
        if row.eval_status != "passed" or row.quality_status != "clean" or row.behaviorally_wrong_pass
    ][:8]
    if not failures:
        return "No failed or warning cases."
    parts: list[str] = []
    for row in failures:
        parts.extend(
            [
                f"### `{row.task_id}` / `{row.agent}`",
                "",
                f"- Eval: `{row.eval_status}`",
                f"- Semantic: `{row.semantic_status}`",
                f"- Quality: `{row.quality_status}`",
                f"- Clean pass: `{row.clean_pass}`",
                f"- Warnings: {', '.join(row.patch_quality_warnings) if row.patch_quality_warnings else 'none'}",
                "",
            ]
        )
    return "\n".join(parts)


def render_table(rows: list[list[str]]) -> str:
    header = rows[0]
    separator = ["---"] * len(header)
    return "\n".join("| " + " | ".join(row) + " |" for row in [header, separator, *rows[1:]])


def count(rows: list[BenchmarkRow], predicate) -> int:
    return sum(1 for row in rows if predicate(row))


def format_rate(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def format_average(values) -> str:
    values = list(values)
    if not values:
        return "0.0"
    return f"{sum(values) / len(values):.1f}"
