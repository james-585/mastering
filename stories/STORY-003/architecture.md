# STORY-003 Architecture: Ground-Truth Test Harness

## 0. Scope and how this document is organized

This story does not add a processing pipeline stage. It adds a
verification layer on top of the 11 existing measurement functions
(STORY-001's six, STORY-002's five), fixes two named defects
(DEF-201, DEF-203) inside that layer, and adds a small, always-on
sanity-check layer to production code. Because of that, this document
is organized differently from a typical DSP-pipeline architecture: it
covers (1) where ground-truth signal generators live and how they're
reused, (2) the DEF-201/DEF-203 fix designs, (3) the sanity-assertion
design and its schema/report consequences, (4) per-measurement
ground-truth test specifications, and (5) testability/runtime
mechanics — in that order, since the fixes depend on the generator
design and the generator design depends on what already exists.

**Everything below was checked against the shipped code on disk**
(`stories/STORY-001/implementation/suno_mastering/analysis/*.py`,
`reference_analysis/config.py`, `tests/ref_helpers.py`,
`tests/conftest.py`), not assumed from requirements.md's own
description of it.

**v3 note (this revision, current)**: DEF-201 was reopened after a
real reference-set report showed the v2 fix (`hf_rolloff_threshold_db=20.0`)
still tracks programme material, not a fixed file property (Leftfield,
a ~1995 CD master, reported 8170 Hz; all five real tracks reported
`stable=False`). qa-automation-engineer's follow-up wiring-gap
investigation (`stories/STORY-002/defects.md`, "DEF-201 wiring-gap
investigation" entry) empirically confirmed, by pinning the per-segment
reference anchor to a single whole-track value, that the instability is
caused by re-anchoring the threshold per segment (Hypothesis 3), but —
critically — **the reported 8170 Hz figure does not change even once the
anchor is stabilized**, and the reported crossing moves ~1000-1400 Hz
per dB of anchor perturbation, which is the signature of a threshold
crossing a shallow tilt, not a real filter edge. §2.8-§2.13 replace
threshold-crossing with sustained-slope-plus-floor cliff detection as
the PRIMARY mechanism, superseding §2.2-§2.7's "keep the threshold"
conclusion. DEF-203 was also reopened; §3.5-§3.6 independently
re-derive the mono-sum floors (generalized to unequal channel power)
and resolve a genuine metric-naming/sign-convention defect
(`excess_cancellation_db` renamed to `headroom_db`, plus a new
broadband cancellation flag mirroring the existing per-band one) — the
underlying `-6.0206 dB`/`-3.0103 dB` constants are confirmed correct a
third time, unchanged. See §12 for full revision history.

---

## 1. Where ground-truth signal generators live

**Decision: extend the two shared helper modules that already exist**
(`tests/conftest.py` for STORY-001-domain helpers, `tests/ref_helpers.py`
for STORY-002-domain helpers) — do not create a third shared module.
`ref_helpers.py`'s own module docstring states the reason for the
split explicitly: keep zero risk of an accidental STORY-001 regression
from touching `conftest.py`.

### 1.1 What already exists — reuse, do not reinvent

| Helper | Location | Reuse for |
|---|---|---|
| `sine`, `cosine`, `to_stereo`, `dbfs_to_amplitude`, `rms_amplitude_for_dbfs_sine` | `conftest.py` | AC4a/4b, true-peak fixture base |
| `lowpassed_white_noise(sr, duration_s, cutoff_hz, seed, amplitude, order=8)` — Butterworth, finite slope | `ref_helpers.py` | **NOT the right fixture for HF-threshold ground truth — see §2.5.** Useful as a "gently-filtered, not-a-cliff" cross-check fixture only |
| `pink_noise_mono`/`pink_noise_stereo` — 1/f-shaped via FFT scaling | `ref_helpers.py` | AC6d (the literal DEF-201 regression fixture). **v3 note**: stationary — does not exercise the per-segment non-stationarity failure mode; see §2.12 |
| `independent_noise_stereo(sr, duration_s, sigma, seed)` — rho=0 stereo | `ref_helpers.py` | AC9c, AC9d (rho=0 branch) |
| `calibrated_tone_mono(sr, duration_s, dbfs_rms, freq)` | `ref_helpers.py` | AC7b (LRA two-level) |
| `ref_config(**overrides)` = `dataclasses.replace(ReferenceAnalysisConfig(), **overrides)` | `ref_helpers.py` | the mechanism for the `hf_min_duration_s` override (§1.3) |

Three tests already partially satisfy AC9d: `test_tc311` (rho=+1),
`test_tc313` (rho=0 — **field renamed to `headroom_db` in v3, §3.6;
needs updating**), `test_tc312` (anti-phase-with-noise-floor).

### 1.2 What must be added (net new)

**`ref_helpers.py` additions:**
- `brickwall_lowpass_noise_mono(sr, duration_s, cutoff_hz, seed, amplitude)`
  — genuine brickwall (FFT-domain rectangular lowpass): FFT white
  noise, zero every bin strictly above `cutoff_hz`, inverse FFT. Unlike
  `lowpassed_white_noise`, its threshold-crossing frequency is
  independent of threshold depth (§2.5).
- `brickwall_lowpass_noise_with_drift(sr, first_s, second_s, cutoff1_hz, cutoff2_hz, seed, amplitude)`
  — concatenation of two brickwall segments at different cutoffs.
- `white_noise_mono(sr, duration_s, seed, amplitude)` — plain full-band
  white noise.
- `band_limited_noise_mono(sr, duration_s, band_hz, seed, amplitude, floor_amplitude)`
  — bandpassed noise + an independent low-amplitude broadband floor
  (required so every non-target band's power stays off the
  `_MIN_POWER=1e-20` floor).
- `inverted_stereo(mono) -> np.ndarray` — `np.stack([mono, -mono], axis=1)`.

**`conftest.py` addition:**
- `nyquist_adjacent_sine(sr, duration_s, amplitude=1.0)` —
  `amplitude * np.sin(np.pi * np.arange(n) / 2 + np.pi / 4)`, the
  exact inter-sample-overshoot construction for true-peak ground truth.

### 1.3 Resolving the 2-5 s NFR against real per-function duration floors

Three functions have parameters that make a naive 2-5 s signal
silently exercise a fallback branch instead of the real algorithm:

| Function | Parameter | Required minimum |
|---|---|---|
| `measure_hf_extension` | `hf_min_duration_s=30.0` default | Override via `ref_config(hf_min_duration_s=2.0)`, keep signal at 2-5 s |
| `measure_dynamic_range` | `n_blocks>=5` needed for the exclusion logic to run | ≥15 s (`dr_block_seconds=3.0`) |
| `measure_loudness_range` | needs several full windows per level cluster | AC7a ≥5 s; AC7b/7c reuse DEF-107's calibrated 30 s + 30 s, 18 LU fixture |

This does not threaten AC12's 30 s suite budget — every operation here
is vectorized over sample count, not wall-clock duration; QA should
still measure `pytest -m ground_truth` wall time directly.

---

## 2. DEF-201 fix design

### 2.1 v1/v2 history, condensed (superseded — see §2.8)

`_segment_rolloff_hz` scanned PSD bins from Nyquist down to DC,
returning the highest frequency whose density stayed above
`ref_density_db - hf_rolloff_threshold_db`. The shipped v1 default
(`6.0`) crossed within the first octave or two above the reference band
on ordinary programme tilt (GusGus measured 1979 Hz). **v2** deepened
this to `20.0` — not an arbitrary pick but the midpoint of an
empirically validated `[18, 21] dB` window, established by sweeping
against synthetic brickwall/finite-floor/pink-noise fixtures AND this
project's real five-track set (full sweep tables and the Butterworth
asymptotic-attenuation math live in `stories/STORY-002/defects.md`'s
DEF-201 entry and are not reproduced here a second time). v2 also
migrated `test_tc304`/`test_tc305` from `lowpassed_white_noise` (a
finite-slope Butterworth filter, whose threshold-crossing frequency
moves when the threshold moves) onto the new true-brickwall generator.
v2's own §2.6/§2.7 explicitly flagged the `[18,21]` window as fragile
(a 4 dB window, each edge set by exactly one data point) and recorded a
slope-based/hybrid follow-up as "recommended, not required." **That
follow-up is now required — see §2.8.**

`hf_rolloff_threshold_db=20.0` and the (renamed, §2.10)
`hf_cliff_slope_db_per_octave=24.0` are **reused, not discarded**, by
the v3 design below, with their roles changed (§2.9/§2.10) — the
empirical validation work behind both numbers remains relevant.

### 2.8 REOPENED (v3): why threshold-crossing (at any depth) is structurally insufficient

**Evidence, from james's report review and qa-automation-engineer's
follow-up wiring-gap investigation (`stories/STORY-002/defects.md`,
both the reopened DEF-201 entry and the dedicated "DEF-201 wiring-gap
investigation" entry — read in full for this revision, not
re-summarized loosely)**:

1. All five real reference tracks report `stable=False` at the
   production default. A genuine cutoff is a fixed file property;
   universal instability across every track is the signature of a
   detector tracking programme material.
