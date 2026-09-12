# STORY-027 Architecture — Close the Spectral and Dynamics Correction Gaps

**Version:** 1.4
**Date:** 2026-08-22
**Status:** Draft — §7.3 no_op_threshold_db derivation corrected (DEF-027-002)

---

## Contract

```
Consumes:  stories/STORY-001/implementation/suno_mastering/mastering/corrective_eq.py
           stories/STORY-001/implementation/suno_mastering/mastering/adaptive_harshness.py
           stories/STORY-001/implementation/suno_mastering/mastering/loudness_limit.py
           stories/STORY-001/implementation/suno_mastering/analysis/hf_extension.py
           stories/STORY-012/implementation/harshness_control.py
           stories/STORY-001/implementation/suno_mastering/pipeline.py
           stories/STORY-001/implementation/suno_mastering/report/builder.py
           targets.json  (spectral_bands, de_mud, hard_targets, leveling)
           CLAUDE.md §6.2 (HF extension standing decision)
           ARCHITECTURE.md §3.4 (mastering chain contract)
           STORY-006 Gate 2 review (de_mud §3.4 exception precedent)

Produces:  (a) targets.json changes: new de_mud.correction_cap_db; raised
               sub.correction_cap_db (value flagged for mastering engineer,
               floor ≥8.14 dB per §3.2 derivation);
               new leveling.no_op_threshold_db; new leveling.max_attenuation_db
           (b) corrective_eq.py change: de_mud reads de_mud.correction_cap_db;
               SpectralCorrectiveAction gains residual_gap_db field
           (c) adaptive_harshness.py wired into both shipped entrypoints;
               remains default-off pending targets.json threshold derivation
           (d) analysis change: hf_extension.py wired into measure_all
           (e) mastering/dynamics_leveler.py  (new module)
           (f) pipeline.py change: dynamics leveler stage inserted; pipeline
               passes post_leveler_dr_db to solver (not Stage [2] source_dr_db)
           (g) report/builder.py change: seven-band balance exposed pre/post,
               residual_gap_db in eq_actions

Consumed by: mastering-engineer Gate 1 (mandatory — see §12)
             python-developer / test-case-writer
             qa-automation-engineer
             STORY-025 evaluate_quality_review (must see new stage actions)
```

---

## 1. Design Intent

Four independent gaps are addressed. None requires a new library beyond the
project's existing stack (`pyloudnorm`, `soundfile`, `scipy.signal`, `numpy`).

1. A cap-size fix in the corrective EQ path (item 1 — `corrective_eq.py` and
   `targets.json`).
2. An entrypoint-wiring fix that makes an existing but unreachable stage
   callable (item 2 — `adaptive_harshness.py`, `cli.py`, `master_track.bat`).
3. An analysis wiring fix that surfaces an existing measurement in the report
   (item 3 / prerequisite — `hf_extension.py` into `measure_all`). No lift
   behaviour is added; HF extension remains report-only per CLAUDE.md §6.2
   (see §10 for the explicit architectural rejection).
4. A new dynamics-leveling stage inserted before the loudness solver (item 4 —
   new `mastering/dynamics_leveler.py`).

---

## 2. Pipeline Stage Order

This story inserts one new stage and changes when hf_extension runs:

```
Stage 3a  Corrective EQ          corrective_eq.py      (CHANGED — cap fix)
Stage 3b  Harshness correction   adaptive_harshness.py (CHANGED — wired to entrypoints)
Stage 3c  Dynamics leveling      dynamics_leveler.py   (NEW)
Stage 4   Reintegrate Lows       (unchanged)
Stage 5   Loudness Normalize     loudness_limit.py     (CHANGED — receives post_leveler_dr_db)
Stage 6a  Analysis (post-master) measure_all()         (CHANGED — hf_extension wired in)
Stage 6b  Report                 report/builder.py     (CHANGED — 7-band + residual_gap_db)
```

`measure_all` runs twice per mastering invocation: pre-master (before Stage 3a)
and post-master (Stage 6a). Both calls must include `hf_extension`. ARCHITECTURE.md
§2 requires the same code path on both calls for measurements to be comparable —
this is already satisfied by the existing measure_all structure. Reference-track
analysis is a separate offline step and is not part of a mastering run.

---

## 3. Item 1 — Corrective EQ Cap Fix

### 3.1 Architectural precedents that govern this item

**ARCHITECTURE.md §3.4** specifies: "Spectral correction applies only when
source is **outside** the target range, and only to the nearest edge, capped
at `max_correction_db`."

`de_mud` fires on in-range low_mid sources and aims at a value that is not the
nearest range edge. This was explicitly examined and cleared at STORY-006 Gate 2:

> "Aim point reads `targets.de_mud.correction_aim_point_db = 2.0`, not the
> subset median (3.394). §9 Category B derivation is sound: the 8.67 dB
> low_mid span disqualifies the median per DOMAIN.md §5. PASS."
> — STORY-006 gate2-arch-review.md

The de_mud trigger is a documented, Gate-2-cleared exception to §3.4. The
2.0 dB aim point is unchanged.

**Important:** Gate 2's language notes the two aim candidates "are
distinguishable only in the cap-free interval (+4.0, +5.394)." This reveals
that Gate 2 evaluated aim=2.0 under conditions where cap=2.0 made the aim
nearly moot for all sources above +5.4 dB. Gate 2 approved the pair (aim=2.0,
cap=2.0), not the aim point in isolation. Raising the cap unbundles them for
the first time and makes aim=2.0 fully effective on sources above +5.4 dB.
The aim point must therefore be explicitly re-confirmed at Gate 1 under the
new cap regime — not for change, but for confirmation that the delivered
outcome (§3.3 below) is acceptable.

### 3.2 sub band — range-compliance cap, with shelf delivery efficiency

`sub` source at +6.83 dB exceeds the reference range max (+1.944 dB). This is
a straightforward range-compliance case; de_mud does not apply to sub.

The current `sub.correction_cap_db = 2.0` allows only −2.0 dB of the needed
−4.886 dB nominal correction.

**Sub shelf implementation (from corrective_eq.py and eq.py):**

The sub correction uses an RBJ cookbook low-shelf filter (`_low_shelf_sos`),
corner frequency fc = 60 Hz (the upper edge of the sub band, read as
`sub_t["freq_hz"][1]`), shelf slope S = 1.0 (default, maximum-slope
Butterworth shelf). The design parameter passed to the constructor is
`applied / 2.0`; `sosfiltfilt` doubles it (forward + backward pass), yielding
the full `applied` gain nominally. The actual band-energy delivery is less
than 1.0× because the shelf's transition band covers most of the 20–60 Hz
measurement band.

**Delivery efficiency — from corrective_eq.py docstring:**

