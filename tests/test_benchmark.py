from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from reposcale.cli import app


runner = CliRunner()


def test_benchmark_command_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    run_git(repo, ["init"])
    run_git(repo, ["add", "app.py"])
    run_git(repo, ["-c", "user.name=RepoScale", "-c", "user.email=reposcale@example.com", "commit", "-m", "init"])
    commit = git_stdout(repo, ["rev-parse", "--short", "HEAD"])
    (repo / "app.py").write_text("dirty = True\n", encoding="utf-8")

    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "task_id: bench-task",
                "title: Benchmark task",
                f"repo_path: {repo.as_posix()}",
                "problem_statement: Exercise benchmark mode.",
                "test_command: python -c \"print('ok')\"",
                "test_timeout_seconds: 5",
                "",
            ]
        ),
        encoding="utf-8",
    )
    suite_path = tmp_path / "suite.yaml"
    suite_path.write_text(
        "\n".join(
            [
                "suite_id: test-suite",
                "harness_ref: test-freeze",
                "agents: [baseline, engineered]",
                "model:",
                "  provider: mistral",
                "  model: devstral-latest",
                "  temperature: 0",
                "  max_tokens: 128",
                "budgets:",
                "  max_steps: 2",
                "  recursion_limit: 20",
                "tasks:",
                f"  - task_path: {task_path.as_posix()}",
                f"    repo_commit: {commit}",
                "    source_issue: local-test",
                "    difficulty: easy",
                "    domain: harness",
                "",
            ]
        ),
        encoding="utf-8",
    )
    reports_dir = tmp_path / "reports"

    result = runner.invoke(
        app,
        [
            "benchmark",
            "--suite",
            str(suite_path),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--evals-dir",
            str(tmp_path / "evals"),
            "--reports-dir",
            str(reports_dir),
        ],
    )

    assert result.exit_code == 0
    report_path = next(reports_dir.glob("*.json"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["suite_id"] == "test-suite"
    assert len(report["rows"]) == 2
    assert {row["agent"] for row in report["rows"]} == {"baseline", "engineered"}
    assert (reports_dir / f"{report_path.stem}.md").exists()
    csv_path = reports_dir / f"{report_path.stem}.csv"
    with csv_path.open("r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == 2
    assert (repo / "app.py").read_text(encoding="utf-8") == "value = 1\n"


def run_git(cwd: Path, args: list[str]) -> None:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def git_stdout(cwd: Path, args: list[str]) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()
