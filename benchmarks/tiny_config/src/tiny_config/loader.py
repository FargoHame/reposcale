from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    api_url: str
    debug: bool


def load_config(file_config: dict[str, object]) -> AppConfig:
    api_url = os.getenv("API_URL", str(file_config.get("api_url", "")))
    debug = bool(file_config.get("debug", False))

    return AppConfig(api_url=api_url, debug=debug)