```
Sub shelf delivery efficiency over 20–60 Hz band: ~0.60×
(stated in corrective_eq.py docstring; measured against the actual band-energy
 change from the RBJ S=1 shelf at fc=60 Hz on band-limited noise.)
```

The sub corrective_eq.py path now compensates for this efficiency by computing
`nominal_shelf_gain = raw_gap / 0.60` before passing to `_low_shelf_sos`
(DEF-027-004, status: Fixed-Pending-Retest). `action.applied_db` stores the
expected delivered band-level change (`nominal_shelf_gain × 0.60 = raw_gap`),
not the filter design parameter, keeping semantics consistent across bands.

**Minimum cap derivation:**

The cap governs the filter design parameter after efficiency compensation:

```
Required band-energy change (Sunday Club): 4.886 dB
  (src_sub=6.83, range_max_sub=1.944; gap = 6.83 − 1.944 = 4.886 dB)

Filter design parameter needed = 4.886 / 0.60 = 8.143 dB  (raw_gap / efficiency)

Minimum safe sub.correction_cap_db = 8.14 dB  (rounded up)
```

A cap below 8.14 dB cannot deliver the full required correction on Sunday Club.
The 4.886 dB floor stated in v1.1 was incorrect because it did not account for
delivery efficiency; efficiency compensation is now in the implementation path.

**Gate 1 action required:** Mastering engineer to set `sub.correction_cap_db`
to a value ≥8.14 dB, based on the audibility threshold for a 60 Hz RBJ
Butterworth shelf of that magnitude on Suno material. No value is asserted here.

**Incidental effect on the `low` band (60–120 Hz):**

The RBJ low-shelf transition at fc=60 Hz extends above 60 Hz. At fc itself
(60 Hz) the shelf delivers approximately full applied_db after the sosfiltfilt
pass. This means the lower portion of the `low` band (60–90 Hz) sees
substantial attenuation from a large sub correction:

At a nominal applied_db of 8–10 dB (correcting sub excess at cap):
- At 60 Hz: ≈ full applied_db attenuation (shelf boundary)
- At 90 Hz: several dB attenuation (transition still in progress)
- At 120 Hz: ≈ 0 dB (shelf has rolled off into passband)

**Implementation requirement:** The sub correction action log must attribute any
post-correction `low` band measurement shift to shelf spillover, not to a
separate `low`-band anomaly. No additional logic is required to compensate; the
log attribution is sufficient.

**Risk flag:** The 0.60× delivery efficiency figure comes from the
corrective_eq.py docstring. If this figure was measured at a different nominal
correction level (efficiency may vary slightly with magnitude), the minimum cap
floor of 8.14 dB may be slightly off. Implementation must verify the delivery
efficiency at the actual cap value set by the mastering engineer and update the
docstring and `targets.json` comment if the empirical efficiency differs by
more than 0.05.

### 3.3 low_mid band — de_mud cap, aim point unchanged

**Aim point: 2.0 dB — unchanged.** Changing it would require a new Gate 2
review of the STORY-006 decision.

**The cap problem — critical structural observation:**

With cap=2.0 and aim=2.0, the required correction for any de_mud trigger is
`2.0 − src` where src > 4.0. Since src > 4.0 always when de_mud fires,
`|required| = src − 2.0 > 2.0` always. **`cap_reached` is structurally `True`
for every de_mud firing ever.** The aim of 2.0 dB has been unreachable since
STORY-006 shipped, for any source that triggers the rule. This is the primary
reason to raise the cap.

**New field: `de_mud.correction_cap_db`**

```
de_mud.correction_cap_db = range_max_db_re_mid − correction_aim_point_db
                         = 8.52243176025526 − 2.0
                         = 6.52243176025526 dB
```

Derivation: any source within the reference range that triggers de_mud (src up
to range_max = 8.522 dB) should be correctable toward the aim point in a
single pass. The maximum nominal correction required from any in-range source
to the aim is exactly range_max − aim. This is derived from two fields already
in `targets.json` with no rounding.

**Delivered outcome computation (required for Gate 1 confirmation of aim=2.0
under the new cap):**

The peaking bell at the low_mid geometric centre delivers approximately 0.75×
of the applied_db in band-energy terms (per `corrective_eq.py` docstring).
The low_mid path does NOT apply efficiency compensation (DEF-027-004 confirmed
non-compensating is correct for low_mid — `applied_db` stores the raw gap).

For the worst in-range de_mud case (src = 8.522 dB, range_max):
- applied_db = −(8.522 − 2.0) = −6.522 (cap not binding)
- Delivered band-energy change ≈ −6.522 × 0.75 ≈ −4.9 dB
- Post-correction seven-band low_mid ≈ 8.522 − 4.9 ≈ **+3.6 dB re mid**
- Reference range: [−0.145, +8.522]; range median: +3.394
- Landing: inside the range, near the median, well clear of the range floor.

For Sunday Club (src = 6.54 dB):
- applied_db = −(6.54 − 2.0) = −4.54 (cap not binding with cap=6.522)
- Delivered ≈ −4.54 × 0.75 ≈ −3.4 dB
- Post-correction seven-band low_mid ≈ 6.54 − 3.4 ≈ **+3.1 dB re mid**
- Landing: inside the range, near the median.

Both cases land near the reference median (+3.394), inside the reference range,
well clear of the range floor (−0.145).

**Gate 1 confirmation required:** The mastering engineer must review the
delivered outcomes above and confirm that aim=2.0 with cap=6.522 produces
acceptable behaviour on these cases.

**Note on delivery efficiency dependence:** These delivered outcomes depend on
the ~0.75 peaking-bell delivery factor. If the filter or the `applied_db/2`
zero-phase convention is ever changed, the aim point must be revisited. Flag
this as a maintenance note in the implementation.

**targets.json change:** Add `de_mud.correction_cap_db: 6.52243176025526`.

**corrective_eq.py changes:**
1. When trigger is `de_mud`, read `cap_lm = float(de_mud["correction_cap_db"])` 
   (not `float(lm_t["correction_cap_db"])`). The existing `low_mid.correction_cap_db`
   is retained for the range-compliance case.
2. After the post-master seven-band measurement is available, `report/builder.py`
   computes and adds `residual_gap_db = aim_point_db − post_master_relative_db`
   for each corrected band. This satisfies AC3 (see §5.3).

**Precedence rule unchanged:** de_mud checked before range_compliance.
STORY-006 TC-625 must not regress.

### 3.4 H6 check (parameter vs method change)

Both cap changes are parameter changes: the method (peaking bell for low_mid,
low shelf for sub, cap-clamped correction toward an aim) is unchanged. The sub
efficiency compensation (DEF-027-004) is a method addition; it does not change
the filter type or the zero-phase convention.

