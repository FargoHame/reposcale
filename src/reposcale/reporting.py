from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reposcale.artifacts import load_evaluation, load_run
from reposcale.diagnostics import collect_run_diagnostics
from reposcale.patch_quality import analyze_patch_quality, is_clean_pass, quality_status, render_patch_quality
from reposcale.schemas import EvaluationResult, RunArtifact, RunDiagnostics, TraceEvent
from reposcale.validation_evidence import render_validation_evidence, summarize_validation


@dataclass(frozen=True)
class ReportRow:
    run: RunArtifact
    evaluation: EvaluationResult | None


def render_report(
    runs_dir: Path = Path("runs"),
    evals_dir: Path = Path("evals"),
    details: bool = False,
    task_id: str | None = None,
    latest: bool = False,
) -> str:
    rows = load_report_rows(runs_dir, evals_dir, task_id)
    if latest:
        rows = latest_rows(rows)
    if not rows:
        return "No matching run artifacts found."

    parts = [render_summary_table(rows)]
    if details:
        parts.append(render_details(rows))
    return "\n\n".join(part for part in parts if part)


def load_report_rows(runs_dir: Path, evals_dir: Path, task_id: str | None = None) -> list[ReportRow]:
    evaluations = load_evaluations_by_run_id(evals_dir)
    rows: list[ReportRow] = []
    for run_path in sorted(runs_dir.glob("*.json")):
        run = load_run(run_path)
        if task_id is not None and run.task.task_id != task_id:
            continue
        rows.append(ReportRow(run=run, evaluation=evaluations.get(run.run_id)))
    return rows


def latest_rows(rows: list[ReportRow]) -> list[ReportRow]:
    latest_by_key: dict[tuple[str, str], ReportRow] = {}
    for row in rows:
        key = (row.run.task.task_id, row.run.agent)
        current = latest_by_key.get(key)
        if current is None or row.run.started_at > current.run.started_at:
            latest_by_key[key] = row
    return sorted(latest_by_key.values(), key=lambda row: (row.run.task.task_id, row.run.agent))


def load_evaluations_by_run_id(evals_dir: Path) -> dict[str, EvaluationResult]:
    evaluations: dict[str, EvaluationResult] = {}
    for eval_path in sorted(evals_dir.glob("*.json")):
        try:
            evaluation = load_evaluation(eval_path)
        except Exception:
            continue
        evaluations[evaluation.run_id] = evaluation
    return evaluations


def render_summary_table(rows: list[ReportRow]) -> str:
    headers = [
        "task",
        "agent",
        "run",
        "eval",
        "quality",
        "clean",
        "model",
        "tools",
        "invalid",
        "tool_err",
        "repeat",
        "rep_err",
        "ctx_stall",
        "edits",
        "noop",
        "edit_rep",
        "val_after",
        "reads",
        "cmds",
        "files",
        "+",
        "-",
        "run_s",
        "test_s",
    ]
    values = [headers]
    for row in rows:
        run = row.run
        evaluation = row.evaluation
        diagnostics = get_diagnostics(run)
        test_command = evaluation.test_command if evaluation else None
        evaluation_quality = get_quality_status(run, evaluation) if evaluation else "-"
        values.append(
            [
                run.task.task_id,
                run.agent,
                run.status,
                evaluation.status if evaluation else "missing",
                evaluation_quality,
                str(get_clean_pass(run, evaluation)) if evaluation else "-",
                str(diagnostics.model_calls),
                str(diagnostics.tool_calls),
                str(diagnostics.invalid_responses),
                str(diagnostics.tool_errors),
                str(diagnostics.repeated_tool_calls),
                str(diagnostics.repeated_tool_errors),
                str(diagnostics.context_stall_tool_calls),
                str(diagnostics.edit_attempts),
                str(diagnostics.no_op_edits),
                str(diagnostics.repeated_edit_attempts),
                str(diagnostics.validations_after_edit),
                str(diagnostics.files_read),
                str(diagnostics.commands_run),
                str(diagnostics.changed_files),
                str(diagnostics.lines_added),
                str(diagnostics.lines_removed),
                f"{diagnostics.run_duration_seconds:.2f}",
                f"{test_command.duration_seconds:.2f}" if test_command else "-",
            ]
        )

    widths = [max(len(row[index]) for row in values) for index in range(len(headers))]
    lines = [format_table_row(headers, widths), format_table_row(["-" * width for width in widths], widths)]
    lines.extend(format_table_row(row, widths) for row in values[1:])
    return "\n".join(lines)


def render_details(rows: list[ReportRow]) -> str:
    return "\n\n".join(render_row_details(row) for row in rows)