2. Leftfield (a ~1995 CD master) reports 8170 Hz — implausible for a
   commercial CD master.
3. **QA's isolation experiment is the decisive evidence**: pinning
   Leftfield's per-segment reference-band anchor to a single,
   whole-track-computed value collapses the per-segment spread from
   9160.4 Hz to 706.1 Hz (fixing the *instability*) — but the **median
   rolloff stays at 8170.2 Hz, unchanged**. Comparing each segment's
   own-anchor rolloff against its fixed-anchor rolloff gives an
   empirical sensitivity of **~1000-1400 Hz of reported "rolloff" per
   1 dB of reference-anchor shift** near the crossing region. A
   genuine brickwall/codec cliff is, by construction, threshold-depth-
   independent (TC-020/021 move only a handful of Hz across a 6-40 dB
   sweep, per the same defects.md entry); Leftfield's reading moving by
   thousands of Hz for single-digit-dB anchor perturbations is direct,
   affirmative evidence there is no cliff at 8 kHz on this track — not
   merely an absence of evidence for one. **This rules out "just
   stabilize the anchor" as a sufficient fix**: a narrower patch that
   only computes the reference anchor once per track (instead of once
   per segment) would make `stable=True` while leaving the wrong
   8170 Hz figure unchanged, because the underlying defect is the
   detection *method* (an absolute-level crossing against a naturally
   declining spectrum), not merely where the anchor is computed from.

**This reverses §2.2/§2.7's "keep the threshold" conclusion.** That
conclusion rested on an averaging-depth objection to slope-based
detection at this story's fixture/segment lengths. §2.9 answers that
objection directly (whole-track PSD, band-averaged probes) rather than
ignoring it — the objection was about *how* to compute a slope
reliably, not about whether slope is the right thing to detect; §2.7's
own text already identified slope as the physically correct target
("a rate-of-change event... not a level event").

### 2.9 v3 redesign: sustained slope + floor cliff detection (primary mechanism)

**Two-stage design.** Stage 1 answers "does a genuine cliff exist at
all." Stage 2, only reached once Stage 1 confirms a cliff, answers
"exactly where" — and reuses v1/v2's own already-validated
scan-down-from-the-top localization logic, now correctly **gated**
rather than run unconditionally as the sole detector (Stage 2's
precision was never the bug; using it, ungated, as the existence test
itself was).

```python
def _probe_band_levels_db(freqs, psd, f_start, nyquist, probes_per_octave):
    """Log-spaced probe ladder from f_start to nyquist, ppo points per
    octave. Each probe's value is the MEAN density (_psd.band_mean_density,
    NOT a single Welch bin) over the fractional-octave band the probe
    represents -- [f*2**(-1/(2*ppo)), f*2**(1/(2*ppo))]. Band-averaging
    each probe, combined with running Stage 1 on the WHOLE-track PSD (not
    per-segment), is what answers Section 2.2's original averaging-depth
    objection to slope-as-primary-mechanism (Section 2.8)."""
    ratio = 2.0 ** (1.0 / probes_per_octave)
    half_step = 2.0 ** (1.0 / (2.0 * probes_per_octave))
    freqs_list = [f_start]
    while freqs_list[-1] * ratio <= nyquist:
        freqs_list.append(freqs_list[-1] * ratio)
    probe_freqs = np.array(freqs_list)
    probe_db = np.array([
        10.0 * np.log10(max(
            _psd.band_mean_density(freqs, psd, (f / half_step, f * half_step)),
            _MIN_DENSITY))
        for f in probe_freqs
    ])
    return probe_freqs, probe_db


def _cliff_exists(freqs, psd, ref_density_db, config):
    """Stage 1 -- existence gate. Slides a fixed-width
    (config.hf_cliff_min_span_octaves, default 1/3 octave) log-frequency
    window from the top of the reference band (config.freq_reference_band_hz[1],
    2000 Hz) toward Nyquist. A candidate window [f, f*2**min_span_octaves]
    is a confirmed cliff only if ALL THREE hold:

      (a) PASSBAND PRECONDITION: probe_db[i] within
          config.hf_cliff_passband_max_deviation_db (6.0 dB default) of
          ref_density_db -- the window must start from genuine,
          near-full-strength content. WITHOUT this precondition, a
          window entirely embedded inside an already-declined region
          (e.g. Leftfield-style: already 18 dB down by some frequency,
          then declining a further 8+ dB before settling) would satisfy
          (b)/(c) below without ever being a genuine "full-strength
          content falling off a cliff" -- this is Leftfield's own
          failure mode reproduced inside the new detector if omitted,
          confirmed necessary directly against QA's own 8170 Hz finding
          (a threshold-vs-tilt crossing, not a cliff, per Section 2.8).
      (b) SUSTAINED SLOPE: the two-point decline across the WHOLE
          window >= config.hf_cliff_slope_db_per_octave (24.0 default)
          dB/octave. At the default hf_cliff_min_span_octaves=1/3, this
          is a minimum total drop of 24.0*(1/3) = 8 dB across the
          window -- the number to reason about when tuning either
          default, since it is their product, not either alone.
      (c) FLOOR: from the window's END to Nyquist, at least
          config.hf_cliff_floor_min_fraction (0.8 default) of probes
          sit at or below (ref_density_db - config.hf_rolloff_threshold_db)
          -- rules out a transient notch that recovers. hf_rolloff_threshold_db's
          role changes from "primary crossing threshold" (v1/v2) to
          "floor depth"; the [18,21] dB validation is repurposed, not
          discarded.

    Returns (window_start_hz, window_end_hz) of the FIRST confirmed
    cliff, or None -- this IS the "no cliff -> NO CUTOFF" case, enforced
    structurally."""
    nyquist = float(freqs[-1])
    f_start = config.freq_reference_band_hz[1]
    ppo = config.hf_cliff_probes_per_octave
    window_ratio = 2.0 ** config.hf_cliff_min_span_octaves
    floor_level_db = ref_density_db - config.hf_rolloff_threshold_db

    probe_freqs, probe_db = _probe_band_levels_db(freqs, psd, f_start, nyquist, ppo)
    if probe_freqs.size < 2:
        return None

    for i, f in enumerate(probe_freqs):
        f_end = f * window_ratio
        if f_end > nyquist:
            break
        if probe_db[i] < ref_density_db - config.hf_cliff_passband_max_deviation_db:
            continue  # (a)
        j = int(np.argmin(np.abs(probe_freqs - f_end)))
        if j <= i:
            continue
        octaves = np.log2(probe_freqs[j] / probe_freqs[i])
        if octaves <= 0:
            continue
        slope_db_per_octave = (probe_db[i] - probe_db[j]) / octaves
        if slope_db_per_octave < config.hf_cliff_slope_db_per_octave:
            continue  # (b)
        remaining = probe_db[j:]
        fraction_at_floor = (1.0 if remaining.size == 0
                              else float(np.mean(remaining <= floor_level_db)))
        if fraction_at_floor >= config.hf_cliff_floor_min_fraction:
            return float(probe_freqs[i]), float(probe_freqs[j])  # (c)
        # sustained slope but no lasting floor -- a notch, keep scanning
    return None


def _localize_crossing_hz(freqs, levels_db, floor_level_db, lo_hz, hi_hz):
    """Stage 2. v1/v2's ORIGINAL scan-down-from-the-top logic,
    UNCHANGED, applied ONLY within the confirmed [lo_hz, hi_hz] window
    -- safe now because Stage 1 has already ruled out the false-cliff
    case this scan alone could not distinguish."""
    mask = (freqs >= lo_hz) & (freqs <= hi_hz)
    idx = np.nonzero(mask)[0]
    if idx.size == 0:
        return hi_hz
    for i in idx[::-1]:
        if levels_db[i] > floor_level_db:
            return float(freqs[i])
    return float(lo_hz)


def _segment_result(segment, sr, config):
    """Runs both stages on ONE PSD (whole-track OR per-segment --
    caller decides). Returns (rolloff_hz: float, cutoff_detected: bool).
    rolloff_hz is ALWAYS concrete once reached (Nyquist when
    cutoff_detected is False -- Section 2.11)."""
    freqs, psd = _psd.compute_psd(segment, sr)
    nyquist = float(freqs[-1])
    ref_density = _psd.band_mean_density(freqs, psd, config.freq_reference_band_hz)
    ref_density_db = 10.0 * np.log10(max(ref_density, _MIN_DENSITY))
    kernel = min(5, len(psd) if len(psd) % 2 == 1 else len(psd) - 1)
    kernel = max(1, kernel)
    smoothed = medfilt(psd, kernel_size=kernel) if kernel > 1 else psd
    levels_db = 10.0 * np.log10(np.maximum(smoothed, _MIN_DENSITY))

    window = _cliff_exists(freqs, psd, ref_density_db, config)
    if window is None:
        return nyquist, False
    lo_hz, hi_hz = window
    floor_level_db = ref_density_db - config.hf_rolloff_threshold_db
    return _localize_crossing_hz(freqs, levels_db, floor_level_db, lo_hz, hi_hz), True
```

