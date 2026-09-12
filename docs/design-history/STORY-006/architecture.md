# STORY-006 Architecture — Mastering Targets Derivation and Corrective Processing

**Version:** 1.3
**Date:** 2026-08-12
**Status:** Revised — see §23

---

## Contract

```
Consumes:  reference_set_report.json  (STORY-005 — Reference Tracks/reference_set_report.json)
           mastering-review-gate1.md  (gating document for this story)
Produces:  targets.json               (machine-readable JSON; schema in requirements.md §3)
           Updated mastering chain with corrective EQ and per-band stereo width correction
Consumed by: STORY-007 (batch processing and reporting)
```

---

## 1. Design Intent

STORY-006 does two separable things:

1. **Offline target generation.** A standalone module (`suno_mastering/targets/targets_generator.py`) reads `reference_set_report.json`, selects the three contributing tracks, computes spectral and stereo width statistics, and writes `targets.json`. A thin repo-root shim `generate_targets.py` delegates to `suno_mastering.targets.targets_generator.main()`. Generation runs once and the result is committed to the repository. The mastering chain does not regenerate it.

2. **Runtime corrective processing.** The existing 10-stage pipeline is extended with two new modules — `mastering/corrective_eq.py` and `mastering/stereo_width_corrector.py` — inserted before the existing dynamics/loudness solver stage. Both modules read `targets.json` at startup; absent or invalid `targets.json` is a hard startup failure.

The existing STORY-001 pipeline is **extended**, not replaced. The existing `mastering/eq.py` biquad primitives (`_peaking_sos`, `_low_shelf_sos`, `_normalize_sos`) are reused by the new `corrective_eq.py`. The existing `mastering/stereo_correct.py` broadband windowed stereo element correction is retained and runs after the new per-band narrowing.

---

## 2. Updated Pipeline Stage Order

The normative chain order is from DOMAIN.md §5 and gate1 §3: corrective EQ → dynamics/glue → loudness and limiting → dither. The existing STORY-001 pipeline does not have a separate dynamics stage — the loudness/limiting solver (`mastering/loudness_limit.py`, stage [6]) integrates glue compression toward DR8.3 with loudness targeting. No additional compressor is introduced by this story; what gate1 calls "dynamics/glue" is implemented by stage [6].

The updated pipeline:

| Stage | Name | Module | Change |
|---|---|---|---|
| [1] | Ingest & Validate | `io/ingest.py` | No change |
| [2] | Pre-Master Analysis | `analysis/` + `measure_all()` | No change — measures pre-correction state |
| [3] | Resample (conditional) | `mastering/resample.py` | No change |
| **[4]** | **Corrective EQ** | **`mastering/corrective_eq.py`** (new) | **Replaces old `eq.py` call** |
| **[5a]** | **Per-Band Stereo Width Correction** | **`mastering/stereo_width_corrector.py`** (new) | **New stage** |
| [5b] | Broadband Stereo Element Correction | `mastering/stereo_correct.py` | No change — runs after per-band correction |
| [6] | Loudness/Limiting (+ dynamics) | `mastering/loudness_limit.py` | No change |
| [7] | Dither & Bit-Depth Conversion | `mastering/dither.py` | No change — 24-bit WAV + TPDF, as STORY-001 |
| [8] | Export | `io/export.py` | No change |
| [9] | Post-Master Analysis | `analysis/` + `measure_all()` | No change |
| [10] | Report Generation | `report/builder.py` | Updated to include CorrectiveAction log |

**Stage interaction — [5a] and [5b]:** Both narrow the stereo image but via different mechanisms. Stage [5a] applies a whole-track per-band gain reduction to the S (side) component of the sub (20–60 Hz) and low (60–120 Hz) bands only. Stage [5b] applies windowed broadband M/S narrowing to time-windows detected as having abnormal correlation in stage [2]. Their triggers and frequency scope are disjoint; both CorrectiveAction logs must be reported separately so the test-case-writer and reporting stage can distinguish them.

**Resolving the "dynamics/glue" conflict:** The STORY-001 pipeline note refers to stage [6] as "Loudness/Limiting," but gate1 §3 and DOMAIN.md §5 both name a "dynamics/glue" step between EQ and loudness. These refer to the same stage: `loudness_limit.py`'s DR solver provides glue compression by targeting DR8.3. No new compressor is introduced. The requirement that dynamics respond to spectral balance is satisfied by running stages [4] and [5a] before stage [6].

---

## 3. Module Layout — New and Changed Files

### New files

```
suno_mastering/
  targets/
    __init__.py
    loader.py                # load_targets(path) -> TargetsDocument; raises TargetsLoadError
    schema.py                # TargetsDocument dataclass + JSON deserialization
    targets_generator.py     # generation logic + main(); CLI: python -m suno_mastering.targets.targets_generator
  mastering/
    corrective_eq.py         # apply_corrective_eq_v2(audio, sr, targets) -> (audio, List[SpectralCorrectiveAction])
    stereo_width_corrector.py   # apply_stereo_width_correction(audio, sr, targets, pre_widths) -> (audio, List[WidthCorrectiveAction])
  report/
    corrective_actions.py    # SpectralCorrectiveAction, WidthCorrectiveAction dataclasses

generate_targets.py          # Repo-root shim: from suno_mastering.targets.targets_generator import main; main()
                             # Usage: python generate_targets.py <report.json> <targets.json>
```

### Existing files changed

| File | Change |
|---|---|
| `suno_mastering/pipeline.py` | Import and call `corrective_eq.py` and `stereo_width_corrector.py`; load `targets.json` at startup; pass `CorrectiveAction` lists to report builder; remove old `eq.py` call |
| `suno_mastering/config.py` | Add `targets_json_path`; remove retired spectral constants (see §14) |
| `suno_mastering/report/builder.py` | Accept and render spectral and width `CorrectiveAction` lists; add band classification column (met / cap reached / informational) |

### Existing files unchanged

`mastering/eq.py` — its biquad primitives (`_peaking_sos`, `_low_shelf_sos`, `_normalize_sos`, `_band_center_hz`, `_band_bandwidth_octaves`) are imported by `corrective_eq.py`. The `apply_corrective_eq()` function in `eq.py` is no longer called from the pipeline; it remains for backward compatibility but is deprecated by this story.

---

## 4. targets_generator.py Design

### 4.1 Inputs and outputs

**Input:** `Reference Tracks/reference_set_report.json` — a JSON array of `ReferenceMeasurements` objects serialised by STORY-005.

Key consumed fields per track:
- `label: str` — human-readable track name; used for contributor matching (see §4.2)
- `track_path: str` — fallback for label matching (filename component only)
- `seven_band.bands[n].band: str` — band name ("sub", "low", etc.)
- `seven_band.bands[n].relative_db: float` — dB re mid band
- `per_band_stereo_width.bands[n].band: str`
- `per_band_stereo_width.bands[n].width: float`
- `dynamic_range_db_exact: float` — unrounded TT DR value
- `core.sample_rate: int` — for Nyquist computation

**Output:** `targets.json` conforming to schema in requirements.md §3.

### 4.2 Track selection — contributing subset

The generator maintains a hardcoded list of contributing track names (UTF-8, em dashes as in requirements.md §3.2):

```
contributing_tracks = [
    "Chemical Brothers — Live Again",
    "GusGus — Over (Arabian Horse)",
    "Black Flute (Remastered)",
]
```

Matching is performed by Unicode NFKC normalization of both the configured name and the `label` field in each `ReferenceMeasurements` entry, followed by case-insensitive comparison. If `label` is None, the filename component (stem only, no extension) of `track_path` is used.

**Contributor count assertion:** After iterating through the JSON, the generator asserts that exactly `len(contributing_tracks)` (= 3) contributors have been resolved. If any configured contributing track fails to match any entry, the generator raises `ValueError` naming the unmatched track — it does not silently proceed with fewer than 3. This satisfies the brief's "fails loudly if file absent or wrong tracks present": the "wrong tracks" case is a track from the contributing list that is absent from or unresolvable in the JSON.

**Non-contributing tracks (Leftfield, Wavy Gravy) are not an error.** The five-track `reference_set_report.json` legitimately contains all five tracks; this is the designed input format. Non-matching entries are silently ignored. Leftfield and Wavy Gravy data are read and stored in `provenance.excluded_tracks` only; they are never used in statistical computation.

**Label encoding note:** If `label` fields were serialised with different em-dash encoding variants or trailing whitespace, NFKC normalization handles them. If a label was serialised as an ASCII hyphen (`--`) rather than em-dash (`—`), the match will fail and the generator must log all `label` values it encountered alongside the unmatched contributing name, to aid debugging.

### 4.3 Computation

For each spectral band across the three contributing tracks, the generator computes:
- `min` = `min(relative_db_chem, relative_db_gusgus, relative_db_blackflute)`
- `max` = `max(...)`
- `median` = median of the three values

For stereo width per band: same statistics on the `width` field.

For dynamic range: statistics on `dynamic_range_db_exact` across the three tracks.

All computations use the `statistics.median()` function for robustness (exact for n=3: the middle of the sorted triple).

**Air band upper edge:** The air band upper edge in `targets.json` is set to `min(24000, min(sr // 2 for each contributing track))` — the minimum Nyquist across all three contributing tracks, capped at 24000 Hz. This is conservative: if any contributing track has a lower sample rate, the air upper edge does not extend above that track's actual content. All three contributing tracks are expected to be at 44100 Hz (Nyquist = 22050 Hz); the expected value in targets.json is therefore `min(24000, 22050) = 22050` Hz. See §8.1 for the resulting band label.

At **report time**, the mastering pipeline clamps the displayed air band upper edge to `min(targets.spectral_bands.air.freq_hz.max, source_nyquist_hz)` to avoid reporting above the source's own Nyquist. This clamping is a reporting artefact only; it does not change `targets.json`.

### 4.4 OQ3 resolution — generation trigger

