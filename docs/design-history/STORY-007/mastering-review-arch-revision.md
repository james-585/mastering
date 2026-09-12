# STORY-007 Architecture Revision Review — Targeted Gate (Post-Gate-2)

**Reviewer**: mastering-engineer  
**Date**: 2026-08-13  
**Scope**: Three changed detector methods only — §5.1, §5.2, §5.3. §5.4 (PHASE_SWISH) unchanged and not reviewed here.

**Provenance note**: `mastering-review-gate2.md` does not exist in the story directory. Gate 2 findings were available only secondhand via architecture.md §11's own summary of them — self-reported provenance. architecture.md §11 already flags this as weaker evidence than a file-based review. Specific findings referenced below reflect the stated method changes and defect resolutions; where Gate 2 findings are cited, they are drawn from the architecture's own summary.

---

## §5.1 — SMEARED_TRANSIENT: Local Crest Factor Gate

**Verdict: BLOCKER**

**Finding 1 — Gate and measurement operate on different frequency bands**

The LCF gate computes crest factor on full-band audio. The rise-time measurement that follows computes the 10%–90% HF Hilbert envelope in 6–16 kHz. For the archetypal percussive onset this gate is designed to admit — a kick drum — these bands are nearly disjoint. A kick drum's transient lives in 50–100 Hz with click energy extending to perhaps 5–8 kHz; there is essentially no kick energy in 6–16 kHz. The kick correctly passes the full-band LCF gate (sharp transient, high crest), and then the detector measures the rise-time of whatever occupies 6–16 kHz in the subsequent 150 ms window — which is hat wash, vocal sibilance, mix noise floor, reverb tail from the previous bar. That rise-time is arbitrary and frequently slow. The gate admits the onset; the measurement fires a false positive on unrelated HF content the gate was never evaluating.

This is also the mechanism behind DEF-707's saturation: the HF envelope's behaviour was governed by the pre-onset HF bed level, not by the onset. A full-band gate in front of that measurement does not resolve the dependency; it enables entry to the same broken measurement.

The 2–4 dB vocal / 8–20 dB percussive figures were derived for full-band attack shapes. They do not transfer to an HF-band crest factor at all — a kick drum has no HF to show a crest on. The 6 dB threshold, if band-limited to 6–16 kHz (or 2–16 kHz), is an undone derivation, not an unvalidated one. The number must be re-derived for the correct band before implementation, not simply validated afterward.

**What to do**: Band-limit the crest-factor computation to match the band whose rise-time is being measured — 6–16 kHz, or at minimum 2–16 kHz to include snare crack. "Percussive" then means "has an impulsive HF transient," which is the precondition the rise-time measurement actually requires. Snare, hat, and cymbal pass; kick correctly does not (kick HF content is too low); vocal onsets fail on HF crest regardless of mix density. The 6 dB number must be re-derived, not merely re-labelled.

**Finding 2 — Onset window placement is undefined relative to sample-accurate onset timing**

The LCF gate specifies a "30 ms window centred on the onset." The onset is identified by a spectral flux peak at STFT frame granularity (250 ms hop). The onset sample can fall anywhere within a 500 ms frame. A 30 ms window centred on the frame midpoint is placed up to ±250 ms from the actual transient peak. When the transient falls at the frame boundary, the 30 ms window captures quiescent pre-onset material. LCF of the pre-onset period is near 0 dB, which falls below the 6 dB threshold, causing the gate to exclude the onset — a false negative. This is identical in structure to DEF-710 (rise-time measurement derived from a different timing reference than the detector uses).

The architecture must specify the localisation rule: find the envelope maximum of the full-band (or HF-band, per Finding 1) audio within the flux frame's time span, and centre the LCF window on that sample. The calibration measurement in §9 must use the same placement rule. If the engineer measures LCF one way and the code computes it another, the 6 dB provisional threshold has no validity on the production detector.

**Finding 3 — LCF of 6 dB is PROVISIONAL, honestly labelled, not the anti-pattern**

The architecture explicitly labels 6 dB as a shape-based estimate, acknowledges window-position effects, and specifies a validation protocol. This is a genuine improvement over the SFM figures that were asserted without derivation or a path to measurement. The PROVISIONAL label is not the problem. The problem is that the estimate was derived for the wrong band (full-band), so re-labelling it would be premature — it needs to be re-derived, not re-validated.

**Finding 4 — Dense arrangement false negatives are a known limitation, not a blocker**