**Top-level restructure — whole-track is authoritative, per-segment is
drift/stability-only**:

```python
def measure_hf_extension(audio, sr, config) -> HfExtensionResult:
    mono = _to_mono(audio)
    duration_s = mono.size / sr if sr else 0.0
    if duration_s < config.hf_min_duration_s:
        return HfExtensionResult(rolloff_hz=None, stable=False,
                                  insufficient_duration=True, cutoff_detected=False)

    active = extract_active_audio(mono, sr, block_ms=config.silence_block_ms,
                                   threshold_db=config.silence_gate_threshold_db)
    if active.size < 8:
        active = mono

    # Primary result: ONE existence+localization pass on the WHOLE
    # active signal. Fixes both reopened symptoms at once: instability
    # (no more per-segment median of independently-anchored crossings)
    # AND the threshold-vs-tilt confound (Section 2.8's own passband/
    # slope/floor gate, not a bare crossing).
    rolloff_hz, cutoff_detected = _segment_result(active, sr, config)

    # Per-segment pass: informational / drift-detection ONLY.
    n_segments = max(1, config.hf_stability_segment_count)
    seg_len = active.size // n_segments
    if seg_len < 8:
        n_segments = 1
        seg_len = active.size

    per_segment_rolloff_hz, per_segment_cutoff_detected = [], []
    for i in range(n_segments):
        start = i * seg_len
        end = active.size if i == n_segments - 1 else start + seg_len
        segment = active[start:end]
        if segment.size < 8:
            continue
        seg_rolloff, seg_detected = _segment_result(segment, sr, config)
        per_segment_rolloff_hz.append(seg_rolloff)
        per_segment_cutoff_detected.append(seg_detected)

    stable = _compute_stability(cutoff_detected, rolloff_hz,
                                 per_segment_cutoff_detected, per_segment_rolloff_hz, config)

    # suspected_transcode simplifies: slope adequacy is now a
    # PRECONDITION of cutoff_detected=True, so _transcode_slope_check's
    # separate recomputation is retired (Section 2.10).
    suspected_transcode, reason = False, None
    if cutoff_detected and stable:
        in_suspect_band = any(lo <= rolloff_hz <= hi for lo, hi in config.transcode_suspect_bands_hz)
        if in_suspect_band:
            suspected_transcode = True
            reason = (f"rolloff at {rolloff_hz:.0f} Hz falls within an encoder-typical cutoff "
                       f"band and is a confirmed cliff (sustained slope >= "
                       f"{config.hf_cliff_slope_db_per_octave:.1f} dB/octave followed by a floor), "
                       f"stable across segments -- suspected lossy-source transcode.")

    return HfExtensionResult(
        rolloff_hz=rolloff_hz, cutoff_detected=cutoff_detected, stable=stable,
        per_segment_rolloff_hz=per_segment_rolloff_hz,
        per_segment_cutoff_detected=per_segment_cutoff_detected,
        insufficient_duration=False, suspected_transcode=suspected_transcode,
        suspected_transcode_reason=reason)


def _compute_stability(cutoff_detected, rolloff_hz, per_segment_cutoff_detected,
                        per_segment_rolloff_hz, config) -> bool:
    """Stability is agreement, across per-segment INDEPENDENT
    cliff-confirmations (same Stage 1+2 test), with the whole-track
    result -- NOT the spread of raw per-segment threshold crossings."""
    n_evaluated = len(per_segment_cutoff_detected)
    if n_evaluated == 0:
        return True
    n_confirming = sum(per_segment_cutoff_detected)
    if not cutoff_detected:
        # Only flip to unstable if a genuine MAJORITY of segments
        # independently disagree.
        return n_confirming <= n_evaluated / 2.0
    confirming_freqs = [f for f, d in zip(per_segment_rolloff_hz, per_segment_cutoff_detected) if d]
    if not confirming_freqs:
        # No segment corroborates the whole-track cliff -- treat as
        # unstable. DELIBERATE COUPLING, stated explicitly: since
        # suspected_transcode above also requires stable=True, this
        # means a marginal per-segment corroboration failure suppresses
        # transcode flagging even in a suspect band -- a conservative
        # trade (a possible missed flag, never a flag off one
        # uncorroborated estimate).
        return False
    spread = max(confirming_freqs) - min(confirming_freqs)
    return spread <= config.hf_stability_tolerance_hz
```

### 2.10 v3 config changes

| Field | Change | Default | Role |
|---|---|---|---|
| `transcode_suspect_slope_db_per_octave` | **RENAMED** → `hf_cliff_slope_db_per_octave` | `24.0` (reused — DEF-201 reopened's own literal suggestion) | Primary Stage 1 slope criterion (was: secondary corroborator only) |
| `hf_rolloff_threshold_db` | reused, role changed, no rename | `20.0` (reused) | Stage 1 floor-depth + Stage 2 localization depth (was: sole primary crossing threshold) |
| `hf_cliff_min_span_octaves` | **NEW** | `1/3` | Stage 1 window width. Product with the slope default = 8 dB minimum total drop |
| `hf_cliff_floor_min_fraction` | **NEW** | `0.8` | Stage 1 floor-confirmation fraction (tolerates up to 20% of remaining spectrum above the floor) |
| `hf_cliff_probes_per_octave` | **NEW** | `48` | Stage 1 probe-ladder resolution (step ≈217 Hz at 15 kHz, comfortably under the existing 500 Hz test tolerance) |
| `hf_cliff_passband_max_deviation_db` | **NEW** | `6.0` | Stage 1 passband precondition |
| `_transcode_slope_check` (function) | **DELETED** | — | Superseded — its slope computation is now Stage 1's own precondition (b) |

**Provisional-vs-derived, stated explicitly**: `hf_cliff_slope_db_per_octave=24.0`
and `hf_rolloff_threshold_db=20.0` are reused, previously-validated
values. `hf_cliff_min_span_octaves`, `hf_cliff_floor_min_fraction`,
`hf_cliff_probes_per_octave`, `hf_cliff_passband_max_deviation_db` are
this pass's own provisional judgment calls, reasoned inline above but
**not empirically validated by this pass, since this document cannot
execute code** — flagged in §9/§10, concrete QA ask in §2.13.

`report/reference_builder.py::config_summary()` line 66 currently reads
`config.transcode_suspect_slope_db_per_octave` — update to the renamed
field; recommend also adding the four new fields for completeness.

### 2.11 v3 return-contract changes (`HfExtensionResult`)

```python
@dataclass
class HfExtensionResult:
    rolloff_hz: Optional[float]         # None ONLY when insufficient_duration=True.
                                          # Otherwise ALWAYS concrete: the localized
                                          # cliff frequency (cutoff_detected=True) or
                                          # Nyquist (sr/2, cutoff_detected=False --
                                          # resolves requirements.md Open Question 5).
    cutoff_detected: bool                # NEW. True iff Stage 1 confirmed a genuine
                                          # cliff on the WHOLE active signal.
    stable: bool                         # REDEFINED: agreement across per-segment
                                          # INDEPENDENT cliff-confirmations with the
                                          # whole-track result.
    per_segment_rolloff_hz: List[float] = field(default_factory=list)
    per_segment_cutoff_detected: List[bool] = field(default_factory=list)  # NEW
    insufficient_duration: bool = False
    suspected_transcode: bool = False
    suspected_transcode_reason: Optional[str] = None
```

| `insufficient_duration` | `cutoff_detected` | `rolloff_hz` |
|---|---|---|
| `True` | `False` | `None` |
| `False` | `False` | Nyquist (`sr/2`) |
| `False` | `True` | Stage-2-localized cliff frequency |

**Downstream consumers**: `check_hf_rolloff_vs_air_band` (`analysis/sanity.py`)
already only fires on `rolloff_hz < 5000.0`, which Nyquist can never
satisfy — correct without modification (§2.13 recommends an optional
defensive tightening only). `pipeline.py`'s `suspected_transcode`/`_reason`
wiring is unchanged in shape. `report/reference_render.py` does not
currently render `cutoff_detected` — recommend (not required) adding
it alongside the rendered rolloff value for transparency.

**Schema**: both new fields are additive to `HfExtensionResult` —
combines with DEF-203's schema change (§3.6) into one bump, `"1.2"` →
`"1.3"`.

### 2.12 v3 wiring-gap investigation — now empirically answered by QA, summarized here

**Full investigation, with reproduction numbers, lives in
`stories/STORY-002/defects.md`'s "DEF-201 wiring-gap investigation"
entry — not re-derived here, only summarized and connected to the
design decisions above.** Three candidate causes were checked directly
against the shipped code (no modifications):

1. **`extract_active_audio` silence-gating** — checked, NOT the
   driver. Removes a similar, small fraction (93.3% synthetic vs. 97.9%
   real survives) in both cases; not differential.
2. **Segmentation reducing Welch averages on real material** — checked,
   REFUTED, and in the opposite direction than hypothesized: real
   segments (61.44 s at the production default) get ~89 averaged Welch
   windows; the 3 s ground-truth fixture's segments (0.56 s) get only
   ~2. Real material has MORE per-segment averaging depth, not less.
3. **`freq_reference_band_hz` anchoring, recomputed independently per
   segment** — CONFIRMED as the mechanical driver of the *instability*
   specifically. On stationary pink noise this is harmless (anchor
   spread 0.37 dB across segments); on real, dynamically-arranged music
   the reference band's own energy genuinely varies between different
   61 s stretches (Leftfield: 8.22 dB anchor spread, roughly half a
   level artifact from a quieter intro segment, half genuine
   spectral-balance variation) — pinning the anchor to one whole-track
   value collapses the reported spread from 9160.4 Hz to 706.1 Hz.

**The critical second half of QA's finding — why this is a detection-
method defect, not merely an anchor-stability defect**: with the anchor
pinned, Leftfield's median rolloff is STILL 8170.2 Hz, unchanged. A
fix that only stabilizes the anchor (compute it once per track instead
of once per segment) would achieve `stable=True` while leaving the
implausible 8170 Hz figure untouched. §2.9's redesign fixes both
findings via the same mechanism: the whole-track pass (single
reference anchor, computed once) removes the instability, and the
passband+slope+floor gate (not a bare level crossing) removes the
threshold-vs-tilt confound that produces the wrong number in the first
place — confirmed directly by QA's own sensitivity measurement (~1000-
1400 Hz of reported rolloff per dB of anchor perturbation, the
signature of a tilt crossing a threshold, not a cliff).

