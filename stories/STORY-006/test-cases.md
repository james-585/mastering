# STORY-006 Test Cases — Mastering Targets Derivation and Corrective Processing

**Story:** STORY-006  
**Version:** 1.0  
**Date:** 2026-08-11  
**Covers:** AC1–AC23 from requirements.md §7  
**Reads from:** requirements.md v1.0, architecture.md v1.2, DOMAIN.md §3, CLAUDE.md §4–§5  

---

## How to read these test cases

**Analytical derivations are shown explicitly.** Every expected numeric value is derived from how the test signal was constructed or from the constants in architecture.md §9 — not from running the implementation and recording its output. Where the derivation is non-trivial, the arithmetic is shown in full.

**Stage [9] vs `resulting_db`:** `SpectralCorrectiveAction.resulting_db` is an arithmetic log field (source_db + applied_db). The Stage [9] post-master measurement reflects energy-weighted under-delivery (~0.60× for sub shelf, ~0.75× for low_mid bell) plus mid-band bleed (~−0.15 dB per −2.0 dB low_mid cut). These are different numbers by design. AC16 classification uses Stage [9]; log field assertions use `resulting_db`. Tests that conflate the two are wrong — and this distinction is tested explicitly in TC-657.

**Tolerance conventions:**
- Stage [9] sub band assertions: ±0.5 dB (architecture §5.2, energy-weighted delivery ~0.60×)
- Stage [9] low_mid band assertions: ±0.6 dB (architecture §5.3, ~0.75× delivery + mid-band bleed)
- All LUFS values: ±0.5 LU unless stated
- All dBTP values: stated ceiling (≤ not ≈)
- Width assertions: ±0.02 width units on programme material (architecture §20 risk 2)

**Precision:** Test assertions use 3-decimal-place values from architecture §8.1 (e.g. range_min = −3.747 for sub, not −3.75). The requirements document rounds to 2 dp for readability; architecture §8.1 and §9 provide the 3-dp values that the generator actually produces.

**Signal construction:** Prefer short synthetic signals (≤5 s) except where the analysis window requires more. Sub-band Welch estimation requires ≥10 s (architecture §17.3); those tests are marked **[Slow]**.

**Injectability:** `apply_corrective_eq(audio, sr, targets, pre_band_levels)` and `apply_stereo_width_correction(audio, sr, targets, pre_widths)` accept explicit arguments with no global state (architecture §17.2). Tests of the correction decision logic inject a synthetic `pre_band_levels` dict and a constructed `TargetsDocument` — no complex audio fixture is needed for those tests. Audio fixtures are only required for Stage [9] assertions.

---

## Section 1 — Target Generation (AC1, AC2, AC3, AC8, AC21)

### TC-601 — Generator provenance block: contributing tracks only

**Covers:** AC1  
**Type:** Functional  

**Preconditions:**  
- `reference_set_report.json` containing all five reference tracks (Chemical Brothers, GusGus, Black Flute, Leftfield, Wavy Gravy) with correct `label`, `seven_band`, `per_band_stereo_width`, and `dynamic_range_db_exact` fields.

**Steps:**  
1. Run `python generate_targets.py "Reference Tracks/reference_set_report.json" targets.json`.
2. Parse the output `targets.json`.
3. Read `provenance.contributing_tracks` array.
4. Read `provenance.excluded_tracks` array.

**Expected result:**  
- `provenance.contributing_tracks` contains exactly three entries: `"Chemical Brothers — Live Again"`, `"GusGus — Over (Arabian Horse)"`, `"Black Flute (Remastered)"` — in any order, but all three present.
- `provenance.excluded_tracks` contains exactly: `"Leftfield — Melt"` and `"Wavy Gravy"`.
- No derived numeric field (spectral min/max/median, DR values, width statistics) changes when Leftfield and Wavy Gravy entries are removed from the input JSON and the generator is re-run. (Establish baseline with all five; remove excluded two; re-run; diff numeric fields — zero difference expected.)

---

### TC-602 — Hard targets match specified values

**Covers:** AC3  
**Type:** Functional  

**Preconditions:** `targets.json` produced from the five-track `reference_set_report.json`.

**Steps:**  
1. Parse `targets.json`.
2. Read `hard_targets.integrated_lufs.value`.
3. Read `hard_targets.true_peak_dbtp.ceiling`.
4. Read `hard_targets.dynamic_range_db.target_median`, `.range_min`, `.range_max`.

**Expected result:**  
- `integrated_lufs.value` == −13.5 (exact; policy-fixed, CLAUDE.md §4.2)
- `true_peak_dbtp.ceiling` == −1.0 (exact; policy-fixed)
- `dynamic_range_db.target_median` == 8.26 — **not 8.3**. Derivation: median(8.26, 8.65, 6.60) = 8.26 (Chemical Brothers is the middle value when sorted). "DR8.3" is a conventional display label, not the stored value.
- `dynamic_range_db.range_min` == 6.60 (GusGus)
- `dynamic_range_db.range_max` == 8.65 (Black Flute)

**Note:** An implementation that stores 8.3 instead of 8.26 has hardcoded the display label. This test distinguishes them.

---

### TC-603 — Sub band 3-track statistics match architecture derivation

**Covers:** AC2, AC3  
**Type:** Functional  

**Preconditions:** `targets.json` produced from the reference set.

**Steps:**  
1. Parse `targets.json.spectral_bands.sub`.
2. Check `range_db_re_mid.min`, `.max`, and `median_db_re_mid`.

**Expected result:**  
Derivation (architecture §8.1, §9 Category A):
- Per-track sub values: Chemical Brothers +1.944, GusGus −3.085, Black Flute −3.747.
- `range_db_re_mid.min` == −3.747 (Black Flute)
- `range_db_re_mid.max` == +1.944 (Chemical Brothers)
- `median_db_re_mid` == −3.085 (GusGus; middle of sorted triple −3.747, −3.085, +1.944)
- `freq_hz` == [20, 60]
- `classification` == "soft"
- `correction_cap_db` == 2.0

**Note:** Requirements §3.4 quotes rounded values "−3.75 to +1.94" for readability. `targets.json` must store the 3-dp values.

---

### TC-604 — Low_mid band statistics and de-mud block match derivation

**Covers:** AC2, AC5  
**Type:** Functional  

**Preconditions:** `targets.json` produced from the reference set.

**Steps:**  
1. Parse `targets.json.spectral_bands.low_mid`.
2. Parse `targets.json.de_mud`.

**Expected result:**  
Derivation (architecture §8.1, §9):
- Per-track low_mid values: Chemical Brothers −0.145, GusGus +3.394, Black Flute +8.522.
- `spectral_bands.low_mid.range_db_re_mid.min` == −0.145
- `spectral_bands.low_mid.range_db_re_mid.max` == +8.522
- `spectral_bands.low_mid.median_db_re_mid` == +3.394
- `de_mud.flag_threshold_db_above_mid` == 4.0
- `de_mud.correction_aim_point_db` == 2.0 — **not 3.394**. 3.394 is the subset median which is disqualified by DOMAIN.md §5 (span 8.67 dB > 4 dB disagreement threshold).
- `de_mud.applies_to_band` == "low_mid"

---

### TC-605 — Air band upper edge resolved to 22050 Hz

**Covers:** AC2, AC8  
**Type:** Functional  

**Preconditions:** `targets.json` produced from the three contributing tracks, all at 44100 Hz sample rate.

**Steps:**  
1. Parse `targets.json.spectral_bands.air.freq_hz`.

**Expected result:**  
Derivation (architecture §4.3, §8.1): `min(24000, min(44100//2, 44100//2, 44100//2))` = `min(24000, 22050)` = 22050.
- `freq_hz[1]` (upper edge) == 22050 (numeric literal, not a string placeholder)
- `freq_hz[0]` (lower edge) == 10000

---

### TC-606 — All value fields in targets.json are numeric literals

**Covers:** AC8  
**Type:** Functional  

**Preconditions:** `targets.json` produced from the reference set.

**Steps:**  
1. Parse `targets.json`.
2. Inspect all value fields in `spectral_bands`, `stereo_width`, `hard_targets`, `de_mud`.

