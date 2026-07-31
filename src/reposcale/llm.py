from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from reposcale.schemas import ModelConfig


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


class LlmError(RuntimeError):
    pass


class OpenRouterClient:
    def __init__(self, api_key: str, site_url: str | None = None, app_name: str = "RepoScale") -> None:
        self._api_key = api_key
        self._site_url = site_url
        self._app_name = app_name

    def chat(self, messages: list[dict[str, str]], model: ModelConfig) -> str:
        body: dict[str, Any] = {
            "model": model.model,
            "messages": messages,
            "temperature": model.temperature,
            "tools": tool_schemas(),
        }
        if model.max_tokens is not None:
            body["max_tokens"] = model.max_tokens

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Title": self._app_name,
        }
        if self._site_url:
            headers["HTTP-Referer"] = self._site_url

        request = urllib.request.Request(
            OPENROUTER_URL,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise OpenRouterError(f"OpenRouter request failed with HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise OpenRouterError(f"OpenRouter request failed: {error.reason}") from error

        choices = payload.get("choices") or []
        if not choices:
            raise OpenRouterError("OpenRouter response did not include any choices")

        message = choices[0].get("message") or {}
        return extract_message_text(message)


class MistralClient:
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def chat(self, messages: list[dict[str, str]], model: ModelConfig) -> str:
        body: dict[str, Any] = {
            "model": model.model,
            "messages": messages,
            "temperature": model.temperature,
            "tools": tool_schemas(),
        }
        if model.max_tokens is not None:
            body["max_tokens"] = model.max_tokens

        request = urllib.request.Request(
            MISTRAL_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise LlmError(f"Mistral request failed with HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise LlmError(f"Mistral request failed: {error.reason}") from error

        choices = payload.get("choices") or []
        if not choices:
            raise LlmError("Mistral response did not include any choices")

        message = choices[0].get("message") or {}
        try:
            return extract_message_text(message)
        except OpenRouterError as error:
            raise LlmError(str(error)) from error


def create_llm_client(model: ModelConfig) -> OpenRouterClient | MistralClient:
    if model.provider == "openrouter":
        return OpenRouterClient(
            load_openrouter_api_key(),
            site_url="https://github.com/FargoHame/reposcale",
            app_name="RepoScale",
        )
    if model.provider == "mistral":
        return MistralClient(load_mistral_api_key())
    raise LlmError(f"unsupported model provider: {model.provider}")


def load_openrouter_api_key(env_path: Path = Path(".env")) -> str:
    existing = os.environ.get("OPENROUTER_API_KEY")
    if existing:
        return existing

    if env_path.exists():
        value = read_env_value(env_path, "OPENROUTER_API_KEY")
        if value:
            return value

    raise OpenRouterError("OPENROUTER_API_KEY is not set")


def load_mistral_api_key(env_path: Path = Path(".env")) -> str:
    existing = os.environ.get("MISTRAL_API_KEY")
    if existing:
        return existing

    if env_path.exists():
        value = read_env_value(env_path, "MISTRAL_API_KEY")
        if value:
            return value

    raise LlmError("MISTRAL_API_KEY is not set")


def read_env_value(env_path: Path, key: str) -> str | None:
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", maxsplit=1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def extract_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str) and content:
        return content

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        if parts:
            return "\n".join(parts)

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list) and tool_calls:
        first_call = tool_calls[0]
        if isinstance(first_call, dict):
            function = first_call.get("function")
            if isinstance(function, dict):
                name = function.get("name")
                arguments = function.get("arguments")
                if isinstance(name, str):
                    return json.dumps({"tool": name, "input": parse_tool_arguments(arguments)})

    raise OpenRouterError("OpenRouter response did not include text content")


def parse_tool_arguments(arguments: object) -> dict[str, object]:
    if isinstance(arguments, dict):
        return arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files under a relative directory in the task repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative directory path.", "default": "."}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read one UTF-8 text file from the task repository.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "description": "Relative file path."}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_text",
                "description": "Search text in files under the task repository.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "Text to search for."}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Replace a file with complete UTF-8 text content.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative file path."},
                        "content": {"type": "string", "description": "Complete replacement file content."},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Run a shell command in the task repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to run."},
                        "timeout_seconds": {"type": "number", "description": "Timeout in seconds.", "default": 30},
                    },
                    "required": ["command"],
                },
            },
        },
    ]