**Why `test_tc024_pink_noise_no_cutoff` did not catch this**: pink
noise is stationary — with a fixed spectral character across its whole
duration, "anchor computed once per track" and "anchor recomputed per
segment" are numerically equivalent for this fixture, so it cannot
expose Hypothesis 3's mechanism, and its gentle tilt does not reach a
20 dB-relative crossing until near Nyquist, so it cannot expose the
threshold-vs-tilt confound either. **QA flags a genuine test-cases.md
coverage gap** (not fixed by this architecture pass, routed to
test-case-writer): no existing fixture combines a realistic, declining-
but-not-infinite tilt WITH genuine per-segment non-stationarity — this
is the missing negative control that would have caught both symptoms
before they reached the real reference set. QA also flags that every
HF-extension ground-truth fixture is built at 44100 Hz while all five
real reference tracks are 48000 Hz — not shown to be causal here, but a
real, unexercised regime (differing Nyquist, differing Welch-cap
crossover duration, differing effective medfilt smoothing bandwidth in
Hz) worth a dedicated fixture in the same test-case-writer pass.

### 2.13 v3 blast-radius / migration notes — predictions, not assertions

**This pass cannot execute code. Every claim below is a reasoned
prediction with a concrete verification ask — do not treat as confirmed
until run.**

- **TC-020/TC-021 (brickwall)**: predicted to still pass — flat
  passband trivially satisfies the passband precondition; the
  transition to exact zero trivially satisfies slope+floor.
- **TC-022/TC-024 (white/pink noise)**: predicted to still pass, via a
  DIFFERENT mechanism than v1/v2 (Nyquist placeholder from
  `cutoff_detected=False`, not a crossing landing near Nyquist by
  construction) — the existing `rolloff_hz >= 0.9*(sr/2)` assertion is
  satisfied either way, so **no re-fixture needed for these two,
  only re-confirmation.**
- **TC-023 (finite floor)**: predicted to still pass — 27 dB down
  comfortably exceeds both the 8 dB slope-window minimum and the 20 dB
  floor-depth criterion.
- **TC-025 (drift)**: predicted to still pass `stable is False`, via
  the redesigned mechanism (whole-track finds ~15000 Hz since content
  only fully vanishes above 15 kHz everywhere in the file; second-half
  segments independently confirm ~8000 Hz, a genuine large
  disagreement).
- **TC-020's `stable is True`**: reasoned to hold (every segment of a
  true brickwall has literally zero energy above cutoff, trivially
  satisfying every criterion regardless of averaging depth) but **not
  confirmed by this pass — required QA ask.**
- **Real five-track set**: Leftfield is **expected** to report
  `cutoff_detected=False`/Nyquist. **GusGus's outcome is genuinely
  unknown** (may have a real lossy-sourced/generation-limited cliff at
  some frequency, may not) — the v2 fix's 12065.9 Hz figure was itself
  a threshold-vs-tilt symptom and should not be treated as a prediction
  for v3. **Required QA ask**: re-run the real five-track set, record
  per track `rolloff_hz`/`cutoff_detected`/`stable`/
  `per_segment_cutoff_detected`/`suspected_transcode`, cross-check
  against `check_hf_rolloff_vs_air_band`, and record in
  `stories/STORY-002/defects.md`'s DEF-201 entry before closing a
  second time.

**Other required re-verification**: re-run `test_tc304`/`test_tc305`/
`test_tc307`/`test_tc308` (predicted unaffected, true brickwalls); grep
`tests/` for `transcode_suspect_slope_db_per_octave`/
`_transcode_slope_check` and update every hit; update
`config_summary()`'s renamed key; full `test_ref_*.py`/`test_ac*.py`/
`test_ground_truth_*.py` regression re-run.

---

## 3. DEF-203 — derivation, and resolution

### 3.1 The derivation (equal-power special case; see §3.5 for the general v3 re-derivation)

Let L, R be zero-mean, equal-power (`Var(L)=Var(R)=σ²`) stereo channels
with correlation ρ. `mono_sum=(L+R)/2`, so `Var(mono_sum) = σ²(1+ρ)/2`.

**Broadband `level_change_db`**: both `stereo_lufs`/`mono_lufs` come
from `measure_integrated_lufs`, BS.1770's channel-**summed** convention:
`level_change_db = 10·log10((1+ρ)/4)`.

**Per-band `delta_db`**: denominator is the per-channel-**mean** band
power (`(P_L+P_R)/2`), numerator is `Var(mono_sum)`:
`delta_db = 10·log10((1+ρ)/2)`.

| ρ | `level_change_db` (broadband) | `delta_db` (per-band) |
|---|---|---|
| +1 | `-3.0103 dB` | `0.0000 dB` |
| 0 | `-6.0206 dB` | `-3.0103 dB` |
| -1 | `-inf` | `-inf` |

**Confirms the shipped constants (`_BROADBAND_DECORRELATED_FLOOR_DB=-6.0206`,
`_PERBAND_DECORRELATED_FLOOR_DB=-3.0103`) are already correct** — the
same conclusion DEF-101/DEF-104 reached, matching DEF-101's own
empirical measurement (`-6.0111` measured vs. `-6.0206` predicted,
~0.01 dB gap = finite-sample noise).

### 3.2 Why DEF-203's original report was wrong, quantified

DEF-203 stated "-3.01 dB is correct" without specifying which formula,
treating `-6.02`/`-3.01` as competing answers to the same question —
they are the correct ρ=0 floor for two *different* fields. DEF-203's
own measured evidence (-3.47 to -4.03 dB across five references)
back-solves to `ρ ≈ 0.58-0.80` (`ρ = 4·10^(level_change_db/10)-1`),
squarely inside "moderately-high inter-channel correlation for
center-heavy commercial mixes." **v3 caveat**: this back-solve assumes
near-equal L/R power — §3.5 shows it is exact only under that
assumption.

### 3.3 Tolerance basis

Finite-sample correlation error `O(1/√N)`; at 3-5 s/44.1kHz ≈0.003 in
ρ ≈0.013 dB noise. **Broadband: ±0.1 dB. Per-band: ±1.0 dB** (Welch/CSD
band-power estimates have materially more variance than the full-signal
time-domain LUFS computation).

### 3.4 AC6 branch

The constant was already correct — **no code fix required for the
constant** (§3.6 identifies a genuine, different defect in the same
area). Ground-truth test still added (§7.5), becomes the
derivation-of-record. AC6's failing-test-first requirement applies to
**DEF-201 only** — a deliberate, documented exception for DEF-203's
constant.

### 3.5 REOPENED (v3): independent re-derivation, generalized to unequal channel power

**Re-derived from scratch per the reopened instruction, deliberately
generalized beyond §3.1's equal-power assumption** (an unequal-power
fixture is exactly the kind of case that could produce a fourth,
superficially different "bug" report against the same correct code).

Let `Var(L)=σ_L²`, `Var(R)=σ_R²` (not assumed equal), `ρ=Cov(L,R)/(σ_Lσ_R)`.
`Var(mono_sum) = (σ_L²+σ_R²+2ρσ_Lσ_R)/4`.

**Broadband**:
```
level_change_db = 10·log10(Var(mono_sum)/(σ_L²+σ_R²))
                 = 10·log10((1+kρ)/4),  k = 2σ_Lσ_R/(σ_L²+σ_R²)
```
`k≤1` by AM-GM, `k=1` iff `σ_L=σ_R`. **ρ=0 floor = -6.0206 dB regardless
of k** (`kρ=0` for any `k` when `ρ=0`).

`headroom_db = level_change_db - (-6.0206) = 10·log10(1+kρ)`.

