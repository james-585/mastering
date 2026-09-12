# STORY-006 Requirements — Mastering Targets Derivation and Corrective Processing

## 1. Overview / Contract

### Restated intent

Derive a machine-readable `targets.json` from the three modern-mastered reference tracks and update the mastering chain to apply corrective processing — spectral, dynamic, and stereo width — only where the Suno source falls measurably outside the reference range or triggers the de-mud rule, never toward a median no reference occupies.

### Disposition of the six story complaints

The user story asks for correction of six specific problems. Each is addressed, informational-only, or rejected here. Downstream agents must not assume all six are in the build.

| Story complaint | Disposition | Where specified |
|---|---|---|
| Muddiness (excess low-mid) | **Corrected** — de-mud rule fires when low_mid > mid+4 dB; aims toward +2 dB, single-pass ±2 dB cap | Sections 3.4, 3.6, 4 |
| Weak low-end / sub balance | **Corrected** — sub band soft target; correct to nearest range edge if outside [−3.75, +1.94] dB, ±2 dB cap | Sections 3.4, 4 |
| Dull presence (high-mid) | **Rejected** — 12.2 dB reference spread; gate1 §3 explicit; informational only | Q3, Section 6 |
| Missing air / HF | **Rejected** — content above ~12–14 kHz is absent, not attenuated; boosting adds only noise floor | Sections 3.4, 6 |
| Flat dynamics | **Corrected** — dynamics stage targets DR8.3 (range 6.60–8.65); hard target | Section 3.3 |
| Narrow stereo | **Partially corrected** — sub/low bands narrowed toward near-mono if source is wide; widening at any band is out of scope (no explicit widening requirement) | Sections 3.5, 8 |

### Contract

```
Consumes:  reference_set_report.json (produced by STORY-005)
           mastering-review-gate1.md (gate1 gating document)
Produces:  targets.json (machine-readable JSON; schema specified in Section 3)
           Updated mastering chain with corrective processing modules
Consumed by: STORY-007 (batch processing and reporting)
```

`targets.json` is consumed directly by the mastering chain at runtime with no further transformation. It must be valid and complete before STORY-007 begins.

### Input / output assumptions

**Input (Suno exports):**
- Format: WAV or MP3 from Suno. Exact bit depths and sample rates vary; the tool must not assume a fixed rate.
- Loudness: typically loudness-inconsistent across exports (Suno does not normalise).
- HF ceiling: approximately 12–16 kHz (generative band limit). Material above this is silence, not programme.
- Stereo: typically stereo. Mono handling is out of scope for this story.

**Internal processing:**
- Sample rate: the architect must specify. Requirements do not mandate a rate; however, true peak detection requires 4× or 8× oversampling of the native sample rate (DOMAIN.md §1). The `air` band upper edge must be `min(24000, Nyquist_hz)` where `Nyquist_hz` is half the native sample rate after any internal upsampling — this value must be a computed numeric literal in `targets.json`, not a placeholder string.
- Processing must use `soundfile` (or equivalent) with `sr=None` to avoid silent resampling (CLAUDE.md §5).

**Output format:** The architect must specify the output file format, bit depth, and whether lossy (MP3) output is in scope. Dither is required at final bit-depth reduction (AC12); the bit depth at which this occurs must be determined before the dither stage can be designed. These are flagged as open questions (Section 9, OQ4 and OQ5).

### Non-functional requirements

- **Batch size / speed:** Full fast test suite must run in under 60 seconds (AC23). Batch processing requirements are specified in STORY-007.
- **Reproducibility:** Given identical `reference_set_report.json` and identical source audio, the mastering chain must produce bit-identical output. The chain is deterministic; no randomised processing.
- **Fail loudly:** Absent or invalid `targets.json` must cause the mastering chain to exit non-zero with a clear error. Silent defaults are not permitted (AC13, AC22).
- **No hardcoded spectral constants:** All numeric mastering targets must be read from `targets.json`. No spectral constants may appear in mastering source or config files (AC13, CLAUDE.md §5 DEF-202 pattern).
- **Provenance:** Every derived value in `targets.json` must be traceable to the three contributing tracks. Excluded tracks must not shift any derived value.

---

## 2. Resolved Open Questions

### Q1 — Stereo width correction cap