---

## 4. Item 2 — Harshness Correction Path (2–5 kHz)

### 4.1 Scope reduction — 2–5 kHz, not 2–8 kHz

The implementable scope for this story is **2–5 kHz only.** Reasons:

- The `presence_harsh` three-band measurement covers 2–5 kHz against a
  reference-derived `reference_db`.
- The seven-band `high` band (5–10 kHz) carries `classification: "informational"`
  with no `correction_cap_db` in `targets.json`.
- ARCHITECTURE.md §3.4: "Prohibited: any numeric spectral or dynamics target
  in this stage's source or config." Correcting the `high` band would require
  a `correction_cap_db` derived from the reference set — a target-derivation
  step this story cannot perform.

Open Question 12 from requirements.md explicitly routes this dependency to the
targets-derivation process. The 5–10 kHz gap is a documented scope limit.

### 4.2 Decision: adaptive_harshness.py is the authoritative stereo-sum path

`adaptive_harshness.py` is preferred because:
- It triggers against a reference-derived measurement (`presence_harsh.deviation_db`).
- It has STORY-010's Gate 1 rationale (broad shelf vs narrow cut classification).
- It operates on the stereo sum, correct for mix-level 2–5 kHz measurement.

`harshness_control.py` (STORY-012) is retained as the stem-only supplemental
path. Its `_band_edges("mix")` fallback of (2500, 5000) Hz is not
reference-derived and is inadequate as a primary path. `harshness_control.py`'s
"mix" fallback produces zero actions in the stereo-fallback path and must be
documented as a known no-op for that case.

### 4.3 Threshold derivation pass (2026-08-22)

Threshold derivation completed in the same story (session continuation). Status:

**`narrow_threshold_db` — reference-derived:**
```
range_max_high_mid_db_re_mid (−1.243459886663965)
  − presence_harsh.reference_db (−4.0)
= 2.756540113336035
```
Fires when the track's 2–5 kHz presence level is at or above the top of the
reference population range (Chemical Brothers — Live Again sits exactly at this
level). Committed to `targets.json harshness.narrow_threshold_db`.
`apply_adaptive_harshness()` now reads this from `targets` dict at call time.

**`broad_threshold_db` — admitted placeholder (5.0):**
No reference-population evidence for broad harshness. All three reference tracks
have deviation_db ≤ 2.756 from reference_db(−4.0). 5.0 dB retains the STORY-010
placeholder. A Suno-population measurement of N≥10 tracks with confirmed harshness
is required before this value can be considered derived.

**Gain values (`broad_gain_db`, `narrow_gain_db`, `max_gain_db`) — listening-set,
not reference-derived.** Committed to `targets.json` with explicit derivation
strings noting they are uncalibrated pending DEF-027-008 resolution.

**DEF-027-008 — sosfiltfilt double-pass (Fixed 2026-08-22):**
Both RBJ call sites now pass `gain_db / 2` as the design parameter; `sosfiltfilt`
doubles back to `gain_db` at ω₀. Delivery verified by unit tests: peaking at 3162 Hz
delivers −3.0 dB ±0.5 dB; low-shelf below 3500 Hz delivers −2.0 dB ±0.5 dB.
`max_gain_db=4.0` now correctly caps the delivered gain at 4.0 dB (not 8.0 dB).

**Remaining `enabled = False` default.** One gate remains before default-on:
- `broad_threshold_db` population-derived value (N≥10 Suno tracks with confirmed harshness).

**AC5 partial satisfaction:** Reachability delivered (STORY-027). `narrow_threshold_db`
now reference-derived. Default-fire blocked by DEF-027-008. QA must not mark AC5 fully met.

### 4.4 STORY-010 third branch (reference-target mismatch)

Explicitly deferred. STORY-010 TC-0103 has no corresponding code in
`adaptive_harshness.py`. This story does not implement it.

### 4.5 Stem path — what covers the stereo-fallback

The stereo-fallback coverage is answered by routing the fallback to
`adaptive_harshness.py` (once the flag is used). `harshness_control.py`'s "mix"
fallback is a known no-op for that case, not silently relied upon.

---

## 5. Item 0 (Prerequisite) — Seven-Band Balance in Report

### 5.1 Current state

`pipeline.py` Stage [4b] calls `measure_seven_band_balance()` for all 7 bands
but extracts only `sub`, `low_mid`, and `mid` into `pre_band_levels`. The
report contains no seven-band block. The three-band `frequency_balance` block
covers different frequency ranges (e.g. `low_mid_mud` is 200–500 Hz vs.
seven-band `low_mid` at 120–500 Hz) and must not be substituted.

### 5.2 Report schema change

`pipeline.py` extracts all 7 bands and stores the full dict. `report/builder.py`
adds:

```json
"seven_band_balance": {
  "before": {
    "sub":      { "relative_db": ..., "range_min": ..., "range_max": ..., "in_range": ... },
    "low":      { "relative_db": ... },
    "low_mid":  { "relative_db": ..., "range_min": ..., "range_max": ..., "in_range": ..., "de_mud_triggered": ... },
    "mid":      { "relative_db": ... },
    "high_mid": { "relative_db": ..., "range_min": ..., "range_max": ..., "in_range": ... },
    "high":     { "relative_db": ..., "range_min": ..., "range_max": ..., "in_range": ... },
    "air":      { "relative_db": ..., "range_min": ..., "range_max": ..., "in_range": ... }
  },
  "after": { ...same structure... }
}
```

`range_min`/`range_max` are omitted for `low` and `mid` (degenerate reference
ranges in targets.json). The `in_range` boolean is derived at report time.
The existing `frequency_balance` block is unchanged.

The report schema must include a disambiguation note that seven-band band names
do not correspond to the three-band band names by frequency range.

### 5.3 Residual gap field (AC3)

After the post-master analysis runs, `report/builder.py` computes:

```
residual_gap_db = aim_point_db - post_master_seven_band_relative_db[band]
```

for each band that appears in `eq_actions`. A positive `residual_gap_db` means
the aim was not fully reached. This field is added to the
`SpectralCorrectiveAction` schema (or equivalently, to the `eq_actions` entries
in the report JSON). Satisfies AC3.

### 5.4 DSP cost

`measure_seven_band_balance` already runs at Stage [4b]; the computation is not
added, only the results are stored rather than partially discarded. No DSP cost
increase.

---

## 6. Item 3 — HF Extension Wiring and Explicit Rejection of HF Lift

### 6.1 Architectural rejection of HF lift — CLAUDE.md §6.2

**No HF lift behaviour is implemented in this story.**

