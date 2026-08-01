from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from reposcale.commands import run_command
from reposcale.llm import load_mistral_api_key
from reposcale.schemas import ModelConfig, TaskSpec, TraceEvent


ENGINEERED_SYSTEM_PROMPT = """You are RepoScale's engineered coding agent.
Solve repository tasks with a disciplined software-engineering workflow.

Workflow:
1. Write a short todo plan.
2. Search for the smallest relevant context.
3. Read only files needed for the fix.
4. Make a focused patch with replace_line_range when line numbers are known.
5. Run the validation tool.
6. Stop when validation passes or when you can clearly explain the blocker.

Rules:
- Work only inside the task repository.
- Prefer grep/glob before broad file reads.
- Avoid unrelated docs/config edits unless the task asks for them.
- Do not keep searching after you have found the target function.
- Use replace_line_range when you know the target line numbers or exact edit_file replacement fails.
- Use the validation tool instead of inventing a test command.
"""


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
        return EngineeredAgentResult(
            status="failed",
            trace=trace,
        )

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
        tools=[make_validation_tool(task), make_replace_line_range_tool(task)],
        system_prompt=ENGINEERED_SYSTEM_PROMPT,
        backend=backend,
    )


class GuardedFilesystemBackend:
    def __new__(cls, root_dir, virtual_mode: bool = True):
        from deepagents.backends import FilesystemBackend

        class _GuardedFilesystemBackend(FilesystemBackend):
            CONTEXT_GUARDRAIL_THRESHOLD = 8

            def __init__(self, guarded_root_dir, guarded_virtual_mode: bool = True) -> None:
                super().__init__(root_dir=guarded_root_dir, virtual_mode=guarded_virtual_mode)
                self._failed_edit_counts: dict[tuple[str, str, bool], int] = {}
                self._context_calls_since_write_or_edit = 0

            def ls(self, path: str):
                result = super().ls(path)
                if self._record_context_call() and result.error is None:
                    result.error = context_guardrail_message()
                return result

            def grep(
                self,
                pattern: str,
                path: str | None = None,
                glob: str | None = None,
                *,
                max_count: int | None = None,
                context_lines: int = 0,
            ):
                result = super().grep(pattern, path, glob, max_count=max_count, context_lines=context_lines)
                if self._record_context_call() and result.error is None:
                    result.error = context_guardrail_message()
                return result

            def glob(self, pattern: str, path: str | None = None):
                result = super().glob(pattern, path)
                if self._record_context_call() and result.error is None:
                    result.error = context_guardrail_message()
                return result

            def read(
                self,
                file_path: str,
                offset: int = 0,
                limit: int = 2000,
            ):
                result = super().read(file_path, offset, limit)
                should_warn = self._record_context_call()
                if (
                    should_warn
                    and result.error is None
                    and result.file_data is not None
                    and result.file_data.get("encoding") == "utf-8"
                ):
                    result.file_data["content"] = (
                        f"{result.file_data['content']}\n\n"
                        f"{context_guardrail_message()} "
                        "This narrow read is allowed so you can use the visible line numbers."
                    )
                return result

            def _record_context_call(self) -> bool:
                self._context_calls_since_write_or_edit += 1
                return self._context_calls_since_write_or_edit > self.CONTEXT_GUARDRAIL_THRESHOLD

            def write(
                self,
                file_path: str,
                content: str,
            ):
                self._context_calls_since_write_or_edit = 0
                return super().write(file_path, content)

            def edit(
                self,
                file_path: str,
                old_string: str,
                new_string: str,
                replace_all: bool = False,
            ):
                self._context_calls_since_write_or_edit = 0
                result = super().edit(file_path, old_string, new_string, replace_all)
                if result.error is None:
                    self._failed_edit_counts.pop((file_path, old_string, replace_all), None)
                    return result

                key = (file_path, old_string, replace_all)
                count = self._failed_edit_counts.get(key, 0) + 1
                self._failed_edit_counts[key] = count
                if count >= 2:
                    result.error = (
                        f"{result.error}\n\n"
                        "GUARDRAIL: This exact edit_file call has failed repeatedly. "
                        "Do not call edit_file again with the same old_string. "
                        "Read the current target region again, then use a smaller exact replacement "
                        "or rewrite the full file with write_file."
                    )
                return result

        return _GuardedFilesystemBackend(root_dir, virtual_mode)