**Generate once, commit to repository.** `targets.json` is not regenerated on each mastering run. It is regenerated explicitly by running:

```
python generate_targets.py "Reference Tracks/reference_set_report.json" targets.json
```

This keeps mastering runs fast and reproducible. `targets.json` is read at mastering startup; an absent file is a hard failure with a clear error message and non-zero exit.

If `reference_set_report.json` changes (e.g. after a STORY-005 fix), the mastering engineer regenerates `targets.json` manually and commits both. This is a deliberate forcing function: changing reference analysis requires explicit target review.

---

## 5. corrective_eq.py Design

### 5.1 Interface

```python
def apply_corrective_eq(
    audio: np.ndarray,    # float64, shape (N,) mono or (N, 2) stereo
    sr: int,
    targets: TargetsDocument,
    pre_band_levels: dict[str, float],  # pre-correction relative_db per band, from stage [2] analysis
) -> tuple[np.ndarray, list[SpectralCorrectiveAction]]:
```

`pre_band_levels` is derived from `before.frequency_balance` seven-band measurement (stage [2] result). Keys are band names matching requirements.md §3.4; values are `relative_db` floats.

Returns the (possibly modified) audio array and a list of CorrectiveAction entries. If no correction is applied, the list is empty and the audio is returned unmodified.

### 5.2 Filter design — sub band

**Filter type:** Low shelf (RBJ cookbook, `_low_shelf_sos` from `mastering/eq.py`).

**Corner frequency:** 60 Hz (the upper edge of the sub band, 20–60 Hz). Placing the shelf corner at the band top is consistent with the existing `eq.py` pattern and concentrates the gain within the sub band.

**Slope:** 1.0 (standard RBJ shelf slope, the existing `_low_shelf_sos` default).

**sosfiltfilt gain convention:** `sosfiltfilt` applies the filter forward and then backward, delivering `|H(f)|²` — twice the dB response of the design parameter. A `gain_db` design of X dB delivers 2X dB at output. To deliver `applied_db` dB as the logged and intended gain, the value passed to `_low_shelf_sos` is `applied_db / 2`. `SpectralCorrectiveAction.applied_db` logs the delivered gain (not the design parameter). See §7.1.

**Energy-weighted band delivery:** The sub shelf delivers approximately **0.60 × applied_db** as an energy-weighted band average across 20–60 Hz. Music energy in the sub band concentrates toward 40–60 Hz rather than 20–25 Hz; the shelf gain is lower at those frequencies than at DC. For a ±2.0 dB applied_db, the energy-weighted sub band change is approximately ±1.2 dB. The Stage [9] sub band measurement will reflect this shortfall; test tolerances for Stage [9] sub band level assertions should be ±0.5 dB.

**Gain:** determined by the range compliance rule:
- If `source_sub_db < targets.spectral_bands.sub.range_min`: gain = min(+cap, range_min - source_sub_db)
- If `source_sub_db > targets.spectral_bands.sub.range_max`: gain = max(-cap, range_max - source_sub_db)
- If within range: no filter applied.

where `cap = targets.spectral_bands["sub"].correction_cap_db` (= 2.0, from targets.json). The cap is never read from `config.py`.

**Bleed into adjacent low band (60–120 Hz):** A RBJ low shelf at 60 Hz with slope 1.0 delivers approximately 50% of the shelf gain at one octave above the corner (120 Hz). For a ±2.0 dB applied_db shelf, the bleed at 120 Hz is approximately ±1.0 dB. The low band (60–120 Hz) is classified as informational; this bleed affects the post-correction band measurement but does not trigger any further correction. This is documented in the report caveat for the low band.

### 5.3 Filter design — low_mid band

**Filter type:** Wide peaking bell (RBJ cookbook `_peaking_sos` from `mastering/eq.py`), using the bandwidth-octaves parameterization.

**Center frequency:** `f0 = sqrt(120 × 500) = 244.9 Hz` (geometric mean of band edges).

**Bandwidth:** `BW = log2(500 / 120) = 2.06 octaves` (full band span). This is the standard RBJ bandwidth-in-octaves approach used in the existing `eq.py`. Note: `2.06` is a geometrically derived constant from the band edges; it is not a policy value and may appear as a literal or named constant in `corrective_eq.py`.

**sosfiltfilt gain convention:** The value passed to `_peaking_sos` is `applied_db / 2`, so sosfiltfilt delivers `applied_db` dB at center frequency (244.9 Hz). At the bandwidth edges (120 Hz and 500 Hz), sosfiltfilt delivers `applied_db / 2` (single-pass RBJ delivers half-gain at the bandwidth edge; sosfiltfilt doubles it, giving `2 × applied_db/2 × 0.5 = applied_db / 2`).

**Energy-weighted band delivery:** The low_mid bell delivers approximately **0.75 × applied_db** as an energy-weighted band average across 120–500 Hz. The full `applied_db` is delivered only at center (244.9 Hz); delivery tapers toward `applied_db / 2` at the bandwidth edges (120 Hz and 500 Hz). For a ±2.0 dB applied_db, the energy-weighted band change is approximately ±1.5 dB. The Stage [9] low_mid measurement will reflect this shortfall.

**Bleed into mid reference band (500–2000 Hz):** In the RBJ bandwidth-in-octaves parameterization, the gain at the bandwidth edges (±BW/2 octaves from center) equals half the peak gain in dB. 500 Hz is at exactly +1.03 octaves above center (244.9 Hz), which is at the BW/2 boundary. Therefore, for any `applied_db` delivered at center:

> **Response at 500 Hz = applied_db × 0.5 (dB)**

Here `applied_db` is the delivered center gain (not the design parameter `applied_db / 2` passed to `_peaking_sos`). The bleed figures in this section describe what sosfiltfilt delivers using the `applied_db / 2` design-parameter convention and are correct as stated: for a −2.0 dB applied_db correction, −1.0 dB at 500 Hz.

The filter then rolls off as frequency increases above 500 Hz. The integrated power change in the 500–2000 Hz mid reference band is approximately −0.15 dB for a −2.0 dB applied_db center correction (conservative estimate: −1.0 dB at 500 Hz tapering to ≈0 dB at ~1000 Hz; the band spans 2 octaves, so the bottom octave carries about half the weight on a log scale).

**Impact on AC19 assertion 2:** Assertion 2 uses a source at +4.5 dB and a separation of 0.89 dB between the two aim points. The filter bleed shifts the post-correction mid-reference measurement by ≈−0.15 dB, which causes the measured `resulting_db` to overstate by ≈+0.15 dB. This is less than one-sixth of the 0.89 dB separation and does not invalidate assertion 2.

**Semantic clarification:** `SpectralCorrectiveAction.resulting_db` is computed arithmetically as `source_db + applied_db` (not re-measured from the audio). The Stage [9] post-master measurement will differ from this arithmetic value by the filter bleed amount and the energy-weighted band delivery shortfall (see above). The report must distinguish between `CorrectiveAction.resulting_db` (nominal intended outcome for logging) and the Stage [9] after-measurement (actual outcome); they are different numbers for known reasons. AC16 pass/fail classification uses Stage [9], not `resulting_db` — see §5.4.

### 5.4 Correction logic — single pass, cap, de-mud

**Single-pass rule:** For each band (sub, then low_mid), at most one filter operation is applied per track per pipeline run. No iteration.

**Sub band correction:**
1. Measure `source_db = pre_band_levels["sub"]`
2. If within range `[range_min, range_max]`: skip. Return no action.
3. Determine `aim_point_db`: the nearest range edge (range_min if below, range_max if above).
4. Compute `required_change = aim_point_db - source_db`
5. `cap = targets.spectral_bands["sub"].correction_cap_db`
6. `applied_db = clamp(required_change, -cap, +cap)`
7. Apply `_low_shelf_sos(sr, f0=60.0, gain_db=applied_db / 2)` via `sosfiltfilt(sos, audio, axis=0)`. Passing `applied_db / 2` to the design function so that sosfiltfilt's forward-backward application delivers the full `applied_db` at every frequency.
8. Emit `SpectralCorrectiveAction(band="sub", trigger="range_compliance", ...)`

**Low_mid band correction — decision tree:**

```
source_db = pre_band_levels["low_mid"]
mid_db = pre_band_levels["mid"]   # always 0.0 by definition

# All thresholds read from TargetsDocument — never literal in corrective_eq.py
de_mud_threshold = targets.de_mud.flag_threshold_db_above_mid   # 4.0 from targets.json
de_mud_aim       = targets.de_mud.correction_aim_point_db        # 2.0 from targets.json
cap              = targets.spectral_bands["low_mid"].correction_cap_db  # 2.0 from targets.json
range_min        = targets.spectral_bands["low_mid"].range_db_re_mid.min
range_max        = targets.spectral_bands["low_mid"].range_db_re_mid.max

de_mud_fires = (source_db > mid_db + de_mud_threshold)
out_of_range = not (range_min <= source_db <= range_max)

if de_mud_fires:
    trigger = "de_mud"
    aim_point_db = de_mud_aim
elif out_of_range:
    trigger = "range_compliance"
    aim_point_db = nearest range edge
else:
    # No correction
    return audio, []

required_change = aim_point_db - source_db
applied_db = clamp(required_change, -cap, +cap)
cap_reached = (abs(applied_db) < abs(required_change))
resulting_db = source_db + applied_db   # arithmetic nominal intent; NOT used for AC16 classification
```

**Single trigger per pass:** If both de_mud and out-of-range would fire, de_mud governs (requirements.md §3.7 rule 6). No second pass is applied.

**Filter application:** `_peaking_sos(sr, f0=244.9, gain_db=applied_db / 2, bandwidth_octaves=2.06)` via `sosfiltfilt(sos, audio, axis=0)` (zero-phase). Passing `applied_db / 2` so that sosfiltfilt delivers `applied_db` at center frequency (244.9 Hz) and `applied_db / 2` at the bandwidth edges (120 Hz, 500 Hz). Applied identically to both channels on the interleaved `(N, 2)` array; never M/S, as this would alter the stereo image in the mid/high bands.

