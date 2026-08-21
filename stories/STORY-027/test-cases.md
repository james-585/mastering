# STORY-027 Test Cases — Close Spectral and Dynamics Correction Gaps

**Story:** STORY-027
**Version:** 1.1
**Date:** 2026-08-21
**Covers:** AC0–AC21, NFR from requirements.md
**Architecture version:** 1.2
**Gate 1 review:** gate1-review.md (Blockers 1 and 2 resolved)

---

## How to Read These Test Cases

No implementation was read. Test cases are derived from architecture.md v1.2,
requirements.md, and gate1-review.md. Every expected value either:
(a) is derived analytically from how the fixture was constructed, or
(b) is traced to architecture.md's explicit derivation (§3.2, §3.3, §7.4), or
(c) is flagged as `[OPEN]` where no derivation exists yet.

**Why band-limited noise, not single tones:** Delivery efficiency figures (sub ~0.60×,
low_mid ~0.75×) are band-energy-weighted averages across the entire measurement band.
A single tone samples one point on the filter transfer function. A 30 Hz sine sits deep
in the low-shelf plateau where delivery ≈ 1.0× (not 0.60×); a 250 Hz sine sits at the
peaking bell's geometric centre where delivery ≈ 1.0× (not 0.75×). Band-limited noise
filling the whole band is required to reproduce these factors — without it, every expected
landing value is wrong and TC-2711 selects the incorrect implementation.

**Unit discipline.** All loudness values are LUFS (BS.1770) unless stated as dBFS (sample
amplitude domain) or dBTP (true peak). Seven-band `relative_db` values are stated as
"dB re mid" throughout. `applied_db` is the nominal filter-gain parameter; `delivered_db`
is the actual band-energy change in the target band after filtering. These differ by the
delivery efficiency (~0.60× sub shelf, ~0.75× low_mid bell).

---

## Open Questions Affecting Expected Values

| OQ | Question | Affected TCs |
|---|---|---|
| OQ-A | Does `corrective_eq.py` pre-compensate for sub shelf delivery efficiency (`applied_db = gap / 0.60`) or apply the raw gap? Architecture §3.2 derives the 8.14 dB minimum cap floor from this efficiency but the `corrective_eq.py` changes list (§3) does not specify the compensation step. TC-2711 asserts the delivered outcome (band-energy change in 20–60 Hz must reach range_max) and will distinguish both implementations. | TC-2711 |
| OQ-B | `leveling.no_op_threshold_db` — pending reference-track derivation pass (architecture §7.3). Tests that must force the gate to fire inject a value. | TC-2751, TC-2752, TC-2756, TC-2761, TC-2780, TC-2783, TC-2784 |
| OQ-C | `leveling.max_attenuation_db` — pending mastering-engineer listening derivation (architecture §7.4). Tests that exercise the cap inject a known value. | TC-2750, TC-2756 |
| OQ-D | Boundary inclusivity at `src_db = range_max = 8.522` for de_mud: does exactly 8.522 produce `cap_reached=False`? architecture §3.3 derives cap = 6.522 exactly. | TC-2722 |
| OQ-E | `UnresolvableMasteringConstraintError` — exact module import path. | TC-2754 |
| OQ-F | Architecture §7.2 Step 1 uses `pyloudnorm.Meter(sr).integrated_loudness(window_audio)`, which applies BS.1770 relative gating *within* each 3-second chunk. gate1-review Concern 2 identifies this as incorrect for straddling windows (quiet half gated out, biasing the LUFS and over-attenuating the pre-transition zone). Architecture v1.2 does not resolve this. TC-2760 tests this and is marked `[OPEN — Concern 2 unresolved in v1.2]`. | TC-2760 |
| OQ-G | `sub.correction_cap_db = 9.0` is the Gate 1 confirmed value (gate1-review v1.2 follow-up Decision). | TC-2713 |

---

## Fixture Specifications

All frequency-band fixtures use band-limited noise, not single-frequency tones. Every
fixture includes in-range filler in all seven bands to prevent unintended range-compliance
corrections on empty bands (which would read as −∞ and fall below range_min).

```python
import numpy as np
from scipy.signal import butter, sosfiltfilt

def band_noise(f_low: float, f_high: float, rms_target: float,
               n: int, sr: int, rng: np.random.Generator) -> np.ndarray:
    """White noise bandpassed to [f_low, f_high] Hz, scaled to rms_target."""
    raw = rng.standard_normal(n)
    sos = butter(N=4, Wn=[f_low, f_high], btype='bandpass', fs=sr, output='sos')
    filtered = sosfiltfilt(sos, raw)
    actual_rms = np.sqrt(np.mean(filtered ** 2))
    return filtered * (rms_target / actual_rms)
```

### Common fixture construction parameters

```python
SR   = 44100
DUR  = 5.0       # seconds (sufficient for seven-band measurement)
N    = int(SR * DUR)
RNG  = np.random.default_rng(seed=42)   # fixed seed → deterministic
RMS_MID = 0.10   # mid-band reference amplitude (-20 dBFS)
```

### Amplitude helpers (relative to `RMS_MID`)

```python
def rms_for_relative_db(relative_db: float) -> float:
    """Return the RMS amplitude that places this band at relative_db re mid."""
    return RMS_MID * (10 ** (relative_db / 20.0))
```

### In-range filler levels (used in all multi-band fixtures)

```
low:      0.0  dB re mid  (60–120  Hz; no range target; informational)
low_mid:  3.0  dB re mid  (120–500 Hz; in range [-0.145, 8.522]; below de_mud threshold 4.0)
high_mid: -2.0 dB re mid  (2000–5000 Hz; inside its reference range)
high:     -4.0 dB re mid  (5000–10000 Hz; inside its reference range)
air:      -14.0 dB re mid (10000–20000 Hz; inside air range [-20.05, -11.44])
```

---

### F-01: Sub-excess signal (src = +6.83 dB re mid)

```python
sub_sig = band_noise(20,    60,    rms_for_relative_db(6.83),  N, SR, RNG)
low_sig = band_noise(60,    120,   rms_for_relative_db(0.0),   N, SR, RNG)
lm_sig  = band_noise(120,   500,   rms_for_relative_db(3.0),   N, SR, RNG)  # in range, below de_mud
mid_sig = band_noise(500,   2000,  RMS_MID,                     N, SR, RNG)
hm_sig  = band_noise(2000,  5000,  rms_for_relative_db(-2.0),  N, SR, RNG)
hi_sig  = band_noise(5000,  10000, rms_for_relative_db(-4.0),  N, SR, RNG)
air_sig = band_noise(10000, 20000, rms_for_relative_db(-14.0), N, SR, RNG)
mono_F01 = sub_sig + low_sig + lm_sig + mid_sig + hm_sig + hi_sig + air_sig
audio_F01 = np.stack([mono_F01, mono_F01], axis=1).astype(np.float64)
```

Ground truth: `sub.relative_db` = +6.83 dB re mid ± 0.2 dB (analytically from RMS ratio
construction; tolerance covers band-integration boundary effects). `low_mid.relative_db`
= +3.0 dB re mid ± 0.2 dB (in range, de_mud not triggered). sub range_max = +1.944 dB.
Required delivered correction to reach range edge: 4.886 dB. Required nominal applied
(if compensating for 0.60× efficiency): 4.886 / 0.60 = 8.14 dB. Cap = 9.0 dB → not binding.

---

### F-02: de_mud near-threshold signal (src ≈ +4.1 dB re mid low_mid)

```python
sub_sig_F02 = band_noise(20,    60,    rms_for_relative_db(0.5),  N, SR, RNG)  # sub in range
lm_sig_F02  = band_noise(120,   500,   rms_for_relative_db(4.1),  N, SR, RNG)  # just above threshold
mid_sig_F02 = band_noise(500,   2000,  RMS_MID,                    N, SR, RNG)
# ... add low, high_mid, high, air filler at in-range levels (same as F-01)
audio_F02 = np.stack([mono_F02, mono_F02], axis=1).astype(np.float64)
```

Ground truth: `low_mid.relative_db` = +4.1 dB re mid ± 0.2 dB. de_mud triggers (4.1 > 4.0).
`applied_db` = −(4.1 − 2.0) = −2.1 dB. Cap = 6.522 dB → not binding. Delivered ≈ −2.1 × 0.75
= −1.575 dB. Post `low_mid.relative_db` ≈ **+2.525 dB re mid ± 0.3 dB**.
Inside reference range [−0.145, +8.522]; above range floor.

