from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from reposcale.schemas import EvaluationResult, RunArtifact, TaskSpec

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_task(path: Path) -> TaskSpec:
    with path.open("r", encoding="utf-8") as file:
        raw_task = yaml.safe_load(file)

    if not isinstance(raw_task, dict):
        raise ValueError("task YAML must contain a mapping/object at the top level")

    return TaskSpec.model_validate(raw_task)


def load_run(path: Path) -> RunArtifact:
    return load_json_model(path, RunArtifact, "run artifact JSON")


def load_evaluation(path: Path) -> EvaluationResult:
    return load_json_model(path, EvaluationResult, "evaluation artifact JSON")


def write_artifact(path: Path, artifact: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")


def load_json_model(path: Path, model_type: type[ModelT], label: str) -> ModelT:
    with path.open("r", encoding="utf-8") as file:
        raw_artifact = json.load(file)

    if not isinstance(raw_artifact, dict):
        raise ValueError(f"{label} must contain an object at the top level")

    return model_type.model_validate(raw_artifact)
