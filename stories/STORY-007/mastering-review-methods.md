# STORY-007: Gate 1 Method Review — Artifact Detection

**Reviewed**: architecture.md §5 (Detector Specifications) and supporting derivations.

**Question**: Will this method produce correct results on real music, not just on the idealized case?

---

## Findings

### 1. SMEARED_TRANSIENT: HF/LM ratio threshold will fail on dark programme material

**Severity**: Blocker

**What is proposed**: Flag onset if HF (6–16 kHz) energy is < 12 dB below LM (500–2000 Hz) energy.

**Why it fails**: Programme material has naturally declining spectra (DOMAIN.md §2). A dark track with -6 dB/octave tilt from mid to high-mid will have HF naturally 12–15 dB below LM across the entire mix. A kick drum in a dark, heavily filtered mix — entirely legitimate — will trigger this detector on every hit.

**The design claims**: "Normal kick + snare attacks show HF ≈ LM ± 3 dB. Suno generations show HF 12–18 dB below LM." This is stated as measured fact but with no referenced dataset. If this derivation comes from analysing only Suno outputs with an existing defective band-limit detector (DEF-201, still open), the baseline is already compromised. Credible reference data requires:
- Real kick/snare samples from the reference set (Chemical Brothers, GusGus) measured with a known-correct spectral analyser
- Documented Suno outputs confirming 12–18 dB separation
- Both measured identically (same windowing, frequency resolution, energy normalisation)

Without this, the 12 dB threshold is guesswork on dark material.

**Concrete case that breaks it**: A sidechain-compressed bass synth (common in electronic music) with spectral tilt -8 dB/octave will have HF 16 dB below LM at 1 kHz. The first kick hit after the bass entry will flag, even though the kick is normal. False positive.

**What to do instead**: 
- Derive the 12 dB threshold from measured onset spectra on the actual reference set (not from Suno), using the same analysis method as will be used for the detector.
- Report the threshold value and the reference dataset in architecture.md with explicit derivation shown (numbers, not just text). Include measured values for all reference tracks.
- Or, abandon the ratio detector and rely only on rise-time (§1 risk still stands for rise-time across window boundaries; see Finding 3).

---

### 2. DIGITAL_HAZE: SFM threshold cannot distinguish natural diffusion from generation artifacts

**Severity**: Concern (accepted by design, but risk is higher than stated)

**What is proposed**: Flag continuous SFM > 0.85 in 8–16 kHz for ≥ 2.0 s, combined with dynamic range < 6 dB.

**Why it fails**: SFM is insensitive to whether diffuse energy is naturally occurring or generatively produced. Legitimate programme material that will trigger this:
- Long reverb tail (diffuse, broadband) on a vocal or percussion element
- Cymbal or hi-hat decay phase (naturally uniform noise across frequencies)
- White-noise pad or effect (intentional)
- Granular synthesis (intentional diffusion)
- Vinyl crackle or tape hiss

All of these are legitimate audio. The architecture acknowledges "pink noise will flag" and calls it a "known limitation — accepted by design" with "human review filters false positives."

**The risk**: On a heavily compressed mix, a cymbal crash into a pad sustain could easily run 2+ s with SFM > 0.85 and crest factor < 6 dB, especially after limiting. This is normal mastering content, not a generation artifact. The false-positive rate is unknown — could be low on Suno outputs, but could be high on real mixes. Acceptance criteria state "reference tracks produce zero false-positive flags," but the references may simply lack the cymbal+pad scenarios that trigger this.

**Concrete case**: Chemical Brothers "Live Again" has filtered synth pads with natural broadband sustain. If that pad measures SFM 0.87 for 2.5 s and is in a compressed section with crest < 6 dB, the detector will flag it. This would be a false positive on a commercial reference.

**What to do instead**:
- Test the detector on all five reference tracks and report actual SFM and crest factor values in windows spanning 2–5 s.
- If any reference track triggers the flag, the threshold is too loose and must be raised (SFM > 0.92, or duration > 3.5 s, or dynamic range < 4 dB).
- If references do not trigger it, re-test on a synthetic cymbal+pad combining SFM 0.88 and crest 5.5 dB to confirm the design decision is intentional.
- Document in the output report: "DIGITAL_HAZE is known to flag natural diffuse sound (reverb tails, cymbal decay). This flag indicates HF spectral character; it does not prove generation artifact."

---

### 3. SMEARED_TRANSIENT: Rise-time measurement across STFT window boundaries is unspecified

**Severity**: Blocker (affects reproducibility and correctness)

**What is proposed**: For each STFT window, measure onset rise-time as "time from 10% to 90% of peak energy in the high-frequency band (6–16 kHz)."

