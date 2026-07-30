from __future__ import annotations

from tiny_api_client.types import Transport


class ApiClient:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list_items(self) -> list[str]:
        """Return all available items."""
        page = self._transport.fetch_items()
        return page.items
