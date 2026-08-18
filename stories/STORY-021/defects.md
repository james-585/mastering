# STORY-021 — Defects

## Open issues
- None.

## Architectural disposition
- Accepted as-is: the runtime optimization remains confined to the Demucs execution boundary and does not alter the mastering DSP path.
- Accepted as-is: CUDA/MPS preference and explicit CPU fallback are consistent with the local-only, CLI-first project constraints.
- Accepted as-is: the singleton model cache is keyed by model/device/config fingerprint and rejects incompatible config reuse.
- Accepted as-is: the runtime preserves backend-init error context in the fallback report rather than silently hiding it.

## QA summary
- Validation executed: `c:/Users/james/Documents/suno-mastering/stories/STORY-021/implementation/test_demucs_runtime.py`
- Command used: `$env:PYTHONPATH = "stories/STORY-021/implementation"; cd "c:\Users\james\Documents\suno-mastering"; python -m pytest stories/STORY-021/implementation/test_demucs_runtime.py`
- Result: `7 passed in 0.06s`
- QA disposition: no unresolved defect remains open for Story 021.

## Active workflow QA — 2026-08-17
- Focused command: `python -m pytest stories/STORY-021/automation/test_story021_active_runtime.py -q`
- Focused result: `10 passed in 1.11s`.
- Regression command: `python -m pytest stories/STORY-001/implementation/tests/test_story008_stem_separation.py -m "not slow" -q`
- Regression result: `11 passed, 2 deselected in 0.51s`.
- Combined command: `python -m pytest stories/STORY-020/automation stories/STORY-021/automation stories/STORY-022/automation -q`
- Combined result: `34 passed in 1.26s`.
- Evidence: injected capability and inference objects verify CUDA/MPS/CPU preference, cache hits across run-only changes, model/device cache isolation, one-shot CPU fallback, strict mode, malformed-output non-fallback, and runtime provenance.
- Release limitation: fake capabilities do not establish real accelerator performance, CPU/accelerator equivalence, or musical transparency.
- Defect assignment: none; no active-workflow failure was observed.
