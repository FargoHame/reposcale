from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from reposcale.schemas import TraceEvent


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