Stereo width is a dimensionless ratio in [0, 1], not a dB quantity. The ±2 dB spectral cap does not apply.

**Resolution:**
- Correction aim point: width = 0.15 (near-mono threshold, the nearest range edge).
- Correction floor: width must not be reduced below 0.10 under any circumstance. This is a safety bound against true-mono collapse — it is **not** the aim point.
- Maximum single-pass correction step: 0.15 width units. Correction is single-pass, not iterative. If the full correction cannot be reached within the step limit, the mastering report logs the residual as "cap reached."
- Correction fires only when source band width exceeds 0.15. The three-track subset shows sub widths of 0.001–0.04 and low widths of 0.001–0.15; exceeding this on a Suno track is out-of-range behaviour.

**Example:** source sub width = 0.80. Aim = 0.15. Required change = −0.65. Cap = 0.15. Applied correction = −0.15. Resulting width = 0.65. Report: `aim_point=0.15, applied=−0.15, cap_reached=true, residual=0.50`.

### Q2 — De-mud threshold configurability

**Resolution: hardcoded as a fixed constant.**

The +4 dB flag threshold (relative to the mid band) is derived from the reference set: Chemical Brothers — Live Again sits at −0.15 dB (the de-mud anchor, the lowest low_mid value in the three-track subset). The flag fires at mid+4.0 dB, which is 4.15 dB above the Chemical Brothers anchor and well above the reference range floor. There is no validated alternative calibration. Making this value configurable creates miscalibration risk with no corresponding benefit.

The correction aim point (+2.0 dB re mid) is also fixed. It is not the subset median (+3.39 dB). +2.0 dB sits 2.15 dB above the Chemical Brothers anchor (−0.15 dB), inside the reference range, and 6.52 dB below Black Flute (+8.52 dB). This choice is deliberate: correcting toward the median (+3.39) would leave muddy sources fully uncorrected when the ±2 dB cap is reached first (a source at +7.0 dB, capped, lands at +5.0 dB regardless of aim point — see Section 4, de-mud rule, for cap semantics).

### Q3 — Presence / high-mid correction

**Resolution: report-only. No correction.**

Gate 1 review is explicit: "Do not correct. GusGus and Black Flute are aesthetically opposite in this band." The three-track spread is 12.2 dB (−1.24 to −13.41 dB re mid). Any single target value is outside the range of two of the three references. Correcting toward any value in this band makes the master sound less like two of the three references.

This resolves the conflict with story.md AC4 (which listed high_mid as a soft correction target). Gate 1 findings govern. See Section 7, AC4 for full conflict traceability.

---

## 3. Target Specification — targets.json Schema

### 3.1 General rules for targets.json

1. `targets.json` must be valid JSON and pass schema validation on load.
2. Every numeric field must contain a numeric literal. No string placeholders survive into the final file; all computed values (spectral medians, Nyquist-dependent bounds) are resolved to numbers at generation time.
3. All subset-derived values — spectral min, max, and median for every band; DR median, min, and max — are **computed by the generator from `reference_set_report.json`** using the three contributing tracks only. The numeric values stated in this document (e.g. sub range −3.75 to +1.94, DR median 8.26) are expected outputs for validation purposes, not values to be copied into the generator.
4. The mastering chain must refuse to process if `targets.json` is absent or fails schema validation. Error must be explicit and non-zero exit.
5. No spectral constant may be hardcoded in mastering source or config files — every target is read from `targets.json` at runtime.

### 3.2 Provenance block (required)

```json
{
  "version": "1.0",
  "provenance": {
    "contributing_tracks": [
      "Chemical Brothers — Live Again",
      "GusGus — Over (Arabian Horse)",
      "Black Flute (Remastered)"
    ],
    "excluded_tracks": [
      "Leftfield — Melt",
      "Wavy Gravy"
    ],
    "exclusion_reason": "Mid-1990s masters at DR14–15, −13 to −15 LUFS. Mastering philosophy diverges from modern streaming-aware subset. Including them produces a five-track range that describes no record in the set."
  }
}
```

### 3.3 Hard targets

These are fixed, not reference-derived.

