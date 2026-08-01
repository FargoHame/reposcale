from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from reposcale.commands import run_command
from reposcale.engineered_backend import GuardedFilesystemBackend
from reposcale.engineered_editing import make_replace_line_range_tool, replace_file_line_range, resolve_virtual_repo_path
from reposcale.engineered_prompts import ENGINEERED_SYSTEM_PROMPT, build_engineered_prompt
from reposcale.engineered_trace import has_final_message, now, trace_from_deepagents_result
from reposcale.llm import load_mistral_api_key
from reposcale.schemas import ModelConfig, TaskSpec, TraceEvent
from reposcale.validation_evidence import render_validation_evidence, summarize_validation


@dataclass(frozen=True)
class EngineeredAgentResult:
    status: Literal["completed", "failed"]
    trace: list[TraceEvent]


def run_engineered_agent(
    task: TaskSpec,
    model: ModelConfig,
    max_steps: int,
    recursion_limit: int | None = None,
) -> EngineeredAgentResult:
    effective_recursion_limit = recursion_limit or max(max_steps * 8, 100)
    result: Any = None
    try:
        agent = create_agent(task, model)
        for update in agent.stream(
            {"messages": [{"role": "user", "content": build_engineered_prompt(task)}]},
            config={"recursion_limit": effective_recursion_limit},
            stream_mode="values",
        ):
            result = update
    except Exception as error:
        trace = trace_from_deepagents_result(result)
        trace.append(
            TraceEvent(
                event_type="model_error",
                message=str(error),
                timestamp=now(),
                metadata={"recursion_limit": effective_recursion_limit},
            )
        )
        return EngineeredAgentResult(status="failed", trace=trace)

    trace = trace_from_deepagents_result(result)
    status: Literal["completed", "failed"] = "completed" if has_final_message(result) else "failed"
    return EngineeredAgentResult(status=status, trace=trace)


def create_agent(task: TaskSpec, model: ModelConfig) -> Any:
    from deepagents import create_deep_agent
    from langchain.chat_models import init_chat_model

    chat_model = init_chat_model(
        model=to_langchain_model_name(model),
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        timeout=120,
        max_retries=4,
    )
    backend = GuardedFilesystemBackend(root_dir=task.repo_path.resolve(), virtual_mode=True)
    return create_deep_agent(
        model=chat_model,
        tools=[make_validation_tool(task), make_search_context_tool(task), make_replace_line_range_tool(task)],
        system_prompt=ENGINEERED_SYSTEM_PROMPT,
        backend=backend,
    )


def to_langchain_model_name(model: ModelConfig) -> str:
    if model.provider == "mistral":
        os.environ.setdefault("MISTRAL_API_KEY", load_mistral_api_key())
        return f"mistralai:{model.model}"
    raise ValueError(f"engineered agent only supports provider=mistral for now, got: {model.provider}")


def make_validation_tool(task: TaskSpec):
    def run_validation() -> str:
        """Run the task's configured validation command in the task repository."""
        if task.test_command is None:
            return "No validation command configured."
        result = run_command(task.test_command, task.repo_path, task.test_timeout_seconds)
        evidence = summarize_validation(result)
        return (
            f"exit_code: {result.exit_code}\n"
            f"timed_out: {result.timed_out}\n"
            f"{render_validation_evidence(evidence)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return run_validation


def make_search_context_tool(task: TaskSpec):
    def search_context(
        pattern: str,
        path: str = "/",
        file_glob: str = "*.py",
        context_lines: int = 3,
        max_matches: int = 20,
    ) -> str:
        """Search text and return compact numbered context around each match."""
        if not pattern:
            return "error: pattern must not be empty"
        if context_lines < 0:
            return "error: context_lines must be >= 0"
        if max_matches < 1:
            return "error: max_matches must be >= 1"

        root = task.repo_path.resolve()
        search_root = resolve_virtual_repo_path(root, path)
        if not search_root.exists():
            return f"error: path not found: {path}"

        files = [search_root] if search_root.is_file() else sorted(search_root.rglob(file_glob))
        matches: list[str] = []
        for file_path in files:
            if len(matches) >= max_matches:
                break
            if not file_path.is_file() or should_skip_search_file(root, file_path):
                continue
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue

            for index, line in enumerate(lines):
                if pattern not in line:
                    continue
                start = max(index - context_lines, 0)
                end = min(index + context_lines + 1, len(lines))
                relative = "/" + file_path.relative_to(root).as_posix()
                matches.append(render_match(relative, lines, start, end, index))
                if len(matches) >= max_matches:
                    break

        if not matches:
            return f"no matches for {pattern!r}"
        return "\n\n".join(matches)

    return search_context


def should_skip_search_file(root: Path, file_path: Path) -> bool:
    relative_parts = file_path.relative_to(root).parts
    skipped_dirs = {".git", ".venv", "__pycache__", "node_modules", "dist", "build"}
    if any(part in skipped_dirs for part in relative_parts):
        return True
    return file_path.suffix in {".pyc", ".pyo", ".so", ".dll", ".exe", ".png", ".jpg", ".jpeg", ".gif", ".zip"}


def render_match(relative_path: str, lines: list[str], start: int, end: int, match_index: int) -> str:
    rendered_lines = []
    for line_index in range(start, end):
        marker = ">" if line_index == match_index else " "
        rendered_lines.append(f"{marker}{line_index + 1}: {lines[line_index]}")
    return f"{relative_path}:{match_index + 1}\n" + "\n".join(rendered_lines)
