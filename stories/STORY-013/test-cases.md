# STORY-013 — Test cases: stem-local stereo imaging and depth control

## Scope
This test set validates the stem-local stereo imaging stage and its demand for conservative evidence-based widening, center stability, mono compatibility, and clear auditability.

## TC-0131 — Voice or lead center stability
- Precondition: A lead vocal stem with a modest stereo spread but stable center content.
- Expected result: The stage leaves the stem unchanged because vocal stems are center-stable by default.
- Coverage: center stability, no-op behavior, no fake widening.

## TC-0132 — Ambience or pad width increase without phase artifacts
- Precondition: A stereo ambience or pad stem with measurable stereo headroom but no phase instability.
- Expected result: The stage applies a small width increase and leaves the stem mono-compatible; no phase smear is introduced.
- Coverage: selective widening, local width increase, phase safety.

## TC-0133 — Mono compatibility guard
- Precondition: A near-mono or mono stem.
- Expected result: The stage leaves the stem unchanged; no fake stereo is synthesized.
- Coverage: mono compatibility, no fake stereo generation, no-op path.

## TC-0134 — Already-good stereo image remains unchanged
- Precondition: A synth or pad stem already with a stable, musically credible image.
- Expected result: The stage performs no width change because the stem is already acceptable.
- Coverage: no-op behavior, no unnecessary correction.

## TC-0135 — Low-energy or silent stem remains untouched
- Precondition: A silent or near-silent ambience or pad stem.
- Expected result: The stage is a no-op and does not widen or synthesize content.
- Coverage: silent/low-energy handling, safety.

## TC-0136 — Phase-unstable stem is rejected
- Precondition: A stereo stem with strong anti-correlation or phase instability.
- Expected result: The stage raises a hard safety error rather than applying a widening move.
- Coverage: phase issues, safety guardrails.

## TC-0137 — Clipping / oversampling safety check
- Precondition: A widened stem that approaches the clipping threshold.
- Expected result: The stage uses oversampled true-peak detection and blocks or attenuates the operation rather than silently clipping.
- Coverage: clipping risk, true peak, oversampling.

## TC-0138 — Report auditability
- Precondition: At least one widening action is applied.
- Expected result: The report exposes the stem name, width before/after, correlation, gain, and reason for the change.
- Coverage: auditability, report visibility, explainability.

## Revision history
- 2026-08-16: Initial Story 013 test cases covering center stability, selective widening, phase safety, mono compatibility, no-op behavior, and auditability.
