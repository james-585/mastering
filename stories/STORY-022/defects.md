# STORY-022 — Defects

## Open issues
- None. The explicit 6-stem contract is implemented and validated.

## Architectural disposition
- Accepted as-is: the optional `htdemucs_6s` branch is treated as a distinct model path rather than a hidden replacement of the existing four-stem flow.
- Accepted as-is: `piano` and `guitar` are explicit semantic outputs and are not silently collapsed into `other`.
- Accepted as-is: the validation contract enforces the complete 6-stem bundle and rejects partial/incomplete outputs before hand-off to mastering.
- Accepted as-is: recombination remains deterministic and identity-safe under a strict tolerance, while preserving float64 handling and explicit safety checks.
- QA validation executed: `python -m pytest stories/STORY-022/implementation/test_story022_6stem.py -q` passed with 4/4 tests green.

## Active workflow QA — 2026-08-17
- Focused command: `python -m pytest stories/STORY-022/automation/test_story022_active_stems.py -q`
- Focused result: `15 passed in 1.15s`.
- Regression command: `python -m pytest stories/STORY-001/implementation/tests/test_story008_stem_separation.py -m "not slow" -q`
- Regression result: `11 passed, 2 deselected in 0.51s`.
- Combined command: `python -m pytest stories/STORY-020/automation stories/STORY-021/automation stories/STORY-022/automation -q`
- Combined result: `34 passed in 1.26s`.
- Evidence: injected four/six-source models verify explicit piano/guitar channels, alternate source-order mapping, all specified malformed bundle classes without fallback, uncorrected residual telemetry without stem mutation, and metadata propagation through preprocessing into JSON reports.
- Release limitation: fake models do not establish installed `htdemucs_6s` source compatibility, leakage, transient preservation, phase behavior, residual acceptability, or listening quality.
- Defect assignment: none; no active-workflow failure or internally inconsistent telemetry was observed.
