from __future__ import annotations

import json
from pathlib import Path

from reposcale.reporting import render_report


def test_render_report_summary_table(tmp_path: Path) -> None:
    write_run(tmp_path, run_id="run-1", task_id="task-a")
    write_eval(tmp_path, run_id="run-1", status="passed")

    report = render_report(tmp_path / "runs", tmp_path / "evals")

    assert "task" in report
    assert "task-a" in report
    assert "baseline" in report
    assert "passed" in report
    assert "quality" in report
    assert "clean" in report
    assert "invalid" in report
    assert "tool_err" in report
    assert "rep_err" in report
    assert "ctx_stall" in report
    assert "edits" in report
    assert "noop" in report
    assert "edit_rep" in report
    assert "val_after" in report
    assert "read_file" not in report


def test_render_report_details_include_tools_diff_and_eval_tail(tmp_path: Path) -> None:
    write_run(tmp_path, run_id="run-1", task_id="task-a")
    write_eval(tmp_path, run_id="run-1", status="passed")

    report = render_report(tmp_path / "runs", tmp_path / "evals", details=True)

    assert "Tool calls:" in report
    assert "Diagnostics:" in report
    assert "tool_calls: 1" in report
    assert "1. read_file {'path': 'src/app.py'}" in report
    assert "Changed files:" in report
    assert "src/app.py" in report
    assert "-old" in report
    assert "+new" in report
    assert "Eval stdout tail:" in report
    assert "Validation evidence:" in report
    assert "headline: Test command exited successfully." in report
    assert "Patch quality:" in report
    assert "2 passed" in report


def test_render_report_filters_by_task(tmp_path: Path) -> None:
    write_run(tmp_path, run_id="run-1", task_id="task-a")
    write_run(tmp_path, run_id="run-2", task_id="task-b")
    write_eval(tmp_path, run_id="run-1", status="passed")
    write_eval(tmp_path, run_id="run-2", status="failed")

    report = render_report(tmp_path / "runs", tmp_path / "evals", task_id="task-b")

    assert "task-b" in report
    assert "task-a" not in report


def test_render_report_can_show_latest_run_per_task_agent(tmp_path: Path) -> None:
    write_run(tmp_path, run_id="older", task_id="task-a", started_at="2026-07-31T00:00:00Z")
    write_run(tmp_path, run_id="newer", task_id="task-a", started_at="2026-07-31T00:01:00Z")

    report = render_report(tmp_path / "runs", tmp_path / "evals", latest=True)

    assert "task-a" in report
    assert report.count("task-a") == 1


def test_render_report_handles_empty_dirs(tmp_path: Path) -> None:
    assert render_report(tmp_path / "runs", tmp_path / "evals") == "No matching run artifacts found."


def test_render_report_skips_legacy_eval_artifacts(tmp_path: Path) -> None:
    write_run(tmp_path, run_id="run-1", task_id="task-a")
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "legacy.json").write_text(json.dumps({"run_id": "run-1"}), encoding="utf-8")

    report = render_report(tmp_path / "runs", evals_dir)

    assert "task-a" in report
    assert "missing" in report


def test_render_report_calculates_diagnostics_for_legacy_run(tmp_path: Path) -> None:
    write_run(tmp_path, run_id="run-1", task_id="task-a", include_diagnostics=False)

    report = render_report(tmp_path / "runs", tmp_path / "evals", details=True)

    assert "model_calls: 1" in report
    assert "tool_calls: 1" in report
    assert "invalid_responses: 1" in report
    assert "tool_errors: 1" in report
    assert "repeated_tool_calls: 0" in report
    assert "repeated_tool_errors: 0" in report
    assert "context_stall_tool_calls: 0" in report
    assert "edit_attempts: 0" in report
    assert "no_op_edits: 0" in report
    assert "repeated_edit_attempts: 0" in report
    assert "validations_after_edit: 0" in report