**Per-band**, same construction with `k_band = 2√(P_L·P_R)/(P_L+P_R)`:
`delta_db = 10·log10((1+k_band·ρ_band)/2)`; **ρ_band=0 floor = -3.0103 dB
regardless of k_band**; `excess_delta_db = 10·log10(1+k_band·ρ_band)`.

**Key finding, stronger than §3.1**: the broadband and per-band excess
metrics are algebraically **identical in form** —
`10·log10(1+effective correlation)` — for ANY channel power balance,
collapsing to the literal `10·log10(1+ρ)` only when `k=1`/`k_band=1`
exactly. Both ρ=0 floors are exact regardless of imbalance: **the
shipped constants were never wrong, at any channel balance.**

**Cross-check against the reopened report's own quoted range**
("1.995-2.548 dB... across all five references"): back-solving under
`k≈1`: `10·log10(1+ρ)=1.995` → `ρ≈0.583`; `=2.548` → `ρ≈0.798` —
almost exactly the `ρ≈0.58-0.80` range §3.2 independently back-solved
from different quoted figures. Two independently-quoted five-track
figure sets, through two related-but-different formulas, converge on
the same range — the strongest evidence in this document that the
"narrow spread" is explained by the reference material's own
consistent mix character, not a wrong constant.

**Caveat, stated precisely**: `stereo_phase.overall_correlation` reads
the TRUE `ρ`, not `kρ` — the back-solve cross-check is exact only when
`k≈1` (near-equal channel power); for genuinely imbalanced material a
discrepancy would not by itself indicate a bug.

**Conclusion (third confirmation)**: the shipped `-6.0206 dB`/`-3.0103 dB`
constants are correct. This was never the actual defect — §3.6
identifies what is.

### 3.6 REOPENED (v3): metric semantics — the actual defect, resolved

**Sign-convention analysis.** From §3.5, `headroom_db (renamed below)
= 10·log10(1+kρ)`: ρ=+1 → `+3.0103` (best case); ρ=0 → `0.0000`; ρ=-1 →
`-inf`. **Higher is better.** A field literally named
`excess_cancellation_db` reading `+2.5 dB` reads, to any plain-English
reader, as "2.5 dB of excess (bad) cancellation present" — i.e. higher
should be worse. The actual metric is the opposite: higher is better.
**This directly explains why the same, now-three-times-confirmed-
correct number has been reported as a bug three times (DEF-101,
DEF-104, DEF-203).**

**Comparison with the per-band convention.** `BandCancellation.excess_delta_db`
has the identical sign polarity, but is materially less confusing
because it is never the primary reader-facing signal on its own —
`BandCancellation.cancellation` (a correctly-signed boolean) is. The
broadband field has **no equivalent flag** — a reader must interpret
the raw, backwards-feeling number directly. This asymmetry (per-band:
number + a correctly-signed boolean; broadband: number only) is the
structural root of the repeated misreads.

**Concrete fix, both halves of the reopened options adopted, not
either alone**:

1. **Rename**: `MonoSumResult.excess_cancellation_db` →
   `MonoSumResult.headroom_db`. Same formula, same sign, only the name
   changes (zero recomputation risk). **Deliberately NOT
   `mono_sum_headroom_db`**: `reference_analysis/aggregate.py` already
   prefixes the aggregate key with `"mono_sum."` — a field named
   `mono_sum_headroom_db` would double it (`"mono_sum.mono_sum_headroom_db"`);
   `headroom_db` gives the clean `"mono_sum.headroom_db"`. **A rename,
   not an added alias, is deliberate** — keeping the old, confusing
   name available does not fix the problem; this is the third report
   against the same field.
2. **Add a broadband flag, mirroring the per-band pattern exactly**:
   `MonoSumResult.broadband_cancellation: bool =
   headroom_db < config.mono_broadband_cancellation_headroom_db`.
   New config field `mono_broadband_cancellation_headroom_db: float = -3.0`.
   **Derived, not a fresh guess**: §3.5's closed form shows the
   existing per-band default (`mono_band_cancellation_excess_db=-3.0`)
   corresponds to flagging `k_band·ρ_band < -0.5` (solve
   `10·log10(1+x)=-3.0103` → `x=-0.5`). Since the broadband metric
   reduces to the identical closed form, reusing `-3.0` for the
   broadband flag means it flags the SAME physical criterion
   (`kρ<-0.5`) — not a coincidence, the mathematically consistent
   choice.

**Exact code changes required (instructions to python-developer, not
made by this document)**:

1. `analysis/mono_sum.py`: rename `excess_cancellation_db` →
   `headroom_db` (formula unchanged); add
   `broadband_cancellation = headroom_db < config.mono_broadband_cancellation_headroom_db`;
   update the `MonoSumResult(...)` construction; update module
   docstring pointing to this section.