```json
"hard_targets": {
  "integrated_lufs": {
    "value": -13.5,
    "tolerance_lu": 0.5,
    "source": "Fixed — streaming-aware. References sit at −7.56 to −8.70 LUFS; streaming platforms normalise to approximately −14 LUFS, discarding dynamics. −13.5 LUFS recovers that headroom without being normalised down."
  },
  "true_peak_dbtp": {
    "ceiling": -1.0,
    "source": "Fixed — lossy transcode headroom. Contributing references all exceed 0 dBTP (+0.52 to +0.68 dBTP); acceptable for their era but creates clip risk in transcoding."
  },
  "dynamic_range_db": {
    "target_median": 8.26,
    "target_label": "DR8.3",
    "range_min": 6.60,
    "range_max": 8.65,
    "source": "Computed from three-track subset. Per-track values: Chemical Brothers DR8.26, Black Flute DR8.65, GusGus DR6.60. Median 8.26 is conventionally labelled DR8.3. CLAUDE.md §4.2 states range as 6.6–8.7 (max rounded from 8.65). All three values must be derived from reference_set_report.json, not hardcoded."
  }
}
```

### 3.4 Spectral bands

All values are relative to the mid band (500–2000 Hz, defined as 0 dB). Ranges are expressed as [min, max] with min < max. Do not invert the ordering even where gate1 review states a band's range high-first (e.g. high_mid "−1.24 to −13.41" — the requirement is min=−13.41, max=−1.24).

**The mid band is not a correction target.** All spectral values are relative to mid, so "correcting mid" is a broadband gain change; that belongs to the loudness stage, not corrective EQ. This resolves the conflict where story.md AC4 names mid as a soft correction band.

```json
"spectral_bands": {
  "sub": {
    "freq_hz": [20, 60],
    "classification": "soft",
    "range_db_re_mid": {"min": -3.75, "max": 1.94},
    "median_db_re_mid": "<generator computes from reference_set_report.json — numeric literal in output>",
    "correction_cap_db": 2.0,
    "correct_when": "source_outside_range",
    "correct_toward": "nearest_range_edge"
  },
  "low": {
    "freq_hz": [60, 120],
    "classification": "informational",
    "range_db_re_mid": {"min": 0.47, "max": 8.62},
    "median_db_re_mid": "<generator computes from reference_set_report.json — numeric literal in output>",
    "correction_cap_db": null,
    "note": "8.2 dB spread. Gate1 §3: too wide for meaningful correction. Report only."
  },
  "low_mid": {
    "freq_hz": [120, 500],
    "classification": "soft",
    "range_db_re_mid": {"min": -0.15, "max": 8.52},
    "median_db_re_mid": 3.39,
    "correction_cap_db": 2.0,
    "correct_when": "source_outside_range_or_de_mud_triggered",
    "correct_toward": "nearest_range_edge_unless_de_mud",
    "de_mud": {
      "flag_threshold_db_above_mid": 4.0,
      "correction_aim_point_db": 2.0,
      "overrides_range_compliance": true,
      "anchor_track": "Chemical Brothers — Live Again",
      "anchor_value_db": -0.15,
      "note": "De-mud fires independently of range compliance. See Section 4."
    }
  },
  "mid": {
    "freq_hz": [500, 2000],
    "classification": "reference",
    "value_db_re_mid": 0.0,
    "correction_cap_db": null,
    "note": "Reference denominator. Correcting mid is broadband gain change — loudness stage responsibility."
  },
  "high_mid": {
    "freq_hz": [2000, 5000],
    "classification": "informational",
    "range_db_re_mid": {"min": -13.41, "max": -1.24},
    "median_db_re_mid": "<generator computes from reference_set_report.json — numeric literal in output>",
    "correction_cap_db": null,
    "note": "12.2 dB spread. Gate1 §3 explicit: GusGus and Black Flute aesthetically opposite. No correction."
  },
  "high": {
    "freq_hz": [5000, 10000],
    "classification": "informational",
    "range_db_re_mid": {"min": -17.06, "max": -4.06},
    "median_db_re_mid": "<generator computes from reference_set_report.json — numeric literal in output>",
    "correction_cap_db": null,
    "note": "13.0 dB spread. Not a correction target."
  },
  "air": {
    "freq_hz": [10000, "<min(24000, Nyquist_hz) — generator resolves to numeric literal>"],
    "classification": "informational",
    "range_db_re_mid": {"min": -20.05, "max": -11.44},
    "median_db_re_mid": "<generator computes from reference_set_report.json — numeric literal in output>",
    "correction_cap_db": null,
    "note": "Upper edge is min(24000, Nyquist_hz), resolved to a numeric literal at generation time. Near-Nyquist metering caveat applies. HF extension measurement method is unreliable (gate1 §5, STORY-F2). Report only with explicit caveat."
  }
}
```

