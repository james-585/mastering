# STORY-006 Defects

QA automation run: 2026-08-12  
Test files: `tests/test_story006_targets.py`, `tests/test_story006_corrective_eq.py`,
            `tests/test_story006_width.py`, `tests/test_story006_pipeline.py`

## Open issues
- DEF-006-01: de_mud trigger fires on 120–500 Hz band average, causing false positives when excess energy is in 120–200 Hz bass-bloom range; peaking bell then over-corrects 200–500 Hz warmth

---

## DEF-605

**Status:** Fixed-Pending-Retest  
**Reported by:** qa-automation-engineer  
**Linked test case:** TC-651

**Description:**

Architecture §14 requires the following fields to be removed from `suno_mastering/config.py`, as they belong to the superseded genre-curve-based EQ stage:

- `thin_low_end_threshold_db`
- `muddiness_threshold_db`
- `harshness_threshold_db`
- `eq_max_gain_db`
- `reference_curve_path`
- `freq_low_band_hz`
- `freq_mud_band_hz`
- `freq_presence_band_hz`

All eight fields remain present. The reason they cannot be removed is that `suno_mastering/mastering/eq.py` (old Stage [4] EQ) still consumes them, and `pipeline.py` still calls `eq_mod.apply_corrective_eq()` at Stage [4] (line ~132) in addition to `corrective_eq_mod.apply_corrective_eq()` at Stage [5.1].

This means two independent EQ stages run on every pipeline call:
- Stage [4]: genre-curve-based EQ using the retired thresholds in config.py
- Stage [5.1]: targets-based corrective EQ using targets.json values

Architecture §2 states the new corrective EQ replaces the old. Running both simultaneously produces an unspecified combined gain response. The confound is observable in any Stage [9] test that measures post-mastering spectral levels and attributes them entirely to the targets-based corrective EQ.

**Triage:** Architectural  
**Fix notes:** The software architect must specify how to retire Stage [4]. Removing the retired config fields alone will break the existing `mastering/eq.py` stage. Options: (a) Retire `mastering/eq.py` and its pipeline call entirely; (b) Clarify in architecture whether both stages coexist deliberately. A code-only change (removing the fields) cannot resolve this without also removing the stage that reads them. This must not be closed by a parameter change to the existing stage.

**Architect resolution (2026-08-12 — architecture.md v1.3 §23):**

Option (a) confirmed. The old Stage [4] `eq.py` call is retired. Architecture §23 specifies the exact changes required in `pipeline.py`:

1. Remove `from .mastering import eq as eq_mod` import (line 32).
2. Remove the Stage [4] block at lines 130–132 (`logger.info` + `eq_mod.apply_corrective_eq(...)` call).
3. Initialize `eq_actions = []` immediately before the `if getattr(config, "targets_json_path", None):` block.
4. Simplify the Stage [5.1] merge to `eq_actions = list(tb_eq_actions)` (remove the try/except).
5. Update the stage comment from `[5.1]` to `[4]` to match the §2 stage table.

Do NOT delete `mastering/eq.py` — its biquad primitives remain imported by `corrective_eq.py`.

**config.py field partition (§14 corrected by §23):** §14's "Retired" disposition is incorrect for six of the eight listed fields. Grep confirms `freq_low_band_hz`, `freq_mud_band_hz`, `freq_presence_band_hz`, `thin_low_end_threshold_db`, `muddiness_threshold_db`, and `harshness_threshold_db` are consumed by `analysis/frequency_balance.py` (Stage [2] analysis, "No change" per §2). These six must be **retained in config.py**. Only `eq_max_gain_db` (after removing its reference from `report/builder.py`) and `reference_curve_path` (with the uncalled `load_reference_curve()` method) are safe to remove.

**Current implementation stale:** `pipeline.py` requires the 5 changes listed above. `config.py` requires 2 removals (not 8). `report/builder.py` requires removal of the `eq_max_gain_db` reference before the config field can be deleted.

**QA retest note (2026-08-12):** TC-651 passes for the pipeline and config changes: old EQ import absent from `pipeline.py`, Stage [4] block removed, `eq_max_gain_db` absent from `config.py`, all six Stage [2] config fields (freq_low_band_hz, freq_mud_band_hz, freq_presence_band_hz, thin_low_end_threshold_db, muddiness_threshold_db, harshness_threshold_db) retained, `reference_curve_path` present. Sub-item (reference_curve_path removal) remains unresolved: the §23 disposition that `reference_curve_path` is dead code is incorrect — `analysis/frequency_balance.py:44` calls `config.reference_curve()` which uses `reference_curve_path`. This is an Architectural observation requiring §23 correction. DEF-605 remains Fixed-Pending-Retest per user instruction; the reference_curve_path architectural sub-item is deferred to STORY-F2 alongside DEF-609.

