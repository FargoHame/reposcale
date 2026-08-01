from __future__ import annotations

import re

from reposcale.schemas import CommandResult, ValidationEvidence


MAX_EVIDENCE_ITEMS = 8
ERROR_PATTERNS = (
    "assertionerror",
    "error:",
    "exception",
    "failed",
    "failures",
    "scannererror",
    "traceback",
)
PYTEST_SUMMARY_PREFIXES = ("FAILED ", "ERROR ", "PASSED ", "SKIPPED ")
FILE_LINE_PATTERN = re.compile(r'File "([^"]+)", line (\d+)')
PYTEST_LOCATION_PATTERN = re.compile(r"^([\w./\\-]+\.py):(\d+):")


def summarize_validation(command_result: CommandResult | None) -> ValidationEvidence | None:
    if command_result is None:
        return None

    combined = combine_output(command_result.stdout, command_result.stderr)
    lines = [line.rstrip() for line in combined.splitlines() if line.strip()]
    error_lines = select_error_lines(lines)
    traceback_locations = select_traceback_locations(lines)
    pytest_summary = select_pytest_summary(lines)
    headline = build_headline(command_result, error_lines, pytest_summary)

    return ValidationEvidence(
        exit_code=command_result.exit_code,
        timed_out=command_result.timed_out,
        headline=headline,
        error_lines=error_lines,
        traceback_locations=traceback_locations,
        pytest_summary=pytest_summary,
    )


def render_validation_evidence(evidence: ValidationEvidence | None) -> str:
    if evidence is None:
        return "Validation evidence: no validation command was configured."

    parts = [
        "Validation evidence:",
        f"- exit_code: {evidence.exit_code}",
        f"- timed_out: {evidence.timed_out}",
        f"- headline: {evidence.headline}",
    ]
    parts.extend(render_list("error_lines", evidence.error_lines))
    parts.extend(render_list("traceback_locations", evidence.traceback_locations))
    parts.extend(render_list("pytest_summary", evidence.pytest_summary))
    return "\n".join(parts)


def combine_output(stdout: str, stderr: str) -> str:
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr


def select_error_lines(lines: list[str]) -> list[str]:
    selected: list[str] = []
    for line in lines:
        lower = line.lower()
        if any(pattern in lower for pattern in ERROR_PATTERNS) or line.lstrip().startswith(("E   ", ">")):
            selected.append(trim_line(line))
        if len(selected) >= MAX_EVIDENCE_ITEMS:
            break
    return selected


def select_traceback_locations(lines: list[str]) -> list[str]:
    selected: list[str] = []
    for line in lines:
        file_match = FILE_LINE_PATTERN.search(line)
        pytest_match = PYTEST_LOCATION_PATTERN.search(line)
        if file_match:
            selected.append(f"{file_match.group(1)}:{file_match.group(2)}")
        elif pytest_match:
            selected.append(f"{pytest_match.group(1)}:{pytest_match.group(2)}")
        if len(selected) >= MAX_EVIDENCE_ITEMS:
            break
    return dedupe(selected)


def select_pytest_summary(lines: list[str]) -> list[str]:
    selected = [
        trim_line(line)
        for line in lines
        if line.startswith(PYTEST_SUMMARY_PREFIXES) or " failed" in line or " passed" in line
    ]
    return selected[-MAX_EVIDENCE_ITEMS:]


def build_headline(command_result: CommandResult, error_lines: list[str], pytest_summary: list[str]) -> str:
    if command_result.timed_out:
        return "Validation timed out."
    if command_result.exit_code == 0:
        return pytest_summary[-1] if pytest_summary else "Validation passed."
    concrete_error = first_concrete_error(error_lines)
    if concrete_error is not None:
        return concrete_error
    if pytest_summary:
        return pytest_summary[-1]
    if error_lines:
        return error_lines[0]
    return "Validation failed with a non-zero exit code."


def render_list(label: str, values: list[str]) -> list[str]:
    if not values:
        return [f"- {label}: none"]
    return [f"- {label}:", *[f"  - {value}" for value in values]]


def trim_line(line: str, limit: int = 220) -> str:
    stripped = line.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 14] + "... truncated"


def first_concrete_error(error_lines: list[str]) -> str | None:
    noisy_fragments = ("traceback", "failures", "errors")
    for line in error_lines:
        lower = line.lower()
        if any(fragment in lower for fragment in noisy_fragments) and not any(
            marker in line for marker in ("Error", "Exception")
        ):
            continue
        return line
    return None


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
