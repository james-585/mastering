# STORY-017 — Architecture: real-world tuning and validation

## Goal
Validate the product on actual Suno material, prove the stem-aware mastering chain improves the music in real listening and metric review, and keep every tuning decision auditable.

## Product architecture
1. Curated validation set
   - Maintain a small set of representative real source tracks from the Suno product domain.
   - Select tracks across a few production profiles so the validation set exercises the realistic range of material the tool must handle.
   - Keep the set deliberately narrow: enough to claim product realism, but not so broad that the tuning becomes speculative or unbounded.

2. End-to-end execution per file
   - For each validation track, read the source audio as float64.
   - Run the existing end-to-end mastering pipeline in its normal order: ingest → analysis → stem choice / fallback → transient restoration → harshness control → stereo imaging → bus glue → final safety → quality review.
   - Record the execution mode as stem-first or explicit stereo fallback, with a reason written into the audit output.

3. Before/after capture and review
   - Capture the original and processed audio, then compute the relevant before/after metrics and a human-readable summary.
   - Review the result for clarity, control, width, depth, fatigue, and emotional contour.
   - Document whether the master is more convincing musically or whether it is safe but empty, dull, or artificial.

4. Structured review of product goals
   - Evaluate the result against the repo’s product goals: transient realism, controlled width and depth, reduced fatigue, improved tonal balance, and more believable emotional contour.
   - Keep the review grounded in both objective evidence and product judgment; no “good numbers” override of human musical evaluation.
   - Reject any pass that is technically safe but musically weak.

5. Parameter-tuning and decision traceability
   - For each accepted or rejected parameter decision, record the input condition, the chosen adjustment, and the evidence that supported or challenged it.
   - If a tuning change is accepted, it must be tied to an observed real-world issue in the source material.
   - If it is rejected, the report must say why the result was musically weak or not product-fit.

6. Integration with the end-to-end review flow
   - The validation report is part of the same final review flow used by the orchestration layer.
   - The final decision must remain pass / reject / refine, with an explicit explanation linked to the musical outcome.
   - A real-world validation report that fails the musical bar must block product acceptance even when the metrics are numerically acceptable.

## Architecture rules
- The validation pass is evidence-driven and uses actual source material, not synthetic-only checks.
- Stem-first operation is the default; stereo-only is a deliberate fallback that must be labeled as such.
- Every stage change and review outcome must be logged in the report so the tuning decisions are traceable.
- No speculative feature additions are allowed without a real-world failure or demonstration from the curated validation set.
- Float64 internal processing and oversampled true-peak validation remain mandatory.

## Expected result
The story produces a real-world validation report that either confirms the mastering chain is musically convincing on Suno material or rejects it with explicit, evidence-based reasons. The result is auditable, aligned to the repo’s product guardrails, and tied to the product’s actual musical goals rather than synthetic compliance alone.

## Revision history
- 2026-08-16: Story 017 architecture written for a real-world validation pass on the curated Suno set.
