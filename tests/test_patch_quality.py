from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcale.patch_quality import analyze_patch_quality, find_duplicate_added_lines, render_patch_quality
from reposcale.schemas import PatchSnapshot, RunArtifact, TaskSpec


def test_find_duplicate_added_imports_against_hunk_context() -> None:
    diff = """diff --git a/app.py b/app.py
@@ -1,3 +1,4 @@
+from pytest import fixture, mark
 from pytest import fixture, mark
 from app import build
"""

    assert find_duplicate_added_lines(diff, ("import ", "from ")) == ["from pytest import fixture, mark"]


def test_find_duplicate_added_decorators_against_hunk_context() -> None:
    diff = """diff --git a/test_app.py b/test_app.py
@@ -10,3 +10,5 @@
 @mark.describe("write")
+@mark.describe("write")
+@mark.time_machine("2020-01-01")
 @mark.time_machine("2020-01-01")
 class TestWrite:
"""

    assert find_duplicate_added_lines(diff, ("@",)) == [
        '@mark.describe("write")',
        '@mark.time_machine("2020-01-01")',
    ]


def test_analyze_patch_quality_flags_syntax_errors_and_generated_files(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    run = make_run(
        repo,
        PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            changed_files=["broken.py", "uv.lock"],
            untracked_files=[],
        ),
    )

    report = analyze_patch_quality(run)

    assert report is not None
    assert report.syntax_errors == ["broken.py:1: invalid syntax"]
    assert report.generated_files == ["uv.lock"]
    assert "python syntax error: broken.py:1: invalid syntax" in report.warnings
    assert "generated dependency file changed: uv.lock" in report.warnings
    assert "Patch quality warnings:" in render_patch_quality(report)


def make_run(repo_path: Path, patch: PatchSnapshot) -> RunArtifact:
    now = datetime.now(timezone.utc)
    return RunArtifact(
        run_id="run-1",
        task=TaskSpec(
            task_id="task-1",
            title="Task",
            repo_path=repo_path,
            problem_statement="Fix it.",
            test_command="pytest",
        ),
        agent="engineered",
        status="completed",
        started_at=now,
        completed_at=now,
        patch=patch,
    )