**AC16 classification rule:** The three-way band classification (met / cap-reached / informational) uses the Stage [9] post-correction measurement, not `resulting_db`. `resulting_db = source_db + applied_db` is the nominal intended outcome for logging only and does not account for energy-weighted under-delivery across the band. A source 1.5 dB below `range_min` with `applied_db = +1.5 dB` logs `resulting_db = range_min` ("met"), but the Stage [9] measurement reflects ~0.9 dB energy-weighted delivery and may classify the band as still outside range. Classification must use Stage [9] to avoid false "met" reports.

---

## 6. stereo_width_corrector.py Design

### 6.1 Interface

```python
def apply_stereo_width_correction(
    audio: np.ndarray,               # float64, shape (N, 2) — stereo only; mono not supported
    sr: int,
    targets: TargetsDocument,
    pre_widths: dict[str, float],    # band_name -> width, from stage [2] per_band_stereo_width
) -> tuple[np.ndarray, list[WidthCorrectiveAction]]:
```

`pre_widths` is derived from `before.per_band_stereo_width.bands` (stage [2]). Keys are band names; values are `width` floats.

Returns corrected audio and a list of WidthCorrectiveAction entries. No correction for any band means empty list and unmodified audio.

### 6.2 Estimator identity — mandatory

**The width measurement driving the correction and the width measurement verifying the result must use the same function.** `pre_widths` is produced by STORY-002's `measure_per_band_stereo_width` (called in stage [2]). The post-correction width in `resulting_value` is computed arithmetically (see §6.4). The Stage [9] post-master measurement must call the same `measure_per_band_stereo_width` for the "after" report values.

Do not implement a second, time-domain width estimator inside `stereo_width_corrector.py`. Use `pre_widths` from stage [2] for the input measurement.

### 6.3 Per-band gain formula — derivation

**Width estimator (from `analysis/per_band_stereo_width.py`):**

```
w = 1 − |Re{ ∫_band S_LR(f) df }| / sqrt( ∫_band S_LL(f) df × ∫_band S_RR(f) df )
```

where S_LR is the Welch cross-spectral density of L and R, and S_LL, S_RR are their Welch power spectral densities (identical nperseg/noverlap/window across all three). This is a frequency-domain coherence-style estimate; see `per_band_stereo_width.py` module docstring for caveats relative to broadband time-domain correlation.

**Connection to the gain formula:** Under the M⊥S assumption (M and S are uncorrelated within the band) and for material where the within-band cross-spectrum is predominantly real (no large inter-channel phase offset), the CSD-based width reduces to `2r / (1 + r)` where `r = E_S / E_M` (side-to-mid band energy ratio). This is the same formula used in the gain derivation below.

**For M/S processing with per-band side gain `g` (0 ≤ g ≤ 1):**
- `L_new = M_band + g × S_band`
- `R_new = M_band − g × S_band`

where `M_band = (L_band + R_band) / 2`, `S_band = (L_band − R_band) / 2`, and `L_band`, `R_band` are the bandpass-filtered L and R channels for the target band.

Under M⊥S within the band:
- `E_L = E_M + g²E_S`, `E_R = E_M + g²E_S`, `E_LR = E_M − g²E_S`
- Width: `w = 2g²r / (1 + g²r)` where `r = E_S / E_M`

At `g = 1` (no correction): `w_src = 2r / (1 + r)`, so `r = w_src / (2 − w_src)`.

**Gain formula for target width `w_t`:**

```
r = w_src / (2 - w_src)
g = sqrt( w_t × (2 - w_src) / (w_src × (2 - w_t)) )
```

**Verification against AC20:**

Source sub width = 0.60, aim point = 0.15, max_step = 0.15.

Step 1 — apply cap in width units (not in g):
```
w_target = max(aim_point, w_src - max_step)
         = max(0.15, 0.60 - 0.15) = max(0.15, 0.45) = 0.45
```

Step 2 — solve for g:
```
r = 0.60 / (2 - 0.60) = 0.60 / 1.40 = 0.4286
g = sqrt(0.45 × 1.40 / (0.60 × 1.55))
  = sqrt(0.630 / 0.930) = sqrt(0.677) = 0.823
```

Step 3 — verify resulting width:
```
g²r = 0.677 × 0.4286 = 0.290
w_new = 2 × 0.290 / (1 + 0.290) = 0.580 / 1.290 = 0.450  ✓
```

**Verification against Q1 example (w_src = 0.80):**
```
w_target = max(0.15, 0.80 - 0.15) = 0.65
r = 0.80 / 1.20 = 0.667
g = sqrt(0.65 × 1.20 / (0.80 × 1.35)) = sqrt(0.780 / 1.080) = sqrt(0.722) = 0.850  ✓
```

**Critical implementation note:** The cap is applied in **width units** (`w_target = max(aim, w_src - max_step)`), and then `g` is solved for the capped `w_target`. The cap is **not** applied to `g` directly. A developer who clamps `g` instead of clamping `w_target` will produce a different resulting width and AC20 will fail.

### 6.4 Correction decision and WidthCorrectiveAction

For each band in `["sub", "low"]`:
```
w_src = pre_widths[band]
threshold = targets.stereo_width[band].near_mono_threshold  # = 0.15

if w_src <= threshold:
    # No correction
    continue

# Apply cap in width units
max_step = targets.stereo_width[band].max_correction_step  # = 0.15
aim_point = targets.stereo_width[band].correction_aim_point  # = 0.15
w_target = max(aim_point, w_src - max_step)

cap_reached = (w_target > aim_point)  # True when step cap was the binding constraint

# Solve for g
g = sqrt(w_target × (2 - w_src) / (w_src × (2 - w_target)))

# Apply per-band M/S narrowing (see §6.5)
audio = _apply_band_narrowing(audio, sr, band_hz, g)

# CorrectiveAction — resulting_value is arithmetic (w_src - (w_src - w_target))
applied = -(w_src - w_target)   # negative = narrowing
resulting_value = w_src + applied   # = w_target

emit WidthCorrectiveAction(band=band, ...)
```

`WidthCorrectiveAction.resulting_value = w_target` (arithmetic, same pattern as `SpectralCorrectiveAction.resulting_db = source_db + applied_db`).

**Floor assertion:** The floor (0.10) is never reachable by construction: `w_target = max(0.15, w_src − 0.15) ≥ 0.15 > 0.10` always. The implementation must include a post-condition assertion `assert resulting_value >= floor, ...` rather than a clamp. If this assertion ever fires, it indicates an error in the gain formula or a non-finite audio sample — it must not be silently swallowed.

### 6.5 Per-band M/S narrowing implementation

The `_apply_band_narrowing(audio, sr, band_hz, g)` helper:

1. Bandpass-filter both channels using `scipy.signal.butter(order=8, Wn=band_hz, btype='bandpass', fs=sr, output='sos')` + `sosfiltfilt` (zero-phase). Order 8 Butterworth gives approximately 48 dB/octave rolloff, providing adequate band isolation for sub (20–60 Hz) and low (60–120 Hz).

2. Compute M/S per band:
   ```
   L_band, R_band = bandpass-filtered channels
   M_band = (L_band + R_band) / 2
   S_band = (L_band - R_band) / 2
   ```

3. Apply side gain:
   ```
   L_band_new = M_band + g * S_band
   R_band_new = M_band - g * S_band
   ```

4. Compute the residual (what was changed):
   ```
   delta_L = L_band_new - L_band
   delta_R = R_band_new - R_band
   ```

5. Add the per-band correction back to the full-band signal:
   ```
   audio[:, 0] += delta_L
   audio[:, 1] += delta_R
   ```

This approach (add the in-band delta, not the reconstructed full signal) avoids the phase and magnitude artifacts that arise from bandpass → reconstruct on music signals.

**Band frequency bounds:**
- Sub: `band_hz = (20.0, 60.0)` Hz
- Low: `band_hz = (60.0, 120.0)` Hz

The sub band lower edge (20 Hz) is below the standard audio floor; the 8th-order Butterworth is robust to this. At 44.1 kHz, the sub band spans roughly 5 frequency bins of a 4096-point FFT — adequate for energy estimation but not for frequency-domain measurement (which is why `g` is derived from the bandpass energy ratio, not from Welch/CSD directly).

**Bandpass filter isolation check:** At 44.1 kHz sr, the low-band filter (60–120 Hz) has its upper corner at 120 Hz. The lower corner of the existing `low_mid` band is also 120 Hz. An 8th-order Butterworth delivers ≈48 dB/oct attenuation above the corner, giving ≈6 dB attenuation at 240 Hz (one octave above 120 Hz). The per-band correction at 240 Hz would receive ≈1/4 of the band correction amplitude, contributing a systematic narrowing artifact at the bottom of the low_mid band. This is a known limitation of IIR bandpass isolation; for the application (≤15 width-unit correction on sub/low bands), the artifact is small relative to the band energy in low_mid. Document in the report if per-band width correction is applied.

---

## 7. Data Structures

### 7.1 SpectralCorrectiveAction

```python
@dataclass
class SpectralCorrectiveAction:
    band: str           # "sub" | "low_mid"
    trigger: str        # "range_compliance" | "de_mud"
    source_db: float    # pre-correction relative_db for the band
    aim_point_db: float # de_mud.correction_aim_point_db for de_mud; nearest range edge for range_compliance
    applied_db: float   # signed dB of DELIVERED gain at center frequency — equals sosfiltfilt output
                        # (= 2 × filter design parameter passed to _low_shelf_sos / _peaking_sos).
                        # Negative = cut. This is NOT the raw design parameter; it is the gain
                        # the listener hears at the filter's center frequency.
    cap_reached: bool
    resulting_db: float # source_db + applied_db (arithmetic, NOMINAL INTENDED OUTCOME for logging only).
                        # Does not account for energy-weighted under-delivery across the band
                        # (~0.60× for sub shelf, ~0.75× for low_mid bell).
                        # NOT used for AC16 pass/fail classification.
                        # Stage [9] post-correction measurement governs classification.
```

