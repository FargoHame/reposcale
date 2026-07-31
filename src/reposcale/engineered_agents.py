from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
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
4. Make a focused patch.
5. Run the validation tool.
6. Stop when validation passes or when you can clearly explain the blocker.

Rules:
- Work only inside the task repository.
- Prefer grep/glob before broad file reads.
- Avoid unrelated docs/config edits unless the task asks for them.
- Use the validation tool instead of inventing a test command.
"""


@dataclass(frozen=True)
class EngineeredAgentResult:
    status: Literal["completed", "failed"]
    trace: list[TraceEvent]


def run_engineered_agent(task: TaskSpec, model: ModelConfig, max_steps: int) -> EngineeredAgentResult:
    try:
        agent = create_agent(task, model)
        result = agent.invoke(
            {"messages": [{"role": "user", "content": build_engineered_prompt(task)}]},
            config={"recursion_limit": max(max_steps * 4, 25)},
        )
    except Exception as error:
        return EngineeredAgentResult(
            status="failed",
            trace=[
                TraceEvent(
                    event_type="model_error",
                    message=str(error),
                    timestamp=now(),
                )
            ],
        )

    trace = trace_from_deepagents_result(result)
    status: Literal["completed", "failed"] = "completed" if has_final_message(result) else "failed"
    return EngineeredAgentResult(status=status, trace=trace)


def create_agent(task: TaskSpec, model: ModelConfig) -> Any:
    from deepagents import create_deep_agent
    from deepagents.backends import FilesystemBackend
    from langchain.chat_models import init_chat_model

    chat_model = init_chat_model(
        model=to_langchain_model_name(model),
        temperature=model.temperature,
        max_tokens=model.max_tokens,
        timeout=120,
        max_retries=4,
    )
    backend = FilesystemBackend(root_dir=task.repo_path.resolve(), virtual_mode=True)
    return create_deep_agent(
        model=chat_model,
        tools=[make_validation_tool(task)],
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
        return (
            f"exit_code: {result.exit_code}\n"
            f"timed_out: {result.timed_out}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return run_validation


def build_engineered_prompt(task: TaskSpec) -> str:
    validation = task.test_command or "No validation command provided."
    return (
        f"Task ID: {task.task_id}\n"
        f"Title: {task.title}\n"
        "Repository root is mounted as the filesystem root.\n"
        f"Problem:\n{task.problem_statement}\n\n"
        f"Validation: use the run_validation tool. It runs: {validation}\n"
    )


def trace_from_deepagents_result(result: Any) -> list[TraceEvent]:
    trace: list[TraceEvent] = []
    messages = result.get("messages", []) if isinstance(result, dict) else []
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
                    trace.append(
                        TraceEvent(
                            event_type="tool_call",
                            message="Deep agent tool call.",
                            timestamp=now(),
                            tool_name=str(tool_call.get("name")),
                            tool_input=dict(tool_call.get("args") or {}),
                            metadata={"step": index, "message_type": message_type},
                        )
                    )
            continue

        if message_type == "ToolMessage":
            status = getattr(message, "status", "success")
            trace.append(
                TraceEvent(
                    event_type="tool_error" if status == "error" else "tool_result",
                    message="Deep agent tool result.",
                    timestamp=now(),
                    tool_name=str(getattr(message, "name", "") or ""),
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
