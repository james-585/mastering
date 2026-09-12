# STORY-023 — Test cases: automated audio forensics

## TC-023-01: clipping detection
- Given a clipped waveform
- When the diagnostics stage runs
- Then the report flags clipping and identifies the threshold breach

## TC-023-02: phase mismatch detection
- Given phase-inverted or mismatched channels
- When analysis executes
- Then the stage reports the mismatch before output acceptance

## TC-023-03: residual artifact detection
- Given an artifact-rich recombination path
- When residual measurement occurs
- Then the diagnostic result fails the output quality gate

## TC-023-04: clean pass case
- Given a valid, lossless identity path
- When the forensics stage runs
- Then the output is marked as clean and passable