Field names pin to the example in requirements.md §4 (`source_db`, `aim_point_db`, `applied_db`). The AC19 assertion checks `aim_point_db == targets.de_mud.correction_aim_point_db` (de_mud case) and `aim_point_db == nearest_edge` (range_compliance case).

### 7.2 WidthCorrectiveAction

```python
@dataclass
class WidthCorrectiveAction:
    band: str              # "sub" | "low"
    trigger: str           # "width_above_threshold"
    source_value: float    # pre-correction width (from pre_widths)
    aim_point: float       # near_mono_threshold (0.15), not the floor (0.10)
    applied: float         # negative (narrowing): -(w_src - w_target)
    cap_reached: bool      # True when max_step was the binding constraint
    resulting_value: float # w_target = w_src + applied (arithmetic)
```

Field names follow the neutral-name convention from requirements.md §3.7 rule 4. The distinction from `SpectralCorrectiveAction` (which uses `_db` suffix) is intentional: the test-case-writer must not conflate the two when asserting on AC20 (`aim_point = 0.15`, not `aim_point_db`).

**Note:** `aim_point = 0.15` in `WidthCorrectiveAction`. The floor (0.10) must never appear as `aim_point`. An implementation that sets `aim_point = 0.10` is wrong; AC20 asserts `aim_point == 0.15`.

### 7.3 TargetsDocument

The `suno_mastering/targets/schema.py` module defines `TargetsDocument` as a nested dataclass tree mirroring the `targets.json` schema (requirements.md §3). `loader.py` provides `load_targets(path: str) -> TargetsDocument` which:
1. Opens and JSON-parses the file.
2. Validates all required fields are present and have numeric types.
3. Raises `TargetsLoadError(message, path)` on any failure.

`pipeline.py` calls `load_targets(config.targets_json_path)` before stage [1]. A `TargetsLoadError` propagates immediately as a startup failure; no partial processing occurs.

---

## 8. targets.json Schema — Expected Values for Validation

These values are expected outputs of the generator, derived from the actual `reference_set_report.json` at `Reference Tracks/reference_set_report.json`. They are stated here as validation targets (H4); they must be computed by the generator, not hardcoded.

### 8.1 Spectral band derivation table

Source measurements extracted from `reference_set_report.json` (per-track `seven_band.bands[n].relative_db` fields, n=3 contributing tracks):

| Band | Chemical Brothers | GusGus | Black Flute | 3-track min | 3-track median | 3-track max |
|---|---|---|---|---|---|---|
| sub (20–60 Hz) | +1.944 | −3.085 | −3.747 | −3.747 | −3.085 | +1.944 |
| low (60–120 Hz) | +0.471 | +4.335 | +8.617 | +0.471 | +4.335 | +8.617 |
| low_mid (120–500 Hz) | −0.145 | +3.394 | +8.522 | −0.145 | +3.394 | +8.522 |
| mid (500–2000 Hz) | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| high_mid (2000–5000 Hz) | −6.714 | −13.408 | −1.243 | −13.408 | −6.714 | −1.243 |
| high (5000–10000 Hz) | −9.772 | −17.062 | −4.060 | −17.062 | −9.772 | −4.060 |
| air (10000–22050 Hz) | −16.015 | −20.053 | −11.444 | −20.053 | −16.015 | −11.444 |

**Air band upper edge (22050 Hz):** Resolved per §4.3 rule: `min(24000, min Nyquist of contributing tracks)`. All three contributing tracks are at 44100 Hz (Nyquist = 22050 Hz), so the value is `min(24000, 22050) = 22050`. The analysis pipeline's `air (10000–Nyquist Hz)` label resolves to 22050 Hz at both analysis and targets.json generation time for these tracks.

**Gate1 §3 range confirmation:** sub range [−3.75, +1.94] matches (rounded to 2 dp). low range [+0.47, +8.62] matches. low_mid [−0.15, +8.52] matches.

### 8.2 Stereo width derivation table

Source measurements from `reference_set_report.json` (`per_band_stereo_width.bands[n].width` fields):

| Band | Chemical Brothers | GusGus | Black Flute | 3-track min | 3-track median | 3-track max |
|---|---|---|---|---|---|---|
| sub (20–60 Hz) | 0.00916 | 0.00125 | 0.04036 | 0.00125 | 0.00916 | 0.04036 |
| low (60–120 Hz) | 0.01650 | 0.00078 | 0.14691 | 0.00078 | 0.01650 | 0.14691 |

Expected targets.json stereo_width section per band: sub {min≈0.001, median≈0.009, max≈0.040}; low {min≈0.001, median≈0.017, max≈0.147}.

### 8.3 Dynamic range derivation

From CLAUDE.md §4.1 (values per-track; must be derived from `dynamic_range_db_exact` field):

| Track | DR exact |
|---|---|
| Chemical Brothers — Live Again | 8.26 |
| Black Flute (Remastered) | 8.65 |
| GusGus — Over | 6.60 |

3-track median = 8.26, min = 6.60, max = 8.65. Label "DR8.3" (conventional rounding of 8.26 to one decimal).

---

## 9. Constants Derivation (H4)

Every constant compared against must have its derivation shown here. Constants fall into three categories:

### Category A — Derived from 3-track reference measurements

| Constant | Value | Derivation |
|---|---|---|
| `sub.range_db_re_mid.min` | −3.747 | min(+1.944, −3.085, −3.747) = −3.747 (Black Flute, from reference_set_report.json line 5219) |
| `sub.range_db_re_mid.max` | +1.944 | max(+1.944, −3.085, −3.747) = +1.944 (Chemical Brothers, from reference_set_report.json line 26530) |
| `low.range_db_re_mid.min` | +0.471 | min(+0.471, +4.335, +8.617) = +0.471 (Chemical Brothers) |
| `low.range_db_re_mid.max` | +8.617 | max(+0.471, +4.335, +8.617) = +8.617 (Black Flute) |
| `low_mid.range_db_re_mid.min` | −0.145 | min(−0.145, +3.394, +8.522) = −0.145 (Chemical Brothers) |
| `low_mid.range_db_re_mid.max` | +8.522 | max(−0.145, +3.394, +8.522) = +8.522 (Black Flute) |
| `low_mid.median_db_re_mid` | +3.394 | median(−0.145, +3.394, +8.522) = +3.394 (GusGus, middle of sorted triple) |
| `stereo_width.sub.max` | 0.04036 | max(0.00916, 0.00125, 0.04036) = 0.04036 (Black Flute) |
| `stereo_width.low.max` | 0.14691 | max(0.01650, 0.00078, 0.14691) = 0.14691 (Black Flute) |
| `dynamic_range_db.target_median` | 8.26 | median(8.26, 8.65, 6.60) = 8.26 (Chemical Brothers) |
| `dynamic_range_db.range_min` | 6.60 | min(8.26, 8.65, 6.60) = 6.60 (GusGus) |
| `dynamic_range_db.range_max` | 8.65 | max(8.26, 8.65, 6.60) = 8.65 (Black Flute) |

### Category B — Fixed policy values with stated relationship to reference data

| Constant | Value | Source and derivation |
|---|---|---|
| `hard_targets.integrated_lufs` | −13.5 LUFS | CLAUDE.md §4.2. Fixed streaming-aware target. References sit at −7.56 to −8.70 LUFS; streaming normalises to ≈−14 LUFS, discarding dynamics. −13.5 recovers headroom. NOT reference-derived. |
| `hard_targets.true_peak_dbtp` | −1.0 dBTP | CLAUDE.md §4.2. Fixed lossy transcode headroom. References exceed 0 dBTP (+0.52 to +0.68); acceptable for their era but creates clip risk in transcoding. |
| `de_mud.flag_threshold_db_above_mid` | +4.0 dB | requirements.md Q2. Derived from reference data: +4.0 dB sits above Chemical Brothers (−0.145 dB, the de-mud anchor) by 4.145 dB and above GusGus (+3.394 dB) by 0.606 dB. Both are non-muddy references. The threshold fires on Black Flute-like material (+8.522 dB > mid+4.0) deliberately — requirements.md §3.7 rule 6 licenses correction when excess low-mid energy is present regardless of reference range membership. The valid interval for this threshold is the open set (3.394, 8.522) — any value here would fire on Black Flute and not on the non-muddy references. +4.0 dB is a policy choice within this interval, providing a 0.6 dB margin above GusGus. |
| `de_mud.correction_aim_point_db` | +2.0 dB | requirements.md Q2. Derived from two arguments: (a) DOMAIN.md §5 prohibits correcting toward a median where references disagree by more than ~4 dB; the low_mid span is 8.67 dB, so the subset median (+3.394 dB) is disqualified on principle regardless of its numeric value. (b) The two candidate aim points (+2.0 and +3.394) produce different correction outcomes only when the cap is not binding — i.e. when source is in the interval (mid+4.0, mid+5.394). In that interval, correcting to +2.0 dB lands nearer the reference range floor (Chemical Brothers at −0.145 dB) than correcting to the median. Above +5.394 dB (including the capped case at source = +7.0 dB cited in AC19), both aim points result in cap binding at applied_db = −2.0 and identical resulting_db = source_db − 2.0; the choice of aim point makes no difference to the audio output at those levels. |
| `stereo_width.near_mono_threshold` | 0.15 | requirements.md Q1 + gate1 §3 + reference data. Maximum observed low-band stereo width across 3-track subset: Black Flute low = 0.14691. Rounded up to 0.15 for a clean boundary. Any Suno track with sub or low width > 0.15 is wider than every reference track's low band. Applied to both sub and low bands (conservative for sub, where the reference max is only 0.040). |
| `spectral correction_cap_db` | ±2.0 dB | requirements.md §3.7 (normative). Gate1 §3: "Broad spectral balance nudges within the reference range … max ±2 dB." Fixed; not configurable. |