**Note on low_mid median:** The three per-track values are available from story.md and gate1 (Chemical Brothers −0.15, GusGus +3.39, Black Flute +8.52; median = +3.39). This is the only band for which requirements.md states a literal median. It must still be computed from `reference_set_report.json` by the generator — +3.39 here is the expected validation value.

**Note on string placeholders in the schema above:** These appear in the description document only. The generated `targets.json` file must contain numeric literals in all value positions. Schema type for all `median_db_re_mid`, `freq_hz`, `range_db_re_mid.min`, and `range_db_re_mid.max` fields is `number`, not `string`.

### 3.5 Stereo width targets

```json
"stereo_width": {
  "sub": {
    "freq_hz": [20, 60],
    "classification": "soft",
    "near_mono_threshold": 0.15,
    "correction_aim_point": 0.15,
    "correction_floor": 0.10,
    "max_correction_step": 0.15,
    "correct_when": "source_width_exceeds_threshold"
  },
  "low": {
    "freq_hz": [60, 120],
    "classification": "soft",
    "near_mono_threshold": 0.15,
    "correction_aim_point": 0.15,
    "correction_floor": 0.10,
    "max_correction_step": 0.15,
    "correct_when": "source_width_exceeds_threshold"
  },
  "mid": {"classification": "informational"},
  "high_mid": {"classification": "informational"},
  "high": {"classification": "informational"},
  "air": {"classification": "informational"}
}
```

Width floor 0.10 is a safety bound against true-mono collapse, not the aim point. The aim point is 0.15. A developer targeting 0.10 instead of 0.15 is implementing the wrong value; tests must distinguish these (see AC20).

AC7 in story.md constitutes the "explicit requirement" that gate1 §3 defers stereo width correction to ("Report first; correct only on explicit requirement"). Width narrowing on sub and low bands is therefore in scope. Width widening at any band is not in scope for this story — no explicit widening requirement exists (see Section 8).

### 3.6 De-mud block (top-level in targets.json)

```json
"de_mud": {
  "flag_threshold_db_above_mid": 4.0,
  "correction_aim_point_db": 2.0,
  "applies_to_band": "low_mid",
  "anchor_track": "Chemical Brothers — Live Again",
  "anchor_value_db": -0.15,
  "derivation": "Hardcoded. Flag at mid+4.0 dB is 4.15 dB above anchor (Chemical Brothers −0.15 dB low_mid). Aim +2.0 dB sits 2.15 dB above anchor, inside the reference range, and 6.52 dB below Black Flute (+8.52 dB). Aim is not the subset median (+3.39 dB). Cap ±2 dB applies."
}
```

### 3.7 Correction cap semantics (normative)

These rules govern all spectral and stereo width corrections.

1. **Single-pass:** Correction is applied once per band per track. No iteration.
2. **Aim point, not guaranteed target:** "Correct toward X" means X is the aim point. The output value need not reach X; the cap takes precedence.
3. **Cap wins:** The ±2 dB spectral cap (or 0.15 width step cap) takes precedence over the aim point when the required change exceeds the cap.
4. **Report the residual:** Every CorrectiveAction log entry must contain: `band`, `trigger` (range_compliance or de_mud), `source_value`, `aim_point`, `applied`, `cap_reached` (bool), `resulting_value`. Residual is reported under the "outside range but not corrected (cap reached)" category, not as a failure.
5. **No range-compliance correction within range:** If the source value is already within the target range, range-compliance correction is not applied. This rule does not prevent de-mud from firing — see rule 6.
6. **De-mud exception to rule 5:** The de-mud rule fires whenever the source low_mid level exceeds mid+4.0 dB, regardless of whether that level falls within the range [−0.15, +8.52]. The low_mid range maximum (+8.52) represents Black Flute's aesthetic choice, described in story.md as "aesthetic, not muddy." Gate1 §2 lists low-mid de-muddification as a mastering-addressable problem. A Suno source is not Black Flute; the reference range upper edge does not confer permission to remain muddy. If both de-mud and range-compliance triggers would fire simultaneously, de-mud governs.

