# STORY-010 — Requirements: Adaptive harshness correction

## Contract
Consumes: the existing frequency-balance result for the presence/harsh band and the current reference curve.
Produces: a second-pass harshness decision and optional corrective action.
Consumed by: the mastering pipeline after corrective EQ and before final loudness limiting.

## Restated intent
The current tool detects harshness by a single 2–5 kHz threshold and applies a conservative, capped peaking cut. That is a valid baseline, but on real material it remains too blunt for broad brightness, narrow resonant spikes, and systematic target mismatch. This story defines a second-pass stage that classifies the harshness and chooses the ratio of correction that matches the actual problem.

## Requirements
1. Preserve the existing first-pass corrective EQ and keep it as the baseline correction stage.
2. Add an optional second-pass harshness classification stage that checks whether the excess is:
   - broad-band brightness across the 2–5 kHz band
   - a narrow resonant peak inside the band
   - a consistent reference mismatch across many processed files
3. Use a gentle shelf or tilt for broad-band brightness.
4. Use a narrow, evidence-driven cut for a localized resonance.
5. Use a reference-target update only when the issue is systematic and material-independent, not as a hidden override for a single track.
6. Keep all corrections capped, logged, and report-visible.
7. Never use arbitrary user-defined notch frequencies. Any notch must be generated from measured spectral evidence within the current track.
8. Do not reintroduce the project’s known-wrong patterns: fixed arbitrary values, threshold-only detection, or broad dulling as a generic fix.

## Acceptance criteria
- The stage is default-off unless explicitly enabled.
- A broad brightness case triggers shelf/tilt rather than a deep peaking cut.
- A resonant harshness case triggers a narrow cut at the measured peak.
- A target-mismatch case triggers a reference adjustment only when the deviation is systematic.
- The report clearly identifies the method chosen and the reason.
- Balanced material remains unchanged.
