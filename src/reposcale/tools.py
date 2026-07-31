from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from reposcale.commands import run_command


IGNORED_DIRS = {".git", ".venv", ".pytest_cache", "__pycache__"}
MAX_TOOL_OUTPUT_CHARS = 12_000


@dataclass(frozen=True)
class ToolResult:
    output: str
    summary: str


class RepoTools:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path.resolve()
        if not self.repo_path.exists() or not self.repo_path.is_dir():
            raise ValueError(f"task repo_path must be an existing directory: {repo_path}")

    def run(self, tool_name: str, tool_input: dict[str, object]) -> ToolResult:
        if tool_name == "list_files":
            path = tool_input.get("path")
            return self.list_files(path if isinstance(path, str) and path else ".")
        if tool_name == "read_file":
            return self.read_file(require_string(tool_input, "path"))
        if tool_name == "search_text":
            return self.search_text(require_string(tool_input, "query"))
        if tool_name == "write_file":
            return self.write_file(require_string(tool_input, "path"), require_string(tool_input, "content"))
        if tool_name == "run_command":
            timeout = float(tool_input.get("timeout_seconds", 30))
            return self.run_shell_command(require_string(tool_input, "command"), timeout)
        raise ValueError(f"unknown tool: {tool_name}")

    def list_files(self, path: str = ".") -> ToolResult:
        root = self.resolve_inside_repo(path)
        if not root.is_dir():
            raise ValueError(f"path is not a directory: {path}")

        files: list[str] = []
        for candidate in sorted(root.rglob("*")):
            if should_skip(candidate):
                continue
            if candidate.is_file():
                files.append(relative_to(candidate, self.repo_path))

        output = "\n".join(files[:500])
        if len(files) > 500:
            output += f"\n... {len(files) - 500} more files omitted"
        return ToolResult(output=output, summary=f"Listed {min(len(files), 500)} files under {path}.")

    def read_file(self, path: str) -> ToolResult:
        target = self.resolve_inside_repo(path)
        if not target.is_file():
            raise ValueError(f"path is not a file: {path}")
        text = target.read_text(encoding="utf-8")
        output = truncate(text)
        return ToolResult(output=output, summary=f"Read {relative_to(target, self.repo_path)}.")

    def search_text(self, query: str) -> ToolResult:
        matches: list[str] = []
        for candidate in sorted(self.repo_path.rglob("*")):
            if should_skip(candidate) or not candidate.is_file():
                continue
            try:
                lines = candidate.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(lines, start=1):
                if query.lower() in line.lower():
                    matches.append(f"{relative_to(candidate, self.repo_path)}:{line_number}: {line}")
                    if len(matches) >= 100:
                        output = "\n".join(matches)
                        return ToolResult(output=output, summary="Search returned first 100 matches.")

        output = "\n".join(matches)
        return ToolResult(output=output, summary=f"Search found {len(matches)} matches.")

    def write_file(self, path: str, content: str) -> ToolResult:
        target = self.resolve_inside_repo(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return ToolResult(output=f"Wrote {relative_to(target, self.repo_path)}.", summary=f"Wrote {path}.")

    def run_shell_command(self, command: str, timeout_seconds: float) -> ToolResult:
        result = run_command(command, self.repo_path, timeout_seconds)
        output = (
            f"exit_code: {result.exit_code}\n"
            f"timed_out: {result.timed_out}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
        return ToolResult(output=truncate(output), summary=f"Command exited with {result.exit_code}.")

    def resolve_inside_repo(self, path: str) -> Path:
        target = (self.repo_path / path).resolve()
        if target != self.repo_path and self.repo_path not in target.parents:
            raise ValueError(f"path escapes task repo: {path}")
        return target


def require_string(tool_input: dict[str, object], key: str) -> str:
    value = tool_input.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"tool input must include string field: {key}")
    return value


def should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def relative_to(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... truncated {len(text) - limit} characters"
