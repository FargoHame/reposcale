from __future__ import annotations


def main() -> int:
    import yaml

    source = "test:\n  - foo \t\n  - bar\n"
    try:
        parsed = yaml.safe_load(source)
    except Exception as error:
        print(f"expected trailing tab after plain scalar to parse, got {type(error).__name__}: {error}")
        return 1

    if parsed != {"test": ["foo", "bar"]}:
        print(f"expected {{'test': ['foo', 'bar']}}, got {parsed!r}")
        return 1

    print("PyYAML trailing-tab plain scalar check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
