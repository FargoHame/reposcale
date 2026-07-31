from __future__ import annotations


class MetricStore:
    def __init__(self) -> None:
        self._values: dict[str, int] = {}
        self._total_cache: int | None = None

    def set_value(self, name: str, value: int) -> None:
        self._values[name] = value

    def total(self) -> int:
        if self._total_cache is None:
            self._total_cache = sum(self._values.values())
        return self._total_cache