---

### F-03: Sunday Club low_mid case (src = +6.54 dB re mid)

```python
lm_sig_F03 = band_noise(120, 500, rms_for_relative_db(6.54), N, SR, RNG)
sub_sig_F03 = band_noise(20,  60, rms_for_relative_db(0.5),  N, SR, RNG)  # sub in range
# ... add remaining bands at in-range filler levels
audio_F03 = np.stack([mono_F03, mono_F03], axis=1).astype(np.float64)
```

Ground truth: `low_mid.relative_db` = +6.54 dB re mid ± 0.2 dB. `applied_db` = −4.54 dB.
Cap = 6.522 dB → not binding. Delivered ≈ −4.54 × 0.75 = −3.405 dB.
Post `low_mid.relative_db` ≈ **+3.1 dB re mid ± 0.3 dB** (architecture §3.3).

---

### F-04: de_mud worst-case (src = +8.522 dB re mid, low_mid at range_max)

```python
lm_sig_F04 = band_noise(120, 500, rms_for_relative_db(8.522), N, SR, RNG)
# sub in range; other bands at filler levels
audio_F04 = np.stack([mono_F04, mono_F04], axis=1).astype(np.float64)
```

Ground truth: `low_mid.relative_db` = +8.522 dB re mid ± 0.2 dB. `applied_db` = −6.522 dB
(= range_max − aim; see OQ-D for `cap_reached`). Delivered ≈ −4.892 dB.
Post `low_mid.relative_db` ≈ **+3.6 dB re mid ± 0.3 dB** (architecture §3.3).

---

### F-05: Above-range low_mid, de_mud cap binding (src = +10.0 dB re mid)

```python
lm_sig_F05 = band_noise(120, 500, rms_for_relative_db(10.0), N, SR, RNG)
# sub in range; other bands at filler levels
audio_F05 = np.stack([mono_F05, mono_F05], axis=1).astype(np.float64)
```

Ground truth: `low_mid.relative_db` = +10.0 dB re mid ± 0.2 dB (above range_max = 8.522).
de_mud fires first (precedence rule). `applied_db` = −6.522 dB (capped). `cap_reached = True`.
Delivered ≈ −4.892 dB. Post `low_mid.relative_db` ≈ **+5.1 dB re mid ± 0.3 dB**.

---

### F-06: In-range negative control (no corrections expected)

```python
sub_sig_F06 = band_noise(20,  60,  rms_for_relative_db(0.5), N, SR, RNG)  # sub in range
lm_sig_F06  = band_noise(120, 500, rms_for_relative_db(3.0), N, SR, RNG)  # in range, below threshold
# all other bands at in-range filler levels
audio_F06 = np.stack([mono_F06, mono_F06], axis=1).astype(np.float64)
```

Ground truth: sub in range, low_mid in range and below threshold. Zero corrections expected.

---

### F-07: Alternating-loudness leveler fixture (4 distinct non-gated levels)

```python
sr_lev = 44100
windows_F07 = []
for level_dBFS in [-20.0, -16.0, -12.0, -8.0]:
    amplitude = 10 ** (level_dBFS / 20.0)
    t_win = np.arange(int(sr_lev * 3.0)) / sr_lev
    win = amplitude * np.sin(2 * np.pi * 440.0 * t_win)
    windows_F07.append(np.stack([win, win], axis=1))
audio_F07 = np.concatenate(windows_F07, axis=0).astype(np.float64)   # 12 s, shape (N,2)
```

Ground truth (direction only; exact LUFS depends on K-weighting at 440 Hz):
All four windows are above BS.1770 absolute gate (well above −70 LUFS). Assuming LUFS ≈ dBFS
(within ~0.5 LU for a 440 Hz tone): mean_L ≈ −14 LUFS, `std_lufs_before` ≈ √20 ≈ **4.47 LU**.
Direction assertion is unconditional: `std_lufs_after < std_lufs_before`.
Downward-only leveling with cap ≥ 8 dB: windows at −12 and −8 attenuated toward mean −14;
windows at −20 and −16 unchanged. Post levels ≈ −20/−16/−14/−14. `std_lufs_after` ≈ √6 ≈ **2.45 LU**.
Requires injected `max_attenuation_db ≥ 8.0` (OQ-C) and `no_op_threshold_db < 4.47 LU` (OQ-B).

---

### F-08: No-op fixture (stationary-loudness, non-zero TT DR)

```python
rng_noop = np.random.default_rng(seed=42)
n_noop = int(44100 * 30.0)
noise = rng_noop.standard_normal(n_noop)
noise /= np.std(noise)
noise *= 10 ** (-12.0 / 20.0)      # −12 dBFS RMS
audio_F08 = np.stack([noise, noise], axis=1).astype(np.float64)
```

Ground truth: `std_L` over 3-second windows ≈ 0.3–0.5 LU (stochastic, noise statistics).
TT DR (peak block RMS minus mean block RMS) ≈ 10 dB (established for Gaussian noise; crest
factor ≈ 10 dB). Test injects `no_op_threshold_db = 2.0` (well above 0.3–0.5 LU) to guarantee
gate fires. Expected `post_leveler_dr_db` ≈ 10 dB ± 3 dB, not None, not 0.0.

---

### F-09: Drop-entrance smoothing fixture (quiet → loud step transition)

```python
t_pre  = np.arange(int(44100 * 5.0))  / 44100
t_drop = np.arange(int(44100 * 30.0)) / 44100
pre_section  = (10 ** (-26.0/20.0)) * np.sin(2*np.pi*440*t_pre)
drop_section = (10 ** (-10.0/20.0)) * np.sin(2*np.pi*440*t_drop)
mono_F09 = np.concatenate([pre_section, drop_section])
audio_F09 = np.stack([mono_F09, mono_F09], axis=1).astype(np.float64)   # 35 s
```

Ground truth: both sections are above BS.1770 absolute gate. Pre-drop window LUFS ≈ −29 LUFS;
drop window LUFS ≈ −13 LUFS (approximate; 440 Hz K-weight offset). Drop is louder than mean
→ downward gain applied at drop entrance. The gain steps from 0 dB toward a negative final
value `G_final` at the first sample of the drop. The IIR smooths toward `G_final` with τ=1.5 s.
See TC-2757 for analytic assertions.

---

### F-10: Brickwalled noise at 15 kHz (HF detection)

30-second pink noise at −18 dBFS brickwall low-pass filtered at exactly 15 000 Hz
via a high-order `scipy.signal.firwin` FIR (N ≥ 1001, 44.1 kHz). Stereo.
Ground truth: `hf_band_limit_hz` ≈ 15 000 ± 500 Hz.

---

### F-11: Full-band pink noise (HF negative control)

30-second unfiltered pink noise at −18 dBFS, 44.1 kHz stereo. No artificial cutoff.
Ground truth: `hf_band_limit_hz = null` (no band limit detected; naturally declining
HF spectrum must not be misidentified as a brick-wall cutoff).

---

### F-12: Gated-window fixture for TC-2752 (2 gated + 3 non-gated levels)

```python
# 5 windows × 3 s = 15 s total
# Windows: -16 / -90 / -10 / -90 / -6 dBFS
# Windows at -90 dBFS are below BS.1770 absolute gate → gated
windows_F12 = []
for level_dBFS in [-16.0, -90.0, -10.0, -90.0, -6.0]:
    amp = 10 ** (level_dBFS / 20.0)
    t_w = np.arange(int(44100 * 3.0)) / 44100
    w = amp * np.sin(2*np.pi*440*t_w)
    windows_F12.append(np.stack([w, w], axis=1))
audio_F12 = np.concatenate(windows_F12, axis=0).astype(np.float64)
```

Ground truth: `gated_windows = 2`. Non-gated window LUFS ≈ −19, −13, −9 LUFS (approx for
440 Hz; K-weighting offset ~+4 dB → LUFS ≈ dBFS + 4 − 23 LU relative; direction is known).
std_lufs_before (non-gated) ≈ 5 LU (three levels spread ≈ 10 LU). Applied=True (non-gated
windows have different LUFS). Requires `no_op_threshold_db < 5 LU` (OQ-B).

---

### F-13: Sunday Club reference file (Slow fixture)

`artifacts/Sunday Club_mastered_report.json` run 2026-08-20, plus corresponding source file.
Known: sub source = +6.83 dB re mid; low_mid source = +6.54 dB re mid; source DR = 9.0 TT.

---

## Section 1 — Prerequisite: Seven-Band Balance Report (AC0)

