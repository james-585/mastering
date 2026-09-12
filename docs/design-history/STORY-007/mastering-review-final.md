# STORY-007 Architecture Final Sign-Off — Targeted Gate

**Reviewer**: mastering-engineer
**Date**: 2026-08-13
**Scope**: Three blocker/concern fixes in §5.1, §5.2, §5.3 only.

---

## 1. SMEARED_TRANSIENT §5.1 — PASS

Both blockers are resolved. Step 2a now band-limits the LCF computation to 6–16 kHz, matching the band the rise-time measurement operates on. The revised derivation correctly reasons through this band: kick drums produce near-zero HF-band LCF (correctly excluded), vocals show 1–3 dB (correctly excluded), snare and cymbal show 8–15 dB (correctly admitted) — and the 6 dB threshold now sits in the right gap for the right band. The threshold is honestly re-derived and carried forward as PROVISIONAL with a measurement protocol, which is the correct posture. The onset localisation rule is explicitly specified: find the sample of maximum HF envelope amplitude within the flux frame's time span, centre both the 30 ms LCF window and the subsequent 150 ms rise-time window on that same sample. Step 3 repeats the anchor reference to remove any implementation ambiguity. The gate and the measurement are now localised to the same physical event by the same rule.

## 2. DIGITAL_HAZE §5.2 — PASS

The duration contradiction is resolved. Step 4 now states explicitly: "The 2 s / 8-frame requirement describes the metric computation window… not a consecutive-windows run. One qualifying window is sufficient to trigger DIGITAL_HAZE." The testability section confirms the arithmetic: 3 s of stationary noise at 250 ms hop produces approximately 12 STFT frames and multiple overlapping qualifying 2 s windows, and one qualifying window is all that is required. The canonical positive control (3 s stationary HF noise) can now trigger. The prior ambiguity that would have required approximately 14 frames — effectively making the positive control fail — is gone. The fix is a single unambiguous sentence that closes the contradiction without introducing new conditions.

## 3. STATIONARY_WHISTLE §5.3 — PASS

The frequency tolerance is now applied at harmonic position matching, not only at proto-flag merging. Step 4 reads: "search within ±FREQUENCY_TOLERANCE_HZ (50 Hz) of h_k; take the bin with maximum prominence within that range." This is precisely the fix that was needed. A sustained vocal tone with ±30 cent vibrato at 1 kHz drifts approximately ±17 Hz — well inside the ±50 Hz search band. At higher fundamentals the ±3% approximation stays within the tolerance through the mid-vocal range. The harmonic check will now suppress flags on vibrato-containing musical tones as intended, which is what DEF-705 Issue B required.

---

## Overall verdict

All three blockers and the concern are resolved. Architecture is cleared for implementation.
