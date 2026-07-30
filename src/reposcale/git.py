from __future__ import annotations

import subprocess
from pathlib import Path

from reposcale.schemas import PatchSnapshot


def capture_patch_snapshot(repo_path: Path) -> PatchSnapshot:
    resolved_repo_path = repo_path.resolve()
    if not resolved_repo_path.exists() or not resolved_repo_path.is_dir():
        raise ValueError(f"task repo_path must be an existing directory: {repo_path}")

    git_root = run_git(resolved_repo_path, ["rev-parse", "--show-toplevel"])
    if git_root.returncode != 0:
        return PatchSnapshot(repo_path=resolved_repo_path, is_git_repo=False)

    git_root_path = Path(git_root.stdout.strip()).resolve()
    pathspec = resolved_repo_path.relative_to(git_root_path).as_posix()
    if pathspec == ".":
        pathspec = "."

    base_ref = run_git(git_root_path, ["rev-parse", "--short", "HEAD"])
    status = run_git(git_root_path, ["status", "--short", "--", pathspec])
    diff = run_git(git_root_path, ["diff", "--", pathspec])
    staged_diff = run_git(git_root_path, ["diff", "--cached", "--", pathspec])
    untracked = run_git(git_root_path, ["ls-files", "--others", "--exclude-standard", "--", pathspec])

    diff_text = diff.stdout
    staged_diff_text = staged_diff.stdout
    lines_added, lines_removed = count_diff_lines(diff_text + staged_diff_text)

    return PatchSnapshot(
        repo_path=resolved_repo_path,
        is_git_repo=True,
        base_ref=base_ref.stdout.strip() or None,
        status=status.stdout,
        diff=diff_text,
        staged_diff=staged_diff_text,
        untracked_files=[strip_pathspec(path, pathspec) for path in parse_output_lines(untracked.stdout)],
        changed_files=parse_changed_files(status.stdout, pathspec),
        lines_added=lines_added,
        lines_removed=lines_removed,
    )


def run_git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def parse_changed_files(status_output: str, pathspec: str = ".") -> list[str]:
    files: list[str] = []
    for line in status_output.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", maxsplit=1)[1]
        files.append(strip_pathspec(path, pathspec))
    return files


def parse_output_lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line]


def strip_pathspec(path: str, pathspec: str) -> str:
    if pathspec == ".":
        return path
    prefix = f"{pathspec}/"
    if path.startswith(prefix):
        return path.removeprefix(prefix)
    return path


def count_diff_lines(diff_text: str) -> tuple[int, int]:
    lines_added = 0
    lines_removed = 0
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            lines_added += 1
        elif line.startswith("-"):
            lines_removed += 1
    return lines_added, lines_removed