def context_guardrail_message() -> str:
    return (
        "GUARDRAIL: Too many context-gathering tool calls have happened without a patch. "
        "Stop searching/listing. If you have line numbers, call replace_line_range now. "
        "If one final look is required, read one narrow target region only."
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
        return (
            f"exit_code: {result.exit_code}\n"
            f"timed_out: {result.timed_out}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return run_validation


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


def build_engineered_prompt(task: TaskSpec) -> str:
    validation = task.test_command or "No validation command provided."
    return (
        f"Task ID: {task.task_id}\n"
        f"Title: {task.title}\n"
        "Repository root is mounted as the filesystem root.\n"
        f"Problem:\n{task.problem_statement}\n\n"
        f"Validation: use the run_validation tool. It runs: {validation}\n"
        "Editing: use replace_line_range(file_path, start_line, end_line, new_text) "
        "when a read_file result gives reliable line numbers. It rebases replacement "
        "indentation onto the original code block by default.\n"
    )


def trace_from_deepagents_result(result: Any) -> list[TraceEvent]:
    trace: list[TraceEvent] = []
    messages = result.get("messages", []) if isinstance(result, dict) else []
    pending_tool_inputs: dict[str, dict[str, object]] = {}
    for index, message in enumerate(messages, start=1):
        message_type = message.__class__.__name__
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            trace.append(
                TraceEvent(
                    event_type="model_response",
                    message="Deep agent requested tool call(s).",
                    timestamp=now(),
                    output_summary=message_content(message),
                    metadata={"step": index, "message_type": message_type},
                )
            )
            for tool_call in tool_calls:
                if isinstance(tool_call, dict):
                    tool_name = str(tool_call.get("name"))
                    tool_input = dict(tool_call.get("args") or {})
                    tool_call_id = str(tool_call.get("id") or "")
                    if tool_call_id:
                        pending_tool_inputs[tool_call_id] = tool_input
                    trace.append(
                        TraceEvent(
                            event_type="tool_call",
                            message="Deep agent tool call.",
                            timestamp=now(),
                            tool_name=tool_name,
                            tool_input=tool_input,
                            metadata={"step": index, "message_type": message_type},
                        )
                    )
            continue

        if message_type == "ToolMessage":
            status = getattr(message, "status", "success")
            tool_call_id = str(getattr(message, "tool_call_id", "") or "")
            trace.append(
                TraceEvent(
                    event_type="tool_error" if status == "error" else "tool_result",
                    message="Deep agent tool result.",
                    timestamp=now(),
                    tool_name=str(getattr(message, "name", "") or ""),
                    tool_input=pending_tool_inputs.get(tool_call_id),
                    output_summary=message_content(message),
                    metadata={"step": index, "message_type": message_type},
                )
            )
            continue

        if message_type == "AIMessage":
            trace.append(
                TraceEvent(
                    event_type="model_response",
                    message="Deep agent model response.",
                    timestamp=now(),
                    output_summary=message_content(message),
                    metadata={"step": index, "message_type": message_type},
                )
            )

    if has_final_message(result):
        trace.append(
            TraceEvent(
                event_type="agent_final",
                message=message_content(result["messages"][-1]),
                timestamp=now(),
            )
        )
    return trace


def has_final_message(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    messages = result.get("messages", [])
    if not messages:
        return False
    last_message = messages[-1]
    return last_message.__class__.__name__ == "AIMessage" and not getattr(last_message, "tool_calls", None)


def message_content(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content[:500]
    return str(content)[:500]


def now() -> datetime:
    return datetime.now(timezone.utc)
