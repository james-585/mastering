# STORY-025 — Requirements: Grounded quality validation — proving the master actually sounds better

## Contract
Consumes: `stories/STORY-015/implementation/final_quality_review.py` (`evaluate_quality_review`, `_summary_metrics`, `_spectral_tilt`, `_stereo_width`, `_true_peak`), `stories/STORY-017/implementation/real_world_validation.py` (`build_validation_report`, `ACCEPTED_PARAMETERS`), STORY-007's `ArtifactDetectionResult.overall_artifact_density_score` (`stories/STORY-001/implementation/suno_mastering/analysis/types.py`), the existing seven-band spectral analysis (`measure_seven_band_balance` in `stories/STORY-001/implementation/suno_mastering/analysis/seven_band_balance.py`), the existing TT DR-meter (`measure_dynamic_range` in `stories/STORY-001/implementation/suno_mastering/analysis/dynamic_range.py`), the existing BS.1770-4 integrated-LUFS measurement (`measure_integrated_lufs` in `stories/STORY-001/implementation/suno_mastering/analysis/loudness.py`), and the real Suno validation set already referenced by STORY-017 (`DEFAULT_VALIDATION_SET`).

Produces: a revised quality-review module whose pass/reject/refine verdict is computed from grounded, already-existing project measurements (seven-band spectral balance, TT DR / crest factor, artifact-density delta) instead of invented proxies; a LUFS-matching precondition enforced in code before any before/after delta is computed; a real (non-simulated) human-listening capture step with `human_decision`/`human_note` actually populated by a person; and an environment-verification step confirming real Demucs/Torch stem separation succeeds on a real file before stem-first validation results are trusted.

Consumed by: STORY-017 real-world validation re-run (as the replacement quality-review dependency); the release gate that currently reads `evaluate_quality_review` / `build_validation_report` output.

## Restated intent
The pipeline's pass/reject verdict must be backed by evidence that actually measures what it claims to measure, and by a real human listen — not by a loudness proxy mislabeled as "clarity," a 2-bin FFT ratio mislabeled as spectral tilt, an artifact-density measurement that exists but is never consulted, an unenforced level-matching rule, or auto-generated report prose standing in for a human judgment on an unvalidated stem-separation path.

## Grounding for each problem (source-cited, not paraphrased)

1. **Proxy metrics that don't measure what they claim.** In `final_quality_review.py`, `_summary_metrics()` computes `clarity_delta = mean(abs(proc)) - mean(abs(orig))` — this is a mean-absolute-amplitude (loudness-proxy) delta, not a clarity measurement, yet `evaluate_quality_review()` uses `clarity_gain` (bound to `clarity_delta`) as the primary signal for both `"dullness"` and `"pass"` branches. `_spectral_tilt()` computes `hi/lo` from only two crude FFT-bin-range means (`spec[:size//50]` vs `spec[size//10:]`), not the project's existing seven-band scheme (`measure_seven_band_balance`, which already produces per-band `relative_db` across seven bands against a reference band). `evaluate_quality_review()` must instead source its before/after delta from `measure_seven_band_balance` (spectral balance) and `measure_dynamic_range` (DR/crest-factor), reusing the existing project measurements rather than the ad hoc `_spectral_tilt`/`clarity_delta` proxies.

2. **`overall_artifact_density_score` never compared before/after.** `ArtifactDetectionResult.overall_artifact_density_score` (`analysis/types.py`) is a fully implemented 0.0–1.0 measurement (via `detect_artifacts`, wired into `measure_all()` per STORY-007 architecture §4.2) but neither `final_quality_review.py` nor `real_world_validation.py` calls `detect_artifacts` or reads this field anywhere. The verdict in `evaluate_quality_review()` must incorporate a before/after `overall_artifact_density_score` comparison as part of the pass/reject/refine decision.

3. **CLAUDE.md §6.3 LUFS-matching not enforced.** CLAUDE.md §6.3 states level-matching is mandatory before comparing a mastered result to a reference, because a target chosen for streaming/safety may sound quieter than the reference at unmatched levels. Neither `_summary_metrics()` nor `evaluate_quality_review()` measures or matches LUFS before computing `peak_delta_db`, `width_delta`, `spectral_tilt_delta`, or `clarity_delta` — the comparison is done directly on unmatched-level audio. This story must require that integrated LUFS (via `measure_integrated_lufs`) be measured for both `original` and `processed`, and that a level-matching step occur, as a precondition before any before/after delta feeding the verdict is computed.

