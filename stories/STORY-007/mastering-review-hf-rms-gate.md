# Mastering Engineer Review — HF-RMS Gate Sign-off
# STORY-007 §5.1 Step 2a: `_ONSET_HF_PRESENCE_RATIO = 3.0`

**Verdict: PASS. Architecture is cleared for final implementation.**

---

## Finding: Energy-level gate correctly separates the two classes

**Severity**: PASS (no blocker, no concern)

**Gate behaviour on kicks and silence.** A kick drum carries near-zero energy in the 6–16 kHz band. The 30 ms gate window centred on the onset anchor yields an HF-band RMS dominated by the local noise floor — the same quantity the denominator estimates from adjacent tiles. The ratio is therefore approximately 1.0, well below 3.0, and the gate correctly rejects the onset. This holds regardless of absolute track level: a louder track raises numerator and denominator equally, leaving the ratio at ≈ 1.0. Scale-invariance here is a feature, not a risk — it is the property crest factor tried to exploit and could not, because CF measures peak-to-RMS within a single window.

**Gate behaviour on HF-bearing onsets.** Vocal sibilants, snare transients, open hats, and synth attacks carry substantial energy in the 6–16 kHz band above the quiescent HF floor. A natural /s/ or snare crack is readily 15–25 dB above the local HF floor at onset, placing the ratio at 5–18, well above 3.0. These onsets pass the gate and are adjudicated by rise-time alone, which is the correct architecture.

**Local floor estimation robustness.** The median over approximately 32 non-overlapping 30 ms tiles spanning ±480 ms from the anchor is robust to: (a) individual outlier onsets within the neighbourhood — the median absorbs these; (b) the onset itself — tile 0 is excluded from the median; (c) slowly-varying HF bed levels across musical sections — the 960 ms neighbourhood tracks slow changes adequately. The estimator adapts correctly across tracks with different absolute noise levels.

**Ratio of 3.0 (~9.5 dB).** The derivation in §5.1 is sound. For a 30 ms gate window at 6–16 kHz bandwidth (BW ≈ 10 kHz), the number of approximately independent samples is N ≈ 2 × 10000 × 0.030 = 600, yielding a relative standard deviation of the RMS estimate of approximately 1/sqrt(1200) ≈ 3%. A kick drum's ratio clusters at 1.0 ± a few percent — the 3.0 threshold provides more than 10 sigma of separation from the estimator's own variance for the kick-drum class. The 0.5 dB difference from exactly +10 dB (ratio 3.162) is immaterial given the large natural separation between the two classes. 3.0 is defensible.

**Acknowledged limitation — HF-dense passages.** In passages with sustained broadband HF activity (dense hi-hat sixteenths, open cymbal wash), the tile-neighbourhood median reflects the sustained HF signal level rather than a quiescent noise floor. A snare onset within such a passage may not achieve HF_RMS_window > 3 × (sustained HF wash level), producing a false negative. The architecture correctly identifies this as a false-negative risk only (kick drum rejection functions correctly in all contexts), marks the ratio PROVISIONAL, and specifies a validation measurement step. This is correct engineering practice; it does not block implementation.

---

Architecture cleared. The PROVISIONAL label on `_ONSET_HF_PRESENCE_RATIO = 3.0` should remain in code pending post-implementation measurement of the ratio distribution in HF-dense passages as specified in §5.1.
