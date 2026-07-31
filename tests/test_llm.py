from __future__ import annotations

from reposcale.llm import extract_message_text, tool_schemas


def test_extract_message_text_reads_plain_content() -> None:
    assert extract_message_text({"content": "hello"}) == "hello"


def test_extract_message_text_converts_native_tool_call() -> None:
    message = {
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "list_files",
                    "arguments": '{"path": "."}',
                }
            }
        ],
    }

    assert extract_message_text(message) == '{"tool": "list_files", "input": {"path": "."}}'


def test_openrouter_tools_include_baseline_tool_schemas() -> None:
    tool_names = [tool["function"]["name"] for tool in tool_schemas()]

    assert tool_names == ["list_files", "read_file", "search_text", "write_file", "run_command"]