4. **Auto-generated prose standing in for a real listen; stem-first path never run on real models.** `build_validation_report()` in `real_world_validation.py` constructs `summary`/`auditable_summary` and `tuning_decisions` text programmatically from the decision string (e.g. `"REJECT — real-world validation on {name}; the source remained musically weak..."`), and `QualityReviewResult.human_decision`/`human_note` in `final_quality_review.py` remain `None`/`""` unless a `human_review` dict is explicitly passed in — which the default `build_validation_report()` path never does. Per `memories/repo/suno-mastering-status.md` and the story background, Demucs/Torch are absent from the current working environment, so `pipeline.run(..., use_stems=True, allow_stereo_fallback=True)` in `build_validation_report()` has never been confirmed to actually exercise real stem separation rather than silently falling back to stereo-only. This story must require (a) an environment-verification step that confirms real Demucs/Torch stem separation succeeds on a real audio file before any stem-first validation result is trusted, and (b) that `human_decision`/`human_note` be actually set by a person for each validation file, with no default/templated value accepted as a substitute.

## Acceptance criteria

1. Given `original` and `processed` audio, when the quality review computes its before/after delta, then the spectral-balance component of that delta is produced by `measure_seven_band_balance` (or equivalent reuse of the seven-band scheme), not by `_spectral_tilt`.
2. Given `original` and `processed` audio, when the quality review computes its before/after delta, then the dynamics component of that delta is produced by `measure_dynamic_range` (TT DR) and/or an equivalent crest-factor measurement grounded in the existing DR implementation, not by `clarity_delta`.
3. Given the removal of `_spectral_tilt` and the `clarity_delta` proxy from the verdict logic, when the verdict is computed, then no new ad hoc metric is invented in their place — only the seven-band and DR/crest-factor measurements named above, plus artifact density (below), feed the decision.
4. Given `original` and `processed` audio, when the quality review runs, then `detect_artifacts` (or the equivalent existing artifact-detection entry point) is invoked on both, and the before/after change in `overall_artifact_density_score` is included as an explicit input to the pass/reject/refine decision.
5. Given `original` and `processed` audio at differing integrated LUFS, when the quality review is asked to compute a before/after delta, then it must first measure integrated LUFS for both (via `measure_integrated_lufs`) and perform level-matching before computing any spectral, DR, or artifact-density delta; a delta computed on unmatched levels must not be accepted as verdict evidence.
6. Given a request to compute a before/after delta where level-matching has not occurred, then the module must reject or refuse to proceed (fail loudly), not silently compute the delta on unmatched levels.
7. Given the real-world validation entry point (`build_validation_report()` or its successor), when it is run for the purpose of producing a trusted product verdict, then it must first perform an environment-verification step confirming that real Demucs/Torch stem separation completes successfully on a real audio file; if that verification fails, the validation run must report that the stem-first path is unverified rather than silently proceeding under stereo fallback.
8. Given a validation file processed through the pipeline, when the validation report is produced, then `human_decision` and `human_note` must reflect an actual person's listening judgment for that specific file; a report where these fields are `None`/empty, or where they are populated by templated/auto-generated text rather than a person's input, does not satisfy this story.
9. Given the existing `evaluate_quality_review(..., human_review=None)` default-parameter behavior, when this story is implemented, then the human-listening step must not remain an optional bypass in the real-world validation default path — `build_validation_report()`'s default invocation must not produce a final "trusted" verdict without a populated human review.

## Audio quality targets

- No new numeric thresholds are specified by this story. The seven-band, DR, artifact-density, and LUFS measurements already carry their own established methods/behavior from STORY-001/STORY-002/STORY-007; this story requires their reuse, not the invention of new pass/fail threshold values for width, tilt, or clarity.
- The specific decision boundaries (how much artifact-density increase is acceptable, how much DR change is acceptable, what constitutes a meaningful spectral-balance improvement) are architecture/mastering-engineer decisions — flagged as open questions below.

## Input/output assumptions

- Inputs: `original` and `processed` audio as float64 numpy arrays (mono or stereo), consistent with the existing `_as_float64` contract in `final_quality_review.py` and the plain-array `(np.ndarray, int)` contract used across `analysis/measure_all`.
- Sample-rate is required for `measure_seven_band_balance`, `measure_dynamic_range`, `measure_integrated_lufs`, and `detect_artifacts` — the current `evaluate_quality_review(original, processed, human_review=None)` signature does not accept a sample rate; this story requires the signature to be extended to carry `sr` (or an equivalent context object) since sample-rate-free operation is not possible for the replacement metrics.
- Output: the existing `QualityReviewResult` dataclass shape (`decision`, `summary`, `flags`, `before_after`, `human_decision`, `human_note`, `audit`) is retained as the reporting contract, with `before_after` populated from the new grounded metrics instead of the old proxy fields.
- The real-world validation set continues to be the existing `DEFAULT_VALIDATION_SET` (real Suno/reference files) from `real_world_validation.py`; this story does not introduce new validation files.

