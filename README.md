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
| Patch quality can improve with engineered context. | Tiny cache engineered changed 1 file and 1 line; baseline artifact showed noisier historical patch stats. | Harnesses can improve patch focus. |

## Latest Experiment Results

These reports can be reproduced locally after running the benchmark setup scripts and agent runs. The JSON artifacts live under `runs/` and `evals/`; they are ignored by Git because they are generated run outputs.

| Task | Agent | Run | Eval | Model calls | Tool calls | Invalid | Tool errors | Repeated calls | Files changed | Run seconds |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| `tiny-cache-invalidation` | baseline | completed | passed | 11 | 6 | 3 | 1 | 0 | 5 | 36.59 |
| `tiny-cache-invalidation` | engineered | completed | passed | 10 | 9 | 0 | 0 | 1 | 1 | 24.65 |
| `scanapi-pytest-freezegun-migration` | baseline | failed | failed | 20 | 11 | 9 | 0 | 0 | 0 | 239.11 |
| `scanapi-pytest-freezegun-migration` | engineered | failed | failed | 120 | 120 | 0 | 103 | 99 | 0 | 707.16 |
| `pyyaml-trailing-tab-plain-scalar` | baseline | failed | failed | 24 | 16 | 4 | 4 | 2 | 1 | 138.10 |
| `pyyaml-trailing-tab-plain-scalar` | engineered | failed | failed | 90 | 90 | 0 | 59 | 58 | 1 | 344.36 |
| `pyyaml-trailing-tab-plain-scalar` | engineered + edit guardrail | failed | failed | 60 | 60 | 0 | 1 | 7 | 0 | 438.90 |

## Verify Locally

Render the latest report for a task:

```powershell
uv run reposcale report --latest --task tiny-cache-invalidation --details
uv run reposcale report --latest --task scanapi-pytest-freezegun-migration --details
uv run reposcale report --latest --task pyyaml-trailing-tab-plain-scalar --details
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

Milestone 13 adds loop-control guardrails. The harness detects repeated failed edit actions and changes the tool error feedback so the agent is told to stop repeating the same replacement and switch strategy. The next guardrail should detect repeated context reads without a patch attempt and force an edit-or-validate phase transition.