---

## 4. Corrective Processing Requirements — Per Band

### Classification definitions

| Classification | Behaviour |
|---|---|
| Hard target | Applied to every master; failure to meet is an error |
| Soft target | Correct only when source is outside stated range or when a named rule fires; cap applies; report residual |
| Informational | Measure and report; no filter operations |
| Reference | Denominator for spectral measurements; not a correction category |

### Per-band specification

| Band | Freq range | Classification | Target range (re mid) | Correction cap | Additional rules |
|---|---|---|---|---|---|
| sub | 20–60 Hz | Soft | −3.75 to +1.94 dB | ±2 dB | Correct to nearest edge when outside range |
| low | 60–120 Hz | Informational | +0.47 to +8.62 dB | None | Report only |
| low_mid | 120–500 Hz | Soft + de-mud | −0.15 to +8.52 dB | ±2 dB | Range compliance: nearest edge. De-mud (source > mid+4.0): aim +2.0 dB. De-mud fires within or outside the range. |
| mid | 500–2000 Hz | Reference | 0 dB (by definition) | N/A | Not a correction target |
| high_mid | 2000–5000 Hz | Informational | −13.41 to −1.24 dB | None | Report only |
| high | 5000–10000 Hz | Informational | −17.06 to −4.06 dB | None | Report only |
| air | 10000–Nyquist Hz | Informational | −20.05 to −11.44 dB | None | Report only with method caveat |

### De-mud rule — expanded

**Trigger condition:** source low_mid level > (mid_level + 4.0 dB). Fires regardless of whether source is inside or outside the reference range.

**When triggered:** correct toward aim point +2.0 dB re mid (not toward the subset median +3.39 dB). ±2 dB cap applies. Single-pass.

**When de-mud fires while source is inside range [−0.15, +8.52]:** The range compliance rule ("no correction within range") is suspended for low_mid. Rationale: the range maximum +8.52 dB is Black Flute's aesthetic choice, described in story.md as "aesthetic, not muddy." Gate1 §2 lists low-mid de-muddification as a mastering-addressable problem. A Suno source is not Black Flute; the reference range upper edge does not confer permission to remain muddy.

**Aim point vs cap example:** Source at +7.0 dB. Aim = +2.0 dB. Required change = −5.0 dB. Cap = −2.0 dB. Applied = −2.0 dB. Result = +5.0 dB. The aim point is +2.0; the actual output is +5.0. The CorrectiveAction log must record the aim point, not the result, as the target.

**CorrectiveAction log entry (required fields):**
```json
{
  "band": "low_mid",
  "trigger": "de_mud",
  "source_db": 7.0,
  "aim_point_db": 2.0,
  "applied_db": -2.0,
  "cap_reached": true,
  "resulting_db": 5.0
}
```

### Stereo width — cap semantics

Width correction for sub and low bands follows the same cap-semantics as spectral bands. Aim point is 0.15 (nearest edge, not the floor). Floor 0.10 is a safety bound and must not appear as an `aim_point` in any CorrectiveAction log entry.

---

## 5. Processing Chain Order

The following order is normative (DOMAIN.md §5, gate1 §3). Any implementation that reorders these stages fails.

1. **Corrective EQ** — sub band, then low_mid band, in that order. Applied as shelves or wide-bell filters only (BACKLOG STORY-006: no surgical notching on a stereo sum). Informational bands (low, high_mid, high, air) produce measurements and report entries only — no filter operations.
2. **Dynamics / glue compression** — after corrective EQ. Dynamics respond to spectral balance; reversing the order invalidates the spectral correction.
3. **Loudness and limiting** — bring integrated loudness to −13.5 LUFS (±0.5 LU tolerance); apply −1.0 dBTP ceiling. Loudness measured **after** limiting, never before.
4. **Dither** — last operation, once only, at final bit-depth reduction. Must not appear at any intermediate stage. The bit depth at which dither is applied must be specified by the architect (see OQ4).

### Conflict resolution — AC9

