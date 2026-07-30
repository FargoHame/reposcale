from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Page:
    items: list[str]
    next_cursor: str | None = None


class Transport(Protocol):
    def fetch_items(self, cursor: str | None = None) -> Page:
        """Return one page of items from the API."""
