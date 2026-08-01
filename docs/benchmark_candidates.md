# Benchmark Candidates

These are candidate GitHub issues for broadening RepoScale beyond the current tiny tasks, PyYAML, and ScanAPI. They are not committed task specs yet. Each needs a pinned checkout, dependency setup, and deterministic validation before it becomes part of the benchmark suite.

| Candidate | Difficulty | Domain | Why it is useful | Validation shape |
|---|---|---|---|---|
| `pytest-dev/pytest#14514` dotted test filenames | easy | test discovery | Small likely-localized change; tests whether agents can find collection rules. | Add a dotted `*.test.py` fixture and assert pytest collects it. |
| `pytest-dev/pytest#14329` `get_closest_marker` behavior | medium | marker lookup | Exercises API behavior and fixture-style tests without huge dependency migrations. | Add regression around marker lookup precedence. |
| `pytest-dev/pytest#14445` walrus assertion rewrite | hard | AST/assertion rewriting | Tests deep semantic localization in compiler/AST transformation code. | Add assertion-rewrite regression that fails before fix. |
| `openai/openai-python#3312/#3314/#3321` Responses stream `output=None` crash | medium | streaming parser | Good for parser robustness and event-state handling. | Feed synthetic stream events and assert no `NoneType` iteration crash. |
| `openai/openai-python#3303` `NO_PROXY` with newline causes `InvalidURL` | easy-medium | env/config parsing | Compact config normalization problem, likely deterministic. | Unit test env var containing newline and assert client construction/request prep handles it. |
| `jsoncons#734` `json_schema` fails with `wjson` | medium-hard | C++ template/compile | Adds non-Python, compile-time failure coverage. | Build minimal C++ repro with `wjson` schema compile. |
| `jsoncons#590` test vectors not marked binary | easy-medium | test data/classification | Tests repo search and data-driven validation without deep algorithm changes. | Assert specific vectors are classified/marked correctly. |
| `OpenHands-CLI#786` SDK bump blocked by dependency pin | medium | dependency resolution | Similar to ScanAPI but with different repo and package metadata shape. | Update pins and run dependency metadata/lock validation. |
| `OpenHands-CLI#676` JSON flag emits invalid JSONL | medium | CLI output serialization | Very relevant to agent/eval tooling; checks output format rigor. | Run CLI command and parse each output line as JSON. |
| `apache/eventmesh#5233` HTTP connector JSON deserialization error | hard | Java integration/serialization | Broader stack and integration complexity. | Reproduce with connector payload and assert deserialization succeeds. |

## Selection Rule

Do not add a candidate just because it is interesting. Add it only when:

- setup can be pinned and automated
- validation can run without external services
- the task exercises a distinct failure mode
- the expected patch can be judged by tests plus patch-quality diagnostics

## Suggested First Expansion Set

1. `pytest-dev/pytest#14514` for easy test-discovery behavior.
2. `openai/openai-python#3303` for compact environment/config parsing.
3. `OpenHands-CLI#676` for CLI JSON output validity.
4. `pytest-dev/pytest#14445` for hard AST/semantic localization.
