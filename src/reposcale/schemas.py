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


class EvaluationResult(BaseModel):
    eval_id: str
    run_id: str
    status: Literal["passed", "failed", "not_evaluated"]
    evaluated_at: datetime
    patch_applies: bool | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    notes: str | None = None
