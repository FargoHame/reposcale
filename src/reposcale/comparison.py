from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcale.artifacts import load_evaluation, write_artifact
from reposcale.schemas import ComparisonReport, EvaluationResult, EvaluationSummary


def create_comparison_report(baseline_path: Path, candidate_path: Path, reports_dir: Path) -> Path:
    baseline_eval = load_evaluation(baseline_path)
    candidate_eval = load_evaluation(candidate_path)
    if baseline_eval.task_id != candidate_eval.task_id:
        raise ValueError("baseline and candidate evals must have the same task_id")

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

    output_path = reports_dir / f"{report_id}.json"
    write_artifact(output_path, report)
    return output_path


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
