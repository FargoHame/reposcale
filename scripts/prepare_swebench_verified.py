from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import yaml


DATASET = "princeton-nlp/SWE-bench_Verified"
SPLIT = "test"
PAGE_SIZE = 100


def main() -> int:
    root = Path.cwd()
    selection_path = root / "benchmarks" / "v1" / "swebench_verified_20_selection.yaml"
    selection = load_yaml(selection_path)
    selected_ids = selection["selected_instances"]
    rows = fetch_selected_rows(set(selected_ids))
    missing = [instance_id for instance_id in selected_ids if instance_id not in rows]
    if missing:
        raise SystemExit(f"Missing selected SWE-bench rows: {', '.join(missing)}")

    tasks_dir = root / "tasks" / "v1"
    patches_dir = root / "benchmarks" / "v1" / "validation_patches"
    external_dir = root / "benchmarks" / "external" / "swebench"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    patches_dir.mkdir(parents=True, exist_ok=True)
    external_dir.mkdir(parents=True, exist_ok=True)
    clear_generated_files(tasks_dir, "*.yaml")
    clear_generated_files(patches_dir, "*.patch")

    suite_tasks: list[dict[str, Any]] = []
    for instance_id in selected_ids:
        row = rows[instance_id]
        repo_path = prepare_repo(external_dir, instance_id, row["repo"], row["base_commit"])
        validation_patch_path = patches_dir / f"{instance_id}.patch"
        validation_patch_path.write_text(row["test_patch"], encoding="utf-8")
        task_path = tasks_dir / f"{instance_id}.yaml"
        write_task_yaml(
            task_path,
            repo_path.relative_to(root),
            validation_patch_path.relative_to(root),
            row,
        )
        suite_tasks.append(
            {
                "task_path": task_path.relative_to(root).as_posix(),
                "repo_commit": restore_ref(row["base_commit"]),
                "source_base_commit": row["base_commit"],
                "source_issue": f"https://github.com/{row['repo']}/issues/{issue_number(instance_id)}",
                "difficulty": row["difficulty"],
                "domain": row["repo"],
            }
        )

    suite = {
        "suite_id": selection["suite_id"],
        "harness_ref": selection["harness_ref"],
        "agents": selection["agents"],
        "model": selection["model"],
        "budgets": selection["budgets"],
        "tasks": suite_tasks,
    }
    suite_path = root / "benchmarks" / "v1" / "swebench_verified_20_suite.yaml"
    suite_path.write_text(yaml.safe_dump(suite, sort_keys=False), encoding="utf-8")
    print(f"Wrote {suite_path}")
    print(f"Wrote {len(suite_tasks)} task specs under {tasks_dir}")
    return 0


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a mapping")
    return data


def fetch_selected_rows(selected_ids: set[str]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for offset in range(0, 500, PAGE_SIZE):
        for row in fetch_page(offset):
            instance_id = row["instance_id"]
            if instance_id in selected_ids:
                rows[instance_id] = row
        if selected_ids.issubset(rows):
            return rows
    return rows


def fetch_page(offset: int) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(
        {
            "dataset": DATASET,
            "config": "default",
            "split": SPLIT,
            "offset": offset,
            "length": PAGE_SIZE,
        }
    )
    url = f"https://datasets-server.huggingface.co/rows?{query}"
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [item["row"] for item in payload["rows"]]


def prepare_repo(external_dir: Path, instance_id: str, repo: str, base_commit: str) -> Path:
    repo_path = external_dir / instance_id
    validate_child_path(external_dir, repo_path)
    if repo_path.exists() and has_restore_ref(repo_path, base_commit):
        run(["git", "reset", "--hard", restore_ref(base_commit)], repo_path)
        run(["git", "clean", "-fd"], repo_path)
        return repo_path
    if repo_path.exists():
        remove_tree(repo_path)
    download_source_archive(repo, base_commit, repo_path)
    run(["git", "init"], repo_path)
    run(["git", "config", "user.name", "RepoScale"], repo_path)
    run(["git", "config", "user.email", "reposcale@example.com"], repo_path)
    run(["git", "add", "."], repo_path)
    run(["git", "commit", "-m", f"upstream {base_commit}"], repo_path)
    run(["git", "tag", restore_ref(base_commit)], repo_path)
    run(["git", "clean", "-fd"], repo_path)
    return repo_path


def download_source_archive(repo: str, base_commit: str, repo_path: Path) -> None:
    owner, name = repo.split("/", maxsplit=1)
    url = f"https://codeload.github.com/{owner}/{name}/zip/{base_commit}"
    with tempfile.TemporaryDirectory(prefix="reposcale_swebench_archive_") as temp_dir:
        temp_path = Path(temp_dir)
        archive_path = temp_path / "source.zip"
        urllib.request.urlretrieve(url, archive_path)
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(temp_path)
        extracted_roots = [path for path in temp_path.iterdir() if path.is_dir()]
        if len(extracted_roots) != 1:
            raise RuntimeError(f"expected one extracted root for {repo}@{base_commit}")
        shutil.move(str(extracted_roots[0]), repo_path)


def has_restore_ref(repo_path: Path, base_commit: str) -> bool:
    if not (repo_path / ".git").exists():
        return False
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", restore_ref(base_commit)],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def restore_ref(base_commit: str) -> str:
    return f"upstream-{base_commit}"


def validate_child_path(parent: Path, child: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_child = child.resolve()
    try:
        resolved_child.relative_to(resolved_parent)
    except ValueError as error:
        raise RuntimeError(f"refusing to remove path outside {resolved_parent}: {resolved_child}") from error


def clear_generated_files(directory: Path, pattern: str) -> None:
    for path in directory.glob(pattern):
        if path.is_file():
            path.unlink()


def remove_tree(path: Path) -> None:
    def on_error(function, target, _exc_info) -> None:
        os.chmod(target, 0o700)
        function(target)

    shutil.rmtree(path, onerror=on_error)


def write_task_yaml(task_path: Path, repo_path: Path, validation_patch_path: Path, row: dict[str, Any]) -> None:
    fail_to_pass = json.loads(row["FAIL_TO_PASS"])
    pass_to_pass = json.loads(row["PASS_TO_PASS"])
    tests = [*fail_to_pass, *pass_to_pass[:5]]
    task = {
        "task_id": row["instance_id"],
        "title": f"SWE-bench Verified {row['instance_id']}",
        "repo_path": repo_path.as_posix(),
        "problem_statement": row["problem_statement"],
        "test_command": "python -m pytest " + " ".join(shell_quote(test) for test in tests),
        "test_timeout_seconds": 120,
        "validation_patch": validation_patch_path.as_posix(),
    }
    task_path.write_text(yaml.safe_dump(task, sort_keys=False), encoding="utf-8")


def issue_number(instance_id: str) -> str:
    return instance_id.rsplit("-", maxsplit=1)[-1]


def shell_quote(value: str) -> str:
    escaped = value.replace('"', '\\"')
    return f'"{escaped}"'


def run(command: list[str], cwd: Path) -> None:
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(f"command failed in {cwd}: {' '.join(command)}\n{detail}")


if __name__ == "__main__":
    raise SystemExit(main())
