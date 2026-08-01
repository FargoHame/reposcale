# RepoScale

RepoScale is a controlled evaluation harness for comparing coding-agent behavior on the same repository tasks. The goal is to measure how harness design, retrieval, context management, traces, and validation affect agent reliability while keeping the model, task, repository, and budget fixed.

## Current Thesis

RepoScale compares a simple baseline coding-agent harness against a more engineered harness on the same task, repository, model, and budget. The goal is not just to measure whether a model can solve a task, but whether harness design improves reliability, context use, patch quality, and recovery from bad tool actions.

## Current Findings

| Finding | Evidence | Why it matters |
|---|---|---|
| The model often finds the right files. | ScanAPI, PyYAML, and tiny benchmarks all show relevant searches and reads. | Search is not the only bottleneck. |
| Baseline fails partly through invalid responses. | Baseline PyYAML had 4 invalid responses; baseline tiny cache had 3. | Plain ReAct JSON control is brittle. |
| Deep Agents reduces invalid responses. | Engineered tiny cache and PyYAML had 0 invalid responses. | Structured harnesses improve tool-call format. |
| Deep Agents can still get stuck. | ScanAPI and PyYAML engineered runs repeated failed `edit_file` calls. | We need loop-control guardrails, not just more recursion. |
| Guardrails expose the next bottleneck. | After adding repeated-edit guardrails, PyYAML no longer repeated failed edits, but over-read `scanner.py` without editing. | Loop control must cover repeated reads and phase transitions too. |
| Read-stall guardrails change behavior but do not solve exact edit failures. | The latest PyYAML engineered run emitted read-stall warnings, then attempted edits, but those edits still failed because the replacement strings did not match. | The next harness improvement should help the agent make reliable edits from the current file region. |
| Line-range edits improve patch mechanics. | The latest PyYAML engineered run used `replace_line_range` and produced a focused, syntactically clean patch. | The harness can reduce edit-tool friction once the model has line numbers. |
| Semantic localization is now the bottleneck on PyYAML. | The line-range patch changed `scan_plain_spaces`, but validation still failed at the scanner's token boundary handling. | The next harness improvement should extract better failure evidence from validation and point the agent to the responsible phase. |
| Validation evidence makes failures easier to audit. | PyYAML still failed after validation summaries, but reports now surface the exact headline: trailing tab still raises `ScannerError` while scanning for the next token. | This gives the agent and evaluator a cleaner signal than raw stdout alone. |
| Static checkers can overstate success. | The latest ScanAPI engineered run passed the checker, but the diff duplicated imports/decorators and looked structurally broken. | We need stronger evals that run representative tests or inspect patch quality, not only static migration markers. |
| Patch-quality warnings catch suspicious passes. | ScanAPI still reports `passed`, but detailed reports now flag duplicate imports and decorators in the patch. | This separates task-check success from human-review risk. |
| The harness changes generalize on a fresh local task. | The new tiny serialization benchmark passed with 10 model calls, 9 tool calls, no invalid responses, and a one-file patch. | The line/edit/context improvements are not only PyYAML-specific. |
| Clean pass is now separate from pass. | Eval artifacts record `quality_status` and `clean_pass`, so a static-check pass with patch warnings is not treated like a clean test pass. | This gives batch benchmarks a more honest success metric. |
| Compact context search helps retrieval, but not editing discipline by itself. | `search_context` gave agents numbered snippets around matches, and tiny API clean-passed, but PyYAML and ScanAPI still failed after bad edit loops. | Large-repo context engineering needs retrieval, edit planning, and loop control together. |
| Patch quality now catches repeated generated code. | The latest PyYAML engineered run is marked `warning` because the diff added `length += 1` repeatedly. | Evaluations should expose pathological patches even when syntax is valid. |
| Patch quality can improve with engineered context. | Tiny cache engineered changed 1 file and 1 line; baseline artifact showed noisier historical patch stats. | Harnesses can improve patch focus. |

## Latest Experiment Results