### TC-2701 — Seven-band block present in report for all 7 bands
**Covers:** AC0
**Type:** Functional
**Preconditions:** F-01.

**Steps:**
1. Run the pipeline on F-01.
2. Parse output report JSON. Inspect `seven_band_balance.before` and `seven_band_balance.after`.

**Expected result:**
- Both `before` and `after` blocks present with exactly 7 keys: `sub`, `low`, `low_mid`, `mid`, `high_mid`, `high`, `air`.
- Each entry contains a `relative_db` field (finite float).
- Bands with reference ranges (`sub`, `low_mid`, `high_mid`, `high`, `air`) include `range_min`, `range_max`, `in_range` fields.
- `in_range` is a boolean derived correctly from `relative_db` vs range bounds.
- `low` and `mid` have `relative_db` but no `range_min`/`range_max` (degenerate ranges — architecture §5.2).

---

### TC-2702 — Seven-band and three-band blocks coexist without substitution
**Covers:** AC0 (three-band must remain unchanged)
**Type:** Functional
**Preconditions:** F-06.

**Steps:**
1. Run pipeline on F-06. Parse report JSON.

**Expected result:**
- `frequency_balance` block is present and contains `low_end`, `low_mid_mud`, `presence_harsh`.
- `seven_band_balance` block is present separately.
- `frequency_balance.low_mid_mud.reference_db` (200–500 Hz) is not overwritten by any seven-band value.
- `seven_band_balance.before.low_mid.relative_db` (120–500 Hz) and `frequency_balance.before.low_mid_mud` cover overlapping but different frequency ranges and may differ numerically — no assertion requires them to agree.

---

### TC-2703 — `residual_gap_db` populated in eq_actions for corrected bands
**Covers:** AC0 (§5.3), AC3
**Type:** Functional
**Preconditions:** F-03 (de_mud fires for low_mid).

**Steps:**
1. Run pipeline on F-03. Find `eq_actions` entry for `low_mid`.

**Expected result:**
- Entry contains `trigger: "de_mud"` and `residual_gap_db` field.
- `residual_gap_db = aim_point_db − post_master_seven_band_low_mid_relative_db`.
- Numerically: post ≈ +3.1 dB, aim = 2.0, so `residual_gap_db ≈ −1.1 dB ± 0.3 dB`.
- Negative `residual_gap_db` (post landed past the aim toward the reference median) is expected and correct.

---

### TC-2704 — `seven_band_balance.before` reflects pre-correction state
**Covers:** AC0
**Type:** Functional
**Preconditions:** F-03.

**Steps:**
1. Run pipeline on F-03. Compare `seven_band_balance.before.low_mid.relative_db` to the known fixture value.

**Expected result:**
- `seven_band_balance.before.low_mid.relative_db` = +6.54 dB ± 0.2 dB (matches F-03 construction).
- `seven_band_balance.after.low_mid.relative_db` = +3.1 dB ± 0.3 dB (post-correction).
- The `before` value is not updated by the correction.

---

### TC-2705 — HF extension fields present in both report sections
**Covers:** AC0, architecture §6.2
**Type:** Functional
**Preconditions:** F-11.

**Steps:**
1. Run pipeline on F-11. Parse both pre-master and post-master report sections.

**Expected result:**
- Both sections contain `hf_band_limit_hz` and `hf_band_limit_confidence`.
- For F-11: `hf_band_limit_hz = null` in both sections.
- `hf_band_limit_confidence` is a float in [0.0, 1.0] or null.

---

## Section 2 — Item 1: Sub-Band Correction (AC1)

### TC-2710 — Sub correction reaches range edge (happy path)
**Covers:** AC1
**Type:** Audio-quality / Functional
**Preconditions:** F-01. Confirmed: `sub.correction_cap_db = 9.0`, `sub.range_max_db_re_mid = 1.944`.

**Steps:**
1. Run corrective EQ on F-01.
2. Read `seven_band_balance.after.sub.relative_db` and `eq_actions` entry for `sub`.

**Expected result:**
- `eq_actions` contains entry for `sub` with `trigger: "range_compliance"`.
- `seven_band_balance.after.sub.relative_db` ≤ +1.944 dB re mid (at or inside range edge).
- `seven_band_balance.after.sub.in_range = True`.
- `cap_reached = False` (see TC-2713 for cap boundary; see OQ-A for applied_db mechanism).
- Sanity: `relative_db` > −10 dB re mid (not overcorrected).

---

### TC-2711 — Sub delivery efficiency: delivered 20–60 Hz band-energy change reaches aim (Blocker 2 key test)
**Covers:** AC1, architecture §3.2, gate1-review Blocker 2 resolution
**Type:** Audio-quality (mandatory named test)
**Preconditions:** F-01 (band-limited noise 20–60 Hz at +6.83 dB re mid). Required: `sub.correction_cap_db = 9.0`.

**Steps:**
1. Compute 20–60 Hz band RMS of F-01 before corrective EQ: `rms_sub_before`.
   (Bandpass filter 20–60 Hz on the input; compute RMS.)
2. Run corrective EQ on F-01.
3. Compute 20–60 Hz band RMS of the corrected output: `rms_sub_after`.
4. `delivered_db = 20 * log10(rms_sub_after / rms_sub_before)`.
5. Read `seven_band_balance.after.sub.relative_db`.

**Expected result:**
- `delivered_db ≈ −4.886 dB ± 0.5 dB` (sufficient to reach range_max = +1.944 from source = +6.83).
- `seven_band_balance.after.sub.relative_db` ≈ +1.944 dB ± 0.5 dB (at range edge).

**OQ-A discrimination:** With F-01's band-limited noise, the 0.60× shelf delivery factor applies:
- Non-compensating implementation (`applied_db = raw_gap = 4.886`): delivered ≈ 0.60 × 4.886 = **2.93 dB**.
  Post = 6.83 − 2.93 = **+3.90 dB — still above range_max (+1.944)**. This test FAILS. AC1 not met.
- Compensating implementation (`applied_db = 4.886 / 0.60 = 8.14`): delivered ≈ 0.60 × 8.14 = **4.88 dB**.
  Post ≈ **+1.944 dB — at range edge**. This test PASSES. AC1 met.
The fixture correctly distinguishes the two branches.

---

### TC-2712 — Sub in-range: no correction fires (negative control; STORY-006 TC-625 guard)
**Covers:** AC1 (negative control)
**Type:** Functional / Regression
**Preconditions:** F-06 (sub at +0.5 dB re mid, inside range [−3.747, +1.944]).

**Steps:**
1. Run corrective EQ on F-06. Read `eq_actions`.

**Expected result:**
- No `eq_actions` entry with `band: "sub"`.
- `seven_band_balance.before.sub.relative_db` ≈ +0.5 dB ± 0.2 dB.
- `seven_band_balance.after.sub.relative_db` ≈ +0.5 dB ± 0.2 dB (unchanged).

---

### TC-2713 — Sub cap not binding at the confirmed cap value (cap=9.0 dB)
**Covers:** AC1, Gate 1 Decision (gate1-review v1.2 follow-up, OQ-G)
**Type:** Functional / Boundary
**Preconditions:** F-01 (gap = 4.886 dB; nominal applied ≈ 8.14 dB via OQ-A compensating path; both < cap=9.0).

**Steps:**
1. Run corrective EQ on F-01. Read `cap_reached` from sub `eq_actions` entry.

**Expected result:**
- `cap_reached = False`.

---

### TC-2714 — Sub shelf spillover into `low` band is logged as spillover, not an anomaly
**Covers:** AC1, architecture §3.2 (spillover note)
**Type:** Functional
**Preconditions:** F-01.

**Steps:**
1. Run pipeline on F-01. Read `seven_band_balance.before.low.relative_db` and `.after.low.relative_db`.
2. Read `eq_actions` for any entry with `band: "low"`.

**Expected result:**
- `after.low.relative_db < before.low.relative_db` (shelf transition at fc=60 Hz attenuates 60–90 Hz;
  architecture §3.2 quantifies ~4–5 dB at 80 Hz at 9 dB nominal).
- No `eq_actions` entry with `band: "low"` (the drop is not a `low`-band correction; it is shelf spillover).
- The sub `eq_actions` entry or report log attributes the `low`-band shift to spillover.
- Sanity: `after.low.relative_db` does not drop below −15 dB re mid (overcorrection guard).

---

