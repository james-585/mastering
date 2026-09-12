# STORY-016 — Architecture: end-to-end pipeline integration and acceptance

## Goal
Create the product-level orchestration layer that turns the accepted Stage 011–015 building blocks into one coherent mastering flow, with explicit auditability, fallback transparency, and a review gate before export.

## Product contract
The orchestrator is the product’s control plane. It accepts source audio, chooses the correct stage path, executes the chain in the intended order, records per-stage decisions, triggers the final gate, and enforces the export decision.

## Stage sequence
1. Ingest and metadata capture
   - Accept source audio as a float64 array and record sample rate, shape, and source signal characteristics.
   - Keep the source untouched for comparison and put the processed signal through the chain only after the original is captured.

2. Analysis and pipeline decision
   - Measure the input peak, stereo width, and relevant quality context.
   - Determine whether a stem-aware path is valid or whether a stereo-only fallback must be used explicitly.
   - Record the chosen mode in the audit trail with a reason.

3. Stem separation or explicit fallback
   - Prefer real stems when available.
   - If stems are unavailable, use an explicit stereo fallback instead of silently bypassing the real stage logic.
   - A fallback must be labeled as limited and not equivalent to a full stem-first master.

4. Transient restoration
   - Restore local attack energy where the measured stem exhibits a real transient deficit.
   - Keep the stage conservative and fail loudly if the stem is already near a safe clipping ceiling.

5. Harshness / de-haze control
   - Reduce narrow-band harshness on the offending stems only.
   - Keep the gain local, evidence-driven, and subject to oversampled peak safety.

6. Stereo imaging and depth shaping
   - Widen or stabilize only stems that have real stereo headroom and maintain mono compatibility.
   - Reject anti-correlated or phase-unstable content instead of inventing fake width.

7. Bus glue and final dynamic balance
   - Recombine the processed stems into the bus.
   - Apply conservative glue or balance only when the recombined output shows measurable instability or tonal imbalance.
   - Normalize the bus to the original signal’s usable energy without hidden gain inflation.

8. Final loudness / true-peak safety
   - Run a final oversampled true-peak check.
   - Attenuate only when the project ceiling is breached, and report the reason in the audit output.

9. Final quality review gate
   - Compare the processed output to the original on a before/after basis.
   - Use a pass / reject / refine decision that reflects musical outcome and the repo’s no-hidden-good-numbers rule.
   - Require a documented explanation when the result is not meaningfully better.

10. Export or rejection path
   - Export only when the result passes or when a human override provides a reasoned note.
   - A reject or refine result blocks export unless an override is explicitly documented.

## Architectural rules
- Orchestration is the only layer allowed to schedule and sequence the stage chain.
- No pipeline branch may silently skip a required stage.
- Every stage outcome must be recorded in a traceable audit record.
- The product must never claim to recover information absent from source audio.
- Float64 processing is mandatory for all internal steps.
- True peak must be derived from oversampled data, not sample peak.

## Expected result
The completed pipeline is not a loose set of stage scripts. It is a real product path: validated stage logic composed into one auditable, safety-first mastering workflow with an explicit pass / reject / refine gate and no hidden fallback logic.
