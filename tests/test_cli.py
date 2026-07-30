from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from reposcale.cli import app


runner = CliRunner()


def test_run_writes_artifact(tmp_path: Path) -> None:
    task_path = write_task(tmp_path, test_command=None)
    runs_dir = tmp_path / "runs"

    result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )

    assert result.exit_code == 0
    artifacts = list(runs_dir.glob("*.json"))
    assert len(artifacts) == 1

    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["task"]["task_id"] == "cli-test"
    assert artifact["agent"] == "baseline"
    assert artifact["status"] == "not_implemented"


def test_eval_runs_test_command_and_records_pass(tmp_path: Path) -> None:
    task_path = write_task(tmp_path, test_command='python -c "print(123)"')
    runs_dir = tmp_path / "runs"
    evals_dir = tmp_path / "evals"

    run_result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0

    run_artifact = next(runs_dir.glob("*.json"))
    eval_result = runner.invoke(app, ["eval", "--run", str(run_artifact), "--evals-dir", str(evals_dir)])

    assert eval_result.exit_code == 0
    eval_artifact = json.loads(next(evals_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert eval_artifact["status"] == "passed"
    assert eval_artifact["task_id"] == "cli-test"
    assert eval_artifact["agent"] == "baseline"
    assert eval_artifact["test_command"]["exit_code"] == 0
    assert eval_artifact["test_command"]["stdout"] == "123\n"


def test_compare_prefers_passing_candidate(tmp_path: Path) -> None:
    baseline_path = write_eval(tmp_path, "baseline-eval", "baseline-run", "failed")
    candidate_path = write_eval(tmp_path, "candidate-eval", "candidate-run", "passed")
    reports_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "compare",
            "--baseline",
            str(baseline_path),
            "--candidate",
            str(candidate_path),
            "--reports-dir",
            str(reports_dir),
        ],
    )

    assert result.exit_code == 0
    report = json.loads(next(reports_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["winner"] == "candidate"
    assert report["baseline"]["status"] == "failed"
    assert report["candidate"]["status"] == "passed"


def write_task(tmp_path: Path, test_command: str | None) -> Path:
    command_line = "test_command: null" if test_command is None else f"test_command: {test_command}"
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "task_id: cli-test",
                "title: CLI test",
                f"repo_path: {tmp_path.as_posix()}",
                "problem_statement: Exercise the CLI.",
                command_line,
                "test_timeout_seconds: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return task_path


def write_eval(tmp_path: Path, eval_id: str, run_id: str, status: str) -> Path:
    path = tmp_path / f"{eval_id}.json"
    path.write_text(
        json.dumps(
            {
                "eval_id": eval_id,
                "run_id": run_id,
                "task_id": "compare-test",
                "agent": "baseline" if "baseline" in eval_id else "engineered",
                "status": status,
                "evaluated_at": "2026-07-30T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return path