**Expected result:**  
- Every `median_db_re_mid`, `range_db_re_mid.min`, `range_db_re_mid.max`, `freq_hz`, `correction_cap_db`, `integrated_lufs.value`, `true_peak_dbtp.ceiling`, `dynamic_range_db.target_median`, `dynamic_range_db.range_min`, `dynamic_range_db.range_max`, `de_mud.flag_threshold_db_above_mid`, `de_mud.correction_aim_point_db` field is a JSON number (float or int), not a string.
- The document passes JSON Schema type validation with all value fields typed as `number`.

---

### TC-607 — Excluded tracks removed from report: no derived value changes (AC21 negative)

**Covers:** AC21  
**Type:** Functional  

**Preconditions:**  
- Fixture A: `reference_set_report.json` with all five tracks.
- Fixture B: same JSON with Leftfield and Wavy Gravy entries removed.

**Steps:**  
1. Run generator on Fixture A → `targets_A.json`.
2. Run generator on Fixture B → `targets_B.json`.
3. Compare all numeric derived fields: spectral min/max/median for each band, DR target_median/range_min/range_max, stereo width statistics.

**Expected result:**  
Every numeric derived value in `targets_A.json` equals the corresponding value in `targets_B.json` to full floating-point precision. No derived metric shifts when excluded tracks are removed.

---

### TC-608 — Contributing track perturbation shifts output (AC21 positive)

**Covers:** AC21  
**Type:** Functional  

**Preconditions:**  
- Fixture A: `reference_set_report.json` with five tracks.
- Fixture C: Fixture A with Chemical Brothers low_mid `relative_db` changed from −0.145 to −2.145.

**Steps:**  
1. Run generator on Fixture A → `targets_A.json`.
2. Run generator on Fixture C → `targets_C.json`.
3. Compare `spectral_bands.low_mid.range_db_re_mid.min`.

**Expected result:**  
- Fixture A: `low_mid.range_db_re_mid.min` == −0.145
- Fixture C: `low_mid.range_db_re_mid.min` == −2.145

Derivation: Chemical Brothers is the minimum in the three-track low_mid set. Shifting it by −2.0 shifts the minimum by −2.0. No other band's values change (perturbation is only to low_mid).

---

### TC-609 — Generator: missing reference_set_report.json → FileNotFoundError

**Covers:** Architecture §16 (error handling)  
**Type:** Failure mode  

**Preconditions:** `reference_set_report.json` does not exist at the specified path.

**Steps:**  
1. Run `python generate_targets.py "nonexistent/path/reference_set_report.json" targets.json`.

**Expected result:**  
- Process exits non-zero.
- Error message (stderr or exception) explicitly names the missing file path.
- No `targets.json` is written.

---

### TC-610 — Generator: contributing track absent from report → ValueError

**Covers:** AC1, architecture §4.2, §16  
**Type:** Failure mode  

**Preconditions:**  
- Fixture D: `reference_set_report.json` with Chemical Brothers entry removed (only GusGus and Black Flute present).

**Steps:**  
1. Run generator on Fixture D.

**Expected result:**  
- `ValueError` raised naming `"Chemical Brothers — Live Again"` as the unmatched track.
- Process exits non-zero.
- No `targets.json` written.

---

### TC-611 — Stereo width statistics in targets.json match derivation

**Covers:** AC2  
**Type:** Functional  

**Preconditions:** `targets.json` produced from the reference set.

**Steps:**  
1. Parse `targets.json.stereo_width`.

**Expected result:**  
Derivation (architecture §8.2):
- Per-track sub widths: Chemical Brothers 0.00916, GusGus 0.00125, Black Flute 0.04036.
- `stereo_width.sub.min` ≈ 0.001 (0.00125, GusGus)
- `stereo_width.sub.median` ≈ 0.009 (0.00916, Chemical Brothers)
- `stereo_width.sub.max` ≈ 0.040 (0.04036, Black Flute)
- Per-track low widths: Chemical Brothers 0.01650, GusGus 0.00078, Black Flute 0.14691.
- `stereo_width.low.max` ≈ 0.147 (0.14691, Black Flute)
- `stereo_width.sub.near_mono_threshold` == 0.15
- `stereo_width.sub.correction_aim_point` == 0.15
- `stereo_width.sub.correction_floor` == 0.10
- `stereo_width.sub.max_correction_step` == 0.15

---

## Section 2 — Sub Band Corrective EQ (AC4, AC9, AC14, AC15, AC16)

### TC-612 — Sub below range, cap binds: CorrectiveAction fields

**Covers:** AC4, AC15  
**Type:** Functional  

**Preconditions:**  
- Construct `TargetsDocument` with sub range [−3.747, +1.944], cap 2.0.
- Construct `pre_band_levels = {"sub": −6.247, "low_mid": 0.0, "mid": 0.0, ...}` (all other bands within range, low_mid below de-mud threshold).
- Stereo audio fixture: 3 s, 44100 Hz, two channels of white noise, any level.

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.
2. Inspect returned `List[SpectralCorrectiveAction]`.

**Expected result (derived):**  
- Exactly one `SpectralCorrectiveAction` with `band == "sub"`.
- `trigger` == `"range_compliance"` (source −6.247 is below range_min −3.747; de-mud does not apply to sub).
- `source_db` == −6.247
- `aim_point_db` == −3.747 (nearest range edge is range_min)
- `required_change` = −3.747 − (−6.247) = +2.500 dB
- `applied_db` == +2.0 (cap = 2.0 < required +2.500; applied = clamp(+2.500, −2.0, +2.0) = +2.0)
- `cap_reached` == True (abs(+2.0) < abs(+2.500))
- `resulting_db` == −6.247 + 2.0 = **−4.247** (arithmetic log field only; does NOT equal aim_point −3.747 because cap bound)

**Note:** `resulting_db = −4.247` is above range_min = −3.747? No: −4.247 < −3.747, so still outside range. AC16 classifies as "cap reached." This is expected and correct.

---

### TC-613 — Sub below range, cap does not bind: CorrectiveAction fields

**Covers:** AC4, AC15  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": −4.247, "low_mid": 0.0, "mid": 0.0, ...}`.
- All other setup as TC-612.

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result (derived):**  
- One `SpectralCorrectiveAction` with `band == "sub"`.
- `source_db` == −4.247
- `aim_point_db` == −3.747
- `required_change` = −3.747 − (−4.247) = +0.500 dB
- `applied_db` == +0.500 (cap = 2.0 > required 0.500; not capped)
- `cap_reached` == False
- `resulting_db` == −4.247 + 0.500 = **−3.747** (= range_min, arithmetic)

**Open question — AC16 energy delivery gap:** The arithmetic `resulting_db = −3.747 = range_min` suggests "met." But Stage [9] sub band measurement ≈ −4.247 + 0.60 × 0.500 = −3.947, which is 0.200 dB below range_min. AC16 has no classification for "not cap-reached but Stage [9] still outside range due to energy-weighted under-delivery." Requirements.md §3.7 rules only enumerate: met / cap-reached / informational. This gap must be resolved before the reporting classification logic is finalised. Until resolved, the test asserts `cap_reached == False` and confirms Stage [9] ∈ [−4.547, −3.447] (±0.5 dB), noting in the report that AC16 classification is pending resolution.

---

### TC-614 — Sub above range, cap binds: CorrectiveAction fields

**Covers:** AC4, AC15  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": +5.0, "low_mid": 0.0, "mid": 0.0, ...}`.

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result (derived):**  
- `band` == "sub", `trigger` == "range_compliance"
- `source_db` == +5.0, `aim_point_db` == +1.944 (range_max, nearest edge since source is above max)
- `required_change` = +1.944 − 5.0 = −3.056 dB
- `applied_db` == −2.0 (cap = 2.0; clamp(−3.056, −2.0, +2.0) = −2.0)
- `cap_reached` == True
- `resulting_db` == 5.0 − 2.0 = **+3.0** (above range_max +1.944 still; cap reached, classified accordingly)

---

### TC-615 — Sub within range: no correction applied

**Covers:** AC4, AC18 (partial)  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": 0.0, "mid": 0.0, ...}` (sub at 0.0, within [−3.747, +1.944]).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- No `SpectralCorrectiveAction` with `band == "sub"` in the returned list.
- Audio returned is unchanged for the sub band (no filter applied to sub).

---

### TC-616 — Sub at exactly range_min: no correction (boundary)

**Covers:** AC4  
**Type:** Edge case  