def write_run(
    tmp_path: Path,
    run_id: str,
    task_id: str,
    started_at: str = "2026-07-31T00:00:00Z",
    include_diagnostics: bool = True,
) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir(exist_ok=True)
    artifact = {
        "run_id": run_id,
        "task": {
            "task_id": task_id,
            "title": "Task",
            "repo_path": ".",
            "problem_statement": "Fix it.",
            "test_command": "uv run pytest",
            "test_timeout_seconds": 15,
        },
        "agent": "baseline",
        "status": "completed",
        "started_at": started_at,
        "completed_at": "2026-07-31T00:00:01Z",
        "patch": {
            "repo_path": ".",
            "is_git_repo": True,
            "base_ref": "abc123",
            "status": " M src/app.py\n",
            "diff": "diff --git a/src/app.py b/src/app.py\n-old\n+new\n",
            "changed_files": ["src/app.py"],
            "lines_added": 1,
            "lines_removed": 1,
        },
        "trace": [
            {
                "event_type": "model_response",
                "message": "Model produced a response.",
                "timestamp": "2026-07-31T00:00:00Z",
                "output_summary": "{\"tool\": \"read_file\"}",
            },
            {
                "event_type": "tool_call",
                "message": "Executed tool call.",
                "timestamp": "2026-07-31T00:00:00Z",
                "tool_name": "read_file",
                "tool_input": {"path": "src/app.py"},
                "output_summary": "Read src/app.py.",
            },
            {
                "event_type": "agent_error",
                "message": "Model response did not include a valid tool call or final answer.",
                "timestamp": "2026-07-31T00:00:00Z",
            },
            {
                "event_type": "tool_error",
                "message": "path is not a file: missing.py",
                "timestamp": "2026-07-31T00:00:00Z",
                "tool_name": "read_file",
                "tool_input": {"path": "missing.py"},
            },
        ],
    }
    if include_diagnostics:
        artifact["diagnostics"] = {
            "model_calls": 1,
            "tool_calls": 1,
            "tool_errors": 1,
            "model_errors": 0,
            "invalid_responses": 1,
            "repeated_tool_calls": 0,
            "repeated_tool_errors": 0,
            "context_stall_tool_calls": 0,
            "edit_attempts": 0,
            "no_op_edits": 0,
            "repeated_edit_attempts": 0,
            "validations_after_edit": 0,
            "files_read": 1,
            "commands_run": 0,
            "max_steps_reached": False,
            "changed_files": 1,
            "lines_added": 1,
            "lines_removed": 1,
            "run_duration_seconds": 1.0,
            "artifact_saved": True,
        }
    (runs_dir / f"{run_id}.json").write_text(
        json.dumps(artifact),
        encoding="utf-8",
    )


def write_eval(tmp_path: Path, run_id: str, status: str) -> None:
    evals_dir = tmp_path / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / f"eval-{run_id}.json").write_text(
        json.dumps(
            {
                "eval_id": f"eval-{run_id}",
                "run_id": run_id,
                "task_id": "task-a",
                "agent": "baseline",
                "status": status,
                "evaluated_at": "2026-07-31T00:00:02Z",
                "test_command": {
                    "command": "uv run pytest",
                    "cwd": ".",
                    "exit_code": 0 if status == "passed" else 1,
                    "timed_out": False,
                    "started_at": "2026-07-31T00:00:02Z",
                    "completed_at": "2026-07-31T00:00:03Z",
                "duration_seconds": 0.5,
                "stdout": "line 1\nline 2\n2 passed\n",
                "stderr": "",
            },
            "validation_evidence": {
                "exit_code": 0,
                "timed_out": False,
                "headline": "Test command exited successfully.",
                "error_lines": [],
                "traceback_locations": [],
                "pytest_summary": ["2 passed"],
            },
            "patch_quality": {
                "warnings": [],
                "syntax_errors": [],
                "duplicate_imports": [],
                "duplicate_decorators": [],
                "repeated_added_lines": [],
                "generated_files": [],
            },
            "quality_status": "clean",
            "clean_pass": status == "passed",
        }
    ),
        encoding="utf-8",
    )
