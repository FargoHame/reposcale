from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskSpec(BaseModel):
    task_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    repo_path: Path
    problem_statement: str = Field(min_length=1)
    test_command: str | None = None
    test_timeout_seconds: float = Field(default=30, gt=0)


class ModelConfig(BaseModel):
    provider: str
    model: str
    temperature: float = 0
    max_tokens: int | None = None


class TraceEvent(BaseModel):
    event_type: str
    message: str
    timestamp: datetime
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    output_summary: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchSnapshot(BaseModel):
    repo_path: Path
    is_git_repo: bool
    base_ref: str | None = None
    status: str = ""
    diff: str = ""
    staged_diff: str = ""
    untracked_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    lines_added: int = 0
    lines_removed: int = 0


class RunDiagnostics(BaseModel):
    model_calls: int = 0
    tool_calls: int = 0
    tool_errors: int = 0
    model_errors: int = 0
    invalid_responses: int = 0
    repeated_tool_calls: int = 0
    repeated_tool_errors: int = 0
    context_stall_tool_calls: int = 0
    files_read: int = 0
    commands_run: int = 0
    max_steps_reached: bool = False
    changed_files: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    run_duration_seconds: float = 0
    artifact_saved: bool = True


class RunArtifact(BaseModel):
    run_id: str
    task: TaskSpec
    agent: Literal["baseline", "engineered"]
    status: Literal["completed", "failed", "not_implemented"]
    started_at: datetime
    completed_at: datetime
    model: ModelConfig | None = None
    patch: PatchSnapshot | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    diagnostics: RunDiagnostics | None = None


class CommandResult(BaseModel):
    command: str
    cwd: Path
    exit_code: int | None
    timed_out: bool = False
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    stdout: str
    stderr: str


class ValidationEvidence(BaseModel):
    exit_code: int | None = None
    timed_out: bool = False
    headline: str = ""
    error_lines: list[str] = Field(default_factory=list)
    traceback_locations: list[str] = Field(default_factory=list)
    pytest_summary: list[str] = Field(default_factory=list)


class PatchQualityReport(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    syntax_errors: list[str] = Field(default_factory=list)
    duplicate_imports: list[str] = Field(default_factory=list)
    duplicate_decorators: list[str] = Field(default_factory=list)
    generated_files: list[str] = Field(default_factory=list)


class EvaluationResult(BaseModel):
    eval_id: str
    run_id: str
    task_id: str
    agent: Literal["baseline", "engineered"]
    status: Literal["passed", "failed", "not_evaluated"]
    evaluated_at: datetime
    test_command: CommandResult | None = None
    validation_evidence: ValidationEvidence | None = None
    patch_quality: PatchQualityReport | None = None
    patch_applies: bool | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    notes: str | None = None


class EvaluationSummary(BaseModel):
    eval_id: str
    run_id: str
    task_id: str
    agent: Literal["baseline", "engineered"]
    status: Literal["passed", "failed", "not_evaluated"]
    duration_seconds: float | None = None
    exit_code: int | None = None
    timed_out: bool | None = None


class ComparisonReport(BaseModel):
    report_id: str
    baseline: EvaluationSummary
    candidate: EvaluationSummary
    winner: Literal["baseline", "candidate", "tie", "none"]
    compared_at: datetime
    notes: list[str] = Field(default_factory=list)