**Preconditions:**  
- `pre_band_levels = {"sub": −3.747, ...}` (source exactly at range_min).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- Condition: `range_min <= source_db <= range_max` evaluates True (−3.747 ≤ −3.747 ≤ +1.944).
- No sub `SpectralCorrectiveAction` emitted.

---

### TC-617 — Sub at range_min − ε: correction triggered (boundary)

**Covers:** AC4  
**Type:** Edge case  

**Preconditions:**  
- `pre_band_levels = {"sub": −3.748, ...}` (one milli-dB below range_min).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result (derived):**  
- One sub `SpectralCorrectiveAction`.
- `applied_db` == +0.001 (required = −3.747 − (−3.748) = +0.001; within cap)
- `cap_reached` == False

---

### TC-618 — Stage [9] sub band level after cap correction: analytical tolerance

**Covers:** AC14, AC16  
**Type:** Audio-quality  

**Preconditions:**  
- Synthesise a 3 s stereo signal at 44100 Hz that, when measured by `analysis.measure_all()`, reports sub band = −6.247 dB re mid (± 0.1 dB), with all other bands at 0.0 dB re mid.
- Run the full pipeline (stages [1]–[9]) with this signal as input; `targets.json` from the reference set.

**Steps:**  
1. Run mastering pipeline end-to-end.
2. Read Stage [9] post-master measurement: `after.seven_band.bands["sub"].relative_db`.
3. Inspect `SpectralCorrectiveAction` for sub band.

**Expected result (derived):**  
Applied correction: source −6.247, aim −3.747, required +2.500, cap +2.0, applied +2.0.
Stage [9] sub band ≈ source + 0.60 × applied = −6.247 + 0.60 × 2.0 = −6.247 + 1.2 = **−5.047 dB**.
Assert Stage [9] sub ∈ [**−5.547, −4.547**] dB (±0.5 dB, architecture §5.2).

AC16 classification: source −6.247 corrected with cap reached → "cap reached" (not "met").
`SpectralCorrectiveAction.resulting_db` == −4.247. Stage [9] == approximately −5.047. These differ by ~0.8 dB. This is expected; the test must not assert Stage [9] == resulting_db.

**Sanity:** Stage [9] sub must be within [−20.0, +5.0] dB (physically plausible range for sub re mid on programme material, DOMAIN.md §3).

---

### TC-619 — Low band: informational only, no filter applied

**Covers:** AC4, AC6  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low": +12.0, "low_mid": 0.0, "mid": 0.0, ...}` (low band far outside its reported range [+0.471, +8.617]).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- No `SpectralCorrectiveAction` with `band == "low"`.
- Audio returned bit-identical to audio supplied (no filter applied to any band when only low is out of range).
- `low` band appears in the report as an informational measurement only.

---

## Section 3 — Low_mid Band Corrective EQ and De-mud (AC4, AC5, AC9, AC16, AC18, AC19)

### TC-620 — Low_mid below range: range_compliance boost

**Covers:** AC4, AC15  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": −1.0, "mid": 0.0, ...}` (low_mid −1.0, below range_min −0.145).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result (derived):**  
- `band` == "low_mid", `trigger` == "range_compliance"
- `source_db` == −1.0, `aim_point_db` == −0.145 (range_min)
- `required_change` = −0.145 − (−1.0) = +0.855 dB
- `applied_db` == +0.855 (cap = 2.0 > required; not capped)
- `cap_reached` == False
- `resulting_db` == −1.0 + 0.855 = **−0.145** (= range_min, arithmetic)

**Open question — AC16 energy delivery gap (same as TC-613):** Stage [9] low_mid ≈ −1.0 + 0.75 × 0.855 = −0.359 dB, which is 0.214 dB below range_min −0.145. No AC16 category covers "corrected, cap not reached, but Stage [9] still outside range." Flag for specification clarification before reporting logic is finalised.

Stage [9] assertion: ∈ [**−0.959, +0.241**] dB (±0.6 dB).

---

### TC-621 — Low_mid above range, below de-mud threshold: range_compliance cut

**Covers:** AC4  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": +3.0, "mid": 0.0, ...}` (low_mid +3.0, inside range [−0.145, +8.522]; below de-mud threshold mid + 4.0 = 4.0 dB).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- `de_mud_fires` = (3.0 > 0.0 + 4.0) = False.
- `out_of_range` = not(−0.145 ≤ 3.0 ≤ 8.522) = False.
- No `SpectralCorrectiveAction` emitted (source is within range and de-mud not triggered).

---

### TC-622 — De-mud fires above threshold, cap binds (source +7.0)

**Covers:** AC5, AC19 (cap case where aim point cannot be discriminated by audio)  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": +7.0, "mid": 0.0, ...}`.

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result (derived):**  
- `de_mud_fires` = (7.0 > 0.0 + 4.0) = True.
- `trigger` == "de_mud"
- `source_db` == +7.0, `aim_point_db` == +2.0 (not +3.394)
- `required_change` = 2.0 − 7.0 = −5.0 dB
- `applied_db` == −2.0 (cap = 2.0; clamp(−5.0, −2.0, +2.0) = −2.0)
- `cap_reached` == True
- `resulting_db` == 7.0 − 2.0 = **+5.0** (arithmetic log field)

**Note on aim point discrimination at source +7.0:** With `aim = +3.394`: required = 3.394 − 7.0 = −3.606; cap binds; applied = −2.0; resulting_db = +5.0. Audio output is identical for both aim points at this source level — the cap binds regardless. The aim_point_db log field is the **only discriminator** here. See TC-623 and TC-624 for the discriminating interval and the primary assertion.

---

### TC-623 — AC19 Assertion 1: de-mud always logs aim_point_db == 2.0

**Covers:** AC19 (primary discriminator)  
**Type:** Functional  

**Preconditions:**  
- Three separate calls with `low_mid` at +4.5, +6.0, and +10.0 (all above threshold 4.0 dB).
- `mid` == 0.0 in all cases.

**Steps:**  
1. Call `apply_corrective_eq` for each case.
2. Read `SpectralCorrectiveAction.aim_point_db` from each.

**Expected result:**  
- All three return `aim_point_db` == **2.0** exactly.
- None return `aim_point_db == 3.394` (the subset median, which is the wrong value).

**Why this is the primary test:** At source levels above +5.394 dB, both aim points (+2.0 and +3.394) produce identical `applied_db = −2.0` and identical `resulting_db`. Log-field assertion is the only way to catch a wrong aim point at those levels. The test should run at a range of source levels, not just +7.0.

---

### TC-624 — AC19 Assertion 2: discriminating interval (source +4.5)

**Covers:** AC19 (audio-level confirmation)  
**Type:** Audio-quality  

**Preconditions:**  
- Synthesise a 3 s stereo signal at 44100 Hz with low_mid = +4.5 dB re mid (± 0.1 dB).
- Run full pipeline (stages [1]–[9]).

**Steps:**  
1. Confirm Stage [2] `before.seven_band.bands["low_mid"].relative_db` ≈ +4.5.
2. Inspect `SpectralCorrectiveAction`: `trigger`, `aim_point_db`, `applied_db`, `cap_reached`.
3. Read Stage [9] `after.seven_band.bands["low_mid"].relative_db`.

**Expected result (derived — correct implementation, aim = +2.0):**  
- `de_mud_fires` = (4.5 > 4.0) = True. `trigger` == "de_mud".
- `aim_point_db` == +2.0
- `required_change` = 2.0 − 4.5 = −2.5 dB
- `applied_db` == −2.0 (cap = 2.0; clamp(−2.5, −2.0, +2.0) = −2.0; cap reached)
- `cap_reached` == True
- `resulting_db` == 4.5 − 2.0 = +2.5 (arithmetic log field)

Stage [9] low_mid derivation:
`≈ source + 0.75 × applied + mid_bleed_correction`
For a −2.0 dB cut: 0.75 × (−2.0) = −1.5 dB energy-weighted delivery; mid-band bleed ≈ −0.15 dB on the mid band → measured low_mid-re-mid increases by +0.15 dB.
`= +4.5 − 1.5 + 0.15 = +3.15 dB`
Assert Stage [9] low_mid ∈ [**+2.55, +3.75**] dB (±0.6 dB).