Story.md AC9 specifies: "low-end → low-mid → high-mid (before dynamics)." Gate1 §3 establishes high_mid as informational, not corrective. Requirements.md resolves: corrective EQ chain is sub → low_mid only. High_mid is measured for reporting; no filter is applied. Gate1 findings govern over AC9.

---

## 6. What Mastering Cannot Fix

The following must not be promised, attempted, or treated as defects when they persist after processing. Source: DOMAIN.md §4, gate1 §2 and §4.

| Problem | Why correction is impossible |
|---|---|
| Content above Suno's 12–14 kHz band limit | Absent, not attenuated. A high-shelf boost raises only noise floor. No information is recovered. |
| Transient smearing and metallic cymbal character | The generative model never rendered fast-attack transients. Information was not masked; it was never produced. No mastering process reconstructs it. |
| Baked-in reverb and ambience | Baked into the stereo sum at generation time. Requires source separation, which is outside project scope (CLAUDE.md §2). |
| Per-element balance (kick vs bass, vocal vs pad) | Requires per-element access. Elements are inextricably combined in the stereo sum. |
| LRA targeting | Three-track reference subset spans 3.21–12.20 LU (9 LU range). No defensible single target. LRA is guidance-only (CLAUDE.md §4.2). |
| Spectral correction in high_mid or high | 12–13 dB reference spread means any single target describes no record in the set. |
| Stereo widening | Not in scope for this story. Gate1 §3 permits widening only on explicit requirement; no such requirement exists. Only narrowing (sub and low bands toward near-mono) is implemented. |

**Permanent audible Suno marker:** The 12–14 kHz band limit produces characteristic dullness in the top octave relative to studio-recorded material. Loudness-matching the master against a studio reference makes this contrast more audible, not less. Stereo width and dynamic range can be aligned; the frequency ceiling is a permanent property of the generative source.

---

## 7. Acceptance Criteria

Acceptance criteria from story.md (AC1–AC23) mapped to requirements. Conflicts with gate1 are called out explicitly.

### Targets (targets.json)

**AC1:** `targets.json` derived from three-track subset only; contributing and excluded tracks named explicitly.
→ Section 3.2. Passed when: `provenance.contributing_tracks` lists exactly three tracks; `provenance.excluded_tracks` lists Leftfield and Wavy Gravy; no derived metric changes when Leftfield or Wavy Gravy data is removed from the generator input.

**AC2:** Every target carries median, min, max from the subset.
→ Section 3.4. `median_db_re_mid`, `range_db_re_mid.min`, and `range_db_re_mid.max` must be present for all spectral bands. DR median, min, and max must be present in `hard_targets.dynamic_range_db`. All values computed from `reference_set_report.json`; no hand-coded numerics in generator source.

**AC3:** Hard targets: `integrated_lufs` = −13.5, `true_peak_dbtp` = −1.0, `dynamic_range_db` median = 8.26 (DR8.3), range 6.60–8.65.
→ Section 3.3. Passed when: `targets.json` contains these values and no alternative numeric targets appear in mastering source or config files.

**AC4:** Soft targets on sub, low, low_mid, mid, high_mid — correct only when outside range, max ±2 dB.
→ **Partial conflict with gate1. Resolution:**
- **sub**: Soft target. Confirmed.
- **low**: Gate1 §3: 8.2 dB spread, too wide. Reclassified to Informational. No correction.
- **low_mid**: Soft target with de-mud rule. Confirmed.
- **mid**: Reference denominator. "Correcting mid" is broadband gain. Not a spectral correction target.
- **high_mid**: Gate1 §3 explicit: "Do not correct." Reclassified to Informational. See Q3.
Gate1 governs over story.md AC4 on low and high_mid.

**AC5:** De-muddification: flag at source > mid+4 dB; correct toward +2 dB, not median.
→ Section 4, de-mud rule. Passed when: CorrectiveAction log shows `aim_point_db = 2.0` (not 3.39) for any flagged track; flag fires at source > mid+4.0 dB.

**AC6:** High and air: report-only, no correction.
→ Section 3.4. Passed when: no filter operations on high or air measurements.

**AC7:** Stereo width: sub/low corrected toward near-mono (width < 0.15) if source is wide; mid/high informational.
→ Section 3.5. Passed when: width correction fires on sub or low when source > 0.15; aim_point logged as 0.15 (not 0.10); no width correction applies to mid or above.

