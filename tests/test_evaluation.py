from __future__ import annotations

import subprocess
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


def test_run_test_command_replays_stored_patch_from_base_ref(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "value.txt").write_text("broken\n", encoding="utf-8")
    subprocess.run(["git", "add", "value.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    base_ref = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    diff = (
        "diff --git a/value.txt b/value.txt\n"
        "index 257cc56..3acdd5e 100644\n"
        "--- a/value.txt\n"
        "+++ b/value.txt\n"
        "@@ -1 +1 @@\n"
        "-broken\n"
        "+fixed\n"
    )
    (repo / "value.txt").write_text("already changed after run\n", encoding="utf-8")
    run = make_run(
        repo,
        test_command=(
            "python -c \"import pathlib, sys; "
            "sys.exit(0 if pathlib.Path('value.txt').read_text() == 'fixed\\n' else 1)\""
        ),
        patch=PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            base_ref=base_ref,
            changed_files=["value.txt"],
            diff=diff,
        ),
    )

    result = run_test_command(run)

    assert result is not None
    assert result.exit_code == 0
    assert (repo / "value.txt").read_text(encoding="utf-8") == "already changed after run\n"


def test_create_evaluation_fails_when_semantic_check_fails(tmp_path: Path) -> None:
    from reposcale.artifacts import write_artifact
    from reposcale.evaluation import create_evaluation_artifact

    repo = tmp_path / "repo"
    repo.mkdir()
    patch = PatchSnapshot(repo_path=repo, is_git_repo=False)
    run = make_run(
        repo,
        test_command='python -c "raise SystemExit(0)"',
        patch=patch,
        semantic_check_command='python -c "raise SystemExit(1)"',
    )
    run_path = tmp_path / "run.json"
    write_artifact(run_path, run)

    eval_path = create_evaluation_artifact(run_path, tmp_path / "evals")
    payload = eval_path.read_text(encoding="utf-8")

    assert '"status": "failed"' in payload
    assert "Semantic check failed" in payload


def test_run_test_command_applies_validation_patch_in_isolated_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def value():\n    return 'broken'\n", encoding="utf-8")
    validation_patch = tmp_path / "validation.patch"
    validation_patch.write_text(
        "diff --git a/hidden_test.py b/hidden_test.py\n"
        "new file mode 100644\n"
        "index 0000000..4064997\n"
        "--- /dev/null\n"
        "+++ b/hidden_test.py\n"
        "@@ -0,0 +1,3 @@\n"
        "+from app import value\n"
        "+\n"
        "+assert value() == 'fixed'\n",
        encoding="utf-8",
    )
    run = make_run(
        repo,
        test_command="python hidden_test.py",
        patch=PatchSnapshot(
            repo_path=repo,
            is_git_repo=False,
            changed_files=["app.py"],
            diff=(
                "diff --git a/app.py b/app.py\n"
                "--- a/app.py\n"
                "+++ b/app.py\n"
                "@@ -1,2 +1,2 @@\n"
                " def value():\n"
                "-    return 'broken'\n"
                "+    return 'fixed'\n"
            ),
        ),
        validation_patch=validation_patch,
    )

    result = run_test_command(run)

    assert result is not None
    assert result.exit_code == 0
    assert not (repo / "hidden_test.py").exists()
    assert (repo / "app.py").read_text(encoding="utf-8") == "def value():\n    return 'broken'\n"


def make_run(
    repo_path: Path,
    test_command: str,
    patch: PatchSnapshot,
    semantic_check_command: str | None = None,
    validation_patch: Path | None = None,
) -> RunArtifact:
    now = datetime.now(timezone.utc)
    return RunArtifact(
        run_id="run-1",
        task=TaskSpec(
            task_id="task-1",
            title="Task",
            repo_path=repo_path,
            problem_statement="Fix it.",
            test_command=test_command,
            validation_patch=validation_patch,
            semantic_check_command=semantic_check_command,
        ),
        agent="engineered",
        status="completed",
        started_at=now,
        completed_at=now,
        patch=patch,
    )