**Wrong implementation (aim = +3.394) prediction:**  
- `required` = 3.394 − 4.5 = −1.106; cap does NOT bind; applied = −1.106.
- Stage [9] ≈ +4.5 + 0.75×(−1.106) + 0.15 = +4.5 − 0.830 + 0.15 = +3.82 dB.
- Upper bound of assertion is +3.75 dB; wrong implementation gives +3.82, which is 0.07 dB above — extremely tight margin.

**Conclusion:** The Stage [9] audio assertion **alone barely discriminates** the two implementations at this source level. The primary discriminator remains Assertion 1 (TC-623): `aim_point_db == 2.0` in the log. Run both assertions together for complete coverage.

---

### TC-625 — De-mud fires within range: de-mud overrides no-correction-within-range rule

**Covers:** AC5, requirements §3.7 rule 6  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": +5.0, "mid": 0.0, ...}` (low_mid +5.0, inside range [−0.145, +8.522] AND above de-mud threshold 4.0).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result (derived):**  
- `de_mud_fires` = (5.0 > 4.0) = True.
- `out_of_range` = not(−0.145 ≤ 5.0 ≤ 8.522) = False.
- De-mud governs. One `SpectralCorrectiveAction` with `trigger == "de_mud"`, `aim_point_db == 2.0`.
- `required` = 2.0 − 5.0 = −3.0, `applied` = −2.0 (cap reached), `resulting_db` = +3.0.
- **No range-compliance action emitted** (only de-mud fires in a single pass).

**Key assertion:** Correction IS applied even though source is inside the reference range. A conforming implementation must not skip de-mud simply because out_of_range is False.

---

### TC-626 — De-mud at exactly threshold (boundary)

**Covers:** AC5  
**Type:** Edge case  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": +4.0, "mid": 0.0, ...}` (source exactly at de-mud threshold mid+4.0).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- `de_mud_fires` = (4.0 > 0.0 + 4.0) = False (strict `>` per architecture §5.4 pseudocode).
- Source is within range [−0.145, +8.522]. `out_of_range` = False.
- No CorrectiveAction emitted. Audio unchanged.

---

### TC-627 — De-mud at threshold + ε: fires (boundary)

**Covers:** AC5  
**Type:** Edge case  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": +4.001, "mid": 0.0, ...}`.

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- `de_mud_fires` = (4.001 > 4.0) = True.
- One `SpectralCorrectiveAction` with `trigger == "de_mud"`, `aim_point_db == 2.0`.
- `required` = 2.0 − 4.001 = −2.001, `applied` = −2.0 (cap reached), `cap_reached` = True.

---

### TC-628 — AC18 negative control: all bands within range, no de-mud

**Covers:** AC18  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": −1.0, "low": 3.0, "low_mid": +2.0, "mid": 0.0, "high_mid": −5.0, "high": −10.0, "air": −15.0}`.
- sub = −1.0 ∈ [−3.747, +1.944] ✓
- low_mid = +2.0 ∈ [−0.145, +8.522] ✓; not > 4.0 (de-mud does not fire) ✓
- `pre_widths = {"sub": 0.10, "low": 0.10}` (both ≤ 0.15 threshold).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.
2. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.

**Expected result:**  
- Zero `SpectralCorrectiveAction` entries from step 1.
- Zero `WidthCorrectiveAction` entries from step 2.
- Audio returned from both calls is bit-identical to input audio.

**Note:** This test verifies the negative control as specified in AC18 and architecture §17.1. The `pre_band_levels` values are deliberately chosen below the de-mud threshold — a common mistake is to accidentally trigger de-mud when constructing "within range" test cases (any low_mid value above +4.0 will trigger de-mud even if within the range).

---

### TC-629 — Stage [9] low_mid after cap de-mud cut: analytical tolerance

**Covers:** AC14, AC16  
**Type:** Audio-quality  

**Preconditions:**  
- Synthesise a 3 s stereo signal at 44100 Hz with Stage [2] low_mid = +7.0 dB re mid (± 0.1 dB).
- Run full pipeline.

**Steps:**  
1. Confirm Stage [2] low_mid ≈ +7.0.
2. Read Stage [9] `after.seven_band.bands["low_mid"].relative_db`.

**Expected result (derived):**  
applied = −2.0 (cap case, from TC-622 derivation).
Stage [9] ≈ +7.0 + 0.75×(−2.0) + 0.15 = 7.0 − 1.5 + 0.15 = **+5.65 dB**.
Assert Stage [9] low_mid ∈ [**+5.05, +6.25**] dB (±0.6 dB).

AC16 classification: cap reached → "cap reached."
`SpectralCorrectiveAction.resulting_db` == +5.0. Stage [9] ≈ +5.65. The 0.65 dB discrepancy is expected and must not be treated as a defect.

---

## Section 4 — Stereo Width Correction (AC7, AC20)

### TC-630 — AC20 canonical case: sub width 0.60, cap binds

**Covers:** AC20  
**Type:** Functional  
**Duration:** ≥ 10 s [**Slow**]  

**Preconditions:**  
- Synthesise a 10 s stereo signal at 44100 Hz engineered to produce sub-band (20–60 Hz) width = 0.60 ± 0.02 as measured by `measure_per_band_stereo_width()`. (Method: decorrelated low-frequency noise summed into L and R channels with controlled side/mid energy ratio.)
- `pre_widths = {"sub": 0.60, "low": 0.10}` (injected, or measured from the fixture).

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.
2. Inspect `WidthCorrectiveAction` for sub band.
3. Measure resulting audio sub-band width using `measure_per_band_stereo_width()`.

**Expected result (derived — architecture §6.3, §6.4):**  
Step 1 — apply cap in width units:
```
w_target = max(aim_point, w_src - max_step) = max(0.15, 0.60 - 0.15) = max(0.15, 0.45) = 0.45
```
Cap is binding (w_target = 0.45 > aim_point 0.15).

Step 2 — WidthCorrectiveAction fields:
- `band` == "sub", `trigger` == "width_above_threshold"
- `source_value` == 0.60
- `aim_point` == **0.15** (not 0.10 — the floor is never the aim point)
- `applied` == −(0.60 − 0.45) = **−0.15**
- `cap_reached` == True (w_target 0.45 > aim_point 0.15)
- `resulting_value` == 0.60 + (−0.15) = **0.45**

Step 3 — verify g formula:
```
r = 0.60 / (2 − 0.60) = 0.60 / 1.40 = 0.4286
g = sqrt(0.45 × 1.40 / (0.60 × 1.55)) = sqrt(0.630 / 0.930) = sqrt(0.677) = 0.823
```
Measured sub width after correction ≈ 0.45 ± 0.02.

**Floor assertion:** `resulting_value >= 0.10` (must never breach floor; 0.45 >> 0.10 here, but the assertion must be present).

---

### TC-631 — Width aim_point is 0.15, not 0.10

**Covers:** AC20, requirements §3.5  
**Type:** Functional  

**Preconditions:**  
- `pre_widths = {"sub": 0.20, "low": 0.10}` (sub barely above threshold).

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.
2. Read `WidthCorrectiveAction.aim_point`.

**Expected result:**  
- `aim_point` == **0.15** in the emitted action.
- `aim_point` != 0.10.

**Why this test exists:** The floor (0.10) is documented as a safety bound, not the aim point. An implementation that reads `correction_floor` instead of `correction_aim_point` from `TargetsDocument` will log `aim_point == 0.10`. This test catches that error.

---

### TC-632 — Width cap does not bind: source just above threshold

**Covers:** AC7  
**Type:** Functional  

**Preconditions:**  
- `pre_widths = {"sub": 0.20, "low": 0.10}`.

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.

**Expected result (derived):**  
```
w_target = max(0.15, 0.20 - 0.15) = max(0.15, 0.05) = 0.15
```
Cap does NOT bind (w_target = 0.15 = aim_point; the step 0.05 is less than max_step 0.15, so we reach the aim).
- `applied` == −(0.20 − 0.15) = −0.05
- `cap_reached` == False
- `resulting_value` == 0.15

---

### TC-633 — Width within threshold: no correction

**Covers:** AC7, AC18 (partial)  
**Type:** Functional  

**Preconditions:**  
- `pre_widths = {"sub": 0.15, "low": 0.08}` (sub exactly at threshold; low below threshold).

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.

