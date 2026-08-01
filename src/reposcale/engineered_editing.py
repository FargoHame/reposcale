from __future__ import annotations

from pathlib import Path

from reposcale.schemas import TaskSpec


def make_replace_line_range_tool(task: TaskSpec):
    def replace_line_range(
        file_path: str,
        start_line: int,
        end_line: int,
        new_text: str,
        preserve_indentation: bool = True,
    ) -> str:
        """Replace a 1-based inclusive line range in a repository file."""
        return replace_file_line_range(
            task.repo_path,
            file_path,
            start_line,
            end_line,
            new_text,
            preserve_indentation=preserve_indentation,
        )

    return replace_line_range


def replace_file_line_range(
    repo_path: Path,
    file_path: str,
    start_line: int,
    end_line: int,
    new_text: str,
    preserve_indentation: bool = True,
) -> str:
    target = resolve_virtual_repo_path(repo_path, file_path)
    if not target.is_file():
        return f"error: file not found: {file_path}"
    if start_line < 1:
        return "error: start_line must be >= 1"
    if end_line < start_line:
        return "error: end_line must be >= start_line"

    content = target.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)
    if end_line > len(lines):
        return f"error: end_line {end_line} is past file length {len(lines)}"

    newline = "\r\n" if "\r\n" in content else "\n"
    replacement = normalize_replacement_lines(new_text, newline)
    if preserve_indentation:
        replacement = rebase_replacement_indentation(lines[start_line - 1], replacement)
    updated = "".join(lines[: start_line - 1] + replacement + lines[end_line:])
    if updated == content:
        return (
            f"no-op: replacement left {file_path} unchanged at lines {start_line}-{end_line}. "
            "Read the current target region and choose a different edit or stop if validation is already decisive."
        )
    target.write_text(updated, encoding="utf-8", newline="")
    return f"replaced lines {start_line}-{end_line} in {file_path}"


def normalize_replacement_lines(new_text: str, newline: str) -> list[str]:
    if new_text == "":
        return []
    normalized = new_text.replace("\r\n", "\n").replace("\r", "\n")
    replacement = [line + newline for line in normalized.split("\n")]
    if normalized.endswith("\n"):
        replacement.pop()
    return replacement


def leading_whitespace(line: str) -> str:
    return line[: len(line) - len(line.lstrip(" \t"))]


def rebase_replacement_indentation(original_first_line: str, replacement: list[str]) -> list[str]:
    first_replacement = first_nonblank_line(replacement)
    if first_replacement is None:
        return replacement

    original_indent = leading_whitespace(original_first_line)
    replacement_indent = leading_whitespace(first_replacement)
    if original_indent == replacement_indent:
        return replacement

    rebased: list[str] = []
    for line in replacement:
        if line.strip() == "":
            rebased.append(line)
        elif line.startswith(replacement_indent):
            rebased.append(original_indent + line[len(replacement_indent) :])
        else:
            rebased.append(original_indent + line.lstrip(" \t"))
    return rebased


def first_nonblank_line(lines: list[str]) -> str | None:
    for line in lines:
        if line.strip():
            return line
    return None


def resolve_virtual_repo_path(repo_path: Path, file_path: str) -> Path:
    relative_path = file_path[1:] if file_path.startswith("/") else file_path
    target = (repo_path / relative_path).resolve()
    root = repo_path.resolve()
    if target != root and root not in target.parents:
        raise ValueError(f"path escapes task repo: {file_path}")
    return target