Reasons (each independently sufficient):
1. CLAUDE.md §6.2 standing decision has not been cleared by Gate 1.
2. The wired per-file band-limit prerequisite did not exist before this story.
3. DEF-009-001 (open): HF-territory processing on Suno material was judged
   "highly destructive to the track" at the listening gate.
4. STORY-007 `STATIONARY_WHISTLE` detection operates in this frequency range.
5. The motivating track (Sunday Club) shows no flagged air-band excess.
6. Suno exports typically band-limit at 13–16 kHz; boosting above the measured
   limit amplifies the noise floor (DOMAIN.md §4).

**Gate 1 confirmed decision:** HF lift/shimmer is rejected for STORY-027.
This is a standing Gate 1 recorded decision, not a silent omission.

### 6.2 What IS implemented — hf_extension.py wiring

- `analysis.measure_all()` adds a call to `measure_hf_extension(audio, sr,
  config)` from `analysis/hf_extension.py`.
- Result populates `Measurements.hf_band_limit_hz` (nullable, already declared
  in ARCHITECTURE.md §3.2) and `Measurements.hf_band_limit_confidence`.
- Both before and after report blocks expose these fields.
- Both pre-master and post-master `measure_all` calls include `hf_extension`.
- `hf_extension.py`'s public API is unchanged; only the call site is added.

**Runtime cost flag for Gate 1:** Two full PSD+segment calls per run. Gate 1
to decide whether per-segment analysis should be config-gated.

---

## 7. Item 4 — Intra-Track Dynamics Leveling

### 7.1 Design overview

New `mastering/dynamics_leveler.py` implements a short-time loudness ride that
reduces arrangement-level loudness swings. Sits at Stage 3c, before the
LUFS/DR/TP solver.

**Stem vs sum (AC17):** Operates on the stereo sum. Arrangement-level loudness
variation is a property of the complete mix; per-stem leveling changes relative
stem balance, which is compositional mixing, not mastering.

**Metric for acceptance (AC15):** Window-based loudness range/std is the primary
acceptance metric. TT DR is a hard constraint, not the acceptance target. They
move independently: downward gain riding reduces window-LUFS std while
simultaneously reducing TT DR. QA verifies both independently.

**Stage is inert until targets.json has a `leveling` block (DEF-027-002):** When
`targets.json` has `leveling: null` or the key is absent, the stage returns
immediately: `LevelingAction(applied=False, reason="leveling_targets_not_derived",
...)` and populates `post_leveler_dr_db` from the unchanged buffer. This is the
correct pipeline contract; no code change is needed to preserve it. The stage
becomes active after the targets.json derivation pass specified in §7.3.

### 7.2 Algorithm

A numpy-based time-varying gain envelope operating on second-to-second
timescales. A DAW-grade note-level compressor (millisecond attack/release) is
the wrong tool for arrangement-level variation.

**Step 1 — Window-loudness computation (ungated K-weighted mean-square):**

**Rationale for switching from integrated_loudness (DEF-027-001 resolution):**
`pyloudnorm.Meter.integrated_loudness()` applies a relative gate *within* each
window. A window straddling a section boundary (e.g. breakdown→drop) gates out
the quieter half and returns a LUFS value biased toward the loud half. The
resulting uniform gain over the whole 3-second chunk then over-attenuates the
pre-transition zone. This is a method defect, not a parameter defect (H6). The
fix is to measure K-weighted mean-square without intra-window gating.

**Implementation:**
```
1. Apply BS.1770 K-weighting to the full audio buffer:
   a. Pre-filter (high-shelf, accounts for acoustic head effect):
      scipy.signal.sosfilt(kw_prefilter_sos, audio, axis=0)
   b. Highpass (2nd-order Butterworth at 38.135 Hz):
      scipy.signal.sosfilt(kw_highpass_sos, kw_filtered, axis=0)
   Design both filters using scipy.signal at the track's sample rate.
   Use scipy.signal.sosfilt (single-pass forward, not sosfiltfilt) —
   zero-phase is not required for loudness measurement.

2. Compute K-weighted mean-square over sliding windows:
   window_samples = int(3.0 * sr)
   hop_samples    = int(0.10 * sr)   # 100 ms hop
   For n in range(0, len(audio) - window_samples + 1, hop_samples):
       window = kw_filtered[n : n + window_samples]
       ms[n]  = numpy.mean(window ** 2)  # mean across samples AND channels

3. Convert to LUFS (no gating):
   L[n] = -0.691 + 10.0 * log10(ms[n])   if ms[n] > 0
   L[n] = -inf                             if ms[n] == 0 (silent window)

4. For silent windows (ms[n] == 0 / L[n] = -inf): assign gain_db = 0.0
   (pass-through). Do not propagate -inf into the gain envelope.

5. Result: vector L[n] of per-window LUFS values, 100 ms resolution, no gating.
```

The 100 ms hop provides finer resolution than the previous non-overlapping 3 s
blocks, removing the step quantisation that the 1.5 s IIR smoothing was
compensating for. The 3 s window length is retained for temporal consistency.

**K-weighting coefficients** are derived from the BS.1770-4 specification at the
track's actual sample rate. The coefficients are computed once on entry to
`apply_dynamics_leveler` using `scipy.signal.bilinear_zpk` or
`scipy.signal.iirfilter` with the standard continuous-time prototype. They are
not hardcoded — they must be sample-rate-correct or the K-weighting is wrong.

**Step 2 — Target:**
- Internal target = mean of finite `L[n]` values. This is the track's own
  windowed mean, not the downstream LUFS target. The two are independent.

**Step 3 — Gain envelope:**
- `gain_db[n] = target_mean_L − L[n]` for finite L[n]; 0.0 for gated windows.
- **Downward-only:** `gain_db[n] = min(gain_db[n], 0.0)`. Never boost.
  Rationale: avoids new true-peak violations entering the solver; the solver
  handles final loudness unconditionally. Downward-only cannot create new
  true-peak violations — satisfied by construction.
- **Attenuation cap:** `gain_db[n] = max(gain_db[n], −max_attenuation_db)`
  where `max_attenuation_db` comes from `targets.json: leveling.max_attenuation_db`.
  This is the sole cap; there is no DR-derived runtime cap (see §7.4).
- Up-sample to sample rate and smooth with a first-order IIR low-pass at
  1.5-second time constant, yielding a continuous linear-scale envelope `g[t]`.

**Step 4 — Apply:**
- `audio_out = audio_in * g[t][:, None]` (float64 throughout; broadcasting
  over channels; shape (N, 2) in, (N, 2) out).

**Step 5 — Gate (AC16 negative control):**
- `std_L = std of finite L[n]`.
- If `std_L < no_op_threshold_db` (from targets.json, see §7.3): return audio
  unchanged with `LevelingAction(applied=False,
  reason="loudness_range_below_threshold", ...)`.

