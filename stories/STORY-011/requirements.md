# STORY-011 — Requirements: Stem-aware transient restoration

## Contract
Consumes: HTDemucs-separated stems and the current stem-level analysis output produced by the stem-separation stage.
Produces: a per-stem transient-restoration decision list, with conservative attack boosts and gain shaping only where local transient evidence supports a real attack deficit.
Consumed by: the mastering pipeline after stem separation and before final bus glue and loudness/true-peak safety.

## Restated intent
The current stereo-only mastering pass is limited to broad mix-level changes and cannot restore the attack and articulation that a real stem structure contains. With valid HTDemucs stems available, the product can correct the specific source of transient smear and under-definition on drums, bass, vocals, and melodic material while staying conservative and report-visible.

## Requirements
1. Operate on per-stem signal, not on the summed stereo file.
2. Detect weak or smeared attack in drums, bass, and melodic sources using local transient evidence rather than a global mix formula.
3. Apply transient restoration only when the stem shows measured evidence of attack loss or smear, and allow a no-op when the stem is already good.
4. Keep corrections mild, localised, and band-limited to avoid adding harshness or aliasing.
5. Preserve the original envelope and avoid over-sharpening, pumping, or broadband excitation.
6. Keep all restoration decisions report-visible and traceable in the final audit log.
7. Never claim to recover missing source information; only correct measured transient deficit that is present in the actual signal.
8. Keep the default mode off unless the story and validation explicitly require transient correction for a given stem.

## Acceptance criteria
1. Given a drum stem with smeared attack and weak onset energy, when transient restoration runs, then the stem gains attack definition without becoming brittle or over-bright.
2. Given a bass stem with soft low-end contour and weak punch, when transient restoration runs, then the stem gains clarity and punch without pumping or excessive sub-bass energy.
3. Given a vocal stem with dull articulation but no sustained harshness, when transient restoration runs, then the vocal gains clarity without sibilance bias or audible brightness spikes.
4. Given a synth or melodic stem with already-good transient definition, when the signal is measured, then no restoration should be applied.
5. Given an input where the transient deficit is absent, when the detector checks for attack weakness, then the restoration stage must remain a no-op.
6. Given each stem action, when the final report is generated, then the stem name, reason, gain, and action type must be visible in the audit log.
7. Given any stem with peak energy approaching full scale, when transient restoration evaluates the signal, then the stage must fail loudly or report the risk rather than silently clipping the output.

## Measurable outcomes
- Restored stems must remain within a safe amplitude envelope: no final output sample may exceed ±1.0 without an explicit error or high-level warning.
- Wide-band or global boosts must not be used as a substitute for stem-local evidence.
- Attack restoration should be local to the onset region, not an unbounded gain applied across the full stem.
- The stage must use the same float64 internal representation as the surrounding pipeline and cast to int only at final I/O boundaries.
- True-peak checks must be handled with oversampling (minimum 4x, preferred 8x) and must not rely on simple sample peak.

## Input/output assumptions
- Input: HTDemucs-separated stems as float64 arrays, typically stereo or per-channel arrays with shape (samples, 2) or (samples,).
- Output: a dictionary of processed stems identical in layout and sample rate to the input, with an action list describing each applied restoration.
- Supported file types: local WAV/FLAC/AIFF input as decoded to float64 arrays; no cloud-hosted processing, no in-memory model endpoints.
- Source material: local Suno or generated audio with valid stems available; stereo-only fallback remains out of scope for this story’s primary path.

## Explicit out-of-scope
- Stereo-only transient repair as the main product path.
- Reconstructing source detail that never existed in the stem content.
- Reverb or ambience removal as a hidden recovery mechanism.
- Broad global mix correction that ignores stem identity.
- Any attempt to “repair” a transient by tuning one global parameter without changing the underlying method.

## Non-functional requirements
- Run locally and deterministically on a developer workstation.
- Maintain report transparency: every action is traceable to stem, reason, and measured evidence.
- Behave as a no-op when no valid transient deficit exists rather than forcing a correction.
- Preserve the original input signal and keep all processing reversible in the audit trail.
- The design must be testable in short synthetic fixtures and in real stem batches without requiring GUI tools.

## Edge cases
- Silence or near-silence stems must remain untouched.
- Single-channel stems must be handled without requiring stereo conversion.
- Very short stems or sparse transients must use local-window gating rather than long-window averages.
- Signals with pre-existing clipping should be reported as unsafe; the stage must not attempt to hide clipping.
- Stem names may vary, but required interpretation is: drums, bass, vocals, synth/other, melodic content.
- If stem separation is unavailable or invalid, the restoration stage must report the condition and exit cleanly without manufacturing a fix.

## Open questions
- The exact stem names returned by the separator and downstream pipeline are implementation-specific; the restoration stage must support the canonical set above and degrade gracefully for additional names.
- The story does not prescribe a fixed dB gain or attack threshold; the implementation must derive those from the local transient evidence and document the justification in the report.

## Validation plan
- Synthetic fixtures will include a positive-control smeared transient, a negative-control sharp transient, a low-energy silence case, and a clean stem that must remain unchanged.
- Real programme validation will inspect onset clarity and oversampling safety on actual stems and confirm that the stage only boosts when the transient deficit is real.
- QA must confirm that every action summary includes the stem name, reason, and effect size, and that no output exceeds safe peak limits.

## Revision history
- 2026-08-16: Initial requirement artifact for Story 11, aligned to local-only stem-aware workflow and repo guardrails.
