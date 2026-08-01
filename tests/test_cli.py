from __future__ import annotations

import json
import subprocess
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
    assert artifact["patch"]["is_git_repo"] is False
    assert artifact["trace"][0]["event_type"] == "run_created"


def test_run_rejects_unknown_agent(tmp_path: Path) -> None:
    task_path = write_task(tmp_path, test_command=None)

    result = runner.invoke(app, ["run", "--agent", "unknown", "--task", str(task_path)])

    assert result.exit_code != 0
    assert "agent must be one of: baseline, engineered" in result.output


def test_run_rejects_invalid_task_yaml(tmp_path: Path) -> None:
    task_path = tmp_path / "bad-task.yaml"
    task_path.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    result = runner.invoke(app, ["run", "--agent", "baseline", "--task", str(task_path)])

    assert result.exit_code != 0
    assert "task YAML must contain a mapping/object at the top level" in result.output


def test_run_rejects_missing_repo_path(tmp_path: Path) -> None:
    task_path = write_task(tmp_path, test_command=None, repo_path=tmp_path / "missing")

    result = runner.invoke(app, ["run", "--agent", "baseline", "--task", str(task_path)])

    assert result.exit_code != 0
    assert "task repo_path must be an existing directory" in result.output


def test_run_execute_agent_requires_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    task_path = write_task(tmp_path, test_command=None)

    result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--execute-agent"],
        catch_exceptions=False,
    )

    assert result.exit_code != 0
    assert "MISTRAL_API_KEY is not set" in result.output