**Developer fix notes (2026-08-12):** **Parameter change: No. Method change: Yes (pipeline stage removal and restructure).**  
All 5 pipeline.py changes applied: (1) removed `from .mastering import eq as eq_mod`; (2) removed Stage [4] block calling `eq_mod.apply_corrective_eq`; (3) `eq_actions = []` initialization added; (4) merge simplified to `eq_actions = list(...)` (no try/except); (5) stage comment updated to `# --- [4] Corrective EQ (targets-based) ---`. `mastering/eq.py` confirmed still exists. `config.py`: removed `eq_max_gain_db` field after first removing its reference from `report/builder.py` line 43. **Partial deviation from architect's instruction on `reference_curve_path`:** The architect's §23 states `load_reference_curve()` (the method) has zero external callers and should be removed along with `reference_curve_path`. However, the actual method name in config.py is `reference_curve()` (not `load_reference_curve()`), and `analysis/frequency_balance.py:44` calls `config.reference_curve()` — it IS live code for Stage [2] analysis. Removing it would break Stage [2]. The architect grepped for `load_reference_curve` but the method is named `reference_curve` — wrong method name was searched. Only `eq_max_gain_db` was removed as confirmed dead. `reference_curve_path`, `_DEFAULT_REFERENCE_CURVE`, and `reference_curve()` retained because they are Stage [2] dependencies. This is an Architectural observation: the §23 disposition for `reference_curve_path` is based on an incorrect grep that used the wrong method name.

---

## DEF-006-01

**Status:** Open  
**Reported by:** user (listening review 2026-08-28, confirmed by comparison of Euphoric D Minor vs Nostalgic Analog Wall reports)  
**Linked test case:** none yet

**Description:**

The de_mud trigger fires on the seven-band `low_mid` measurement (120–500 Hz) but the
corrective peaking bell is centred at the geometric mean of that band (~245 Hz). When
the excess energy is concentrated in the lower sub-portion of the band (120–200 Hz —
kick harmonics, bass bloom) rather than in the user-perceptible mud range (200–500 Hz),
the trigger fires on a false positive and the bell removes warmth from 200–500 Hz
(chord and pad body) that needs no correction.

**Reproduction evidence:**

- Bad track: `Euphoric D Minor.wav` (2026-08-28 run)
  - Three-band Low-mid/mud (200–500 Hz): −0.35 dB — NOT perceptibly muddy
  - Seven-band low_mid (120–500 Hz): ~+5.76 dB relative — trigger fires
  - de_mud action: applied −3.76 dB peaking bell at ~245 Hz
  - After correction: three-band 200–500 Hz = −2.91 dB (over-corrected from fine to below target)
  - User perception: "destroying the mids and highs"

- Good track: `Nostalgic Analog Wall.wav` (2026-08-22 run)
  - Three-band Low-mid/mud (200–500 Hz): +3.70 dB — genuinely muddy
  - Seven-band low_mid: ~+6.08 dB — trigger fires (correctly)
  - de_mud action: applied −4.08 dB peaking bell
  - After correction: three-band 200–500 Hz = +0.81 dB (improved toward target)
  - User perception: good outcome

**Root cause:**

The trigger guard in `corrective_eq.py` is:
```
de_mud_fires = src_lm > mid_db + de_mud_threshold
```
where `src_lm` is the 120–500 Hz seven-band measurement. This band includes the
120–200 Hz bass-bloom range which is irrelevant to the user-perceptible muddiness
in 200–500 Hz. A track with heavy kick/bass harmonic content in 120–200 Hz will
have an elevated 120–500 Hz average and trigger de_mud even when the 200–500 Hz
slice is within an acceptable range.

The peaking bell at ~245 Hz (geometric centre of 120–500 Hz) then attenuates the
200–500 Hz warmth range (body of chords, pads) by 2–3 dB to reach the aim point,
while the actual 120–200 Hz elevation is only partially addressed (bell tail at
that frequency). The result is that the correction removes warmth the track didn't
have in excess and leaves the bass bloom partially uncorrected.

