from __future__ import annotations

from pathlib import Path


def main() -> int:
    repo = Path.cwd()
    failures: list[str] = []

    pyproject = read_text(repo / "pyproject.toml")
    if "pytest-freezegun" in pyproject:
        failures.append("pyproject.toml still depends on pytest-freezegun")
    if "time-machine" not in pyproject:
        failures.append("pyproject.toml does not depend on time-machine")

    affected_files = [
        repo / "tests" / "unit" / "test_reporter.py",
        repo / "tests" / "unit" / "test_session.py",
    ]
    for path in affected_files:
        text = read_text(path)
        if "freezegun" in text:
            failures.append(f"{relative(path, repo)} still imports or references freezegun")
        if "freeze_time" in text:
            failures.append(f"{relative(path, repo)} still uses freeze_time")
        if "time_machine" not in text and "travel(" not in text:
            failures.append(f"{relative(path, repo)} does not use time-machine")

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("ScanAPI pytest-freezegun migration checks passed.")
    return 0


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
