# STORY-016 — Test cases: end-to-end pipeline integration and acceptance

## Test coverage

### TC-016-01 — Valid full pipeline run on a real Suno track
- Input: a real stereo Suno track at 44.1 kHz or 48 kHz.
- Mode: stem-first workflow with valid stem data when available.
- Steps:
  1. Run the orchestrator end-to-end.
  2. Confirm all stages appear in the audit output in the required order.
  3. Confirm the final output remains finite, float64-safe, and within the true-peak guardrail.
- Expected result: a final decision of pass, reject, or refine, plus a traceable audit record.

### TC-016-02 — Explicit fallback without hidden bypass
- Input: a stereo source with no valid stem payload.
- Mode: `use_stems=True` and `allow_stereo_fallback=True`.
- Steps:
  1. Invoke the orchestrator with `stems=None`.
  2. Confirm the recorded mode is `stereo_fallback`.
  3. Confirm the fallback is logged in the audit trail as a limited condition.
- Expected result: the pipeline continues and records the fallback instead of silently bypassing the required gates.

### TC-016-03 — Fallback rejection when not explicitly allowed
- Input: a stereo-only signal with no valid stems.
- Mode: `use_stems=True`, `allow_stereo_fallback=False`.
- Expected result: the orchestrator raises a `ValueError` indicating the fallback is disallowed.

### TC-016-04 — Stage ordering and traceability
- Input: a synthetic stereo signal and a valid stem dictionary.
- Steps:
  1. Run the orchestrator with known stem inputs.
  2. Check the audit sequence exactly matches: ingest, analysis, stem_choice, transient_restoration, harshness_control, stereo_imaging, bus_glue, final_safety, quality_review.
- Expected result: the stage order is stable and each stage includes a summary.

### TC-016-05 — Pass / reject / refine flow
- Input: one accepted signal and one clearly over-processed or weak signal.
- Steps:
  1. Run the orchestrator on a stable, musically improved synthetic mix.
  2. Run it on a weak or over-processed mix.
  3. Compare final decisions.
- Expected result: a meaningful pass case is accepted, while a weak result becomes reject or refine.

### TC-016-06 — Oversampled true-peak safety
- Input: a near-ceiling signal with a large transient.
- Steps:
  1. Feed a high-amplitude stereo signal into the final safety stage.
  2. Confirm the final apparent peak is measured using oversampling logic.
- Expected result: any excess peak triggers attenuation and the final output remains at or below the project ceiling.

### TC-016-07 — Export gate enforcement
- Input: a result that fails the final quality gate.
- Steps:
  1. Run the orchestrator with a poor-quality final output.
  2. Check the export flag and reason.
- Expected result: `export_allowed` is false and the output carries a documented rejection or refinement reason.

## Negative checks
- The orchestrator must not silently skip final safety or quality review.
- A fallback must never masquerade as a full stem-first master.
- The pipeline must not claim to reconstruct information absent from the source.
- A technically compliant but musically weak result must not be exported without an explicit override reason.