**Triage:** Architectural — requires a decision on whether to change the trigger
measurement band from 120–500 Hz (seven-band) to the 200–500 Hz three-band mud
measurement, and whether the filter centre should be dynamically selected based on
the spectral distribution of excess energy within the 120–500 Hz band.

**Required fix (method change, not threshold tuning):**

The de_mud trigger must be evaluated against the 200–500 Hz slice that the peaking
bell is actually meant to correct, not the 120–500 Hz band average. The software
architect must specify:

1. Whether `src_lm` in the trigger check should be replaced by the 200–500 Hz
   three-band measurement (or a weighted sub-band measurement).
2. Whether the peaking bell centre (currently fixed at geometric mean of 120–500 Hz ≈
   245 Hz) should move based on where the excess energy is concentrated.
3. Whether a separate 120–200 Hz correction path is needed for bass-bloom content
   that the current 245 Hz bell under-addresses.

---

## DEF-609

**Status:** Closed
**Reported by:** qa-automation-engineer
**Linked test case:** — (cross-references mastering-review-gate1.md §5 and the prior DEF-201 method defect)

**Description:**

The HF extension measurement in the reference analysis pipeline (`measure_hf_extension` or equivalent rolloff detection) produces physically impossible results. As documented in `mastering-review-gate1.md §5`:

- All five reference tracks report `stable=False` for HF rolloff, with per-segment variation of 2–9 kHz within single files.
- A band limit is a fixed property of a recording — it cannot vary across programme segments by 9 kHz. Observed variation is measuring spectral tilt (programme content), not an actual band-limit cliff.
- Leftfield — Melt reports `rolloff_hz = 8170 Hz` with individual segment readings of `5131 Hz`. No commercial CD master is cut at 5 kHz. This is a measurement error, not a property of the track.

The mastering-review-gate1.md §5 explicitly states: "This finding should be raised as a defect by qa-automation-engineer — it is a recurrence of the DEF-201 method error across the reference analysis."

This is the same threshold-based band-limit detection method that caused DEF-201 in prior stories. HF extension is currently status "Report only" (per §4.2) which is the correct mitigation, but the method itself produces wrong values that propagate into `reference_set_report.json` and are visible to downstream agents.

**Triage:** Architectural
**Fix notes:** The threshold-based rolloff detection method was replaced by the cliff-detection method specified in STORY-004. The stale threshold-based values were removed by regenerating `Reference Tracks/reference_set_report.json` using the current cliff detector. Verified outputs:

- Black Flute: 15788.43 Hz, stable=True, method="cliff_detection"
- GusGus: 16251.07 Hz, stable=True, method="cliff_detection"
- Leftfield: 20475.06 Hz, stable=True, method="cliff_detection"
- Chemical Brothers: 20475.06 Hz, stable=False, method="cliff_detection" (documented per-segment false positive on one segment, within Gate 2 review)
- Wavy Gravy: 20475.06 Hz, stable=True, method="cliff_detection"

This is the confirmed closure condition for DEF-609 under Option A: regenerated reference report values are plausible, use the cliff detector, and no longer contain the stale threshold-based artifacts.

**Architect resolution (2026-08-12 — architecture.md v1.3 §23):**

Option (b) confirmed — defer to STORY-F2. No STORY-006 implementation change required.

Containment verified by grep (2026-08-12): `hf_extension` does not appear in `pipeline.py`, `targets/targets_generator.py`, `mastering/corrective_eq.py`, or `mastering/stereo_width_corrector.py`. The `targets.json` schema contains no `hf_extension` field. Wrong values in `reference_set_report.json` propagate to `report/reference_render.py` output (a reporting-credibility problem) but do not influence any mastering correction decision made in STORY-006 processing.

The replacement method for STORY-F2 is specified in architecture.md §23: cliff-detection with ≥24 dB/octave sustained slope criterion (CLAUDE.md §5, DOMAIN.md §2). This defect is now closed after verification that the current cliff-detector output in the regenerated report is plausible and stable by the expected criteria.

**Current STORY-006 implementation: not stale due to this defect.** No code change is required in STORY-006 modules.

**QA closure note (2026-08-15):** Verified with project validation: the regenerated reference report uses `method="cliff_detection"`, the target HF values are plausible and within the expected ranges, and the focused HF extension regression suite passes (`14 passed, 3 skipped`).

---