### Category C — Not derivable from reference data; flagged for mastering engineer

| Constant | Value | Status |
|---|---|---|
| `stereo_width.correction_floor` | 0.10 | **NOT DERIVED.** No reference measurement approaches 0.10 (minimum observed sub width = 0.00125). 0.10 is a safety floor against mono collapse with no validated reference basis. Flagged for mastering engineer review: if it can be derived from a psychoacoustic principle or a measurement on the reference set, that derivation should be added before STORY-007. As specified in requirements.md Q1, it is not the aim point — it functions as a post-condition assertion only (see §6.4). Note: the floor is unreachable by construction (`w_target = max(0.15, w_src − 0.15) ≥ 0.15 > 0.10`), so it serves only as a guard against programmer error. |
| `stereo_width.max_correction_step` | 0.15 | **NOT DERIVED.** Numerically equal to `near_mono_threshold`, which is a coincidence from requirements.md Q1 resolution. No reference basis for a step limit specifically. Flagged for mastering engineer: a single-pass correction from the most extreme plausible width (e.g. 0.95) to 0.15 would require g ≈ 0.27 (large narrowing). The step of 0.15 limits this to a maximum resulting width of 0.80 (one step from 0.95). Whether this represents an appropriate rate of change requires mastering judgment. |

---

## 10. OQ Resolution Record

| OQ | Resolution |
|---|---|
| OQ1 — CorrectiveAction data structure | Two dataclasses: `SpectralCorrectiveAction` (with `_db` field suffix) and `WidthCorrectiveAction` (neutral field names). See §7. |
| OQ2 — HF extension method | Out of scope. STORY-F2. HF extension is informational-only; air band corrects toward nothing. No action in STORY-006. |
| OQ3 — targets.json generation trigger | Generate once offline, commit to repository. Regenerate explicitly via `generate_targets.py` (shim) or `python -m suno_mastering.targets.targets_generator` when `reference_set_report.json` changes. See §4.4. |
| OQ4 — Output bit depth | 24-bit WAV + TPDF dither, inherited from STORY-001 `config.output_bit_depth = 24`. No change. |
| OQ5 — Internal sample rate | Native sample rate; no forced resampling. True peak uses 8x oversampling (`config.true_peak_oversample_factor = 8`), inherited from STORY-001. No change. |

---

## 11. Library Choices

| Need | Library | Rationale |
|---|---|---|
| Audio I/O | `soundfile` | Float64 arrays, no silent resampling, sample-accurate. `librosa.load` is prohibited (CLAUDE.md §5 — silently resamples to 22050 Hz). |
| Biquad filter design | `mastering/eq.py` (existing) | RBJ Audio-EQ-Cookbook implementation already in the project. Reuse prevents a second implementation of the same coefficients. |
| Zero-phase filter application | `scipy.signal.sosfiltfilt` | Zero-phase (forward-backward), offline batch. Prevents phase shift artifacts in corrective EQ on electronic material with pronounced kick transients. Design parameter is halved (`gain_db = applied_db / 2`) to account for the forward-backward gain doubling; see §5.2, §5.3. |
| Bandpass filter design for stereo width | `scipy.signal.butter(..., btype='bandpass', output='sos')` | 8th-order Butterworth provides adequate isolation (≈48 dB/oct) for the sub and low bands. Used only for the bandpass step in stereo_width_corrector.py. |
| LUFS measurement | `pyloudnorm` | Correct ITU-R BS.1770 implementation. No change from STORY-001. |
| True peak | 8× oversampled peak via `scipy.signal` FIR chain | Same as STORY-001. `np.max(np.abs(x))` is sample peak, not true peak (CLAUDE.md §5). |
| JSON I/O | `json` (stdlib) | No external JSON library needed; `targets.json` is generated once offline. |
| Statistical computation (median, min, max) | `statistics.median` (stdlib) | Exact for n=3; no floating-point sorting concerns. |

**pedalboard is not used.** This project established the RBJ biquad pattern (`mastering/eq.py`) in STORY-001, and pedalboard would introduce a parallel filter implementation path for no benefit. Changing the EQ implementation without a validated equivalence test would be an unnecessary risk.

---

## 12. Data Flow

```
[OFFLINE]
reference_set_report.json
    → suno_mastering/targets/targets_generator.py  (via generate_targets.py shim)
        → targets.json (committed to repo)

[RUNTIME, per-track]
input.wav (float64 via soundfile)
    → [1] Ingest (float64 in memory)
    → [2] Pre-master analysis
           seven_band: {band -> relative_db}
           per_band_stereo_width: {band -> width}
    → [3] Resample (conditional, native sr preferred)
    → [4] corrective_eq.py
           reads: targets.json (TargetsDocument in memory since startup)
           reads: before.seven_band as pre_band_levels
           output: audio (float64), List[SpectralCorrectiveAction]
    → [5a] stereo_width_corrector.py
           reads: targets.json
           reads: before.per_band_stereo_width as pre_widths
           output: audio (float64), List[WidthCorrectiveAction]
    → [5b] stereo_correct.py (existing, broadband windowed)
    → [6] loudness_limit.py (dynamics + loudness + limiting)
    → [7] TPDF dither + 24-bit quantize
    → [8] Export to output.wav
    → [9] Post-master analysis (re-read from disk)
    → [10] Report (before/after measurements + CorrectiveAction log)
```

**Internal representation:** float64 throughout stages [1]–[7]. Conversion to int24 happens exactly once at stage [7]. No intermediate float32 or int16 conversions.

---

## 13. Non-Destructive Handling

Inherited from STORY-001:
- SHA-256 hash of input taken at stage [1]; re-verified at end of stage [8]; any change raises `NonDestructiveIntegrityError`.
- Output path never equals input path (enforced by `io/export.py`).
- `targets.json` is read-only at runtime; the generator is never called during a mastering run.

---

## 14. config.py Changes

The following fields in `suno_mastering/config.py` are retired by this story (their values move to `targets.json`):

| Field | Old purpose | STORY-006 disposition |
|---|---|---|
| `freq_low_band_hz` | 3-band EQ low range | Retired. Band edges now in `targets.json spectral_bands.sub.freq_hz`. |
| `freq_mud_band_hz` | 3-band EQ mud range | Retired. Band edges now in `targets.json spectral_bands.low_mid.freq_hz`. |
| `freq_presence_band_hz` | 3-band EQ presence range | Retired. high_mid is informational; no filter. |
| `freq_reference_band_hz` | Mid-band reference | Retained in config for analysis consistency; this is the denominator used by analysis code. |
| `thin_low_end_threshold_db` | EQ trigger | Retired. Sub correction triggered by range compliance from targets.json. |
| `muddiness_threshold_db` | EQ trigger | Retired. De-mud threshold now in `targets.json de_mud.flag_threshold_db_above_mid`. |
| `harshness_threshold_db` | EQ trigger | Retired. high_mid not corrected. |
| `eq_max_gain_db` | EQ cap | Retired. Per-band caps in `targets.json spectral_bands[band].correction_cap_db`. |
| `reference_curve_path` | Path to genre curve JSON | Retired. Genre reference curve replaced by `targets.json`. The genre curve file `reference/progressive_house_124bpm.json` and its −1.5/−3.0/−4.0 dB values are no longer used. |

**New field added to `MasteringConfig`:**
```python
targets_json_path: str  # default = str(Path(__file__).parent.parent / "targets.json")
```

All retained stereo correction config fields (`stereo_side_mid_ratio_threshold`, `stereo_window_ms`, etc.) are unchanged — they drive the existing `stereo_correct.py` (stage [5b]).

**AC13 grep test — spectral target values:** After this story is implemented, `grep -r "0\.47\|8\.52\|0\.145\|3\.394\|8\.617\|1\.944\|3\.747" suno_mastering/` on mastering source must return no matches (these are the spectral target constants from targets.json). The generator may contain these as validation-only expected values, clearly marked.

**AC13 supplementary check — de-mud and cap constants:** The values `4.0` (de-mud threshold), `2.0` (correction aim point), and `2.0` (correction cap) must not appear as literal arguments to filter-construction calls or comparison operators in `suno_mastering/mastering/corrective_eq.py`; they must be read from `TargetsDocument` fields. This is a code-review check, not a grep check: a naive `grep "4\.0\|2\.0" corrective_eq.py` will spuriously match the geometrically derived bandwidth constant (`bandwidth_octaves=2.06`, which contains the substring `2.0`) and will therefore always fire. Instead, a reviewer must verify that no call to `_peaking_sos`, `_low_shelf_sos`, or comparison with `>` / `<` passes one of these values as a literal float. The `2.06` bandwidth constant is geometrically derived from `log2(500/120)` and may legitimately appear as a literal or named constant.

---

## 15. Integration Points

### 15.1 Consuming reference_set_report.json

`reference_set_report.json` is produced by STORY-005. The generator consumes it as a JSON array where each element represents one track's `ReferenceMeasurements` serialised form.

The generator does **not** import STORY-005 Python modules; it reads the JSON directly to avoid a module dependency on STORY-005's implementation. The field paths are:
- `[n].label` — track name
- `[n].track_path` — fallback path
- `[n].seven_band.bands[k].band` and `.relative_db`
- `[n].per_band_stereo_width.bands[k].band` and `.width`
- `[n].dynamic_range_db_exact`
- `[n].core.sample_rate` — for Nyquist computation

### 15.2 Existing STORY-001 analysis pipeline

Stage [2] already calls `analysis.measure_all()` which produces `before.frequency_balance` (7-band spectral balance) and `before.per_band_stereo_width`. These existing outputs are the input to stages [4] and [5a] respectively. No new analysis is added in STORY-006 — the existing analysis already produces what is needed.