**AC8:** `targets.json` is machine-readable JSON; consumed directly by mastering chain.
→ Section 3.1. Passed when: `targets.json` parses as valid JSON; all value fields are numeric literals (no string placeholders); mastering chain reads it at startup with no manual transformation.

### Corrective processing

**AC9:** Corrective EQ order: low-end → low-mid → high-mid (before dynamics).
→ **Conflict with gate1.** Resolution: chain order is sub → low_mid only. High_mid is informational; no filter applied. See Section 5.

**AC10:** Dynamics applied after EQ.
→ Section 5. Confirmed.

**AC11:** Loudness and limiting applied after dynamics.
→ Section 5. Confirmed.

**AC12:** Dither last, once, at final bit-depth reduction.
→ Section 5. Confirmed. Output bit depth to be specified by architect (OQ4).

**AC13:** No hardcoded spectral constants; absent `targets.json` fails loudly.
→ Section 3.1 rules 4–5. Passed when: grep of mastering source reveals no numeric spectral targets; startup with missing `targets.json` exits non-zero with explicit error.

### Reporting

**AC14:** Before/after measurements for every corrective band.
→ Report must contain pre-correction and post-correction values for sub and low_mid; measured values for all informational bands.

**AC15:** Correction amounts logged with what was applied and why.
→ Section 3.7. Passed when: every correction produces a CorrectiveAction log entry with all required fields (band, trigger, source_value, aim_point, applied, cap_reached, resulting_value).

**AC16:** Report classifies each band as: met, outside range but cap reached, or informational.
→ Section 3.7. Three-category classification required for every measured band in the report.

**AC17:** HF extension reported as-measured with caveat.
→ Section 3.4 (air note). Report must include measurement alongside explicit statement that the method is unreliable (gate1 §5, STORY-F2) and that the value is not a correction input.

### Tests

**AC18:** Negative control: source within range → no correction applied.
→ Test source must be specified carefully to avoid triggering the de-mud rule (which fires within the range): synthesise a signal with low_mid at +2.0 dB re mid (within range [−0.15, +8.52] and below de-mud threshold mid+4.0 dB), sub within [−3.75, +1.94], and both band widths ≤ 0.15. Assert: zero CorrectiveAction entries for sub, low_mid, and width bands; output audio is unchanged in those bands.

**AC19:** De-mud test: source flagged and corrected toward +2 dB, not toward subset median (+3.39 dB).
→ **A source at +7.0 dB cannot discriminate aim points by audio output alone.** At +7.0 dB: aim +2.0 → −5.0 dB required → −2.0 dB applied → +5.0 dB result. Aim +3.39 → −3.61 dB required → −2.0 dB applied → +5.0 dB result. Outputs are identical.
→ **Assertion 1 (required, primary discriminator): assert on the CorrectiveAction log.** The correct implementation logs `aim_point_db = 2.0`. An implementation using the median logs `aim_point_db = 3.39`. This assertion discriminates them regardless of source level.
→ **Assertion 2 (complementary audio-level assertion): use a source value in the discriminating interval (+4.0, +5.39) dB.** At source = +4.5 dB: aim +2.0 → −2.5 dB required → −2.0 dB applied (cap) → +2.5 dB result. Aim +3.39 → −1.11 dB required → cap does not bind → +3.39 dB result. Separation = 0.89 dB. For reference: the separation formula in this interval is `(5.39 − S)` dB where S is source level; use S ≤ +4.5 dB to maintain separation ≥ 0.89 dB against realistic band-measurement tolerance. Note: the +5.39 endpoint is excluded from the discriminating interval — at exactly +5.39 both aim points produce +3.39 dB after their respective caps.

**AC20:** Sub/low width test: wide low-end → narrowed toward reference.
→ Synthesise a signal with sub width = 0.60 (> 0.15). Assert: width correction applied; CorrectiveAction log shows `aim_point = 0.15` (not 0.10); applied correction = −0.15; resulting width = 0.45; resulting width > 0.10 (floor not breached). Assert no width correction applied to mid or higher bands.

