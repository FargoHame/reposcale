from __future__ import annotations

from reposcale.engineered_agents import to_langchain_model_name, trace_from_deepagents_result
from reposcale.schemas import ModelConfig


class FakeAIMessage:
    def __init__(self, content: str, tool_calls: list[dict[str, object]] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class FakeToolMessage:
    def __init__(self, content: str, name: str = "read_file", status: str = "success") -> None:
        self.content = content
        self.name = name
        self.status = status


FakeAIMessage.__name__ = "AIMessage"
FakeToolMessage.__name__ = "ToolMessage"


def test_mistral_model_maps_to_langchain_provider(monkeypatch) -> None:
    monkeypatch.setenv("MISTRAL_API_KEY", "test-key")
    model = ModelConfig(provider="mistral", model="devstral-latest", temperature=0)

    assert to_langchain_model_name(model) == "mistralai:devstral-latest"


def test_engineered_agent_rejects_unsupported_provider() -> None:
    model = ModelConfig(provider="openrouter", model="example/free", temperature=0)

    try:
        to_langchain_model_name(model)
    except ValueError as error:
        assert "only supports provider=mistral" in str(error)
    else:
        raise AssertionError("expected provider rejection")


def test_trace_from_deepagents_result_counts_tool_requests_once() -> None:
    result = {
        "messages": [
            FakeAIMessage(
                "",
                tool_calls=[
                    {
                        "name": "read_file",
                        "args": {"file_path": "/pyproject.toml"},
                    }
                ],
            ),
            FakeToolMessage("file content", name="read_file"),
            FakeAIMessage("done"),
        ]
    }

    trace = trace_from_deepagents_result(result)

    assert [event.event_type for event in trace] == [
        "model_response",
        "tool_call",
        "tool_result",
        "model_response",
        "agent_final",
    ]
    assert trace[1].tool_name == "read_file"
    assert trace[1].tool_input == {"file_path": "/pyproject.toml"}
