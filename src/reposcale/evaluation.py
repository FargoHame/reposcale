from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcale.artifacts import load_run, write_artifact
from reposcale.commands import run_command
from reposcale.patch_quality import analyze_patch_quality, quality_status
from reposcale.schemas import CommandResult, EvaluationResult, TaskSpec
from reposcale.validation_evidence import summarize_validation


def create_evaluation_artifact(run_path: Path, evals_dir: Path) -> Path:
    run_artifact = load_run(run_path)
    evaluated_at = datetime.now(timezone.utc)
    timestamp = evaluated_at.strftime("%Y%m%dT%H%M%SZ")
    eval_id = f"{timestamp}-{run_artifact.run_id}"
    command_result = run_test_command(run_artifact.task)
    validation_evidence = summarize_validation(command_result)
    patch_quality = analyze_patch_quality(run_artifact)
    patch_quality_status = quality_status(patch_quality)
    status, notes = evaluate_command_result(command_result)

    result = EvaluationResult(
        eval_id=eval_id,
        run_id=run_artifact.run_id,
        task_id=run_artifact.task.task_id,
        agent=run_artifact.agent,
        status=status,
        evaluated_at=evaluated_at,
        test_command=command_result,
        validation_evidence=validation_evidence,
        patch_quality=patch_quality,
        quality_status=patch_quality_status,
        clean_pass=status == "passed" and patch_quality_status == "clean",
        notes=notes,
    )

    output_path = evals_dir / f"{eval_id}.json"
    write_artifact(output_path, result)
    return output_path


def run_test_command(task: TaskSpec) -> CommandResult | None:
    if task.test_command is None:
        return None
    return run_command(task.test_command, task.repo_path, task.test_timeout_seconds)


def evaluate_command_result(command_result: CommandResult | None) -> tuple[str, str]:
    if command_result is None:
        return "not_evaluated", "Task has no test_command, so no evaluation command was run."
    if command_result.timed_out:
        return "failed", "Test command timed out."
    if command_result.exit_code == 0:
        return "passed", "Test command exited successfully."
    return "failed", "Test command exited with a non-zero status."
