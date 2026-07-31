from __future__ import annotations

from tiny_cache import MetricStore


def test_total_sums_current_values() -> None:
    store = MetricStore()
    store.set_value("alpha", 2)
    store.set_value("beta", 3)

    assert store.total() == 5


def test_total_updates_after_value_changes() -> None:
    store = MetricStore()
    store.set_value("alpha", 2)
    assert store.total() == 2

    store.set_value("beta", 3)

    assert store.total() == 5
