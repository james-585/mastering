# STORY-014 — Requirements: Stem-aware bus glue and final dynamic balance

## Contract
Consumes: corrected stems, the earlier final stem-level adjustments, and the current mix integral.
Produces: a final bus glue and dynamic-balance pass that improves cohesion without flattening transients, erasing depth, or creating a loud but lifeless master.

## Restated intent
The stem-first mastering flow requires a final stage at the bus, not a blanket limiter. This stage should glue the corrected stems together with only the minimum motion control needed to make the mix feel whole, stable, and emotionally coherent. It must preserve the music’s contour and perceived depth while staying safe in loudness and true-peak terms.

## Requirements
1. Gentle bus glue across corrected stems
   - Recombine the corrected stems into a final mix and apply a subtle, evidence-led bus glue stage only when the full mix is not yet sufficiently cohesive.
   - The operation must feel musical and supportive, not like a blanket compressor introduced to chase loudness.

2. Final dynamic balance without destructive over-compression
   - Apply only the dynamic control needed to balance macro-level movement, vocal or lead emotional contour, and overall internal cohesion.
   - Avoid broad pumping, squashing, or a flat-limiting pass that removes the arrangement’s natural shape.

3. Preserve emotional contour and perceived depth
   - Keep attack, decay, transients, and instrument separation intact.
   - The stage must not erase the sense of space, depth, or forward/backward movement created by earlier stem corrections.

4. Loudness and true-peak safety at the final stage
   - Keep final loudness within the project’s practical target range while respecting true-peak safety.
   - Use oversampled true-peak metering rather than sample peak; do not silently clip or exceed the configured safety ceiling.

5. No-op behavior when the mix already has sufficient cohesion
   - If the mix already feels balanced, stable, and controlled, the stage must be a no-op.
   - Do not force unnecessary processing onto material that is already in a healthy state.

6. No claim of recovering source quality that was never present
   - The stage may improve cohesion and control, but it must not imply it can restore missing information that was never captured in the source or created by earlier stages.
   - The story is about controlled finishing, not magical recovery.

7. Auditability and explainability
   - Every action must be auditable in the final report: which decision was applied, why, and what effect it had on loudness, peak safety, or effective cohesion.
   - The report must distinguish bus glue from dynamic balance and from pure safety limiting.

## Acceptance criteria
- The mix feels more cohesive and controlled without sounding flattened or over-pressed.
- Transients and emotional contour remain intact at the bus stage.
- Already-cohesive material remains unchanged.
- Final loudness and true-peak constraints are respected with oversampled metering.
- The report clearly states that the final pass is conservative and not a blanket loudness-only fix.
- The stage does not claim to recover source information that was never present.
