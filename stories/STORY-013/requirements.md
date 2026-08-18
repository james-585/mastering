# STORY-013 — Requirements: Stem-local stereo imaging and depth control

## Contract
Consumes: valid stem-separated audio, measured stereo width, inter-channel correlation, and center-stability indicators for each stem.
Produces: conservative per-stem stereo imaging decisions that create believable depth and width without fake widening, phase issues, or over-processed spatial effects.
Consumed by: the mastering pipeline after harshness control and before final bus glue / loudness safety.

## Restated intent
The project’s stem-first mastering direction is not a generic stereo-sum widening pass. It is a local imaging stage that uses actual signal evidence to give width to the stems that can support it while keeping low-frequency and lead sources stable and mono-compatible. The stage must never invent stereo information that is not present in the source.

## Requirements
1. Treat stereo width as a per-stem decision, not a global mix decision.
2. Keep kick, bass, and lead vocal stems center-stable by default.
3. Allow selective widening only for stems with enough real stereo information, such as ambience, synths, and pads.
4. Reject any widening action for mono-like, low-energy, or phase-unstable content.
5. Preserve mono compatibility and channel correlation as hard safety constraints.
6. Keep any width or depth change local to the offending or under-developed stem.
7. Make every image decision auditable in the final report, including width before/after, correlation, outcome, and reason.
8. Treat already-stable stems as a no-op.
9. Never generate fake stereo from mono source material or from weak signal content.
10. Limit the stage to actual, evidence-based local correction and avoid a full-bus widening pass.

## Detailed acceptance criteria
1. Given a kick, bass, or lead vocal stem with existing center anchoring, when the imaging stage runs, then the stem remains unchanged unless there is a demonstrated safety issue.
2. Given an ambience, synth, or pad stem with real stereo headroom, when the stage evaluates it, then it may apply a conservative width increase that preserves mono compatibility and avoids phase smear.
3. Given a mono or near-mono stem, when the stage evaluates it, then the stem remains a no-op and does not receive fake widening.
4. Given a low-energy or silent stem, when the stage evaluates it, then the stem remains untouched.
5. Given a phase-unstable stem, when the imaging stage runs, then it raises a hard safety rejection instead of applying a widening move.
6. Given an already-good stereo image, when the stage evaluates it, then the stem is left unchanged.
7. Given any applied imaging action, when the final report is generated, then each decision includes the stem name, before/after width, channel correlation, reason, and result.
8. Given a valid stem-local correction, when the processing completes, then the output must remain within safe true-peak limits and preserve float64 internals until final I/O.

## Explicit non-goals
- No blanket widening of the whole mix.
- No stereo-only fallback as the primary product path when valid stems exist.
- No fake-stereo recovery from mono or weak content.
- No claiming to recover information that was never present.
- No broad depth or width shaping across unrelated stems.

## Input/output assumptions
- Input: float64 stem arrays shaped as (samples,) or (samples, 2), each with a sample rate and a stem label.
- Output: processed stem dictionary plus a structured action list describing each local imaging decision.
- Supported file types: local WAV/FLAC/AIFF reads and writes only; no cloud APIs, no GUI, and no plugin hosting.
- Stereo-only fallback is allowed only as an explicit last resort; the preferred path is stem-first local imaging.

## Auditability and reporting
- Each action must include: stem name, action type, width before, width after, correlation value, gain or depth amount, reason, and safety status.
- The report must distinguish clearly between “no-op because already good,” “no-op because mono/weak/silent,” and “accepted local width increase.”
- Any rejected or skipped stem must be reported as such rather than silently ignored.

## Edge cases
- Silence or near-silence stems remain untouched.
- Very short stems are handled conservatively and only with evidence-based width decisions.
- Signals near the clipping boundary are rejected or attenuated rather than silently clipped.
- If a stem is missing or malformed, the stage reports it instead of manufacturing a stereo fix.

## Revision history
- 2026-08-16: Initial Story 013 requirements draft for conservative stem-local stereo imaging and depth control.