**Expected result:**  
- Zero `WidthCorrectiveAction` entries.
- Audio unchanged.
- Threshold condition is `w_src <= threshold` (i.e. source at exactly 0.15 does not trigger). Trigger fires only when `w_src > 0.15`.

---

### TC-634 — Low band width correction (AC7)

**Covers:** AC7  
**Type:** Functional  
**Duration:** ≥ 10 s [**Slow**]  

**Preconditions:**  
- `pre_widths = {"sub": 0.10, "low": 0.50}` (sub within threshold; low above threshold at 0.50).

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.

**Expected result (derived):**  
Sub: no action (0.10 ≤ 0.15). Low:
```
w_target = max(0.15, 0.50 - 0.15) = max(0.15, 0.35) = 0.35
cap_reached = True (0.35 > 0.15)
applied = −(0.50 − 0.35) = −0.15
resulting_value = 0.35
```
- One `WidthCorrectiveAction` with `band == "low"`, `aim_point == 0.15`, `applied == −0.15`, `resulting_value == 0.35`, `cap_reached == True`.

---

### TC-635 — Mid and higher bands: no width correction applied

**Covers:** AC7  
**Type:** Functional  

**Preconditions:**  
- `pre_widths = {"sub": 0.10, "low": 0.10, "mid": 0.80, "high_mid": 0.90, "high": 0.95, "air": 0.98}`.

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.

**Expected result:**  
- Zero `WidthCorrectiveAction` entries (sub and low are within threshold; mid and higher are not correction targets).
- Architecture §6.4 iterates only over `["sub", "low"]` — no width correction is designed for mid, high_mid, high, or air.

---

### TC-636 — Mono input to width corrector: ValueError raised

**Covers:** Architecture §16 (error handling)  
**Type:** Failure mode  

**Preconditions:**  
- `audio` is shape `(N,)` (mono, 1D array).

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.

**Expected result:**  
- `ValueError` raised with message indicating stereo audio is required and mono is not supported (per architecture §16).

---

### TC-637 — Width gain formula: w_src = 0.80 (Q1 example verification)

**Covers:** AC20, architecture §6.3  
**Type:** Audio-quality  
**Duration:** ≥ 10 s [**Slow**]  

**Preconditions:**  
- `pre_widths = {"sub": 0.80, "low": 0.10}`.

**Steps:**  
1. Call `apply_stereo_width_correction(audio, sr, targets, pre_widths)`.
2. Read `WidthCorrectiveAction` for sub band.
3. Measure sub width of resulting audio.

**Expected result (derived — architecture §6.3 Q1 example):**  
```
w_target = max(0.15, 0.80 - 0.15) = 0.65
r = 0.80 / (2 − 0.80) = 0.80 / 1.20 = 0.667
g = sqrt(0.65 × 1.20 / (0.80 × 1.35)) = sqrt(0.780 / 1.080) = sqrt(0.722) = 0.850
```
- `applied` == −0.15, `resulting_value` == 0.65, `cap_reached` == True.
- Measured sub width ≈ 0.65 ± 0.02.

**Critical:** g is derived from capped `w_target = 0.65`, not directly from the uncapped aim `0.15`. An implementation that applies the cap to g (clamps g to some value) rather than clamping w_target first will produce a different resulting width and a different `WidthCorrectiveAction.resulting_value`. This test catches that error because the expected `resulting_value` is 0.65, not 0.15.

---

### TC-638 — Width estimator same function pre and post

**Covers:** Architecture §6.2  
**Type:** Functional  

**Preconditions:**  
- A stereo audio fixture with known sub and low widths.

**Steps:**  
1. Measure sub and low widths using `measure_per_band_stereo_width()` → these feed `pre_widths`.
2. Apply width correction.
3. Stage [9] measures width using the same `measure_per_band_stereo_width()`.

**Expected result:**  
- Both the pre-correction measurement in step 1 and the Stage [9] post-correction measurement in step 3 use the same function (`measure_per_band_stereo_width`).
- The implementation does not introduce a second, internal width estimator in `stereo_width_corrector.py`.
- A code review check: `stereo_width_corrector.py` imports `measure_per_band_stereo_width` from `analysis/` for any post-correction reporting, rather than computing width via a local formula.

---

## Section 5 — Pipeline Chain Order and Integration (AC9–AC12, AC6, AC17)

### TC-639 — EQ order: sub before low_mid

**Covers:** AC9  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels` with both sub and low_mid needing correction.

**Steps:**  
1. Call `apply_corrective_eq` and observe the order of filter application.
2. Alternatively, confirm via code review: `corrective_eq.py` processes sub band first, then low_mid band.

**Expected result:**  
- Sub shelf filter is applied before the low_mid bell filter within a single `apply_corrective_eq` call.
- A test using a signal requiring both corrections confirms both `SpectralCorrectiveAction` entries are present; the sub entry's effects precede the low_mid entry in signal processing order.

---

### TC-640 — EQ (stages [4,5a]) precedes dynamics/limiting (stage [6])

**Covers:** AC10, AC11  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run with a source requiring sub EQ correction.

**Steps:**  
1. Confirm pipeline module invocation order in `pipeline.py`: stages [4] and [5a] called before stage [6].
2. Confirm Stage [2] pre-correction measurements feed stage [4] (not post-correction values).

**Expected result:**  
- `corrective_eq.apply_corrective_eq()` is called before `loudness_limit.process()`.
- `stereo_width_corrector.apply_stereo_width_correction()` is called before `loudness_limit.process()`.
- The loudness and dynamics stage sees the spectrally and spatially corrected audio.
- (Code review check on `pipeline.py` call order.)

---

### TC-641 — Dither: applied once at stage [7], not at intermediate stages

**Covers:** AC12  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run producing a 24-bit WAV output.

**Steps:**  
1. Confirm `dither.py` is called exactly once in the pipeline (after stage [6]).
2. Confirm stages [1]–[6] operate on float64 internally (no bit-depth reduction before stage [7]).

**Expected result:**  
- Exactly one call to the dither/quantize function.
- No intermediate int16 or int24 conversions before stage [7].
- Output is 24-bit WAV with TPDF dither as specified in architecture §10 (OQ4 resolution).

---

### TC-642 — High and air bands: no filter applied

**Covers:** AC6  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"sub": 0.0, "low_mid": 0.0, "high_mid": −15.0, "high": −20.0, "air": −25.0, "mid": 0.0}` (multiple bands far outside their ranges).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- No `SpectralCorrectiveAction` with `band` in `["high_mid", "high", "air"]`.
- Audio is not filtered for any of those bands.
- These bands appear in the Stage [9] report as measurements with no correction applied.

---

### TC-643 — High_mid informational: no filter (Q3 resolution)

**Covers:** AC4 (Q3 resolution), AC6  
**Type:** Functional  

**Preconditions:**  
- `pre_band_levels = {"high_mid": −15.0, "sub": 0.0, "low_mid": 0.0, "mid": 0.0, ...}` (high_mid far below its range [−13.408, −1.243]).

**Steps:**  
1. Call `apply_corrective_eq(audio, sr, targets, pre_band_levels)`.

**Expected result:**  
- No filter applied to the high_mid band.
- Zero `SpectralCorrectiveAction` entries with `band == "high_mid"`.
- `high_mid` is classified "informational" in the report, not "cap reached" or "met."

**Note:** Story.md AC4 included high_mid as a soft correction target. Gate 1 review overrides this (12.2 dB reference spread; GusGus and Black Flute aesthetically opposite). Requirements.md §7 AC4 explicitly notes gate1 governs. A developer implementing high_mid correction would be implementing out-of-specification behaviour.

---

### TC-644 — HF extension (air band) reported with explicit method caveat

**Covers:** AC17  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run on a test input.

**Steps:**  
1. Read the generated mastering report.
2. Find the air band entry.

**Expected result:**  
- Air band measurement is present in the report with a numeric value.
- Report includes explicit caveat that the HF extension method is unreliable (per gate1 §5, STORY-F2) and that the value is not used as a correction input.
- Air band `classification` field reads "informational" — not "soft" or "corrected."

---

### TC-645 — Before/after measurements for corrective bands

**Covers:** AC14  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run on a source with both sub and low_mid corrections applied.

**Steps:**  
1. Read mastering report.