**Why it's unclear**: STFT windows are non-overlapping and 500 ms wide. An onset that begins at 480 ms and peaks at 550 ms spans two windows. The detector must:
- Identify the onset in window 1 (partial view)
- Detect the peak in window 2
- Measure rise-time from 10% to 90%

But if the 10% point is in window 1 and the 90% point is in window 2, how is the time difference computed? Are windows concatenated for this purpose? If so, the time resolution is lost at the boundary. If not, the rise-time is clipped and artificially long, flagging normal transients as smeared.

**The architecture does not specify**: whether rise-time detection works within a single window, across window boundaries, or uses some other temporal alignment. This is a critical detail for correctness.

**Concrete case**: A kick drum attack from 480 ms to 510 ms (30 ms duration, normal) straddles a window boundary. If rise-time is computed only within the window containing the peak (window 2, starting at 500 ms), the rise-time measured includes only the tail of the attack (10 ms). But if the 10% threshold is in window 1, the method must look back — and this is unspecified.

**What to do instead**:
- Specify explicitly: rise-time detection uses a pre-transient buffer. Onsets are tracked using spectral flux in non-overlapping windows, but rise-time is always computed over a 100 ms sliding window aligned to the spectral flux peak, spanning window boundaries if needed.
- Show pseudocode for the boundary-crossing case.
- Or, abandon per-window processing and use a sliding-window STFT (50% overlap, or greater). This is the standard approach and avoids boundary artifacts.

---

### 4. STATIONARY_WHISTLE: ±50 Hz frequency tolerance may catch legitimate vibrato on programme material

**Severity**: Concern

**What is proposed**: Flag if a spectral peak with Q ≥ 8, prominence ≥ 6 dB persists within ±50 Hz frequency tolerance for ≥ 1.5 s.

**Why it may fail**: The architecture states "vibrato is typically 4–7 Hz, so shouldn't be an issue." This is true for classical vibrato, but electronic music uses much wider modulation:
- String synthesis with wide vibrato: 50–100 Hz peak-to-peak
- FM synthesis with slow LFO (1–2 Hz rate, 100 Hz width): produces ±50 Hz drift
- Granular synthesis with micro-pitch shifts: uncorrelated across grains, but sustained high Q peaks

The statement "Legitimate harmonic content (vibrato, pitch slides) changes frequency more rapidly" is contradicted by intentional vibrato widths that could fit within ±50 Hz.

**Concrete case**: A sustained cello note with moderate vibrato (e.g., ±40 Hz around 400 Hz fundamental) lasting 2 s will have a high-Q peak that drifts ±40 Hz. If Q = 8–10 (typical for a sustained tone in a synthetic ensemble) and prominence = 6–8 dB (typical), it will flag at 1.5 s persistence. This is not an artifact; it is musical content.

**What to do instead**:
- Tighten the frequency tolerance to ±20 Hz, or measure drift rate (dF/dt) and flag only if drift is slower than typical vibrato modulation (< 0.5 Hz/s).
- Or, add a modulation-rate detector: if the peak frequency oscillates periodically (characteristic of vibrato), suppress the flag.
- Test the current design on the reference set with a sustained cello/string sample to confirm it does not flag.

---

### 5. PHASE_SWISH: HF decorrelation threshold will flag intentional stereo width

**Severity**: Concern

**What is proposed**: Flag if HF phase variance > 0.5 rad², HF cross-correlation < 0.4, and LF correlation ≥ 0.7.

**Why it may fail**: Modern electronic music routinely decorrelates HF for width while keeping LF centered. A panned synth element with delay or reverb will have:
- Different phase relationships in L and R due to differential delay
- High phase variance in HF bins (> 0.5 rad²) ✓ triggers
- Low correlation in HF (< 0.4) ✓ triggers
- Stable LF (kick/bass centered, ≥ 0.7) ✓ triggers

This is a legitimate stereo mixing decision, not a Suno artifact. The difference between this and PHASE_SWISH is only the intentionality. The detector cannot distinguish.

**The design's mitigation**: "confidence score is designed to be conservative (0.70–0.85 max) to avoid aggressive false positives." But this does not prevent false positives; it only reduces their reported confidence. A 0.75-confidence flag on intentional stereo width is still a false positive.

