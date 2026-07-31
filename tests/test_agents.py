from __future__ import annotations

from pathlib import Path

from reposcale.agents import parse_action, run_baseline_agent
from reposcale.schemas import ModelConfig, TaskSpec


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], model: ModelConfig) -> str:
        self.messages.append(messages.copy())
        return self.responses.pop(0)


class FailingClient:
    def chat(self, messages: list[dict[str, str]], model: ModelConfig) -> str:
        raise RuntimeError("model unavailable")


def test_baseline_agent_executes_tool_then_finishes(tmp_path: Path) -> None:
    (tmp_path / "example.py").write_text("value = 1\n", encoding="utf-8")
    task = make_task(tmp_path)
    client = FakeClient(
        [
            '{"tool": "read_file", "input": {"path": "example.py"}}',
            '{"final": "Read the file."}',
        ]
    )

    result = run_baseline_agent(task, make_model(), client, max_steps=4)  # type: ignore[arg-type]

    assert result.status == "completed"
    assert [event.event_type for event in result.trace] == ["model_response", "tool_call", "model_response", "agent_final"]
    assert result.trace[1].tool_name == "read_file"
    assert "value = 1" in client.messages[-1][-1]["content"]


def test_baseline_agent_records_tool_errors(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    client = FakeClient(
        [
            '{"tool": "read_file", "input": {"path": "../outside.py"}}',
            '{"final": "Stopped after error."}',
        ]
    )

    result = run_baseline_agent(task, make_model(), client, max_steps=4)  # type: ignore[arg-type]

    assert result.status == "completed"
    assert result.trace[1].event_type == "tool_error"
    assert "escapes task repo" in result.trace[1].message


def test_baseline_agent_fails_after_max_steps(tmp_path: Path) -> None:
    task = make_task(tmp_path)
    client = FakeClient(['{"tool": "list_files", "input": {"path": "."}}'])

    result = run_baseline_agent(task, make_model(), client, max_steps=1)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert result.trace[-1].event_type == "agent_error"
    assert "max_steps=1" in result.trace[-1].message


def test_baseline_agent_records_model_errors(tmp_path: Path) -> None:
    result = run_baseline_agent(make_task(tmp_path), make_model(), FailingClient(), max_steps=2)  # type: ignore[arg-type]

    assert result.status == "failed"
    assert result.trace[0].event_type == "model_error"
    assert result.trace[0].message == "model unavailable"


def test_parse_action_recovers_first_json_object() -> None:
    action = parse_action('{"tool": "list_files", "input": {"path": "."}}\n}')

    assert action == {"tool": "list_files", "input": {"path": "."}}


def make_task(repo_path: Path) -> TaskSpec:
    return TaskSpec(
        task_id="agent-test",
        title="Agent test",
        repo_path=repo_path,
        problem_statement="Inspect the repo.",
        test_command=None,
    )


def make_model() -> ModelConfig:
    return ModelConfig(provider="test", model="fake", temperature=0, max_tokens=128)
