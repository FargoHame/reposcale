from __future__ import annotations

import json

from reposcale.schemas import RunArtifact, RunDiagnostics, TraceEvent

CONTEXT_STALL_THRESHOLD = 8
CONTEXT_TOOLS = {"read_file", "grep", "glob", "ls"}
PHASE_RESET_TOOLS = {"edit_file", "write_file", "run_validation", "run_command"}


def collect_run_diagnostics(run: RunArtifact) -> RunDiagnostics:
    return RunDiagnostics(
        model_calls=count_events(run.trace, "model_response"),
        tool_calls=count_events(run.trace, "tool_call"),
        tool_errors=count_events(run.trace, "tool_error"),
        model_errors=count_events(run.trace, "model_error"),
        invalid_responses=count_invalid_responses(run.trace),
        repeated_tool_calls=count_repeated_tool_calls(run.trace),
        repeated_tool_errors=count_repeated_tool_errors(run.trace),
        context_stall_tool_calls=count_context_stall_tool_calls(run.trace),
        files_read=count_tool_name(run.trace, "read_file"),
        commands_run=count_tool_name(run.trace, "run_command"),
        max_steps_reached=any(event.message.startswith("Agent reached max_steps=") for event in run.trace),
        changed_files=len(run.patch.changed_files) if run.patch else 0,
        lines_added=run.patch.lines_added if run.patch else 0,
        lines_removed=run.patch.lines_removed if run.patch else 0,
        run_duration_seconds=max((run.completed_at - run.started_at).total_seconds(), 0),
        artifact_saved=True,
    )


def count_events(trace: list[TraceEvent], event_type: str) -> int:
    return sum(1 for event in trace if event.event_type == event_type)


def count_tool_name(trace: list[TraceEvent], tool_name: str) -> int:
    return sum(1 for event in trace if event.event_type == "tool_call" and event.tool_name == tool_name)


def count_invalid_responses(trace: list[TraceEvent]) -> int:
    return sum(
        1
        for event in trace
        if event.event_type == "agent_error"
        and event.message == "Model response did not include a valid tool call or final answer."
    )


def count_repeated_tool_calls(trace: list[TraceEvent]) -> int:
    seen: set[tuple[str, str]] = set()
    repeated = 0
    for event in trace:
        if event.event_type != "tool_call" or event.tool_name is None:
            continue
        key = (event.tool_name, stable_json(event.tool_input or {}))
        if key in seen:
            repeated += 1
        seen.add(key)
    return repeated


def count_repeated_tool_errors(trace: list[TraceEvent]) -> int:
    seen: set[tuple[str, str, str]] = set()
    repeated = 0
    for event in trace:
        if event.event_type != "tool_error" or event.tool_name is None:
            continue
        key = (
            event.tool_name,
            stable_json(event.tool_input or {}),
            event.output_summary or event.message,
        )
        if key in seen:
            repeated += 1
        seen.add(key)
    return repeated


def count_context_stall_tool_calls(trace: list[TraceEvent]) -> int:
    context_calls_since_reset = 0
    stalled_calls = 0
    for event in trace:
        if event.event_type != "tool_call" or event.tool_name is None:
            continue
        if event.tool_name in PHASE_RESET_TOOLS:
            context_calls_since_reset = 0
            continue
        if event.tool_name not in CONTEXT_TOOLS:
            continue

        context_calls_since_reset += 1
        if context_calls_since_reset > CONTEXT_STALL_THRESHOLD:
            stalled_calls += 1
    return stalled_calls


def stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