### 7.3 No-op threshold and maximum attenuation derivation (targets.json)

Both values come from the targets.json `leveling` block. Neither may be hardcoded
in stage source per ARCHITECTURE.md §3.4.

**`leveling.no_op_threshold_db` — derivation (DEF-027-002 resolution, 2026-08-21):**

**The v1.3 median() procedure was tried and failed.** The procedure specified in
v1.3 (median of block-LUFS std across the three reference tracks) was executed
using `_compute_block_lufs` (non-overlapping 3-second blocks, per-block
K-weighting, -70 LUFS absolute gate — the same function the runtime gate uses).
Results:

| Track | Block-LUFS std |
|-------|----------------|
| Chemical Brothers — Live Again | 4.75 dB |
| GusGus — Over (Arabian Horse) | 4.15 dB |
| Black Flute (Remastered) | 2.74 dB |
| **Sunday Club (motivating)** | **2.02 dB** |

`median(4.75, 4.15, 2.74) = 4.15 dB` — above Sunday Club's std of 2.02 dB.
Committing 4.15 dB would leave the leveling stage permanently inert on the
motivating track. Root cause: the procedure assumed reference masters would have
lower loudness variation than Suno-generated material. The opposite is true:
all three reference masters (professional dance/electronic productions) have
substantially more arrangement-level dynamics than Sunday Club. The median
aggregator does not rescue the procedure when all three references are outliers
in the wrong direction.

**Replacement: absolute threshold calibrated to Suno material (DEF-027-002 path a).**

```
no_op_threshold_db = 1.0 dB
```

Derivation: 1.0 dB is below Sunday Club's measured block-LUFS std (2.02 dB),
the lowest known motivating-track std. The leveler fires on any track with more
than 1.0 dB arrangement-level loudness variation — conservative enough to avoid
false triggers on uniformly-produced Suno outputs. The median() procedure is
abandoned for this target; the reference-master population is not the correct
reference population for a leveler that targets Suno-generated material.

Measurement method used for this threshold: `_compute_block_lufs`
(non-overlapping 3-second blocks, per-block K-weighting, -70 LUFS absolute
gate) — the same function the runtime gate uses, ensuring threshold and gate
use identical measurement.

Committed to `targets.json` 2026-08-21. Revisit trigger: when >=3 Suno
motivating-population tracks are measured, recalibrate against that population.

**`leveling.max_attenuation_db` — derivation and initial candidate:**

This is the ceiling on per-window downward gain, set by listening. The procedure:

```
For max_attenuation_db candidates of 2, 3, 4, 5 dB:
  Apply the leveler to Sunday Club reference track with that ceiling.
  Listen at the 1.5 s smoothing time constant for audible pumping at
  section boundaries (drop entrances, breakdown exits).
  The smallest value where pumping becomes perceptible becomes the ceiling.
```

**Initial candidate for the first listening pass: 3.0 dB.** Rationale: a 3 dB
attenuation at the 1.5 s smoothing time constant produces a gain envelope that
changes at approximately 2 dB/s — within the temporal masking threshold for
most material. Inter-section loudness variation in Suno tracks typically spans
6–10 LU; a 3 dB ceiling corrects roughly half of a typical swing without
forcing a second-pass correction. This is an empirical starting point, not a
derived value — the mastering engineer's listening test may revise it. Committed
to `targets.json` 2026-08-21 as the §7.3 initial candidate; AC21 listening
confirmation is still required.

### 7.4 Maximum attenuation cap and DR interaction

**The pre-emptive `dr_budget × 0.5` cap is removed (rationale from v1.2):**

The formula was impotent by construction: on Sunday Club (source_dr=9.0,
dr_floor=8.0) it gave effective_max=0.5 dB; on reference-compliant tracks it
approached zero. Root cause: it used the pre-leveler Stage [2] DR as the
baseline, compensating for the wrong reference. Replacement: re-measure TT DR
from the leveled audio buffer, pass `post_leveler_dr_db` to the solver.

**DR re-measurement:** After `audio_out` is computed, measure TT DR via numpy
crest factor on the leveled buffer: `peak_rms_db − mean_rms_db`. This is a
simple in-memory numpy operation, not a `measure_all` call.

**Sole remaining cap:** `targets.json: leveling.max_attenuation_db` — the
audibility/quality ceiling. No DR-derived runtime cap.

**DR proof — scope and limitation (DEF-027-003):**

The v1.2 proof showed: `post_leveler_dr ≤ source_dr` (Stage [2] pre-EQ
measurement) because downward-only leveling lowers crest factor. This proof
holds for the leveler in isolation. However, the pipeline order is:

```
Stage 3a: sub EQ (corrective_eq.py) → Stage 3c: leveler → Stage 5: solver
```

A large sub-band shelf cut (up to 9 dB nominal with the new cap) reduces RMS
in the 20–60 Hz band. If sub-band energy is a material fraction of the track's
total RMS, reducing it can **raise** TT DR (reduced RMS, peaks largely
unchanged). In that case:

```
post_EQ_dr  > source_dr   (EQ raised crest factor)
post_leveler_dr  ≤ post_EQ_dr  (leveler is downward-only relative to its input)

∴  post_leveler_dr may be > source_dr
```

When this occurs, the solver receives `post_leveler_dr_db > source_dr_db`:

```
dr_required = max(dr_floor, post_leveler_dr_db − dr_max_reduction_db)
            > max(dr_floor, source_dr_db − dr_max_reduction_db)   [when post_leveler > source]
```

The solver's dr_required is **higher** than it would have been without the
leveler stage — the constraint is tighter, not looser.

**Assessment — this is accurate calibration, not a regression:**

If sub EQ raises TT DR, the audio entering the solver genuinely has more
dynamic range than the Stage [2] baseline. The solver's dr_required correctly
reflects this: it is asking "can we preserve the DR that this audio actually
has?" A higher dr_required means the solver rejects solutions that would
over-limit the now-more-dynamic audio. This is the correct behaviour.

The only scenario where this causes a problem: the EQ-raised DR plus the
solver's limiting push `dr_required` to a level no candidate can satisfy,
producing `UnresolvableMasteringConstraintError`. This would be a genuine
constraint (the target is unachievable for this audio), not a spurious
regression introduced by the leveler. The solver's existing error path handles
it correctly.

**However, a practical guard is warranted:** The sub correction only raises TT
DR if sub-band energy is a material fraction of overall RMS. For most Suno
tracks (pop, dance), the sub band (20–60 Hz) contributes 5–15% of total power.
A 9 dB sub cut on a 10% power fraction reduces total RMS by ≈0.46 dB. This
could raise crest factor by up to 0.46 dB — a marginal effect on dr_required.
For tracks with heavy bass (sub fraction 25–30%), the effect approaches 1.5 dB.

