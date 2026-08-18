# STORY-009: Wire `suno_dsp` into the Mastering Chain — Test Cases

**Story**: STORY-009
**Version**: 1.1
**Date**: 2026-08-16
**Tracing**: Acceptance criteria AC1–AC16 (requirements.md), architecture.md §1–§14

**Revision history**:
- 1.1 (2026-08-16): Self-review corrections (no defects.md exists for this story yet —
  these are pre-handoff fixes, not defect-driven). (1) TC-010 rewritten: the original
  version set the co-gate floor to exactly the detector's emission floor (6.0 dB) and
  asserted the flag was forwarded, but framed the derivation ambiguously and invited a
  wrong-operator-guess in the pass/fail note. Rewritten as a direct equivalence test:
  the forwarded set at `prominence_floor_db=6.0` must equal the forwarded set at
  `prominence_floor_db=5.0` (both at-or-below the detector's own floor), which is the
  actual "no effect" claim architecture §6 derives. (2) TC-032's hand-derived rolloff
  figures were internally inconsistent (a −9.6 dB figure at 16 kHz stated as "one octave
  above 5000 Hz," which is 10 kHz, not 16 kHz) and asserted specific per-frequency dB
  values that a correct band-integrated measurement cannot be expected to match exactly.
  Rewritten to compute the expected attenuation from the same `scipy.signal.freqz`
  evaluation TC-035 already performs, and to assert a floor (≥ 8 dB reduction in an
  8–16 kHz band-integrated measurement) rather than an exact figure. (3) Added TC-052
  (full-scale/near-clipping input through each stage individually) to close the
  "full-scale input" coverage gap the original version left open in the checklist; the
  "very quiet input" and "DC offset" rows are retained as deliberately-not-gaps with
  their existing one-line justifications, since scaling F-002 to test loudness handling
  or reusing F-001's inherent DC-by-construction already provides adequate coverage at
  low risk. (4) TC-051 assertion 3 given concrete numeric thresholds (was previously an
  unfalsifiable "small margin attributable to the filter" statement).
- 1.0 (2026-08-16): Initial version. No prior `defects.md` existed for this story
  (folder created fresh in this run) — no defect-driven coverage gaps to close.

---

## Status legend — read before running any test in this document

Architecture §14 records that several required design elements are **specifications
for a future C++ patch, not yet implemented**:

- `repair_whistles`'s OLA normalisation bug (architecture §3, Blocker 1) — **fixed**
  (`overlap_weights[...] += hann[i] * hann[i]` at all four accumulation sites in
  `src_cpp/spectral_repair.cpp`, plus `kMinReliableOverlapWeight = 4.0e-6f` edge-frame
  passthrough guard). TC-001, TC-002, TC-003, and TC-022 are now **expected to pass**.
- `shape_transients`'s highpassed detector sidechain (150 Hz working value) and
  stereo-linked control signal (`max(|L|,|R|)`) (architecture §7, Blockers 3/4/11) —
  **not yet implemented**. The 2f-flutter and stereo-link tests are expected to fail
  against the gain-law-only (or unmodified) C++.

Every test case below is tagged with one of:

| Tag | Meaning |
|---|---|
| *(none)* | Expected to pass against the wrapper as architected, independent of the two C++ patches above. |
| `[BLOCKED-ON: OLA fix, arch §3]` | OLA fix has landed (2026-08-18). Tests carrying this tag are now **expected to pass**. Tag is retained as a historical trace of what the test exercises. |
| `[BLOCKED-ON: sidechain+link patch, arch §7]` | Requires the highpass-before-rectify + stereo-link C++ patch. Expected **FAIL** until then. |
| `[OPEN: <ref>]` | Expected value depends on a number not yet set by Gate 1 (see Open Questions table). Assertion is qualitative or deferred. |
| `[Baseline]` | No automated pass/fail; records a measurement used to make a future numeric decision (e.g. final sidechain cutoff, final slow-envelope constant). |
| `[Slow]` | Uses longer/real audio; run separately from the fast suite. |

A blocked test failing is **expected and correct** — it is not a defect until the
corresponding C++ patch lands and the test is still red. A blocked test unexpectedly
**passing** is itself worth flagging (it may mean the patch landed without updating
this document, or the test is not exercising the bug).

---

## Open Questions Affecting Expected Values

Do not invent values for open questions. Each affected test case calls out the
dependency and uses an explicit **test-fixture value**, clearly labelled as not a
project default, until Gate 1 sets one.

| OQ | Question | Test-fixture value used here | Affected TCs |
|---|---|---|---|
| OQ-A | `prominence_floor_db` final value (architecture §6, Blocker 2 — must be > 6.0 dB, no specific number set) | 10.0 dB, stated explicitly as a test parameter only | TC-011, TC-012, TC-013 |
| OQ-B | `collapse_swish.cutoff_freq_hz` final default (architecture §8, Blocker 6 — no default asserted) | 5000.0 Hz, stated explicitly as a test parameter only | TC-030–TC-034 |
| OQ-C | `shape_transients` sidechain highpass final cutoff within 150–250 Hz (architecture §7) | 150 Hz (working value) plus a swept near-corner set (160/200/250 Hz) as a `[Baseline]` measurement, not a pass/fail | TC-022, TC-023 |
| OQ-D | `shape_transients` slow-envelope constant final value within 100–500 ms (architecture §7, Blocker 4) | Not directly testable at the wrapper level (internal C++ constant); flagged, not asserted | — (see TC-023 note) |
| OQ-E | `attack_boost_db`/`sustain_cut_db` final defaults (Blocker 3/4) | +3 dB / −3 dB, the values architecture §7 itself specifies for the required flutter test | TC-020–TC-024 |
| OQ-F | Type-enforcement posture for `apply_whistle_repair`'s `artifact_detection` parameter — passing a raw `list[float]` raises `AttributeError` in practice (no runtime annotation enforcement in Python), not necessarily `TypeError` as requirements.md AC8(c) literally states | TC-014 asserts `(TypeError, AttributeError)` and flags the discrepancy | TC-014 |
| OQ-G | AC6's "final master must still meet standing targets" — no explicit tolerance is restated for this story; reuses architecture.md §5's existing convention (`±0.1 LU`) for MASTERING: loudness ground truth, DR range 6.6–8.7 (CLAUDE.md §4.2), −1.0 dBTP ceiling (hard) | ±0.1 LU, DR 6.6–8.7, ≤ −1.0 dBTP | TC-045 |

---

## Fixture Specifications

Fixtures are short synthetic signals with analytically derivable properties, per
architecture §13's testability notes. `np.random.default_rng(seed=42)` throughout for
reproducibility. Full-length reference tracks are used only for the tests explicitly
marked `[Slow]`.

### F-001: Constant-amplitude signal for direct OLA gain-curve measurement

```python
import numpy as np

sr = 44100
duration = 3.0                       # >> one frame (4096) and many hops (2048)
n = int(sr * duration)
signal = np.full(n, 0.5, dtype=np.float64)   # constant, non-zero -> safe divisor
samples = np.column_stack([signal, signal])  # stereo; also test mono variant

# Rationale: g[n] = out[n] / in[n] is exactly the OLA reconstruction gain curve
# when the input carries no spectral content of its own (constant amplitude ->
# repair_whistles with target_frequencies=[] does not touch any bin, so any
# departure from g[n] == 1 is purely a reconstruction-gain artifact, not a
# notch side-effect). This is the correct fixture for isolating the OLA bug --
# a tone would show the modulation as sidebands (see F-002), not a clean gain
# curve.
```

48 kHz variant: `sr = 48000`, everything else identical. `frame_size` (4096) and
`hop_size` (2048) are fixed **sample counts** in the C++ (architecture §3),
independent of sample rate, so:
- `f_mod(44100) = 44100 / 2048 ≈ 21.5332 Hz`
- `f_mod(48000) = 48000 / 2048 ≈ 23.4375 Hz`

Testing both rates validates the *formula* `sample_rate / hop_size`, not a
hardcoded constant — a wrapper or test that hardcodes `21.53 Hz` would silently
pass at 44.1 kHz and be meaningless at 48 kHz.

---

### F-002: 1 kHz tone at −20 dBFS, sideband check for the OLA bug

```python
sr = 44100
duration = 2.0
n = int(sr * duration)
t = np.arange(n) / sr
amplitude = 10 ** (-20 / 20)          # -20 dBFS -> 0.1
signal = (amplitude * np.sin(2 * np.pi * 1000 * t)).astype(np.float64)
samples = np.column_stack([signal, signal])

# Derivation: amplitude-modulating a 1000 Hz carrier by a periodic gain at
# f_mod = 21.5332 Hz produces sidebands at 1000 +/- 21.5332 Hz (and higher-order
# sidebands at +/- 2*f_mod, etc., from the cos(2*theta) term in g(theta)).
# A correctly-implemented (fixed) OLA reconstruction shows no sidebands above
# the float32 round-trip noise floor (arch Sec.2, ~-120 dBFS).
```

---

### F-003: Sustained 55 Hz bass tone (shape_transients sidechain, below corner)

```python
sr = 44100
duration = 2.0
n = int(sr * duration)
t = np.arange(n) / sr
signal = (0.5 * np.sin(2 * np.pi * 55 * t)).astype(np.float64)   # -6 dBFS
samples = np.column_stack([signal, signal])       # identical L/R -- isolates
                                                    # the rectification/gain-law
                                                    # question from stereo linking
# 110 Hz variant: replace 55 with 110 (kick/808 fundamental region).
# 440 Hz variant: replace 55 with 440 (well above the 150 Hz sidechain corner;
#   880 Hz ripple is ~21 dB down at the fast follower's 79.6 Hz one-pole corner).
```

---

### F-004: Near-corner fundamentals, 160/200/250 Hz (baseline sweep)

```python
sr = 44100
duration = 2.0
n = int(sr * duration)
t = np.arange(n) / sr
for f0 in (160, 200, 250):
    signal = (0.5 * np.sin(2 * np.pi * f0 * t)).astype(np.float64)
    samples = np.column_stack([signal, signal])
    # ripple at 2*f0 = 320/400/500 Hz, only ~12-16 dB down through a single
    # one-pole 150 Hz highpass -- worst-case residual per architecture Sec.7.
```

---

### F-005: Stereo-linking fixture — shared sustained bed + one-channel transient

```python
sr = 44100
duration = 1.0
n = int(sr * duration)
t = np.arange(n) / sr
rng = np.random.default_rng(42)

# Shared sustained bed on BOTH channels -- avoids the ill-conditioned "silent
# channel" case (0/0 in g_R = out_R/in_R if R were pure silence).
bed = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float64)

# Broadband percussive transient (hi-hat-like burst), L channel only, at t=0.5s.
burst_start = int(0.5 * sr)
burst_len = int(0.02 * sr)             # 20 ms burst
burst = rng.standard_normal(burst_len).astype(np.float64) * 0.8
envelope = np.exp(-np.arange(burst_len) / (0.003 * sr))   # fast decay
L = bed.copy()
L[burst_start:burst_start + burst_len] += burst * envelope
R = bed.copy()                          # no transient on R

samples = np.column_stack([L, R])
# Both |L| and |R| stay bounded away from zero throughout (bed present on both
# channels) -- g_L and g_R are well-defined at every sample.
```

---

### F-006: Decorrelated broadband noise, stereo (collapse_swish HF-collapse / LF-preserve)

```python
sr = 44100
duration = 2.0
n = int(sr * duration)
rng = np.random.default_rng(42)
L = rng.standard_normal(n).astype(np.float64) * 0.2
R = rng.standard_normal(n).astype(np.float64) * 0.2   # independent draw -> rho ~ 0

samples = np.column_stack([L, R])
# Fully decorrelated broadband noise: side energy present across the whole
# spectrum. Used with a test cutoff (5000 Hz, OQ-B) to measure per-band width
# before/after collapse_swish -- HF band width should collapse toward mono,
# LF band width should be materially unchanged (DC gain of the deployed
# lowpass is exactly 1, architecture Sec.8).
```

---

### F-007: Sub-frame and at-threshold audio (repair_whistles refusal boundary)

```python
sr = 44100
rng = np.random.default_rng(42)
just_under = rng.standard_normal(4095).astype(np.float64) * 0.3   # 4095 samples
                                                                    # ~92.85 ms
at_threshold = rng.standard_normal(4096).astype(np.float64) * 0.3 # 4096 samples
                                                                    # exactly one frame
samples_under = np.column_stack([just_under, just_under])
samples_at = np.column_stack([at_threshold, at_threshold])
```

---

### F-008: Digital silence (all three stages, divide-by-zero / NaN robustness)

```python
sr = 44100
duration = 1.0
n = int(sr * duration)
signal = np.zeros(n, dtype=np.float64)
samples = np.column_stack([signal, signal])
```

---

### F-009: NaN-contaminated input (failure-mode control)

```python
sr = 44100
duration = 1.0
n = int(sr * duration)
rng = np.random.default_rng(42)
signal = rng.standard_normal(n).astype(np.float64) * 0.2
signal[n // 2] = np.nan
samples = np.column_stack([signal, signal])
```

---

### F-010: Synthetic `ArtifactDetectionResult` fixtures for `repair_whistles` gating

```python
# Reuses STORY-007's ArtifactFlag/ArtifactDetectionResult shape.
# Four flags straddling the confidence and prominence thresholds independently.
def make_flag(confidence, prominence, freq=6400.0, start=1.0, end=3.5):
    return ArtifactFlag(
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=confidence,
        timestamp_start_s=start,
        timestamp_end_s=end,
        details={"frequency_hz": freq, "prominence_db": prominence, "q_factor": 120.0},
    )

# Test-fixture prominence_floor_db = 10.0 (OQ-A; not a project default)
flag_high_conf_high_prom  = make_flag(0.90, 12.0)   # both gates pass -> forwarded
flag_high_conf_low_prom   = make_flag(0.90, 8.0)    # confidence ok, prominence fails (< 10.0)
flag_low_conf_high_prom   = make_flag(0.60, 12.0)   # prominence ok, confidence fails (< 0.8)
flag_boundary_conf        = make_flag(0.80, 12.0)   # exactly at confidence threshold -> forwarded (>=)
flag_boundary_prom        = make_flag(0.90, 10.0)   # exactly at prominence floor -> forwarded (>=)
flag_just_under_conf      = make_flag(0.79, 12.0)   # just under confidence -> excluded
flag_just_under_prom      = make_flag(0.90, 9.9)    # just under prominence -> excluded
flag_at_detector_min      = make_flag(0.90, 6.0)    # exactly the detector's own emission
                                                     # floor -- used by TC-010 with the
                                                     # co-gate itself set to 6.0 and 5.0
                                                     # (both at-or-below the detector floor)
                                                     # to prove the co-gate has no effect there
```

### F-011: Full-scale / near-clipping input (all three stages)

```python
sr = 44100
duration = 2.0
n = int(sr * duration)
rng = np.random.default_rng(42)

# Broadband noise scaled to a sample peak of -0.3 dBFS (0.9647), well above
# normal programme level, close enough to full scale that a stage adding gain
# mid-chain (repair_whistles' OLA reconstruction swing, shape_transients'
# attack_boost_db) could plausibly push samples past +-1.0 before [6] limiting
# ever sees the signal.
noise = rng.standard_normal(n).astype(np.float64)
target_peak = 10 ** (-0.3 / 20)          # 0.9647
signal = noise / np.max(np.abs(noise)) * target_peak
samples = np.column_stack([signal, signal])
```

---

## Test Cases

### Group 1 — `repair_whistles`: OLA no-op ground truth (AC7, AC10, architecture §3)

---

**TC-001**
**Title**: OLA gain curve — empty frequency list, direct gain measurement, 44.1 kHz
**Covers**: AC10, architecture §3, §13
**Type**: Audio-quality / ground truth `[BLOCKED-ON: OLA fix, arch §3]`
**Preconditions**: Fixture F-001 (constant 0.5, stereo, 44.1 kHz, 3.0 s).

**Steps**:
1. Cast F-001 to float32 (`_to_dsp_input`), matching the wrapper's own cast.
2. Call `suno_dsp.repair_whistles(audio, 44100, target_frequencies=[])`.
3. Compute `g[n] = out[n] / in_f32[n]` sample-wise (safe: `in` is constant 0.5, never zero).
4. FFT `g[n]` (after discarding the first/last frame's edge region, which architecture
   §3 separately notes as worse than the steady-state case) and locate the peak
   magnitude bin.

**Expected result — PRE-FIX (current code, expected today)**:
- Prominent spectral peak in `g[n]` at `44100 / 2048 ≈ 21.5332 Hz` (±1 FFT bin).
- Steady-state `g[n]` swings between 0.5 and 1.0 (derivation: `a²+b² = 0.5 + 0.5·cos²θ`,
  architecture §3).
- `mean(g[n]) ≈ 0.75` (−2.5 dB) within ±0.02.
- `rms(g[n]) ≈ 0.7706` (−2.26 dB) within ±0.01 — this is the corrected Gate-1 figure,
  not the retracted −1.25 dB framing.

**Expected result — POST-FIX (once the C++ divisor fix lands)**:
- No prominent component in `g[n]`'s FFT at `21.5332 Hz` above the noise floor.
- `g[n] ≈ 1.0` everywhere (peak absolute deviation ≤ 1e-6, the derived float32
  round-trip tolerance, architecture §2).

**Pass/fail criterion (post-fix only)**: peak `|g[n] − 1|` > 1e-6, or a spectral peak in
`g[n]`'s FFT within ±1 bin of 21.5332 Hz with magnitude > 3× the noise floor → FAIL.
**Pre-fix**: this test is expected to reproduce the modulation signature above; its
purpose pre-fix is diagnostic/regression, not pass/fail.

---

**TC-002**
**Title**: OLA gain curve — empty frequency list, 48 kHz (formula validation)
**Covers**: AC10, architecture §3
**Type**: Audio-quality / ground truth `[BLOCKED-ON: OLA fix, arch §3]`
**Preconditions**: Fixture F-001, 48 kHz variant.

**Steps**: As TC-001.

**Expected result — PRE-FIX**: peak in `g[n]`'s FFT at `48000 / 2048 ≈ 23.4375 Hz`
(±1 bin), not at 21.5332 Hz. A test or implementation that hardcodes 21.5 Hz instead of
computing `sample_rate/hop_size` would fail this case even after the fix (false pass at
44.1 kHz, false fail/false pass by coincidence at 48 kHz) — this case exists specifically
to catch that class of bug.

**Expected result — POST-FIX**: no prominent component at 23.4375 Hz; peak `|g[n]-1|` ≤ 1e-6.

**Pass/fail criterion**: same structure as TC-001, evaluated at the 48 kHz-scaled frequency.

---

**TC-003**
**Title**: OLA sideband check — 1 kHz tone at −20 dBFS
**Covers**: AC10, architecture §3
**Type**: Audio-quality / ground truth `[BLOCKED-ON: OLA fix, arch §3]`
**Preconditions**: Fixture F-002.

**Steps**:
1. Process F-002 through `repair_whistles` with `target_frequencies=[]`.
2. FFT the output. Locate magnitude at exactly 1000 Hz (carrier) and at
   `1000 ± 21.5332 Hz` (first-order sidebands).

**Expected result — PRE-FIX**: sidebands at 1000 ± 21.5332 Hz present, measurably above
the noise floor (record the measured dB gap to the carrier as a `[Baseline]` figure —
not asserted as an exact value here, since the precise sideband level depends on
windowing/leakage in the measurement FFT as well as the OLA modulation itself).
**Expected result — POST-FIX**: no sidebands above the float32 round-trip noise floor
(~−120 dBFS) at 1000 ± 21.5332 Hz or ± 2×21.5332 Hz.

**Pass/fail criterion (post-fix)**: sideband magnitude within 20 dB of the carrier → FAIL.
**Pass/fail criterion (pre-fix)**: none — the sideband-gap measurement pre-fix is
baseline data, per the correction in this document's Revision history.

---

**TC-004**
**Title**: Scalar-only test is diagnostically insufficient (illustrative negative-method control)
**Covers**: architecture §3 (explains why TC-001–003 exist)
**Type**: Functional / method-validation, `[Baseline]` — documents a known limitation of a naive approach, not a pass/fail on the implementation

**Preconditions**: Fixture F-001, pre-fix code.

**Steps**:
1. Compute scalar peak-diff and RMS-diff between input and `repair_whistles([])` output.
2. Compare that scalar alone against the §2 tolerance (1e-6).

**Expected result**: the scalar test fails loudly (diff ≈ 0.5 in places, five orders of
magnitude over tolerance) but a bare "output != input" fail is **uninformative** — it
cannot distinguish a static level trim from the 21.5332 Hz periodic modulation
demonstrated in TC-001. This test exists to document that a scalar-only regression
test must not be substituted for TC-001–003 in the automated suite, per architecture
§3's explicit finding.

**Pass/fail criterion**: not applicable — informational only. QA automation must not
treat a passing scalar-diff test as equivalent coverage to TC-001.

---

### Group 2 — `repair_whistles`: confidence + prominence co-gate (AC8, architecture §6)

---

**TC-005**
**Title**: Co-gate — both thresholds met, flag is forwarded
**Covers**: AC8, architecture §6 Blocker 2
**Type**: Functional / ground truth
**Preconditions**: `flag_high_conf_high_prom` (confidence=0.90, prominence=12.0dB),
`RepairWhistlesConfig(confidence_threshold=0.8, prominence_floor_db=10.0)` (OQ-A test value).

**Steps**: Call `apply_whistle_repair(audio, sr, ArtifactDetectionResult(artifact_flags=[flag]), config)`. Inspect the frequency list passed onward and the returned actions.

**Expected result**: `6400.0` is included in the frequencies forwarded to `suno_dsp.repair_whistles`; the summary action entry's `frequencies_notched` contains `6400.0`.

**Pass/fail criterion**: frequency absent from the forwarded list → FAIL.

---

**TC-006**
**Title**: Co-gate — confidence passes, prominence fails → excluded
**Covers**: AC8, architecture §6
**Type**: Functional / ground truth
**Preconditions**: `flag_high_conf_low_prom` (confidence=0.90, prominence=8.0 dB), same config as TC-005 (floor=10.0).

**Expected result**: `6400.0` NOT forwarded to `suno_dsp.repair_whistles`; `frequencies_notched == []`; `stage_ran` may be `True` (invoked with empty list) or the stage records "no flags met the co-gate" — either satisfies AC7's no-op posture, but the frequency must not appear.

**Pass/fail criterion**: frequency present in forwarded list → FAIL.

---

**TC-007**
**Title**: Co-gate — prominence passes, confidence fails → excluded
**Covers**: AC8, architecture §6
**Type**: Functional / ground truth
**Preconditions**: `flag_low_conf_high_prom` (confidence=0.60, prominence=12.0 dB), same config.

**Expected result**: `6400.0` NOT forwarded. Same assertions as TC-006.

**Pass/fail criterion**: as TC-006.

---

**TC-008**
**Title**: Co-gate — boundary at confidence threshold (0.80, inclusive)
**Covers**: AC8, architecture §6
**Type**: Boundary value
**Preconditions**: `flag_boundary_conf` (confidence=0.80 exactly, prominence=12.0), `flag_just_under_conf` (confidence=0.79).

**Expected result**: confidence=0.80 → forwarded (`>=` per architecture §6's stated
comparison). confidence=0.79 → not forwarded.

**Pass/fail criterion**: 0.80 case excluded, or 0.79 case included → FAIL.

---

**TC-009**
**Title**: Co-gate — boundary at prominence floor (10.0 dB test value, inclusive)
**Covers**: AC8, architecture §6
**Type**: Boundary value
**Preconditions**: `flag_boundary_prom` (prominence=10.0 exactly), `flag_just_under_prom` (prominence=9.9).

**Expected result**: prominence=10.0 → forwarded (`>=`). prominence=9.9 → not forwarded.

**Pass/fail criterion**: 10.0 case excluded, or 9.9 case included → FAIL.

---

**TC-010**
**Title**: Co-gate has no effect at or below the detector's own emission floor (6.0 dB) — equivalence test
**Covers**: AC8, architecture §6 ("floor at or below 6 dB has no effect")
**Type**: Audio-quality / ground truth

**Preconditions**: `flag_at_detector_min` (prominence=6.0 exactly, the STORY-007
detector's own minimum emission floor per requirements.md). Two configs:
`RepairWhistlesConfig(prominence_floor_db=6.0)` and `RepairWhistlesConfig(prominence_floor_db=5.0)`
— both at or below the detector's own floor.

**Steps**:
1. Call `apply_whistle_repair` with `flag_at_detector_min` and `prominence_floor_db=6.0`.
   Record the forwarded frequency set.
2. Repeat with the same flag and `prominence_floor_db=5.0`.
3. Compare the two forwarded sets.

**Expected result (derived claim, restated as an equivalence, not a single-value assertion)**:
the forwarded frequency set is **identical** between the `floor=6.0` and `floor=5.0` runs
— both include `6400.0` — because STORY-007 never emits `STATIONARY_WHISTLE` below
6.0 dB prominence in the first place, so any floor at or below that value is
indistinguishable in effect from having no floor at all (confidence-gate-only
behaviour). This is the actual "no effect" claim architecture §6 derives; asserting a
single floor value forwards a flag does not, by itself, demonstrate the floor had no
effect — the two-floor comparison does.

**Pass/fail criterion**: the two runs produce different forwarded sets → FAIL (this would
mean the co-gate comparison is behaving differently at 5.0 vs 6.0, which — given neither
value can ever be met by a flag below the detector's 6.0 dB floor — would indicate a
logic error, e.g. an off-by-one in the comparison operator).

---

**TC-011**
**Title**: `enabled=True` with `prominence_floor_db=None` raises a config-validation error
**Covers**: architecture §6 ("raises a config-validation error if enabled=True and
prominence_floor_db is None")
**Type**: Functional / negative control
**Preconditions**: `RepairWhistlesConfig(enabled=True, prominence_floor_db=None)` (the dataclass default for `prominence_floor_db`).

**Steps**: Construct config, attempt to run the pipeline (or call `apply_whistle_repair` directly) with this config.

**Expected result**: a clear, typed error is raised before any audio processing begins (not a silent no-op, not a `None`-comparison `TypeError` from deep inside the gate logic).

**Pass/fail criterion**: audio processed without error, or a bare unstructured exception with no diagnostic message → FAIL.

---

**TC-012**
**Title**: Negative control — zero `STATIONARY_WHISTLE` flags at or above the co-gate
**Covers**: AC7 (BACKLOG AC4), architecture §3, §6
**Type**: Audio-quality / negative control `[BLOCKED-ON: OLA fix, arch §3]` (for the tolerance
assertion only; the "empty list is what gets forwarded" assertion is not blocked)

**Preconditions**: `ArtifactDetectionResult(artifact_flags=[])` (or a result containing only
flags that fail the co-gate, e.g. `flag_high_conf_low_prom`), config as TC-005.

**Steps**:
1. Call `apply_whistle_repair`.
2. Confirm zero frequencies are forwarded to `suno_dsp.repair_whistles` (or the stage is
   not invoked at all — either is architecturally acceptable per requirements AC7).
3. If invoked with an empty list, run TC-001's gain-curve test on the actual output vs
   input for this specific call.

**Expected result**: `frequencies_notched == []`. Post-OLA-fix: output within 1e-6 of
input. Pre-fix: output shows the TC-001 modulation signature (documented, not a defect
in this stage's gating logic specifically — the gating logic is correct; the OLA bug is
a separate, already-tracked issue).

**Pass/fail criterion (gating)**: any frequency forwarded when no flag meets the co-gate → FAIL.
**Pass/fail criterion (no-op, post-fix only)**: peak diff > 1e-6 → FAIL.

---

**TC-013**
**Title**: Confidence + prominence co-gate is auditable from the action log
**Covers**: AC2, architecture §11
**Type**: Functional
**Preconditions**: Mixed set of flags: `flag_high_conf_high_prom`, `flag_high_conf_low_prom`.

**Expected result**: the per-flag action entry for `flag_high_conf_high_prom` includes
`prominence_db: 12.0`; the excluded flag either does not appear in the per-flag entries
at all, or appears with an explicit `"excluded": true` / equivalent reason field — either
satisfies "auditable from the report, not just log-level reasoning" (architecture §6),
but a silent drop with no trace anywhere in `actions` → FAIL.

**Pass/fail criterion**: `prominence_db` absent from a forwarded flag's action entry, or
no trace of the excluded flag anywhere in the actions payload → FAIL.

---

### Group 3 — `repair_whistles`: structural contract enforcement (AC8, architecture §6)

---

**TC-014**
**Title**: `artifact_detection` parameter rejects a raw frequency list
**Covers**: AC8(c), architecture §6 required test (c)
**Type**: Functional / contract, negative control

**Steps**: Call `apply_whistle_repair(audio, sr, [6400.0, 6500.0], config)` — passing a
raw `list[float]` where `ArtifactDetectionResult | None` is expected.

**Expected result**: an exception is raised before any frequency reaches
`suno_dsp.repair_whistles` — **not necessarily `TypeError`** (Python does not enforce
type annotations at runtime; passing a list where `.artifact_flags` is accessed will
most likely raise `AttributeError` from inside the function body, per OQ-F). Assert
`pytest.raises((TypeError, AttributeError))`, and separately assert (via a mock/spy on
`suno_dsp.repair_whistles`) that it was never called.

**Note (OQ-F)**: requirements.md AC8(c) literally specifies `TypeError`. This test
documents the discrepancy rather than asserting an exception type the code is unlikely
to actually raise. If the architect wants a guaranteed `TypeError`, the wrapper needs an
explicit `isinstance(artifact_detection, ArtifactDetectionResult)` guard — not present in
the current contract (architecture §6). Flagged as an open implementation question.

**Pass/fail criterion**: no exception raised, or `suno_dsp.repair_whistles` is called with
data derived from the raw list → FAIL.

---

**TC-015**
**Title**: `RepairWhistlesConfig` has no frequency-shaped field
**Covers**: AC8(a), architecture §6 required test (a), §9
**Type**: Functional / contract

**Steps**: `[f.name for f in dataclasses.fields(RepairWhistlesConfig)]`. Assert no field
name contains the case-insensitive substring `"freq"` or `"frequenc"`.

**Expected result**: only `enabled`, `confidence_threshold`, `prominence_floor_db`,
`crossfade_ms` present (architecture §9). No frequency field exists.

**Pass/fail criterion**: any matching field name found → FAIL.

---

**TC-016**
**Title**: `apply_whistle_repair` signature has no `list[float]`-typed parameter
**Covers**: AC8(b), architecture §6 required test (b)
**Type**: Functional / contract

**Steps**: `inspect.signature(apply_whistle_repair)`. Inspect each parameter's annotation.

**Expected result**: no parameter is annotated `list[float]` or an equivalent raw
frequency-list type. The only audio-adjacent input parameters are `audio: np.ndarray`,
`sample_rate: int`, `artifact_detection: ArtifactDetectionResult | None`,
`config: RepairWhistlesConfig`.

**Pass/fail criterion**: a `list[float]`-typed (or untyped `list`) parameter present → FAIL.

---

**TC-017**
**Title**: `suno_dsp.repair_whistles` is called from exactly one call site
**Covers**: AC8, architecture §6 ("no code path by which a caller can pass a raw frequency list")
**Type**: Functional / contract, static

**Steps**: Grep the pipeline source tree for `suno_dsp.repair_whistles(` and
`suno_dsp\.repair_whistles`. Also grep for direct `import suno_dsp` outside
`whistle_repair.py`.

**Expected result**: exactly one call site, inside `apply_whistle_repair` in
`mastering/whistle_repair.py`. `pipeline.py` never imports `suno_dsp` directly
(architecture §6).

**Pass/fail criterion**: more than one call site, or a direct `suno_dsp` import in
`pipeline.py` → FAIL. **Note**: this is a static/structural check that runs against the
source tree (grep/AST), outside pytest's normal collection/execution model — it should
be wired into the automation suite as a source-inspection step, not implemented as a
runtime assertion inside a test that imports and calls the module.

---

### Group 4 — `repair_whistles`: sub-frame refusal (AC9, architecture §5)

---

**TC-018**
**Title**: Sub-frame input (4095 samples) is refused, not padded or silently bypassed
**Covers**: AC9, architecture §5
**Type**: Edge case / negative control
**Preconditions**: Fixture F-007, `samples_under` (4095 samples, ~92.85 ms at 44.1 kHz).

**Steps**: Enable `repair_whistles`, call the pipeline (or `apply_whistle_repair`
directly) with this input and a config that would otherwise process it.

**Expected result**: `SubFrameAudioError` (architecture §5) is raised **before**
`suno_dsp.repair_whistles` is called. Output is never returned as all-zero silence.

**Pass/fail criterion**: no exception raised, or output is silence (all zeros), or the
raw `suno_dsp` divide-by-zero-guard silence propagates through unflagged → FAIL.

---

**TC-019**
**Title**: At-threshold input (exactly 4096 samples) is accepted, not refused
**Covers**: AC9, architecture §5 (boundary — main loop condition `start + frame_size <= n_samples`)
**Type**: Boundary value
**Preconditions**: Fixture F-007, `samples_at` (exactly 4096 samples).

**Steps**: Same as TC-018 but with the at-threshold fixture.

**Expected result**: no `SubFrameAudioError`. The stage processes normally (one analysis
frame; edge-frame OLA artifacts per architecture §3 may apply pre-fix, but the call must
not be refused).

**Pass/fail criterion**: `SubFrameAudioError` raised for exactly 4096 samples → FAIL.

---

### Group 5 — `repair_whistles`: windowed crossfade localisation (architecture §4)

---

**TC-020**
**Title**: Crossfade localisation — output outside the flagged window is bit-identical to original
**Covers**: architecture §4
**Type**: Functional / ground truth (not blocked by the OLA fix — this assertion is
independent of what happens *inside* the window)

**Preconditions**: 10 s stereo broadband noise (seed=42, 44.1 kHz), one `ArtifactFlag`
with `timestamp_start_s=4.0`, `timestamp_end_s=6.0`, meeting the co-gate,
`crossfade_ms=50.0`.

**Steps**:
1. Run `apply_whistle_repair` with this single flag.
2. Compare output to input sample-for-sample outside `[4.0 - 0.05 - skirt, 6.0 + 0.05 + skirt]`
   (the crossfade region plus its 50 ms ramp, per architecture §4's docstring: "outside
   that range, output is bit-identical to `original`").

**Expected result**: bit-identical (exact equality, not tolerance-bounded) outside the
window+skirt. This is the "localized near the detected window, not applied to the whole
file" requirement from the task brief.

**Pass/fail criterion**: any sample difference outside the window+skirt → FAIL. This is
the strongest and most diagnostic test in this group — it isolates the wrapper's
crossfade logic from the C++ OLA bug entirely.

---

**TC-021**
**Title**: Crossfade localisation — multiple overlapping flags merge into one region, not doubled
**Covers**: architecture §4 ("overlapping flag windows produce a single merged processed region")
**Type**: Functional / edge case

**Preconditions**: Two `ArtifactFlag`s meeting the co-gate: `[2.0, 4.0]` and `[3.5, 5.5]`
(overlapping by 0.5 s), same or different frequencies.

**Steps**: Run `apply_whistle_repair`. Inspect the effective processed region.

**Expected result**: the union `[2.0, 5.5]` (± skirt) is processed once — the overlap
region `[3.5, 4.0]` is not double-crossfaded (which would produce a different, incorrect
attenuation depth than either single-flag case). Outside `[2.0-skirt, 5.5+skirt]`, output
is bit-identical to input (per TC-020's criterion).

**Pass/fail criterion**: attenuation depth in the overlap region measurably different
(deeper) than in the non-overlapping single-flag portions → FAIL.

---

**TC-022**
**Title**: In-window notch depth — attenuation reaches at least 20 dB at the target frequency
**Covers**: architecture §4, requirements.md ("Genuinely surgical... Q ≈ 120")
**Type**: Audio-quality / ground truth `[BLOCKED-ON: OLA fix, arch §3]` (measuring notch
depth cleanly requires the reconstruction gain to be unity outside the intended
attenuation; pre-fix, the 21.5 Hz modulation adds noise to this measurement)

**Preconditions**: 10 s stereo signal: broadband noise bed + a 6400 Hz tone (prominence
well above 6 dB) sustained across `[3.0, 7.0]` s. One `ArtifactFlag` at 6400 Hz covering
that window, co-gate satisfied.

**Steps**: Run `apply_whistle_repair`. Measure the level at 6400 Hz in the output vs
input, within the processed window (excluding crossfade ramps).

**Expected result**: at least 20 dB of attenuation at 6400 Hz within the window (the C++
notch depth is nominally −40 dB per requirements.md; 20 dB is a conservative floor
allowing for window-leakage/measurement-FFT effects, stated explicitly as a safety
margin, not the exact expected value).

**Pass/fail criterion**: attenuation < 20 dB within the window → FAIL.

---

### Group 6 — `shape_transients`: highpassed sidechain / 2f flutter (AC13, architecture §7)

---

**TC-023**
**Title**: No 2f gain flutter on a sustained 55 Hz bass tone (corrected test target per Gate 1)
**Covers**: AC13, architecture §7, §14 Blocker 3
**Type**: Audio-quality / ground truth `[BLOCKED-ON: sidechain+link patch, arch §7]`
**Preconditions**: Fixture F-003 (55 Hz, stereo identical L=R, 2.0 s), `attack_boost_db=+3, sustain_cut_db=-3` (architecture §7's stated required-test parameters, OQ-E).

**Steps**:
1. Run `apply_transient_shaping(audio, 44100, config)`.
2. Compute `g[n] = out[n] / in[n]` (masked where `|in[n]|` is below a small floor, e.g.
   1% of peak, to avoid division blow-ups near zero-crossings).
3. FFT `g[n]`. Assert no prominent component at `2 × 55 = 110 Hz` (this is the corrected
   target — the *original* required test checked flutter at the fundamental `55 Hz`,
   which architecture §7/§14 found would falsely pass a broken implementation, because
   full-wave rectification of a sine at `f` produces no energy at `f` — its lowest AC
   component is at `2f`).
4. Additionally, AM sidebands: an AM of a 55 Hz carrier by a 110 Hz modulator places a
   new spectral line at the sum frequency `55 + 110 = 165 Hz` (3× the fundamental) not
   present in the input. Assert no new line at 165 Hz above −60 dBc (60 dB below the
   carrier).

**Expected result — pre-patch (current gain-law-only or unmodified C++)**: prominent
component at 110 Hz in `g[n]`'s spectrum, and/or a new line at 165 Hz in the output
spectrum — the sub/bass fundamental leaks through the unfiltered rectifier per
architecture §7's root-cause analysis.
**Expected result — post-patch (highpass-before-rectify + stereo link landed)**: no
prominent component at 110 Hz in `g[n]` above the noise floor; no new line at 165 Hz
above −60 dBc.

**Pass/fail criterion (post-patch)**: either assertion fails → FAIL.

---

**TC-024**
**Title**: Minimal flutter at 880 Hz for a 440 Hz fundamental (well above the sidechain corner)
**Covers**: AC13, architecture §7
**Type**: Audio-quality / ground truth `[BLOCKED-ON: sidechain+link patch, arch §7]`
**Preconditions**: Fixture F-003, 440 Hz variant, same config as TC-023.

**Steps**: As TC-023, targeting `2 × 440 = 880 Hz` and the 1320 Hz AM sideband.

**Expected result**: minimal flutter at 880 Hz — architecture §7 derives this as ~21 dB
down at the fast follower's 79.6 Hz one-pole corner even *without* the sidechain fix
(since 880 Hz is far above 79.6 Hz regardless of whether a 150 Hz highpass precedes
rectification). This case should show low flutter both pre- and post-patch; it is
included as a sanity check that the fix does not *introduce* a regression at
mid/high fundamentals, not primarily to catch the bug itself.

**Pass/fail criterion**: flutter magnitude at 880 Hz worse (more prominent) after the
patch than before → FAIL (regression). This is the one sub-case in this group not
strictly blocked on the patch landing — it can be run against current code as a
baseline and re-run post-patch for comparison.

---

**TC-025**
**Title**: Near-corner residual flutter, 160/200/250 Hz fundamentals — baseline for final cutoff choice
**Covers**: architecture §7 (OQ-C — sidechain cutoff selection within 150–250 Hz)
**Type**: Audio-quality `[Baseline]` — no automated pass/fail; feeds the eventual cutoff decision
**Preconditions**: Fixture F-004 (160/200/250 Hz sweep), same config as TC-023.

**Steps**: As TC-023/024, for each fundamental in {160, 200, 250} Hz, targeting `2×f0`
(320/400/500 Hz).

**Expected result**: record the measured flutter magnitude at `2×f0` for each fundamental
against the 150 Hz working sidechain cutoff. Architecture §7 states: "if it still
flutters audibly at 150 Hz, that is evidence for moving the cutoff toward 250 Hz." This
test's output is the evidence, not a pass/fail verdict.

**Pass/fail criterion**: none. Record as baseline data in the QA report.

---

**TC-026**
**Title**: Stereo-linked control signal — L and R gain multipliers are sample-for-sample identical
**Covers**: AC13, architecture §7, §14 Blocker 11
**Type**: Functional / ground truth `[BLOCKED-ON: sidechain+link patch, arch §7]`
**Preconditions**: Fixture F-005 (shared 220 Hz bed both channels, hi-hat-like burst on L only).

**Steps**:
1. Run `apply_transient_shaping(audio, sr, config)`.
2. Compute `g_L[n] = out_L[n] / in_L[n]`, `g_R[n] = out_R[n] / in_R[n]` (both denominators
   safe — bed is present on both channels throughout, per F-005's design, avoiding the
   ill-conditioned "silent channel" case).
3. Compute `max(|g_L[n] - g_R[n]|)` across the full signal, including the burst region.

**Expected result — pre-patch (independent per-channel envelope followers)**: `g_L` and
`g_R` diverge measurably during the burst window on L (R's follower never sees the
transient, so its multiplier stays near the sustain value while L's briefly switches to
the attack value).
**Expected result — post-patch (stereo-linked `max(|L|,|R|)` control)**: `max(|g_L[n] -
g_R[n]|)` ≤ the same 1e-6 float32 round-trip tolerance (architecture §2) at every sample,
including through the burst.

**Pass/fail criterion (post-patch)**: `max(|g_L[n] - g_R[n]|)` > 1e-6 → FAIL.

---

**TC-027**
**Title**: Mono input degenerates correctly (`max` over channels == `|L|`)
**Covers**: architecture §7 ("no mono/multi-channel branch is required... degenerates
correctly to `|audio[n, 0]|` for mono input")
**Type**: Functional / ground truth `[BLOCKED-ON: sidechain+link patch, arch §7]`
**Preconditions**: F-003 (55 Hz), mono variant (shape `(n, 1)` or `(n,)`).

**Steps**: Run `apply_transient_shaping` on the mono signal. Confirm no exception, no
special-case branch behaviour (compare gain envelope to the same signal duplicated to
stereo and processed, then take either channel — should match, since `max(|L|,|R|)` on
identical channels equals `|L|`).

**Expected result**: mono processes without error; gain envelope matches the
identical-stereo-channel case exactly (within the 1e-6 tolerance).

**Pass/fail criterion**: exception raised for mono input, or gain envelope diverges from
the stereo-identical-channel case beyond tolerance → FAIL.

---

### Group 7 — `shape_transients`: SMEARED_TRANSIENT guard (AC11, AC12, architecture §7)

---

**TC-028**
**Title**: Signature has no artifact/detection-shaped parameter
**Covers**: AC11, architecture §7 required test (structural, not commentary)
**Type**: Functional / contract, negative control

**Steps**: `inspect.signature(apply_transient_shaping).parameters`. For each parameter
name and its type annotation (as a string), case-insensitive substring check for
`"artifact"`, `"flag"`, `"detection"`, `"smear"`.

**Expected result**: no match. Only `audio`, `sample_rate`, `config` parameters exist.

**Pass/fail criterion**: any matching substring found in a parameter name or annotation → FAIL.

---

**TC-029**
**Title**: `ShapeTransientsConfig` carries only plain user-supplied constants
**Covers**: AC11, architecture §7, §9
**Type**: Functional / contract

**Steps**: `dataclasses.fields(ShapeTransientsConfig)`. Assert field set is exactly
`{enabled, attack_boost_db, sustain_cut_db}` — no field referencing artifact detection,
and no sidechain-cutoff or slow-constant field (those remain internal C++ constants
per architecture §7/§9).

**Pass/fail criterion**: extra or artifact-referencing field present → FAIL.

---

**TC-030**
**Title**: Report/log text never uses artifact-repair vocabulary
**Covers**: AC12, architecture §7 ("Report/log text is generated from a hardcoded
template... never references artifact/repair vocabulary")
**Type**: Functional

**Steps**: Run `apply_transient_shaping` with `enabled=True`, inspect the generated
log/report string for this stage.

**Expected result**: string matches the template "Transient shaping (dynamics/glue):
attack ±X dB, sustain ±Y dB" (or equivalent); case-insensitive substring check for
`"artifact"`, `"repair"`, `"smear"`, `"correction"` (as applied to the *problem*, not
generic dynamics terms) finds no match.

**Pass/fail criterion**: any of the above substrings present in the rendered report/log
text for this stage → FAIL.

---

### Group 8 — `collapse_swish`: HF collapse / LF preserve ground truth (AC15, architecture §8)

---

**TC-031**
**Title**: DC gain of the deployed lowpass is exactly 1 — LF side content preserved (algebraic ground truth)
**Covers**: architecture §8 ("DC gain is exactly 1... low-frequency stereo width is
preserved, not collapsed")
**Type**: Functional / ground truth (algebraic, not signal-dependent — can be verified
directly on the coefficients, independent of any audio fixture)

**Steps**:
1. Compute RBJ biquad coefficients for the deployed lowpass at the test cutoff
   (`cutoff_freq_hz = 5000.0`, OQ-B) and `sample_rate = 44100`, Q = 0.7071
   (`b0 = (1-cosω)/2, b1 = 1-cosω, b2 = (1-cosω)/2, a0 = 1+α, a1 = -2cosω, a2 = 1-α`).
2. Compute `(b0+b1+b2)/(a0+a1+a2)`.

**Expected result**: `(b0+b1+b2)/(a0+a1+a2) = 1.0` exactly (within float64 rounding,
~1e-12), algebraically independent of the cutoff value chosen — this is the derivation
in architecture §8, restated as a direct numeric check.

**Pass/fail criterion**: deviation from 1.0 beyond float64 rounding → FAIL. This is the
single strongest ground-truth check available for this stage — a wrong sign or
coefficient error would show up here immediately.

---

**TC-032**
**Title**: HF side content collapses toward mono; LF side content preserved (signal-level ground truth, freqz-derived expected attenuation)
**Covers**: AC15, architecture §8
**Type**: Audio-quality / ground truth
**Preconditions**: Fixture F-006 (decorrelated broadband noise, stereo), `cutoff_freq_hz=5000.0` (OQ-B test value).

**Steps**:
1. Independently compute the deployed biquad's coefficients at `cutoff_freq_hz=5000.0`,
   44.1 kHz, Q=0.7071 (same computation as TC-035), and evaluate `H(e^jω)` via
   `scipy.signal.freqz` across the 8–16 kHz band.
2. Integrate `|H(f)|²` (power) across the 8–16 kHz band on a fine frequency grid to get
   an expected **band-averaged attenuation figure for that band**, rather than a single
   per-frequency dB value (a band-integrated measurement over a sloped response cannot
   be expected to match a single-point filter value exactly).
3. Measure stereo width (side/mid energy ratio) in two bands of the **input**: LF
   (200–1000 Hz) and HF (8000–16000 Hz).
4. Run `apply_collapse_swish`.
5. Measure the same two bands in the **output**. Compare HF-band attenuation to the
   `freqz`-derived expected figure from step 2; compare LF-band width to the input,
   expecting near-zero change consistent with TC-031's exact-unity DC gain.

**Expected result**: HF-band (8–16 kHz) side energy is reduced by **at least 8 dB**
relative to input (a floor, not the exact `freqz`-derived figure, to allow for
measurement-window and band-integration effects — the `freqz` figure from step 2 is the
primary reference value the automation engineer should reconcile the measured result
against, this 8 dB floor is the fallback sanity bound if the exact reconciliation proves
noisy). LF-band (200–1000 Hz) width changes by no more than ±0.5 dB.

**Pass/fail criterion**: HF-band attenuation < 8 dB, or LF-band width changes by more
than ±0.5 dB → FAIL.

---

**TC-033**
**Title**: Cutoff at/above Nyquist raises (C++ guard), not a passthrough
**Covers**: architecture §8 ("guarded against by the C++'s own `cutoff_freq < sample_rate/2` check")
**Type**: Edge case / negative control
**Preconditions**: Fixture F-006, `cutoff_freq_hz = 22050.0` (== Nyquist at 44.1 kHz) and `cutoff_freq_hz = 30000.0` (> Nyquist).

**Expected result**: `suno_dsp.collapse_swish` raises (the C++'s own guard), surfaced by
the wrapper as a clear error — **not** silently treated as a full-passthrough case. (Note:
this corrects an earlier framing risk — a cutoff *approaching* Nyquist from below is
where the response approaches a full passthrough asymptotically; a cutoff *at or above*
Nyquist is invalid input, not a valid degenerate case.)

**Pass/fail criterion**: no exception raised for `cutoff_freq_hz >= sample_rate/2` → FAIL.

---

**TC-034**
**Title**: `cutoff_freq_hz=0.0` (config default) raises — stage cannot silently run unreviewed
**Covers**: architecture §9 ("0.0 deliberately invalid — forces Gate 1 to set it before this stage can ever run")
**Type**: Functional / negative control
**Preconditions**: `CollapseSwishConfig(enabled=True)` — i.e. `cutoff_freq_hz` left at its dataclass default, 0.0.

**Expected result**: the C++'s own `> 0.0f` guard raises, surfaced as a clear error before
processing.

**Pass/fail criterion**: audio processed (even trivially) with `cutoff_freq_hz=0.0` → FAIL.

---

### Group 9 — `collapse_swish`: [5a] skirt-band report (AC16, architecture §8, §11, §14 Blocker 8)

---

**TC-035**
**Title**: −1 dB and −3 dB skirt points are computed numerically from the deployed biquad, not the analog-prototype approximation
**Covers**: architecture §8 ("must compute both... numerically from the deployed biquad's
actual transfer function," "the analog-prototype formula... is not the value the wrapper
should use directly")
**Type**: Functional / ground truth, negative control against a known-wrong shortcut

**Steps**:
1. Independently (in the test, not reusing the wrapper's internal computation) compute
   the RBJ biquad coefficients at `cutoff_freq_hz=5000.0`, 44.1 kHz, Q=0.7071.
2. Evaluate `H(e^jω)` over a fine frequency grid (e.g. `scipy.signal.freqz`), find the
   frequencies where `|H|` crosses −1 dB and −3 dB.
3. Compare against the wrapper's reported `f₋₁dB` and `f₋₃dB` in the `collapse_swish`
   action-log entry.
4. Separately compute the analog-prototype cross-check `f₋₁dB ≈ 0.713 × 5000 = 3565 Hz`
   and confirm it is numerically **close to but not identical to** the digital-biquad
   result from step 2 (the gap is the expected bilinear-transform warp, architecture §8)
   — this is the negative control against wrongly asserting the 0.713 figure as the
   expected value.

**Expected result**:
- `f₋₃dB` reported by the wrapper equals `cutoff_freq_hz` exactly (5000.0 Hz) — this is
  by construction of Q=0.7071 (architecture §8), an exact ground truth.
- `f₋₁dB` reported by the wrapper matches the test's independent `freqz`-based
  computation within a small numeric tolerance (e.g. 1 Hz), and differs from the
  0.713×cutoff analog-prototype figure by a measurable, non-zero amount.

**Pass/fail criterion**: wrapper's `f₋₁dB` matches the 0.713×cutoff figure exactly (to
more precision than the analog/digital warp would allow) rather than the `freqz`-based
figure → FAIL (this indicates the wrapper used the prototype formula directly, which
architecture §8 explicitly forbids). Wrapper's `f₋₃dB` != `cutoff_freq_hz` → FAIL.

---

**TC-036**
**Title**: `overlapping_5a_bands` correctly classifies band edges by skirt severity
**Covers**: AC16, architecture §8, §11
**Type**: Functional / ground truth
**Preconditions**: `cutoff_freq_hz=5000.0`. Using [5a]'s existing band definitions
(read from `pipeline.py`, not redefined here per architecture — this test's expected
classifications are derived once the actual band edges are known; flagged as needing
the real band-edge values to complete).

**Steps**: Run `apply_collapse_swish` with `artifact_detection` containing whatever
PHASE_SWISH flags are present (or `None`). Inspect `overlapping_5a_bands` in the action
log.

**Expected result**: each [5a] band is classified `"unaffected"` (band edge below
`f₋₁dB`), `"partial(-1..-3dB)"` (between `f₋₁dB` and `f₋₃dB`), or `"significant(>=-3dB)"`
(at/above `f₋₃dB`), consistent with TC-035's independently-computed `f₋₁dB`/`f₋₃dB`.

**Pass/fail criterion**: a band's classification inconsistent with its edge frequency
relative to the independently-computed skirt points → FAIL.

**Note**: exact expected classifications per band name are an open item pending the
actual [5a] band-edge values from `pipeline.py` — this test's assertions must be
completed against those real values, not invented here (H9 — do not read the
implementation from this document's authoring context).

---

### Group 10 — `collapse_swish`: PHASE_SWISH not auto-triggered (architecture §8, §14 Blocker 7)

---

**TC-037**
**Title**: `artifact_detection` is advisory only — audio output identical whether PHASE_SWISH flags are present or absent
**Covers**: architecture §8 ("artifact_detection is consumed only to append advisory
PHASE_SWISH context... never gates or parameterises the call")
**Type**: Functional / negative control (this is the "never auto-triggered" guarantee, made testable)
**Preconditions**: Fixture F-006, `cutoff_freq_hz=5000.0`, `enabled=True`. Two runs:
(a) `artifact_detection=None`, (b) `artifact_detection` containing two `PHASE_SWISH` flags.

**Steps**: Run `apply_collapse_swish` both ways with identical audio/config. Compare
output audio arrays and compare `phase_swish_flags_present` in the action log.

**Expected result**: output audio is bit-identical between (a) and (b) — the presence of
PHASE_SWISH flags changes only the log's `phase_swish_flags_present` count (0 vs 2), never
the processing itself.

**Pass/fail criterion**: any sample difference in the output audio between (a) and (b) → FAIL.

---

**TC-038**
**Title**: `collapse_swish` is never invoked when the flag is off, regardless of PHASE_SWISH presence
**Covers**: AC1, architecture §8
**Type**: Functional / negative control
**Preconditions**: `CollapseSwishConfig(enabled=False)` (default), `artifact_detection`
containing PHASE_SWISH flags.

**Steps**: Run the pipeline. Spy on `suno_dsp.collapse_swish` to confirm zero calls.

**Expected result**: zero calls to `suno_dsp.collapse_swish`; `"collapse_swish"` key
absent from `result.actions` (AC1 literalism, architecture §11).

**Pass/fail criterion**: `suno_dsp.collapse_swish` called, or the key present (even as
`None`/`[]`) → FAIL.

---

### Group 11 — `collapse_swish`: channel-count guard (AC14, architecture §8)

---

**TC-039**
**Title**: Non-stereo input is checked before the call, not caught as control flow
**Covers**: AC14, architecture §8
**Type**: Edge case / negative control
**Preconditions**: Mono (1-channel) and 3-channel synthetic input, `enabled=True`,
valid `cutoff_freq_hz`.

**Steps**: Run `apply_collapse_swish` on each. Spy on `suno_dsp.collapse_swish` to
confirm it is never called for non-stereo input (proving the wrapper checks
`audio.shape[1] == 2` itself, per architecture §8, rather than relying on catching the
C++'s `std::invalid_argument`).

**Expected result**: for both mono and 3-channel input — `suno_dsp.collapse_swish` is
never called; the action log records a `"skipped — not stereo"` entry (or equivalent);
audio is returned unmodified.

**Pass/fail criterion**: `suno_dsp.collapse_swish` called for non-stereo input, or an
uncaught `std::invalid_argument`/`RuntimeError` propagates from the C++, or audio is
modified → FAIL.

---

### Group 12 — All three stages: config gating / bypass (AC1, AC3, AC4, AC5, architecture §10, §14)

---

**TC-040**
**Title**: All flags off — pipeline output is byte-identical to a run where `suno_dsp` is entirely unavailable
**Covers**: architecture §10 ("All three flags off... import failure... never affects the run")
**Type**: Functional / ground truth
**Preconditions**: Any representative fixture (e.g. F-006), default `MasteringConfig` (all three new flags `False`).

**Steps**:
1. Run the full pipeline normally (with `suno_dsp` importable, but no flags enabled).
2. Run the full pipeline again with `suno_dsp` made unavailable (e.g. `sys.modules['suno_dsp'] = None` or uninstalled in a clean environment).
3. Compare output WAV files byte-for-byte.

**Expected result**: byte-identical output in both cases — a pipeline run with the
stage's module absent/unavailable produces identical output to a run where it is present
but unused (this is the module-absence equivalence the task brief specifically calls out).

**Pass/fail criterion**: any byte difference → FAIL.

---

**TC-041**
**Title**: Enabling one flag with `suno_dsp` unimportable fails loudly before processing begins
**Covers**: AC3, architecture §10
**Type**: Functional / negative control
**Preconditions**: Any one of the three flags `True`, `suno_dsp` made unimportable.

**Expected result**: `DependencyError` raised immediately after config load, before
Stage [1] (ingest) begins — matching the existing `load_targets` fail-fast pattern
(`pipeline.py` ~line 141).

**Pass/fail criterion**: no exception, or an exception raised mid-pipeline (after some
processing already occurred) rather than at the pre-flight check → FAIL.

---

**TC-042**
**Title**: AC1 literalism — disabled stage's key is absent from `actions`, not `None`
**Covers**: AC1, architecture §11
**Type**: Functional
**Preconditions**: All three flags off (default).

**Steps**: Run pipeline. Inspect `result.actions`.

**Expected result**: `"repair_whistles" not in result.actions`, `"collapse_swish" not in
result.actions`, `"shape_transients" not in result.actions` — key absence, not
`is None`. (Contrast with the existing weaker `"resample": None` convention, which
architecture §11 explicitly calls out as different.)

**Pass/fail criterion**: any of the three keys present with value `None` or `[]` when
the corresponding flag is off → FAIL.

---

**TC-043**
**Title**: Each enabled stage's invocation is logged with before/after data (AC2)
**Covers**: AC2, architecture §11
**Type**: Functional
**Preconditions**: Each of the three flags enabled individually, each with a valid
(non-degenerate) config and input that triggers real processing.

**Steps**: Run pipeline with each flag on individually. Inspect the corresponding
action-log entry's fields against architecture §11's minimum-field lists.

**Expected result**:
- `repair_whistles`: per-flag entries with `frequency_hz`, `confidence_score`,
  `prominence_db`, `timestamp_start_s`, `timestamp_end_s`, `peak_delta_db`,
  `rms_delta_db`; plus a summary entry with `frequencies_notched`, `stage_ran`.
- `shape_transients`: `attack_boost_db`, `sustain_cut_db`, `peak_delta_db`, `rms_delta_db`.
- `collapse_swish`: `cutoff_freq_hz`, `side_energy_delta_db`, `phase_swish_flags_present`,
  `overlapping_5a_bands`.

**Pass/fail criterion**: any required field missing → FAIL.

---

**TC-044**
**Title**: No default may be on without a Gate 1 clearance record (AC5)
**Covers**: AC5
**Type**: Functional / contract, static

**Steps**: Inspect `RepairWhistlesConfig()`, `ShapeTransientsConfig()`,
`CollapseSwishConfig()` — the dataclass field defaults, unconstructed.

**Expected result**: `enabled=False` on all three. `prominence_floor_db=None`,
`cutoff_freq_hz=0.0` (deliberately invalid — see TC-011, TC-034). No numeric value that
would allow a silent, unreviewed run if `enabled` were accidentally flipped.

**Pass/fail criterion**: any of the three defaults to `enabled=True`, or a numeric
default exists that would allow `collapse_swish`/`repair_whistles` to run without an
explicit value being set → FAIL. This test should also be re-run any time architecture.md
is revised, to catch an accidental default flip that was not accompanied by a recorded
Gate 1 clearance.

---

### Group 13 — Determinism (AC4, architecture §12)

---

**TC-045**
**Title**: Identical input + config produces byte-identical output across repeated runs (all three stages, individually and combined)
**Covers**: AC4, architecture §12
**Type**: Functional / regression (property test — **not** a ground-truth test; H2 does
not apply, per architecture §12's own framing — "assert this, don't assume it")

**Preconditions**: Fixture F-006 or similar, all 2³=8 combinations of the three flags
(on/off), each with a fixed valid config.

**Steps**: For each combination, run the full pipeline twice with identical input and
config. Compare output WAV files byte-for-byte.

**Expected result**: byte-identical output for every combination, every run pair.

**Pass/fail criterion**: any byte difference between the two runs of the same
combination → FAIL.

---

### Group 14 — Edge cases: silence, near-clipping, NaN, mono/stereo, sample rates

---

**TC-046**
**Title**: Digital silence through all three stages — no NaN/Inf, no crash
**Covers**: Non-functional / robustness (divide-by-zero risk named explicitly in
requirements.md and architecture §7 for the `diff/(|diff|+eps)` and proposed
`diff/(slow_env+eps)` gain laws)
**Type**: Edge case
**Preconditions**: Fixture F-008 (digital silence, 1.0 s stereo, 44.1 kHz), all three
flags enabled with valid configs (using a synthetic single `STATIONARY_WHISTLE` flag for
`repair_whistles` so it has something to act on, or an empty list for the no-op case).

**Steps**: Run each stage individually and in combination on F-008. Check `np.isnan`,
`np.isinf` on the output.

**Expected result**: no NaN, no Inf, in any stage's output. `collapse_swish` on silent
input: side channel is zero, filter output remains zero (stable, no denormal blow-up
expected but worth confirming no exception).

**Pass/fail criterion**: any NaN/Inf in output, or an unhandled exception → FAIL.

---

**TC-047**
**Title**: NaN-contaminated input is refused or clearly detected, never silently zeroed
**Covers**: Non-functional / failure mode (NFR: "never a silent fallback to unmodified
audio when a flag is explicitly enabled and the call was attempted")
**Type**: Edge case / negative control
**Preconditions**: Fixture F-009 (one NaN sample injected).

**Steps**: Run each of the three stages (enabled) on F-009.

**Expected result**: either (a) a clear, typed validation error is raised before
processing (preferred, consistent with the sub-frame refusal posture in architecture
§5), or (b) the NaN propagates visibly into the output (detectable, not silently
replaced with zero or a plausible-looking value). Silent NaN-to-zero substitution
anywhere in the chain → FAIL, since that is indistinguishable from a correct result
without independently checking.

**Pass/fail criterion**: NaN silently converted to a finite value with no error/warning
raised → FAIL.

---

**TC-048**
**Title**: 48 kHz input processes correctly through all three stages (sample-rate-dependent math)
**Covers**: Non-functional / audio-quality (requirements.md explicitly flags notch width
and OLA modulation frequency as sample-rate-dependent)
**Type**: Audio-quality
**Preconditions**: F-001, F-003, F-006 all reconstructed at `sr=48000`.

**Steps**: Run TC-002 (already 48 kHz), and re-run representative cases from Groups 6
and 8 at 48 kHz.

**Expected result**: all sample-rate-dependent derived quantities (OLA modulation
frequency, biquad coefficients, envelope-follower time constants converted to samples)
scale correctly with `sample_rate` — no hardcoded 44100 assumption anywhere in the
wrapper chain.

**Pass/fail criterion**: any assertion in the 48 kHz variant matching the 44.1 kHz
expected numeric value instead of the sample-rate-scaled one → FAIL (this would indicate
a hardcoded rate assumption).

---

**TC-049**
**Title**: Mono input to `repair_whistles` and `shape_transients` — no crash, `collapse_swish` skips cleanly
**Covers**: Edge case / channel-count coverage
**Type**: Edge case
**Preconditions**: F-003 mono variant, F-001 mono variant.

**Steps**: Run each stage on mono input.

**Expected result**: `repair_whistles` processes mono (L/R-independent notching
degenerates to single-channel notching, per requirements.md — "L and R... notched
independently" applies trivially to a single channel). `shape_transients` processes
mono per TC-027. `collapse_swish` skips per TC-039 (mono is non-stereo).

**Pass/fail criterion**: crash, or `collapse_swish` attempting to process mono input → FAIL.

---

**TC-052**
**Title**: Full-scale / near-clipping input — no new NaN/Inf, any overshoot reported, not silently occurring
**Covers**: Non-functional / robustness (coverage gap closed per this document's Revision history)
**Type**: Edge case
**Preconditions**: Fixture F-011 (sample peak −0.3 dBFS, stereo, 44.1 kHz, 2.0 s). Each
of the three stages enabled individually with a valid config
(`shape_transients` with `attack_boost_db=+3` specifically — the one parameter of the
three stages that adds broadband gain mid-chain and is therefore the most plausible
source of a new overshoot past ±1.0 before Stage [6] limiting sees the signal).

**Steps**:
1. Run each stage on F-011.
2. Check output for NaN/Inf.
3. Compute output sample peak. If it exceeds the input sample peak (−0.3 dBFS) by more
   than 0.1 dB, confirm this is reflected in the stage's `peak_delta_db` action-log
   field (architecture §11) — i.e. any overshoot is visible in the report, not a silent
   excursion that only [6] Loudness/Limiting downstream happens to catch.

**Expected result**: no NaN/Inf in any stage's output. Any peak increase beyond the
input's −0.3 dBFS is present in `peak_delta_db` for that stage's action-log entry —
consistent in sign and rough magnitude with the observed output peak change.

**Pass/fail criterion**: NaN/Inf present, or an output peak increase not reflected in
the corresponding `peak_delta_db` field → FAIL.

---

### Group 15 — Chain-level: final master still meets standing targets (AC6)

---

**TC-050**
**Title**: Any subset of the three stages enabled — final master still meets −13.5 LUFS, −1.0 dBTP, DR 6.6–8.7
**Covers**: AC6
**Type**: Audio-quality / ground truth `[Slow]`
**Preconditions**: A representative full-length input track (or several seconds
sufficient for LUFS gating — note LUFS integration requires enough programme material
to gate meaningfully; use at least one reference-length track per architecture.md §5's
convention for `MASTERING: loudness`), each of the 8 flag combinations (as TC-045).

**Steps**: Run the full pipeline for each combination. Measure integrated LUFS, true
peak (dBTP), and TT DR on the final output.

**Expected result** (OQ-G — reusing architecture.md §5's stated tolerance convention,
since this story does not restate one): integrated loudness within **±0.1 LU** of
−13.5 LUFS; true peak **≤ −1.0 dBTP**; DR within **6.6–8.7** (CLAUDE.md §4.2 hard
target). The report must show the before/after delta introduced specifically by each
newly-enabled stage (architecture §11's per-stage action entries), so a regression is
attributable to a specific stage, not just to "the pipeline" in aggregate.

**Pass/fail criterion**: any combination misses the loudness tolerance, exceeds the true
peak ceiling, or falls outside the DR range → FAIL. Additionally, if a failure occurs,
the per-stage delta fields (architecture §11) must be sufficient to identify which
newly-enabled stage caused it — inability to attribute the regression to a specific
stage is itself a defect in the logging contract, not just the audio result.

---

### Group 16 — Sanity assertions (physically impossible output, cheap, no ground truth needed)

---

**TC-051**
**Title**: Sanity invariants across all three stages
**Covers**: General robustness (mirrors ARCHITECTURE.md's cross-cutting sanity-check discipline)
**Type**: Functional / sanity
**Preconditions**: Any of the fixtures above run through each enabled stage.

**Steps and assertions** (all must hold on every processed output):
1. Output sample count matches input sample count exactly (no stage changes duration).
2. Output dtype is `float64` at the wrapper boundary (architecture §2 — the float32
   round-trip is confined inside the wrapper functions).
3. Output sample peak does not exceed a stage-specific bound relative to input sample
   peak: for `collapse_swish` and `repair_whistles` (neither adds intentional broadband
   gain), output peak ≤ input peak + 0.5 dB; for `shape_transients`, output peak ≤ input
   peak + `attack_boost_db` + 0.5 dB (the 0.5 dB margin in both cases accounts for the
   float32 round-trip and, pre-OLA-fix, the reconstruction-gain modulation itself —
   this bound is deliberately generous enough not to double as an OLA-bug detector,
   which is TC-001–003's job specifically).
4. `collapse_swish`'s reported `f₋₃dB` always equals the configured `cutoff_freq_hz`
   (algebraic identity, TC-035) — a mismatch is impossible under the correct
   coefficients and indicates a bug regardless of any specific fixture.
5. `repair_whistles`'s per-flag `prominence_db` in the action log is always ≥ 6.0 (the
   detector's own emission floor) — a lower value appearing here would mean an
   unfiltered flag reached the notch, contradicting the co-gate (TC-005–010).

**Pass/fail criterion**: any invariant violated on any fixture → FAIL, independent of
whether that specific combination was covered by a named ground-truth test above.

---

## Traceability Table

| Acceptance Criterion | Test Case IDs |
|---|---|
| **AC1**: disabled stage never called, key absent from report | TC-038, TC-040, TC-042 |
| **AC2**: every invocation logged with before/after measurements | TC-013, TC-043 |
| **AC3**: `suno_dsp` import failure fails loudly when any flag on; no effect when all off | TC-040, TC-041 |
| **AC4**: bit-identical output across repeated runs (determinism) | TC-045 |
| **AC5**: no default flip without recorded Gate 1 clearance | TC-044 |
| **AC6**: final master meets standing targets across all flag combinations, regression attributable per stage | TC-050 |
| **AC7**: zero-flag / co-gate-failing case is a no-op (or empty-list invocation) | TC-005–TC-012 |
| **AC8**: frequency list sourced only from `ArtifactDetectionResult`, structurally enforced | TC-014–TC-017 |
| **AC9**: sub-frame input refused, not padded/bypassed | TC-018, TC-019 |
| **AC10**: OLA gain-risk closed by measured test before default-on | TC-001–TC-004 |
| **AC11**: `shape_transients` params are config-supplied, never SMEARED_TRANSIENT-derived | TC-028, TC-029 |
| **AC12**: report/log text never describes `shape_transients` as artifact repair | TC-030 |
| **AC13**: Gate 1 rules on gain law + hardcoded constants before default-on | TC-023–TC-027 (2f flutter, near-corner baseline, stereo link) |
| **AC14**: non-stereo input to `collapse_swish` checked before call, never relies on catching the C++ exception | TC-039 |
| **AC15**: BACKLOG/measured-behaviour discrepancy resolved and recorded before default cutoff chosen | TC-031, TC-032 |
| **AC16**: `collapse_swish` vs [5a]/[5b] interaction named at band granularity | TC-035, TC-036 |

---

## Coverage Checklist

| Category | Coverage |
|---|---|
| Happy path for each AC | TC-005, TC-013, TC-020, TC-023 (post-patch), TC-032, TC-043 |
| Boundary values at thresholds | TC-008 (confidence 0.79/0.80), TC-009 (prominence 9.9/10.0), TC-010 (co-gate equivalence at/below detector floor 6.0/5.0), TC-018/TC-019 (4095/4096 samples) |
| Idempotency | Not directly applicable — these are gated, discrete edits, not iterative corrections. Chain-level idempotency (re-running the whole pipeline on an already-mastered file) is out of this story's scope; covered, if at all, by STORY-001's test suite. |
| Bypass/disabled stage → bit-identical output | TC-038, TC-040, TC-042 |
| Mono input | TC-027, TC-039, TC-049 |
| Stereo input | All other tests |
| 44.1 kHz | All tests except TC-002/TC-048 |
| 48 kHz | TC-002, TC-048 |
| Silence / near-silence | TC-046 |
| Full-scale / already-clipping input | TC-052 (F-011, −0.3 dBFS sample peak, each stage individually — closed gap, see Revision history) |
| Very quiet input | F-002 (−20 dBFS) exercised in TC-003. Not a separate dedicated case beyond that; treated as a deliberate non-gap — the −20 dBFS case already probes low-level behaviour for the one function (repair_whistles) where a level-dependent artifact (OLA modulation) is actually a live concern; `shape_transients`/`collapse_swish` have no documented level-dependent failure mode that a lower amplitude would newly expose. |
| DC offset | F-001's constant-0.5 signal is DC by construction (TC-001/TC-002), covering `repair_whistles`. Not separately tested for `shape_transients`/`collapse_swish`; treated as a deliberate non-gap — requirements.md does not name DC offset as a concern for those two functions (unlike STORY-007's detectors, which explicitly derive a DC-offset case), and `collapse_swish`'s M/S transform (`mid=(L+R)/2`) passes a constant DC offset through both mid and side deterministically with no division or windowing involved. |
| Very short file (< one analysis window) | TC-018, TC-019 (repair_whistles' 4096-sample frame) |
| Corrupt / truncated file | Not applicable — these stages consume an in-flight `AudioBuffer`/array, not a file path (requirements.md "Input/output assumptions"). |
| Unsupported format | Not applicable, same reason. |
| Missing file | Not applicable, same reason. |
| Wrong channel count than expected | TC-039 (collapse_swish, 1/3-channel), TC-027/TC-049 (shape_transients/repair_whistles, mono) |
| Units explicit (LUFS vs dBFS vs dBTP vs prominence_db) | TC-050 states LUFS/dBTP/DR explicitly; TC-005–TC-013 use `prominence_db`/`confidence_score` as STORY-007-defined, never conflated with level. |
| Sample peak vs true peak | Not directly exercised by this story's new stages (no true-peak-specific processing here — true peak is measured downstream at [6] Loudness/Limiting, out of this story's scope); AC6's ≤ −1.0 dBTP check in TC-050 relies on the existing true-peak measurement from STORY-001/002. TC-051/TC-052 explicitly work in **sample** peak, stated as such, to avoid conflating the two. |
| Negative control per stage | TC-004 (method-validation control), TC-012 (repair_whistles no-op), TC-025 note / TC-024 (shape_transients regression-guard at 440 Hz), TC-037/TC-038 (collapse_swish not auto-triggered) |
| Sanity invariants (physically impossible output) | TC-051 |
| Structural/type-level contract tests | TC-014–TC-017, TC-028, TC-029, TC-044 |
| Performance / non-functional | No test included — requirements.md explicitly defers this ("no measured baseline exists yet... recommend a baseline measurement be taken during Gate 1/implementation") and does not set an SLA. Flagged as an open item, matching STORY-007's OQ-6 pattern, not invented here. |

---

## Notes on scope and what remains genuinely open

- Several tests in Groups 1, 6, and parts of 5/9 are expected to **fail today** by
  architecture's own account (§14). This is intentional and documented via the
  `[BLOCKED-ON: ...]` tags — do not close these as defects until the corresponding
  C++ patch lands; do not "fix" them by loosening the stated tolerances (H4).
- `prominence_floor_db` (OQ-A), `cutoff_freq_hz` (OQ-B), the final sidechain cutoff
  within 150–250 Hz (OQ-C), the final slow-envelope constant within 100–500 ms (OQ-D),
  and `attack_boost_db`/`sustain_cut_db` (OQ-E) are all still open numeric decisions per
  architecture §14/§15. This document uses explicit test-fixture values for each,
  clearly labelled as not project defaults, so the test suite is runnable without
  waiting for those decisions — but no test case here should be read as recommending
  those values for production config.
- TC-036's exact per-band classifications depend on `pipeline.py`'s actual [5a] band
  definitions, which this document (per H9) does not read — the test structure is
  specified, the concrete expected classifications are not.
