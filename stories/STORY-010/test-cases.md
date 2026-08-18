# STORY-010 — Test Cases

## TC-0101 broad brightness correction
- Input: track with elevated 2–5 kHz energy across the band, no narrow resonant peak.
- Expected: adaptive stage selects broad shelf/tilt correction, not a deep notch.

## TC-0102 narrow resonance correction
- Input: track with one sharp 3.2 kHz peak dominating the harshness.
- Expected: adaptive stage selects a narrow corrective cut at the measured peak.

## TC-0103 target mismatch case
- Input: repeated tracks sit above the reference curve but are not resonant.
- Expected: stage calls out target mismatch and adjusts the reference logic, not just the EQ depth.

## TC-0104 balanced material no-op
- Input: track already aligned to the reference curve.
- Expected: no harshness correction is applied.

## TC-0105 logging and reporting
- Expected: every corrective action includes method, center frequency, gain, and reason.
