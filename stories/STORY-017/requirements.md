# STORY-017 — Requirements: Real-world tuning and validation on Suno source material

## Contract
Consumes: a curated set of real Suno source files, the existing stem-aware mastering pipeline, and the repo’s product guardrails.
Produces: a real-world validation pass that measures whether the pipeline meaningfully improves actual musical material and records the accepted tuning decisions in an auditable report.

## Product requirements
1. Real-world validation set
   - Use a small but representative set of real Suno source files with varied production profiles, not synthetic-only fixtures.
   - The set must include different tonal balances, dynamic behavior, and stereo character so the tuning result is not a single-track artifact.
   - The validation set is a product reality check: if a result only works on synthetic signals, it is not accepted for this story.

2. Before/after product evidence
   - For each validation file, capture the original source and the processed result in the same workflow the product would ship.
   - Record before/after evidence for clarity, control, width, depth, fatigue, and emotional contour.
   - The comparison must be musical and practical, not only metric-driven; a “good number” that does not improve the listening experience is a fail.

3. Listening and reporting checks
   - Review each result for clarity, control, width, depth, fatigue, and emotional contour.
   - The report must note whether the output feels more resolved, more balanced, and more musically convincing than the source.
   - A result is not accepted if it is technically safe but musically flat, artificial, sterile, or fatiguing.

4. Tuning based on evidence, not guesswork
   - Parameter tuning decisions must be tied to the actual source behaviour and the measured before/after evidence, not to unverified assumptions or placeholder values.
   - Any accepted adjustment must be auditable in the report: what changed, why it changed, and what evidence supported it.
   - Rejected adjustments must state why they were not accepted.

5. Rejection of weak but safe results
   - The validation pass must reject outputs that are technically safe but musically weak, dull, over-processed, or emotionally flat.
   - A result may not pass just because it keeps true peak under the ceiling or does not trigger a numeric metric violation.

6. No feature drift without evidence
   - No additional processing feature or tuning change may be added unless it is justified by a real-world failure or a demonstrated product need from the validation set.
   - The project must not drift toward “more processing” without evidence that the added change improves real source material.

7. Stem-first default, stereo fallback only when explicit
   - The real-world validation pass must operate in the stem-first default pathway whenever the source supports it.
   - Stereo-only mastering remains a deliberate fallback and must be called out as limited in the report.
   - The validation result must explain whether the pipeline remained stem-aware or whether the input forced an explicit fallback.

8. Audio safety and product guardrails
   - Internal processing must remain float64; integer conversion happens only at the final I/O boundary.
   - True peak must use oversampled metering, not sample peak.
   - No silent clipping or unsafe aggressive gain may be accepted.
   - Every tuning and validation decision must be auditable in the final report.

## Acceptance criteria
- Real source material is used for validation rather than synthetic fixtures alone.
- The pipeline is evaluated before/after on a small, representative set of Suno files.
- The review explicitly covers clarity, control, width, depth, fatigue, and emotional contour.
- Parameter decisions are recorded with evidence and traceability.
- Results that are technically safe but musically weak are rejected.
- The final validation report states whether the pipeline met the real-world product bar or failed it.
- No feature additions are accepted without evidence from the real-world validation pass.

## Validation plan
- Run the end-to-end mastering path on the curated Suno set.
- Capture the before/after signal and summary metrics.
- Record the musical review for each file and the accepted or rejected parameter choices.
- Ensure the final summary states yes/no for product acceptance and the reason for that decision.

## Revision history
- 2026-08-16: Story 017 requirements created for real-world validation and tuning evidence.