**Concrete case**: A panned ambient pad with a 40 ms delay on one channel will have:
- Phase variance in HF > 1.0 rad² (the delay is a phase shift proportional to frequency)
- Cross-correlation in HF < 0.3 (different delay times destroy correlation in HF)
- LF correlation ≥ 0.95 (the pad's low-frequency content is still correlated)
- This will flag with confidence 0.75–0.85.

Is this acceptable? Only if the project accepts that stereo mixing techniques will be reported as potential artifacts, and users must learn to ignore conservative-confidence flags. This should be explicit in the report.

**What to do instead**:
- Test on the reference set with intentionally panned/delayed synth elements to measure the false-positive rate.
- If any reference triggers this flag, the thresholds are too loose.
- Or, add context: detect whether the phase variance correlates with a known delay pattern (linear phase shift with frequency). True decorrelation from generation would be random; intentional stereo would show structure.
- Document in the report: "PHASE_SWISH flags high-frequency decorrelation and may be triggered by intentional stereo width techniques. Disregard flags on intentionally panned elements."

---

### 6. Confidence calibration is heuristic-based, not ground-truth validated

**Severity**: Note (expected for best-effort detection, but worth stating explicitly)

**What is proposed**: Confidence scores are derived from proximity to thresholds. E.g., "rise-time > 25 ms: base 0.85; approach 1.0 as rise-time approaches 50 ms."

**Why it matters**: Confidence should reflect error probability, not just distance from a threshold. A 0.88 confidence should mean "88% chance this is a real artifact." But the current calibration is guesswork:
- There is no ground-truth dataset comparing flagged regions to human judgement.
- No false-positive rate has been measured.
- No false-negative rate has been measured.

If the detector flags a 50 ms rise-time with 1.0 confidence, but 10% of 50 ms onsets in Suno outputs are actually legitimate (synthesis attack envelope), the true confidence is 0.90, not 1.0.

The architecture states this is "best-effort heuristics" (BACKLOG.md says "low priority"), but confidence scores imply precision.

**What to do instead**:
- Explicitly label confidence scores as "proximity scores, not error rates."
- After implementation and testing on real Suno outputs, measure false-positive rates on reference tracks and false-negative rates on problem Suno tracks.
- Recalibrate confidence if needed.
- Document the calibration method in the final report.

---

### 7. Threshold derivation sources are not fully specified

**Severity**: Note

**What is proposed**: Thresholds (e.g., 25 ms rise-time, 12 dB HF/LM ratio) are derived from "measured on synthetic percussive attacks" and "analyzed chemical Brothers, GusGus reference tracks."

**Why it matters**: The derivation sources are vague. "Measured on" could mean:
- 1 sample? 10 samples? A published dataset?
- Which Suno outputs? Version? Generation parameters?
- Which reference tracks? The full stereo mix or isolated percussion?

Architecture.md does not provide:
- Measurement counts (n = ?)
- Statistical summaries (mean ± stdev, not just ranges)
- Links to the dataset or reference measurements
- Reproduction steps (how to re-derive the threshold)

**What to do instead**:
- For each threshold, state: "Derived from N samples of [source]. Mean [value] ± [stdev], measured with [method]. Reference measurements available at [location]."
- Example: "Derived from 47 kick drum onsets from Chemical Brothers 'Live Again,' measured with sliding Hann window (100 ms) STFT at 44.1 kHz. Mean rise-time ± stdev: 9.2 ± 2.3 ms. File: analysis/reference_measurements.json."
- This allows the thresholds to be revisited if new reference data becomes available.

---

## Summary

**Blockers** (must resolve in architecture before implementation):
1. **SMEARED_TRANSIENT HF/LM ratio**: Threshold 12 dB is not derived from credible reference data and will fail on dark programme material. Require explicit measured values from reference set or abandon this branch of the detector.
2. **SMEARED_TRANSIENT rise-time window boundary**: Unclear how rise-time is measured when onsets span STFT window boundaries. Specify or use sliding windows.

**Concerns** (worth addressing; may affect acceptance criteria):
3. **DIGITAL_HAZE false positives**: Will flag legitimate diffuse content (reverb tails, cymbal decay). Test on reference set; if any flag, tighten thresholds.
4. **STATIONARY_WHISTLE vibrato overlap**: ±50 Hz tolerance may catch musical vibrato. Tighten to ±20 Hz or add modulation detection.
5. **PHASE_SWISH intentional stereo**: Will flag stereo width techniques. Test on panned reference content; document as expected false-positive source.

**Notes** (as designed; clarification in report):
6. Confidence scores are proximity-based, not ground-truth calibrated. Label as such.
7. Threshold derivations lack specific measurement counts and source links. Provide before implementation.

---

## Recommendation

**Gate status**: Blocker findings 1 and 2 must be resolved. Resubmit architecture.md with:
- Explicit measured HF/LM values from reference set for SMEARED_TRANSIENT baseline
- Specified rise-time computation across window boundaries (or switch to sliding STFT)
- Updated thresholds with measurement counts and source documentation

Proceed with testing on concerns 3–5 during implementation; document false-positive risks in final report.

---

**Reviewed by**: mastering-engineer  
**Date**: 2026-08-12  
**Confidence in findings**: High. Concerns are grounded in known audio engineering practice (DOMAIN.md §2 spectrum tilt, CLAUDE.md §5 known-wrong patterns). Blockers require method changes, not just parameter tuning.
