from __future__ import annotations

from tiny_api_client import ApiClient, Page


class FakeTransport:
    def __init__(self, pages: dict[str | None, Page]) -> None:
        self.pages = pages
        self.seen_cursors: list[str | None] = []

    def fetch_items(self, cursor: str | None = None) -> Page:
        self.seen_cursors.append(cursor)
        return self.pages[cursor]


def test_list_items_returns_single_page() -> None:
    transport = FakeTransport({None: Page(items=["alpha", "beta"])})
    client = ApiClient(transport)

    assert client.list_items() == ["alpha", "beta"]
    assert transport.seen_cursors == [None]


def test_list_items_follows_next_cursor_until_exhausted() -> None:
    transport = FakeTransport(
        {
            None: Page(items=["alpha"], next_cursor="page-2"),
            "page-2": Page(items=["beta"], next_cursor="page-3"),
            "page-3": Page(items=["gamma"]),
        }
    )
    client = ApiClient(transport)

    assert client.list_items() == ["alpha", "beta", "gamma"]
    assert transport.seen_cursors == [None, "page-2", "page-3"]
