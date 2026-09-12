# STORY-009 — Mastering-Engineer Gate 2 Review (Results)

Reviewed against the live output from the Sunday Club pass:
- `Reference Tracks/Sunday Club_mastered.wav`
- `Reference Tracks/Sunday Club_mastered_report.md`
- `Reference Tracks/Sunday Club_mastered_report.json`

This is a plausibility review of the measured result, not an implementation review.

---

## Blocker 1 — Final true peak sits exactly on the project ceiling and leaves no margin

**Severity**: Blocker

**The value and file**: `achieved_true_peak_dbtp = -1.0000000000000007 dBTP` in `Sunday Club_mastered_report.json`.

**Why it is implausible**: The project’s specification is explicit: `-1.0 dBTP` is the ceiling, not a target. A master sitting exactly on the ceiling with no headroom is not a safe or well-controlled result. This is the decisive threshold for transcode safety, and it should not be treated as a design target.

**What it suggests about the cause**: The chain is over-correcting and then allowing the limiter to sit flat on the ceiling. This is not controlled mastering; it is a damaged output that has been pushed into the limit condition to satisfy the loudness/solver objective without preserving margin.

---

## Blocker 2 — The file still contains the same artifact burden after the so-called repair pass

**Severity**: Blocker

**The value and file**: `Sunday Club_mastered_report.md` reports 454 total flags before and 455 total flags after, with `STATIONARY_WHISTLE` dominating both runs. The JSON also shows multiple `repair_whistles_actions` entries with large peak/RMS deltas.

**Why it is implausible**: A repair stage designed to reduce whistle artifacts should reduce their density and/or their impact. This output does not. The artifact burden remains essentially unchanged while the processing has added a large amount of invasive gain manipulation.

**What it suggests about the cause**: The detector-to-repair gate is not yielding a valid corrective intervention. The pass is modifying the file more aggressively than the artifact profile actually warrants, and the repair step is not solving the underlying issue.

---

## Blocker 3 — The repair stage is acting like destructive broadband attenuation, not surgical notching

**Severity**: Blocker

**The value and file**: `repair_whistles_actions` in `Sunday Club_mastered_report.json`, including values such as `peak_delta_db ≈ -5.24 dB` and `rms_delta_db ≈ -7.81 dB` for multiple flagged frequencies.

**Why it is implausible**: That is a large tonal loss in the affected region, not a narrow, controlled notch. A true whistle repair should be a local, controlled corrective action. These deltas are large enough to reshape the material seriously rather than remove a single offending tone.

**What it suggests about the cause**: The frequency list is being applied across too wide a window and/or with too much gain reduction. The method is not preserving programme content; it is damaging it in the name of repair.

---

## Concern 1 — The pass is producing a “fixed” result without showing the artifact count actually improved

**Severity**: Concern

**The value and file**: `Sunday Club_mastered_report.md` still contains large `STATIONARY_WHISTLE` and `SMEARED_TRANSIENT` lists after the pass.

**Why it matters**: This is the core physical question: does the fix improve the file, or simply move energy around? Based on the output, it does not materially improve the file. That is a warning sign that the detector and repair stages are mismatched or the repair is failing to address the signal pathology.

**What it suggests about the cause**: The repair method is likely being applied too broadly, too aggressively, or to the wrong subset of frequencies. This should be treated as a method flaw, not as a valid result.

---

## Summary verdict

This pass does not pass the plausibility bar for a usable mastering result. The strongest evidence is that:

- the true peak sits exactly at the hard ceiling,
- the artifact count remains effectively unchanged,
- and the repair stage introduces large energy loss in the notched regions.

That combination is the hallmark of a destructive pass, not a corrected one.

This should be treated as a real domain review finding: the workflow is not surviving real programme material in a musically acceptable way, and it should not be shipped as a valid mastering result.