**Expected result:**  
- For sub band: pre-correction measurement (`before.seven_band.bands["sub"].relative_db`) and post-correction Stage [9] measurement (`after.seven_band.bands["sub"].relative_db`) are both present and numerically different.
- For low_mid band: same.
- For all informational bands (low, high_mid, high, air): measurements present in both before and after sections; values may differ due to the sub correction's bleed into the low band (expected and documented, architecture §5.2) but no dedicated corrective action was emitted for those bands.

---

### TC-646 — Band classification in report: three-way

**Covers:** AC16  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run with: sub at −6.247 (cap reached), low_mid at +2.0 (within range, no de-mud), low band (informational).

**Steps:**  
1. Read mastering report band classification entries.

**Expected result:**  
- Sub band: classified as "cap reached" (Stage [9] still outside range, cap was binding; architecture §5.4 AC16 classification rule).
- Low_mid band: classified as "met" or "no correction needed" (Stage [9] within range; no correction applied since source was within range and below de-mud threshold).
- Low band: classified as "informational."
- Air band: classified as "informational."
- Three distinct labels (met / cap-reached / informational) are present for at least one band each in a test pipeline run that exercises all three categories.

---

### TC-647 — CorrectiveAction log fields: all required fields present

**Covers:** AC15  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run with a source triggering both a sub correction and a low_mid de-mud correction.

**Steps:**  
1. Read `SpectralCorrectiveAction` entries from the log/report.

**Expected result:**  
Every `SpectralCorrectiveAction` entry contains all required fields (architecture §7.1):
- `band` (str)
- `trigger` ("range_compliance" or "de_mud")
- `source_db` (float)
- `aim_point_db` (float)
- `applied_db` (float, negative for cut)
- `cap_reached` (bool)
- `resulting_db` (float = source_db + applied_db)

Every `WidthCorrectiveAction` entry contains all required fields (architecture §7.2):
- `band`, `trigger`, `source_value`, `aim_point`, `applied`, `cap_reached`, `resulting_value`

---

## Section 6 — Error Handling and Robustness (AC13, AC22)

### TC-648 — Missing targets.json: TargetsLoadError, non-zero exit

**Covers:** AC22, AC13  
**Type:** Failure mode  

**Preconditions:**  
- `targets.json` does not exist at `config.targets_json_path`.

**Steps:**  
1. Run mastering pipeline on any audio file.

**Expected result:**  
- `TargetsLoadError` raised before stage [1] begins.
- Process exits non-zero.
- Error message (stderr or log) explicitly names the missing file path.
- No output audio file produced.
- No default spectral values are substituted — the pipeline does not fall back to hardcoded targets.

---

### TC-649 — Invalid targets.json schema: TargetsLoadError

**Covers:** AC22  
**Type:** Failure mode  

**Preconditions:**  
- `targets.json` exists but is malformed (test with: (a) not valid JSON, (b) valid JSON but missing `hard_targets` block, (c) valid JSON with `integrated_lufs.value` as a string "−13.5" instead of a number).

**Steps:**  
1. Run mastering pipeline with each malformed fixture.

**Expected result:**  
- `TargetsLoadError` raised, specifying the failing field name.
- Non-zero exit; no output produced.
- All three malformed variants must fail loudly.

---

### TC-650 — No spectral constants in mastering source (AC13 code-review check)

**Covers:** AC13  
**Type:** Non-functional (code review)  

**Preconditions:**  
- Implementation of `suno_mastering/mastering/corrective_eq.py` complete.

**Steps:**  
1. Grep mastering source for hardcoded spectral target values:
   `grep -r "0\.47\|8\.52\|0\.145\|3\.394\|8\.617\|1\.944\|3\.747" suno_mastering/mastering/`
2. Separately verify — by code review, not grep — that the de-mud threshold (4.0), correction aim point (2.0), and correction cap (2.0) are not passed as literal float arguments to filter functions or comparison operators in `corrective_eq.py`.

**Expected result:**  
- Step 1: zero matches. Any match indicates a spectral target has been hardcoded rather than read from `TargetsDocument`.
- Step 2: All three values (`4.0`, `2.0`, `2.0`) appear in `corrective_eq.py` only as attribute reads from `TargetsDocument` fields — e.g. `targets.de_mud.flag_threshold_db_above_mid`, `targets.de_mud.correction_aim_point_db`, `targets.spectral_bands["low_mid"].correction_cap_db`. **Not** as literal floats in comparisons or filter calls.

**Critical note:** Do not run `grep "4\.0\|2\.0"` on `corrective_eq.py` — this will spuriously match `bandwidth_octaves=2.06` (the geometrically derived constant `log2(500/120)`, which legitimately appears as a literal). The bandwidth constant is derived from band edges, not a policy value; it is explicitly exempted from the AC13 check (architecture §14).

---

### TC-651 — Retired config fields removed; targets_json_path added

**Covers:** AC13  
**Type:** Non-functional (code review)  

**Preconditions:**  
- `suno_mastering/config.py` updated per architecture §14.

**Steps:**  
1. Verify the following fields are absent from `config.py`: `thin_low_end_threshold_db`, `muddiness_threshold_db`, `harshness_threshold_db`, `eq_max_gain_db`, `reference_curve_path`, `freq_low_band_hz`, `freq_mud_band_hz`, `freq_presence_band_hz`.
2. Verify `targets_json_path` is present with default pointing to `targets.json` at repo root.

**Expected result:**  
- All listed fields absent.
- `targets_json_path` present.
- `reference/progressive_house_124bpm.json` (the genre curve) no longer referenced by mastering code — its −1.5/−3.0/−4.0 dB values must not influence processing.

---

### TC-652 — Missing source audio file: non-zero exit

**Covers:** Architecture §16  
**Type:** Failure mode  

**Preconditions:**  
- `targets.json` valid. Source audio path does not exist.

**Steps:**  
1. Run `master_track.bat` (or CLI equivalent) with a non-existent input path.

**Expected result:**  
- Non-zero exit code.
- Error message names the missing file.
- No output file created.

---

### TC-653 — Corrupt/truncated audio file: non-zero exit

**Covers:** Failure mode  
**Type:** Failure mode  

**Preconditions:**  
- `targets.json` valid. Input file is a valid filename but contains only 100 bytes of random data.

**Steps:**  
1. Run mastering pipeline on the corrupt file.

**Expected result:**  
- Non-zero exit with an explicit error (soundfile / audio decode error).
- No output file created.

---

### TC-654 — sosfiltfilt design parameter halved: center gain matches applied_db

**Covers:** Architecture §5.2, §5.3 (BLOCKER 1 resolution)  
**Type:** Audio-quality  

**Preconditions:**  
- Sub correction case: synthesise a 3 s stereo 440 Hz tone (negligible sub content) with injected 40 Hz sub content at a measured level.
- `pre_band_levels = {"sub": −5.0, ...}` → sub correction required; `applied_db` = +2.0 (cap case).
- Alternatively: run the corrective EQ module in isolation with a 40 Hz sine at known amplitude and measure amplitude before and after.

**Steps:**  
1. Apply `apply_corrective_eq` with sub needing +2.0 dB boost.
2. Measure amplitude of a pure 40 Hz component (center of sub shelf ≈ effective gain region) before and after.

**Expected result:**  
- The gain at 40 Hz ≈ +2.0 dB (the `applied_db` value, not +4.0 dB which would result if the design parameter were not halved).
- Tolerance: ±0.1 dB at 40 Hz.

**Derivation:** Architecture §5.2 states: design parameter passed to `_low_shelf_sos` = `applied_db / 2`; `sosfiltfilt` doubles it, delivering `applied_db` at center frequency. If the implementation forgets to halve (passes `applied_db` directly), the shelf will deliver twice the intended gain, violating the ±2 dB cap.

---

## Section 7 — Precision and Classification (AC14, AC15, AC16)

### TC-655 — AC16 classification uses Stage [9] measurement, not resulting_db

**Covers:** AC16, architecture §5.4 AC16 classification rule  
**Type:** Functional  

**Preconditions:**  
- Source with sub = −4.247 dB (TC-613 case: applied = +0.500, arithmetic `resulting_db = −3.747 = range_min`, `cap_reached = False`).
- Stage [9] sub ≈ −3.947 (derived: −4.247 + 0.60×0.500 = −3.947; below range_min −3.747).