**Test requirement for DEF-027-003 (add to §7.7):** Run the full pipeline on
Sunday Club (which has a large sub correction) with leveler enabled. Verify
`post_leveler_dr_db` vs `source_dr_db` in the LevelingAction log. If
`post_leveler_dr_db > source_dr_db`, verify the solver does not raise
`UnresolvableMasteringConstraintError` and the mastered track's DR satisfies
`achieved_dr ≥ dr_required`. If the error fires, it is a genuine constraint —
report to the mastering engineer, not a code defect.

**STORY-006/STORY-025 contract compatibility:**

`solve_loudness_and_limit` accepts any `float` for `source_dr_db`. Passing
`post_leveler_dr_db` uses the same parameter with an accurate baseline. No API
change. The solver's guarantee ("achieved DR ≥ dr_required") remains in force.

### 7.5 Module contract

```python
@dataclass
class LevelingAction:
    applied: bool
    reason: str              # "leveling_applied" | "loudness_range_below_threshold"
                             # | "leveling_targets_not_derived"
    std_lufs_before: float
    std_lufs_after: float | None    # None if not applied
    max_gain_db_applied: float      # most negative value; 0.0 if not applied
    window_count: int
    gated_windows: int
    post_leveler_dr_db: float       # TT DR measured from leveled (or unchanged) audio;
                                    # always populated; pipeline passes this to solver

def apply_dynamics_leveler(
    audio: np.ndarray,          # float64, shape (N, 2)
    sr: int,
    targets: dict,              # parsed targets.json
    config,                     # MasteringConfig
) -> tuple[np.ndarray, LevelingAction]:
    ...
```

`source_dr_db` is **not** a parameter to the leveler. The leveler measures
`post_leveler_dr_db` from its output and returns it. `pipeline.py` passes that
value to the solver. The Stage [2] `source_dr_db` is used only for Stage [2]
logging and is not passed through to the leveler.

### 7.6 Float64 and bit-identity

All arithmetic uses float64 throughout. K-weighting filters use
`scipy.signal.sosfilt` with float64 arrays. Gain envelope computation:
`10.0 ** (gain_db / 20.0)` in float64. Output shape and dtype identical to
input. No float32 conversion. Reproducibility: the envelope computation is
deterministic for identical input and config (no wall-clock or random elements).

### 7.7 Testability (independently verifiable against synthetic signals)

- **Positive case (ungated):** Alternating-loudness stereo signal (3 s burst
  at −10 dBFS RMS, 3 s silence, repeated). Verify `std_lufs_after <
  std_lufs_before`, `applied: True`. Verify `post_leveler_dr_db` is populated.
  Verify using the K-weighted ungated method (not integrated_loudness) to compute
  expected L[n] values for the fixture.
- **Section boundary case (DEF-027-001 regression guard):** Construct a 6-second
  signal where the first 4 s is −10 dBFS and the last 2 s is −30 dBFS, placed
  so a 3 s window straddles the boundary. Verify the gain applied to the first
  3 s does not over-attenuate the quiet zone. The ungated measurement must
  produce a lower gain than the gated measurement would have.
- **Negative control:** Uniform-loudness signal (std below `no_op_threshold_db`).
  Verify `applied: False, reason: "loudness_range_below_threshold"`. Verify
  `post_leveler_dr_db` equals the input crest factor (no change).
- **Inert state (DEF-027-002):** Invoke with `targets.json: leveling: null`.
  Verify `applied: False, reason: "leveling_targets_not_derived"`.
  Verify `post_leveler_dr_db` is populated from the unchanged buffer.
- **Gated windows:** Signal with silent windows interleaved. Verify silent
  windows receive `gain = 1.0` and do not shift the mean loudness target.
- **DR handoff:** Construct a signal where downward leveling measurably reduces
  TT DR (3 dB burst reduction). Verify `post_leveler_dr_db < pre_leveler_dr`
  in LevelingAction. Verify solver receives `post_leveler_dr_db`.
- **Large-sub-EQ DR interaction (DEF-027-003 guard):** Full pipeline on Sunday
  Club (large sub correction) with leveler enabled. Verify `post_leveler_dr_db`
  vs `source_dr_db` in the LevelingAction log. Verify no
  `UnresolvableMasteringConstraintError`. Verify `achieved_dr ≥ dr_required`
  in SolverOutcome. If `post_leveler_dr_db > source_dr_db`, log the delta —
  this is the EQ-induced crest factor increase, not a leveler regression.
- **Solver regression guard:** On Sunday Club with leveler on vs off, verify
  `SolverOutcome.below_documented_lufs_floor` and error counts do not increase.

---

## 8. Library Choices

| Need | Library | Used in |
|---|---|---|
| K-weighting filter design | `scipy.signal` (bilinear_zpk / iirfilter) — BS.1770 compliant at any sr | `dynamics_leveler.py` |
| Windowed K-weighted mean-square, gain envelope | `numpy` | `dynamics_leveler.py` |
| pyloudnorm | Retained for LUFS measurements elsewhere in the pipeline | NOT used in leveler window measurement (see DEF-027-001) |
| Corrective EQ filters (zero-phase) | `scipy.signal.sosfiltfilt` — unchanged | `corrective_eq.py` |
| Harshness cut filters (zero-phase) | `scipy.signal.sosfiltfilt` — unchanged | `adaptive_harshness.py` |
| PSD computation for hf_extension | existing `_psd` module — unchanged | `hf_extension.py` |
| File read/write | `soundfile` — unchanged | `io/ingest.py`, `io/export.py` |

**Why pyloudnorm is NOT used for leveler window measurement (DEF-027-001):**
`Meter.integrated_loudness()` applies a relative gate within each window. This
causes a measurement bias when a window straddles a section boundary (the
quieter half is gated out, the LUFS value is biased toward the loud half, and
uniform gain over the window over-attenuates the pre-transition zone). The fix
is K-weighted ungated mean-square via scipy + numpy. pyloudnorm remains in use
elsewhere in the pipeline for integrated-loudness measurements that correctly
use gating.

**Why not pedalboard for the leveler:** `pedalboard.Compressor` is a sample-
accurate note-level compressor (millisecond attack/release). Arrangement-level
variation is a 3+ second phenomenon. The correct tool is a slow numpy gain
envelope, which stays float64 throughout.

**Why not pedalboard for adaptive_harshness:** `adaptive_harshness.py`'s
`sosfiltfilt` implementation uses the project's established zero-phase doubling
convention (`applied_db / 2` to constructors). Replacing with pedalboard
introduces a float32 boundary (ARCHITECTURE.md §1.5), changes the transfer
function, and would break bit-identical output. No requirement asks for this.