These reports can be reproduced locally after running the benchmark setup scripts and agent runs. The JSON artifacts live under `runs/` and `evals/`; they are ignored by Git because they are generated run outputs.

| Task | Agent | Run | Eval | Model calls | Tool calls | Invalid | Tool errors | Repeated calls | Repeated errors | Context stalls | Files changed | Run seconds |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `tiny-cache-invalidation` | baseline | completed | passed | 11 | 6 | 3 | 1 | 0 | 0 | 0 | 5 | 36.59 |
| `tiny-cache-invalidation` | engineered | completed | passed | 10 | 9 | 0 | 0 | 1 | 0 | 0 | 1 | 24.65 |
| `scanapi-pytest-freezegun-migration` | baseline | failed | failed | 20 | 11 | 9 | 0 | 0 | 0 | 0 | 0 | 239.11 |
| `scanapi-pytest-freezegun-migration` | engineered | failed | failed | 120 | 120 | 0 | 103 | 99 | 98 | 5 | 0 | 707.16 |
| `scanapi-pytest-freezegun-migration` | engineered + current harness | completed | passed | 23 | 22 | 0 | 1 | 1 | 0 | 1 | 3 | 47.49 |
| `scanapi-pytest-freezegun-migration` | engineered + search context | failed | failed | 110 | 110 | 0 | 73 | 69 | 60 | 56 | 4 | 206.69 |
| `pyyaml-trailing-tab-plain-scalar` | baseline | failed | failed | 24 | 16 | 4 | 4 | 2 | 0 | 0 | 1 | 138.10 |
| `pyyaml-trailing-tab-plain-scalar` | engineered | failed | failed | 90 | 90 | 0 | 59 | 58 | 57 | 15 | 1 | 344.36 |
| `pyyaml-trailing-tab-plain-scalar` | engineered + edit guardrail | failed | failed | 60 | 60 | 0 | 1 | 7 | 0 | 52 | 0 | 438.90 |
| `pyyaml-trailing-tab-plain-scalar` | engineered + edit/read guardrails | failed | failed | 60 | 60 | 0 | 16 | 12 | 4 | 19 | 0 | 314.46 |
| `pyyaml-trailing-tab-plain-scalar` | engineered + line-range helper | failed | failed | 30 | 30 | 0 | 6 | 4 | 0 | 14 | 1 | 79.78 |
| `pyyaml-trailing-tab-plain-scalar` | engineered + validation evidence | failed | failed | 30 | 30 | 0 | 8 | 2 | 0 | 16 | 1 | 85.75 |
| `pyyaml-trailing-tab-plain-scalar` | engineered + search context/no-op feedback | failed | failed | 120 | 120 | 0 | 5 | 77 | 0 | 12 | 1 | 227.20 |
| `tiny-api-client-pagination` | engineered + search context | completed | passed | 11 | 10 | 0 | 1 | 0 | 0 | 0 | 1 | 49.30 |
| `tiny-serialization-score-keys` | engineered + current harness | completed | passed | 10 | 9 | 0 | 0 | 1 | 0 | 0 | 1 | 52.82 |

## Verify Locally

Render the latest report for a task:

```powershell
uv run reposcale report --latest --task tiny-cache-invalidation --details
uv run reposcale report --latest --task scanapi-pytest-freezegun-migration --details
uv run reposcale report --latest --task pyyaml-trailing-tab-plain-scalar --details
uv run reposcale report --latest --task tiny-serialization-score-keys --details
uv run reposcale report --latest --task tiny-api-client-pagination --details
```

Set up external benchmark checkouts:

```powershell
.\scripts\setup_scanapi.ps1
.\scripts\setup_pyyaml.ps1
```

Run the test suite:

```powershell
uv run pytest
```

## Next Milestone

Milestone 23 adds compact numbered context search, no-op edit feedback, and repeated-line patch-quality warnings. The reruns show that retrieval improved on a small task, but larger external tasks still need stronger edit-loop control and validation-driven planning.
