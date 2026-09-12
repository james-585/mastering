# STORY-007 Targeted Sign-Off: LCF Gate and DIGITAL_HAZE Consecutive Windows

**Reviewer**: mastering-engineer
**Date**: 2026-08-14
**Scope**: §5.1 (LCF gate re-derived as HF-presence gate) and §5.2 (consecutive-window trigger). §5.3 and §5.4 not reviewed here.

**Provenance note**: `mastering-review-gate2-final.md` does not exist in this story directory. Prior findings referenced in this review are drawn from `mastering-review-arch-revision.md`: §5.1 Finding 1 (LCF band mismatch BLOCKER) and §5.2 Finding 1 (duration semantics BLOCKER).

---

## §5.1 SMEARED_TRANSIENT — BLOCKER

The band mismatch from the prior Finding 1 blocker is resolved: the gate now correctly band-limits to 6–16 kHz, matching the band the rise-time measurement operates on. The shared HF-envelope-peak anchor (step 2a localisation rule, restated as the step 3 window anchor) removes the DEF-710-class timing divergence — gate and rise-time now reference the same physical sample. That part of the prior blocker is closed and the fix is correct.

The threshold derivation is wrong, and the gate does the opposite of what is stated on the single event class it was designed to reject.

**The threshold of 4.0 dB cannot separate near-silent HF from HF-bearing content because crest factor is scale-invariant.** CF = 20·log10(peak/RMS) does not change when you attenuate the band. "Near-zero HF energy" is a level condition; CF is a shape metric. The architecture's claim at line 172 — "raw HF signal is near-zero → LCF approaches 0 dB (sparse waveform near noise floor)" — is wrong twice. First, attenuation does not lower CF; the ratio is unchanged regardless of absolute level. Second, a genuinely sparse waveform (occasional peaks over a mostly-silent RMS) has *high* CF, not low. The only signal that reads 0 dB CF is a constant-amplitude sinusoid.

The actual HF-band CF for near-silent content falls out from noise statistics: Gaussian noise at N ≈ 1323 samples (30 ms at 44.1 kHz) gives E[max|x|]/RMS ≈ sqrt(2·ln(1323)) ≈ 3.79, or approximately 11.6 dB. The Hilbert/Rayleigh envelope of the same signal gives approximately 9.6 dB. Undithered uniform quantization noise gives sqrt(3) ≈ 4.8 dB. All three are above the 4.0 dB threshold. A kick drum whose 6–16 kHz band contains only noise floor therefore *passes* the gate, not fails it. An HF-bearing onset (vocal sibilant, cymbal) also reads approximately 10–13 dB from carrier oscillations. Both classes land in the same range. There is no value of threshold that separates them using this metric, because the metric is insensitive to the condition being tested.

The PROVISIONAL label at line 175 does not cover this case. The arch-revision review drew this line explicitly (Finding 3: "the estimate was derived for the wrong band — it needs to be re-derived, not re-validated"). The same applies here: the validation protocol at line 175 instructs lowering the threshold if HF-bearing onsets fall below 4 dB and raising it if kicks exceed 4 dB — but measurement would find both classes at 10–12 dB, so the protocol converges on no threshold at all. A validation step that cannot produce a separating threshold is not a safety net.

**Consequence for escalation rule**: with the gate non-functional, ONSET_RISETIME_THRESHOLD_MS is not a backstop — it is the sole mechanism preventing the Chemical Brothers vocal false positives from DEF-705. The escalation rule is correctly specified as a rule; it is carrying the full discriminative burden rather than acting as a fallback.

**What is needed instead**: replace CF with a level test. HF-band RMS in the 30 ms window compared against the local HF noise floor (e.g., median HF RMS over the surrounding 500 ms), with rejection if the window RMS is within X dB of that floor. This measures what the gate claims to measure — presence of HF energy above the noise floor — and is derivable. The alternative "or extract the Hilbert envelope and compute peak/RMS" in step 2a must also be removed; it yields approximately 9.6 dB on noise floor alone, so the two options are not equivalent and leaving both in the architecture would ship two different detectors depending on implementation choice.

**Verdict: BLOCKER.** §5.1 cannot go to implementation with the current threshold or derivation.

---

## §5.2 DIGITAL_HAZE — PASS

The prior Finding 1 blocker (duration semantics ambiguity — one qualifying window vs. eight consecutive windows) is resolved and the resolution is sound.

The window geometry arithmetic is correct. Each metric window covers 8 STFT frames at 250 ms hop = 2.0 s span. Consecutive positions in the sliding scan advance by one frame. Four consecutive qualifying positions span frames *i* through *i*+10 = 11 frames = 0.25 × 11 = 2.75 s. This matches the stated figure at line 223. The positive control at 5 s: 5 s at 250 ms hop = 20 frames; the number of qualifying 8-frame windows is 20 − 8 + 1 = 13 consecutive qualifying positions, comfortably above the threshold of 4. The minimum signal length to trigger (approximately 3.0 s including first-window span) is correctly stated and the 5 s positive control provides safe margin.

The 2.75 s minimum trigger duration is physically credible for Suno generation noise. At 120–128 BPM that exceeds one bar; Suno's stationary HF noise floor persists across multiple bars. Natural episodic HF content — cymbal decay, reverb tails, open hi-hat in a breakdown — typically modulates on a 0.3–2.0 s scale. A 2.75 s continuously-qualifying run excludes the single-event case.

`_find_consecutive_runs()` over a boolean qualifying-window array with one ArtifactFlag emitted per qualifying run (time span: first qualifying window start → last qualifying window end) is structurally sound.

**Concern (does not block, must inform calibration step):** With 1-frame stride, adjacent qualifying windows share 7/8 of their STFT frames. Four consecutive qualifying positions are therefore closer to one test with smoothed edges than four independent confirmations. If Gate 2's finding that prompted this change was driven by false positives on reference tracks, the consecutive requirement may suppress less than the "4 windows" framing implies. For the calibration step at lines 229–233 — where TMI_HF and CC_HF_LF thresholds are derived from reference measurement — values must be measured under the consecutive run criterion, not per-window. A per-window threshold measurement that feeds a consecutive-run trigger produces a threshold that does not correspond to the actual trigger condition.

**Verdict: PASS.**

---

## Overall verdict

§5.2 is cleared for implementation. §5.1 is blocked on the HF-presence gate threshold derivation — the LCF metric is insensitive to the absence-of-HF condition it is required to detect. Architecture is **not** cleared for a final implementation pass; §5.1 requires a method change to the gate criterion before implementation proceeds.
