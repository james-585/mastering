# Gate 2 Review — v1.5a
Reviewer: mastering-engineer
Date: 2026-08-08
Implementation: hf_extension.py v1.5a (freeze_index = i_max, _floor_onset_index suffix-max)
Source material: `stories/STORY-004/gate2-trace-v1.5a.md`

---

## 1. Gate 2 Verdict: PASS-WITH-FINDINGS

The whole-track localization results are physically and musically plausible for the material described. The architecture prediction for Leftfield is confirmed. The floor-onset mechanism works as designed: drop margins at j* are large, freeze points are diagnostically coherent, and the tie-free guarantee holds in practice.

Four findings require disposition, two of which require explicit defect entries:

- **Finding 1 (Chemical Brothers stable=False)**: the architecture prediction failed, but the whole-track value is correct and the stable=False is honest. A separate finding within this — segment 1 producing a false positive number rather than an abstention — is defect-grade and should be raised by qa-automation-engineer.
- **Finding 2 (5/5 transcode flags)**: the detection is likely correct, but the three tracks at 20475 Hz have an alternative explanation (44.1→48 kHz SRC passband cutoff) that cannot be discriminated from the trace alone. This must be resolved before STORY-005 target derivation proceeds.
- **Finding 3 (Black Flute 0.08 dB margin)**: code-level, not a Blocker.
- **Finding 4 (Wavy Gravy stable=True by zero margin)**: a Note, not a Blocker, but worth fixing before the confidence threshold becomes a tuning knob.

DEF-201 can close on the basis that whole-track localization is correct and stable=False on Chemical Brothers is a correct, honest report. Two required actions before closure are listed at the end.

---

## 2. Plausibility Check — Per Track

### Black Flute Remastered — 15788 Hz, stable=True, confidence=1.0

**Plausible, and almost certainly not a lossless CD master.**

A hard cutoff at 15.8 kHz is characteristic of mid-bitrate lossy encoding — specifically, it is inconsistent with any lossless source, and with any high-bitrate lossy source at 256 kbps or above, which cut at 19 kHz or higher. A legitimate CD-sourced remaster ripped losslessly would extend to approximately 22 kHz in a 48 kHz file. It would not produce a hard wall at 15.8 kHz. The wall is real: all five segments land on band 81, the whole-track margin is 0.39 dB (thin but above noise on the whole-track PSD), and GusGus below shows what a robust margin looks like on the same grid. The 0.39 dB whole-track margin is not concerning for the whole-track report value.

The "Remastered" in the filename does not change the source quality — a remaster sourced from a lossy file carries the original cutoff.

**Verdict**: plausible measurement. The suspected_transcode flag is correct. This file is not a lossless CD master.

---

### GusGus — Over Arabian Horse — 16251 Hz, stable=True, confidence=1.0

**Plausible, almost certainly not a lossless source.**

16.25 kHz with 7.35 dB margin is the most robust localization in the set. The floor at bands 82–86 sits at −97 to −99 dBFS — below programme content levels but not at digital zero, consistent with a decoded lossy file's residual noise in the near-stopband region. A hard cutoff below 17 kHz is inconsistent with any lossless CD source or high-bitrate lossy encoding. The GusGus "Over" album (Over, 2000) is a genuine commercial release; the question is only what format this specific file came from.

**Verdict**: plausible measurement. The suspected_transcode flag is correct. This file is not a lossless CD master.

---

### Leftfield — Melt — 20475 Hz, stable=True, confidence=1.0

**Plausible measurement, but the source characterization is uncertain. See Section 5.**

Architecture prediction before the run: ≈20475 Hz. Measured: 20475.06 Hz. Margin at j*: 22.99 dB. All five segments also land at band 90. The floor from band 91 onward reads −147 to −148 dBFS — this is a real PSD measurement, not a clamp artifact (`_MIN_POWER = 1e-20` clamps at −200 dBFS; the measured floor is 53 dB above that). The hard wall character is genuine.

However, a floor at −147 dBFS in the stopband is equally consistent with two completely different sources:

