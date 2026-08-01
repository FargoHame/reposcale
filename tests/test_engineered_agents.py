from __future__ import annotations

from reposcale.engineered_agents import (
    GuardedFilesystemBackend,
    replace_file_line_range,
    run_engineered_agent,
    to_langchain_model_name,
    trace_from_deepagents_result,
)
from reposcale.schemas import ModelConfig


class FakeAIMessage:
    def __init__(self, content: str, tool_calls: list[dict[str, object]] | None = None) -> None:
        self.content = content
        self.tool_calls = tool_calls or []


class FakeToolMessage:
    def __init__(
        self,
        content: str,
        name: str = "read_file",
        status: str = "success",
        tool_call_id: str = "",
    ) -> None:
        self.content = content
        self.name = name
        self.status = status
        self.tool_call_id = tool_call_id


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
                        "id": "call-1",
                        "args": {"file_path": "/pyproject.toml"},
                    }
                ],
            ),
            FakeToolMessage("file content", name="read_file", tool_call_id="call-1"),
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
    assert trace[2].tool_input == {"file_path": "/pyproject.toml"}


def test_engineered_agent_records_recursion_limit_on_failure(monkeypatch, tmp_path) -> None:
    class FakeAgent:
        def stream(self, *args, **kwargs):
            yield {"messages": [FakeAIMessage("working")]}
            raise RuntimeError("recursion failed")

    monkeypatch.setattr("reposcale.engineered_agents.create_agent", lambda task, model: FakeAgent())

    result = run_engineered_agent(make_task(tmp_path), make_model(), max_steps=2, recursion_limit=123)

    assert result.status == "failed"
    assert result.trace[-1].event_type == "model_error"
    assert result.trace[-1].metadata["recursion_limit"] == 123
    assert result.trace[0].event_type == "model_response"


def test_guarded_filesystem_backend_warns_after_repeated_failed_edit(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("value = 1\n", encoding="utf-8")
    backend = GuardedFilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    first = backend.edit("/example.py", "missing", "replacement")
    second = backend.edit("/example.py", "missing", "replacement")

    assert first.error is not None
    assert "GUARDRAIL" not in first.error
    assert second.error is not None
    assert "GUARDRAIL" in second.error


def test_guarded_filesystem_backend_warns_after_many_reads_without_edit(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("value = 1\n", encoding="utf-8")
    backend = GuardedFilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    result = None
    for _ in range(9):
        result = backend.read("/example.py")

    assert result is not None
    assert result.file_data is not None
    assert "GUARDRAIL" in result.file_data["content"]


def test_guarded_filesystem_backend_blocks_repeated_search_context_without_edit(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("value = 1\n", encoding="utf-8")
    backend = GuardedFilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    result = None
    for _ in range(9):
        result = backend.grep("value")

    assert result is not None
    assert result.error is not None
    assert "replace_line_range" in result.error


def test_guarded_filesystem_backend_resets_read_guardrail_after_edit(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("value = 1\n", encoding="utf-8")
    backend = GuardedFilesystemBackend(root_dir=tmp_path, virtual_mode=True)

    for _ in range(8):
        backend.read("/example.py")
    backend.edit("/example.py", "value = 1", "value = 2")
    result = backend.read("/example.py")

    assert result.file_data is not None
    assert "GUARDRAIL" not in result.file_data["content"]


def test_replace_file_line_range_replaces_inclusive_lines(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = replace_file_line_range(tmp_path, "/example.py", 2, 2, "TWO")

    assert result == "replaced lines 2-2 in /example.py"
    assert path.read_text(encoding="utf-8") == "one\nTWO\nthree\n"


def test_replace_file_line_range_preserves_single_line_indentation_by_default(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("if ready:\n    value = 1\n", encoding="utf-8")

    replace_file_line_range(tmp_path, "example.py", 2, 2, "      value = 2")

    assert path.read_text(encoding="utf-8") == "if ready:\n    value = 2\n"


def test_replace_file_line_range_rebases_multiline_indentation_by_default(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("while ready:\n    old_call()\n", encoding="utf-8")

    replace_file_line_range(tmp_path, "example.py", 1, 2, "  while ready:\n      new_call()")

    assert path.read_text(encoding="utf-8") == "while ready:\n    new_call()\n"


def test_replace_file_line_range_can_disable_indentation_preservation(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("if ready:\n    value = 1\n", encoding="utf-8")

    replace_file_line_range(
        tmp_path,
        "example.py",
        2,
        2,
        "value = 2",
        preserve_indentation=False,
    )

    assert path.read_text(encoding="utf-8") == "if ready:\nvalue = 2\n"


def test_replace_file_line_range_can_delete_lines(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("one\ntwo\nthree\n", encoding="utf-8")

    result = replace_file_line_range(tmp_path, "example.py", 2, 2, "")

    assert result == "replaced lines 2-2 in example.py"
    assert path.read_text(encoding="utf-8") == "one\nthree\n"


def test_replace_file_line_range_rejects_invalid_ranges(tmp_path) -> None:
    path = tmp_path / "example.py"
    path.write_text("one\n", encoding="utf-8")

    assert replace_file_line_range(tmp_path, "example.py", 0, 1, "x") == "error: start_line must be >= 1"
    assert replace_file_line_range(tmp_path, "example.py", 2, 1, "x") == "error: end_line must be >= start_line"
    assert replace_file_line_range(tmp_path, "example.py", 1, 2, "x") == "error: end_line 2 is past file length 1"


def test_replace_file_line_range_rejects_paths_outside_repo(tmp_path) -> None:
    outside = tmp_path.parent / "outside.py"

    try:
        replace_file_line_range(tmp_path, f"../{outside.name}", 1, 1, "x")
    except ValueError as error:
        assert "path escapes task repo" in str(error)
    else:
        raise AssertionError("expected path escape rejection")


def make_task(repo_path):
    from reposcale.schemas import TaskSpec

    return TaskSpec(
        task_id="engineered-test",
        title="Engineered test",
        repo_path=repo_path,
        problem_statement="Fix it.",
        test_command=None,
    )


def make_model() -> ModelConfig:
    return ModelConfig(provider="mistral", model="devstral-latest", temperature=0)
