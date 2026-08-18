# STORY-007: Gate 1 Method Review — Artifact Detection
## REVISED: Blockers Resolved ✓

**Reviewed**: architecture.md §5 (Detector Specifications) and supporting derivations.

**Question**: Will this method produce correct results on real music, not just on the idealized case?

---

## Blocker Resolution Summary

### Blocker 1: SMEARED_TRANSIENT HF/LM ratio → RESOLVED ✓

**Original issue**: HF/LM ratio threshold (12 dB) would fail on dark programme material with naturally declining spectrum.

**Resolution**: Removed HF/LM ratio detector entirely. SMEARED_TRANSIENT now uses **rise-time only** (25 ms threshold).

**Why this works**: Rise-time is spectral-tilt-independent. A 30 ms attack sounds slow in both a bright and dark mix. This is the defining characteristic of Suno's transient smearing and is sufficient for detection without false positives on naturally EQ'd material.

**Confidence impact**: Reduced from "both conditions present → max confidence" to "rise-time only → monotonic rise from 0.75 to 0.95." Single-metric detection is more conservative but more robust.

---

### Blocker 2: Rise-time window boundary ambiguity → RESOLVED ✓

**Original issue**: Non-overlapping STFT (500 ms hop) caused onsets spanning two windows to have ambiguous rise-time measurement.

**Resolution**: Changed to sliding-window STFT with 50% overlap (hop = 250 ms). This is standard practice for transient analysis.

**Why this works**: 50% overlap ensures that an onset occurring at any point in the audio is fully contained within at least one window. Rise-time is measured from the spectral flux peak within a 150 ms window, avoiding boundary artifacts.

---

## Revised Findings

### 1. SMEARED_TRANSIENT: Rise-time baseline is empirical, validation required

**Severity**: Concern (acceptable; validation planned for implementation)

**What is proposed**: 25 ms rise-time threshold, with no HF/LM ratio branch.

**Validation required**: After implementation, measure rise-times on Chemical Brothers and GusGus kick/snare to confirm all are < 25 ms. This is documented in §10.2 Open Question 3 and in §9.1 test coverage.

**Status**: Acceptable. Threshold is empirical and will be validated during implementation. Rise-time is the correct metric for detecting Suno's decoder blur.

---

### 2. DIGITAL_HAZE: False positives on natural diffuse content are expected and mitigated

**Severity**: Concern (accepted by design; reference-track validation gates acceptance)

**What is proposed**: SFM > 0.85 + low dynamic range for 2+ s continuous window.

**Known limitation**: Will flag reverb tails, cymbal decay, natural broadband noise. This is accepted design — the detector is intentionally sensitive; human review filters false positives.

**Mitigation**: §9.2 test includes "reference control" — all five reference tracks must not produce false-positive flags specific to Suno generation. If any reference flags due to natural diffuse content, the threshold SFM > 0.85 is too loose and must be raised.

**Status**: Acceptable with validation gate. Thresholds may require adjustment after testing on reference set.

---

### 3. STATIONARY_WHISTLE: ±50 Hz tolerance may catch musical vibrato — mitigated

**Severity**: Concern (mitigated; drift-rate detector deferred as optional optimization)

**What is proposed**: Frequency tolerance ±50 Hz for sustained peaks (Q >= 8, prominence >= 6 dB) over 1.5 s.

**Risk**: May flag intentional vibrato on sustained strings or synthesis.

**Mitigation**: 
- Architecture notes this in §5.3 "Known limitations" section (revised).
- Test includes "vibrato control": synthetic cello with intentional vibrato (±40 Hz, 2 Hz rate, 1.5 s duration). Expected: may flag; **implementation should document this as expected behavior**.
- Open Question 4: "Stationary whistle drift-rate detector" defers a potential optimization (measure drift rate and suppress if > 0.5 Hz/s). This is optional and does not block implementation.

**Status**: Acceptable. Confidence score is conservative (0.75–1.0 max); flags on intentional vibrato are acknowledged and will be documented in output.

---

### 4. PHASE_SWISH: Intentional stereo width will flag — documented and expected

**Severity**: Concern (mitigated; confidence design and documentation)

**What is proposed**: HF phase variance > 0.5 rad² + HF correlation < 0.4 + stable LF (>= 0.7).

**Risk**: Intentional stereo width (panned synth with delay/reverb) produces similar signatures and will trigger flags.

