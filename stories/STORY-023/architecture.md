# STORY-023 — Architecture: Automated audio forensics and diagnostics

## Pipeline placement
Insert as a final validation gate immediately after any Demucs split/re-summation work and before the final mastering process begins.

## Design decisions
- The diagnostics stage is not a listening pass; it is an explicit technical measurement stage.
- It evaluates clipping, phase confidence, and artifact residuals using objective thresholds.
- The stage is mandatory for any Demucs-based pre-processing path so that the project’s claim of mathematically lossless signal flow is actually enforced.

## Module boundaries
- Module: `audio_forensics.py`
- Public API:
  - `run_forensics(original, recombined, stems, sample_rate) -> DiagnosticsReport`
  - `flag_clipping(signal) -> bool`
  - `flag_phase_mismatch(stems) -> bool`
  - `measure_reconstruction_residual(original, recombined) -> float`
- Helper functions:
  - `_true_peak_check()`
  - `_phase_alignment_score()`
  - `_residual_energy()`

## Data contract
- The report must include threshold values, actual measures, and pass/fail verdicts.
- Every metric must be numeric and auditable.
- A clean bypass path should return zero or near-zero residual and a pass verdict.

## Library choices
- `numpy` for signal statistical checks
- `scipy` if phase or spectral diagnostics are needed
- `json` for structured outputs

## Implementation constraints
- Use oversampled true-peak checks, not sample peak.
- Fail loudly on invalid or non-finite outputs.
- Keep the internal processing float64-only and only cast to integer at the final I/O boundary.

## Mastering-engineer review
- Accepted as-is: oversampled true-peak clipping checks, explicit inter-channel correlation phase scoring, and max-absolute residual artifact checks are objective, auditable, and consistent with the repo’s lossless-signal standards.
- Explicit implementation action: use a hard fail when clipping exceeds the ceiling, when phase correlation falls below -0.75, or when residual energy exceeds 1e-6 max absolute error.
- Explicit implementation action: emit a structured JSON/text report including threshold values, measured values, and pass/fail reasons for QA and debugging.
- Accepted as-is: the bypass/identity path remains safe when the recombined signal matches the original within floating-point tolerance and reports a zero residual clean pass.

## Revision history
- 2026-08-17: Initial architecture for automated audio forensics.
- 2026-08-17: Added mastering-engineer review disposition and implementation guardrails.
