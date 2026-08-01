from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcale.patch_quality import analyze_patch_quality, find_duplicate_added_lines, quality_status, render_patch_quality
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


def test_find_duplicate_added_assertions_against_hunk_context() -> None:
    diff = """diff --git a/test_app.py b/test_app.py
@@ -10,3 +10,4 @@
 def test_elapsed_time():
     assert str(session.elapsed_time()) == "0:01:41"
+    assert str(session.elapsed_time()) == "0:01:41"
"""

    assert find_duplicate_added_lines(diff, ("assert ",)) == [
        'assert str(session.elapsed_time()) == "0:01:41"'
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
    assert quality_status(report) == "risky"


def test_analyze_patch_quality_flags_toml_syntax_errors(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text("[project]\ndependencies = [\ntime-machine>=2.14.0,<3.0.0\n]\n", encoding="utf-8")
    run = make_run(
        repo,
        PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            changed_files=["pyproject.toml"],
        ),
    )

    report = analyze_patch_quality(run)

    assert report is not None
    assert len(report.toml_errors) == 1
    assert report.toml_errors[0].startswith("pyproject.toml:")
    assert "toml syntax error: pyproject.toml:" in report.warnings[0]
    assert quality_status(report) == "risky"


def test_analyze_patch_quality_uses_stored_diff_when_checkout_is_restored(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        '[project]\ndependencies = [\n    "pytest-freezegun==0.4.2",\n]\n',
        encoding="utf-8",
    )
    run = make_run(
        repo,
        PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            changed_files=["pyproject.toml"],
            diff=(
                "diff --git a/pyproject.toml b/pyproject.toml\n"
                "--- a/pyproject.toml\n"
                "+++ b/pyproject.toml\n"
                "@@ -1,4 +1,4 @@\n"
                " [project]\n"
                " dependencies = [\n"
                '-    "pytest-freezegun==0.4.2",\n'
                "+    time-machine>=2.14.0,<3.0.0\n"
                " ]\n"
            ),
        ),
    )

    report = analyze_patch_quality(run)

    assert report is not None
    assert len(report.toml_errors) == 1
    assert "pyproject.toml" in report.toml_errors[0]
    assert quality_status(report) == "risky"


def test_analyze_patch_quality_flags_repeated_added_lines(tmp_path: Path) -> None:
    run = make_run(
        tmp_path,
        PatchSnapshot(
            repo_path=tmp_path,
            is_git_repo=True,
            changed_files=["example.py"],
            diff=(
                "diff --git a/example.py b/example.py\n"
                "@@ -1,1 +1,4 @@\n"
                "+length += 1\n"
                "+length += 1\n"
                "+length += 1\n"
            ),
        ),
    )
    (tmp_path / "example.py").write_text("length += 1\nlength += 1\nlength += 1\n", encoding="utf-8")

    report = analyze_patch_quality(run)

    assert report is not None
    assert report.repeated_added_lines == ["length += 1"]
    assert "repeated added line: length += 1" in report.warnings


def test_analyze_patch_quality_replays_stored_patch_from_base_ref(tmp_path: Path) -> None:
    import subprocess

    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "test_app.py").write_text(
        "def test_elapsed_time():\n"
        '    assert str(session.elapsed_time()) == "0:01:41"\n',
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "test_app.py"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=repo, check=True, capture_output=True)
    base_ref = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    (repo / "test_app.py").write_text("def test_dirty_checkout():\n    assert True\n", encoding="utf-8")
    run = make_run(
        repo,
        PatchSnapshot(
            repo_path=repo,
            is_git_repo=True,
            base_ref=base_ref,
            changed_files=["test_app.py"],
            diff=(
                "diff --git a/test_app.py b/test_app.py\n"
                "index 357ec0d..f4968ee 100644\n"
                "--- a/test_app.py\n"
                "+++ b/test_app.py\n"
                "@@ -1,2 +1,3 @@\n"
                " def test_elapsed_time():\n"
                '     assert str(session.elapsed_time()) == "0:01:41"\n'
                '+    assert str(session.elapsed_time()) == "0:01:41"\n'
            ),
        ),
    )

    report = analyze_patch_quality(run)

    assert report is not None
    assert report.duplicate_assertions == [
        'assert str(session.elapsed_time()) == "0:01:41"'
    ]


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
