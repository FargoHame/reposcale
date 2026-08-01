from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcale.evaluation import run_test_command
from reposcale.schemas import PatchSnapshot, RunArtifact, TaskSpec


def test_run_test_command_validates_stored_patch_state(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("broken\n", encoding="utf-8")
    run = make_run(
        repo,
        test_command=(
            "python -c \"import pathlib, sys; "
            "sys.exit(0 if pathlib.Path('value.txt').read_text() == 'fixed\\n' else 1)\""
        ),
        patch=PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            changed_files=["value.txt"],
            diff=(
                "diff --git a/value.txt b/value.txt\n"
                "--- a/value.txt\n"
                "+++ b/value.txt\n"
                "@@ -1 +1 @@\n"
                "-broken\n"
                "+fixed\n"
            ),
        ),
    )

    result = run_test_command(run)

    assert result is not None
    assert result.exit_code == 0
    assert (repo / "value.txt").read_text(encoding="utf-8") == "broken\n"


def test_run_test_command_fails_when_stored_patch_cannot_apply(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "value.txt").write_text("different\n", encoding="utf-8")
    run = make_run(
        repo,
        test_command="python -c \"raise SystemExit(0)\"",
        patch=PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            changed_files=["value.txt"],
            diff=(
                "diff --git a/value.txt b/value.txt\n"
                "--- a/value.txt\n"
                "+++ b/value.txt\n"
                "@@ -1 +1 @@\n"
                "-broken\n"
                "+fixed\n"
            ),
        ),
    )

    result = run_test_command(run)

    assert result is not None
    assert result.exit_code == 1
    assert "stored patch did not apply cleanly for validation" in result.stdout


def make_run(repo_path: Path, test_command: str, patch: PatchSnapshot) -> RunArtifact:
    now = datetime.now(timezone.utc)
    return RunArtifact(
        run_id="run-1",
        task=TaskSpec(
            task_id="task-1",
            title="Task",
            repo_path=repo_path,
            problem_statement="Fix it.",
            test_command=test_command,
        ),
        agent="engineered",
        status="completed",
        started_at=now,
        completed_at=now,
        patch=patch,
    )