In a dense mix with sustained pads and bass, the RMS floor in a 30 ms window is elevated, reducing LCF for all onsets including percussion. This is a real sensitivity reduction but a false-negative risk (missing real smear artifacts), not a false-positive risk (which was the stated problem). The gate's primary goal is to exclude vocal phrase starts, and LCF of vocals vs. percussion maintains its relative ordering even as absolute values shift down in a dense mix. This warrants documentation as a limitation, not a method change.

---

## §5.2 — DIGITAL_HAZE: TMI_HF + CC_HF_LF Temporal Approach

**Verdict: BLOCKER on duration semantics; CONCERN (proceed with calibration) on everything else**

**Finding 1 — Duration trigger specification is internally contradictory; canonical positive control cannot fire as written**

The method specifies: trigger if both conditions are "sustained for >= 2.0 s (8 consecutive STFT frames)."

TMI_HF and CC_HF_LF are each computed over a sliding 2 s window (8 frames). "8 consecutive STFT frames" where each frame is itself a 2 s window means the detection requires frames 0 through 14 — approximately 4 s of audio — not 2 s. Read the other way, "2.0 s" means the metric window itself, and "8 consecutive frames" is simply describing the window size, meaning one qualifying window is sufficient.

The canonical positive control in §5.3 testability uses "stationary HF noise sustained 3 s." At 3 s with 250 ms hop you get approximately 12 STFT frames and roughly 5 consecutive qualifying 2 s windows (frames 0..7, 1..8, ..., 4..11). On the first reading (8 consecutive windows required), 5 < 8 and the positive control does not trigger. On the second reading (one window required), it does. The architecture must resolve this before implementation, because this is DEF-712's failure mode — canonical positive case cannot reliably trigger the detector — reintroduced in the replacement method by an ambiguity in the trigger condition.

**What to do**: State explicitly whether the 2 s / 8-frame requirement applies to the metric computation window (meaning one qualifying window is sufficient, and `HAZE_DURATION_THRESHOLD_S` is already captured by the window size) or to a run of consecutive qualifying windows (meaning the duration check is additional). Update the positive control duration to be derivable from whichever reading is correct.

**Finding 2 — Physical reasoning is sound**

Natural HF (cymbal decay, reverb tail) is time-locked to its source event and temporally modulated. Suno HF is stationary and decoupled from musical activity below it. The discriminating axis is temporal, not spectral. This is correct and avoids SFM's fundamental failure (both signal classes are spectrally flat — the SFM axis carries no discriminative information). The method change is justified.

**Finding 3 — PROVISIONAL labelling is honest and sufficient**

The TMI_HF derivation error in the prior version (claiming CV ≈ 1/sqrt(N_bins/2) characterises the floor of TMI_HF, when it characterises only the within-frame estimator variance) has been corrected. The current text correctly states that the TMI_HF distribution under 8 correlated frames requires simulation. The threshold is labelled PROVISIONAL, a simulation step is specified in §9.3, and unit tests are restricted to synthetic signals with analytically-known values. This is not the asserted-without-derivation anti-pattern. It is the correct engineering approach when the derivation requires empirical measurement.

**Finding 4 — TMI_HF floor under correlated frames and CC_HF_LF confounding by mix-level dynamics are calibration concerns**

With 50% STFT overlap, adjacent frames share half their samples, increasing frame-to-frame autocorrelation. The distribution of TMI_HF for stationary noise across 8 correlated frames is not derivable analytically and requires the simulation specified in §9.3. If the floor turns out to be 0.08, the provisional 0.10 threshold provides only 0.02 separation. Similarly, CC_HF_LF can be inflated by shared mix-level dynamics even when HF and LF are acoustically independent (both driven by overall mix level variation). Both risks are acknowledged in the architecture. Neither is a blocker; both must be caught in the calibration step.

**Finding 5 — Sustained ride, open hi-hat, and intentional HF pads will trigger; this is acknowledged and accepted**

A sustained open hi-hat with low temporal modulation and low correlation to kick/bass activity (common in breakdown sections of electronic music) will produce low TMI_HF and low CC_HF_LF and will trigger DIGITAL_HAZE. The architecture acknowledges this in §10.1 and recommends human review for any flag. For a triage tool, this is an acceptable limitation, not a method flaw.

**Finding 6 — AC4 invalidation does not require BA sign-off before implementation**

Implementation should proceed. The architecture's §10.2 instruction — no implementation should preserve SFM computation to pass the old AC4 — is correct. AC4 update is parallel BA work, not a prerequisite. The test-case-writer must redesign F-004 and TC-005 for the temporal method. This is already noted in defects.

---

## §5.3 — STATIONARY_WHISTLE: Harmonic Stack Suppression

**Verdict: CONCERN — implement, but the harmonic search must add a frequency tolerance before it will close DEF-705 Issue B**