### TC-2715 — Sub correction: `cap_reached=True` when correction exceeds cap
**Covers:** AC1 (cap boundary)
**Type:** Boundary
**Preconditions:** Construct signal with sub_relative_db = +20.0 dB re mid (gap = 18.056 dB;
nominal required = 18.056 / 0.60 ≈ 30 dB via OQ-A, or 18.056 dB raw; both exceed cap=9.0).
Use `rms_for_relative_db(20.0)` for sub band noise in F-01 structure.

**Steps:**
1. Run corrective EQ on the fixture.
2. Read `cap_reached` from sub `eq_actions` entry.

**Expected result:**
- `cap_reached = True`.
- `applied_db ≤ 9.0` (capped).
- `seven_band_balance.after.sub.relative_db` > +1.944 dB (cap insufficient to reach range edge at this extreme — expected and correct).

---

## Section 3 — Item 1: Low_mid De_mud (AC2, AC3, AC4)

### TC-2720 — de_mud near-threshold case (gate1 Concern 1 mandatory test)
**Covers:** AC2, AC3; gate1-review.md Concern 1 (explicitly required)
**Type:** Audio-quality (mandatory)
**Preconditions:** F-02 (low_mid = +4.1 dB re mid via band-limited noise 120–500 Hz).

**Steps:**
1. Run corrective EQ on F-02.
2. Read `eq_actions` for `low_mid`: `trigger`, `applied_db`, `cap_reached`.
3. Read `seven_band_balance.after.low_mid.relative_db`.

**Expected result:**
- `trigger: "de_mud"`.
- `applied_db` = −2.1 dB ± 0.1 dB (= −(4.1 − 2.0)).
- `cap_reached = False` (2.1 < cap = 6.522).
- `seven_band_balance.after.low_mid.relative_db` ≈ **+2.525 dB ± 0.3 dB** re mid.
  (Delivered: −2.1 × 0.75 = −1.575 dB applied to band-energy; post = 4.1 − 1.575 = 2.525.)
- `in_range = True` (2.525 is inside [−0.145, +8.522]).
- Note (gate1-review Concern 1): near-threshold triggers land BELOW the reference median (+3.394)
  — mild cases land furthest from the median. This is expected; not a defect. The test
  confirms it is inside the range and above the range floor.

---

### TC-2721 — Sunday Club low_mid de_mud (src = 6.54 dB)
**Covers:** AC2, AC3
**Type:** Audio-quality
**Preconditions:** F-03 (low_mid = +6.54 dB re mid via band-limited noise).

**Steps:**
1. Run corrective EQ on F-03.
2. Read `applied_db`, `cap_reached`, `seven_band_balance.after.low_mid.relative_db`, `residual_gap_db`.

**Expected result:**
- `trigger: "de_mud"`.
- `applied_db` = −4.54 dB ± 0.1 dB.
- `cap_reached = False` (4.54 < 6.522).
- `seven_band_balance.after.low_mid.relative_db` ≈ **+3.1 dB ± 0.3 dB** re mid.
  (Delivered: −4.54 × 0.75 = −3.405 dB; post = 6.54 − 3.405 = 3.135.)
- `residual_gap_db ≈ 2.0 − 3.1 = −1.1 dB ± 0.3 dB` (negative = post passed the aim; correct).
- Measurably closer to aim than old cap=2.0 allowed (+6.54 − 1.5 ≈ +5.04 was old effective post).

---

### TC-2722 — Worst-case de_mud (src = range_max = +8.522 dB)
**Covers:** AC2, AC3; OQ-D (boundary inclusivity)
**Type:** Audio-quality / Boundary
**Preconditions:** F-04 (low_mid = +8.522 dB re mid via band-limited noise).

**Steps:**
1. Run corrective EQ on F-04.
2. Read `applied_db`, `cap_reached`, `seven_band_balance.after.low_mid.relative_db`.

**Expected result:**
- `trigger: "de_mud"` (de_mud fires first even at range_max).
- `applied_db` = −6.522 dB ± 0.1 dB.
- `cap_reached`: [OPEN — OQ-D; `False` if clamp uses strict `<`, `True` if `≤`].
- `seven_band_balance.after.low_mid.relative_db` ≈ **+3.6 dB ± 0.3 dB** re mid.
  (Delivered: −6.522 × 0.75 = −4.892 dB; post = 8.522 − 4.892 = 3.630.)
- `in_range = True`. Near reference median (+3.394).

---

### TC-2723 — Above-range low_mid: de_mud fires first, cap binding
**Covers:** AC2, architecture §11 risk 10
**Type:** Functional / Boundary
**Preconditions:** F-05 (low_mid = +10.0 dB re mid, above range_max = 8.522).

**Steps:**
1. Run corrective EQ on F-05. Read `trigger`, `applied_db`, `cap_reached`.

**Expected result:**
- `trigger: "de_mud"` (not `range_compliance` — precedence rule; de_mud fires first even above range).
- `applied_db` = −6.522 dB (clamped at cap).
- `cap_reached = True`.
- `seven_band_balance.after.low_mid.relative_db` ≈ **+5.1 dB ± 0.3 dB** re mid (inside range).
- Note: range_compliance aim (+1.944) is NOT used here. de_mud aim (+2.0) governs but cap prevents reaching it.

---

### TC-2724 — low_mid in-range below de_mud threshold: no correction (negative control)
**Covers:** AC4 (negative control)
**Type:** Functional
**Preconditions:** F-06 (low_mid at +3.0 dB re mid, inside range and below 4.0 threshold).

**Steps:**
1. Run corrective EQ on F-06. Read `eq_actions`.

**Expected result:**
- No entry with `band: "low_mid"` in `eq_actions`.
- `seven_band_balance.before.low_mid.relative_db` ≈ +3.0 dB ± 0.2 dB.
- `seven_band_balance.after.low_mid.relative_db` ≈ +3.0 dB ± 0.2 dB (unchanged).

---

### TC-2725 — de_mud reads `de_mud.correction_cap_db`, not `low_mid.correction_cap_db`
**Covers:** AC2, architecture §3.3 change 1
**Type:** Functional / Regression
**Preconditions:** F-03. Verify `targets.json` contains `de_mud.correction_cap_db ≈ 6.522` and
`low_mid.correction_cap_db` (= 2.0, retained for range-compliance case).

**Steps:**
1. Confirm targets.json contains both fields.
2. Run corrective EQ on F-03. Confirm `applied_db = −4.54` (not −2.0).

**Expected result:**
- `applied_db ≈ −4.54` (governed by `de_mud.correction_cap_db = 6.522`).
- `cap_reached = False`.
- If `applied_db = −2.0` and `cap_reached = True`: regression — old `low_mid.correction_cap_db`
  is governing the de_mud path. Test fails.

---

### TC-2726 — de_mud precedes range_compliance (STORY-006 TC-625 regression guard)
**Covers:** AC4, architecture §3.3 precedence rule
**Type:** Regression
**Preconditions:** F-05 (low_mid = +10.0 dB, above range_max).

**Steps:**
1. Run corrective EQ on F-05.
2. Verify `trigger = "de_mud"` and `aim_point_db = 2.0`.

**Expected result:**
- `trigger: "de_mud"`, not `"range_compliance"`.
- `aim_point_db = 2.0` (de_mud aim), not `+1.944` (range_max).
- If `trigger = "range_compliance"` or `aim ≠ 2.0`: STORY-006 TC-625 regression.

---

## Section 4 — Item 2: Harshness Correction Reachability (AC5a/AC5b, AC6, AC7, AC8)

> **AC5 is partially satisfied per architecture §4.3.** TC-2730/2731 cover AC5a (entrypoint
> reachability — delivered). AC5b (fires by default on excess) is deferred pending
> targets.json threshold derivation. No test asserts default-on behaviour.

### TC-2730 — Adaptive harshness reachable from cli.py without stem separation (AC5a)
**Covers:** AC5a; architecture §4.3
**Type:** Functional (named mandatory test)
**Preconditions:** Stereo bandpassed noise 2–5 kHz at −2 dBFS RMS, 10 s. `adaptive_harshness`
currently default-off.

**Steps:**
1. Invoke `python -m suno_mastering <input> --harshness-correction`.
2. Inspect exit code and report JSON.

**Expected result:**
- Process exits without exception (unrecognised-flag error would indicate the wiring is absent).
- `adaptive_harshness_actions` field is present in the report.
- Stage is demonstrably reached (log entry or report field indicating invocation occurred).

---

