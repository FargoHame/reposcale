from __future__ import annotations

from datetime import datetime, timezone

from reposcale.diagnostics import count_context_stall_tool_calls
from reposcale.schemas import TraceEvent


def test_context_stall_counts_context_calls_after_threshold() -> None:
    trace = [tool_call("read_file", {"file_path": f"/src/{index}.py"}) for index in range(10)]

    assert count_context_stall_tool_calls(trace) == 2


def test_context_stall_resets_after_edit_or_validation() -> None:
    trace = [
        *[tool_call("read_file", {"file_path": f"/src/{index}.py"}) for index in range(8)],
        tool_call("edit_file", {"file_path": "/src/app.py"}),
        *[tool_call("read_file", {"file_path": f"/src/again_{index}.py"}) for index in range(8)],
        tool_call("run_validation", {}),
        tool_call("read_file", {"file_path": "/src/final.py"}),
    ]

    assert count_context_stall_tool_calls(trace) == 0


def tool_call(tool_name: str, tool_input: dict[str, object]) -> TraceEvent:
    return TraceEvent(
        event_type="tool_call",
        message="tool call",
        timestamp=datetime.now(timezone.utc),
        tool_name=tool_name,
        tool_input=tool_input,
    )
