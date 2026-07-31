from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reposcale.artifacts import load_evaluation, load_run
from reposcale.schemas import EvaluationResult, RunArtifact, TraceEvent


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
    headers = ["task", "agent", "run", "eval", "tools", "files", "+", "-", "test_s"]
    values = [headers]
    for row in rows:
        run = row.run
        evaluation = row.evaluation
        patch = run.patch
        test_command = evaluation.test_command if evaluation else None
        values.append(
            [
                run.task.task_id,
                run.agent,
                run.status,
                evaluation.status if evaluation else "missing",
                str(count_tool_calls(run.trace)),
                str(len(patch.changed_files) if patch else 0),
                str(patch.lines_added if patch else 0),
                str(patch.lines_removed if patch else 0),
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
    parts = [
        f"Task: {run.task.task_id}",
        f"Agent: {run.agent}",
        f"Run: {run.status}",
        f"Eval: {evaluation.status if evaluation else 'missing'}",
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
        parts.extend(["", "Eval stdout tail:", indent_text(tail(evaluation.test_command.stdout), "  ")])

    return "\n".join(parts)


def count_tool_calls(trace: list[TraceEvent]) -> int:
    return sum(1 for event in trace if event.event_type == "tool_call")


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