**Steps:**  
1. Run full pipeline; read both `SpectralCorrectiveAction.resulting_db` and Stage [9] sub measurement.
2. Read report's AC16 band classification for sub.

**Expected result:**  
- `SpectralCorrectiveAction.resulting_db` == −3.747 (arithmetic, equals range_min).
- Stage [9] sub ≈ −3.947 (below range_min − outside range despite cap not binding).
- AC16 classification is derived from Stage [9] (−3.947), not from `resulting_db` (−3.747).
- **This means the band is classified as "outside range" or "energy delivery shortfall" at Stage [9], not "met."** The report must not classify this band as "met" solely because `resulting_db == range_min`.

**Open question (as noted in TC-613):** The three-way classification (met / cap-reached / informational) has no defined label for this case. Until clarified, the test asserts Stage [9] is measured and reported correctly and that `resulting_db` is not used as the sole classification input.

---

### TC-656 — Mid-band bleed from low_mid bell cut is documented, not flagged as a defect

**Covers:** AC14, architecture §5.3  
**Type:** Functional  

**Preconditions:**  
- Full pipeline run with low_mid de-mud cut applied (−2.0 dB applied_db).

**Steps:**  
1. Read Stage [9] mid band measurement.
2. Compare to Stage [2] mid band measurement.

**Expected result:**  
- Stage [9] mid band ≈ Stage [2] mid + (−0.15 dB) for a −2.0 dB applied_db correction. Tolerance: ±0.05 dB.
- This change is expected, documented in architecture §5.3, and must be reported with a caveat ("bleed from low_mid bell cut") rather than flagged as an unexplained measurement anomaly.
- The low band (60–120 Hz) may also show ≈−1.0 dB bleed from a sub shelf (architecture §5.2) — also documented, not a defect.

---

## Section 8 — Integration and End-to-End (AC3, AC11)

### TC-657 — Loudness target −13.5 LUFS (±0.5 LU) achieved end-to-end

**Covers:** AC3, AC11  
**Type:** Audio-quality  

**Preconditions:**  
- 3 s stereo pink noise at 44100 Hz at any initial loudness level (e.g. −20 LUFS integrated).
- `targets.json` with `hard_targets.integrated_lufs.value = −13.5`.

**Steps:**  
1. Run full pipeline.
2. Measure integrated loudness (ITU-R BS.1770 K-weighted, gated) of output file.

**Expected result:**  
- Integrated loudness ∈ [−14.0, −13.0] LUFS (±0.5 LU around −13.5).
- Measurement uses `pyloudnorm` (K-weighted, gated) — not RMS, not sample peak.

---

### TC-658 — True peak ceiling −1.0 dBTP

**Covers:** AC3  
**Type:** Audio-quality  

**Preconditions:**  
- As TC-657.

**Steps:**  
1. Measure true peak of output file using 8× oversampled peak detection.

**Expected result:**  
- True peak ≤ −1.0 dBTP.
- Measurement uses oversampled peak (8× minimum), not sample peak.
- Sample peak and true peak are expected to differ on output material with inter-sample peaks — if they are identical, true peak detection is not implemented (CLAUDE.md §5, DOMAIN.md §1).

---

### TC-659 — Reproducibility: same input, bit-identical output

**Covers:** NFR (reproducibility)  
**Type:** Non-functional  

**Preconditions:**  
- Fixed input file; fixed `targets.json`.

**Steps:**  
1. Run mastering pipeline twice.
2. Compare output files with SHA-256.

**Expected result:**  
- SHA-256 hashes of both output files are identical.
- The pipeline contains no randomised processing.

---

### TC-660 — AC23: fast suite completes in ≤ 60 seconds

**Covers:** AC23  
**Type:** Non-functional  

**Steps:**  
1. Run the complete fast test suite (all tests not marked [Slow]).
2. Measure wall-clock elapsed time.

**Expected result:**  
- Total elapsed time ≤ 60 seconds on the development machine.
- [Slow] tests are excluded from this timing (they are run separately, per AC23).

---

## Section 9 — Edge Cases

### TC-661 — Silence input: no crash, no correction

**Covers:** Edge case  
**Type:** Edge case  

**Preconditions:**  
- Input: 3 s stereo silence (all samples == 0.0 exactly) at 44100 Hz.
- `targets.json` valid.

**Steps:**  
1. Run full pipeline.

**Expected result:**  
- No exception raised.
- If loudness measurement returns −∞ LUFS (gated silence), the pipeline handles this gracefully (either skips loudness correction or reports as unmeasurable).
- No NaN or Inf values in output audio.
- No division-by-zero error in width estimator (E_M and E_S could both be zero).

---

### TC-662 — Near-silence input: no divide-by-zero in width estimator

**Covers:** Edge case  
**Type:** Edge case  

**Preconditions:**  
- Input: 3 s stereo at 44100 Hz with very low amplitude (e.g. −80 dBFS white noise).

**Steps:**  
1. Run `apply_stereo_width_correction(audio, sr, targets, pre_widths)` with pre_widths from such a signal.

**Expected result:**  
- No `ZeroDivisionError` or `nan` in WidthCorrectiveAction fields.
- Width estimator handles near-zero band energy without crash.

---

### TC-663 — Full-scale input: true peak ceiling still applied

**Covers:** Edge case  
**Type:** Audio-quality  

**Preconditions:**  
- Input: 3 s stereo at 44100 Hz with sample amplitude approaching 0 dBFS (e.g. a 1 kHz sine at 0 dBFS).

**Steps:**  
1. Run full pipeline.
2. Measure true peak of output.

**Expected result:**  
- True peak ≤ −1.0 dBTP.
- No clipping (sample values all within [−1.0, +1.0] before dither).

---

### TC-664 — DC offset input: EQ and width correction do not crash

**Covers:** Edge case  
**Type:** Edge case  

**Preconditions:**  
- Input: 3 s stereo at 44100 Hz; both channels have a +0.1 DC offset added to pink noise.

**Steps:**  
1. Run `apply_corrective_eq` and `apply_stereo_width_correction`.

**Expected result:**  
- No exception.
- Output audio contains no NaN or Inf.
- DC offset may pass through (corrective EQ is not a DC removal filter); the test only asserts no crash.

---

### TC-665 — Very short file: shorter than analysis window

**Covers:** Edge case  
**Type:** Edge case  

**Preconditions:**  
- Input: 0.1 s stereo at 44100 Hz (4410 samples — shorter than a typical Welch window of 65536 samples).

**Steps:**  
1. Run full pipeline.

**Expected result:**  
- Pipeline either completes with a warning about insufficient data for some measurements, or exits with a clear error.
- No unhandled exception (no IndexError, no silent NaN propagation).
- If it completes: output file is valid audio.

---

### TC-666 — 48 kHz input: pipeline handles without forced resampling

**Covers:** NFR (multi-sample-rate)  
**Type:** Functional  

**Preconditions:**  
- Input: 3 s stereo at **48000 Hz** (not 44100 Hz).
- `targets.json` valid (generated from 44100 Hz reference tracks; air band upper edge = 22050 Hz).

**Steps:**  
1. Run full pipeline.
2. Check output sample rate.

**Expected result:**  
- Output sample rate == 48000 Hz (native rate preserved; no forced resampling to 44100 Hz).
- Pipeline uses `soundfile` (not `librosa.load`) which preserves sample rate.
- Air band displayed upper edge in report is clamped to `min(22050, 24000)` = 22050 Hz (from targets.json), even though Nyquist of this source is 24000 Hz. This clamping is a report artefact (architecture §4.3).
- No crash or silent resampling.

---

### TC-667 — Idempotency: re-processing already-corrected audio

**Covers:** Correctness (idempotency)  
**Type:** Functional  

**Preconditions:**  
- Run the pipeline once on a source needing sub and low_mid corrections → output_1.wav.
- Run the pipeline again on output_1.wav → output_2.wav.

**Steps:**  
1. Inspect Stage [2] measurements for the second run on output_1.wav.
2. Inspect CorrectiveAction log for second run.

**Expected result:**  
- Second-run sub band level is within [range_min, range_max] (correction already applied in first run). No sub `SpectralCorrectiveAction` in second run, or if applied, applied_db is near zero.
- Second-run loudness is close to −13.5 LUFS already; limiting applies minimal additional gain.
- Outputs are not compared for bit-identity (loudness stage may re-apply small corrections), but the second run must not degrade dynamic range substantially below the first run's DR target.
- No crash. This is a "behave sensibly" check, not a bit-identity requirement.

