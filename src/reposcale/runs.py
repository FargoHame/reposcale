from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from reposcale.artifacts import load_task, write_artifact
from reposcale.git import capture_patch_snapshot
from reposcale.schemas import RunArtifact, TraceEvent


AgentName = Literal["baseline", "engineered"]


def create_run_artifact(task_path: Path, agent: AgentName, runs_dir: Path) -> Path:
    task_spec = load_task(task_path)
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
        patch=capture_patch_snapshot(task_spec.repo_path),
        trace=[
            TraceEvent(
                event_type="run_created",
                message="Created placeholder run artifact; agent execution is not implemented yet.",
                timestamp=started_at,
            )
        ],
    )

    output_path = runs_dir / f"{run_id}.json"
    write_artifact(output_path, artifact)
    return output_path
