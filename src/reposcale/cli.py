from __future__ import annotations

import json
import os
import signal
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Annotated

import typer
import yaml

from reposcale.schemas import (
    CommandResult,
    ComparisonReport,
    EvaluationResult,
    EvaluationSummary,
    RunArtifact,
    TaskSpec,
    TraceEvent,
)

app = typer.Typer(help="RepoScale coding-agent evaluation harness.")


@app.callback()
def main() -> None:
    """RepoScale command group."""


@app.command()
def run(
    agent: Annotated[str, typer.Option(help="Agent harness to run.")] = "baseline",
    task: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Path to a task YAML file.")] = Path(
        "tasks/example.yaml"
    ),
    runs_dir: Annotated[Path, typer.Option(help="Directory where run artifacts are written.")] = Path("runs"),
) -> None:
    """Create a run artifact for a task.

    Agent execution is intentionally mocked in the first MVP slice.
    """
    if agent not in {"baseline", "engineered"}:
        raise typer.BadParameter("agent must be one of: baseline, engineered")

    task_spec = load_task(task)
    started_at = datetime.now(timezone.utc)
    completed_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{task_spec.task_id}-{agent}"

    artifact = RunArtifact(
        run_id=run_id,
        task=task_spec,
        agent=agent,
        status="not_implemented",
        started_at=started_at,
        completed_at=completed_at,
        trace=[
            TraceEvent(
                event_type="run_created",
                message="Created placeholder run artifact; agent execution is not implemented yet.",
                timestamp=started_at,
            )
        ],
    )

    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / f"{run_id}.json"
    output_path.write_text(json.dumps(artifact.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote run artifact: {output_path}")


@app.command()
def eval(
    run: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Path to a run artifact JSON file.")],
    evals_dir: Annotated[Path, typer.Option(help="Directory where evaluation artifacts are written.")] = Path("evals"),
) -> None:
    """Create an evaluation artifact for a run."""
    run_artifact = load_run(run)
    evaluated_at = datetime.now(timezone.utc)
    timestamp = evaluated_at.strftime("%Y%m%dT%H%M%SZ")
    eval_id = f"{timestamp}-{run_artifact.run_id}"
    command_result = run_test_command(run_artifact.task)

    if command_result is None:
        status = "not_evaluated"
        notes = "Task has no test_command, so no evaluation command was run."
    elif command_result.timed_out:
        status = "failed"
        notes = "Test command timed out."
    elif command_result.exit_code == 0:
        status = "passed"
        notes = "Test command exited successfully."
    else:
        status = "failed"
        notes = "Test command exited with a non-zero status."

    result = EvaluationResult(
        eval_id=eval_id,
        run_id=run_artifact.run_id,
        task_id=run_artifact.task.task_id,
        agent=run_artifact.agent,
        status=status,
        evaluated_at=evaluated_at,
        test_command=command_result,
        notes=notes,
    )

    evals_dir.mkdir(parents=True, exist_ok=True)
    output_path = evals_dir / f"{eval_id}.json"
    output_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote evaluation artifact: {output_path}")


@app.command()
def compare(
    baseline: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Baseline eval artifact JSON.")],
    candidate: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Candidate eval artifact JSON.")],
    reports_dir: Annotated[Path, typer.Option(help="Directory where comparison reports are written.")] = Path(
        "reports"
    ),
) -> None:
    """Compare two evaluation artifacts."""
    baseline_eval = load_evaluation(baseline)
    candidate_eval = load_evaluation(candidate)
    if baseline_eval.task_id != candidate_eval.task_id:
        raise typer.BadParameter("baseline and candidate evals must have the same task_id")

    compared_at = datetime.now(timezone.utc)
    timestamp = compared_at.strftime("%Y%m%dT%H%M%SZ")
    report_id = f"{timestamp}-{baseline_eval.run_id}-vs-{candidate_eval.run_id}"
    winner, notes = choose_winner(baseline_eval, candidate_eval)

    report = ComparisonReport(
        report_id=report_id,
        baseline=summarize_evaluation(baseline_eval),
        candidate=summarize_evaluation(candidate_eval),
        winner=winner,
        compared_at=compared_at,
        notes=notes,
    )

    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / f"{report_id}.json"
    output_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote comparison report: {output_path}")


def load_task(path: Path) -> TaskSpec:
    with path.open("r", encoding="utf-8") as file:
        raw_task = yaml.safe_load(file)

    if not isinstance(raw_task, dict):
        raise typer.BadParameter("task YAML must contain a mapping/object at the top level")

    return TaskSpec.model_validate(raw_task)


def load_run(path: Path) -> RunArtifact:
    with path.open("r", encoding="utf-8") as file:
        raw_run = json.load(file)

    if not isinstance(raw_run, dict):
        raise typer.BadParameter("run artifact JSON must contain an object at the top level")

    return RunArtifact.model_validate(raw_run)


def load_evaluation(path: Path) -> EvaluationResult:
    with path.open("r", encoding="utf-8") as file:
        raw_evaluation = json.load(file)

    if not isinstance(raw_evaluation, dict):
        raise typer.BadParameter("evaluation artifact JSON must contain an object at the top level")

    return EvaluationResult.model_validate(raw_evaluation)


def run_test_command(task: TaskSpec) -> CommandResult | None:
    if task.test_command is None:
        return None

    cwd = task.repo_path.resolve()
    if not cwd.exists() or not cwd.is_dir():
        raise typer.BadParameter(f"task repo_path must be an existing directory: {task.repo_path}")

    started_at = datetime.now(timezone.utc)
    started_timer = perf_counter()
    process = subprocess.Popen(
        task.test_command,
        cwd=cwd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        start_new_session=os.name != "nt",
    )
    try:
        stdout, stderr = process.communicate(timeout=task.test_timeout_seconds)
    except subprocess.TimeoutExpired:
        stop_process_tree(process)
        stdout, stderr = process.communicate()
        completed_at = datetime.now(timezone.utc)
        duration_seconds = perf_counter() - started_timer
        return CommandResult(
            command=task.test_command,
            cwd=cwd,
            exit_code=None,
            timed_out=True,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            stdout=stdout,
            stderr=stderr,
        )
    else:
        completed_at = datetime.now(timezone.utc)
        duration_seconds = perf_counter() - started_timer
        return CommandResult(
            command=task.test_command,
            cwd=cwd,
            exit_code=process.returncode,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration_seconds,
            stdout=stdout,
            stderr=stderr,
        )


def stop_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            text=True,
        )
        return

    os.killpg(process.pid, signal.SIGTERM)


def summarize_evaluation(evaluation: EvaluationResult) -> EvaluationSummary:
    command = evaluation.test_command
    return EvaluationSummary(
        eval_id=evaluation.eval_id,
        run_id=evaluation.run_id,
        task_id=evaluation.task_id,
        agent=evaluation.agent,
        status=evaluation.status,
        duration_seconds=command.duration_seconds if command else None,
        exit_code=command.exit_code if command else None,
        timed_out=command.timed_out if command else None,
    )


def choose_winner(
    baseline: EvaluationResult,
    candidate: EvaluationResult,
) -> tuple[str, list[str]]:
    baseline_score = evaluation_score(baseline)
    candidate_score = evaluation_score(candidate)

    if baseline_score > candidate_score:
        return "baseline", ["Baseline has the better evaluation status."]
    if candidate_score > baseline_score:
        return "candidate", ["Candidate has the better evaluation status."]
    if baseline_score == 0:
        return "none", ["Neither evaluation passed."]
    return "tie", ["Both evaluations have the same status."]


def evaluation_score(evaluation: EvaluationResult) -> int:
    scores = {
        "failed": 0,
        "not_evaluated": 1,
        "passed": 2,
    }
    return scores[evaluation.status]
