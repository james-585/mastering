# STORY-017 — Test cases: real-world tuning and validation

## TC-0171 — Curated real-file validation set runs end-to-end
- Input: a small real Suno validation set with distinct production profiles.
- Expected: the orchestrator runs each file through the product chain without silent bypass and records the chosen mode as stem-first or explicit fallback.
- Evidence: the validation report lists each file with a decision, a recorded mode, and the relevant audit outcome.

## TC-0172 — Before/after evidence covers the product goals
- Input: a real Suno source that both has and lacks obvious tonal or dynamic issues.
- Expected: the report records clarity, control, width, depth, fatigue, and emotional contour before/after.
- Evidence: each file entry includes a summary and a set of auditable tuning decisions that align with the reported real-world outcome.

## TC-0173 — Safe but musically weak results are rejected
- Input: a result that keeps true peak and metrics within safe bounds but feels flat, dull, sterile, or artificial.
- Expected: final decision is `reject`.
- Evidence: the report explicitly states that a safe but musically weak result is not accepted and records the product rejection reason.

## TC-0174 — Parameter tuning remains traceable and evidence-based
- Input: any accepted or rejected tuning change during the validation pass.
- Expected: each change includes a parameter name, its accepted value, the evidence behind it, and the reason for the decision.
- Evidence: the final file-level tuning decision list contains explicit evidence strings and phase-appropriate reasons.

## TC-0175 — No feature drift without a demonstrated need
- Input: a proposed additional processing adjustment or new feature branch.
- Expected: the validation report blocks the change unless the source and real-world evidence justify it.
- Evidence: the audit path records whether the change was required by a real-world failure or product issue, and rejects speculative additions.

## TC-0176 — Safety Guardrails are maintained in the validation path
- Input: real validation files near or above the project safety threshold.
- Expected: the workflow either keeps the source in range or scales the working copy safely while preserving the original for comparison.
- Evidence: reported safety notes show that float64 processing and oversampled true-peak checks were honored and that the original source was not silently clipped or replaced.

## Revision history
- 2026-08-16: Story 017 test cases expanded to cover real-world product validation, musical rejection criteria, and auditable tuning traceability.