### TC-2731 — Adaptive harshness reachable from master_track.bat without stem separation (AC5a)
**Covers:** AC5a; architecture §4.3
**Type:** Functional (named mandatory test)
**Preconditions:** Same signal as TC-2730.

**Steps:**
1. Invoke `master_track.bat <input> --harshness-correction`.
2. Inspect exit code and report JSON.

**Expected result:**
- Process exits successfully.
- Report contains `adaptive_harshness_actions` field.
- No unrecognised-argument error for the flag.

---

### TC-2732 — Adaptive harshness default-off (no flag = no actions)
**Covers:** AC5a/AC5b boundary; architecture §4.3 (enabled=False default preserved)
**Type:** Functional
**Preconditions:** Same 2–5 kHz excess signal. Invoked WITHOUT `--harshness-correction`.

**Steps:**
1. Run pipeline without `--harshness-correction`. Read `adaptive_harshness_actions`.

**Expected result:**
- `adaptive_harshness_actions` is empty (`[]`) or absent.
- No harshness correction applied.

---

### TC-2733 — Actions logged when harshness correction enabled and excess present
**Covers:** AC5a, AC19
**Type:** Functional
**Preconditions:** Signal with `presence_harsh.deviation_db > 5.0 dB` (above
`AdaptiveHarshnessConfig.broad_threshold_db = 5.0`). Invoked with `--harshness-correction`.
Note: `presence_harsh.reference_db = −4.0` is a round number (gate1-review Concern 3);
exact threshold relationship is [OPEN — Concern 3 unresolved]. Construct signal to be well
above threshold (deviation > 7 dB) to avoid boundary ambiguity.

**Steps:**
1. Invoke with `--harshness-correction`. Read `adaptive_harshness_actions`.

**Expected result:**
- `adaptive_harshness_actions` is non-empty.
- Each entry contains `before_db`, `after_db`, `classification` (`broad_shelf` or `narrow_cut`), `applied_db`.
- `applied_db < 0.0` (attenuation only).
- `after_db < before_db` (reduction confirmed).

---

### TC-2734 — No harshness actions on compliant material (negative control, AC7)
**Covers:** AC7; requirements.md Finding 2 (Sunday Club `presence_harsh` not flagged)
**Type:** Functional / Negative control
**Preconditions:** F-06 (no 2–5 kHz excess by construction). Invoked WITH `--harshness-correction`.

**Steps:**
1. Invoke with `--harshness-correction` on F-06. Read `adaptive_harshness_actions`.

**Expected result:**
- `adaptive_harshness_actions` is empty (`[]`).
- Correction must not fire on material that does not exceed the threshold.

---

### TC-2735 — harshness_control.py documented no-op on stereo-fallback path (AC6)
**Covers:** AC6, architecture §4.5
**Type:** Functional / Regression
**Preconditions:** Pipeline without `--split-stems`. Any signal.

**Steps:**
1. Run without stem separation. Read `harshness_control_actions`.

**Expected result:**
- `harshness_control_actions` is empty (`[]`).
- The report field is present (not absent) — no silent no-op.
- Architecture §4.5 states this is the documented stereo-fallback behaviour; this test confirms
  it and guards against STORY-012 accidentally starting to fire on the "mix" fallback.

---

## Section 5 — Item 3: HF Extension Wiring (AC9; AC10–13 rejected)

> **AC10–AC13 (HF lift behaviour) are rejected at Gate 1 Decision 1.** No test covers HF lift
> implementation — such tests would test architecture not implemented. Traceability table records
> these ACs as "Not tested — HF lift rejected at Gate 1 Decision 1."

### TC-2740 — `hf_band_limit_hz` present in report on any pipeline run
**Covers:** AC9, architecture §6.2
**Type:** Functional
**Preconditions:** F-11 (full-band pink noise).

**Steps:**
1. Run pipeline on F-11. Parse report JSON.

**Expected result:**
- Both pre-master and post-master sections contain `hf_band_limit_hz` and `hf_band_limit_confidence`.
- For F-11: `hf_band_limit_hz = null`.
- `hf_band_limit_confidence`: null or 0.0 when band limit is null.

---

### TC-2741 — Brickwalled noise at 15 kHz detected correctly
**Covers:** AC9; architecture §13 item 3
**Type:** Audio-quality
**Preconditions:** F-10 (15 kHz brickwall).

**Steps:**
1. Run pipeline on F-10. Read `hf_band_limit_hz` from pre-master report section.

**Expected result:**
- `hf_band_limit_hz` ≈ 15 000 Hz ± 500 Hz.
- `hf_band_limit_confidence` > 0.5.

---

### TC-2742 — Full-band pink noise: no false cutoff detected (negative control)
**Covers:** AC9; DOMAIN.md §7 (threshold-based detection is wrong pattern)
**Type:** Audio-quality / Negative control
**Preconditions:** F-11 (unfiltered pink noise — naturally declining HF spectrum, no cliff).

**Steps:**
1. Run pipeline on F-11. Read `hf_band_limit_hz`.

**Expected result:**
- `hf_band_limit_hz = null` (no cutoff detected).
- If `hf_band_limit_hz` returns a finite value: the detector is misidentifying spectral slope as a
  band limit — a known-wrong pattern (DOMAIN.md §7).

---

### TC-2743 — `hf_extension` runs on both pre-master and post-master `measure_all` calls
**Covers:** AC9; architecture §2 ("same code path on both calls")
**Type:** Functional
**Preconditions:** F-01 (any signal with sub correction).

**Steps:**
1. Run pipeline on F-01. Parse both pre-master and post-master report sections.

**Expected result:**
- Both sections contain `hf_band_limit_hz`.
- Values should not dramatically diverge (sub correction does not affect HF content above 60 Hz).

---

### TC-2744 — HF extension is analysis-only: audio buffer unchanged
**Covers:** AC9, architecture §9
**Type:** Functional
**Preconditions:** F-11. Compare audio output with and without `hf_extension` wired (or verify no audio-modifying report entry).

**Steps:**
1. Run pipeline with `hf_extension` wired in.
2. Confirm no `hf_extension`-attributed entry in `eq_actions` or `adaptive_harshness_actions`.

**Expected result:**
- Audio output buffer is unmodified by the `hf_extension` wiring.
- No audio-modifying action attributed to `hf_extension` in the report.

---

## Section 6 — Item 4: Dynamics Leveling (AC14–AC18)

### TC-2750 — Leveler reduces loudness std for alternating-loudness signal (positive case)
**Covers:** AC14, architecture §7.7
**Type:** Audio-quality
**Preconditions:** F-07 (4 windows at −20/−16/−12/−8 dBFS, 12 s). Inject `max_attenuation_db = 8.0`
(OQ-C) and `no_op_threshold_db = 2.0` (OQ-B; below expected std_before ≈ 4.47 LU).

**Steps:**
1. Run dynamics leveler on F-07. Read `LevelingAction`.

**Expected result:**
- `applied = True`.
- `reason = "leveling_applied"`.
- `std_lufs_before` ≈ 4.47 LU ± 0.5 LU (variance=20 for even-spaced 4-level signal; tolerance covers K-weighting).
- `std_lufs_after < std_lufs_before` (direction assertion — unconditional; analytically from downward-only leveling toward mean).
- `std_lufs_after` ≈ 2.45 LU ± 0.5 LU (post levels −20/−16/−14/−14; variance=6; contingent on cap ≥ 8 dB).
- `max_gain_db_applied ≤ 0.0` (downward-only).
- `max_gain_db_applied ≥ −8.0 dB` (cap applied).
- `post_leveler_dr_db` is a finite float (not None).

---