**Finding 1 — Single-bin harmonic matching will fail on real vocal content due to vibrato and pitch drift**

Step 4 specifies: "find the nearest bin to h_k" — a single bin, 2 Hz wide. Real sustained musical tones have vibrato, tuning offset, and pitch drift of several bins over a 1.5 s run. The `FREQUENCY_TOLERANCE_HZ = 50` constant exists for merging adjacent proto-flags but is not applied to harmonic position matching. On the Chemical Brothers vocal fundamentals from DEF-705 Issue B (108, 200, 254, 330, 412, 500, 660, 782 Hz), the 2f and 3f positions will drift off the single target bin across the duration of a sustained phrase, fail to accumulate >= 2 matches, and the flag will not be suppressed. DEF-705 Issue B was raised specifically for these false positives; the fix that does not suppress them has not closed the defect.

**What to do**: Apply a frequency search tolerance at each harmonic position — ±FREQUENCY_TOLERANCE_HZ (currently 50 Hz) or ±3% of f_0, taking the bin with maximum prominence within the search range. A vibrato width of ±30 cents is approximately ±3% and will keep harmonic search within a ±30 Hz band for a 1 kHz fundamental. The 50 Hz constant is already appropriate at the mid-range of vocal content.

**Finding 2 — HARMONIC_MATCH_PROMINENCE_DB = 3 dB is defensible but close to the background noise floor**

The harmonic match threshold of 3 dB (below background-subtracted spectrum) is lower than the primary 6 dB threshold by design, since harmonics are generally less prominent than the fundamental. The risk: the median-filtered background subtraction with a 100 Hz kernel will not remove all spectral tilt, and 3 dB margin above the residual background is achievable by spectral noise at any given bin over a 1.5 s run. Spurious matches at harmonic positions could suppress real Suno artifact flags that happen to be near a busy spectral region. If false negatives appear on known Suno content after implementation, the first adjustment should be to raise this to 4–5 dB.

**Finding 3 — HARMONIC_MATCH_MIN_COUNT = 2 is defensible**

Requiring 2 of 4 harmonic positions to match protects against coincidental single-harmonic matches. A Suno artifact at 880 Hz finds f/2 = 440 Hz if a musical fundamental is present there — 1 match, not suppressed. Requiring 2 demands that the primary is genuinely embedded in a harmonic series, not merely adjacent to one. The sensitivity cost (a musical tone with only fundamental and 2nd harmonic passes through) is acceptable for a triage tool.

**Finding 4 — False negative on Suno artifact coinciding with musical harmonic is accepted and appropriate**

An artifact tone appearing at the same frequency and time as a musical harmonic is genuinely ambiguous. The architecture accepts the suppression risk (§10.1). For triage purposes — where human review of flagged items is expected — this is the conservative and appropriate choice.

**Finding 5 — AC3 invariant is correctly specified and preserved**

The 6.4 kHz pure sine positive control has no energy at {3.2, 12.8, 2.13, 19.2} kHz by construction. The harmonic check finds 0 matches; the flag is not suppressed. The AC3 test must explicitly verify the harmonic-match count is 0, per §5.3. This is clearly specified.

---

## Summary

| Detector | Verdict | Blocking issue |
|---|---|---|
| SMEARED_TRANSIENT §5.1 | **BLOCKER** | LCF gate measures full-band; rise-time measures 6–16 kHz. Band mismatch means the gate admits onsets the measurement cannot evaluate, enabling HF false positives rather than suppressing them. Plus: onset window placement (30 ms vs. 250 ms hop) unspecified. |
| DIGITAL_HAZE §5.2 | **BLOCKER** on duration semantics alone | "8 consecutive STFT frames" where each frame is a 2 s window makes the positive control (3 s stationary noise) incapable of triggering. Architecture must state whether 2 s is the metric window or a consecutive-windows requirement. Once resolved: CONCERN (proceed with calibration). |
| STATIONARY_WHISTLE §5.3 | **CONCERN** | Implement, but add ±FREQUENCY_TOLERANCE_HZ to harmonic position search before shipping; without it the single-bin match will not suppress vibrato-containing musical tones and DEF-705 Issue B persists. |

The PROVISIONAL labelling in §5.1 and §5.2 is not the anti-pattern from prior rounds. The prior SFM threshold was asserted against a method that physically could not achieve it. The LCF and TMI_HF thresholds are estimated, labelled as such, and have measurement protocols attached. The §5.1 blocker is not that 6 dB is unvalidated; it is that the gate measures the wrong band. The §5.2 blocker is a one-sentence arithmetic ambiguity, not a method flaw.
