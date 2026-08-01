from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from reposcale.artifacts import load_run, write_artifact
from reposcale.commands import run_command
from reposcale.patch_quality import analyze_patch_quality, quality_status
from reposcale.schemas import CommandResult, EvaluationResult, RunArtifact
from reposcale.validation_evidence import summarize_validation


class PatchApplyError(RuntimeError):
    pass


def create_evaluation_artifact(run_path: Path, evals_dir: Path) -> Path:
    run_artifact = load_run(run_path)
    evaluated_at = datetime.now(timezone.utc)
    timestamp = evaluated_at.strftime("%Y%m%dT%H%M%SZ")
    eval_id = f"{timestamp}-{run_artifact.run_id}"
    command_result = run_test_command(run_artifact)
    semantic_result = run_semantic_command(run_artifact)
    validation_evidence = summarize_validation(command_result)
    semantic_evidence = summarize_validation(semantic_result)
    patch_quality = analyze_patch_quality(run_artifact)
    patch_quality_status = quality_status(patch_quality)
    status, notes = evaluate_results(command_result, semantic_result)

    result = EvaluationResult(
        eval_id=eval_id,
        run_id=run_artifact.run_id,
        task_id=run_artifact.task.task_id,
        agent=run_artifact.agent,
        status=status,
        evaluated_at=evaluated_at,
        test_command=command_result,
        semantic_command=semantic_result,
        validation_evidence=validation_evidence,
        semantic_evidence=semantic_evidence,
        patch_quality=patch_quality,
        quality_status=patch_quality_status,
        clean_pass=status == "passed" and patch_quality_status == "clean",
        notes=notes,
    )

    output_path = evals_dir / f"{eval_id}.json"
    write_artifact(output_path, result)
    return output_path


def run_test_command(run: RunArtifact) -> CommandResult | None:
    task = run.task
    if task.test_command is None:
        return None
    return run_patched_command(run, task.test_command, task.test_timeout_seconds)


def run_semantic_command(run: RunArtifact) -> CommandResult | None:
    task = run.task
    if task.semantic_check_command is None:
        return None
    return run_patched_command(
        run,
        task.semantic_check_command,
        task.semantic_timeout_seconds or task.test_timeout_seconds,
    )


def run_patched_command(run: RunArtifact, command: str, timeout_seconds: float) -> CommandResult:
    try:
        with patched_validation_repo(run) as repo_path:
            return run_command(command, repo_path, timeout_seconds)
    except PatchApplyError as error:
        now = datetime.now(timezone.utc)
        return CommandResult(
            command=command,
            cwd=run.task.repo_path,
            exit_code=1,
            started_at=now,
            completed_at=now,
            duration_seconds=0.0,
            stdout=str(error),
            stderr="",
        )


@contextmanager
def patched_validation_repo(run: RunArtifact) -> Iterator[Path]:
    patch = run.patch
    if patch is None or not patch.diff.strip():
        yield run.task.repo_path
        return

    repo_path = run.task.repo_path
    if patch.is_git_repo and patch.base_ref:
        with patched_git_worktree(repo_path, patch.base_ref, patch.diff) as validation_path:
            yield validation_path
        return

    if patch_is_already_applied(repo_path, patch.diff):
        yield repo_path
        return

    temp_root = Path(tempfile.mkdtemp(prefix=".reposcale_eval_", dir=repo_path.parent))
    try:
        shutil.copytree(
            repo_path,
            temp_root,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", ".pytest_cache"),
        )
        result = subprocess.run(
            ["git", "apply"],
            cwd=temp_root,
            input=patch.diff,
            capture_output=True,
            text=True,
            env=git_apply_env(temp_root),
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise PatchApplyError(f"stored patch did not apply cleanly for validation: {detail}")
        yield temp_root
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


@contextmanager
def patched_git_worktree(repo_path: Path, base_ref: str, diff: str) -> Iterator[Path]:
    git_root_result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    if git_root_result.returncode != 0:
        raise PatchApplyError("stored patch requires git validation, but repo_path is not in a git repository")

    git_root = Path(git_root_result.stdout.strip()).resolve()
    temp_root = Path(tempfile.mkdtemp(prefix=".reposcale_eval_", dir=git_root.parent))
    shutil.rmtree(temp_root, ignore_errors=True)
    try:
        add_result = subprocess.run(
            ["git", "worktree", "add", "--detach", "--quiet", str(temp_root), base_ref],
            cwd=git_root,
            capture_output=True,
            text=True,
        )
        if add_result.returncode != 0:
            detail = (add_result.stderr or add_result.stdout).strip()
            raise PatchApplyError(f"could not create validation worktree at {base_ref}: {detail}")

        apply_result = subprocess.run(
            ["git", "apply"],
            cwd=temp_root,
            input=diff,
            capture_output=True,
            text=True,
            env=git_apply_env(temp_root),
        )
        if apply_result.returncode != 0:
            detail = (apply_result.stderr or apply_result.stdout).strip()
            raise PatchApplyError(f"stored patch did not apply cleanly for validation: {detail}")

        relative_repo_path = repo_path.resolve().relative_to(git_root)
        validation_path = temp_root / relative_repo_path
        yield validation_path
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(temp_root)],
            cwd=git_root,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(temp_root, ignore_errors=True)


def patch_is_already_applied(repo_path: Path, diff: str) -> bool:
    result = subprocess.run(
        ["git", "apply", "--reverse", "--check"],
        cwd=repo_path,
        input=diff,
        capture_output=True,
        text=True,
        env=git_apply_env(repo_path),
    )
    return result.returncode == 0


def git_apply_env(cwd: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CEILING_DIRECTORIES"] = str(cwd.resolve().parent)
    return env


def evaluate_command_result(command_result: CommandResult | None) -> tuple[str, str]:
    if command_result is None:
        return "not_evaluated", "Task has no test_command, so no evaluation command was run."
    if command_result.timed_out:
        return "failed", "Test command timed out."
    if command_result.exit_code == 0:
        return "passed", "Test command exited successfully."
    return "failed", "Test command exited with a non-zero status."


def evaluate_results(
    command_result: CommandResult | None,
    semantic_result: CommandResult | None,
) -> tuple[str, str]:
    command_status, command_notes = evaluate_command_result(command_result)
    if command_status != "passed":
        return command_status, command_notes
    if semantic_result is None:
        return command_status, command_notes
    semantic_status, semantic_notes = evaluate_command_result(semantic_result)
    if semantic_status != "passed":
        return "failed", f"Semantic check failed. {semantic_notes}"
    return "passed", "Test command and semantic check exited successfully."
