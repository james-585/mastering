# STORY-013 — Architecture: stem-local stereo imaging and depth control

## Pipeline placement
Insert after harshness control and before final bus glue / loudness safety.

The order is:
1. ingest source and validate stem availability
2. optional stem separation (stem-first path)
3. stem analysis and issue detection
4. transient restoration per stem
5. harshness control / de-haze per stem
6. stem-local stereo imaging and depth control
7. final bus glue
8. loudness / true-peak safety
9. export and report

## Design decisions
- Width and depth are applied per stem, never as a whole-mix widening pass.
- The stage only operates on actual stereo headroom in the signal; no fake stereo generation is allowed.
- Center-stable sources such as kick, bass, and lead vocal are kept anchored and default to no-op.
- Ambience, synth, and pad stems may receive limited width increases where evidence supports it and where mono compatibility remains acceptable.
- The stage produces a structured audit record for each decision: stem name, before/after width, correlation, result, and rationale.

## Module boundaries
- Module: `stem_stereo_imaging.py`
- Public API: `apply_stem_stereo_imaging(stems: dict[str, np.ndarray], sample_rate: int) -> tuple[dict[str, np.ndarray], list[StemStereoAction]]`
- Helper functions:
  - `_as_float64()` — normalize arrays to float64 without resampling.
  - `_stereo_metrics()` — measure width and inter-channel correlation for each stem.
  - `_phase_guard()` — reject phase-unstable or anti-correlated content.
  - `_is_silent()` — no-op low-energy or silence cases.
  - `_stem_class()` — classify stems into center, wide, or neutral roles.
  - `_apply_width_boost()` — local side-channel widening within safe limits.
  - `_true_peak()` — oversampled true-peak check with 4x to 8x oversampling.

## Data contract
- Input arrays are float64, shaped as (samples,) or (samples, channels), with channels either 1 or 2.
- Stereo stems require channel-wise left/right analysis and must not be widened when correlation indicates phase instability.
- Mono or near-mono stems remain unchanged; only genuine stereo content may receive width increase.
- Output arrays retain the same shape, sample rate, and dtype as the input; integer conversion occurs only at final I/O boundaries.
- Every action record includes at minimum: stem name, action type, width_before, width_after, correlation, gain_db, and human-readable reason.

## Detailed algorithm
### 1. Stem ingestion and width analysis
- For each stem, normalise to float64 and detect whether the signal is mono, stereo, silent, or low-energy.
- For stereo stems, compute an evidence-based width metric and inter-channel correlation.
- If a stem is clearly mono-like or has insufficient stereo information, the stage returns it unchanged.

### 2. Mono-compatibility and correlation checks
- Measure the left-right relationship using inter-channel correlation.
- Reject phase-unstable or anti-correlated content before widening.
- Preserve mono compatibility as a hard requirement; do not widen a stem if the corrected result would reduce compatibility below a safe threshold.

### 3. Center-stability rules
- Kick, bass, and lead vocal stems are treated as center-stable by default.
- Their intervention path is no-op unless safety analysis indicates a problem or a specific design exception is justified.
- Center material must not be artificially widened to satisfy an overall mix target.

### 4. Local width adjustments and depth shaping per stem
- Ambience, synth, and pad stems may receive a small width increase when they have real stereo headroom and no phase issue.
- Depth shaping is done by local width adjustments only; the stage does not create a synthetic depth field or attempt full-bus widening.
- Width changes are intentionally conservative, small, and reversible through the report.

### 5. Safety checks for phase issues, clipping risk, and oversampling
- Anti-correlated or excessive phase mismatch is rejected with a ValueError and cannot be silently ignored.
- Peak risk is checked with a true-peak guard using oversampling, not sample peak.
- Any corrected stem that approaches clipping is blocked or attenuated before export.

### 6. Integration with current pipeline
- This stage sits after harshness control/de-haze and before final bus glue and loudness safety.
- It does not replace the bus glue stage or become a global widening pass.
- It is a local, stem-specific correction stage that reports its decisions transparently.

## Library choices
- `numpy` for float64 processing and stereo metrics.
- `scipy.signal.resample_poly` for true-peak oversampling checks.
- `soundfile` remains the permitted boundary I/O utility; no cloud services or GUI are introduced.
- No `librosa.load(..., sr=...)` path is allowed for in-memory processing or measurement logic.

## Implementation constraints
- All internal calculations use float64.
- The stage is a no-op when the stem is already stable or low-energy.
- The stage never claims to recover information that was never present.
- Widening is limited to the specific stem that needs it and is never a blanket mix decision.
- If a correction is not justified by evidence, it must not be applied.

## Guardrails
- No fake stereo generation from mono material.
- No blanket widening of the whole mix.
- No widening of kick, bass, or lead vocal without explicit, evidence-based justification.
- No phase-breaking expansion on unstable stems.
- No silent clipping; all risky outputs are rejected or attenuated.

## Architectural risks and mitigations
- Risk: A real stereo stem may still be phasey or poorly correlated, leading to unstable widening.
  - Mitigation: reject anti-correlated content and require mono/phase safety before width increase.
- Risk: A weak or silent stem could be widened by accident.
  - Mitigation: detect silence and low-energy conditions and return the stem unchanged.
- Risk: Over-processing can create artificial width or a “smiley-face stereo” effect.
  - Mitigation: keep width gain conservative and local, and require auditability for every action.

## Mastering-review disposition

### Action item 1 — Accepted as-is
- Finding: The story correctly requires local width treatment only where there is measurable stereo headroom and no phase issue.
- Architect decision: Accepted as-is.
- Reason: This matches the repo’s stem-first direction and avoids the known wrong patterns of blanket widening, fake stereo, and over-processed spatial effects.
- Implementation requirement: Keep the stage local, evidence-based, and conservative; center-stable stems remain unchanged by default.

### Action item 2 — Accepted as-is
- Finding: The architecture must keep stereo widening tied to real signal evidence and safe phase/mono compatibility checks.
- Architect decision: Accepted as-is.
- Reason: The repo requires signal honesty and explicit safety checks before any width increase is applied.
- Implementation requirement: Maintain mono/phase guards, oversampling-based true-peak safety, and report-visible action decisions.

## Revision history
- 2026-08-16: Initial Story 013 architecture drafted for a conservative, stem-local imaging stage with explicit safety, no-op, and auditability rules.
- 2026-08-16: Added mastering-review disposition converting the key review findings into accepted-as-is actions.
