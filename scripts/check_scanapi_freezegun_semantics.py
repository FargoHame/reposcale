from __future__ import annotations

import ast
from pathlib import Path


def main() -> int:
    repo = Path.cwd()
    failures: list[str] = []

    reporter = parse(repo / "tests" / "unit" / "test_reporter.py", failures)
    session = parse(repo / "tests" / "unit" / "test_session.py", failures)

    if reporter is not None:
        failures.extend(check_bad_time_machine_imports(reporter, "tests/unit/test_reporter.py"))
        failures.extend(check_bad_time_machine_marks(reporter, "tests/unit/test_reporter.py"))
        failures.extend(check_travel_start_values(reporter, "tests/unit/test_reporter.py"))
        failures.extend(check_now_is_not_string_literal(reporter, "tests/unit/test_reporter.py"))
    if session is not None:
        failures.extend(check_bad_time_machine_imports(session, "tests/unit/test_session.py"))
        failures.extend(check_bad_time_machine_marks(session, "tests/unit/test_session.py"))
        failures.extend(check_shadowed_travel_fixture(session, "tests/unit/test_session.py"))
        failures.extend(check_travel_start_values(session, "tests/unit/test_session.py"))

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("ScanAPI semantic migration checks passed.")
    return 0


def parse(path: Path, failures: list[str]) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    except SyntaxError as error:
        failures.append(f"{path.as_posix()}: python syntax error: {error.msg} at line {error.lineno}")
        return None


def check_bad_time_machine_imports(tree: ast.AST, label: str) -> list[str]:
    failures: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "time_machine":
            names = {alias.name for alias in node.names}
            if "FakeDatetime" in names:
                failures.append(f"{label}: time_machine does not provide FakeDatetime; use datetime or travel/time_machine APIs")
    return failures


def check_bad_time_machine_marks(tree: ast.AST, label: str) -> list[str]:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        if node.attr == "time_machine" and isinstance(node.value, ast.Name) and node.value.id == "mark":
            failures.append(f"{label}: @mark.time_machine is not a time-machine API")
    return failures


def check_shadowed_travel_fixture(tree: ast.AST, label: str) -> list[str]:
    failures: list[str] = []
    imports_travel = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "time_machine"
        and any(alias.name == "travel" for alias in node.names)
        for node in ast.walk(tree)
    )
    if not imports_travel:
        return failures

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if any(arg.arg == "travel" for arg in node.args.args):
            failures.append(f"{label}: function {node.name} shadows imported time_machine.travel with a parameter")
    return failures


def check_travel_start_values(tree: ast.AST, label: str) -> list[str]:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "start":
            continue
        receiver = node.func.value
        if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id == "travel":
            failures.append(
                f"{label}: line {node.lineno}: travel(...).start() returns a traveler, not the frozen datetime value"
            )
    return failures


def check_now_is_not_string_literal(tree: ast.AST, label: str) -> list[str]:
    failures: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values, strict=False):
            if not isinstance(key, ast.Constant) or key.value != "now":
                continue
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                failures.append(f"{label}: line {value.lineno}: context['now'] must stay datetime-like, not a string")
    return failures


if __name__ == "__main__":
    raise SystemExit(main())
