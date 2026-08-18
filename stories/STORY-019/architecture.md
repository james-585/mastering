# STORY-019 — Architecture: Deterministic Mid/Side processing for Demucs “other” stem

## Pipeline placement
Insert immediately after the stem extraction stage and before any per-stem repair or final bus summation. The processing order is:
1. ingest audio
2. optional Demucs separation
3. validate stem bundle
4. M/S processing on `other` stem (optional, bypassable)
5. stem-level diagnostics and summation
6. final mastering output and reporting

## Business analyst confirmation

- Story intent: provide a deterministic Mid/Side encoder/decoder path for the Demucs `other` stem only, with a mathematically exact bypass identity path for validation.
- Signal contract: accept stereo float64 arrays with shape `(samples, 2)` and return the same channel layout after encoding/decoding; no silent transformation of vocals, drums, or bass.
- Acceptance criteria: exact round-trip within `1e-12`, identity bypass without drift, null-sum checks on the bypass branch, non-finite rejection, clipping guard, and fully auditable diagnostics.
- Scope limit: no global stereo-sum repair, no broad width remap, and no other-stem processing outside the explicit `other`-stem M/S stage.
- Ambiguity check: none material remained after the story requirements; the bypass branch is explicit and mandatory.

## Design decisions
- The M/S transform is a narrow, auditable utility rather than a hidden global correction stage.
- It operates only on the `other` stem to avoid touching the more structurally specific stems.
- The architecture doubles as a mechanical safety check for any signal path that must remain mathematically lossless when bypassed.
- All transforms are done in float64 and must remain explicit in the report log.

## Module boundaries
- Module: `stem_ms_dsp.py`
- Public API:
  - `encode_ms(stereo: np.ndarray) -> np.ndarray`
  - `decode_ms(ms: np.ndarray) -> np.ndarray`
  - `process_other_stem(stems: dict[str, np.ndarray], *, bypass: bool = False) -> dict[str, np.ndarray]`
- Helper functions:
  - `_validate_stereo_layout()`
  - `_identity_bypass()`
  - `_phase_null_check()`
  - `_clip_guard()`

## Data contract
- Input must be stereo float64 arrays with shape `(samples, 2)` or equivalent valid channel layout.
- Output must preserve sample count and channel ordering.
- A bypass path must return the exact original array object or value-equivalent content with no floating-point drift.
- Each executed stage must be logged with its status: active or bypassed.

## Library choices
- `numpy` for channel sums and scalar math
- `scipy` for the explicit M/S transform matrix and inverse transform
- `soundfile` only at I/O boundaries
- no hidden resampling or silent dtype conversion

## Implementation constraints
- No sample peak checks are allowed as a substitute for true peak.
- Any transform must operate on the exact signal path and be reversible to machine precision.
- If any stage generates NaN or Inf, fail before writing output.
- The pipeline must not silently clip during any re-summation step.

## Guardrails
- No broad stereo-wide fix or global channel balancing in this story.
- No hidden change to vocals/drums/bass.
- No “repair missing source” framing; this is a deterministic transform boundary.
- A bypass branch is not optional behavior; it is a mandatory test path.

## Testability notes
- Synthetic deterministic stereo fixtures must test the transform in both directions.
- Identity-control tests must run under no-op and inverse processing conditions.
- QA should inspect residual energy after inverse transform to ensure the transformation is mathematically neutral when disabled.

## Gate 1 review (mastering engineer)

**Verdict:** PASS-ON-SCOPE

- The M/S transform is mathematically valid for a stereo signal and is reversible in float64 using an explicit matrix relationship.
- The bypass branch is correctly mandatory and identity-preserving; it is the correct control path for phase-cancellation and null-sum validation.
- The `other`-stem boundary is narrow and appropriate. It does not alter vocals, drums, or bass, which matches the project scope and the no-global-fix rule.
- The implementation must keep diagnostics explicit and fail loudly on non-finite input, invalid channel layouts, or clipping risk.
- No blocker was identified for the story as specified; the architecture is acceptable to proceed into implementation.

## Review disposition (mastering engineer)
- Accepted as-is: the transform is intentionally narrow to the Demucs `other` stem only; it does not touch vocals, bass, or drums.
- Accepted as-is: the exact M/S mapping is the standard orthonormal linear transform with inverse matrix, which is reversible to machine precision in float64.
- Accepted as-is: the bypass branch is a mandatory identity path, not a lossy fallback, and it is required for null-sum and phase-cancel validation.
- Accepted as-is: the implementation keeps all internal math in float64 and performs validation before any final output is emitted.
- Action item: preserve the explicit diagnostic payload (`status`, `dtype`, `output_peak`, `residual`, `safety`) in the processing report so the stage remains auditable.
- Action item: fail loudly on non-finite input, invalid stereo shape, or clipping risk before any writes occur.

## Revision history
- 2026-08-17: Initial architecture for the M/S stem transform story.
- 2026-08-17: Added business analyst confirmation, gate-1 review findings, and explicit review disposition for bypass identity, auditability, and safety guards.