## Explicit out-of-scope

- Adding new corrective DSP processing stages (per Story.md scope).
- Changing loudness/DR/EQ targets or correction caps — that is STORY-006 territory.
- Cloud-based or automated perceptual-quality models (PEAQ/ViSQOL etc.) unless a later story justifies the dependency.
- Redesigning the artifact-detection detectors themselves (STORY-007 scope) — this story only requires their *comparison*, not changes to detection logic.
- Redesigning the seven-band or DR measurement implementations — this story only requires their *reuse*, not changes to their internals.

## Rejected as out of scope

- Any requirement implying the quality review can judge musical quality purely from metrics without the human-listening step described above — DOMAIN.md's constraint that mastering cannot substitute measurement for perceptual judgment on subjective qualities (fatigue, emotional contour) applies; metrics alone (even grounded ones) cannot replace the human-listening acceptance criterion.
- Any requirement implying the stem-first path can be declared validated without Demucs/Torch actually being present and exercised — a validation report produced entirely under stereo fallback must not claim to validate the stem-first product direction (CLAUDE.md §3).

## Non-functional requirements

- The environment-verification step (problem 4) must fail loudly and clearly (not silently fall back) if Demucs/Torch are unavailable, consistent with CLAUDE.md's "fail loudly" rule for invalid/incomplete state.
- Reproducibility: given identical `original`/`processed` inputs and sample rate, the grounded-metric portion of the verdict must be deterministic across runs (matching the existing determinism expectations for `measure_seven_band_balance`/`measure_dynamic_range`/artifact detection).
- The human-listening capture step must be auditable: it must be possible to distinguish, from the report, a run where a human actually reviewed and populated `human_decision`/`human_note` from one where the step was skipped or defaulted.
- No processing-speed or batch-size target is specified by the story; not invented here.

## Open questions

1. What decision logic (thresholds, combination rules) should replace the current if/elif chain in `evaluate_quality_review()` now that spectral-balance, DR, and artifact-density deltas are the inputs instead of `clarity_delta`/`_spectral_tilt`/`width_delta`? This is an architecture/mastering-engineer decision; no numeric threshold is assumed here.
2. What LUFS-matching tolerance or method (gain-match to common integrated LUFS, or some other convention) satisfies CLAUDE.md §6.3 in code? CLAUDE.md states the rule but does not specify a matching algorithm or tolerance — flagged for the architect.
3. What magnitude of `overall_artifact_density_score` change should be considered a meaningful regression vs. noise? Not specified anywhere in the codebase — flagged for the architect/mastering-engineer, since STORY-007 requirements only normalize the score 0.0–1.0 without defining a comparison delta.
4. Should `_stereo_width` and `_true_peak` (both already grounded, unlike `_spectral_tilt`/`clarity_delta`) remain in the verdict as supplementary evidence, or be fully superseded by the seven-band/DR/artifact-density set? The story's four named problems do not flag width or true-peak as wrong, so this needs explicit confirmation rather than assumption.
5. What is an acceptable/available mechanism for the environment-verification step to run real Demucs/Torch inference in this repo's environment given they are currently absent (per `memories/repo/suno-mastering-status.md`)? Is installing them in scope for this story, or does this story only define the verification contract for when they are eventually available? Flagged for the architect.
6. What interface should capture the human-listening step in practice (CLI prompt, structured input file, other) so that `human_decision`/`human_note` are genuinely populated by a person rather than defaulted? Not a requirements-level decision, but the mechanism needs an architecture answer before implementation.
7. Should this story require re-running STORY-017's `build_validation_report()` against the new quality-review module as part of its own acceptance, or is that deferred entirely to a separate re-invocation of STORY-017 (as the Contract's "Consumed by" line implies)? The story text says "consumed by: STORY-017 real-world validation re-run," but does not say whether that re-run is in-scope work for STORY-025 itself.

## Revision history
- 2026-08-17: Initial requirements.md written for STORY-025, grounded in `final_quality_review.py`, `real_world_validation.py`, STORY-007 architecture §4.2, STORY-017 requirements/gate1, and CLAUDE.md §6.3/§3.
