# STORY-014 — Architecture: stem-aware bus glue and final dynamic balance

## Pipeline placement
Insert after the earlier stem-level correction stages and before final export / user-facing reporting. The intended order is:
1. ingest source and validate stem availability
2. optional stem separation (stem-first path)
3. per-stem analysis and issue detection
4. transient restoration per stem
5. de-haze / harshness reduction per stem
6. stereo imaging and depth shaping per stem
7. corrected stem recombination
8. final bus glue and dynamic balance
9. final loudness and true-peak safety
10. export and report

## Design decisions
- This stage operates on the recombined corrected mix, not on a raw single stereo file, and it assumes earlier stem stages have already done the targeted repair work.
- Bus glue is intentionally small and supportive: a little cohesion when needed, otherwise no change.
- Dynamic balancing is a macro-level stability pass, not a loudness chase or blanket limiter.
- The method should preserve the emotional contour of the arrangement, especially where transient shape, vocal phrasing, and low-end motion are important to the song.
- The stage must be reversible in the audit trail: every action should explain the evidence, the amount of change, and the reason it was considered safe.

## Module boundaries
- Module: `final_bus_glue.py`
- Public API: `apply_final_bus_glue(stems: dict[str, np.ndarray], sample_rate: int) -> tuple[dict[str, np.ndarray], list[FinalBusGlueAction]]`
- Helper functions:
  - `_recombine_mix()` — convert the corrected stem dict into a final mixed bus, creating a synthetic "mix" output when the caller only passes stems or a single mix array.
  - `_as_float64()` — normalize arrays to float64 with no resampling.
  - `_mono()` — convert stereo data to mono for energy and contour analysis.
  - `_true_peak()` — oversampled true-peak estimate with 4x to 8x oversampling.
  - `_stereo_metrics()` — estimate width and inter-channel correlation on the recombined mix.
  - `_is_already_cohesive()` — detect whether the full mix is already sufficiently stable and should be left alone.
  - `_apply_bus_glue()` — gently tighten or center the stereo bus without flattening transients.
  - `_apply_dynamic_balance()` — reduce only the necessary macro energy spread while preserving transient shape.

## Data contract
- Input arrays remain float64 internally; integer conversion occurs only at final I/O boundaries.
- Accept 1D mono or 2D stereo arrays; the output must preserve the original channel layout when it exists.
- The recombined mix must remain within the safe peak zone and never silently exceed ±1.0 sample or true-peak limits.
- Every action record includes the result mix name, action type, gain change, before/after loudness, before/after true peak, and the reason for the intervention.

## Detailed algorithm
### 1. Recombine corrected stems
- If the caller passes a `mix` key, use that as the bus source.
- Otherwise, sum the corrected stems into a single final mix, preserving any stereo layout in the resulting bus.
- This is not an attempt at source recovery; it simply recombines the already-corrected stem work into a final output domain.

### 2. Detect no-op conditions
- Measure: peak, rough loudness, true peak, width, and mid/side balance.
- If the signal is already controlled and the stereo image is stable, keep the stage as a no-op.
- The definition of “already cohesive” is intentionally conservative to avoid needless processing on good material.

### 3. Gentle bus glue
- Reduce the side information slightly when the mix lacks internal cohesion or appears overly diffuse.
- Do not force a static amount of glue across all tracks; the amount should be proportional to the actual bus imbalance.
- Glue should be small enough that the emotional contour, transient strikes, and depth remain audible.

### 4. Dynamic balance
- Perform a gentle macro balancing pass only where the signal needs it.
- The pass should preserve relative motion: dynamic contour remains, but the most aggressive peaks are managed in a way that avoids pumping or overall flattening.
- This is a musical-control stage, not a loudness-first limiter.

### 5. Safety gates and peak checks
- Check true peak after every change using oversampling, not sample peak.
- If the corrected bus would exceed the safe true-peak ceiling, attenuate conservatively and record the action in the audit trail.
- Never silently clip or weaken the bus without reporting the reason.

### 6. Audit and reporting
- Emit an action record for each change: bus glue, dynamic balance, or safety attenuation.
- Log the gain change, before/after measured loudness, before/after true peak, and the human-readable justification for the decision.
- If the mix is unchanged, emit no action and record that the signal was already balanced.

## Library choices
- `numpy` for float64 arithmetic and bus metrics.
- `scipy.signal.resample_poly` for oversampled true-peak checks.
- `soundfile` remains the I/O boundary utility at final export; no cloud or plugin hosting is introduced.
- No `librosa.load(..., sr=...)` path is permitted in the in-memory processing logic.

## Implementation constraints
- All internal calculations use float64.
- The stage is a no-op when the mix is already cohesive or near-silent.
- The stage never claims to restore lost source information.
- Bus glue is small and selective; dynamic shaping is limited to the amount needed for balance and restraint.
- Any successful final output must be traceable to a clear, human-readable action record.

## Guardrails
- No blanket compressor or limiter as the primary fix.
- No global destructive limiting to make the track louder.
- No operation that flattens emotional contour, compresses away all motion, or shaves transients.
- No silent peak violations; any safety attenuation must be reported.
- No fake “depth” or “cohesion” that is not supported by actual mix balance.

## Architectural risks and mitigations
- Risk: The final bus pass could overdo cohesion and flatten the arrangement.
  - Mitigation: use a small side-channel glue factor and a conservative dynamic control envelope; require evidence before adjusting the bus.
- Risk: The implementation might chase LUFS at the expense of musical contour.
  - Mitigation: treat loudness as a safety bound and emotion as the primary target; preserve dynamic shape over raw gain.
- Risk: True-peak errors could hide clipping or inter-sample overshoot.
  - Mitigation: always measure true peak using oversampling and attenuate before final output if there is any risk.

## Revision history
- 2026-08-16: Initial Story 014 architecture drafted around a conservative, stem-aware final bus stage that uses evidence-led bus glue and dynamic balancing without destructive limiting.
