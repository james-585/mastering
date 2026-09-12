# STORY-023 — Requirements: Automated audio forensics and diagnostics

## Contract
Consumes: the split and re-summed stem signal path and the project’s safety rules.
Produces: an automated diagnostics stage that detects clipping, phase mismatch, and reconstruction artifacts before the final mastering step proceeds.
Consumed by: pre-mastering validation and reporting.

## Product requirements
1. Add a technical file analysis stage after Demucs split and after recombination.
2. Detect clipping, inter-channel phase mismatch, and reconstruction artifacts with explicit thresholds.
3. Produce a structured diagnostics report in JSON and text form.
4. Block the pipeline or mark the run as unsafe when a threshold is crossed.
5. Preserve the requirement that a bypassed or identity path remain mathematically lossless.

## Acceptance criteria
- Given a clipping event is present, when diagnostics run, then the report identifies the channel and the amplitude threshold breach.
- Given phase mismatch is present, when the analysis executes, then it flags the stem or recombined signal as unsafe before output is accepted.
- Given a recombination artifact is present, when the residual is measured, then the stage records the error and the failing threshold.
- Given a clean signal is present, when analysis runs, then the run passes without warnings.

## Validation plan
- Use synthetic clipped and phase-inverted fixtures.
- Validate artifact detection against a controlled residual threshold.
- Confirm the report includes threshold values and pass/fail reasons for QA and debugging.

## Revision history
- 2026-08-17: Initial requirements artifact for automated audio forensics.
