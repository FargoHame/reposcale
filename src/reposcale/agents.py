from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from reposcale.llm import OpenRouterClient
from reposcale.schemas import ModelConfig, TaskSpec, TraceEvent
from reposcale.tools import RepoTools


SYSTEM_PROMPT = """You are RepoScale's baseline coding agent.
You must solve the task by using the available repository tools.

Respond with exactly one JSON object per turn.

To call a tool:
{"tool": "list_files", "input": {"path": "."}}

To finish:
{"final": "short summary of what you changed and how you validated it"}

Available tools:
- list_files: {"path": "."}
- read_file: {"path": "relative/path.py"}
- search_text: {"query": "text to search for"}
- write_file: {"path": "relative/path.py", "content": "full new file content"}
- run_command: {"command": "uv run pytest", "timeout_seconds": 30}

Rules:
- Work only inside the task repository.
- Prefer reading tests before editing code.
- Use write_file only when you are ready to replace a complete file.
- Run the validation command when possible.
- Do not include markdown outside the JSON object.
"""


@dataclass(frozen=True)
class AgentResult:
    status: Literal["completed", "failed"]
    trace: list[TraceEvent]


def run_baseline_agent(
    task: TaskSpec,
    model: ModelConfig,
    client: OpenRouterClient,
    max_steps: int,
) -> AgentResult:
    tools = RepoTools(task.repo_path)
    trace: list[TraceEvent] = []
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_task_prompt(task)},
    ]

    for step in range(1, max_steps + 1):
        try:
            response = client.chat(messages, model)
        except Exception as error:
            trace.append(
                TraceEvent(
                    event_type="model_error",
                    message=str(error),
                    timestamp=now(),
                    metadata={"step": step},
                )
            )
            return AgentResult(status="failed", trace=trace)

        trace.append(
            TraceEvent(
                event_type="model_response",
                message="Model produced a response.",
                timestamp=now(),
                output_summary=response[:500],
                metadata={"step": step},
            )
        )

        action = parse_action(response)
        if "final" in action:
            trace.append(
                TraceEvent(
                    event_type="agent_final",
                    message=str(action["final"]),
                    timestamp=now(),
                    metadata={"step": step},
                )
            )
            return AgentResult(status="completed", trace=trace)

        tool_name = action.get("tool")
        tool_input = action.get("input", {})
        if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
            trace.append(
                TraceEvent(
                    event_type="agent_error",
                    message="Model response did not include a valid tool call or final answer.",
                    timestamp=now(),
                    metadata={"step": step},
                )
            )
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content": "Invalid response. Return one JSON tool call or final answer."})
            continue

        try:
            result = tools.run(tool_name, tool_input)
            observation = result.output
            trace.append(
                TraceEvent(
                    event_type="tool_call",
                    message="Executed tool call.",
                    timestamp=now(),
                    tool_name=tool_name,
                    tool_input=tool_input,
                    output_summary=result.summary,
                    metadata={"step": step},
                )
            )
        except Exception as error:
            observation = f"Tool error: {error}"
            trace.append(
                TraceEvent(
                    event_type="tool_error",
                    message=str(error),
                    timestamp=now(),
                    tool_name=tool_name,
                    tool_input=tool_input,
                    metadata={"step": step},
                )
            )

        messages.append({"role": "assistant", "content": response})
        messages.append({"role": "user", "content": f"Observation:\n{observation}"})

    trace.append(
        TraceEvent(
            event_type="agent_error",
            message=f"Agent reached max_steps={max_steps}.",
            timestamp=now(),
        )
    )
    return AgentResult(status="failed", trace=trace)


def build_task_prompt(task: TaskSpec) -> str:
    validation = task.test_command or "No validation command provided."
    return (
        f"Task ID: {task.task_id}\n"
        f"Title: {task.title}\n"
        "Repository: task root. Use relative paths only.\n"
        f"Problem:\n{task.problem_statement}\n\n"
        f"Validation command: {validation}\n"
    )


def parse_action(response: str) -> dict[str, object]:
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError:
        start = response.find("{")
        if start == -1:
            return {}
        try:
            parsed, _ = json.JSONDecoder().raw_decode(response[start:])
        except json.JSONDecodeError:
            return {}

    if not isinstance(parsed, dict):
        return {}
    return parsed


def now() -> datetime:
    return datetime.now(timezone.utc)
