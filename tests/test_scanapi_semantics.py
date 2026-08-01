from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


def load_checker():
    script_path = Path(__file__).parents[1] / "scripts" / "check_scanapi_freezegun_semantics.py"
    spec = importlib.util.spec_from_file_location("check_scanapi_freezegun_semantics", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semantic_checker_rejects_travel_start_values() -> None:
    checker = load_checker()
    tree = ast.parse(
        """
from time_machine import travel

def context():
    return {"now": travel("2020-05-12 11:32:34").start()}
"""
    )

    failures = checker.check_travel_start_values(tree, "tests/unit/test_reporter.py")

    assert failures == [
        "tests/unit/test_reporter.py: line 5: travel(...).start() returns a traveler, not the frozen datetime value"
    ]


def test_semantic_checker_allows_travel_context_manager() -> None:
    checker = load_checker()
    tree = ast.parse(
        """
from time_machine import travel

def test_return_time():
    with travel("2020-06-15 18:54:57") as t:
        t.move_to("2020-06-15 18:56:38")
"""
    )

    assert checker.check_travel_start_values(tree, "tests/unit/test_session.py") == []


def test_semantic_checker_rejects_string_now_context_value() -> None:
    checker = load_checker()
    tree = ast.parse(
        """
def context():
    return {"now": "2020-05-12 11:32:34"}
"""
    )

    failures = checker.check_now_is_not_string_literal(tree, "tests/unit/test_reporter.py")

    assert failures == [
        "tests/unit/test_reporter.py: line 3: context['now'] must stay datetime-like, not a string"
    ]