**Zero-phase convention and bit-identity note:** The `applied_db / 2` convention
in `corrective_eq.py` is load-bearing for delivered-correction accounting. It
must not be changed alongside the cap fix.

---

## 9. Non-Destructive Handling

- Originals are never modified. All stages operate on in-memory float64 copies.
- The pipeline's existing non-destructive integrity check (hash comparison) is
  unchanged.
- Every new correction path logs its action in the report per AC19.
- Item 3 (hf_extension wiring) is analysis-only; it never modifies audio.

---

## 10. Explicit Architectural Rejection — HF Lift

Per requirements.md AC13 and CLAUDE.md §6.2:

**Item 3's HF lift (air/shimmer) is rejected for implementation in STORY-027.**

See §6.1 for the six independently sufficient reasons. Recorded as confirmed
Gate 1 decision. A future story may revisit if: the wired band-limit measurement
is in place, Gate 1 grants a scoped exception to §6.2, DEF-009-001 is resolved,
and a human listening result supports the change.

---

## 11. Open Architectural Risks and Flagged Items

1. **sub.correction_cap_db — Gate 1 required, floor ≥8.14 dB** (§3.2):
   Delivery efficiency ~0.60× over 20–60 Hz. Minimum safe nominal cap =
   4.886 / 0.60 = 8.14 dB. Mastering engineer must set ≥8.14 dB based on
   audibility. Implementation must verify 0.60× efficiency at actual cap.

2. **de_mud aim point under new cap — Gate 1 confirmation required** (§3.3):
   aim=2.0 cleared by STORY-006 Gate 2 under conditions where it was moot.
   Gate 1 must confirm delivered outcomes (+3.6 dB worst case, +3.1 dB Sunday
   Club) are acceptable under the new cap=6.522 regime.

3. **AdaptiveHarshnessConfig thresholds** (§4.3 updated 2026-08-22): `narrow_threshold_db`
   reference-derived (2.756540113336035) and in targets.json. DEF-027-008 fixed (gain
   doubling resolved). `broad_threshold_db` remains admitted placeholder (5.0, no
   population evidence). Default-on blocked only by `broad_threshold_db` derivation.

4. **AC5 partially satisfied** (§4.3): Reachability delivered; `narrow_threshold_db`
   derived; gain delivery correct (DEF-027-008 fixed). Default-fire blocked pending
   `broad_threshold_db` derivation (N≥10 Suno tracks). QA must not mark AC5 fully met.

5. **no_op_threshold_db calibrated to single track** (§7.3): Value 1.0 dB is
   calibrated against Sunday Club alone. When ≥3 Suno motivating-population
   tracks are measured, recalibrate against that population. The current value
   is conservative (below the one known motivating-track std by 1.02 dB) and
   will fire on any track with >1 dB arrangement-level variation.

6. **max_attenuation_db listening test pending** (§7.3, §7.4): Initial candidate
   3.0 dB committed to targets.json. AC21 listening confirmation still required;
   pumping at section boundaries may require downward revision.

7. **hf_extension runtime cost** (§6.2): Two full PSD+segment calls per run.
   Gate 1 to decide whether per-segment analysis is config-gated.

8. **Effective 2–5 kHz scope for item 2** (§4.1): 5–10 kHz requires separate
   targets-derivation story.

9. **STORY-025 evaluate_quality_review schema** (§7.5): LevelingAction schema
   must be confirmed before implementation. `dr_budget_db` (v1.1) is removed;
   `post_leveler_dr_db` replaces it.

10. **de_mud precedence and above-range sources** (§3.3): For src > 8.522 dB,
    de_mud fires (aim 2.0) before range_compliance (aim 1.944). Gate-2-cleared.
    QA must not expect range_max as the aim for above-range low_mid.

11. **sub shelf spillover into `low` band** (§3.2): At ≥8.14 dB nominal,
    60 Hz shelf transition attenuates the lower `low` band (60–90 Hz).
    Implementation must attribute `low` band shift to spillover in the log.

12. **0.60× sub efficiency at large corrections** (§3.2): Efficiency may vary
    with correction magnitude. Implementation must verify and record.

13. **K-weighting coefficients must be sample-rate-correct** (§7.2 Step 1):
    The BS.1770 K-weighting filters depend on sample rate. The implementation
    must compute them via scipy.signal at the actual track sample rate, not use
    hardcoded coefficients (which are only valid at one specific sr).

14. **DEF-027-003 EQ-induced DR increase** (§7.4): For tracks with heavy sub
    content and large sub corrections, post_leveler_dr_db may exceed source_dr_db.
    This is correct calibration. The DEF-027-003 guard test (§7.7) is the safety
    net; if `UnresolvableMasteringConstraintError` fires, it is a genuine
    constraint, not a code defect.

---

## 12. Gate 1 Requirements

Gate 1 review is **mandatory** before implementation, for:

- **Item 1 (low_mid de_mud aim re-confirmation):** Confirm aim=2.0 with the
  delivered outcomes in §3.3. If unacceptable, aim or cap must be revised.
- **Item 1 (sub cap — floor ≥8.14 dB):** Mastering engineer to set
  `sub.correction_cap_db` ≥8.14 dB based on audibility of a 60 Hz RBJ
  Butterworth shelf at that magnitude. The efficiency compensation is now in
  the implementation path (DEF-027-004 fixed).
- **Item 2 (harshness reachability):** Confirm reachable-but-default-off
  approach; confirm thresholds routed to targets.json derivation.
- **Item 3 (HF rejection — confirmed):** Recorded as Gate 1 decision.
- **Item 4 (targets.json derivation):** `no_op_threshold_db = 1.0 dB` committed
  per DEF-027-002 path a (§7.3 v1.4). `max_attenuation_db = 3.0 dB` committed
  as initial candidate; AC21 listening confirmation still required.
- **Item 4 (DR handoff):** Confirm that passing `post_leveler_dr_db` to the
  solver is acceptable under STORY-006/STORY-025 contracts. Confirm that
  EQ-induced DR increases (DEF-027-003) are treated as accurate calibration.
- **Item 4 (solver regression test):** Confirm §7.7 guard tests — including
  the DEF-027-003 large-sub-EQ case — are included in the test-case-writer's
  brief.

---

## 13. Testability Notes

All items are independently testable against synthetic signals:

- **Item 1 sub:** Noise burst at 30 Hz above range_max. Assert
  trigger=range_compliance, applied_db of expected magnitude (≤ cap after
  efficiency compensation), cap_reached as appropriate. Verify `low` band
  spillover logged.
