from __future__ import annotations

import ast
from pathlib import Path

from typing import Literal

from reposcale.schemas import EvaluationResult, PatchQualityReport, PatchSnapshot, RunArtifact


GENERATED_FILE_NAMES = {
    "uv.lock",
    "poetry.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}


def analyze_patch_quality(run: RunArtifact) -> PatchQualityReport | None:
    if run.patch is None:
        return None

    syntax_errors = find_python_syntax_errors(run.task.repo_path, run.patch)
    duplicate_imports = find_duplicate_added_lines(run.patch.diff, ("import ", "from "))
    duplicate_decorators = find_duplicate_added_lines(run.patch.diff, ("@",))
    repeated_added_lines = find_repeated_added_lines(run.patch.diff)
    generated_files = find_generated_files(run.patch)
    warnings = build_warnings(
        syntax_errors,
        duplicate_imports,
        duplicate_decorators,
        repeated_added_lines,
        generated_files,
    )

    return PatchQualityReport(
        warnings=warnings,
        syntax_errors=syntax_errors,
        duplicate_imports=duplicate_imports,
        duplicate_decorators=duplicate_decorators,
        repeated_added_lines=repeated_added_lines,
        generated_files=generated_files,
    )


def find_python_syntax_errors(repo_path: Path, patch: PatchSnapshot) -> list[str]:
    errors: list[str] = []
    for changed_file in patch.changed_files:
        if not changed_file.endswith(".py"):
            continue
        target = (repo_path / changed_file).resolve()
        try:
            target.relative_to(repo_path.resolve())
        except ValueError:
            errors.append(f"{changed_file}: path escapes repo")
            continue
        if not target.exists():
            continue
        try:
            ast.parse(target.read_text(encoding="utf-8"), filename=changed_file)
        except SyntaxError as error:
            errors.append(f"{changed_file}:{error.lineno or 0}: {error.msg}")
    return errors


def find_duplicate_added_lines(diff: str, prefixes: tuple[str, ...]) -> list[str]:
    duplicates: list[str] = []
    hunk_lines: list[tuple[bool, str]] = []
    for raw_line in diff.splitlines():
        if raw_line.startswith("@@"):
            duplicates.extend(find_duplicate_additions_in_hunk(hunk_lines, prefixes))
            hunk_lines = []
            continue
        if raw_line.startswith("+++") or raw_line.startswith("---"):
            continue
        content = raw_line[1:] if raw_line[:1] in {" ", "+"} else ""
        stripped = content.strip()
        if not stripped or not stripped.startswith(prefixes):
            continue
        hunk_lines.append((raw_line.startswith("+"), stripped))
    duplicates.extend(find_duplicate_additions_in_hunk(hunk_lines, prefixes))
    return dedupe(duplicates)


def find_duplicate_additions_in_hunk(hunk_lines: list[tuple[bool, str]], prefixes: tuple[str, ...]) -> list[str]:
    counts: dict[str, int] = {}
    added: list[str] = []
    for is_added, line in hunk_lines:
        if not line.startswith(prefixes):
            continue
        counts[line] = counts.get(line, 0) + 1
        if is_added and line not in added:
            added.append(line)
    return [line for line in added if counts.get(line, 0) > 1]


def find_repeated_added_lines(diff: str, minimum_repetitions: int = 3) -> list[str]:
    repeated: list[str] = []
    hunk_added_lines: list[str] = []
    for raw_line in diff.splitlines():
        if raw_line.startswith("@@"):
            repeated.extend(find_repeated_lines(hunk_added_lines, minimum_repetitions))
            hunk_added_lines = []
            continue
        if raw_line.startswith("+++") or raw_line.startswith("---") or not raw_line.startswith("+"):
            continue
        stripped = raw_line[1:].strip()
        if is_meaningful_repeated_line_candidate(stripped):
            hunk_added_lines.append(stripped)
    repeated.extend(find_repeated_lines(hunk_added_lines, minimum_repetitions))
    return dedupe(repeated)


def is_meaningful_repeated_line_candidate(line: str) -> bool:
    if len(line) < 6:
        return False
    if line.startswith(("#", "//", "/*", "*")):
        return False
    return line not in {"break", "continue", "return", "pass"}


def find_repeated_lines(lines: list[str], minimum_repetitions: int) -> list[str]:
    counts: dict[str, int] = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    return [line for line, count in counts.items() if count >= minimum_repetitions]


def find_generated_files(patch: PatchSnapshot) -> list[str]:
    changed = [*patch.changed_files, *patch.untracked_files]
    return [path for path in changed if Path(path).name in GENERATED_FILE_NAMES]


def build_warnings(
    syntax_errors: list[str],
    duplicate_imports: list[str],
    duplicate_decorators: list[str],
    repeated_added_lines: list[str],
    generated_files: list[str],
) -> list[str]:
    warnings: list[str] = []
    warnings.extend(f"python syntax error: {error}" for error in syntax_errors)
    warnings.extend(f"possible duplicate import: {line}" for line in duplicate_imports)
    warnings.extend(f"possible duplicate decorator: {line}" for line in duplicate_decorators)
    warnings.extend(f"repeated added line: {line}" for line in repeated_added_lines)
    warnings.extend(f"generated dependency file changed: {path}" for path in generated_files)
    return warnings


def render_patch_quality(report: PatchQualityReport | None) -> str:
    if report is None:
        return "Patch quality: no patch quality analysis available."
    if not report.warnings:
        return "Patch quality: no warnings."
    return "\n".join(["Patch quality warnings:", *[f"- {warning}" for warning in report.warnings]])


def quality_status(report: PatchQualityReport | None) -> Literal["clean", "warning", "risky"]:
    if report is None or not report.warnings:
        return "clean"
    if report.syntax_errors:
        return "risky"
    return "warning"


def is_clean_pass(evaluation: EvaluationResult) -> bool:
    return evaluation.status == "passed" and evaluation.quality_status == "clean"


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
