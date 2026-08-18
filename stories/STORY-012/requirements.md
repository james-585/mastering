# STORY-012 — Requirements: Stem-local harshness control and de-haze

## Contract
Consumes: valid stem-separated signals and stem-level evidence from the current mastering pipeline.
Produces: a conservative per-stem harshness-control and de-haze action list, with audit records for every local correction performed.
Consumed by: the pipeline after transient restoration and before final bus glue / loudness safety.

## Restated intent
The product should reduce listening fatigue without dulling or flattening the programme. Harshness is not a whole-mix problem: it is usually a local issue on specific stems such as harsh vocals, bright synths, cymbals, or bright percussion. The correct product behaviour is to correct the offending stem only when the actual signal shows a real upper-mid/high excess, and leave already-clean material alone.

## Requirements
1. Operate on the offending stem, not the full stereo sum.
2. Detect harshness evidence per stem and per frequency band using spectral content, local energy distribution, and signal-to-noise behaviour rather than a fixed global EQ rule.
3. Apply de-haze only when the measured material is actually brittle, hissy, forward, or resonantly bright in the upper-mid/high region.
4. Keep the correction conservative: reduce harshness and fatigue without making the material dull, flattened, or over-processed.
5. Preserve detail and transient attack on stems that are already musical and clean.
6. Keep every correction auditable in the final report with stem name, frequency band, reason, and gain.
7. Behave as a no-op when a stem is already clean, low-energy, or silence-like.
8. Never claim to recover information that was never present in the actual signal; corrections are limited to measured deficits in the real signal.
9. Keep processing local to the specific offending band, not a blanket global dulling pass across the whole mix.
10. Maintain float64 internals and true-peak safety with oversampling; integer conversion occurs only at final I/O boundaries.

## Acceptance criteria
1. Given a vocal stem with a harsh 2–5 kHz region, when the stem-local harshness detector runs, then the stage reduces the harshness without over-softening the vocal or removing its articulation.
2. Given a bright synth stem with forward upper-mid content, when the detector evaluates it, then the stage controls the brittle energy while preserving the synth’s detail and sparkle.
3. Given a cymbal or bright percussion stem, when the detector sees a de-haze need, then the stage reduces glare and haze without flattening the transient attack.
4. Given a clean stem with no measured excess, when analysis runs, then the stage makes no correction and leaves the stem unchanged.
5. Given a silence or low-energy stem, when the detector runs, then the stage remains a no-op.
6. Given each applied action, when the report is generated, then the stem name, reason, band, and gain are visible in the audit log.
7. Given any signal that approaches clipping risk, when the stage evaluates the corrected output, then it must use oversampling-based true-peak checks and fail loudly or attenuate further rather than silently clipping.

## Explicit non-goals
- No blanket gain reduction or broad global EQ on the full mix.
- No stereo-only “fix everything” correction as the story’s main path.
- No claim of source recovery beyond the information present in the actual signal.
- No dulling pass justified by a fixed target like -1.5 dB, -3.0 dB, or -4.0 dB across every stem.

## Input/output assumptions
- Input: local stem arrays in float64 form, shaped as (samples,) or (samples, channels), with sample rate provided.
- Output: a processed stem dictionary and a list of correction actions; unchanged stems remain byte-identical when no action is warranted.
- Supported file types are local WAV/FLAC/AIFF reads and writes; no cloud services, no GUI, and no plugin-hosting code.
- Stereo-only fallback is permitted only as an explicit last resort; this story’s product path is stem-first and stem-local.

## Auditability and reporting
- Every change must include: stem name, action type, frequency band, gain in dB, reason, and a severity or evidence summary.
- The stage output must be explainable in human terms: what sounded harsh, why it was treated as local, and why no change was applied when clean.
- The report must distinguish between “no action required” and “unsafe to proceed,” so the user can tell whether the stage is no-op or rejecting a risky input.

## Edge cases
- Silence and near-silence stems must remain unchanged.
- Very short or very quiet stems must be treated conservatively with local evidence only.
- Signals with pre-existing clipping or extreme crest factor must be reported as unsafe rather than hidden.
- If a stem is missing, malformed, or invalid, the stage should report the condition instead of fabricating a correction.

## Revision history
- 2026-08-16: Initial requirements drafted for Story 012, aligned to stem-aware harshness control and de-haze with no blanket dulling and explicit auditability requirements.
