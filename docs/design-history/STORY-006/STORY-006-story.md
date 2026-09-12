# STORY-006: Mastering targets derivation and corrective processing

## Contract
Consumes: reference_set_report.json (STORY-005), mastering-review-gate1.md
Produces: targets.json, updated mastering chain with corrective processing
Consumed by: STORY-007 (batch processing and reporting)

---

## User Story
As a producer, I want the mastering tool to automatically correct the
specific sound quality issues in my Suno exports — muddiness, weak
low-end, dull presence, missing air, flat dynamics, and narrow stereo —
so each track sounds as close to a professional studio production as
mastering on a stereo file can achieve.

---

## Mastering Engineer Findings (gate1-review, 2026-08-10)

These findings gate this story's requirements. Do not contradict them.

### Reference subset for target derivation
Three modern masters only:
- Chemical Brothers — Live Again (primary de-mud reference: −0.15 dB low-mid)
- GusGus — Over (Arabian Horse Album) (+3.39 dB low-mid)
- Black Flute (Remastered) (+8.52 dB low-mid — aesthetic, not muddy)

Leftfield and Wavy Gravy excluded from target derivation (mid-90s era,
DR14–15, −13 to −15 LUFS — different mastering philosophy).

**The five-track JSON aggregates must not be used as targets.** They
include Leftfield and Wavy Gravy in every metric and describe no record
in the set.

### What mastering can fix on Suno
- Loudness and true peak
- Dynamic range — compress toward DR8.3 where source is too wide
- Low-mid de-muddification — excess 200–500 Hz energy
- Low-end weight — sub/low balance nudge if outside reference range
- Presence — gentle high-mid lift if source is recessed
- Stereo width — sub/low tightening toward near-mono reference
- Broad spectral balance nudges within the reference range

### What mastering cannot fix — do not attempt or promise
- HF ceiling: Suno cuts at 13–16 kHz. Content above that is silence.
  Boosting the air band amplifies noise floor only.
- Transient smearing / metallic cymbal character
- Baked-in reverb / ambience
- Per-element balance (kick vs bass, vocal vs pad)

---

## Acceptance Criteria

### Targets (targets.json)
1. Derived from three-track subset only; contributing and excluded tracks
   named explicitly
2. Every target carries median, min, max from the subset
3. Hard targets: integrated_lufs (−13.5, fixed), true_peak_dbtp (−1.0,
   fixed), dynamic_range_db (DR8.3 median, DR6.6–8.65 range)
4. Soft targets (correct only when source is outside range, max ±2 dB):
   sub, low, low_mid, mid, high_mid bands
5. De-muddification rule: flag low-mid when source exceeds +4 dB
   (relative to mid); correct toward +2 dB, not the median. Chemical
   Brothers (−0.15 dB) is the de-mud anchor, not Black Flute (+8.52 dB)
6. high and air bands: report-only, no correction — 12–13 dB disagreement
   across subset makes these targets unsupportable
7. Stereo width: sub/low bands corrected toward near-mono (width < 0.15)
   if source is wide; mid/high bands informational only
8. targets.json is machine-readable JSON; consumed directly by mastering
   chain with no further processing

### Corrective processing
9. Corrective EQ applied in this order: low-end → low-mid → high-mid
   (before dynamics — dynamics respond to spectral balance)
10. Dynamics applied after EQ
11. Loudness and limiting applied after dynamics
12. Dither last, once, at final bit-depth reduction
13. No hardcoded spectral constants in mastering chain — all read from
    targets.json; absent targets.json fails loudly

### Report
14. Before/after measurements for every corrective band
15. Correction amounts logged (what was applied and why)
16. Mastering report states which targets were met, which were outside
    range but not corrected (cap reached), and which were informational
17. HF extension reported as-measured, with caveat — not a correction target

### Tests
18. Negative control: source within range → no correction applied
19. De-mud test: source at +7 dB low-mid → flagged and corrected toward
    +2 dB, not toward subset median (+3.39 dB)
20. Sub/low width test: wide low-end → narrowed toward reference
21. Excluded tracks (Leftfield, Wavy Gravy) do not appear in any derived
    target
22. Absent targets.json → mastering stage fails with a clear error, not
    silent defaults
23. Full fast suite runs under 60 seconds

---

## Backlog item added
DEF-201 recurrence: mastering-engineer Gate 1 review flagged that
stable=False on all five HF tracks in reference_set_report.json is
consistent with DEF-201 threshold-based detection resurfacing in
reference analysis. Added to backlog as STORY-F2 for future investigation.
Not a blocker for STORY-006.

---

## Open questions for BA to resolve
1. Should stereo width correction have a separate max_correction value,
   or use the same ±2 dB cap as spectral bands?
2. Should the de-mud threshold (+4 dB flag) be configurable or hardcoded?
3. Should presence (high-mid) correction be enabled given the 12 dB
   disagreement, or report-only like air and high?
