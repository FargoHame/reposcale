from __future__ import annotations

from tiny_config import load_config


def test_load_config_uses_file_values_by_default(monkeypatch) -> None:
    monkeypatch.delenv("API_URL", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)

    config = load_config({"api_url": "https://file.example", "debug": True})

    assert config.api_url == "https://file.example"
    assert config.debug is True


def test_environment_values_override_file_values(monkeypatch) -> None:
    monkeypatch.setenv("API_URL", "https://env.example")
    monkeypatch.setenv("DEBUG", "false")

    config = load_config({"api_url": "https://file.example", "debug": True})

    assert config.api_url == "https://env.example"
    assert config.debug is False