def render_row_details(row: ReportRow) -> str:
    run = row.run
    evaluation = row.evaluation
    patch = run.patch
    diagnostics = get_diagnostics(run)
    parts = [
        f"Task: {run.task.task_id}",
        f"Agent: {run.agent}",
        f"Run: {run.status}",
        f"Eval: {evaluation.status if evaluation else 'missing'}",
        "",
        "Diagnostics:",
        render_diagnostics(diagnostics),
        "",
        "Tool calls:",
        render_tool_calls(run.trace),
        "",
        "Changed files:",
        render_changed_files(patch.changed_files if patch else []),
        "",
        "Diff:",
        indent_text((patch.diff if patch else "") or "(no diff)", "  "),
    ]

    if evaluation and evaluation.test_command:
        parts.extend(
            [
                "",
                indent_text(render_validation_evidence(get_validation_evidence(evaluation)), "  "),
                "",
                indent_text(render_patch_quality(get_patch_quality(run, evaluation)), "  "),
                "",
                "Eval stdout tail:",
                indent_text(tail(evaluation.test_command.stdout), "  "),
            ]
        )
    if evaluation and evaluation.semantic_command:
        parts.extend(
            [
                "",
                "Semantic stdout tail:",
                indent_text(tail(evaluation.semantic_command.stdout), "  "),
                "",
                indent_text(render_validation_evidence(evaluation.semantic_evidence), "  "),
            ]
        )

    return "\n".join(parts)


def count_tool_calls(trace: list[TraceEvent]) -> int:
    return sum(1 for event in trace if event.event_type == "tool_call")


def get_diagnostics(run: RunArtifact) -> RunDiagnostics:
    return collect_run_diagnostics(run)


def get_validation_evidence(evaluation: EvaluationResult):
    return evaluation.validation_evidence or summarize_validation(evaluation.test_command)


def get_patch_quality(run: RunArtifact, evaluation: EvaluationResult):
    return evaluation.patch_quality or analyze_patch_quality(run)


def get_quality_status(run: RunArtifact, evaluation: EvaluationResult) -> str:
    if evaluation.patch_quality is not None:
        return evaluation.quality_status
    return quality_status(analyze_patch_quality(run))


def get_clean_pass(run: RunArtifact, evaluation: EvaluationResult) -> bool:
    if evaluation.patch_quality is not None:
        return is_clean_pass(evaluation)
    return evaluation.status == "passed" and quality_status(analyze_patch_quality(run)) == "clean"


def render_diagnostics(diagnostics: RunDiagnostics) -> str:
    values = {
        "model_calls": diagnostics.model_calls,
        "tool_calls": diagnostics.tool_calls,
        "invalid_responses": diagnostics.invalid_responses,
        "tool_errors": diagnostics.tool_errors,
        "model_errors": diagnostics.model_errors,
        "repeated_tool_calls": diagnostics.repeated_tool_calls,
        "repeated_tool_errors": diagnostics.repeated_tool_errors,
        "context_stall_tool_calls": diagnostics.context_stall_tool_calls,
        "edit_attempts": diagnostics.edit_attempts,
        "no_op_edits": diagnostics.no_op_edits,
        "repeated_edit_attempts": diagnostics.repeated_edit_attempts,
        "validations_after_edit": diagnostics.validations_after_edit,
        "files_read": diagnostics.files_read,
        "commands_run": diagnostics.commands_run,
        "max_steps_reached": diagnostics.max_steps_reached,
        "run_duration_seconds": f"{diagnostics.run_duration_seconds:.2f}",
        "artifact_saved": diagnostics.artifact_saved,
    }
    return "\n".join(f"  {key}: {value}" for key, value in values.items())


def render_tool_calls(trace: list[TraceEvent]) -> str:
    tool_calls = [event for event in trace if event.event_type == "tool_call"]
    if not tool_calls:
        return "  (none)"

    lines = []
    for index, event in enumerate(tool_calls, start=1):
        lines.append(f"  {index}. {event.tool_name} {event.tool_input or {}}")
    return "\n".join(lines)


def render_changed_files(changed_files: list[str]) -> str:
    if not changed_files:
        return "  (none)"
    return "\n".join(f"  {path}" for path in changed_files)


def format_table_row(values: list[str], widths: list[int]) -> str:
    return "  ".join(value.ljust(width) for value, width in zip(values, widths, strict=True))


def indent_text(text: str, prefix: str) -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def tail(text: str, max_lines: int = 12) -> str:
    lines = text.splitlines()
    return "\n".join(lines[-max_lines:])
