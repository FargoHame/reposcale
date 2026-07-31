from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from reposcale.agents import run_baseline_agent
from reposcale.artifacts import load_task, write_artifact
from reposcale.diagnostics import collect_run_diagnostics
from reposcale.engineered_agents import run_engineered_agent
from reposcale.git import capture_patch_snapshot
from reposcale.llm import create_llm_client
from reposcale.schemas import ModelConfig, RunArtifact, TraceEvent


AgentName = Literal["baseline", "engineered"]


def create_run_artifact(
    task_path: Path,
    agent: AgentName,
    runs_dir: Path,
    execute_agent: bool = False,
    model: ModelConfig | None = None,
    max_steps: int = 12,
) -> Path:
    task_spec = load_task(task_path)
    started_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")
    run_id = f"{timestamp}-{task_spec.task_id}-{agent}"
    trace = [
        TraceEvent(
            event_type="run_created",
            message="Created run artifact.",
            timestamp=started_at,
        )
    ]
    status: Literal["completed", "failed", "not_implemented"] = "not_implemented"

    if execute_agent:
        model = model or default_model_config()
        if agent == "baseline":
            client = create_llm_client(model)
            result = run_baseline_agent(task_spec, model, client, max_steps)
        else:
            result = run_engineered_agent(task_spec, model, max_steps)
        status = result.status
        trace.extend(result.trace)
    else:
        trace.append(
            TraceEvent(
                event_type="agent_skipped",
                message="Agent execution was not requested.",
                timestamp=datetime.now(timezone.utc),
            )
        )

    completed_at = datetime.now(timezone.utc)

    artifact = RunArtifact(
        run_id=run_id,
        task=task_spec,
        agent=agent,
        status=status,
        started_at=started_at,
        completed_at=completed_at,
        model=model if execute_agent else None,
        patch=capture_patch_snapshot(task_spec.repo_path),
        trace=trace,
    )
    artifact.diagnostics = collect_run_diagnostics(artifact)

    output_path = runs_dir / f"{run_id}.json"
    write_artifact(output_path, artifact)
    return output_path


def default_model_config() -> ModelConfig:
    return ModelConfig(
        provider="mistral",
        model="devstral-latest",
        temperature=0,
        max_tokens=2048,
    )