### 15.3 Produced by STORY-006, consumed by STORY-007

`targets.json` is the machine-readable artifact consumed by STORY-007. The `CorrectiveAction` log (per-track list of `SpectralCorrectiveAction` and `WidthCorrectiveAction`) is produced per mastering run and should be available to STORY-007 for batch reporting. The exact format of the per-run mastering report consumed by STORY-007 is to be specified in STORY-007 architecture.

---

## 16. Error Handling Contract

| Condition | Response |
|---|---|
| `targets.json` absent | `TargetsLoadError` raised at startup (stage [1] never reached); non-zero exit; explicit file path in message |
| `targets.json` present but fails schema validation | Same: `TargetsLoadError` with specific field name |
| `reference_set_report.json` absent or unreadable at path passed to generator | `FileNotFoundError` / `IOError` raised; generator exits non-zero; message names the missing file path explicitly |
| Contributing track absent from `reference_set_report.json` | `ValueError` from generator naming the missing track; generator exits non-zero |
| Fewer than 3 contributing tracks resolved | `ValueError` naming all unresolved tracks; generator exits non-zero |
| Excluded tracks present in report JSON | Not an error. Silently ignored by generator. |
| Mono audio passed to `stereo_width_corrector.py` | `ValueError("per-band stereo width correction requires stereo audio; mono not supported")` |
| NaN or Inf in audio at any stage | Caught at stage [8] export (existing `io/export.py` validates before write) |

---

## 17. Testability Notes

### 17.1 Synthetic signal requirements

- **AC18 (negative control):** Synthesise a stereo signal with: sub band at −1.0 dB re mid (within [−3.75, +1.94]), low_mid at +2.0 dB re mid (within range AND below de_mud threshold mid+4.0), sub/low widths at 0.10 (below 0.15). Assert zero CorrectiveAction entries emitted.

- **AC19 (de-mud discriminator):** Two sub-tests:
  - Assertion 1: any source with low_mid > mid + `targets.de_mud.flag_threshold_db_above_mid` → assert `SpectralCorrectiveAction.aim_point_db == targets.de_mud.correction_aim_point_db`. Simple; works at any source level.
  - Assertion 2: source at low_mid = +4.5 dB → assert `SpectralCorrectiveAction.applied_db == −2.0` (cap reached, delivered gain = −2.0 dB) AND `cap_reached == True`. Stage [9] post-correction low_mid measurement: assert within `[+2.5 − 0.6, +2.5 + 0.6]` dB tolerance (arithmetic `resulting_db` = +2.5; Stage [9] reflects ~0.75× energy-weighted delivery plus mid-band bleed; ±0.6 dB accounts for both effects). Note: `SpectralCorrectiveAction.resulting_db == +2.5` is an arithmetic log field only and should not be used as the Stage [9] assertion target.

- **AC14/AC16 (band classification):** The three-way classification (met / cap-reached / informational) uses the Stage [9] post-correction band measurement (`after.seven_band.bands[band].relative_db`), not `SpectralCorrectiveAction.resulting_db`. Test assertions verifying classification must read Stage [9] and compare against `targets.spectral_bands[band].range_db_re_mid`. Sub band Stage [9] level assertions: ±0.5 dB tolerance (shelf energy-weighted delivery ~0.60× across 20–60 Hz). Low_mid band Stage [9] level assertions: ±0.6 dB tolerance (bell energy-weighted delivery ~0.75× across 120–500 Hz, plus mid-band bleed ≈+0.15 dB). A test asserting that a band is classified "met" must confirm Stage [9] measurement is inside `[range_min, range_max]`, not that `resulting_db` equals `range_min`.

- **AC20 (width correction):** Synthesise a stereo signal where sub band width = 0.60. Use minimum 10 s duration at 44.1 kHz (Welch estimator requires adequate averaging windows for sub-band measurements — the sub band 20–60 Hz occupies very few Welch bins at standard window sizes). Assert: `WidthCorrectiveAction.aim_point == 0.15`; `applied == −0.15`; `resulting_value == 0.45`; `cap_reached == True`; `resulting_value > 0.10` (floor assertion).

- **AC21 (excluded track isolation):** Tests must perturb contributing track values in a fixture `reference_set_report.json` and assert the generator output changes correspondingly. Adding or removing Leftfield/Wavy Gravy data must not change any numeric output.

### 17.2 Injectability

- `corrective_eq.py`'s `apply_corrective_eq` receives `targets: TargetsDocument` and `pre_band_levels: dict` as explicit arguments — no global state, no file reads at call time. A test can construct a `TargetsDocument` with arbitrary parameters and a synthetic `pre_band_levels` dict without loading any file.

- `stereo_width_corrector.py`'s `apply_stereo_width_correction` similarly receives `targets` and `pre_widths` as arguments.

- `load_targets(path)` can be mocked at the pipeline level; `pipeline.master()` passes the loaded document rather than re-loading inside each module.

### 17.3 Duration note for sub-band width tests

Standard Welch `nperseg=65536` at 44100 Hz → 1.49 s per window. For stable sub-band (20–60 Hz) cross-spectral density estimation, a minimum of 6–8 non-overlapping windows is needed. Specify test fixtures at ≥ 10 s. A 3 s fixture will produce noisy sub-band width estimates and may cause AC20 to flake.

---

## 18. Known-Wrong Patterns (CLAUDE.md §5) — Addressed

| Known-wrong pattern | Addressed by |
|---|---|
| Threshold-based band-limit detection | Not used in STORY-006's own processing modules. The pattern is present upstream in `analysis/hf_extension.py` (tracked as DEF-609); contained because no STORY-006 code path reads `hf_extension`. See §23. |
| Asserting a constant without derivation | All constants in §9 are derived (Category A), fixed by policy (Category B), or explicitly flagged (Category C). |
| `np.max(np.abs(x))` for true peak | Unchanged from STORY-001 — 8× oversampled peak. |
| `librosa.load` without `sr=None` | Not used; `soundfile` via existing `io/ingest.py`. |
| Hardcoded round-number targets | Spectral targets removed from `config.py`; all read from `targets.json`. `CLAUDE.md §4.2` values (−13.5, −1.0) are policy-fixed and sourced explicitly. De-mud threshold (4.0), aim point (2.0), and correction cap (2.0) read from `TargetsDocument`, not literal in `corrective_eq.py`. |
| Fixing wrong method by tuning parameter | Not applicable to this story (no defect fix). |
| Reporting a fixed property as varying | HF extension method is acknowledged as unreliable; no correction from it. |

---

## 19. What This Story Does NOT Implement

| Not implemented | Reason |
|---|---|
| High_mid EQ correction | Gate1 §3: 12.2 dB spread; GusGus and Black Flute aesthetically opposite. Informational only. |
| High or air band EQ | 13.0 dB and 8.6 dB spreads respectively; informational only. HF extension method unreliable (STORY-F2). |
| Stereo widening at any band | No explicit widening requirement (requirements.md §8). Only sub/low narrowing in scope. |
| LRA targeting | Reference subset spans 9 LU; no defensible target (CLAUDE.md §4.2). |
| Iterative or multi-pass EQ | Single-pass cap rule is normative (requirements.md §3.7). |
| targets.json regeneration at runtime | Generate-once-and-commit policy (OQ3 resolution). |
| Presence correction (high_mid) | Q3 resolved: report-only. |

---

## 20. Open Architectural Risks

1. **M⊥S approximation accuracy.** The gain formula in §6.3 assumes `M_band ⊥ S_band`. For highly phase-coherent bass content (e.g. a mono bass synth whose L and R channels are identical), M and S are correlated within the band, and the formula underestimates the required gain to achieve `w_target`. The post-correction width will be higher than `resulting_value`. The Stage [9] measurement will reveal this; the `CorrectiveAction.resulting_value` is arithmetic and will not match. This is a measurement discrepancy, not an implementation error, but it should be flagged in the test if the difference exceeds 0.05 width units on any test fixture.

2. **CSD real-part approximation in width estimator.** The actual width formula in `per_band_stereo_width.py` uses `|Re{∫ S_LR}|` rather than `|∫ S_LR|`. For material with significant within-band inter-channel phase offset (e.g. a spatially-processed bass where L and R have different phase at sub frequencies), these diverge. The gain formula derivation assumes predominantly real cross-spectrum, which holds for most club bass material. If the CSD phase offset is large, the computed gain will be slightly off and the resulting width will not exactly equal `w_target`. The Stage [9] measurement reveals this; the tolerance for width tests should be ±0.02 width units on programme material.

3. **Bandpass bleed into low_mid.** The 8th-order Butterworth for the low band (60–120 Hz) delivers ≈6 dB attenuation at 240 Hz. For a Suno track with very high energy in the 120–240 Hz region, per-band narrowing at the low band will have a secondary effect on the bottom of the low_mid band. Documented in §6.5. Not expected to be perceptible at ≤15 width-unit corrections.

4. **Correction cap constants (Category C) not derived.** `width_correction_floor = 0.10` and `max_correction_step = 0.15` have no validated reference basis. These are flagged for mastering engineer review before STORY-007. If James listens to the output and finds the narrowing too aggressive or insufficient, these are the values to revisit.

5. **Track label encoding in reference_set_report.json.** If `label` fields were serialised with different em-dash encoding (e.g. `—` vs `—`) or trailing whitespace, the generator's NFKC-normalized match will still succeed. However, if a label was written as an ASCII hyphen variant (`--`), the match will fail. The generator must log all `label` values it encounters when it cannot match, to aid debugging.

6. **Low band bleed from sub shelf.** At 60 Hz shelf corner, RBJ slope=1.0 delivers ≈50% of shelf gain at 120 Hz. For a ±2 dB applied_db sub correction, the low band (60–120 Hz, informational) receives ≈±1 dB. The post-Stage [9] low band measurement will show this bleed. It must be annotated in the report as expected behaviour, not a measurement anomaly.