1. A high-bitrate lossy transcode (MP3 at 320 kbps cuts approximately in the 19.5–20.5 kHz range; AAC at 256 kbps similarly) decoded to 32-bit float, then SRC'd to 48 kHz. The SRC anti-alias filter introduces a soft floor in its stopband, which on a high-quality converter could produce a −130 to −150 dBFS residual.

2. A losslessly ripped 44.1 kHz CD file converted to 48 kHz. A 44.1 kHz source has Nyquist at 22.05 kHz. A high-quality SRC's anti-alias filter passband typically ends around 0.92–0.93× source Nyquist before rolling off sharply. 0.929 × 22050 = 20484 Hz, which is within one grid band of 20475 Hz. The SRC stopband attenuation of −147 dBFS is entirely plausible for a high-quality converter (SoX VHQ, or similar). Under this hypothesis, the wall is present in the 48 kHz file but was absent in the original CD source.

I cannot discriminate between these two hypotheses from the trace alone. Both produce a hard wall near 20475 Hz with a deep floor in the stopband. See Section 5 for the discriminating test and its implications for STORY-005.

**Verdict**: measurement is plausible. The specific cutoff at 20475 Hz is real. The suspected_transcode flag is consistent with the data, but the source of the cutoff (lossy file vs. SRC artifact) cannot be determined here.

---

### Chemical Brothers — Live Again ft. Halo Maud — 20475 Hz, stable=False, confidence=0.4

**Whole-track value plausible and correctly measured. Per-segment behavior contains a defect-grade finding. See Sections 3 and 4.**

Same reasoning as Leftfield for the whole-track value: 25.79 dB margin, hard floor at −112 to −121 dBFS, freeze at band 85. The whole-track measurement is robust. The per-segment instability (discussed below) does not invalidate the whole-track result.

**Verdict**: whole-track value plausible. stable=False and confidence=0.4 are the correct reported metadata. Segment 1's 14066 Hz result is a defect-grade finding (see Section 4).

---

### Wavy Gravy — 20475 Hz, stable=True, confidence=0.6

**Plausible, with a fragile stability boundary.**

Margin 19.48 dB. Floor at bands 91–95: −130 to −148 dBFS. Same hypothesis uncertainty as Leftfield regarding the source of the cutoff. The track is 449.6 seconds — the whole-track PSD is the most averaged in the set, and the 19.48 dB margin is confident.

confidence=0.6 is exactly at the `hf_cliff_confidence_stable_floor=0.6` threshold, so stable=True by zero margin. With five segments, confidence is quantized to multiples of 0.2; one fewer agreeing segment flips stable to False on a track with a 19.48 dB whole-track margin. That the stability boolean for a robust measurement is decided by a 1-segment swing is a parameter-setting problem, not a detector failure. See Finding 4 below.

**Verdict**: measurement plausible. stable=True is technically correct but barely. The threshold sits on a quantization boundary.

---

## 3. Finding Review

### Finding 1 — Chemical Brothers stable=False, confidence=0.4 (architecture prediction failed)

**QA triage: Architectural. My assessment: correct triage. Not a Blocker for DEF-201 closure. Contains an embedded defect-grade finding that should be raised separately.**

The architecture's position was honest: §3.7 stated explicitly "This is a prediction, to be confirmed empirically at §5.3, not asserted as already true." A prediction that fails on real material is not a design failure; it is information. The key question is whether the current output is correct, not whether it matches the prediction.

**What the output says**: whole-track=20475 Hz, stable=False, confidence=0.4.

**Whether that is correct**: the whole-track result is correct (25.79 dB margin). stable=False correctly reflects that only 2/5 segments agreed on the whole-track value within 2000 Hz. confidence=0.4 is the honest quantification of that agreement rate.

The per-segment breakdown requires splitting into two behaviours, which are fundamentally different:

- **Segments 2 and 5 returning None**: these are honest abstentions. The gate found no qualifying window in those segments. This is musically expected behavior for a dynamic electronic track with filtered passages — see Section 6.

