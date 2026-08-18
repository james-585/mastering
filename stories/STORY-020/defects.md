# STORY-020 — Defects

## Open issues
- None.

## DEF-020-01
Status: Closed
Reported by: qa-automation-engineer
Linked test case: TC-020-02
Description:
The initial implementation raised a raw `ValueError` for invalid profile inputs instead of returning a benchmark result with a rejection status. This violated the story contract, which requires unstable or invalid configurations to be rejected in a report-visible way without crashing the benchmark step.

Triage: Code-level
Fix notes:
The benchmark path now catches invalid configuration errors and returns a structured result with `status="rejected"` and a failure reason instead of propagating a Python exception. The validation covers invalid shift count, overlap, and segment-length constraints while preserving deterministic reporting for valid profiles.

## DEF-020-02
Status: Closed
Reported by: qa-automation-engineer
Linked test case: TC-020-01 through TC-020-04
Description:
The Story 020 benchmark contract was initially incomplete because the repository lacked the explicit implementation and QA evidence required for profiling-auditable output, default-selection behavior, and repeated-run determinism.

Triage: Code-level
Fix notes:
The Story 020 harness provides an explicit `benchmark_demucs_config()` result schema, records runtime and peak memory, emits an artifact score, and supports default profile selection via `select_default_demucs_profile()`. The implementation is explicit, versioned, and passes the focused pytest regression suite for the story.

## Architectural disposition
- Accepted as-is: the tuning remains strictly at the Demucs inference boundary and does not alter the mastering DSP chain.
- Accepted as-is: runtime, memory, and artifact metrics are explicit and auditable outputs in the benchmark result schema.
- Accepted as-is: unstable or unsafe profiles are rejected before default selection.

## QA summary
- Validation executed: `c:/Users/james/Documents/suno-mastering/.venv/Scripts/python.exe -m pytest stories/STORY-020/implementation/tests/test_demucs_tuning.py -q`
- Result: `4 passed in 0.11s`
- QA disposition: no unresolved defect remains open for Story 020.

## Active workflow QA — 2026-08-17
- Focused command: `python -m pytest stories/STORY-020/automation/test_story020_active_workflow.py -q`
- Focused result: `9 passed in 1.15s`.
- Combined command: `python -m pytest stories/STORY-020/automation stories/STORY-021/automation stories/STORY-022/automation -q`
- Combined result: `34 passed in 1.26s`.
- Evidence: injected Torch/model/loader/apply tests verify exact run-only kwargs, profile metadata, validation before model loading, nested JSON/CLI precedence, profile-version enforcement, and input-byte preservation.
- Release limitation: Demucs is absent, so no tuning, repeatability, runtime, memory, artifact-quality, or programme-material claim was inferred from fake dependencies.
- Defect assignment: none; no active-workflow failure was observed.