7. **AC19 Assertion 2 tolerance.** Filter bleed from the low_mid bell into the mid reference band (≈+0.15 dB) and energy-weighted under-delivery across the low_mid band (~0.75×, ≈0.5 dB on a 2.0 dB correction) both contribute to divergence between `resulting_db` and Stage [9] measurement. Test assertions on Stage [9] post-correction low_mid level must use ±0.6 dB tolerance. The `CorrectiveAction.resulting_db` arithmetic value remains the primary log field; it is not asserted against Stage [9] directly.

---

## 21. Assumptions Pending BA Confirmation

None. All open questions from requirements.md §9 are resolved in §10 of this document or are deferred to STORY-007 (OQ6). The three open questions from story.md §"Open questions" are resolved in requirements.md §2.

---

## 22. Revision History

### v1.3 — 2026-08-12

Changes from v1.2: architectural defect resolutions for DEF-605 and DEF-609. See §23 for full specification.

**DEF-605:** Retired old Stage [4] `eq.py` pipeline call with exact removal specification for `pipeline.py`. Corrected §14's config field attribution: six of the eight listed "retired" fields (`freq_low_band_hz`, `freq_mud_band_hz`, `freq_presence_band_hz`, `thin_low_end_threshold_db`, `muddiness_threshold_db`, `harshness_threshold_db`) are consumed by `analysis/frequency_balance.py` (Stage [2]), not exclusively by the retired EQ stage. They must be retained in `config.py`. Only `eq_max_gain_db` (after updating `report/builder.py`) and `reference_curve_path` (with its uncalled `load_reference_curve()` method) are safe to remove. §23 supersedes §14's disposition for these six fields.

**DEF-609:** Confirmed option (b) — defer to STORY-F2. Established containment evidence: no STORY-006 code path (`targets_generator.py`, `corrective_eq.py`, `stereo_width_corrector.py`, `pipeline.py`) reads `hf_extension`. Wrong values remain in `reference_set_report.json` but do not influence any mastering correction decision. Cliff-detection method parameters (≥24 dB/oct, per CLAUDE.md §5 and DOMAIN.md §2) specified for STORY-F2 implementation.

**§18 update:** Table row for threshold-based band-limit detection updated to reflect accurate status — pattern present in `analysis/hf_extension.py` (DEF-609), not in STORY-006 processing modules, contained because no STORY-006 code path reads the output.

### v1.2 — 2026-08-11

Changes from v1.1 to resolve Gate 2 blockers and Advisory 2:

**BLOCKER 1 — sosfiltfilt gain convention (§5.2, §5.3, §5.4, §7.1, §11):**

`sosfiltfilt` delivers `|H(f)|²` — twice the dB response of the design parameter. A `gain_db = −2.0` design would deliver −4.0 dB, violating the ±2 dB cap. Resolution: Option A (retain sosfiltfilt; halve the design parameter). Added explicit convention statements to §5.2 and §5.3: the value passed to `_low_shelf_sos` and `_peaking_sos` is `applied_db / 2`, so sosfiltfilt's forward-backward doubling delivers the full `applied_db` at center frequency. Filter call lines in §5.4 updated to `gain_db=applied_db / 2` with inline explanation. `SpectralCorrectiveAction.applied_db` (§7.1) clarified as the delivered gain (= `2 × filter design parameter`), not the raw design parameter. The existing §5.3 bleed figures (−1.0 dB at 500 Hz for a −2.0 dB correction) are confirmed correct as delivered-gain math and unchanged. §11 library choice note for `sosfiltfilt` updated to reference the halved-parameter convention.

**BLOCKER 2 — Cap applied to filter parameter, not measured band change (§5.2, §5.3, §5.4, §7.1, §17.1, §20 risk 7):**

The cap governs the filter design parameter, not the resulting change in the measured band level. A sub shelf delivers ~0.60× of `applied_db` as an energy-weighted band average; a low_mid bell delivers ~0.75×. Classifying a band as "met" using the arithmetic `resulting_db` field misclassifies cases where the filter under-delivers and the band remains outside range. Resolution per reviewer recommendation: AC16 three-way classification uses Stage [9] post-correction measurement, not `resulting_db`. Changes: (a) §5.2 and §5.3 each have a new "Energy-weighted band delivery" paragraph stating the ~0.60× and ~0.75× delivery factors and Stage [9] test tolerances; (b) §5.4 now includes an "AC16 classification rule" paragraph explicitly stating Stage [9] governs and explaining why arithmetic `resulting_db` can misclassify; (c) §7.1 `resulting_db` field comment updated to read "NOMINAL INTENDED OUTCOME for logging only… NOT used for AC16 pass/fail classification"; (d) §17.1 AC14/AC16 test note added with Stage [9] assertion requirements and ±0.5 dB (sub) / ±0.6 dB (low_mid) tolerances; (e) §17.1 AC19 Assertion 2 updated to reference Stage [9] measurement with ±0.6 dB tolerance rather than `resulting_db`; (f) §20 risk 7 updated to name both energy-weighted delivery and mid-band bleed as sources of Stage [9] vs `resulting_db` divergence.

**Advisory 2 — reference_set_report.json not covered in §16 error table:**

Added row: "reference_set_report.json absent or unreadable at path passed to generator → FileNotFoundError/IOError raised; generator exits non-zero; message names the missing file path explicitly."

### v1.1 — 2026-08-11

Changes from v1.0:

**1. Module naming (§1, §3, §4, §12, §10).** The generation script entry point was referred to as `generate_targets.py` (repo root) in §1, §3, §4, and §12, contradicting the section heading which already used `targets_generator.py` from the brief. Resolved: the generation logic lives in `suno_mastering/targets/targets_generator.py` (importable module, `main()` function). A thin repo-root shim `generate_targets.py` delegates to `suno_mastering.targets.targets_generator.main()` for convenience. CLI can also run via `python -m suno_mastering.targets.targets_generator`. All §3 file-tree entries, §4 CLI examples, §10 OQ3, and §12 data flow updated.

**2. Contributor count assertion (§4.2, §16).** Added explicit hard assertion: exactly `len(contributing_tracks)` (= 3) contributors must resolve. The brief states "fails loudly if file absent or wrong tracks present." The "wrong tracks present" case is a contributing track that is absent from the JSON — 0 matches for that name = wrong tracks. Added to error handling table in §16.

**3. Air upper edge — incoherent dual-rule fixed (§4.3, §8.1).** v1.0 stated two contradictory rules ("median Nyquist" and "if any track is <44100 use that track's Nyquist"). Replaced with a single rule: `min(24000, min Nyquist across all contributing tracks)`. All three contributing tracks are at 44100 Hz so the value is 22050 Hz. §8.1 spectral table updated: air band row now reads `air (10000–22050 Hz)` with derivation note. Added runtime clamping note: the pipeline clamps the displayed air band upper edge to `min(targets_value, source_nyquist_hz)` at report time.

**4. Pseudocode reads from TargetsDocument, not literals (§5.4).** All numeric constants in the low_mid decision tree (`4.0` for de-mud threshold, `2.0` for aim point, `±2.0` for cap) were hardcoded literals in v1.0 pseudocode. Replaced with `targets.de_mud.flag_threshold_db_above_mid`, `targets.de_mud.correction_aim_point_db`, and `targets.spectral_bands["low_mid"].correction_cap_db`. Sub band pseudocode similarly updated. This satisfies AC13: no spectral policy constants appear as literals in `corrective_eq.py`.

**5. Width estimator formula corrected (§6.3, §20 risk 2).** v1.0 stated the width definition as `w = 1 − |ρ_band|` (time-domain correlation). Actual implementation in `analysis/per_band_stereo_width.py` uses a Welch CSD-based coherence estimate: `w = 1 − |Re{∫ S_LR df}| / sqrt(∫ S_LL df × ∫ S_RR df)`. The gain formula and all numeric verifications (AC20, Q1) are unchanged — the formula is mathematically compatible under M⊥S and real cross-spectrum assumptions, which are stated explicitly. Risk 2 in §20 added for the real-part approximation. §5.3 note added: `2.06` is geometrically derived and may remain as a literal.

**6. De-mud threshold derivation corrected (§9 Category B).** v1.0 stated the threshold was "calibrated to not trigger on any reference track." This is factually wrong: Black Flute (+8.522 dB) is above mid+4.0 and the threshold deliberately fires on it. Corrected derivation: +4.0 dB is a policy choice within the open interval (3.394, 8.522), providing 0.6 dB margin above GusGus and intentionally firing on Black Flute-like material per requirements.md §3.7 rule 6.

**7. De-mud aim point rationale corrected (§9 Category B).** v1.0 rationale for +2.0 over +3.394: "correcting to median leaves capped sources at +5.0 dB, too muddy." This argument is self-refuting: correcting to +2.0 at source +7.0 also leaves the source at +5.0 (cap binds in both cases). Replaced with two valid arguments: (a) DOMAIN.md §5 span rule (8.67 dB spread disqualifies the median on principle), (b) the two aim points are distinguishable only in the cap-free interval (+4.0, +5.394) where +2.0 lands nearer the reference range floor.

**8. AC13 supplementary check revised (§14).** Removed the self-defeating `grep -n "4\.0\|2\.0"` pattern (would spuriously match `bandwidth_octaves=2.06` which contains the substring `2.0`). Replaced with a code-review instruction that explicitly exempts `2.06` as geometrically derived from `log2(500/120)`.

---

## 23. Architectural Defect Resolutions (v1.3)

### DEF-605 — Retirement of Old Stage [4] EQ Call

**Decision: Option (a) — retire the old `eq.py` pipeline call entirely.**

This is not a new design decision. Architecture §2 and §3 are unambiguous: Stage [4] is `mastering/corrective_eq.py`, and `eq.py`'s `apply_corrective_eq()` function "is no longer called from the pipeline." The implementation failed to remove the old call. This section specifies exactly what the developer must change.