- **Segment 1 returning 14066 Hz**: this is a false positive. The file's band limit is 20475 Hz. It does not become 14066 Hz for 50 seconds. The gate fired at i_max=71 (≈12502 Hz) — a gate-qualifying spectral decline in programme content, not a band-limit wall — and the localizer correctly found a floor onset at 14066 Hz relative to that anchor. The result is a plausible-looking number (inside the DOMAIN.md plausibility floor of 10 kHz) that is wrong. This is the exact failure mode the Gate 1 review described: the gate criterion (8 dB / 12 dB-per-octave) can be satisfied by ordinary spectral decline in real programme material at the wrong frequency.

**The confidence asymmetry**: confidence=0.4 here because two segments abstained (None). If those two segments had instead returned any value within 2000 Hz of 20475 Hz, confidence would have been 0.6 (stable=True) even with segment 1's false positive at 14066 Hz — because 14066 Hz is outside the 2000 Hz tolerance. Had segment 1's false positive landed closer to 20475 Hz (say, at 18.5 kHz), it would have inflated confidence silently. The system partially protected itself by accident, not by design.

**Conclusion**: DEF-201 can close on the whole-track result. The failed architecture prediction should be documented as closed with correct mechanism explanation (the mechanism changed; the output is unchanged; the output is correct on the whole-track PSD). The segment 1 false positive at 14066 Hz is defect-grade and should be raised by qa-automation-engineer as a named finding: the gate criterion admitted a false-qualifying slope on programme content in a 50-second segment of real material, producing a wrong number rather than an abstention.

---

### Finding 2 — 5/5 reference tracks flagged suspected_transcode (0/5 under v1.4)

**QA triage: Architectural. My assessment: correct triage. The detection mechanism is working. The source-vs-SRC question must be resolved before STORY-005 proceeds.**

The change from 0/5 (v1.4) to 5/5 (v1.5a) is not a sign of a newly broken detector. Under v1.4, three tracks were reported at inflated frequencies (Leftfield 22328 Hz, Wavy Gravy 22982 Hz, Chemical Brothers 21075 Hz) as a consequence of argmax saturation. Those inflated values sat outside the transcode suspect bands by coincidence of the bug. Under v1.5a, the correct values happen to fall in the transcode suspect bands — and the detection is physically correct in the sense that the band limits measured are real.

**For Black Flute (15788 Hz) and GusGus (16251 Hz)**: the transcode flags are correct. Sub-17 kHz cutoffs are inconsistent with any lossless or high-bitrate source. These files are not CD masters.

**For Leftfield, Chemical Brothers, and Wavy Gravy (20475 Hz)**: the measurement is correct but the interpretation is uncertain. See Section 5 for the full analysis. The short version: 20475 Hz is within one grid band of the frequency at which a high-quality SRC from 44.1 kHz to 48 kHz would apply its anti-alias filter passband cutoff (0.929 × 22050 ≈ 20484 Hz). If these three files were originally 44.1 kHz CD rips and were converted to 48 kHz for this project, the band limit at 20475 Hz may have been introduced by the conversion, not by the source recordings. That is materially different from "the source files are lossy transcodes."

**Conclusion**: the flags are correct as a detection result (the band limits at these frequencies are real). Whether they indicate source transcodes or a project-internal SRC artifact for the three ~20 kHz tracks is unresolved. This must be documented as a Blocker for STORY-005 target derivation — not because the detector is wrong, but because the remediation differs: if these are lossy sources, the reference set must be replaced; if this is an SRC artifact, the conversion pipeline must be corrected.

---

### Finding 3 — Black Flute localization margin 0.08 dB on segment 2

**QA triage: Code-level. My assessment: correct triage. Not a Blocker for DEF-201 closure.**

The 0.08 dB margin on segment 2 is within Welch estimator noise. On a re-run, that segment could land on band 82 (16251 Hz) instead of band 81 (15788 Hz). The 463 Hz shift is below the 2000 Hz tolerance, so confidence reads 1.0 either way. confidence=1.0 here does not communicate localization robustness — it communicates that the per-segment agreement falls within a tolerance too coarse to see adjacent-band movement.

The whole-track margin (0.39 dB) is above noise and is the primary result. This finding is about the confidence metric's inability to surface known quantization risk, not about the measurement being wrong.

