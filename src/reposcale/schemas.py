from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

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


class RunArtifact(BaseModel):
    run_id: str
    task: TaskSpec
    agent: Literal["baseline", "engineered"]
    status: Literal["completed", "failed", "not_implemented"]
    started_at: datetime
    completed_at: datetime
    model: ModelConfig | None = None
    trace: list[TraceEvent] = Field(default_factory=list)


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


class EvaluationResult(BaseModel):
    eval_id: str
    run_id: str
    task_id: str
    agent: Literal["baseline", "engineered"]
    status: Literal["passed", "failed", "not_evaluated"]
    evaluated_at: datetime
    test_command: CommandResult | None = None
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