**Mitigation**:
- Architecture §5.4 explicitly notes "Note on false positives: This detector will flag intentional stereo width techniques."
- Confidence score is conservative (0.70–0.85 max) to reduce false-positive weight.
- Test includes "negative control": normal stereo electronic mix (drum kick, panned synth). Expected: may flag if synth has intentional HF width; **test must confirm false-positive rate is acceptable**.
- Report output must warn users to distinguish intentional width from generation artifacts.

**Status**: Acceptable with documentation. Users should expect flags on stereo-mixed material and learn to filter them based on musical context.

---

## Remaining Concerns: All Deferred or Acceptable

| Concern | Status | Rationale |
|---|---|---|
| SMEARED_TRANSIENT rise-time validation | Deferred to implementation | Empirical threshold; will verify on reference set. |
| DIGITAL_HAZE on reference tracks | Deferred to implementation | Threshold may need adjustment; reference control gates acceptance. |
| STATIONARY_WHISTLE vibrato overlap | Deferred as optional enhancement | Drift-rate detector suggested in Open Question 4; not required for MVP. |
| PHASE_SWISH stereo width false positives | Deferred to documentation | Rate acceptable per confidence design; users must learn context. |
| Sample rate support (< 32 kHz) | Deferred to BA | Open Question 1; currently raised ValueError. |

---

## Revised Test Coverage (§9.1)

Added tests to validate blocker resolutions and mitigate concerns:

**New for SMEARED_TRANSIENT**:
- `test_smeared_transient_dark_material()`: Heavily EQ'd kick (−12 dB tilt 2–16 kHz) with sharp 8 ms rise-time → Expected: zero flags. Confirms spectral-tilt independence.

**New for DIGITAL_HAZE**:
- `test_digital_haze_reference_tracks()`: All five reference tracks → Expected: no false positives or documented manual review. Gates acceptance.

**New for STATIONARY_WHISTLE**:
- `test_stationary_whistle_vibrato()`: Synthetic vibrato (±40 Hz, 2 Hz rate, 1.5 s) → Expected: may flag. Documents expected behavior.

**New for PHASE_SWISH**:
- Clarified in `test_phase_swish_negative_control()`: "Normal stereo electronic mix… may flag if synth has intentional HF width. Test to confirm false-positive rate is acceptable."

**New system-level**:
- `test_stft_sliding_window_continuity()`: Onset spanning window boundary measured correctly with 50% overlap. Validates blocker 2 resolution.

---

## Acceptance Criteria: REVISED

✓ **Gate 1 Acceptance**:
1. Blockers resolved: rise-time metric is spectral-tilt-independent; sliding STFT handles window boundaries.
2. Remaining concerns are mitigated by design (confidence conservatism, documentation, reference-track validation gates).
3. Test coverage added for all mitigations (dark material, reference tracks, vibrato, sliding-window continuity).
4. Open Questions document deferred optimizations and BA decisions (sample rate, drift-rate detector).
5. Architecture conforms to docs/ARCHITECTURE.md stage contracts (pure analysis, deterministic, hash-invariant).

**Gate 1 Status**: ✅ **PASS with validation gates**

Proceed to **python-developer** for implementation. Reference-track validation and rise-time measurement on Chemical Brothers / GusGus are acceptance criteria for implementation completion.

---

## Recommendation

**Gate 1 re-review: APPROVED** 

Proceed to implementation with the following implementation-time validation requirements:

1. **SMEARED_TRANSIENT rise-time baseline** (Open Question 3): After implementation, measure rise-times on Chemical Brothers and GusGus kick/snare. Confirm all < 25 ms.

2. **DIGITAL_HAZE threshold validation** (Open Question 5): Test on reference set. If any reference flags (reverb tail, cymbal), raise threshold SFM to 0.88–0.90.

3. **STATIONARY_WHISTLE drift-rate detector** (Open Question 4): Optional enhancement for MVP. Document expected vibrato false-positive rate in release notes.

4. **PHASE_SWISH user documentation**: Clearly state in output report that flags on intentionally-panned stereo material are expected and require human judgement.

---

**Re-reviewed by**: mastering-engineer  
**Date**: 2026-08-12  
**Previous Gate 1 findings**: Both blockers resolved. Remaining concerns mitigated by design and test coverage.