---

### TC-668 — Non-contributing tracks in reference JSON: not an error

**Covers:** AC21, architecture §4.2  
**Type:** Functional  

**Preconditions:**  
- `reference_set_report.json` containing all five tracks (three contributing + Leftfield + Wavy Gravy).

**Steps:**  
1. Run generator.

**Expected result:**  
- Generator completes without error.
- Non-matching entries (Leftfield, Wavy Gravy) are silently skipped.
- `targets.json` produced with correct values (same as TC-601).

---

### TC-669 — Sub-band width Welch stability: 10 s fixture vs 3 s fixture

**Covers:** Architecture §17.3, AC20  
**Type:** Non-functional [**Slow**]  

**Preconditions:**  
- Fixture A: 3 s stereo signal engineered for sub width = 0.60.
- Fixture B: 10 s stereo signal engineered for sub width = 0.60 (same method).

**Steps:**  
1. Measure sub band width from Fixture A 10 times using `measure_per_band_stereo_width()` — report variance.
2. Measure sub band width from Fixture B 10 times — report variance.

**Expected result:**  
- Fixture A measurements: variance in sub width measurement likely high (inadequate Welch averaging windows).
- Fixture B measurements: variance in sub width measurement ≤ 0.02 width units standard deviation.
- This confirms architecture §17.3's requirement that width fixtures for sub-band tests must be ≥10 s.

---

## Section 10 — Sanity Assertions (Catch Physically Impossible Output)

These apply to every full-pipeline run regardless of test case. They require no ground truth and should be checked in every test that exercises the full pipeline.

| Assertion | Rationale |
|---|---|
| Integrated loudness ∈ [−20, −5] LUFS | Outside this range on commercial material is a severe error (DOMAIN.md §3) |
| True peak ≤ −1.0 dBTP | Hard ceiling from requirements |
| True peak ≠ sample peak | Proves oversampling is implemented (DOMAIN.md §1, CLAUDE.md §5) |
| Output sample rate == input sample rate | Confirms no silent resampling |
| Width of any measured band ∈ [0.0, 1.0] | Correlation-derived width is bounded; outside is physically impossible |
| `SpectralCorrectiveAction.applied_db` ∈ [−2.0, +2.0] | Cap is normative; outside this means cap logic is broken |
| `WidthCorrectiveAction.resulting_value` ≥ 0.10 | Floor assertion; below 0.10 is a programming error (architecture §6.4) |
| No NaN or Inf in any audio sample at any stage | Indicates divide-by-zero or filter instability |
| Output sample count ≈ input sample count (within 1 s) | Confirms no unintentional truncation |

---

## Traceability Table

| AC | Description | Test Cases |
|---|---|---|
| AC1 | targets.json from 3-track subset; contributing/excluded tracks named | TC-601, TC-609, TC-610 |
| AC2 | Every target has median, min, max from subset | TC-603, TC-604, TC-605, TC-611 |
| AC3 | Hard targets: −13.5 LUFS, −1.0 dBTP, DR8.26, range 6.60–8.65 | TC-602, TC-657, TC-658 |
| AC4 | Soft targets: sub, low_mid; low/high_mid reclassified informational | TC-612–TC-619, TC-620, TC-621, TC-639, TC-640, TC-642, TC-643 |
| AC5 | De-mud: flag > mid+4 dB; aim +2.0 dB, not median | TC-622–TC-627 |
| AC6 | High and air: report-only, no filter | TC-642, TC-643 |
| AC7 | Width: sub/low corrected toward 0.15; mid+ informational; no widening | TC-630–TC-638 |
| AC8 | targets.json is valid machine-readable JSON; all numeric literals | TC-606 |
| AC9 | EQ order: sub → low_mid; before dynamics | TC-639, TC-640 |
| AC10 | Dynamics after EQ | TC-640 |
| AC11 | Loudness/limiting after dynamics | TC-640, TC-641, TC-657 |
| AC12 | Dither: last, once, at final bit-depth reduction | TC-641 |
| AC13 | No hardcoded spectral constants; absent targets.json fails loudly | TC-648, TC-649, TC-650, TC-651 |
| AC14 | Before/after measurements for every corrective band | TC-645, TC-647, TC-655, TC-656 |
| AC15 | Correction log: what was applied and why | TC-617, TC-647 |
| AC16 | Report classification: met / cap-reached / informational | TC-618, TC-629, TC-646, TC-655 |
| AC17 | HF extension reported with method caveat | TC-644 |
| AC18 | Negative control: source within range → no correction | TC-615, TC-628, TC-633 |
| AC19 | De-mud discriminator: aim = +2.0 not +3.394 | TC-623 (primary), TC-624 (audio) |
| AC20 | Width test: source 0.60 → corrected; aim_point 0.15 not 0.10; cap correctly in width units | TC-630, TC-631, TC-637 |
| AC21 | Excluded tracks absent from derived targets | TC-607, TC-608, TC-668 |
| AC22 | Absent targets.json: clear error, non-zero exit | TC-648, TC-649 |
| AC23 | Fast suite ≤ 60 s | TC-660 |

---

## Coverage Checklist

| Category | Coverage |
|---|---|
| Happy path for each AC | TC-601 to TC-640 cover all 23 ACs |
| Boundary: exactly at threshold | TC-616 (sub range_min), TC-626 (de-mud at exactly 4.0), TC-627 (at 4.001), TC-633 (width at 0.15) |
| Boundary: just under and just over | TC-617 (sub range_min − ε), TC-627 (de-mud + ε) |
| Idempotency | TC-667 |
| Bypass / disabled stage | TC-615, TC-628 (no correction when in-range) |
| Mono input | TC-636 (mono → ValueError from width corrector); mono mastering otherwise out of scope |
| Stereo input | All main test cases |
| 44.1 kHz | All reference-derived tests |
| 48 kHz | TC-666 |
| Silence | TC-661 |
| Near-silence | TC-662 |
| Full-scale / clipping input | TC-663 |
| Very quiet input | TC-662 |
| DC offset | TC-664 |
| Very short file | TC-665 |
| Corrupt file | TC-653 |
| Unsupported / missing file | TC-652, TC-653 |
| Missing targets.json | TC-648, TC-649 |
| Wrong channel count | TC-636 |
| LUFS vs dBFS vs dBTP distinguished | TC-657 (LUFS), TC-658 (dBTP), TC-654 (dB gain) — all explicitly labelled |
| Sample peak ≠ true peak | TC-658 (sanity assertion) |
| Regression test label | TC-654 is the borderline case — it verifies the halved design parameter. If the implementation had the wrong convention and was "corrected" by measurement, this would be a regression lock. The test is analytical (the gain formula derives the expected 2.0 dB from the convention spec), not observational. |

---

## Open Questions Affecting Test Cases

**OQ-T1 — AC16 energy-delivery gap (affects TC-613 and TC-620):**  
When `cap_reached == False` but Stage [9] is still outside range due to energy-weighted under-delivery (~0.60× for sub, ~0.75× for low_mid), requirements.md §3.7's three-way classification (met / cap-reached / informational) has no defined label. TC-613 and TC-620 flag this and assert Stage [9] measurements are within derived tolerances, but suspend the AC16 classification assertion until the spec is clarified. The test-case-writer recommends adding a fourth category: "corrected, target not reached (energy delivery shortfall)."

**OQ-T2 — AC19 Assertion 2 tolerance margin (0.07 dB) at source +4.5 dB:**  
TC-624 notes that the Stage [9] assertion barely discriminates a correct implementation (Stage [9] ≈ +3.15) from a wrong one using aim +3.394 (Stage [9] ≈ +3.82). The 0.07 dB margin between the wrong implementation's Stage [9] and the assertion's upper bound (+3.75) is tighter than the stated ±0.6 dB tolerance. TC-623 (Assertion 1 on the log field) must always be run alongside TC-624 for complete AC19 coverage. The automation engineer should note that TC-624 alone may produce a false pass if implementation tolerances are slightly different — Assertion 1 is the definitive test.

---

## Revision History

First issue — 2026-08-11. No `stories/STORY-006/defects.md` exists; no defect-driven coverage gaps to close.
