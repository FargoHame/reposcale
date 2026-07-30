from __future__ import annotations

from pathlib import Path
from collections.abc import Callable
from typing import Annotated, TypeVar, cast

import typer

from reposcale.comparison import create_comparison_report
from reposcale.evaluation import create_evaluation_artifact
from reposcale.runs import AgentName, create_run_artifact

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
) -> None:
    """Create a run artifact for a task."""
    if agent not in {"baseline", "engineered"}:
        raise typer.BadParameter("agent must be one of: baseline, engineered")

    output_path = as_cli_error(lambda: create_run_artifact(task, cast(AgentName, agent), runs_dir))
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


def as_cli_error(action: Callable[[], ReturnT]) -> ReturnT:
    try:
        return action()
    except ValueError as error:
        raise typer.BadParameter(str(error)) from error
