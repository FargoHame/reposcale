from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer
import yaml

from reposcale.schemas import EvaluationResult, RunArtifact, TaskSpec, TraceEvent

app = typer.Typer(help="RepoScale coding-agent evaluation harness.")


@app.callback()
def main() -> None:
    """RepoScale command group."""


@app.command()
def run(
    agent: Annotated[str, typer.Option(help="Agent harness to run.")] = "baseline",
    task: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Path to a task YAML file.")] = Path(
        "tasks/example.yaml"
    ),
    runs_dir: Annotated[Path, typer.Option(help="Directory where run artifacts are written.")] = Path("runs"),
) -> None:
    """Create a run artifact for a task.

    Agent execution is intentionally mocked in the first MVP slice.
    """
    if agent not in {"baseline", "engineered"}:
        raise typer.BadParameter("agent must be one of: baseline, engineered")

    task_spec = load_task(task)
    started_at = datetime.now(timezone.utc)
    completed_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{task_spec.task_id}-{agent}"

    artifact = RunArtifact(
        run_id=run_id,
        task=task_spec,
        agent=agent,
        status="not_implemented",
        started_at=started_at,
        completed_at=completed_at,
        trace=[
            TraceEvent(
                event_type="run_created",
                message="Created placeholder run artifact; agent execution is not implemented yet.",
                timestamp=started_at,
            )
        ],
    )

    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / f"{run_id}.json"
    output_path.write_text(json.dumps(artifact.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote run artifact: {output_path}")


@app.command()
def eval(
    run: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Path to a run artifact JSON file.")],
    evals_dir: Annotated[Path, typer.Option(help="Directory where evaluation artifacts are written.")] = Path("evals"),
) -> None:
    """Create an evaluation artifact for a run.

    Test execution is intentionally mocked in the first evaluation slice.
    """
    run_artifact = load_run(run)
    evaluated_at = datetime.now(timezone.utc)
    timestamp = evaluated_at.strftime("%Y%m%dT%H%M%SZ")
    eval_id = f"{timestamp}-{run_artifact.run_id}"

    result = EvaluationResult(
        eval_id=eval_id,
        run_id=run_artifact.run_id,
        status="not_evaluated",
        evaluated_at=evaluated_at,
        notes="Created placeholder evaluation artifact; test execution is not implemented yet.",
    )

    evals_dir.mkdir(parents=True, exist_ok=True)
    output_path = evals_dir / f"{eval_id}.json"
    output_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Wrote evaluation artifact: {output_path}")


def load_task(path: Path) -> TaskSpec:
    with path.open("r", encoding="utf-8") as file:
        raw_task = yaml.safe_load(file)

    if not isinstance(raw_task, dict):
        raise typer.BadParameter("task YAML must contain a mapping/object at the top level")

    return TaskSpec.model_validate(raw_task)


def load_run(path: Path) -> RunArtifact:
    with path.open("r", encoding="utf-8") as file:
        raw_run = json.load(file)

    if not isinstance(raw_run, dict):
        raise typer.BadParameter("run artifact JSON must contain an object at the top level")

    return RunArtifact.model_validate(raw_run)
