# STORY-012 — Test Cases

## Scope
These cases cover the stem-local harshness control and de-haze stage, with acceptance tied to the story requirements and the repo’s guardrails: no global dulling, no silent clipping, maintenance of float64 internals, and full report visibility.

## TC-0121 — Harsh vocal reduction without dulling
- Preconditions: vocal stem with upper-mid excess around 2–4.5 kHz and no low-end imbalance.
- Procedure: run `apply_stem_harshness_control({"vocals": audio}, sr)`.
- Expected result: a conservative negative gain is applied only to the offending band; the vocal remains intelligible and does not get flattened or over-softened.
- Acceptance: `gain_db < 0`, `action_type == "local_dehaze"`, and the processed vocal remains within ±1.0 true-peak safety.

## TC-0122 — Bright synth control without losing detail
- Preconditions: synth stem with forward 2.2–5.5 kHz hash or brittle harmonic emphasis.
- Procedure: run the stage on the synth stem.
- Expected result: the upper-mid haze is reduced while the note contour and fine detail remain intact.
- Acceptance: a local cut is applied only when the band-energy evidence exceeds the no-op threshold; the signal shape remains within the original stem layout and the action is report-visible.

## TC-0123 — Cymbal or percussion de-haze without over-softening attack
- Preconditions: cymbal / bright percussion stem with harsh top-end glare but a real transient attack.
- Procedure: run the stage on the stem using the cymbal/percussion band window.
- Expected result: top-end glare is reduced without eliminating the initial strike or flattening the whole stem.
- Acceptance: gain remains negative and limited, the attack region is not globally softened, and the final waveform remains numerically safe.

## TC-0124 — Clean stem remains unchanged
- Preconditions: a vocal, synth, or cymbal stem with no measured harshness excess.
- Procedure: run the stage on the stem.
- Expected result: no correction is applied and the output matches the input exactly or within floating-point equality.
- Acceptance: `actions == []` and `np.allclose(processed[stem], input_stem)`.

## TC-0125 — Silence or low-energy stem remains untouched
- Preconditions: silence, near silence, or extremely low-energy stem.
- Procedure: run the stage.
- Expected result: no action and no gain change.
- Acceptance: `actions == []` and `processed[stem]` is unchanged.

## TC-0126 — Clipping / oversampling / true-peak safety
- Preconditions: a stem near or at peak amplitude, including a signal with high crest factor.
- Procedure: run the stage and inspect the corrected waveform by true-peak calculation and oversampling-based check.
- Expected result: the stage does not silently clip and may attenuate more aggressively or reject the correction if the corrected signal is unsafe.
- Acceptance: `true_peak <= 0.995` or a loud error/rejection path, and `np.abs(processed).max() <= 1.0` on accepted outputs.

## TC-0127 — Report auditability
- Preconditions: any stem with a real correction.
- Procedure: inspect the returned action list.
- Expected result: each action includes stem name, action type, gain in dB, band in Hz, reason, and severity/evidence metric.
- Acceptance: `action.stem_name`, `action.gain_db`, `action.band_hz`, `action.reason`, and `action.severity` are all populated.

## TC-0128 — Real-audio validation on a real stem source
- Preconditions: a local real-audio source with a bright or harsh stem present; if unavailable, the test is skipped cleanly.
- Procedure: read the real source, isolate a stem or signal slice, and run the stage.
- Expected result: the stage returns a finite, non-clipped result and preserves the overall stem geometry while reducing measured harshness only when present.
- Acceptance: output is finite, same shape as input, and no broad dulling or invalid numerics occur.