**Conclusion**: not a Blocker. Should be raised as a code-level defect by qa-automation-engineer. The reported hf_band_limit_hz (15788 Hz) is correct.

---

### Finding 4 — Wavy Gravy stable=True by zero margin (Note)

**Severity: Note. Not a blocker for anything.**

With five segments and `hf_cliff_confidence_stable_floor=0.6`, confidence is quantized to {0.0, 0.2, 0.4, 0.6, 0.8, 1.0}. The threshold sits exactly on a quantization point. One fewer agreeing segment — which could happen on a re-run if one segment's margin changes from thin-positive to thin-negative — flips stable to False on a track with a 19.48 dB whole-track margin. The stable boolean for a robust measurement is decided by a 1-segment coin flip.

Two options for a future pass: (a) move the threshold off the quantization boundary (0.7 would require 4/5 agreement), or (b) derive stable from the whole-track margin directly rather than from segment agreement count. Option (b) better reflects what "stable" should mean for a track whose whole-track PSD is unambiguously clear.

---

## 4. Architecture Prediction Failure — Chemical Brothers

**Summary**: the prediction failed; the detector did not fail on the primary output. The whole-track result is correct. The per-segment behavior is a mix of expected abstentions (segments 2, 5) and a defect-grade false positive (segment 1).

The architecture stated at §3.7 that v1.5a's tie-free localization would fix the Chemical Brothers stable=False finding. The prediction's reasoning was sound: v1.4's instability was argmax saturation causing noise-driven per-segment disagreement, and floor-onset localization eliminates that mechanism. But the prediction treated "instability from argmax" as the only cause of instability, and missed that a second cause — the gate criterion firing on programme content at the wrong frequency in a short segment — could produce a similar outcome by a different mechanism.

v1.5a did eliminate the argmax mechanism. The per-segment instability persisted because the gate can be satisfied by spectral content unrelated to a band limit on a 50-second window of a dynamic electronic track. That is a different root cause from v1.4's mechanism, and it is a real property of the material interacting with the gate criterion.

The correct documentation for defects.md: the Chemical Brothers finding carried forward from v1.4 is now explained differently. The output is the same (confidence=0.4, stable=False) but the cause is different (gate false positive on programme content + honest abstentions on filtered segments, not argmax saturation). The whole-track result is correct. The prediction was falsified. DEF-201 can close.

---

## 5. Transcode Flags — Domain Assessment and the SRC Hypothesis

**Black Flute (~15.8 kHz) and GusGus (~16.3 kHz)**: the flags are almost certainly correct. A hard cutoff below 17 kHz is inconsistent with any lossless source and with any high-bitrate lossy format. These are characteristic of mid-bitrate lossy encoding. These files are not CD masters. I have no reason to doubt these flags.

**Leftfield, Chemical Brothers, Wavy Gravy (all at 20475 Hz)**: two hypotheses, both consistent with the trace.

**Hypothesis A — high-bitrate lossy source.** High-bitrate MP3 (320 kbps) or AAC (256 kbps) encoders apply their lowpass in the 19.5–20.5 kHz range, depending on encoder and content. Decoding to 32-bit float and converting to 48 kHz would preserve the stopband character of the encoded file. The deep floor (−107 to −147 dBFS in the stopband) is consistent with the residual noise floor of a high-quality decoded and SRC'd lossy file.

**Hypothesis B — 44.1 kHz CD source, high-quality SRC to 48 kHz.** A losslessly ripped Leftfield CD (44.1 kHz/16-bit) SRC'd to 48 kHz using a high-quality converter with a passband ending at approximately 0.929× source Nyquist would produce a hard wall at 0.929 × 22050 = 20484 Hz — within one 1/24-octave grid band of the measured 20475 Hz. The SRC's own anti-alias filter stopband can reach −140 to −160 dBFS on converters like SoX at VHQ quality, which explains the −147 dBFS measured floor. Under this hypothesis, the original recordings are lossless and full-bandwidth; the band limit was introduced by this project's own file preparation step.

**I cannot discriminate between these hypotheses from the trace.** The floor depths, wall sharpness, and frequency values are consistent with both. The three tracks at the same grid center is a strong hint toward hypothesis B (three independently sourced records would not all be MP3-encoded with identical cutoffs), but it is not conclusive.

