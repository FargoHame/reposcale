from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Literal

from reposcale.commands import run_command
from reposcale.engineered_backend import GuardedFilesystemBackend
from reposcale.engineered_editing import make_replace_line_range_tool, replace_file_line_range
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
        tools=[make_validation_tool(task), make_replace_line_range_tool(task)],
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