**AC21:** Excluded tracks do not appear in any derived target.
→ **Two assertions required:**
- Negative: generate `targets.json`; assert that removing Leftfield and Wavy Gravy from `reference_set_report.json` produces no change in any derived numeric value (min, max, median, DR values).
- Positive: perturb one contributing track's band value in `reference_set_report.json` (e.g. shift Chemical Brothers low_mid from −0.15 to −2.15); assert that `targets.json` `spectral_bands.low_mid.range_db_re_mid.min` shifts correspondingly (from −0.15 to −2.15). This verifies the generator reads contributing track values and does not embed hardcoded literals from this document.

**AC22:** Absent `targets.json` → clear error, not silent defaults.
→ Remove `targets.json`; run mastering chain; assert: non-zero exit; stderr/log identifies missing file; no output file produced; no default spectral values substituted.

**AC23:** Full fast suite runs under 60 seconds.
→ Wall-clock time on development machine for the complete test suite including all synthetic-signal tests.

---

## 8. Out of Scope

Explicitly excluded from STORY-006. Proposing these is scope creep.

- Artwork and metadata tagging
- Track sequencing and gap management
- Stem extraction or source separation (CLAUDE.md §2)
- Real-time or streaming processing (CLAUDE.md §2)
- GUI (CLAUDE.md §2)
- VST3 / AU plugin hosting (CLAUDE.md §2, STORY-F1)
- RoEx or any cloud mastering API (CLAUDE.md §2)
- LRA targeting (9 LU reference span; guidance only)
- Transient shaping or artifact removal
- Reverb reduction
- Per-element mixing adjustments
- Stereo widening — gate1 §3 permits this only on explicit requirement; the user story mentions "narrow stereo" but no explicit widening requirement has been stated; only sub/low narrowing toward near-mono is in scope for this story
- HF extension correction (informational only; method unvalidated; STORY-F2)
- Multi-pass or iterative spectral correction (single-pass cap rule is normative)
- Spectral correction in high_mid or high bands
- Any use of Leftfield — Melt or Wavy Gravy data in target derivation

---

## 9. Open Questions

Story.md's three open questions are resolved in Section 2. The following remain unresolved and require architect decisions or future work.

**OQ1 — CorrectiveAction data structure (architect action required before implementation):** AC19 depends on asserting on the CorrectiveAction log entry. The architect must specify the CorrectiveAction data structure (field names, types, serialisation format) before the test-case-writer designs AC19 tests. Required fields are identified in Section 4.

**OQ2 — HF extension measurement method (STORY-F2, not a blocker for STORY-006):** All five reference tracks report `stable=False` for HF extension in `reference_set_report.json`, with per-segment variation of 2–9 kHz within single files. A band limit is a fixed property of a file (DOMAIN.md §2). This is a recurrence of the DEF-201 threshold-based detection error (CLAUDE.md §5). HF extension is correctly informational-only in this story. Gate1 §5 recommends this be raised as a defect by the qa-automation-engineer.

**OQ3 — targets.json generation trigger (architect decision):** The architect must decide whether `targets.json` is generated once and committed, regenerated on each mastering run, or regenerated only when `reference_set_report.json` changes. This decision affects caching behaviour and reproducibility guarantees.

**OQ4 — Output bit depth (architect decision required before dither stage design):** AC12 requires dither "at final bit-depth reduction." Dither type and level depend on the output bit depth (typically TPDF for 16-bit reduction). The output format and bit depth have not been specified in this story. The architect must determine: output WAV bit depth (16 or 24 bit), whether 32-bit float intermediate files are used, and whether lossy (MP3) output is in scope.

**OQ5 — Internal processing sample rate (architect decision):** True peak detection requires ≥4× (prefer 8×) oversampling. The air band upper edge depends on the native Nyquist. The architect must specify whether processing runs at the native sample rate of each file or is upsampled to a fixed rate.

**OQ6 — De-mud flag discontinuity (future consideration for STORY-007):** The +4.0 dB threshold creates a step discontinuity: a source at +3.9 dB receives no correction; a source at +4.1 dB receives up to −2.0 dB correction. For cross-track consistency (STORY-007), this could produce perceptible inconsistency at the boundary. Flagged for STORY-007 design attention; no action required in STORY-006.

---

## Revision History

First issue — 2026-08-10. No prior defects.md for this story; this is a first-pass document.