**The discriminating test**: were these three files originally 44.1 kHz and converted to 48 kHz for this project? If yes, and if the conversion tool's passband ends near 0.929× Nyquist, hypothesis B is confirmed and the suspected_transcode flag becomes a false positive — the recordings are fine, the project's own conversion is band-limiting the reference set.

**Why this matters for STORY-005**: the two hypotheses have different remediations. Hypothesis A: replace the reference set with confirmed lossless sources. Hypothesis B: redo the SRC with a converter that preserves content to at least 21.5 kHz (0.98× source Nyquist), or use the lossless files directly at their original sample rate. Getting this wrong means STORY-005's HF extension target is calibrated against either a low-bitrate lossy source or a self-inflicted conversion artifact, neither of which is a useful reference for mastering targets.

---

## 6. Segment-Miss Finding — Splitting None Returns from the False Positive

The 4/25 segment calls that did not return 20475 Hz consist of two distinct behaviors that must not be grouped together:

**Segments returning None (3 instances: Chemical Brothers segments 2 and 5, Wavy Gravy segments 2 and 3)**: these are honest abstentions. The gate found no qualifying window in those segments. This is musically expected behavior. A 50-second window of a dynamic electronic track may consist primarily of a filtered breakdown, a bass-heavy drop section, or a fade — portions where HF content above the search range is genuinely attenuated. The gate criterion (8 dB drop in 1/3 octave above 3 kHz, with a passband slope check) requires spectral structure consistent with a wall to be present. If that structure is absent in a segment, returning None is correct — the detector is being honest about what it can see.

The gate is not intended to fire on every segment regardless of content. The whole-track PSD integrates all segments, including the active and the filtered ones, giving the clearest possible view of the global spectral structure. Per-segment analysis is corroboration, not primary measurement. A 12% abstention rate (3/25 on tracks with confirmed whole-track walls) is within plausible range for the genre.

**Segment 1 of Chemical Brothers returning 14066 Hz**: this is categorically different from an abstention. The detector returned a number, but the number is wrong. The file's band limit is 20475 Hz; it does not change within the file. 14066 Hz is the result of the gate firing at i_max=71 (≈12502 Hz) on programme content — ordinary spectral decline or a filtered passage creating a gate-qualifying 8 dB slope at a frequency unrelated to the band limit — and the localizer correctly reporting the floor onset relative to that anchor.

This is the empirical instance of the failure mode DOMAIN.md §2 and the Gate 1 review named: the gate criterion can be satisfied by spectral tilt or arrangement filtering, not only by a band-limit wall. On a whole-track PSD with sufficient averaging, the genuine wall at 20475 Hz dominates. On a 50-second segment where the spectral structure is different, a false-qualifying candidate can appear at a lower frequency and displace the true wall.

**This finding should be raised as a defect by qa-automation-engineer.** It is not a blocker for DEF-201 closure (the whole-track result is correct), but it is evidence that the gate's false-positive rejection depends on programme-content averaging over sufficient duration, and that per-segment results on dynamic material can produce wrong numbers, not just abstentions.

---

## DEF-201 Closure Summary

DEF-201 can close. Two required actions:

1. Document in defects.md that the Chemical Brothers Chemical architecture prediction failed in a specific way: the mechanism changed from argmax saturation (v1.4) to gate false positive + honest segment abstentions (v1.5a), but the correct output (whole-track=20475 Hz, stable=False, confidence=0.4) was produced for the right reasons.

2. The three ~20.5 kHz transcode flags require provenance confirmation (were these files converted from 44.1 kHz by this project, and with what tool?) before STORY-005 target derivation proceeds. This is not a condition on DEF-201 closure — the detector is working — but it is a condition on treating the measured values as reliable mastering reference targets.

Two defects for qa-automation-engineer to raise:
- Segment 1 of Chemical Brothers: gate false positive at 14066 Hz on real programme material (wrong number, not abstention)
- Black Flute confidence=1.0 does not reflect localization robustness (0.08 dB minimum per-segment margin invisible to 2000 Hz tolerance)
