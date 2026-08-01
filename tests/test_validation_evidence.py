from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reposcale.schemas import CommandResult
from reposcale.validation_evidence import render_validation_evidence, summarize_validation


def test_summarize_validation_extracts_pytest_failure_evidence() -> None:
    result = command_result(
        exit_code=1,
        stdout=(
            "tests/test_codec.py F\n"
            "================================== FAILURES ===================================\n"
            "E   AssertionError: assert {'101': 9} == {101: 9}\n"
            "tests/test_codec.py:21: AssertionError\n"
            "FAILED tests/test_codec.py::test_decode_converts_integer_like_score_keys - AssertionError\n"
            "============================== 1 failed in 0.24s ==============================\n"
        ),
    )

    evidence = summarize_validation(result)

    assert evidence is not None
    assert evidence.exit_code == 1
    assert evidence.timed_out is False
    assert "AssertionError" in evidence.headline
    assert "tests/test_codec.py:21" in evidence.traceback_locations
    assert any("FAILED tests/test_codec.py" in line for line in evidence.pytest_summary)


def test_render_validation_evidence_is_compact_and_actionable() -> None:
    evidence = summarize_validation(command_result(exit_code=7, stderr='File "app.py", line 12\nValueError: bad config'))

    rendered = render_validation_evidence(evidence)

    assert "Validation evidence:" in rendered
    assert "exit_code: 7" in rendered
    assert "ValueError" in rendered
    assert "app.py:12" in rendered


def command_result(exit_code: int | None, stdout: str = "", stderr: str = "", timed_out: bool = False) -> CommandResult:
    now = datetime.now(timezone.utc)
    return CommandResult(
        command="pytest",
        cwd=Path("."),
        exit_code=exit_code,
        timed_out=timed_out,
        started_at=now,
        completed_at=now,
        duration_seconds=0.1,
        stdout=stdout,
        stderr=stderr,
    )
