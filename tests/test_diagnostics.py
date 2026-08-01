from __future__ import annotations

from datetime import datetime, timezone

from reposcale.diagnostics import (
    count_context_stall_tool_calls,
    count_edit_attempts,
    count_no_op_edits,
    count_repeated_edit_attempts,
    count_validations_after_edit,
)
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


def test_edit_attempt_metrics_count_edit_loops_and_validation() -> None:
    trace = [
        tool_call("replace_line_range", {"file_path": "/src/app.py", "start_line": 1, "end_line": 1}),
        tool_result("replace_line_range", "replaced lines 1-1 in /src/app.py"),
        tool_call("replace_line_range", {"file_path": "/src/app.py", "start_line": 1, "end_line": 1}),
        tool_result("replace_line_range", "no-op: replacement left /src/app.py unchanged at lines 1-1."),
        tool_call("read_file", {"file_path": "/src/app.py"}),
        tool_call("run_validation", {}),
        tool_call("edit_file", {"file_path": "/src/app.py", "old_string": "x", "new_string": "y"}),
        tool_call("run_validation", {}),
    ]

    assert count_edit_attempts(trace) == 3
    assert count_no_op_edits(trace) == 1
    assert count_repeated_edit_attempts(trace) == 1
    assert count_validations_after_edit(trace) == 2


def tool_call(tool_name: str, tool_input: dict[str, object]) -> TraceEvent:
    return TraceEvent(
        event_type="tool_call",
        message="tool call",
        timestamp=datetime.now(timezone.utc),
        tool_name=tool_name,
        tool_input=tool_input,
    )


def tool_result(tool_name: str, output_summary: str) -> TraceEvent:
    return TraceEvent(
        event_type="tool_result",
        message="tool result",
        timestamp=datetime.now(timezone.utc),
        tool_name=tool_name,
        output_summary=output_summary,
    )