- **Item 1 low_mid de_mud:** Band-shaped signal with low_mid=6.54 dB. Assert
  trigger=de_mud, applied_db=4.54, cap_reached=False (cap=6.522). Assert
  residual_gap_db populated post-master.
- **Item 1 negative control:** sub within range, low_mid below de_mud threshold.
  Assert zero SpectralCorrectiveAction entries. TC-625 must not regress.
- **Item 2 reachable:** Invoke with `--harshness-correction`. Assert actions
  non-empty for signal with presence_harsh above threshold. Invoke without.
  Assert zero actions (default-off preserved).
- **Item 3 report wiring:** Any track output must contain `hf_band_limit_hz`
  and `hf_band_limit_confidence`. Verify with 15 kHz-filtered noise (expect
  ~15 kHz) and full-band pink noise (expect null).
- **Item 4 leveler:** See §7.7 — seven test cases specified.

---

## 14. Assumptions Pending Mastering-Engineer / BA Confirmation

1. STORY-006 Gate 2-cleared aim=2.0 is not re-derived. Gate 1 re-confirmation
   of aim=2.0 under the new cap regime is required. If this reading is wrong,
   the architecture must be revised before implementation.

2. No sub.correction_cap_db value is asserted. Floor is ≥8.14 dB per §3.2
   derivation. Mastering engineer decides final value by listening.

3. `leveling.max_attenuation_db` initial candidate is 3.0 dB (§7.3). Committed
   to targets.json 2026-08-21. AC21 listening confirmation still required.

4. `leveling.no_op_threshold_db = 1.0 dB` is committed to targets.json
   2026-08-21 per DEF-027-002 path a. The §7.3 median() procedure over reference
   tracks is abandoned for this target. Recalibration required when ≥3 Suno
   motivating-population tracks are available.

5. The solver change (post_leveler_dr_db replacing source_dr_db) is backward-
   compatible. Gate 1 must confirm that EQ-induced DR increases (producing
   post_leveler_dr_db > source_dr_db) are treated as accurate calibration rather
   than a regression signal.

---

## Revision History

- 2026-08-21 v1.0: Initial architecture for STORY-027.
- 2026-08-21 v1.1: Advisor review changes:
  - §3.1: Added Gate 2 unbundling note.
  - §3.3: cap_reached structurally True for every de_mud firing. Added delivered-
    outcome calculations. Added delivery-efficiency dependence flag.
  - §3.2: Removed asserted interim sub cap of 5.0 dB.
  - §5.3: Added residual_gap_db field.
  - §7.3: Added no_op_threshold_db aggregation contingency.
  - §7.4: Added solver regression guard and moved max_attenuation_db to targets.json.
  - §6.2/§2: Corrected measure_all call count from 3 to 2 per run.
  - §4.3: Added explicit "AC5 partially satisfied" label.
- 2026-08-21 v1.2: Gate 1 blocker resolution:
  - BLOCKER 1 (DR coupling impotent): §7.4 replaced. Pre-emptive dr_budget×0.5
    cap removed. Option (a) adopted: re-measure TT DR post-leveler; pass to
    solver. Proof: dr_required_new ≤ dr_required_old. LevelingAction schema
    updated (dr_budget_db removed; post_leveler_dr_db added).
  - BLOCKER 2 (sub cap floor): §3.2 expanded. Sub shelf: RBJ, fc=60 Hz,
    slope=1.0. Delivery efficiency ~0.60×. Minimum cap = 4.886/0.60 = 8.14 dB
    (not 4.886 dB as in v1.1). Incidental low-band spillover documented.
  - §7.3: no_op_threshold aggregation confirmed as median() unconditionally.
  - §6.1/§10: HF lift rejection confirmed as Gate 1 decision.
- 2026-08-21 v1.3: Architectural defects resolved (DEF-027-001, -002, -003):
  - DEF-027-001 (BS.1770 intra-window gating bias): §7.2 Step 1 replaced.
    `pyloudnorm.Meter.integrated_loudness()` replaced with K-weighted ungated
    mean-square (BS.1770 short-term equivalent). K-weighting via scipy.signal
    (two-stage IIR: pre-filter + highpass), windowed mean-square at 100 ms hop.
    pyloudnorm is NOT used for leveler window measurement. §8 library table
    updated. §7.7 added section-boundary regression guard test. §11 added
    risk 13 (K-weighting coefficients must be sr-correct). Derivation procedure
    in §7.3 updated to specify K-weighted ungated method for reference tracks.
  - DEF-027-002 (leveling targets not derived): §7.1 added explicit inert-state
    behaviour (reason="leveling_targets_not_derived" when leveling block absent).
    §7.3 concrete derivation procedure specified; median() aggregator confirmed
    unconditionally with rationale. max_attenuation_db initial candidate 3.0 dB
    specified with derivation rationale. §12 Gate 1 updated with both leveling
    values. §14 updated.
  - DEF-027-003 (EQ-induced DR increase): §7.4 proof narrowed to leveler-internal
    scope. Assessment added: EQ-raised DR yields higher post_leveler_dr_db than
    source_dr, which makes solver constraints tighter — this is accurate
    calibration, not regression. Practical magnitude estimate provided. Guard test
    added to §7.7. Risk 14 added to §11. §12 Gate 1 updated.
  - DEF-027-004 (sub efficiency non-compensating, Fixed-Pending-Retest): §3.2
    and §3.4 updated to reflect that efficiency compensation is now in the
    implementation path; action.applied_db stores expected delivered band-level
    change (not filter design parameter). Low_mid path confirmed non-compensating.
- 2026-08-22 v1.4: DEF-027-002 architect resolution — §7.3 no_op_threshold_db
  derivation corrected:
  - §7.3: v1.3 median() procedure over reference tracks was executed and failed.
    All three reference masters (Chemical Brothers 4.75 dB, GusGus 4.15 dB,
    Black Flute 2.74 dB block-LUFS std) exceed Sunday Club's std (2.02 dB);
    median()=4.15 dB would suppress leveling on the motivating track. Procedure
    abandoned. Replaced with absolute threshold calibrated to Suno material:
    no_op_threshold_db = 1.0 dB (DEF-027-002 path a), committed to targets.json.
  - §11: Risk 5 updated — median() procedure replaced; calibration note added.
  - §12: Gate 1 item 4 updated to reflect committed values.
  - §14: Assumption 4 updated to reflect committed value and abandonment of
    median() procedure.
  - Implementation note: targets.json now has the leveling block with
    no_op_threshold_db=1.0. The stage is no longer inert. If the implementation
    was relying on the "leveling_targets_not_derived" inert path, it will now
    execute — verify TC-2761 (second-pass no-op) and TC-2752 (gated windows)
    still pass with the threshold in place.