2. `analysis/reference_types.py`: rename the field with a docstring
   stating the sign convention explicitly (positive=healthier/more
   headroom; 0=at the floor; negative=trending toward cancellation;
   very negative=severe cancellation — do NOT read positive as "X dB of
   cancellation present"). Add `broadband_cancellation: bool` mirroring
   `BandCancellation.cancellation`'s comment.
3. `reference_analysis/config.py`: add
   `mono_broadband_cancellation_headroom_db: float = -3.0` with the
   derivation comment (matches the per-band value not by coincidence —
   §3.5/§3.6).
4. `report/reference_render.py::_track_section()`: update the field
   reference and prose (drop "excess cancellation" framing, describe as
   headroom above the floor), add a line rendering
   `broadband_cancellation` when `True`, mirroring the existing
   per-band `cancelled_bands` line.
5. `reference_analysis/aggregate.py`: update the aggregate key from
   `"mono_sum.excess_cancellation_db"` to `"mono_sum.headroom_db"`.
6. `tests/ref_helpers.py::make_stub_measurements`: the
   `mono_sum_excess_cancellation_db` kwarg and its `MonoSumResult(...)`
   construction need updating — flagged, not edited here (tests/ is
   QA's/test-case-writer's territory).
7. Existing tests referencing the old name (`test_tc311`, `test_tc313`)
   need updating to `result.headroom_db` — flagged for QA.
8. `SCHEMA_VERSION`: this is a rename (not purely additive) plus one
   additive field — bump `"1.2"` → `"1.3"`, combined with §2.11's
   `HfExtensionResult` additions into a single version bump.

**Why this fix breadth, not less**: a threshold alone would give
readers a correctly-signed boolean but leave the confusingly-named raw
number in place for anyone reading it directly — the exact failure mode
that produced three prior reports (none of which involved a boolean;
there wasn't one). A rename alone would fix the raw number's
readability but not give parity with the per-band field's flag-based
interpretation aid. Both together brings the broadband field to full
structural parity with its per-band sibling.

---

## 4. Sanity assertions — production-code design (AC10)

### 4.1 Where they live and the hard rule governing them

New module: `analysis/sanity.py` (in the shared `analysis` package,
since both the mastering pipeline's core six and the reference-analysis
pipeline's eleven need it).

```python
@dataclass
class SanityWarning:
    metric: str       # e.g. "correlation_range", "integrated_lufs_range",
                       # "hf_rolloff_vs_air_band", "seven_band_adjacent_delta.high_air"
    severity: str      # "fail" | "warn" -- see hard rule below
    message: str       # human-readable, must include the actual offending value(s)
```

**Hard rule, stated explicitly because story.md's own language
("→ fail") could be misread as "raise an exception": a sanity check
NEVER raises and NEVER aborts a run.** "fail" severity means the
report shows an unambiguous FAIL marker next to a value a producer
should not trust; "warn" means a milder flag. Both are advisory
metadata attached to the result, exactly matching AC10's own text
("the result is flagged/rejected and the flag surfaces in the
human-readable report, not only in a test"). A false-positive sanity
check on genuine, unusual-but-real audio must degrade to "an odd
report annotation," never to a crashed pipeline run — this is the same
posture as this project's existing `suspected_transcode` flag.

### 4.2 The four checks, as pure functions (independently testable with plain values, not whole result objects)

**v2 correction, DEF-206 (`stories/STORY-002/defects.md`)**: the
`check_lufs_plausible` ceiling below was originally the literal `>
0.0` figure story.md states. python-developer implemented it exactly
as specified and then reported it back (correctly, per this role's
standing instruction not to make an undocumented design call
unilaterally): the `0.0` ceiling has no derivation behind it, unlike
the `-70` floor, and demonstrably false-positives on legitimate,
non-clipping audio — a dual-mono sine at amplitude `0.999` (genuinely
non-clipping) reads up to `+3.297 dB` at 8 kHz through the shipped,
unmodified `measure_all()`, purely as the correct, expected consequence
of two already-established, already-correct properties of this
codebase's own BS.1770 implementation stacking: K-weighting's
high-shelf boost, and BS.1770's channel-**summed** convention (the same
convention DEF-101/DEF-203 already establish as correct, not a bug).
DEF-206 offered three candidate resolutions: (a) derive a real ceiling
that accounts for the shelf-boost + channel-sum stacking, (b) drop the
ceiling check entirely and rely on `clipping.py`'s purpose-built
peak/inter-sample-peak detection, or (c) keep the literal `0.0` and
accept the false-positive rate as documented. **This revision takes
(a)**, not (b) or (c): (b) would remove a real, if narrow, protection
against a genuinely broken BS.1770 implementation; (c) is exactly
the "un-derived, over-tight ceiling gives false positives on real
audio" failure this project's own DEF-101 precedent already treats as
unacceptable for other checks.

**Derivation summary** (full worked algebra: three verified facts —
`_SUPPORTED_CHANNELS={1,2}` ingest bound; a non-clipping signal's max
mean-square power is exactly 1.0 (full-scale square wave); K-weighting's
total filter gain bounded across the entire frequency response,
combining the high-shelf's exact `Vh≈+4.0 dB` asymptote at Nyquist and
the RLB high-pass stage's own small, previously-uncounted `≈+0.047 dB`
excess gain at Nyquist) — combining to `LUFS_max ≈ +6.366 dB` at
44.1 kHz. **Shipped constant: `_LUFS_CEILING_DB = 6.5`** (padded above
the tightest computed bound, valid across supported sample rates, never
tightened below the derived figure; DEF-206's own measured worst case,
`+3.297 dB`, sits more than 3 dB inside this bound).

**Filter-identity caveat**: this derivation is against this codebase's
own `k_weight` reimplementation, not pyloudnorm's actual internal
filter (which is what `measure_integrated_lufs` actually uses) — a
partial empirical cross-check (~0.05 dB agreement at one anchor
frequency) supports but does not prove the two share the same bound;
flagged as an open QA verification item (confirm via `scipy.signal.freqz`
against `pyln.Meter._filters`, or calibrated-tone measurement near
Nyquist). **Second flagged gap**: the "no overshoot between DC and
Nyquist" property both filter stages rely on is asserted from
filter-design theory, not numerically swept by this document (cannot
execute code) — concrete QA ask: `scipy.signal.freqz` on a dense grid,
confirm `|H(f)|` never exceeds the Nyquist-value bound.

```python
_LUFS_CEILING_DB = 6.5
# Derived, not an arbitrary "matches 0 dBFS" guess -- see architecture.md
# Section 4.2 for the full derivation (DEF-206).

def check_correlation_range(correlation: float) -> Optional[SanityWarning]:
    # correlation_coefficient() can read fractionally over 1.0 for
    # identical channels as a pure floating-point artifact -- an epsilon
    # is required or this false-positives on the single MOST correct
    # possible input. math.isnan checked first (NaN compares False
    # against every bound below).
    if math.isnan(correlation):
        return SanityWarning("correlation_range", "fail", "correlation is NaN")
    if correlation < -1.0 - 1e-6 or correlation > 1.0 + 1e-6:
        return SanityWarning("correlation_range", "fail",
            f"correlation {correlation:.6f} outside [-1.0, 1.0]")
    return None

def check_lufs_plausible(lufs: float) -> Optional[SanityWarning]:
    # -inf is the documented, legitimate BS.1770-gated result for
    # silence/near-silence -- exempt exactly -inf.
    # A FINITE value below -70 is mathematically impossible for a
    # correct implementation (BS.1770's integrated loudness is a
    # power-mean of per-block mean-squares that individually passed the
    # -70 LUFS absolute gate; the arithmetic mean of positive values is
    # >= any individual value's own floor).
    # The upper bound, _LUFS_CEILING_DB, is a genuine derived hard
    # bound (DEF-206), not story.md's literal "> 0.0".
    if math.isnan(lufs):
        return SanityWarning("integrated_lufs_range", "fail", "LUFS is NaN")
    if lufs == float("-inf"):
        return None
    if lufs < -70.0 or lufs > _LUFS_CEILING_DB:
        return SanityWarning("integrated_lufs_range", "fail",
            f"integrated LUFS {lufs:.2f} outside (-70, {_LUFS_CEILING_DB}] and not -inf")
    return None

def check_hf_rolloff_vs_air_band(
    rolloff_hz: Optional[float], insufficient_duration: bool,
    air_relative_db: Optional[float],
) -> Optional[SanityWarning]:
    # Uses the SAME quantity already surfaced in every seven-band report
    # (SevenBandMeasurement.relative_db for band="air") -- see
    # architecture.md Section 2.4 for why no density-domain conversion
    # is performed here.
    if rolloff_hz is None or insufficient_duration or air_relative_db is None:
        return None
    if rolloff_hz < 5000.0 and air_relative_db > -40.0:
        return SanityWarning("hf_rolloff_vs_air_band", "fail",
            f"rolloff reported at {rolloff_hz:.0f} Hz but air band "
            f"(10-24 kHz) reads {air_relative_db:.1f} dB relative "
            f"(> -40 dB) -- physically inconsistent")
    return None

def check_seven_band_adjacent_deltas(
    bands: List[SevenBandMeasurement],
    threshold_db: float = 25.0, air_threshold_db: float = 40.0,
) -> List[SanityWarning]:
    # Two thresholds: the air band legitimately sits far below the
    # mid-band reference on ordinary commercial masters (~-20 dB on real
    # tracks with no HF problem) -- a single tight threshold would
    # false-positive on that ordinary case.
    out = []
    for a, b in zip(bands, bands[1:]):
        limit = air_threshold_db if "air" in (a.band, b.band) else threshold_db
        delta = abs(a.relative_db - b.relative_db)
        if delta > limit:
            out.append(SanityWarning(
                f"seven_band_adjacent_delta.{a.band}_{b.band}", "warn",
                f"{a.band} ({a.relative_db:.1f} dB) vs {b.band} "
                f"({b.relative_db:.1f} dB): {delta:.1f} dB gap exceeds "
                f"{limit:.1f} dB plausibility threshold"))
    return out
```

**`25.0`/`40.0` dB are stated here as an explicit, provisional
architectural decision** — a judgment call, not a derived invariant.
**Instruction to qa-automation-engineer**: report the observed maximum
adjacent-band delta for every pair, including air, across the real
five-track set, so these can be tightened/loosened without another
architecture round-trip.

### 4.3 Integration points — two call sites, one field name, no exceptions propagate

**`analysis/__init__.py::measure_all()`**: after computing
`integrated_lufs` and `stereo_phase`, run `check_lufs_plausible`/
`check_correlation_range`, collect non-`None` results, pass as
`Measurements(..., sanity_warnings=warnings)`. Covers both the
mastering and reference pipelines, since both call this same function.

**`reference_analysis/pipeline.py::analyze_track()`**: after `core`,
`hf_ext`, `seven_band` are computed, build
`air_relative_db = next((b.relative_db for b in seven_band.bands if b.band=="air"), None)`,
then `reference_warnings = list(core.sanity_warnings) +
[check_hf_rolloff_vs_air_band(...)] + check_seven_band_adjacent_deltas(...)`,
assign to `ReferenceMeasurements(..., sanity_warnings=reference_warnings)`.
**One field, one list, per result type.**

### 4.4 Schema/report consequences (AC13)

Two additive dataclass fields: `Measurements.sanity_warnings` and
`ReferenceMeasurements.sanity_warnings`, both
`List[SanityWarning] = field(default_factory=list)`.
`report/reference_builder.py::SCHEMA_VERSION`: bump `"1.1"` → `"1.2"`.

**Both renderers updated**: `report/reference_render.py::_track_section()`
renders each entry as a bullet, `[FAIL]`/`[WARN]` prefix by severity;
`report/render.py` (STORY-001's mastering renderer) gets a new block
for `before.sanity_warnings`/`after.sanity_warnings`, same convention.

**Verification required, not performed by this pass**: confirm
`build_reference_set_report()` actually threads `ReferenceMeasurements`
(or a field-for-field copy) rather than reconstructing its own output
shape — if not, the new field silently fails to reach either renderer
despite the dataclass change being correct. §7.6 accordingly requires a
rendered-output assertion, not just a population assertion.

**Golden-file risk**: check whether `test_ac10_reproducibility.py` (or
any file) does an exact stored-JSON/report-text diff before adding
`sanity_warnings` — if so, golden-file regeneration must be a
deliberate, reviewed step.

---

## 5. Ground-truth subset selection mechanism (open question 7)

**Decision: both a filename convention and a pytest marker**
(`test_ref_*.py` filename convention; `@pytest.mark.ground_truth`
marker).

- New files: `test_ground_truth_loudness.py`,
  `test_ground_truth_true_peak.py`, `test_ground_truth_hf_extension.py`,
  `test_ground_truth_dynamic_range.py`, `test_ground_truth_spectral_balance.py`,
  `test_ground_truth_stereo_width.py`, `test_ground_truth_sanity_assertions.py`,
  `test_ground_truth_kweight_oversample.py` — all under
  `stories/STORY-001/implementation/tests/`.
- Each file sets `pytestmark = pytest.mark.ground_truth` at module
  level. Register the marker in `pyproject.toml`.
- Timed invocation: `pytest -m ground_truth`. No isolation marker
  needed (unlike `test_tc150`/`test_tc381`) — sub-second per test.

---

## 6. AC6 sequencing protocol — ordered, owner-assigned

For **DEF-201** (the only defect requiring the failing-test-first
sequence, per §3.4): write the AC6d pink-noise test against unmodified
code, run and record the exact failure (test name, assertion, numeric
actual-vs-expected) in `stories/STORY-002/defects.md`'s DEF-201 entry;
make the config/logic change; re-run, confirm pass, record the post-fix
value; re-run the full HF-extension-adjacent regression surface plus
`test_ref_*.py`/`test_ac*.py`; mark DEF-201 Fixed with the exact
verification numbers, following the DEF-101/DEF-103 fix-notes format.
**v3 note**: this sequence was already completed once for the v1→v2
transition; it must be repeated for the v2→v3 (slope-based) transition,
using TC-024 (still the regression fixture) plus, if test-case-writer
adds it per §2.12's flagged gap, the new declining-tilt/non-stationary
negative control.

For **DEF-203**: no code change to the constant (§3.4). Derive (§3,
done in this document) → write the ground-truth test, passes
immediately → record the derivation in `stories/STORY-002/defects.md`'s
DEF-203 entry, closing the constant question **not-a-defect** a second
time, while the metric-semantics fix (§3.6) proceeds as an ordinary
code change (not gated by AC6's failing-test-first rule, since it is
not a defect in a computed value).

---

## 7. Per-measurement ground-truth test specifications

Brief per AC item — full derivations for HF extension and mono-sum are
in §2/§3.

### 7.1 Loudness (AC4a/4b)

**AC4a already satisfied** by `test_tc010` (mono, -20 dBFS RMS, 1 kHz,
±0.1 LU). **AC4b new**: two calibrated 1 kHz sines at an exact 6.000 dB
linear ratio (`amplitude2 = amplitude1 * 10**(6/20)`, not `2.0`),
assert the measured delta is `6.0 ± 0.1` LU.

### 7.2 True peak (AC5a/5b)

**Fixture: `nyquist_adjacent_sine(sr, duration_s=2.0)`** — `sr/4` Hz
with a 45° phase offset; every sample lands at exactly `±1/√2`
(-3.0103 dBFS sample peak) while the continuous-time true peak is `1.0`
(0 dBTP) exactly. AC5a: assert `dbtp` within 0.05 dB of 0.0, and
`dbtp - sample_peak_dbfs >= 2.9`. AC5b: assert `dbtp !=
pytest.approx(sample_peak_dbfs, abs=0.5)` — the direct regression guard.
Explicitly do not use a near-Nyquist frequency (FIR passband droop
would corrupt the expected value).

### 7.3 HF extension / rolloff (AC6a-e)

**Superseded/extended by §2.9-2.13 (v3) — the fixtures below are
unchanged, but the underlying detector and its `stable`/`cutoff_detected`
semantics are not.** Every test uses `ref_config(hf_min_duration_s=2.0)`.

- AC6a/6b: `brickwall_lowpass_noise_mono` at 15000/8000 Hz, assert
  `rolloff_hz ≈ cutoff_hz` (±500 Hz), `cutoff_detected is True`,
  `stable is True` (predicted, §2.13).
- AC6c: `white_noise_mono`, assert `rolloff_hz >= 0.9*(sr/2)`,
  `cutoff_detected is False`.
- AC6d — the literal DEF-201 regression fixture: `pink_noise_mono`,
  same assertion as AC6c.
- AC6e: `brickwall_lowpass_noise_with_drift` (15000→8000 Hz), assert
  `stable is False`, `rolloff_hz is not None`.

**Migration**: `test_tc304`/`test_tc305` re-fixtured onto
`brickwall_lowpass_noise_mono` (already done per the v2 pass);
unaffected by v3.

### 7.4 Spectral balance (AC8a/8b/8c)

**AC8a**: `band_limited_noise_mono(band_hz=(2000,5000), floor_amplitude=0.005)`
— assert `high_mid.relative_db` is the max among all seven bands and
exceeds every other by ≥20 dB (directional, not a fabricated precise
number). Not yet empirically verified the floor amplitude avoids the
`_MIN_POWER` floor (§10 risk).

**AC8b — exact, closed-form**: for flat white noise,
`relative_db(band) = 10·log10(width_band/width_ref)`, independent of
realization. Worked table (44.1 kHz): sub `-15.74`, low `-13.98`,
low_mid `-5.96`, mid `0.00`, high_mid `+3.01`, high `+5.23`, air
`+9.05`. Tolerance ±1.0 dB/band.

**AC8c — unit-test `_psd.band_power` directly**, not via a synthesized
tone (Welch leakage would spread a tone's energy across bins regardless
of the mask convention, proving nothing about which is implemented):
hand-built `freqs=[100,120,140]`, `psd=[1e-20,1.0,1e-20]` (all energy
at the shared low/low_mid boundary bin), assert both adjacent bands'
`band_power` reads > the noise floor — confirms the mask is inclusive
on both ends.

### 7.5 Stereo width / correlation / mono-sum (AC9a-9d)

AC9a (L=R): `correlation_coefficient ≈1.0`; `per_band_stereo_width <0.05`
every band. AC9b (L=-R): `correlation_coefficient ≈-1.0`;
`level_change_db`/`headroom_db` (renamed, §3.6) both `== float("-inf")`
exactly; `per_band_stereo_width` reads the same `≈0` as AC9a (magnitude-
based, phase-blind by design — not a bug if it doesn't distinguish the
two). AC9c (independent noise): `correlation_coefficient ≈0` (±0.05);
`per_band_stereo_width >=0.8` every band.

**AC9d / DEF-203 resolution**, extended with explicit per-band
`delta_db` assertions and the "which denominator" derivation comment:

```python
def test_ac9d_def203_monosum_floors_derived_from_first_principles():
    """architecture.md Section 3/3.5. level_change_db uses BS.1770's
    channel-SUMMED denominator; delta_db uses the per-band channel-MEAN
    denominator -- different formulas, different rho=0 floors."""
    sr = 44100
    result = measure_mono_sum(to_stereo(pink_noise_mono(sr, 5.0, seed=1)), sr, ref_config())
    assert result.level_change_db == pytest.approx(-3.0103, abs=0.1)
    for b in result.band_cancellations:
        assert b.delta_db == pytest.approx(0.0, abs=1.0)

    result = measure_mono_sum(independent_noise_stereo(sr, 8.0, sigma=0.05, seed=1), sr, ref_config())
    assert result.level_change_db == pytest.approx(-6.0206, abs=0.1)
    for b in result.band_cancellations:
        assert b.delta_db == pytest.approx(-3.0103, abs=1.0)

    result = measure_mono_sum(inverted_stereo(pink_noise_mono(sr, 5.0, seed=1)), sr, ref_config())
    assert result.level_change_db == float("-inf")
```

### 7.6 Sanity assertions (AC10)

**Two layers, not one**: (1) unit-level against the four pure functions
directly (plain values, e.g. `check_lufs_plausible(3.297)` returns
`None`, `check_lufs_plausible(6.6)` returns `fail`); (2) rendered-output
level, both renderers, using a fixture engineered to deliberately trip
a real check (e.g. `hf_rolloff_hz=2000.0` + air `relative_db` forced
above `-40.0`, the exact DEF-201-shaped scenario) — this is what
closes §4.4's flagged report-threading risk rather than assuming it
away. (3) integration-level: confirm `measure_all()`/`analyze_track()`
populate `sanity_warnings` end-to-end.

### 7.7 `k_weight`/`oversample` (recommended additional coverage)

`oversample`: apply to `nyquist_adjacent_sine(sr, 2.0)` at factor 8,
assert `max(abs(oversampled)) ≈1.0` (±0.05). `k_weight`: anchor
frequencies against BS.1770's published response — ≈0 dB at 1 kHz,
≈+4 dB on the high-shelf plateau (e.g. 10 kHz), measurable attenuation
at 20 Hz. Exact literature figures for the 20 Hz anchor are not pinned
down by this architecture — pull from BS.1770-4 Annex 1 directly or a
known-good independent implementation, not from this codebase's own
coefficients (would be circular).

---

## 8. Testability notes

- **Session-scoped fixtures** for signals reused byte-for-byte across
  multiple tests. **Mutation hazard**: pytest session scope returns the
  same array object to every requesting test — `audio.copy()` at the
  top of any test needing a modified variant.
- **Fixed seeds everywhere.**
- **Injectable config** (`ref_config(**overrides)`) is what makes the
  `hf_min_duration_s` override possible — an existing codebase property,
  not something this story adds.
- **Runtime**: §1.3's longer-than-2-5s fixtures do not threaten the 30 s
  budget (vectorized over sample count); QA should still measure
  `pytest -m ground_truth` wall time directly.

---

## 9. Assumptions pending BA confirmation

1. **`25.0`/`40.0` dB seven-band adjacent-delta thresholds (§4.2)** —
   provisional judgment call, not a BA-specified figure; recommend
   calibrating against the real five-track set.
2. **`hf_rolloff_threshold_db=20.0`, `hf_cliff_slope_db_per_octave=24.0`**
   (§2.9/§2.10) — reused, previously-validated values, now repurposed
   as the floor-depth and primary-slope criteria respectively, not
   fresh guesses.
3. **`hf_cliff_min_span_octaves=1/3`, `hf_cliff_floor_min_fraction=0.8`,
   `hf_cliff_probes_per_octave=48`, `hf_cliff_passband_max_deviation_db=6.0`**
   (§2.9/§2.10, new in v3) — this pass's own provisional judgment
   calls, reasoned inline but **not empirically validated, since this
   document cannot execute code** — flagged in §10, concrete QA ask in
   §2.13.
4. **`k_weight`/`oversample` ground-truth coverage (§7.7)** confirmed
   in-scope per requirements.md's own recommendation.
5. **`_LUFS_CEILING_DB=6.5` (§4.2, DEF-206)** — a derived hard bound,
   replacing story.md's literal "LUFS above 0 → fail," a deliberate,
   evidence-backed deviation from a BA-stated figure, not silent.
   Recommend BA confirmation.
6. **`mono_broadband_cancellation_headroom_db=-3.0` (§3.6, new in v3)**
   — NOT a guess; derived to match the physical criterion the existing
   per-band threshold already encodes (`kρ<-0.5`), via the closed-form
   equivalence established in §3.5.

## 10. Open architectural risks

1. AC8a/AC9c tolerances (§7.4/§7.5) are reasoned, not empirically
   verified against this codebase's actual Welch-averaging depth.
2. `band_limited_noise_mono`'s floor/bandpass amplitude split has not
   been run; confirm no band sits at the `1e-20` floor.
3. Exact literature K-weighting anchor figures (§7.7) not pinned down
   by this architecture.
4. **v3, new**: the entire §2.9 redesign (`_cliff_exists`,
   `_localize_crossing_hz`, `_compute_stability`, all four new config
   defaults) has NOT been executed against any fixture by this
   architecture pass — every prediction in §2.13 is reasoned, not
   confirmed. This is the single largest open risk in this revision.
5. **v3, new**: per-segment cliff confirmation at short (3-5 s/5-segment
   ground-truth-fixture) lengths — reasoned to work for true brickwalls
   (zero energy above cutoff trivially satisfies every criterion
   regardless of averaging depth) but not empirically confirmed.
6. **v3, new**: near-Nyquist cliffs (e.g. 19-20 kHz) have a much
   smaller remaining-spectrum sample for the floor-fraction
   confirmation (fewer probes between the cliff and Nyquist) — may need
   a relaxed `hf_cliff_floor_min_fraction` or a minimum-probe-count
   guard; not resolved, flagged for empirical check against
   `transcode_suspect_bands_hz`'s 18.5-20.5 kHz windows.
7. **v3, new**: `extract_active_audio`'s block-splice discontinuities
   (checked by QA and found NOT the primary driver, §2.12) remain a
   minor, unaddressed residual risk (raises broadband HF noise floor at
   splice points).
8. Whether `build_reference_set_report()` threads `ReferenceMeasurements`
   directly has not been confirmed (§4.4) — §7.6 requires a
   rendered-output assertion specifically because of this.
9. `_LUFS_CEILING_DB=6.5`'s derivation has two unresolved gaps: (a)
   derived against this codebase's own `k_weight`, not pyloudnorm's
   actual filter (partial empirical cross-check only); (b) "no
   overshoot between DC and Nyquist" asserted from filter theory, not
   numerically swept.
10. `check_hf_rolloff_vs_air_band`'s own fixed `5000 Hz`/`-40 dB`
    figures remain a second, uninvestigated tunable — not resolved by
    this revision.
11. **v3, new**: the `stereo_phase.overall_correlation` cross-check
    recommended in §3.2/§3.5 is only exact under near-equal channel
    power (§3.5's own caveat) — not a defect, but a precision limit on
    that specific recommended verification step.

## 11. Explicitly out of scope (reaffirmed)

**DEF-202** (mastering stage not consuming STORY-002's reference
measurements) is not addressed anywhere in this document. DEF-202
remains open, tracked separately in `stories/STORY-002/defects.md`.

## 12. Revision history

**v1** — first architecture.md for STORY-003. §2.2 originally specified
`hf_rolloff_threshold_db=40.0`; §4.2 originally specified the literal
story.md `>0.0` LUFS ceiling.

**v2** — two corrections: (1) DEF-201's threshold value corrected
`40.0`→`20.0` (midpoint of an empirically validated `[18,21] dB`
window, sweep tables preserved in `stories/STORY-002/defects.md`'s
DEF-201 entry); flagged the window's fragility and recommended (not
required) a slope-based follow-up. (2) DEF-206's LUFS ceiling derived,
`0.0`→`6.5`, from three verified codebase facts.

**v3 (this revision)** — both DEF-201 and DEF-203 reopened by james
after reviewing a real reference-set report; both resolved by a
redesign, not a retune:

1. **DEF-201: threshold-crossing replaced by sustained slope + floor
   cliff detection as the primary mechanism (§2.8-§2.13), explicitly
   reversing v2's §2.7 "keep the threshold" conclusion.** Trigger: all
   five real reference tracks reported `stable=False`; Leftfield (a
   ~1995 CD master) reported an implausible 8170 Hz. qa-automation-
   engineer's follow-up wiring-gap investigation (`stories/STORY-002/
   defects.md`) empirically isolated the cause: per-segment
   re-anchoring of the reference-band threshold explains the
   *instability*, but pinning the anchor to a single whole-track value
   leaves the 8170 Hz figure **unchanged** — direct evidence the defect
   is the detection method (an absolute-level crossing against a
   naturally declining spectrum measures where a tilt crosses a line,
   not a real filter edge), not merely anchor instability. The v2-era
   averaging-depth objection to slope-as-primary (§2.2/§2.7) is
   answered, not ignored: Stage 1 now runs on the whole-track PSD (not
   per-segment) using band-averaged probes, not single noisy bins.
   `hf_rolloff_threshold_db=20.0` and (renamed) `hf_cliff_slope_db_per_octave=24.0`
   are reused with changed roles (floor-depth and primary-slope
   criteria, respectively), not discarded. Four new config fields
   added (`hf_cliff_min_span_octaves`, `hf_cliff_floor_min_fraction`,
   `hf_cliff_probes_per_octave`, `hf_cliff_passband_max_deviation_db`);
   `_transcode_slope_check` deleted (superseded); `HfExtensionResult`
   gains `cutoff_detected`/`per_segment_cutoff_detected`.
2. **DEF-203: independently re-derived (§3.5), generalized to unequal
   channel power — constants confirmed correct a third time** (not the
   actual defect). **The actual defect, identified by the reopened
   report's own analysis and confirmed here**: `excess_cancellation_db`'s
   name and sign convention invite the opposite of its actual meaning
   (higher = healthier, not "more cancellation"), which is why the same
   correct number was reported as a bug three times. Resolved (§3.6) by
   renaming to `headroom_db` and adding a broadband `cancellation` flag
   (`broadband_cancellation: bool`) mirroring the existing per-band
   pattern, with a derived (not guessed) threshold default that reuses
   `-3.0` because both metrics reduce to the same closed form.

**Downstream impact of v3, for python-developer** (stale points against
the implementation as it existed after v2 — not a full re-implementation):

- `reference_analysis/config.py`: rename
  `transcode_suspect_slope_db_per_octave` → `hf_cliff_slope_db_per_octave`
  (value unchanged); add `hf_cliff_min_span_octaves=1/3`,
  `hf_cliff_floor_min_fraction=0.8`, `hf_cliff_probes_per_octave=48`,
  `hf_cliff_passband_max_deviation_db=6.0`,
  `mono_broadband_cancellation_headroom_db=-3.0`.
- `analysis/hf_extension.py`: implement §2.9's `_cliff_exists`/
  `_probe_band_levels_db`/`_localize_crossing_hz`/`_segment_result`/
  `_compute_stability`, restructure `measure_hf_extension` as shown;
  delete `_transcode_slope_check`.
- `analysis/reference_types.py`: add `HfExtensionResult.cutoff_detected`/
  `per_segment_cutoff_detected`; rename `MonoSumResult.excess_cancellation_db`
  → `headroom_db`, add `MonoSumResult.broadband_cancellation`.
- `analysis/mono_sum.py`: rename the computed field, add the broadband
  flag.
- `report/reference_render.py`: update the mono-sum render line (field
  name + prose), add a `broadband_cancellation` render line; recommend
  adding a `cutoff_detected` render for the HF-extension line.
- `report/reference_builder.py`: `SCHEMA_VERSION` `"1.2"`→`"1.3"`;
  update `config_summary()`'s renamed key.
- `reference_analysis/aggregate.py`: update the mono-sum aggregate key
  to `"mono_sum.headroom_db"`.
- **Not this pass's own deliverable, explicitly required before
  either defect can be closed a second time**: re-fixture/re-verify
  the HF-extension ground-truth suite per §2.13's predictions (all
  reasoned, none confirmed by this architecture pass); re-run the real
  five-track set and record actual `cutoff_detected`/`stable`/
  `suspected_transcode` values per track; update `test_tc311`/
  `test_tc313` to `result.headroom_db`; update
  `ref_helpers.make_stub_measurements`.

---
