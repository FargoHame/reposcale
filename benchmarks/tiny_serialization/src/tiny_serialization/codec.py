from __future__ import annotations

import json
from typing import Any


def encode_record(record: dict[str, Any]) -> str:
    return json.dumps(record, sort_keys=True)


def decode_record(payload: str) -> dict[str, Any]:
    return json.loads(payload)