### TC-2751 — Leveler no-op path: `post_leveler_dr_db` populated (Blocker 1 resolution test)
**Covers:** AC14; gate1-review Blocker 1 resolution (mandatory named test)
**Type:** Functional (mandatory)
**Preconditions:** F-08 (30 s constant-amplitude pink noise at −12 dBFS; deterministic seed).
Inject `no_op_threshold_db = 2.0` (above fixture's stochastic std_L ≈ 0.3–0.5 LU).

**Steps:**
1. Run dynamics leveler on F-08 with `no_op_threshold_db = 2.0`.
2. Read `LevelingAction`.

**Expected result:**
- `applied = False`.
- `reason = "loudness_range_below_threshold"`.
- `post_leveler_dr_db` is **not** `None`.
- `post_leveler_dr_db` is **not** `0.0` (0.0 is the sentinel bug this test guards against).
- `post_leveler_dr_db > 3.0` dB (pink noise natural crest factor ≈ 10 dB).
- `post_leveler_dr_db < 20.0` dB (sanity upper bound).
- Audio buffer returned is the original input (gate1-review incidental note: must not return `audio_out` on the no-op path; assert input and output are identical).

---

### TC-2752 — Gated (silent) windows receive gain = 1.0 (pass-through)
**Covers:** AC14, architecture §7.2 Step 1 (gated window handling)
**Type:** Functional
**Preconditions:** F-12 (5 windows: −16 / −90 / −10 / −90 / −6 dBFS; 2 gated windows at −90 dBFS).
Inject `no_op_threshold_db = 1.0` (below fixture's non-gated window std ≈ 5 LU).

**Steps:**
1. Run dynamics leveler on F-12. Read `LevelingAction.gated_windows`, `window_count`.
2. Inspect output audio samples in the gated windows (windows 2 and 4, t=3–6 s and t=9–12 s).

**Expected result:**
- `window_count = 5`.
- `gated_windows = 2`.
- Output audio samples in windows 2 and 4 are identical to input samples (gain = 1.0; no attenuation applied).
- The gated windows do not shift the `target_mean_L` (excluded from mean computation).
- `applied = True` (non-gated windows at −16/−10/−6 have different LUFS and std > threshold).

---

### TC-2753 — DR handoff: `post_leveler_dr_db` is less than pre-leveler DR
**Covers:** AC14; architecture §7.4 (DR handoff proof)
**Type:** Functional
**Preconditions:** F-07 (alternating-loudness; leveling active). Inject `max_attenuation_db = 8.0`.

**Steps:**
1. Compute TT DR of F-07 input: `pre_leveler_dr_db` (peak block RMS minus mean block RMS).
2. Run dynamics leveler. Read `LevelingAction.post_leveler_dr_db`.
3. Verify `pipeline.py` passes `LevelingAction.post_leveler_dr_db` to `solve_loudness_and_limit`
   (inspect call site or solver's received parameter).

**Expected result:**
- `post_leveler_dr_db < pre_leveler_dr_db` (downward-only leveling attenuates loud peaks,
  reducing crest factor; analytically required by architecture §7.4 proof: `post_leveler_dr ≤ source_dr`).
- `pipeline.py` passes `post_leveler_dr_db`, not Stage [2] `source_dr_db`, to the solver.
- Both `post_leveler_dr_db` and `pre_leveler_dr_db` are > 0 dB (F-07 has amplitude variation).

---

### TC-2754 — Solver regression guard: Sunday Club with leveler enabled (mandatory named test)
**Covers:** AC14; architecture §7.7 solver regression guard
**Type:** Functional / Regression (Slow — uses F-13 real reference file)
**Preconditions:** F-13 (Sunday Club source file). Leveler enabled. `targets.json` production values
[OPEN — OQ-B, OQ-C until derived; proceed with interim injected values if needed].

**Steps:**
1. Run full pipeline on Sunday Club WITH leveler enabled. Record solver outcome.
2. Run full pipeline on Sunday Club WITHOUT leveler. Record solver outcome.
3. Compare: DR achieved, LUFS achieved, any errors raised.

**Expected result:**
- Neither run raises `UnresolvableMasteringConstraintError` (OQ-E — confirm exact type).
- Neither run sets `below_documented_lufs_floor = True` (or equivalent flag).
- Leveler-enabled run: `LevelingAction.post_leveler_dr_db` is present and finite.
- Leveler-enabled run: `achieved_dr ≥ dr_required` (solver guarantee holds with post_leveler_dr_db as input).
- Leveler-disabled run: `achieved_dr ≥ dr_required` (baseline unchanged).
- Architecture §7.4 proof: `dr_required_new ≤ dr_required_old` because `post_leveler_dr ≤ source_dr`
  (downward-only). This test is the empirical confirmation.

---

### TC-2755 — Downward-only enforcement: gain envelope never positive
**Covers:** AC14; architecture §7.2 Step 3
**Type:** Audio-quality
**Preconditions:** F-07 (quiet windows at −20 dBFS and −16 dBFS are below the mean ≈ −14 LUFS
and would receive a boost if upward gain were permitted).

**Steps:**
1. Run dynamics leveler on F-07.
2. Extract gain envelope `g[t]` (in linear scale; extract from intermediate computation or by dividing output by input sample-by-sample where input is non-zero).
3. Compute `max(g[t])`.

**Expected result:**
- `max(g[t]) ≤ 1.0` (no sample receives amplification).
- Windows at −20 and −16 dBFS receive gain = 1.0 (no boost applied).
- Windows at −12 and −8 dBFS receive gain < 1.0 (attenuation).

---

### TC-2756 — Attenuation cap from `targets.json` is enforced
**Covers:** AC14; architecture §7.2 Step 3 cap
**Type:** Functional / Boundary
**Preconditions:** Signal: 2 windows — one at −6 dBFS (3 s), one at −20 dBFS (3 s). 6 s total.
Mean ≈ −13 dBFS (approximate). Window at −6 dBFS needs ~7 dB attenuation to reach mean.
Inject `max_attenuation_db = 5.0` (less than needed 7 dB) and `no_op_threshold_db = 0.5`.

**Steps:**
1. Run leveler with `max_attenuation_db = 5.0`.
2. Read `max_gain_db_applied` from `LevelingAction`.

**Expected result:**
- `max_gain_db_applied ≈ −5.0 dB ± 0.2 dB` (cap applied; full 7 dB not permitted).
- `std_lufs_after < std_lufs_before` (still reduced even with cap binding).

---

### TC-2757 — Drop-entrance gain trajectory: 1.5 s IIR time constant (gate1 Concern 4 / AC21 objective)
**Covers:** AC21 (objective component); gate1-review Concern 4
**Type:** Audio-quality (objective)
**Preconditions:** F-09 (5 s at −26 dBFS then 30 s at −10 dBFS; quiet→loud transition).

**Steps:**
1. Run dynamics leveler on F-09.
2. Extract the **gain_db** envelope at 100 ms resolution (`gain_db[t]` before the linear conversion).
   If the implementation does not expose `gain_db`, derive from `20 * log10(g[t])` where g[t] = output/input.
3. Identify `t0` = first sample of the drop (at 5.0 s elapsed).
4. Let `G_final = gain_db[t → ∞]` (steady-state gain in dB on the drop; estimate from t=25–30 s).
5. Compute settled fraction at elapsed times from t0: `f_dB(t) = gain_db[t0 + t] / G_final`.

**Expected result (analytically from τ=1.5 s first-order IIR response):**
- `G_final < 0 dB` (drop receives attenuation, confirming downward-only enforcement).
- At t0+0 s: `f_dB(0) ≈ 0%` (no gain applied at the instant of the step).
- At t0+1.5 s: `f_dB(1.5) = 63.2% ± 3%` [derived from `1 − e^{−1.5/1.5} = 1 − e^{−1} = 0.632`].
- At t0+3.0 s: `f_dB(3.0) = 86.5% ± 3%` [derived from `1 − e^{−2} = 0.865`].
- At t0+5.0 s: `f_dB(5.0) = 96.4% ± 3%` [derived from `1 − e^{−3.33} = 0.964`].

**Domain note:** Assertions are in the **dB domain**. If the implementation smooths the gain
envelope in linear scale (g[t] directly), the settled percentage in the dB domain differs
at intermediate times even though the time constant is the same. In that case, recompute
using `f_linear(t) = (1.0 − g[t0+t]) / (1.0 − g_final_linear)` and verify `f_linear` equals
63.2%/86.5%/96.4% instead. Confirm which domain the IIR operates in before asserting exact percentages.

**Listening corollary (AC21, subjective):** A human listener must evaluate the drop entrance
on Sunday Club. gate1-review Concern 4 notes 2–3 bars at 130 BPM are potentially perceptible;
this objective test checks only that the time constant is correctly implemented, not that it is
inaudible.

---

### TC-2758 — Artifact density non-regression after leveling (AC18)
**Covers:** AC18
**Type:** Functional / Regression (Slow — uses F-13)
**Preconditions:** F-13 (Sunday Club). Leveler enabled.

**Steps:**
1. Run pipeline WITHOUT leveler. Record `overall_artifact_density_score` and flag counts from `detect_artifacts`.
2. Run pipeline WITH leveler. Record same metrics.

**Expected result:**
- `overall_artifact_density_score` in leveler-enabled run is not higher than disabled run (tolerance ±0.02 for stochastic variation).
- Flag counts (STATIONARY_WHISTLE, BROADBAND_NOISE, etc.) do not increase.

---

### TC-2759 — `LevelingAction` fully logged in report (AC19)
**Covers:** AC19; architecture §7.5
**Type:** Functional
**Preconditions:** F-07 with leveling active.

**Steps:**
1. Run pipeline on F-07 with leveler enabled. Parse report JSON leveling section.

**Expected result:**
- Report contains a leveling entry with: `applied: true`, `reason`, `std_lufs_before`, `std_lufs_after`,
  `max_gain_db_applied`, `window_count`, `gated_windows`, `post_leveler_dr_db`.
- All values are finite (no null in a fired-leveling entry).
- `std_lufs_after < std_lufs_before` in the logged values.

---

### TC-2760 — Chunked BS.1770 gating distortion at window boundaries [OPEN]
**Covers:** Architecture §7.2 Step 1 vs. gate1-review Concern 2
**Type:** Audio-quality [OPEN — gate1-review Concern 2 unresolved in architecture v1.2]
**Preconditions:** Straddling signal: first 3-second window = 1.5 s at −30 dBFS (below BS.1770 relative
gate for a 3-second chunk) followed by 1.5 s at −10 dBFS.

**Steps:**
1. Run dynamics leveler.
2. Observe whether the quiet pre-transition zone (0–1.5 s of window 1) receives the same gain as
   the loud post-transition zone (1.5–3.0 s) within the same window.

**Expected result [OPEN]:**
- If `pyloudnorm.integrated_loudness(window)` gates the quiet half and returns a value reflecting
  primarily the loud half, the computed per-window gain is too large and over-attenuates the quiet zone.
- gate1-review Concern 2 identifies this as incorrect and proposes BS.1770 short-term loudness
  (3 s sliding window, 100 ms hop) instead.
- Mark `[OPEN — Concern 2 unresolved in architecture v1.2]` until developer responds to Concern 2.

---

### TC-2761 — Leveler idempotency: second pass hits no-op gate
**Covers:** Mandatory coverage (idempotency)
**Type:** Functional
**Preconditions:** F-07. Run leveler once (first pass). The first-pass output has `std_lufs_after ≈ 2.45 LU`.
Requires `no_op_threshold_db` to satisfy: `2.45 LU < no_op_threshold_db < 4.47 LU` (between
first-pass output std and first-pass input std). This is [OPEN — OQ-B] until the production
value is derived. Inject interim `no_op_threshold_db = 3.5` for the test.

**Steps:**
1. Run leveler on F-07 (first pass). Record output audio `A1` and `std_lufs_after1` ≈ 2.45 LU.
2. Run leveler on `A1` (second pass) with same config and `no_op_threshold_db = 3.5`.
3. Read `LevelingAction` from second pass. Compare output audio `A2` with `A1`.

**Expected result:**
- Second pass: `applied = False` (std_L of A1 ≈ 2.45 LU < `no_op_threshold_db` = 3.5).
- Second pass: `reason = "loudness_range_below_threshold"`.
- `A2` is bit-identical to `A1` (no modification on no-op path).
- Second pass: `post_leveler_dr_db` is populated and ≈ first-pass `post_leveler_dr_db`.
- Note: if production `no_op_threshold_db` < 2.45 LU, both passes fire and idempotency is not
  achievable in a single step — revise the test using the production value once OQ-B is resolved.

---

## Section 7 — Cross-Cutting and Non-Functional (AC19, AC20, AC21, NFR)

### TC-2770 — Reproducibility: bit-identical output for identical input and config
**Covers:** NFR (reproducibility)
**Type:** Non-functional
**Preconditions:** F-03 (deterministic noise fixture).

**Steps:**
1. Run full pipeline on F-03 twice with identical config.
2. Compare output audio byte-for-byte. Compare report JSON field-by-field.

**Expected result:**
- Audio output bit-identical across runs.
- Report JSON identical (same floats, same fields).
- Leveler envelope computation is deterministic (no wall-clock or random elements per architecture §7.6).

---

### TC-2771 — All new correction paths logged with before/after evidence (AC19)
**Covers:** AC19
**Type:** Functional
**Preconditions:** F-01 (sub correction) and F-03 (low_mid de_mud).

**Steps:**
1. Parse report JSON from each run. Inspect `eq_actions`, leveling entry, `adaptive_harshness_actions`, HF fields.

**Expected result:**
- Each fired correction includes: `band`, `trigger`, `source_db` (or `before_db`), `aim_point_db`, `applied_db`, `cap_reached`, `residual_gap_db`.
- Leveling entry includes `std_lufs_before`, `std_lufs_after`.
- HF fields: `hf_band_limit_hz`, `hf_band_limit_confidence`.
- No field is `null` where a fired correction should have a value.

---

### TC-2772 — No new stage is a silent no-op reported as run (NFR)
**Covers:** NFR (failure posture); requirements.md non-functional requirements
**Type:** Functional
**Preconditions:** F-06 (in-range signal; no corrections expected).

**Steps:**
1. Run full pipeline on F-06. Inspect report.

**Expected result:**
- If leveling gate fires, `reason` is explicitly populated.
- If harshness correction is not flagged, `adaptive_harshness_actions: []` is present (not absent).
- No stage claims to have "run" without either an action or an explicit no-op reason.

---

### TC-2773 — Human listening gate required before any item accepted (AC21)
**Covers:** AC21 (process requirement)
**Type:** Non-functional / Process
**Preconditions:** Sunday Club mastered output from STORY-027 pipeline.

**Steps:**
1. Confirm Gate 2 review record includes documented human listening check on Sunday Club.
2. Confirm listening covers: sub correction audibility (~60 Hz shelf); de_mud low_mid result;
   drop-entrance gain trajectory; artifact perception.

**Expected result:**
- Gate 2 review record exists with explicit per-item human listening result.
- No item (1, 2, or 4) is accepted without this record.
- AC21 is a release-readiness requirement, not optional colour.

---

## Section 8 — Edge Cases

### TC-2780 — Near-silence input through leveler: no crash or divide-by-zero
**Covers:** Edge case (silence handling)
**Type:** Edge case
**Preconditions:** 10-second stereo signal of white noise at −80 dBFS. All LUFS windows below
BS.1770 absolute gate → all gated. Inject `no_op_threshold_db = 2.0`.

**Steps:**
1. Run dynamics leveler. Verify no exception.

**Expected result:**
- No exception (`ZeroDivisionError`, `ValueError`, etc.).
- `gated_windows = window_count` (all gated).
- `applied = False`.
- `post_leveler_dr_db` is populated.
- Output audio is identical to input.

---

### TC-2781 — Stereo shape (N×2) maintained throughout leveling
**Covers:** Edge case (channel handling)
**Type:** Functional
**Preconditions:** F-07 (stereo, shape (N, 2)).

**Steps:**
1. Run dynamics leveler on F-07. Check output audio shape.

**Expected result:**
- Output shape = (N, 2) matching input.
- Both channels receive same gain envelope (broadcast per architecture §7.2 Step 4).
- No mono collapse.

---

### TC-2782 — 48 kHz input handled correctly by leveler
**Covers:** Edge case (sample rate)
**Type:** Functional
**Preconditions:** F-07 reconstructed at 48 000 Hz (same amplitude levels, proportional duration).

**Steps:**
1. Run dynamics leveler with `sr = 48000`.
2. Read `LevelingAction`.

**Expected result:**
- `applied = True`.
- `std_lufs_before` comparable to the 44.1 kHz run (BS.1770 is sample-rate agnostic).
- Output shape = (N_48k, 2).
- No exception from `pyloudnorm.Meter(48000)` call.

---

### TC-2783 — All-gated windows: no divide-by-zero
**Covers:** Edge case (silence)
**Type:** Edge case
**Preconditions:** 12-second stereo signal at 0.0 amplitude (absolute silence). Inject `no_op_threshold_db = 2.0`.

**Steps:**
1. Run dynamics leveler. Observe behaviour.

**Expected result:**
- No `ZeroDivisionError`, `ValueError`, or `np.nan` in output.
- `applied = False`.
- `post_leveler_dr_db` is not NaN. A value of 0.0 is acceptable here (undefined DR for silence;
  distinct from the TC-2751 sentinel-bug because this signal genuinely has no dynamics).

---

### TC-2784 — File shorter than one 3-second leveler window
**Covers:** Edge case (short file)
**Type:** Edge case
**Preconditions:** 2-second stereo 440 Hz tone at −12 dBFS. Inject `no_op_threshold_db = 2.0`.

**Steps:**
1. Run dynamics leveler on 2-second signal.

**Expected result:**
- No exception.
- Either `window_count = 0` (partial window discarded) or `window_count = 1` (partial window included).
- If 0: `applied = False`, audio unchanged.
- If 1: single window; `std_L = 0` (single point has no std); no-op gate fires; `applied = False`.

---

### TC-2785 — Full-scale input: leveler downward-only guarantee
**Covers:** Edge case (clipping input); NFR (no new true-peak violations)
**Type:** Audio-quality
**Preconditions:** Stereo signal with some windows at 0 dBFS amplitude.

**Steps:**
1. Run dynamics leveler.
2. Verify output peak ≤ 0 dBFS (sample domain).

**Expected result:**
- `max_gain_db_applied ≤ 0.0` (downward-only by construction).
- Output peak ≤ 0 dBFS (leveler cannot create new peaks).

---

### TC-2786 — Corrective EQ: 48 kHz input produces correct seven-band measurements
**Covers:** Edge case (sample rate)
**Type:** Functional
**Preconditions:** F-03 reconstructed at 48 kHz (same amplitude ratios).

**Steps:**
1. Run corrective EQ at 48 kHz. Read `seven_band_balance.before.low_mid.relative_db`.

**Expected result:**
- `seven_band_balance.before.low_mid.relative_db` ≈ +6.54 dB ± 0.3 dB.
- Correction applied as in the 44.1 kHz case; `applied_db` and `cap_reached` match.

---

## Traceability Table

| Acceptance Criterion | Test Cases | Notes |
|---|---|---|
| AC0 — Seven-band report prerequisite | TC-2701, TC-2702, TC-2703, TC-2704, TC-2705 | |
| AC1 — Sub correction reaches range edge | TC-2710, TC-2711, TC-2712, TC-2713, TC-2714, TC-2715 | TC-2711 is the key correctness test; flags OQ-A |
| AC2 — de_mud aim/cap (arch states design) | TC-2720, TC-2721, TC-2722, TC-2723, TC-2725 | Design confirmed by architecture §3.3; tests validate implementation |
| AC3 — post-master measurement closer to aim | TC-2721, TC-2703 | residual_gap_db per §5.3 |
| AC4 — No correction when not triggered | TC-2724, TC-2712, TC-2726 | Negative controls |
| AC5a — Harshness reachable from entrypoints | TC-2730, TC-2731 | Delivered |
| AC5b — Harshness fires by default on excess | Not tested (deferred) | Architecture §4.3: explicitly deferred pending targets.json derivation. Documented scope limit, not a testing gap. |
| AC6 — Authoritative path decision | TC-2735 | Design AC — architecture §4.2 states decision. TC-2735 tests documented stereo-fallback behaviour. |
| AC7 — No harshness correction on compliant material | TC-2734 | Negative control |
| AC8 — Third branch scope decision | Design AC | Architecture §4.4: explicitly deferred. Not a testable runtime behaviour for this story. |
| AC9 — Band-limit wiring prerequisite | TC-2740, TC-2741, TC-2742, TC-2743, TC-2744 | |
| AC10 — CLAUDE.md §6.2 exception process | Not tested | HF lift rejected at Gate 1 Decision 1 |
| AC11 — HF lift scoped to below cutoff | Not tested | HF lift rejected at Gate 1 Decision 1 |
| AC12 — HF lift avoids STATIONARY_WHISTLE | Not tested | HF lift rejected at Gate 1 Decision 1 |
| AC13 — HF rejection does not block items 1/2/4 | Not tested (process criterion) | Gate 1 Decision 1 recorded; items 1/2/4 have independent test coverage |
| AC14 — Leveler chain placement and constraints | TC-2750, TC-2753, TC-2754, TC-2755, TC-2761 | AC14 partially design AC (chain position); TC-2753/2754 verify DR handoff |
| AC15 — Metric for leveler acceptance | Design AC | Architecture §7.1: window-LUFS std primary, TT DR hard constraint. TC-2750 asserts std direction; TC-2753 asserts TT DR. |
| AC16 — Leveler no-op on uniform-loudness material | TC-2751 | |
| AC17 — Stem vs sum decision | Design AC | Architecture §7.1: stereo sum. Consistent with AC6 decision. Not a separately testable runtime behaviour. |
| AC18 — Artifact density non-regression | TC-2758 | |
| AC19 — All corrections logged | TC-2703, TC-2759, TC-2771 | |
| AC20 — Gate 1 review mandatory | Verified by gate1-review.md existence | Not a test-automation criterion |
| AC21 — Human listening gate | TC-2757 (objective component), TC-2773 (process) | |
| NFR — Reproducibility | TC-2770 | |
| NFR — Reachable from both entrypoints | TC-2730, TC-2731 | |
| NFR — No silent no-op | TC-2772 | |
| Named mandatory — gate1 Concern 1 | TC-2720 | |
| Named mandatory — Blocker 2 delivery efficiency | TC-2711 | |
| Named mandatory — Blocker 1 no-op DR | TC-2751 | |
| Named mandatory — Solver regression guard | TC-2754 | |
| Named mandatory — Drop-entrance smoothing | TC-2757 | |
| Named mandatory — Harshness reachability | TC-2730, TC-2731 | |
| Edge cases | TC-2780–TC-2786 | |
| Idempotency | TC-2761 | |

---

## Mandatory Coverage Checklist

| Category | Status |
|---|---|
| Happy path for each AC | Covered (see traceability) |
| Boundary: at threshold, just under, just over | TC-2720 (de_mud 4.0 threshold), TC-2722 (range_max, OQ-D), TC-2723 (above range), TC-2713 (cap not binding), TC-2715 (cap binding), TC-2756 (attenuation cap) |
| Idempotency | TC-2761 (leveler; conditional on OQ-B) |
| Bypass/disabled | TC-2732 (harshness default-off), TC-2744 (HF no-op), TC-2751 (leveler no-op path) |
| Mono input | Not applicable — pipeline operates on stereo (N,2). Mono inputs not a documented input format for this story. |
| Stereo input | TC-2781 |
| 44.1 kHz | All synthetic fixtures default to 44 100 Hz |
| 48 kHz | TC-2782, TC-2786 |
| Silence / near-silence | TC-2780, TC-2783 |
| Full-scale / clipping | TC-2785 |
| Very quiet input | TC-2780 |
| DC offset | Not covered — no AC touches DC handling and no new stage is expected to introduce DC. |
| Very short file | TC-2784 |
| Corrupt / truncated file | Not covered — no STORY-027 AC governs file ingestion; `ingest.py` unchanged. |
| Unsupported format | Not covered — same rationale. |
| Wrong channel count | Not covered — pipeline contract specifies stereo (N,2); input validation unchanged. |

---

## Revision History

- 2026-08-21 v1.0: Initial draft. Key named tests included per gate1-review.md and architecture §7.7.
- 2026-08-21 v1.1: Three systematic fixture defects corrected based on advisor review:
  - **Fixture domain bug (Sections 2 and 3):** Single-tone fixtures (30 Hz sine for sub, 250 Hz sine
    for low_mid) sampled the filter transfer function at a single point — sub deep in shelf plateau
    (~1.0× delivery) and low_mid at the bell centre (~1.0× delivery) — making every expected landing
    value wrong and inverting TC-2711's discrimination logic. Replaced F-01 through F-05 with band-limited
    noise filling each measurement band uniformly; delivery efficiency factors (0.60×, 0.75×) now
    apply as stated in architecture §3.2/§3.3. Added all-band filler to prevent empty-band range-compliance
    corrections from contaminating tests.
  - **TC-2752 self-defeating fixture:** Non-gated windows at −10/−10/−10 dBFS produced std_L=0,
    gate fired, applied=False — contradicting the test's assertion of applied=True. Replaced with
    F-12 (−16/−90/−10/−90/−6 dBFS), giving 3 distinct non-gated levels and 2 genuinely gated windows.
  - **TC-2757 domain ambiguity:** Settled-fraction formula was in the linear-gain domain without
    stating so; the percentage differs from the dB-domain calculation at intermediate times because
    the IIR operates in one domain but not both. Added explicit domain note: assert in the dB domain
    with note for the linear-smoothing implementation variant. Also fixed the F-09 fixture from
    loud→silence to quiet→loud (the relevant drop-entrance transition for Concern 4).
  - Added TC-2761 (idempotency) to close the mandatory coverage checklist gap.