def test_run_captures_git_patch_snapshot(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    tracked_file = repo_path / "example.py"
    tracked_file.write_text("value = 1\n", encoding="utf-8")
    run_git(repo_path, ["init"])
    run_git(repo_path, ["add", "example.py"])
    run_git(repo_path, ["-c", "user.name=RepoScale", "-c", "user.email=reposcale@example.com", "commit", "-m", "init"])
    tracked_file.write_text("value = 2\n", encoding="utf-8")

    task_path = write_task(tmp_path, test_command=None, repo_path=repo_path)
    runs_dir = tmp_path / "runs"

    result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )

    assert result.exit_code == 0
    artifact = json.loads(next(runs_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert artifact["patch"]["is_git_repo"] is True
    assert artifact["patch"]["changed_files"] == ["example.py"]
    assert "+value = 2" in artifact["patch"]["diff"]
    assert artifact["patch"]["lines_added"] == 1
    assert artifact["patch"]["lines_removed"] == 1


def test_run_captures_untracked_files(tmp_path: Path) -> None:
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    run_git(repo_path, ["init"])
    (repo_path / "new_file.py").write_text("value = 1\n", encoding="utf-8")

    task_path = write_task(tmp_path, test_command=None, repo_path=repo_path)
    runs_dir = tmp_path / "runs"

    result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )

    assert result.exit_code == 0
    artifact = json.loads(next(runs_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert artifact["patch"]["untracked_files"] == ["new_file.py"]


def test_run_scopes_patch_snapshot_to_task_repo_path(tmp_path: Path) -> None:
    git_root = tmp_path / "workspace"
    task_repo = git_root / "benchmarks" / "task_repo"
    task_repo.mkdir(parents=True)
    outside_file = git_root / "outside.py"
    inside_file = task_repo / "inside.py"
    outside_file.write_text("value = 1\n", encoding="utf-8")
    inside_file.write_text("value = 1\n", encoding="utf-8")
    run_git(git_root, ["init"])
    run_git(git_root, ["add", "."])
    run_git(git_root, ["-c", "user.name=RepoScale", "-c", "user.email=reposcale@example.com", "commit", "-m", "init"])
    outside_file.write_text("value = 2\n", encoding="utf-8")
    inside_file.write_text("value = 3\n", encoding="utf-8")

    task_path = write_task(tmp_path, test_command=None, repo_path=task_repo)
    runs_dir = tmp_path / "runs"

    result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )

    assert result.exit_code == 0
    artifact = json.loads(next(runs_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert artifact["patch"]["changed_files"] == ["inside.py"]
    assert "+value = 3" in artifact["patch"]["diff"]
    assert "outside.py" not in artifact["patch"]["diff"]


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


def test_eval_records_not_evaluated_without_test_command(tmp_path: Path) -> None:
    task_path = write_task(tmp_path, test_command=None)
    runs_dir = tmp_path / "runs"
    evals_dir = tmp_path / "evals"

    run_result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0

    eval_result = runner.invoke(
        app,
        ["eval", "--run", str(next(runs_dir.glob("*.json"))), "--evals-dir", str(evals_dir)],
    )

    assert eval_result.exit_code == 0
    eval_artifact = json.loads(next(evals_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert eval_artifact["status"] == "not_evaluated"
    assert eval_artifact["test_command"] is None


def test_eval_records_failed_command(tmp_path: Path) -> None:
    task_path = write_task(
        tmp_path,
        test_command='python -c "raise AssertionError(\'bad value\')"',
    )
    runs_dir = tmp_path / "runs"
    evals_dir = tmp_path / "evals"

    run_result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0

    eval_result = runner.invoke(
        app,
        ["eval", "--run", str(next(runs_dir.glob("*.json"))), "--evals-dir", str(evals_dir)],
    )

    assert eval_result.exit_code == 0
    eval_artifact = json.loads(next(evals_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert eval_artifact["status"] == "failed"
    assert eval_artifact["test_command"]["exit_code"] == 1
    assert eval_artifact["test_command"]["timed_out"] is False
    assert eval_artifact["validation_evidence"]["exit_code"] == 1
    assert "AssertionError" in eval_artifact["validation_evidence"]["headline"]
    assert eval_artifact["patch_quality"]["warnings"] == []
    assert eval_artifact["quality_status"] == "clean"
    assert eval_artifact["clean_pass"] is False


def test_eval_records_timed_out_command(tmp_path: Path) -> None:
    task_path = write_task(
        tmp_path,
        test_command='python -c "import time; time.sleep(2)"',
        test_timeout_seconds=0.1,
    )
    runs_dir = tmp_path / "runs"
    evals_dir = tmp_path / "evals"

    run_result = runner.invoke(
        app,
        ["run", "--agent", "baseline", "--task", str(task_path), "--runs-dir", str(runs_dir)],
    )
    assert run_result.exit_code == 0

    eval_result = runner.invoke(
        app,
        ["eval", "--run", str(next(runs_dir.glob("*.json"))), "--evals-dir", str(evals_dir)],
    )

    assert eval_result.exit_code == 0
    eval_artifact = json.loads(next(evals_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert eval_artifact["status"] == "failed"
    assert eval_artifact["test_command"]["exit_code"] is None
    assert eval_artifact["test_command"]["timed_out"] is True
    assert eval_artifact["test_command"]["duration_seconds"] < 1.5


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


def test_compare_rejects_mismatched_tasks(tmp_path: Path) -> None:
    baseline_path = write_eval(tmp_path, "baseline-eval", "baseline-run", "failed", task_id="task-a")
    candidate_path = write_eval(tmp_path, "candidate-eval", "candidate-run", "passed", task_id="task-b")

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline_path), "--candidate", str(candidate_path)],
    )

    assert result.exit_code != 0
    assert "baseline and candidate evals must have the same task_id" in result.output


def test_compare_reports_none_when_both_fail(tmp_path: Path) -> None:
    baseline_path = write_eval(tmp_path, "baseline-eval", "baseline-run", "failed")
    candidate_path = write_eval(tmp_path, "candidate-eval", "candidate-run", "failed")
    reports_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline_path), "--candidate", str(candidate_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    report = json.loads(next(reports_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["winner"] == "none"


def test_compare_reports_tie_when_both_pass(tmp_path: Path) -> None:
    baseline_path = write_eval(tmp_path, "baseline-eval", "baseline-run", "passed")
    candidate_path = write_eval(tmp_path, "candidate-eval", "candidate-run", "passed")
    reports_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline_path), "--candidate", str(candidate_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    report = json.loads(next(reports_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["winner"] == "tie"


def test_compare_prefers_clean_pass_over_warning_pass(tmp_path: Path) -> None:
    baseline_path = write_eval(tmp_path, "baseline-eval", "baseline-run", "passed", quality_status="warning")
    candidate_path = write_eval(tmp_path, "candidate-eval", "candidate-run", "passed", quality_status="clean")
    reports_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline_path), "--candidate", str(candidate_path), "--reports-dir", str(reports_dir)],
    )

    assert result.exit_code == 0
    report = json.loads(next(reports_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert report["winner"] == "candidate"
    assert report["baseline"]["quality_status"] == "warning"
    assert report["baseline"]["clean_pass"] is False
    assert report["candidate"]["quality_status"] == "clean"
    assert report["candidate"]["clean_pass"] is True


def write_task(
    tmp_path: Path,
    test_command: str | None,
    repo_path: Path | None = None,
    test_timeout_seconds: float = 5,
) -> Path:
    command_line = "test_command: null" if test_command is None else f"test_command: {test_command}"
    task_repo_path = repo_path or tmp_path
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "task_id: cli-test",
                "title: CLI test",
                f"repo_path: {task_repo_path.as_posix()}",
                "problem_statement: Exercise the CLI.",
                command_line,
                f"test_timeout_seconds: {test_timeout_seconds}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return task_path


def run_git(cwd: Path, args: list[str]) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def write_eval(
    tmp_path: Path,
    eval_id: str,
    run_id: str,
    status: str,
    task_id: str = "compare-test",
    quality_status: str = "clean",
) -> Path:
    path = tmp_path / f"{eval_id}.json"
    path.write_text(
        json.dumps(
            {
                "eval_id": eval_id,
                "run_id": run_id,
                "task_id": task_id,
                "agent": "baseline" if "baseline" in eval_id else "engineered",
                "status": status,
                "quality_status": quality_status,
                "clean_pass": status == "passed" and quality_status == "clean",
                "evaluated_at": "2026-07-30T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    return path