#### Exact removals from pipeline.py

All line numbers reference `stories/STORY-001/implementation/suno_mastering/pipeline.py` as read on 2026-08-12.

**1. Remove the import (line 32):**

```python
from .mastering import eq as eq_mod
```

Remove this line entirely. The biquad primitives (`_peaking_sos`, `_low_shelf_sos`, `_normalize_sos`, `_band_center_hz`, `_band_bandwidth_octaves`) are imported directly inside `mastering/corrective_eq.py`; `pipeline.py` has no remaining need for `eq as eq_mod`.

**Do not delete `mastering/eq.py`.** The file must not be removed. Only the pipeline import and call are retired. The biquad primitives remain active, imported by `corrective_eq.py`.

**2. Remove the Stage [4] block (lines 130–132):**

```python
# --- [4] Corrective EQ ---
logger.info("Stage 4: corrective EQ")
audio, eq_actions = eq_mod.apply_corrective_eq(audio, sr, before.frequency_balance, config)
```

Remove all three lines.

**3. Initialize `eq_actions` before the targets block:**

Insert the following immediately before `if getattr(config, "targets_json_path", None):` (currently at approximately line 142 after the above removal):

```python
eq_actions = []
```

**4. Simplify the Stage [5.1] merge (currently lines 151–154):**

Replace:

```python
try:
    eq_actions = list(eq_actions) + list(tb_eq_actions)
except Exception:
    eq_actions = eq_actions
```

with:

```python
eq_actions = list(tb_eq_actions)
```

There is no longer a prior `eq_actions` list from an old EQ stage to merge into. The try/except was defensive code for the case where `tb_eq_actions` was an unexpected type — that concern is resolved by a simple direct assignment from the known-typed output of `corrective_eq_mod.apply_corrective_eq`.

**5. Update the stage comment:**

Change `# --- [5.1] Optional: targets-based corrective EQ and stereo-width correction ---` to `# --- [4] Corrective EQ (targets-based) ---` to match the §2 stage table. This is a comment change only; leave the surrounding conditional structure as-is (whether targets loading is conditional or mandatory is governed by DEF-606, not DEF-605).

#### Resulting single-EQ-stage pipeline

After these changes the pipeline has exactly one corrective EQ stage — `mastering/corrective_eq.py` at Stage [4] — matching the §2 stage table. The old genre-curve-based three-band EQ (threshold-driven, anchored to `reference/progressive_house_124bpm.json`) is removed from the processing chain. The combined gain response defect (two sequential EQ stages with unspecified interaction) is eliminated.

`mastering/eq.py`'s `apply_corrective_eq()` function has no call site in the pipeline after this change. It becomes uncalled library code. Its biquad primitives remain active.

#### config.py field disposition — correction of §14

Architecture §14 lists eight fields as "retired." Grep of `suno_mastering/` on 2026-08-12 reveals that six of those eight fields are consumed by `analysis/frequency_balance.py`, not exclusively by `eq.py`'s `apply_corrective_eq()`. Architecture §2 marks Stage [2] as "No change." Retiring Stage [2]'s inputs is out of scope for DEF-605.

**Field partition by confirmed consumer:**

| Field | Confirmed consumer (grep 2026-08-12) | DEF-605 disposition |
|---|---|---|
| `freq_low_band_hz` | `analysis/frequency_balance.py` line 65 — Stage [2] analysis band definition | **Retain in config.py.** Stage [2] is "No change." §14's "Retired" disposition is incorrect for this field. |
| `freq_mud_band_hz` | `analysis/frequency_balance.py` line 69 — Stage [2] analysis band definition | **Retain in config.py.** Same reason. |
| `freq_presence_band_hz` | `analysis/frequency_balance.py` line 73 — Stage [2] analysis band definition | **Retain in config.py.** Same reason. |
| `thin_low_end_threshold_db` | `analysis/frequency_balance.py` line 66 — Stage [2] flagging threshold | **Retain in config.py.** Same reason. |
| `muddiness_threshold_db` | `analysis/frequency_balance.py` line 70 — Stage [2] flagging threshold | **Retain in config.py.** Same reason. |
| `harshness_threshold_db` | `analysis/frequency_balance.py` line 74 — Stage [2] flagging threshold | **Retain in config.py.** Same reason. |
| `eq_max_gain_db` | `mastering/eq.py` line 91 (now uncalled) AND `report/builder.py` line 43 (still called) | **Remove from config.py**, but only after first removing the reference from `report/builder.py`. Reporting a retired EQ cap to the user is misleading. Developer must update `report/builder.py` to not emit `eq_max_gain_db` before deleting the field from config. |
| `reference_curve_path` | `config.py`'s `load_reference_curve()` method body only — that method has no callers anywhere in the codebase (grep confirms zero external calls) | **Remove from config.py**, along with the `load_reference_curve()` method body and the `_DEFAULT_REFERENCE_CURVE` module-level default. Both are dead code. |

**§14 amendment:** The disposition column in §14 is incorrect for the six Stage [2] fields above. The accurate disposition for `freq_low_band_hz`, `freq_mud_band_hz`, `freq_presence_band_hz`, `thin_low_end_threshold_db`, `muddiness_threshold_db`, and `harshness_threshold_db` is: **retained in config.py as Stage [2] analysis parameters**; not retired by this story. §23 supersedes §14's disposition for these six fields. Retiring them requires a separate story that re-parameterises or retires the 3-band frequency balance analysis in `analysis/frequency_balance.py`.

**Developer implementation status:** The current `pipeline.py` is stale and must be updated as specified above (5 changes). The current `config.py` requires: (a) remove `reference_curve_path` and `load_reference_curve()` method; (b) remove `eq_max_gain_db` after updating `report/builder.py`. The six Stage [2] analysis fields must remain.

---

### DEF-609 — HF Extension Detection Method (Recurrence of DEF-201)

**Decision: Option (b) — retain as backlog (STORY-F2); reinforce the informational-only caveat.**

#### Containment evidence

This decision is safe because no STORY-006 code path reads or uses `hf_extension`.

`targets_generator.py` reads exactly the field paths enumerated in §15.1: `label`, `track_path`, `seven_band.bands[k].band`, `seven_band.bands[k].relative_db`, `per_band_stereo_width.bands[k].band`, `per_band_stereo_width.bands[k].width`, `dynamic_range_db_exact`, and `core.sample_rate`. `hf_extension` is not among them.

`targets.json` contains no `hf_extension` field (see §7/§8 schema). Therefore `mastering/corrective_eq.py`, `mastering/stereo_width_corrector.py`, and the runtime `pipeline.py` have no path from `hf_extension` to any correction decision.

Grep of `stories/STORY-001/implementation/suno_mastering/` for `hf_extension` (run 2026-08-12) returns 7 files. None of them are STORY-006 processing modules. The matches are confined to: `analysis/hf_extension.py`, `analysis/reference_types.py`, `analysis/_psd.py`, `reference_analysis/aggregate.py`, `reference_analysis/pipeline.py`, `report/reference_render.py`, and `io/reference_ingest.py`. All seven are reference analysis and reference reporting modules; none are in the per-track mastering processing path.

#### Residual risk

The wrong `hf_extension` values remain in `reference_set_report.json` and are visible in reference reports rendered by `report/reference_render.py`. This is a **reporting-credibility problem** — a mastering engineer reading the reference report will see physically impossible cutoff readings (e.g. Leftfield — Melt segments at 5131 Hz, which DOMAIN.md §2 explicitly identifies as a measurement error: "Any reported cutoff below ~10 kHz on a commercial release is a measurement error"). It is **not a mastering-correctness problem** for STORY-006: the wrong values do not influence any correction applied to Suno tracks.

#### Required method for STORY-F2

When STORY-F2 is implemented, the replacement method must conform to CLAUDE.md §5 and DOMAIN.md §2. These are standing project documents that supersede any narrower specification in a story brief.

**Method:** Cliff-detection. Detect a sharp transition from broadband programme content to noise floor. Do not measure spectral tilt. Do not compare energy against a threshold relative to lower-frequency content.

**Cliff criterion (CLAUDE.md §5, DOMAIN.md §2):** A sustained slope of **≥24 dB/octave across adjacent spectral bins**, followed by a noise floor that holds for at least one full octave above the transition frequency. The ≥24 dB/oct figure is the project standard specified in CLAUDE.md §5 and DOMAIN.md §2. This is not a tunable parameter.

**Frequency resolution:** Use Welch PSD with `nperseg` sufficient to resolve at minimum 1/3-octave bins at the frequencies of interest. At 44.1/48 kHz, `nperseg = 8192` gives ≈5 Hz bin width near 10 kHz, which is adequate. Per-segment PSD computation is used for noise-floor estimation only; the rolloff is derived from the ensemble-averaged spectrum.

**No-cliff result:** If no cliff meeting the criterion is found, the module must report `rolloff_hz = null` (or equivalent sentinel), `stable = true`, and `method = "cliff_detection"`. It must not substitute a tilt-derived frequency. DOMAIN.md §2 is explicit: "No cliff → report NO CUTOFF."

**Stability requirement:** A band limit is a fixed property of a file (DOMAIN.md §2). The method must return a single file-level rolloff measurement. If the implementation reports different `rolloff_hz` across segments of the same file, the implementation is wrong. Per-segment instability is evidence that the method is measuring programme content rather than a structural band limit — the same failure mode that produced DEF-201 and DEF-609.

**Closure condition:** DEF-609 cannot be closed by adjusting the current threshold parameter. This is a method-level error (H6 — CLAUDE.md §5: "Fixing a wrong method by tuning its parameter" is a known-wrong pattern; DEF-201's first fix moved a threshold from 6 to 20 dB and the method remained wrong). A method change is required. DEF-609 remains open until STORY-F2 implements cliff-detection and QA confirms all five reference tracks report stable, plausible rolloff values.
