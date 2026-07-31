from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Annotated, TypeVar, cast

import typer

from reposcale.comparison import create_comparison_report
from reposcale.evaluation import create_evaluation_artifact
from reposcale.llm import LlmError, OpenRouterError
from reposcale.reporting import render_report
from reposcale.runs import AgentName, create_run_artifact
from reposcale.schemas import ModelConfig

app = typer.Typer(help="RepoScale coding-agent evaluation harness.")
ReturnT = TypeVar("ReturnT")


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
    execute_agent: Annotated[bool, typer.Option(help="Actually execute the agent instead of writing a placeholder run.")] = False,
    provider: Annotated[str, typer.Option(help="Model provider for agent execution.")] = "mistral",
    model: Annotated[str, typer.Option(help="Model slug for agent execution.")] = "devstral-latest",
    max_tokens: Annotated[int, typer.Option(help="Maximum output tokens for model calls.")] = 2048,
    max_steps: Annotated[int, typer.Option(help="Maximum model/tool loop steps.")] = 12,
) -> None:
    """Create a run artifact for a task."""
    if agent not in {"baseline", "engineered"}:
        raise typer.BadParameter("agent must be one of: baseline, engineered")

    model_config = ModelConfig(provider=provider, model=model, temperature=0, max_tokens=max_tokens)
    output_path = as_cli_error(
        lambda: create_run_artifact(
            task,
            cast(AgentName, agent),
            runs_dir,
            execute_agent=execute_agent,
            model=model_config,
            max_steps=max_steps,
        )
    )
    typer.echo(f"Wrote run artifact: {output_path}")


@app.command()
def eval(
    run: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Path to a run artifact JSON file.")],
    evals_dir: Annotated[Path, typer.Option(help="Directory where evaluation artifacts are written.")] = Path("evals"),
) -> None:
    """Create an evaluation artifact for a run."""
    output_path = as_cli_error(lambda: create_evaluation_artifact(run, evals_dir))
    typer.echo(f"Wrote evaluation artifact: {output_path}")


@app.command()
def compare(
    baseline: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Baseline eval artifact JSON.")],
    candidate: Annotated[Path, typer.Option(exists=True, dir_okay=False, help="Candidate eval artifact JSON.")],
    reports_dir: Annotated[Path, typer.Option(help="Directory where comparison reports are written.")] = Path(
        "reports"
    ),
) -> None:
    """Compare two evaluation artifacts."""
    output_path = as_cli_error(lambda: create_comparison_report(baseline, candidate, reports_dir))
    typer.echo(f"Wrote comparison report: {output_path}")


@app.command()
def report(
    runs_dir: Annotated[Path, typer.Option(help="Directory containing run artifacts.")] = Path("runs"),
    evals_dir: Annotated[Path, typer.Option(help="Directory containing eval artifacts.")] = Path("evals"),
    details: Annotated[bool, typer.Option(help="Show tool calls, changed files, diff, and eval output tail.")] = False,
    latest: Annotated[bool, typer.Option(help="Only show the newest run per task and agent.")] = False,
    task: Annotated[str | None, typer.Option(help="Only show one task_id.")] = None,
) -> None:
    """Render a human-readable report from run and eval artifacts."""
    typer.echo(as_cli_error(lambda: render_report(runs_dir, evals_dir, details=details, task_id=task, latest=latest)))


def as_cli_error(action: Callable[[], ReturnT]) -> ReturnT:
    try:
        return action()
    except (LlmError, OpenRouterError, ValueError) as error:
        raise typer.BadParameter(str(error)) from error
