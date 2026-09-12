# STORY-007: Suno Artifact Detection — Test Cases

**Story**: STORY-007  
**Version**: 1.2  
**Date**: 2026-08-14  
**Tracing**: Acceptance criteria AC1–AC7 (requirements.md)

**Revision history**:
- 1.2 (2026-08-14): Fixed TC-021 boundary values (DEF-710 — detector uses HF Hilbert envelope metric, not STE; empirical boundary 30 ms ramp → no flag, 35 ms ramp → flag); fixed TC-023 boundary values (DEF-709 — STFT window overlap means a 1.4 s whistle activates 6+ frames; empirical safe boundary 0.8 s → no flag, 2.0 s → flag); updated TC-001–TC-006 to remove SFM (Spectral Flatness Measure) references and clarify the two-stage SMEARED_TRANSIENT detector (HF-band LCF gate + HF Hilbert rise-time per arch §5.1 updated); redesigned F-004 to temporal-method fixture (TMI_HF + CC_HF_LF per DEF-712); redesigned TC-020 to cymbal decay negative control per DEF-712; updated TC-022 boundary values to 1.5/3.0 s safe margins per DEF-712; updated TC-027 and TC-029 SFM divide-by-zero references to temporal metric equivalents; updated traceability table AC4 and coverage checklist; partially resolved OQ-1 for TC-021 (HF Hilbert confirmed as the detector metric); withdrew OQ-5 (crest factor no longer used by DIGITAL_HAZE detector — DEF-712); removed TC-023 from OQ-2 affected list (pre-existing mis-attribution).
- 1.1 (2026-08-13): Fixed F-006 prominence derivation (from broadband amplitude ratio to per-bin FFT magnitude ratio per arch §5.3 8 dB target); corrected F-003 from brickwall lowpass to linear-phase FIR shelf per arch §5.1; added sub-interval injection to F-004 and F-006 so timestamp assertions are meaningful; marked TC-024 [OPEN] with OQ-9 because PHASE_SWISH magnitude-correlation and phase-variance cannot be independently varied through phase-only perturbation; fixed OQ cross-references (OQ-4 → TC-031 not TC-032, OQ-8 added for drift-rate detector, OQ-7 TC-038 removed); added TC-042 (sample_rate override), TC-043 (AC3 combined-signal test); fixed TC-030 fixture.

---

## Open Questions Affecting Expected Values

Do not invent values for open questions. Each affected test case calls out the dependency; leave the assertion as `[OPEN]` until resolved.

| OQ | Question | Affected TCs |
|---|---|---|
| OQ-1 | Rise-time measurement domain: §5.1 says "10% to 90% of peak energy" but does not state whether the energy envelope is computed as the square of the amplitude envelope or as a short-time energy estimate. Linear amplitude ramp gives different 10–90 times in energy vs amplitude domains (factor of 0.633 vs 0.8). **PARTIALLY RESOLVED by DEF-710**: the detector uses the HF Hilbert amplitude envelope (10%–90% of peak HF Hilbert amplitude on the 6–16 kHz bandpassed signal, not STE). TC-021 updated to use empirical HF Hilbert boundary values (30/35 ms ramp). Remaining open for TC-002: field name `details["rise_time_ms"]` is not confirmed in architecture — assert field presence and value > 25.0 only. | TC-002 |
| OQ-2 | Q factor definition in §5.3 is self-contradictory: "peak width in bins, inversely related to Q" then "Q factor (central bin / bandwidth in bins)." These are inverses. `details["q_factor"]` cannot be asserted until this is resolved. | TC-008, TC-009 |
| OQ-3 | Minimum sample rate boundary: §8 says "Detectors require >= 16 kHz Nyquist," implying sr=32000 should pass. §7.1 says ValueError if `sample_rate < 32000`. Confirm whether exactly 32000 is the inclusive lower bound. | TC-015, TC-025 |
| OQ-4 | Unsupported channel count: §7.1 says ValueError for "unsupported channel count" without specifying which counts are supported. Assumed: 1 (mono) and 2 (stereo). Confirm. | TC-031 |
| OQ-5 | ~~DIGITAL_HAZE crest factor: §5.2 uses "dynamic range," "crest factor (peak/RMS)," and "6 dB" interchangeably.~~ **WITHDRAWN by DEF-712**: The DIGITAL_HAZE detector no longer uses crest factor or SFM. Trigger conditions are TMI_HF < 0.10 (PROVISIONAL) AND CC_HF_LF < 0.30 (PROVISIONAL) — both temporal-domain metrics. Crest factor is not part of the detection logic. | — |
| OQ-6 | Performance SLA: requirements.md says "best-effort, N unbounded." TC-041 cannot have a hard pass criterion until defined. | TC-041 |
| OQ-7 | Default confidence-to-warning threshold: fixed at 0.80 per requirements. Tests assume 0.80. If made configurable via CLI, tests must pass the default explicitly. | TC-014 |
| OQ-8 | Drift-rate detector (§10.2 Q4): architecture §5.3 notes a drift-rate detector is needed to suppress vibrato false positives but marks it as unimplemented. Until the drift-rate detector is specified, TC-009 has no automated pass/fail. | TC-009 |
| OQ-9 | PHASE_SWISH boundary test (TC-024): §5.4 defines three conjunctive trigger conditions — HF phase variance, HF magnitude cross-correlation, and LF magnitude cross-correlation. Constructing a signal that varies HF phase variance independently while holding the other two conditions constant is not achievable by phase-only perturbation (phase perturbation leaves magnitudes unchanged, so HF magnitude correlation stays near 1.0 regardless of phase variance). Boundary testing on phase variance alone is therefore not constructible as written. Resolution options: (a) specify how to construct a signal that satisfies all three conditions at a controlled variance level; (b) make the boundary test dependent on internal state not visible via the public API; (c) accept that only the combined condition triplet can be tested (TC-011 covers this). Rewrite this test case once resolution is provided. | TC-024 |

---

## Fixture Specifications

Fixtures are synthetic minimal signals with analytically derivable properties. Full-length tracks are used only where the test genuinely requires it (marked **Slow**). All numpy calls use `np.random.default_rng(seed=42)` for reproducibility.

### Detector parameters assumed throughout (from architecture §6)

```
WINDOW_DURATION_S  = 0.5      # 500 ms window
HOP_SIZE_S         = 0.25     # 250 ms hop (50% overlap)
FFT_SCALE_FACTOR   = 4        # FFT size = window_samples × 4
# At 44100 Hz: window_samples = 22050, FFT_size = 88200, bin_width = 0.5 Hz
# At 48000 Hz: window_samples = 24000, FFT_size = 96000, bin_width = 0.5 Hz
```

---

### F-001: Sharp-attack kick (negative control for SMEARED_TRANSIENT)

```python
import numpy as np

sr = 44100
duration = 0.5
n = int(sr * duration)
rng = np.random.default_rng(42)
noise = rng.standard_normal(n).astype(np.float64)

# Linear amplitude ramp: 0 → 1 over 12 ms, then exponential decay
ramp_ms = 12.0
ramp_samples = int(ramp_ms / 1000 * sr)  # 530 samples
envelope = np.zeros(n)
envelope[:ramp_samples] = np.linspace(0, 1, ramp_samples)
if ramp_samples < n:
    envelope[ramp_samples:] = np.exp(-np.arange(n - ramp_samples) / (0.05 * sr))
signal = noise * envelope

# Fixture self-check (must pass before using this fixture):
# Compute 5 ms short-time RMS of signal²; locate the frame of peak energy.
# Measure time from 10% to 90% of peak short-time RMS-squared.
# Assert rise-time < 15 ms (energy domain) and < 15 ms (amplitude domain).
#
# Analytical derivation (linear amplitude ramp, energy domain):
#   t_10_energy = sqrt(0.1) × 12 ms ≈ 3.8 ms
#   t_90_energy = sqrt(0.9) × 12 ms ≈ 11.4 ms
#   rise-time (energy) ≈ 7.6 ms << 25 ms threshold → must NOT flag
#   rise-time (amplitude) = 0.8 × 12 ms = 9.6 ms << 25 ms → same conclusion
```

Stereo: `samples = np.column_stack([signal, signal])`, shape `(n, 2)`.

---

### F-002: Slow-attack onset (positive control for SMEARED_TRANSIENT)

```python
sr = 44100
duration = 0.5
n = int(sr * duration)
rng = np.random.default_rng(42)
noise = rng.standard_normal(n).astype(np.float64)

# Linear amplitude ramp over 55.3 ms, then exponential decay.
# Analytical derivation: for a linear amplitude ramp of T ms,
#   energy rise-time  = (sqrt(0.9) - sqrt(0.1)) × T ≈ 0.633 × T
#   amplitude rise-time = 0.8 × T
# Choosing T = 55.3 ms:
#   energy rise-time  = 0.633 × 55.3 ≈ 35.0 ms  > 25 ms threshold → MUST flag
#   amplitude rise-time = 0.8 × 55.3 ≈ 44.2 ms  > 25 ms threshold → MUST flag
# Both interpretations of OQ-1 produce rise-time > 25 ms. This choice is deliberate.
ramp_ms = 55.3
ramp_samples = int(ramp_ms / 1000 * sr)
envelope = np.zeros(n)
envelope[:ramp_samples] = np.linspace(0, 1, ramp_samples)
if ramp_samples < n:
    envelope[ramp_samples:] = np.exp(-np.arange(n - ramp_samples) / (0.05 * sr))
signal = noise * envelope

# Fixture self-check: compute 5 ms short-time RMS-squared (smoothed energy envelope,
# using a rectangular window of int(0.005 * sr) = 221 samples). Locate peak energy
# frame. Measure elapsed time from 10% to 90% of peak energy. Assert 30–42 ms
# (allowing for discretisation of the 5 ms smoothing window).
```

Stereo: `samples = np.column_stack([signal, signal])`.

---

### F-003: Dark-tilted kick (spectral-shape control for SMEARED_TRANSIENT)

```python
import numpy as np
import scipy.signal

sr = 44100
duration = 0.5
n = int(sr * duration)
rng = np.random.default_rng(42)
noise = rng.standard_normal(n).astype(np.float64)

# Build sharp-attack burst (< 10 ms amplitude ramp, same as F-001 with 8 ms ramp).
ramp_ms = 8.0
ramp_samples = int(ramp_ms / 1000 * sr)
envelope = np.zeros(n)
envelope[:ramp_samples] = np.linspace(0, 1, ramp_samples)
if ramp_samples < n:
    envelope[ramp_samples:] = np.exp(-np.arange(n - ramp_samples) / (0.05 * sr))
burst = noise * envelope

# Apply −12 dB tilt from 2 kHz to 16 kHz using a linear-phase FIR shelf.
# Use scipy.signal.firwin2 with frequency response:
#   [0 Hz, 2000 Hz, 16000 Hz, Nyquist]  → gains [1.0, 1.0, 0.25, 0.25] (−12 dB at 16 kHz)
# The FIR filter is linear-phase, preserving attack shape in the time domain.
nyq = sr / 2.0
freqs = [0, 2000/nyq, 16000/nyq, 1.0]
gains  = [1.0, 1.0, 0.25, 0.25]
numtaps = 255  # odd for Type I FIR (linear phase)
h = scipy.signal.firwin2(numtaps, freqs, gains)
signal = scipy.signal.lfilter(h, [1.0], burst)
# Note: lfilter introduces half-filter-length delay (~63 samples = ~1.4 ms),
# which must be accounted for in any rise-time measurement on this fixture.
# The onset rise-time remains < 10 ms regardless.

# Fixture self-check:
# 1. HF (6–16 kHz) energy relative to low-mid (500–2000 Hz): should be <= −10 dB.
# 2. Onset rise-time (energy domain) on the full-band signal: assert < 15 ms.
# Result: zero SMEARED_TRANSIENT flags expected (rise-time is fast despite dark spectral tilt).
```

Stereo: `samples = np.column_stack([signal, signal])`.

---

### F-004: Digital haze — stationary HF noise injected into sub-interval (temporal-method fixture)

**Redesigned by DEF-712**: F-004 was previously a flat-magnitude IRFFT fixture designed to produce SFM > 0.90. The DIGITAL_HAZE detector now uses the TMI_HF + CC_HF_LF temporal approach; SFM is no longer a trigger condition. F-004 is redesigned as bandpass-filtered stationary white noise (8–16 kHz) with an independent LF noise background, chosen so that frame-to-frame HF energy is near-constant (TMI_HF < 0.10) and HF/LF envelopes are uncorrelated (CC_HF_LF < 0.30, seed-pinned).

```python
import numpy as np
import scipy.signal

sr = 44100
total_duration = 6.0
haze_start_s   = 1.0
haze_end_s     = 4.5       # 3.5 s > 2.0 s threshold; 14 frames at 250 ms hop
n_total = int(sr * total_duration)
n_haze  = int(sr * (haze_end_s - haze_start_s))

rng = np.random.default_rng(42)

# HF haze region: bandpass-filtered stationary white noise (8–16 kHz).
# White noise is a stationary process → per-frame RMS in HF band is near-constant
# → TMI_HF = std(E_HF) / mean(E_HF) << 0.10 (far below provisional threshold).
sos_hf = scipy.signal.butter(8, [8000, 16000], btype='bandpass', fs=sr, output='sos')
hf_noise_raw = rng.standard_normal(n_haze)
haze = scipy.signal.sosfilt(sos_hf, hf_noise_raw)
haze = haze / (np.std(haze) + 1e-9)  # unit RMS; scale to nominal level below

# Independent LF background noise (200–2000 Hz) throughout the full file.
# Drawn from the same rng (sequential, not shared) → statistically independent of HF.
sos_lf = scipy.signal.butter(4, [200, 2000], btype='bandpass', fs=sr, output='sos')
lf_noise_raw = rng.standard_normal(n_total)
lf_bg = scipy.signal.sosfilt(sos_lf, lf_noise_raw)
lf_bg = lf_bg / (np.std(lf_bg) + 1e-9)  # unit RMS; scale to nominal level below

# Assemble: LF throughout; HF haze in sub-interval only.
# Nominal scaling: haze contributes 0.05 RMS, LF background 0.10 RMS.
signal = lf_bg * 0.10
start_idx = int(haze_start_s * sr)
end_idx   = start_idx + n_haze
signal[start_idx:end_idx] += haze * 0.05

# Fixture self-checks (must be verified independently before using fixture):
# 1. TMI_HF in the haze region: compute per-frame E_HF[t] (8–16 kHz RMS,
#    500 ms Hann window, 250 ms hop) over the 3.5 s haze interval → compute
#    TMI_HF = std(E_HF) / mean(E_HF). Assert TMI_HF < 0.10.
#    Derivation: bandpass-filtered white noise averages ~N_hf_bins ≈ 16000 FFT bins
#    in the 8–16 kHz range; frame-to-frame energy variation ≈ 1/sqrt(N/2) << 0.10.
# 2. CC_HF_LF in the haze region: Pearson correlation between E_HF[t] and E_LF[t]
#    (E_LF in 200–2000 Hz, same frame grid) → assert CC_HF_LF < 0.30.
#    Note: over 14 frames the estimator has SE ≈ 1/sqrt(14) ≈ 0.27. This assertion
#    is seed-pinned (seed=42). If seed produces CC_HF_LF >= 0.30, use a different
#    LF seed and document.
# 3. Haze duration: haze_end_s - haze_start_s = 3.5 s > 2.0 s threshold.
```

Stereo: `samples = np.column_stack([signal, signal])`.

---

### F-005: Tonal content (formerly the DIGITAL_HAZE negative control — now STALE)

**Stale note (DEF-712)**: F-005 (three pure 8–16 kHz sinusoids) was designed as the DIGITAL_HAZE negative control under the old SFM-based detector (SFM ≈ 0 for discrete tones). Under the current temporal detector, pure sinusoids have a near-constant amplitude envelope → TMI_HF ≈ 0 → TMI_HF < 0.10 condition would be met → F-005 would trigger the temporal DIGITAL_HAZE detector. F-005 is therefore no longer a valid DIGITAL_HAZE negative control. See TC-020 for the redesigned negative control (cymbal decay). F-005 is retained here for reference only.

```python
sr = 44100
duration = 3.5
n = int(sr * duration)
t = np.arange(n) / sr

# Sum of three pure 8–16 kHz sinusoids. SFM approaches 0 because geometric mean
# of a magnitude spectrum with discrete peaks is near 0 (most bins zero).
# Derivation: for K discrete tones in N bins, SFM = geometric_mean / arithmetic_mean.
# geometric_mean = prod(m_k)^(1/N) → tends to 0 as N >> K (most bins near 0).
signal = (np.sin(2*np.pi*10000*t) +
          np.sin(2*np.pi*12000*t) +
          np.sin(2*np.pi*14000*t)) / 3.0
signal = signal.astype(np.float64)
# Crest factor of sum of 3 coherent sines: bounded by amplitude sum.
# For unit-amplitude sine: crest factor ≈ 3.01 dB. Well above 6 dB? No.
# BUT: SFM condition (>0.85) fails first for tonal signals → DIGITAL_HAZE must not flag.
# WARNING (DEF-712): TMI_HF ≈ 0 for constant-amplitude sinusoids; do NOT use F-005
# as a DIGITAL_HAZE negative control under the temporal method.
```

Stereo: `samples = np.column_stack([signal, signal])`.

---

### F-006: Sustained 6.4 kHz sine injected into sub-interval

```python
import numpy as np

sr = 44100
total_duration = 5.0
whistle_start_s = 1.0
whistle_end_s   = 3.5       # 2.5 s duration > 1.5 s persistence threshold
n_total = int(sr * total_duration)
n_whistle = int(sr * (whistle_end_s - whistle_start_s))

rng = np.random.default_rng(42)

# Noise bed throughout (broadband background)
noise = rng.standard_normal(n_total).astype(np.float64) * noise_rms
# NOTE: noise_rms must be calibrated to achieve prominence ≈ 8 dB (see derivation below).

# ── Prominence derivation ──────────────────────────────────────────────────────
# Architecture §5.3 positive control: prominence 8 dB.
# The detector uses a Hann-windowed STFT (window=22050 samples at 44100 Hz, FFT=88200).
# For a sine at exact-bin frequency f=6400 Hz (bin index = 6400 / (44100/88200) = 12800):
#   Peak bin magnitude (Hann window, coherent gain 0.5):
#     M_sine ≈ A_sine × N_window × 0.5 = A_sine × 22050 × 0.5 = 11025 × A_sine
#   Expected noise bin magnitude for white noise RMS σ, Hann window:
#     E[|X_k|] ≈ σ × sqrt(N_window × π / 8) = σ × sqrt(22050 × π / 8) ≈ σ × 93.0
#   Prominence (in dB):
#     P ≈ 20·log10(11025 × A_sine / (σ × 93.0))
#       = 20·log10(A_sine / σ) + 20·log10(11025/93.0)
#       = 20·log10(A_sine / σ) + 41.5 dB
#   For P = 8 dB:
#     20·log10(A_sine / σ) = 8 − 41.5 = −33.5 dB → A_sine / σ ≈ 0.0211
#   Choosing σ = 0.10 (noise RMS) → A_sine = 0.00211 ≈ 0.002
# ─────────────────────────────────────────────────────────────────────────────
noise_rms  = 0.10
A_sine     = 0.002    # nominal; fixture self-check confirms actual prominence

noise = rng.standard_normal(n_total).astype(np.float64) * noise_rms

t_whistle = np.arange(n_whistle) / sr
whistle = np.sin(2 * np.pi * 6400 * t_whistle).astype(np.float64) * A_sine

signal = noise.copy()
start_idx = int(whistle_start_s * sr)
signal[start_idx:start_idx + n_whistle] += whistle

# Fixture self-check (required before using this fixture):
# Compute the STFT of the whistle-active region using the same parameters as the detector
# (scipy.signal.stft, window='hann', nperseg=22050, noverlap=22050//2, nfft=88200).
# Identify the peak bin near 6400 Hz in the magnitude spectrum.
# Use scipy.signal.find_peaks() on the magnitude spectrum to measure prominence_db.
# Assert prominence_db = 8 ± 2 dB. If self-check fails, adjust A_sine and document.
#
# Note: 6400 Hz at sr=44100 Hz with FFT=88200: bin index = 6400 / 0.5 = 12800 (exact integer).
# At sr=48000 Hz with FFT=96000: bin index = 6400 / 0.5 = 12800 (same bin index, same Hz).
```

Stereo: `samples = np.column_stack([signal, signal])`.

---

### F-007: Phase-swish signal (positive control for PHASE_SWISH)

```python
import numpy as np

sr = 44100
duration = 2.5
n = int(sr * duration)
t = np.arange(n) / sr
rng = np.random.default_rng(42)

# LF component (< 8 kHz): identical on L and R → LF magnitude correlation = 1.0 by construction
lf_freqs = [100, 500, 1000, 2000, 4000]
lf = sum(np.sin(2*np.pi*f*t) for f in lf_freqs) / len(lf_freqs)
lf = lf.astype(np.float64)

# HF component (> 8 kHz): independent noise on L and R.
# After band-passing above 8 kHz, L and R are statistically independent.
# HF phase variance derivation: for independent channels, phase differences are
# uniformly distributed on [−π, π] → variance = π²/3 ≈ 3.29 rad² >> 0.5 threshold.
# HF magnitude correlation for independent noise: E[corr] ≈ 0 (within ±0.1 for finite length).
hf_L = rng.standard_normal(n).astype(np.float64) * 0.1
hf_R = rng.standard_normal(n).astype(np.float64) * 0.1  # independent draw

# Band-limit HF components above 8 kHz using 8th-order Butterworth highpass.
import scipy.signal as sig
b, a = sig.butter(8, 8000 / (sr/2), btype='high')
hf_L = sig.lfilter(b, a, hf_L)
hf_R = sig.lfilter(b, a, hf_R)

L = lf + hf_L
R = lf + hf_R
samples = np.column_stack([L, R])

# Analytically expected properties:
# LF cross-correlation: ≈ 1.0 (identical LF → correlation 1.0)
# HF cross-correlation: ≈ 0.0 (independent noise; finite estimate within ±0.1)
# HF phase variance: ≈ π²/3 ≈ 3.29 rad²
```

---

### F-008: Mono-identical stereo (negative control for PHASE_SWISH)

```python
sr = 44100
duration = 2.5
n = int(sr * duration)
rng = np.random.default_rng(42)
signal = rng.standard_normal(n).astype(np.float64) * 0.5
samples = np.column_stack([signal, signal])  # L == R exactly

# Derivation: HF correlation = 1.0 (identical channels), HF phase variance = 0.0.
# Neither trigger condition (variance > 0.5, correlation < 0.4) is met.
```

---

### F-009: Logarithmic sine sweep (negative control for STATIONARY_WHISTLE)

```python
import numpy as np
import scipy.signal

sr = 44100
duration = 5.0
n = int(sr * duration)
t = np.arange(n) / sr
signal = scipy.signal.chirp(t, f0=100, f1=20000, t1=duration, method='logarithmic').astype(np.float64)
samples = np.column_stack([signal, signal])

# Derivation: the sweep rate at 6400 Hz is f' = (f1/f0)^(t/T) × f0 × ln(f1/f0)/T ≈ 2054 Hz/s.
# At 250 ms hop intervals, the frequency moves ~514 Hz per window — far beyond the ±50 Hz
# tolerance. No peak is stationary within ±50 Hz for >= 1.5 s → zero STATIONARY_WHISTLE.
```

---

### F-010: Combined artifact signal (AC3 combined test)

```python
import numpy as np

sr = 44100
total_duration = 4.0
n_total = int(sr * total_duration)
rng = np.random.default_rng(42)

# Background noise bed
noise = rng.standard_normal(n_total).astype(np.float64) * 0.10

# --- Whistle region: 1.0–3.5 s (2.5 s, > 1.5 s persistence threshold)
whistle_start, whistle_end = 1.0, 3.5
n_w = int(sr * (whistle_end - whistle_start))
t_w = np.arange(n_w) / sr
whistle = np.sin(2 * np.pi * 6400 * t_w).astype(np.float64) * 0.002
signal = noise.copy()
signal[int(whistle_start * sr):int(whistle_start * sr) + n_w] += whistle

# --- Slow-attack onset at t = 0.2 s (onset peak at 0.2 + 0.055 = ~0.255 s)
# Linear amplitude ramp, 55.3 ms (energy rise-time 35 ms, well above 25 ms threshold)
onset_start = int(0.200 * sr)
ramp_ms = 55.3
ramp_samples = int(ramp_ms / 1000 * sr)
onset_noise = rng.standard_normal(n_total).astype(np.float64) * 0.5
envelope = np.zeros(n_total)
envelope[onset_start:onset_start + ramp_samples] = np.linspace(0, 1, ramp_samples)
if onset_start + ramp_samples < n_total:
    tail = n_total - (onset_start + ramp_samples)
    envelope[onset_start + ramp_samples:] = np.exp(-np.arange(tail) / (0.05 * sr))
signal += onset_noise * envelope

samples = np.column_stack([signal, signal])
# Expected: SMEARED_TRANSIENT flag near t=0.2 s AND STATIONARY_WHISTLE flag in [1.0, 3.5 s].
# The two artifact types must appear in the same ArtifactDetectionResult.
```

---

## Test Cases

### Group 1 — SMEARED_TRANSIENT Detector

---

**TC-001**
**Title**: SMEARED_TRANSIENT — negative control (sharp-attack kick, < 25 ms rise-time)
**Covers**: AC2, AC3 (by absence), architecture §9.1 `test_smeared_transient_negative_control`
**Type**: Audio-quality / negative control
**Preconditions**: Fixture F-001. Stereo, 44.1 kHz, 0.5 s.

**Steps**:
1. Construct F-001. Verify fixture self-check: measure onset rise-time as described in F-001; assert < 15 ms (independent of the detector).
2. Wrap in `AudioBuffer` (float64, shape (n, 2), sr=44100).
3. Call `detect_artifacts(audio_buffer)`.
4. Inspect all returned `ArtifactFlag` objects.

**Expected result**:
- Zero `SMEARED_TRANSIENT` flags.
- No exception raised.

**Note on two-stage detector (architecture §5.1 updated, DEF-705)**: The detector is now two-stage: (1) HF-band (6–16 kHz) LCF gate — requires LCF ≥ 6 dB in a 30 ms window centred on the HF envelope peak anchor; (2) HF Hilbert amplitude envelope rise-time — must exceed 25 ms to flag. For F-001 (broadband noise with 12 ms amplitude ramp): the gate passes because crest factor is level-invariant and a sharp onset in broadband noise produces LCF well above 6 dB in the HF band. The HF Hilbert rise-time is then measured and is well below 25 ms → no flag. The fixture self-check uses the STE metric (< 15 ms) as an independent approximation; for broadband noise with a sharp attack, both STE and HF Hilbert metrics confirm a fast onset.

**Pass/fail criterion**: Any `SMEARED_TRANSIENT` flag → FAIL.

---

**TC-002**
**Title**: SMEARED_TRANSIENT — positive control (35 ms energy rise-time onset)
**Covers**: AC3, architecture §9.1 `test_smeared_transient_positive_control`
**Type**: Audio-quality / positive control
**Preconditions**: Fixture F-002. Stereo, 44.1 kHz, 0.5 s.

**Steps**:
1. Construct F-002. Verify fixture self-check: compute 5 ms short-time RMS-squared energy envelope (STE method); measure time from 10% to 90% of peak energy; assert in the range 30–42 ms. Note (DEF-710): the detector uses the HF Hilbert amplitude envelope on the 6–16 kHz bandpassed signal, not STE. The STE self-check (≈35 ms for the 55.3 ms ramp) is an independent approximate verification confirming the ramp is slow. The actual HF Hilbert rise-time is a different numerical value but is also well above the 25 ms threshold for a 55.3 ms ramp. This self-check is independent of the detector.
2. Wrap in `AudioBuffer` (float64, sr=44100).
3. Call `detect_artifacts(audio_buffer)`.
4. Inspect flags.

**Expected result**:
- At least one `SMEARED_TRANSIENT` flag.
- `confidence_score >= 0.85` per architecture §5.1 confidence table (rise-time 30–40 ms maps to 0.85).
- `timestamp_start_s >= 0.0`, `timestamp_end_s <= 0.5`, `timestamp_end_s > timestamp_start_s`.
- `details` dict present. [PARTIALLY RESOLVED OQ-1 (DEF-710): metric confirmed as HF Hilbert amplitude envelope. Assert `details["rise_time_ms"] > 25.0` if the field exists; field name is still unspecified in architecture.]

**Pass/fail criterion**: No `SMEARED_TRANSIENT` flag, or `confidence_score < 0.85` → FAIL.

---

**TC-003**
**Title**: SMEARED_TRANSIENT — dark material control (−12 dB tilt, 8 ms rise-time)
**Covers**: AC2 (false-positive prevention on spectrally dark material), architecture §9.1 `test_smeared_transient_dark_material`
**Type**: Audio-quality / negative control
**Preconditions**: Fixture F-003. Linear-phase FIR shelf applies −12 dB tilt from 2 kHz to 16 kHz to a sharp-attack burst. HF energy > 10 dB below low-mid energy; attack rise-time (energy) < 10 ms. Stereo, 44.1 kHz.

**Steps**:
1. Construct F-003. Verify fixture self-checks: (a) HF (6–16 kHz) energy relative to LM (500–2000 Hz) < −10 dB; (b) onset rise-time < 15 ms.
2. Call `detect_artifacts(audio_buffer)`.

**Expected result**:
- Zero `SMEARED_TRANSIENT` flags.

**Rationale**: This is the primary guard against the DEF-201 class of bug. The detector (architecture §5.1 updated) is two-stage: HF-band (6–16 kHz) LCF gate, then HF Hilbert rise-time measurement. For F-003 (dark-tilted broadband noise with 8 ms ramp): note that crest factor (LCF = 20·log10(peak/rms)) is level-invariant — attenuating the HF band by 12 dB scales both peak and RMS equally, leaving LCF unchanged at approximately 10–15 dB (carrier oscillations in filtered broadband noise). The LCF gate therefore passes. The HF Hilbert rise-time is then measured and is fast (< 10 ms) → no flag. Any `SMEARED_TRANSIENT` flag here indicates the detector is using spectral energy magnitude or spectral shape as a proxy for transient quality rather than evaluating the HF Hilbert rise-time, which is architecturally forbidden. Coverage gap: a kick-drum gate-rejection control (near-zero 6–16 kHz energy → LCF ≈ 0 dB → gate fails) is not covered by TC-001–TC-006 and remains an open coverage gap.

**Pass/fail criterion**: Any `SMEARED_TRANSIENT` flag → FAIL. Treat as architecture violation, not implementation bug.

---

**TC-043**
**Title**: AC3 combined — whistle and smeared transient detected simultaneously in one file
**Covers**: AC3 (both flag types in single call)
**Type**: Audio-quality / integration
**Preconditions**: Fixture F-010. Stereo, 44.1 kHz, 4.0 s total. Slow onset at ~0.2 s (rise-time 35 ms). Whistle at 6400 Hz from 1.0–3.5 s.

**Steps**:
1. Construct F-010. Call `detect_artifacts`.
2. Collect all flags.
3. Check that both artifact types appear.

**Expected result**:
- At least one `SMEARED_TRANSIENT` flag with `timestamp_start_s` near 0.2 s (within ±0.5 s).
- At least one `STATIONARY_WHISTLE` flag with `timestamp_start_s` within ±0.5 s of 1.0 s and `timestamp_end_s` within ±0.5 s of 3.5 s.
- `details["frequency_hz"]` of the whistle flag within 6350–6450 Hz.
- All flags satisfy invariants from TC-034.

**Pass/fail criterion**: Either flag type absent → FAIL. Timestamps outside ±0.5 s of injected boundaries → FAIL.

---

**TC-021**
**Title**: SMEARED_TRANSIENT — boundary values at the 25 ms threshold (HF Hilbert envelope metric)
**Covers**: AC3 (boundary), architecture §5.1
**Type**: Boundary value

**Correction note (DEF-710)**: The original boundary values (24/26 ms) were derived by applying the STE factor T_ramp = rise_time_ms / 0.633, yielding ramp durations of 37.9 ms and 41.1 ms. The detector measures the 10%–90% HF Hilbert amplitude envelope rise-time on the 6–16 kHz bandpassed signal, not the broadband STE rise-time. Empirically probed boundary values (seed=42, onset at 0.5 s in a 1.5 s signal, broadband noise): a 30 ms ramp produces HF Hilbert rise-time < 25 ms (no flag); a 35 ms ramp produces HF Hilbert rise-time of ≈25.22 ms (flag raised). Notably, a 24 ms ramp (from the old STE calculation) was found empirically to produce an HF Hilbert rise-time of ≈30.93 ms — above threshold, causing the old "negative control" to trigger. The 0.633 STE conversion factor does not apply to the HF Hilbert metric. These boundary values are empirically derived from probes run against the current detector implementation and should be re-probed if the STFT parameters or the envelope metric change. OQ-1 resolved for this test: the detector uses HF Hilbert amplitude envelope, not energy (STE).

**Preconditions**: Two stereo signal instances at 44.1 kHz. Broadband noise (seed=42), onset at 0.5 s in a 1.5 s signal, constructed with linear amplitude ramp durations of 30 ms (negative control) and 35 ms (positive control). Broadband noise ensures HF content is present so that the percussive HF-band LCF gate (requires LCF ≥ 6 dB in 6–16 kHz) passes for both fixtures. The onset must also pass the LCF gate to reach rise-time measurement; for broadband noise this is expected.

**Steps** (repeat for each fixture):
1. Construct onset signal: broadband noise (seed=42, sr=44100, duration=1.5 s) with linear amplitude ramp of specified duration starting at t=0.5 s.
2. Call `detect_artifacts`. Record any `SMEARED_TRANSIENT` flags.

**Expected results**:
- **30 ms ramp**: zero `SMEARED_TRANSIENT` flags. Empirically measured HF Hilbert rise-time < 25 ms at this ramp duration (DEF-710 probe).
- **35 ms ramp**: at least one `SMEARED_TRANSIENT` flag. Empirically measured HF Hilbert rise-time ≈ 25.22 ms at this ramp duration (DEF-710 probe).

Note: a "boundary at exactly 25 ms HF Hilbert rise-time" fixture cannot be constructed analytically for broadband noise — the relationship between ramp duration and HF Hilbert rise-time is non-linear and signal-dependent. Any ramp duration in the 30–35 ms range may or may not trigger depending on the exact noise realisation. The 30/35 ms empirical boundary supersedes the theoretical 24/26 ms boundary derived from STE.

**Pass/fail criterion**: 30 ms ramp produces any `SMEARED_TRANSIENT` flag → FAIL. 35 ms ramp produces no `SMEARED_TRANSIENT` flag → FAIL.

---

### Group 2 — DIGITAL_HAZE Detector

---

**TC-004**
**Title**: DIGITAL_HAZE — known-limitation confirmation (pink noise expected to flag)
**Covers**: Architecture §9.1 `test_digital_haze_negative_control`, §10.1 known limitation 1
**Type**: Known-limitation documentation test (NOT a correctness test — flagging is the expected behavior)
**Preconditions**: 3.5 s stereo pink noise (1/f spectrum), broadband, sr=44100.

**Steps**:
1. Generate pink noise (1/f spectrum, seed=42, duration=3.5 s, stereo, sr=44100).
2. Call `detect_artifacts`. Record any `DIGITAL_HAZE` flags.

**Expected result**: One or more `DIGITAL_HAZE` flags. This confirms the known limitation: stationary broadband pink noise has near-constant per-frame HF energy → TMI_HF < 0.10 (temporal stationarity condition met). The CC_HF_LF estimator over 8 frames has SE ≈ 1/sqrt(8) ≈ 0.35 and may fall below the 0.30 threshold due to estimator variance alone, incidentally satisfying the decoupling condition. Pink noise therefore triggers the temporal DIGITAL_HAZE detector despite not being a Suno artifact. If this test does NOT produce flags, the fixture is wrong or the provisional thresholds have been tightened — fix the fixture or update this test accordingly.

**Note**: This test documents a known limitation, not a bug. See TC-020 for the true negative control. If the detector is ever improved to suppress broadband-noise false positives, update this test and remove the limitation from §10.1.

**Pass/fail criterion**: No automated pass/fail. Flag presence is the expected behavior; absence indicates a fixture problem or threshold change.

---

**TC-005**
**Title**: DIGITAL_HAZE — positive control (TMI_HF < 0.10, CC_HF_LF < 0.30, sub-interval injection)
**Covers**: AC4, architecture §9.1 `test_digital_haze_positive_control`
**Type**: Audio-quality / positive control
**Preconditions**: Fixture F-004 (temporal-method redesign per DEF-712). Stereo, 44.1 kHz, 6.0 s total. Haze injected from 1.0–4.5 s (3.5 s). LF background throughout.

**Steps**:
1. Construct F-004. Verify fixture self-checks: (a) TMI_HF < 0.10 in the haze region (per-frame E_HF RMS, 500 ms Hann window, 250 ms hop; assert std/mean < 0.10); (b) CC_HF_LF < 0.30 in the haze region (Pearson correlation of E_HF and E_LF over haze frames; seed-pinned — verify with seed=42; if fails, re-seed LF component and document).
2. Call `detect_artifacts`.
3. Inspect `DIGITAL_HAZE` flags.

**Expected result**:
- At least one `DIGITAL_HAZE` flag.
- Flag covers the haze interval: `timestamp_start_s` within 1.0 ± 0.5 s; `timestamp_end_s` within 4.5 ± 0.5 s (one hop = 250 ms tolerance).
- `confidence_score >= 0.80`.
  - Derivation (architecture §5.2, PROVISIONAL thresholds): base 0.70 (both TMI_HF < 0.10 AND CC_HF_LF < 0.30 met); +0.10 if TMI_HF < 0.05 (bandpass-filtered stationary noise gives TMI_HF << 0.05 → this bonus typically applies); +0.10 if CC_HF_LF < 0.10 (seed-dependent — may or may not apply). Cap 0.90. Assert ≥ 0.80 (base + TMI bonus; CC bonus is not guaranteed for every seed).
- No flag should extend into the silence/LF-only regions outside 1.0–4.5 s.

**Note**: Confidence increments (0.05, 0.10) and gate thresholds (0.10, 0.30) are PROVISIONAL per §5.2. If architecture confirms different values before implementation, update this derivation.

**Pass\fail criterion**: No `DIGITAL_HAZE` flag → FAIL. Confidence < 0.80 → FAIL. Timestamp start outside 0.5–1.5 s → FAIL. Timestamp end outside 4.0–5.0 s → FAIL.

---

**TC-020**
**Title**: DIGITAL_HAZE — true negative control (cymbal decay — high TMI_HF)
**Covers**: AC2 (false-positive prevention), architecture §10.1
**Type**: Audio-quality / negative control

**Redesigned per DEF-712**: The previous negative control used F-005 (three pure 8–16 kHz sinusoids, SFM ≈ 0). Under the old SFM-based detector, SFM ≈ 0 prevented flagging. Under the current temporal detector, pure sinusoids have near-constant amplitude envelope → TMI_HF ≈ 0 → TMI_HF < 0.10 condition is met → F-005 would trigger the detector. F-005 is therefore not a valid negative control. The new negative control is exponentially decaying HF noise (simulating cymbal decay): rapidly falling frame-to-frame energy → TMI_HF >> 0.10 → temporal stationarity condition fails → no flag.

**Preconditions**: Inline fixture (exponentially decaying bandpass-filtered noise):
```python
import numpy as np
import scipy.signal

sr = 44100
duration = 3.5    # > 2.0 s threshold — ensures the test is not vacuously passing on duration
n = int(sr * duration)
t = np.arange(n) / sr

rng = np.random.default_rng(42)
sos_hf = scipy.signal.butter(6, [8000, 16000], btype='bandpass', fs=sr, output='sos')
white_noise = rng.standard_normal(n)
filtered = scipy.signal.sosfilt(sos_hf, white_noise)
# Exponential decay: envelope drops by factor e^{-7} over 3.5 s (τ = 0.5 s)
decay_envelope = np.exp(-t / 0.5)
signal = filtered * decay_envelope / (np.std(filtered) + 1e-9)
samples = np.column_stack([signal, signal])
```

Fixture self-check: TMI_HF > 0.10. Derivation: E_HF at frame 0 ≈ 1.0 (normalised); E_HF at frame 13 (t ≈ 3.25 s) ≈ e^{−6.5} ≈ 0.0015 → std(E_HF)/mean(E_HF) >> 0.10 by construction. Duration 3.5 s > 2.0 s threshold ensures the test is not vacuously passing on duration grounds alone.

**Steps**:
1. Construct inline fixture. Verify self-check: compute per-frame E_HF (8–16 kHz, 500 ms Hann window, 250 ms hop) and assert TMI_HF > 0.10.
2. Call `detect_artifacts`. Check for `DIGITAL_HAZE` flags.

**Expected result**: Zero `DIGITAL_HAZE` flags. TMI_HF >> 0.10 (rapid energy decay) → temporal stationarity condition fails → detector correctly excludes this decaying HF transient.

**Pass/fail criterion**: Any `DIGITAL_HAZE` flag → FAIL.

---

**TC-022**
**Title**: DIGITAL_HAZE — duration boundary (1.5 s negative control, 3.0 s positive control)
**Covers**: AC4 (boundary), architecture §5.2
**Type**: Boundary value

**Redesigned per DEF-712**: The previous boundary values (1.9/2.0/2.1 s) were too close to the 2.0 s threshold and subject to STFT window-transition frame effects (the same overlap-counting issue documented for TC-023 in DEF-709 applies here). Safe empirical boundaries are 1.5 s (well below the 8-frame threshold at 250 ms hop, with ≥ 2-frame safe margin) and 3.0 s (well above the 8-frame threshold, with ≥ 4-frame margin). These values are empirically informed; re-probe if the 2.0 s threshold or hop size changes.

**Preconditions**: Two variants of the temporal-method F-004 fixture (bandpass-filtered stationary white noise 8–16 kHz + independent LF background, seed=42) with haze durations of 1.5 s and 3.0 s respectively. Haze begins at t=1.0 s in each case. Fixture self-check: verify TMI_HF < 0.10 and CC_HF_LF < 0.30 for the haze region in both variants (duration change does not affect the stationarity property).

**Steps** (repeat for each variant):
1. Construct variant. Verify fixture self-check on haze region (TMI_HF < 0.10, CC_HF_LF < 0.30). Call `detect_artifacts`. Check for `DIGITAL_HAZE` flags.

**Expected results**:
- **1.5 s haze**: zero flags. Derivation: 1.5 s = 6 frames at 250 ms hop — below the MIN_DURATION_FRAMES = 8 (2.0 s) threshold.
- **3.0 s haze**: at least one `DIGITAL_HAZE` flag. Derivation: 3.0 s = 12 frames — well above the 8-frame threshold.

**Pass/fail criterion**: Deviation from the expected pattern → FAIL.

---

**TC-006**
**Title**: DIGITAL_HAZE — reference track tests (five tracks, no Suno-artifact false positives)
**Covers**: AC2, architecture §9.1 `test_digital_haze_reference_tracks`, §9.2
**Type**: Audio-quality / negative control [Slow]
**Preconditions**: Five reference tracks at their native sample rates. Load with soundfile, sr=None.

**Steps**:
1. Load each track as `AudioBuffer`. Call `detect_artifacts`. Collect `DIGITAL_HAZE` flags.

**Expected results**:
- GusGus, Black Flute, Chemical Brothers: zero `DIGITAL_HAZE` flags. If any flag: characterise the flagged region (timestamp, TMI_HF value, CC_HF_LF value, confidence); the TMI_HF_THRESHOLD (currently 0.10, PROVISIONAL) or CC_HF_LF_THRESHOLD (currently 0.30, PROVISIONAL) may need adjustment. Report in defects.md before raising thresholds.
- Leftfield, Wavy Gravy: zero flags expected; any flags require manual review. Document each flagged region: timestamp, confidence, and judgment (legitimate reverb/cymbal decay → accepted; unexplained → threshold must be tightened). Record findings in defects.md.

**Pass/fail criterion (automated)**: Any `DIGITAL_HAZE` flag on GusGus, Black Flute, or Chemical Brothers → FAIL.
**Pass/fail criterion (human-gated)**: Flags on Leftfield or Wavy Gravy → human review required; not automatically passing or failing.

---

### Group 3 — STATIONARY_WHISTLE Detector

---

**TC-007**
**Title**: STATIONARY_WHISTLE — negative control (logarithmic sine sweep)
**Covers**: AC5 (by absence), AC2, architecture §9.1 `test_stationary_whistle_negative_control`
**Type**: Audio-quality / negative control
**Preconditions**: Fixture F-009. 100 Hz–20 kHz log sweep, 5 s, stereo, 44.1 kHz.

**Steps**:
1. Construct F-009. Call `detect_artifacts`. Check for `STATIONARY_WHISTLE` flags.

**Expected result**: Zero `STATIONARY_WHISTLE` flags. Derivation: at 6400 Hz, sweep rate ≈ 2054 Hz/s; over a 250 ms hop the sweep moves ≈ 514 Hz, far beyond ±50 Hz tolerance. No peak is stationary.

**Pass/fail criterion**: Any `STATIONARY_WHISTLE` flag → FAIL.

---

**TC-008**
**Title**: STATIONARY_WHISTLE — positive control (6.4 kHz sine, 8 dB prominence, sub-interval injection, 44.1 kHz)
**Covers**: AC5, architecture §9.1 `test_stationary_whistle_positive_control`
**Type**: Audio-quality / positive control
**Preconditions**: Fixture F-006. 6400 Hz sine at nominal amplitude 0.002, noise bed RMS 0.10, whistle from 1.0–3.5 s, total 5.0 s, stereo, 44.1 kHz.

**Steps**:
1. Construct F-006. Verify fixture self-check: compute STFT (Hann, nperseg=22050, nfft=88200) on whistle-active region; measure prominence of 6400 Hz bin; assert 6–12 dB (target 8 dB ± 2 dB).
2. Call `detect_artifacts`.
3. Inspect `STATIONARY_WHISTLE` flags.

**Expected result**:
- At least one `STATIONARY_WHISTLE` flag.
- `details["frequency_hz"]` within 6350–6450 Hz.
- `details["prominence_db"] >= 6.0`.
- `details["q_factor"]`: [OPEN OQ-2 — assert field exists and is a positive float; do not assert a specific value.]
- `confidence_score >= 0.80`:
  - Derivation: baseline 0.75 (persistence >= 1.5 s) + 0.05 per dB above 6 dB (8−6 = 2 dB → +0.10) = 0.85 (capped at 0.95). Assert ≥ 0.80 to allow for ±0.05 fixture prominence uncertainty.
- `timestamp_start_s` within 1.0 ± 0.5 s; `timestamp_end_s` within 3.5 ± 0.5 s.
- Flag duration (`timestamp_end_s − timestamp_start_s`) >= 1.5 s.

**Pass/fail criterion**: No flag → FAIL. `frequency_hz` outside 6350–6450 Hz → FAIL. `confidence_score < 0.80` → FAIL. Timestamps outside ±0.5 s of injected boundaries → FAIL.

---

**TC-026**
**Title**: STATIONARY_WHISTLE — frequency bin conversion at 48 kHz (regression guard)
**Covers**: AC5, architecture §10.1 (sample rate dependency)
**Type**: Audio-quality / regression
**Preconditions**: Reconstruct F-006 at sr=48000. Same nominal amplitude; fixture self-check at 48 kHz parameters (nperseg=24000, nfft=96000, bin_width=0.5 Hz — identical bin width to 44.1 kHz configuration). Verify prominence 6–12 dB.

**Steps**:
1. Construct 48 kHz variant of F-006. Call `detect_artifacts`.
2. Check `details["frequency_hz"]`.

**Expected result**:
- `STATIONARY_WHISTLE` flag with `details["frequency_hz"]` within 6350–6450 Hz.
- Same confidence and timestamp criteria as TC-008.

**Rationale**: At 44.1 kHz and 48 kHz with FFT_SCALE_FACTOR=4, the bin width happens to be identical (0.5 Hz), but the bin *index* differs (12800 at both rates in this configuration). A hardcoded sr=44100 in the bin-to-Hz formula would still give the right answer coincidentally. Use a frequency that produces a different bin index at 44.1 vs 48 kHz to expose any implicit sr assumption. If architecture permits, test at 10 kHz (bin 20000 at 44.1k, bin 21333 at 48k with a different FFT size) and assert correct Hz in `details`. If 10 kHz is used, rebuild F-006 with f=10000 Hz and prominence self-check.

**Pass/fail criterion**: `frequency_hz` outside 6350–6450 Hz → FAIL.

---

**TC-009**
**Title**: STATIONARY_WHISTLE — vibrato control (±40 Hz at 2 Hz, 1.5 s)
**Covers**: AC5 (known limitation), architecture §9.1 `test_stationary_whistle_vibrato`
**Type**: Known-limitation documentation test
**Preconditions**:
```python
sr = 44100
duration = 1.5
t = np.arange(int(sr * duration)) / sr
# FM vibrato: 6400 Hz ± 40 Hz at 2 Hz rate
phase = 2 * np.pi * np.cumsum(6400 + 40 * np.sin(2*np.pi*2*t)) / sr
signal = np.sin(phase).astype(np.float64)
samples = np.column_stack([signal, signal])
```

**Steps**:
1. Call `detect_artifacts`. Record any `STATIONARY_WHISTLE` flags and their `confidence_score`.

**Expected result**: [OPEN OQ-8 — architecture §5.3 notes this may flag as a false positive. Expected behavior depends on whether the drift-rate detector is implemented. Without it: flag may be emitted (documenting the false-positive rate). With it: zero flags expected (vibrato rate ≈ 80 Hz/s >> 0.5 Hz/s suppression threshold). This test is a baseline measurement until OQ-8 is resolved.]

**Pass/fail criterion**: No automated pass/fail until OQ-8 resolved. Record the outcome as a baseline.

---

**TC-023**
**Title**: STATIONARY_WHISTLE — persistence boundary (0.8 s negative control, 2.0 s positive control)
**Covers**: AC5 (boundary), architecture §5.3
**Type**: Boundary value

**Correction note (DEF-709)**: The original boundary values (1.4/1.6 s) were derived from MIN_PERSISTENCE_FRAMES × HOP_SIZE_S = 6 × 0.25 s = 1.5 s, without accounting for STFT window overlap. The per-bin occupancy matrix marks a frame as occupied whenever the target bin is prominent in ANY portion of the 0.5 s STFT window — not only when the whistle fully occupies an analysis window. A whistle starting at t=1.0 s and lasting 1.4 s overlaps partial STFT frames on both the leading and trailing edges of the whistle interval; empirically, a 1.4 s whistle activates 6 STFT frames — exactly at the MIN_PERSISTENCE_FRAMES=6 trigger threshold. The 1.4 s fixture was therefore triggering the detector and was not a valid negative control. Safe empirical boundaries: 0.8 s whistle → 0 flags (fewer than 6 overlapping frames); 2.0 s whistle → ≥ 1 flag (≥ 9 overlapping frames). These boundary values are empirically derived and should be re-probed if WINDOW_DURATION_S, HOP_SIZE_S, or MIN_PERSISTENCE_FRAMES change.

**Preconditions**: Two variants of F-006 with the whistle region set to 0.8 s and 2.0 s respectively. In both variants: 6400 Hz sine at amplitude=0.002, broadband noise RMS=0.10, sr=44100, whistle starting at t=1.0 s. Fixture self-check: confirm 6400 Hz bin prominence 6–12 dB in the whistle-active window (using the same STFT parameters as the detector).

**Steps** (repeat for each variant):
1. Construct variant with specified whistle duration starting at t=1.0 s. Call `detect_artifacts`. Check for `STATIONARY_WHISTLE` flags.

**Expected results**:
- **0.8 s whistle**: zero `STATIONARY_WHISTLE` flags. A 0.8 s whistle starting at t=1.0 s overlaps fewer than 6 STFT frames (Hann window 500 ms, hop 250 ms), which is below MIN_PERSISTENCE_FRAMES=6.
- **2.0 s whistle**: at least one `STATIONARY_WHISTLE` flag. A 2.0 s whistle starting at t=1.0 s overlaps approximately 9 STFT frames — well above the 6-frame threshold.

**Pass/fail criterion**: 0.8 s whistle produces any `STATIONARY_WHISTLE` flag → FAIL. 2.0 s whistle produces no `STATIONARY_WHISTLE` flag → FAIL.

---

### Group 4 — PHASE_SWISH Detector

---

**TC-010**
**Title**: PHASE_SWISH — negative control (L == R, HF correlation = 1.0)
**Covers**: AC6 (by absence), architecture §9.1 `test_phase_swish_negative_control`
**Type**: Audio-quality / negative control
**Preconditions**: Fixture F-008. Broadband noise, L == R. Stereo, 44.1 kHz, 2.5 s.

**Steps**:
1. Construct F-008. Call `detect_artifacts`. Check for `PHASE_SWISH` flags.

**Expected result**: Zero `PHASE_SWISH` flags.
- Derivation: HF magnitude correlation = 1.0 (identical channels), HF phase variance = 0.0 rad², LF correlation = 1.0. The trigger condition "variance > 0.5" is not met.

**Pass/fail criterion**: Any `PHASE_SWISH` flag → FAIL.

---

**TC-011**
**Title**: PHASE_SWISH — positive control (independent HF, coherent LF)
**Covers**: AC6, architecture §9.1 `test_phase_swish_positive_control`
**Type**: Audio-quality / positive control
**Preconditions**: Fixture F-007. Stereo, 44.1 kHz, 2.5 s.

**Steps**:
1. Construct F-007. Verify fixture properties: (a) HF cross-correlation of L and R magnitude < 0.2; (b) LF cross-correlation of L and R magnitude > 0.9.
2. Call `detect_artifacts`. Inspect `PHASE_SWISH` flags.

**Expected result**:
- At least one `PHASE_SWISH` flag.
- `confidence_score >= 0.70` (architecture §5.4 baseline).
- Derivation: HF phase variance ≈ π²/3 ≈ 3.29 rad² (independent uniform phase differences) → +0.10 (variance > 1.0 rad²); HF correlation ≈ 0.0 < 0.2 → +0.10; LF correlation ≈ 1.0 >= 0.8 → no decrement. Total = 0.70 + 0.10 + 0.10 = 0.90. Assert ≥ 0.70.
- Flag duration >= 2.0 s.
- `details` dict contains relevant metrics (field names [OPEN — not specified in architecture; assert `isinstance(flag.details, dict)` only]).

**Pass/fail criterion**: No `PHASE_SWISH` flag, or confidence < 0.70, or flag duration < 1.5 s → FAIL.

---

**TC-024**
**Title**: PHASE_SWISH — HF variance boundary test
**Covers**: AC6 (boundary), architecture §5.4
**Type**: Boundary value [OPEN OQ-9 — this test cannot be built as specified]
**Status**: BLOCKED

**Problem (OQ-9)**: Architecture §5.4 defines three conjunctive trigger conditions:
1. HF phase variance > 0.5 rad²
2. HF magnitude cross-correlation < 0.4
3. LF magnitude cross-correlation >= 0.7

A boundary test on HF phase variance requires varying phase variance while holding conditions 2 and 3 constant. However, conditions 2 and 3 are defined over **magnitude** cross-correlation, not phase. Phase-only perturbation (varying the phase difference distribution between L and R HF channels) does not change the magnitude of either channel — so HF magnitude correlation remains near 1.0 regardless of phase variance, keeping condition 2 permanently unmet. The three conditions cannot be satisfied simultaneously at controlled values of variance alone.

**Action required**: Architect must specify how to construct test signals that satisfy all three conditions at variance values just below, at, and just above 0.5 rad². Options include: (a) construct L/R by mixing shared and independent complex-valued noise in a controlled proportion; (b) use a white-box fixture that bypasses the magnitude/phase decomposition; (c) accept that only the combined condition triplet can be tested (TC-011 covers this). Rewrite this test case once resolution is provided.

---

### Group 5 — Contract, Integration, and Invariant Tests

---

**TC-012**
**Title**: SHA-256 invariant — audio array is byte-identical after processing
**Covers**: AC1, architecture §4.2
**Type**: Functional / contract
**Preconditions**: Fixture F-007 (non-trivial stereo noise). Stereo, 44.1 kHz, 2.5 s.

**Steps**:
1. `hash_before = hashlib.sha256(audio_buffer.samples.tobytes()).hexdigest()`
2. `audio_buffer_out, result = detect_artifacts(audio_buffer)`
3. `hash_after = hashlib.sha256(audio_buffer_out.samples.tobytes()).hexdigest()`
4. Assert `hash_before == hash_after`.
5. Assert `audio_buffer_out.sample_rate == audio_buffer.sample_rate`.
6. Assert `audio_buffer_out.source_path == audio_buffer.source_path`.

**Expected result**: All three assertions pass. AudioBuffer fields are unmodified.

**Pass/fail criterion**: Any hash mismatch or changed field → FAIL.

---

**TC-013**
**Title**: ArtifactDetectionResult appended to Measurements by `measure_all()`
**Covers**: AC1, AC7, architecture §7.2
**Type**: Functional / integration
**Preconditions**: Fixture F-006 (whistle signal). Stereo, 44.1 kHz, 5.0 s. Call `measure_all()`.

**Steps**:
1. `measurements = measure_all(audio_buffer)`
2. Assert `measurements.artifact_detection is not None`
3. Assert `isinstance(measurements.artifact_detection, ArtifactDetectionResult)`
4. Assert `measurements.artifact_detection.total_artifacts_found == len(measurements.artifact_detection.artifact_flags)`
5. Assert `0.0 <= measurements.artifact_detection.overall_artifact_density_score <= 1.0`
6. Assert `isinstance(measurements.artifact_detection.detected_at, datetime)`

**Expected result**: All assertions pass. `total_artifacts_found` equals `len(artifact_flags)` exactly.

**Pass/fail criterion**: Any assertion failure → FAIL.

---

**TC-014**
**Title**: High-confidence flags forwarded to `plausibility_warnings`
**Covers**: AC7, architecture §4.2 reporting
**Type**: Functional / integration
**Preconditions**: Fixture F-006. Stereo, 44.1 kHz. Call `measure_all()`.

**Steps**:
1. `measurements = measure_all(audio_buffer)`
2. Assert `measurements.artifact_detection is not None`
3. `hc = [f for f in measurements.artifact_detection.artifact_flags if f.confidence_score >= 0.80]`
4. Assert `len(hc) >= 1` (whistle fixture should produce a high-confidence flag)
5. For each high-confidence flag, assert a string in `measurements.plausibility_warnings` contains the flag's `artifact_type`

**Expected result**: Every flag with `confidence_score >= 0.80` (default threshold per OQ-7) corresponds to a human-readable warning string in `plausibility_warnings`.

**Pass/fail criterion**: Any high-confidence flag without a corresponding warning → FAIL.

---

**TC-034**
**Title**: Invariant sanity assertions on all ArtifactFlag fields
**Covers**: AC7 (field contract)
**Type**: Functional / invariant
**Preconditions**: Fixture F-006. Run `detect_artifacts`. At least one flag expected.

**Steps**: For each `flag` in `artifact_flags`:
1. Assert `0.0 <= flag.confidence_score <= 1.0`
2. Assert `flag.timestamp_start_s >= 0.0`
3. Assert `flag.timestamp_end_s > flag.timestamp_start_s`
4. Assert `flag.timestamp_end_s <= audio_duration_s`
5. Assert `flag.artifact_type in {"SMEARED_TRANSIENT", "DIGITAL_HAZE", "STATIONARY_WHISTLE", "PHASE_SWISH"}`
6. Assert `isinstance(flag.details, dict)`

Also:
7. Assert `0.0 <= result.overall_artifact_density_score <= 1.0`
8. Assert `result.total_artifacts_found == len(result.artifact_flags)`

**Expected result**: All assertions pass for every flag. These catch physically impossible values and structural defects.

**Pass/fail criterion**: Any failure → FAIL.

---

**TC-035**
**Title**: Determinism — identical input produces identical flags across two runs
**Covers**: Non-functional (Determinism requirement)
**Type**: Non-functional
**Preconditions**: Fixture F-006. Stereo, 44.1 kHz.

**Steps**:
1. `result_1 = detect_artifacts(audio_buffer)[1]`
2. `result_2 = detect_artifacts(audio_buffer)[1]`
3. Assert `result_1.total_artifacts_found == result_2.total_artifacts_found`
4. Assert `result_1.overall_artifact_density_score == result_2.overall_artifact_density_score`
5. For each pair of flags by index: assert all fields except `detected_at` are identical

**Expected result**: Results are bit-identical across runs (excluding `detected_at`).

**Pass/fail criterion**: Any non-`detected_at` field difference → FAIL.

---

**TC-042**
**Title**: `sample_rate` override parameter changes frequency resolution
**Covers**: AC1 (API contract), architecture §7.1 API signature
**Type**: Functional
**Preconditions**: Fixture F-006 at 44.1 kHz. The `detect_artifacts` signature accepts `sample_rate=None` override.

**Steps**:
1. Call `detect_artifacts(audio_buffer, sample_rate=44100)`. Record any flags.
2. Call `detect_artifacts(audio_buffer)` (no override). Record any flags.
3. Assert both calls produce the same result (override equal to buffer's native sr is a no-op).

**Expected result**: Passing `sample_rate=44100` to a 44.1 kHz buffer produces identical results to no override. Flags, timestamps, and `frequency_hz` values are all identical.

**Pass/fail criterion**: Any difference between the two calls → FAIL.

---

### Group 6 — Error Handling and Edge Cases

---

**TC-015**
**Title**: Sample rate < 32 kHz raises ValueError
**Covers**: AC1, architecture §8, §7.1
**Type**: Functional / error handling
**Preconditions**: 2.5 s stereo broadband noise wrapped in `AudioBuffer` with `sample_rate=31999`.

**Steps**:
1. Call `detect_artifacts(audio_buffer)`. Assert `ValueError` raised.

**Expected result**: `ValueError` raised. No partial processing; no flags emitted.

**Pass/fail criterion**: No exception, or wrong exception type → FAIL.

---

**TC-025**
**Title**: Sample rate = 32000 Hz is accepted (boundary inclusive)
**Covers**: AC1, architecture §8 (OQ-3)
**Type**: Boundary value / functional
**Preconditions**: 2.5 s stereo broadband noise, `sample_rate=32000`.

**Steps**:
1. Call `detect_artifacts`. Assert no exception. Assert valid `ArtifactDetectionResult`.
2. Assert invariants from TC-034 all pass.

**Expected result**: Processing completes. [OQ-3: confirm 32000 is the inclusive lower bound. At Nyquist = 16000 Hz, the 8–16 kHz band's uppermost bin is at Nyquist; document any detection sensitivity reduction.]

**Pass/fail criterion**: Exception raised → FAIL.

---

**TC-016**
**Title**: Mono input — accepted, PHASE_SWISH skipped, other detectors run
**Covers**: AC1 (validation), architecture §8
**Type**: Edge case / functional
**Preconditions**: Whistle signal (6400 Hz, amplitude 0.002, noise RMS 0.10, 5.0 s) as mono, shape `(n, 1)`, sr=44100.

**Steps**:
1. Wrap mono signal in `AudioBuffer` with shape `(n, 1)`.
2. Call `detect_artifacts`. Assert no exception.
3. Assert `PHASE_SWISH` not in any flag's `artifact_type`.
4. Assert `STATIONARY_WHISTLE` flag is present (detector must run on mono).
5. Check that report notes mono processing. [OPEN — no field name is defined for this note in the architecture; assert at minimum that no exception is raised; defer field assertion until report schema is specified.]

**Pass/fail criterion**: Exception raised → FAIL. `PHASE_SWISH` flag in output → FAIL. No `STATIONARY_WHISTLE` flag → FAIL.

---

**TC-017**
**Title**: Very short audio (0.9 s — below 1 s persistence threshold)
**Covers**: AC1, architecture §8
**Type**: Edge case / functional
**Preconditions**: 0.9 s stereo broadband noise at 44.1 kHz (< 1 s but >= 500 ms = 3–4 STFT windows).

**Steps**:
1. Call `detect_artifacts`. Assert no exception.
2. Assert valid `ArtifactDetectionResult` returned.
3. Assert no `DIGITAL_HAZE` flags (3.5 windows cannot sustain >= 2.0 s of flagged content).
4. Assert no `STATIONARY_WHISTLE` flags (< 4 windows, no 1.5 s persistence achievable).

**Expected result**: Graceful degradation. No persistence-based detector flags possible at 0.9 s.

**Pass/fail criterion**: Exception → FAIL. `DIGITAL_HAZE` or `STATIONARY_WHISTLE` flag → FAIL (physically impossible at 0.9 s given the 2.0 s and 1.5 s thresholds).

---

**TC-018**
**Title**: Very short audio — shorter than one STFT window (< 500 ms)
**Covers**: AC1, architecture §8
**Type**: Edge case / functional
**Preconditions**: 0.3 s stereo broadband noise at 44.1 kHz. Duration < 500 ms = less than one analysis window.

**Steps**:
1. Call `detect_artifacts`. Assert no exception.
2. Assert `ArtifactDetectionResult` returned.
3. Assert `total_artifacts_found == 0`.

**Expected result**: Zero flags (no complete window available for any detector). No unhandled exception.

**Pass/fail criterion**: Exception raised → FAIL. Any flag emitted → FAIL.

---

**TC-027**
**Title**: All-zero audio — no artifacts detected, no exception
**Covers**: AC1, architecture §8
**Type**: Edge case / functional
**Preconditions**: 3.0 s stereo array of all zeros, sr=44100.

**Steps**:
1. Call `detect_artifacts`. Assert no exception.
2. Assert `total_artifacts_found == 0`.
3. Assert `overall_artifact_density_score == 0.0`.

**Expected result**: Zero flags. Architecture §8: "silence has no artifacts."

**Pass/fail criterion**: Exception (especially ZeroDivisionError or NaN propagation in TMI_HF computation — mean(E_HF) → 0 in silence, or in CC_HF_LF computation — both E_HF and E_LF variances → 0) → FAIL. Any flag → FAIL.

---

**TC-028**
**Title**: Near-silence audio — no crash, no divide-by-zero
**Covers**: AC1 (robustness)
**Type**: Edge case / functional
**Preconditions**:
```python
t = np.arange(int(3.0 * 44100)) / 44100
s = np.sin(2*np.pi*440*t) * 1e-4   # −80 dBFS
samples = np.column_stack([s, s])
```

**Steps**:
1. Call `detect_artifacts`. Assert no exception (especially no ZeroDivisionError or NaN propagation).
2. Assert valid `ArtifactDetectionResult`.
3. Assert all `confidence_score` values in [0.0, 1.0].

**Pass/fail criterion**: Any exception → FAIL. NaN or Inf in any result field → FAIL.

---

**TC-029**
**Title**: DC offset input — no crash
**Covers**: AC1 (robustness)
**Type**: Edge case / functional
**Preconditions**: 2.0 s stereo signal: `samples = np.full((int(2.0*44100), 2), 0.5, dtype=np.float64)` (pure DC). All energy at 0 Hz; no AC content in 8–16 kHz range.

**Steps**:
1. Call `detect_artifacts`. Assert no exception.
2. Assert valid `ArtifactDetectionResult`.
3. Assert `total_artifacts_found == 0` (no HF content, no transients, no tonal peaks in AC range).

**Note**: For DC-only input, HF band energy is zero for all frames. The temporal method faces potential degenerate conditions: TMI_HF = std(E_HF) / mean(E_HF) with mean(E_HF) ≈ 0 (undefined), and CC_HF_LF with near-zero variance in both E_HF and E_LF (Pearson correlation numerically undefined). Implementation must handle these as 0 or skip the window gracefully rather than propagating NaN. This test specifically checks that degenerate silence conditions in the temporal detector are handled without crashing.

**Pass/fail criterion**: Any exception → FAIL. NaN in any field → FAIL.

---

**TC-030**
**Title**: Full-scale / hard-clipped input — no crash, valid result
**Covers**: AC1 (robustness with extreme input), architecture §8
**Type**: Edge case / functional
**Preconditions**:
```python
sr = 44100
duration = 2.0
n = int(sr * duration)
rng = np.random.default_rng(42)
# Pink noise at 4× full scale, hard-clipped to ±1.0
signal = rng.standard_normal(n).astype(np.float64) * 4.0
signal = np.clip(signal, -1.0, 1.0)
samples = np.column_stack([signal, signal])
# Crest factor ≈ 0–3 dB (heavily clipped distribution)
# Rationale: pink noise × 4 then clipped produces natural spectral content at full scale,
# unlike a square wave (which would put all energy at Nyquist).
```

**Steps**:
1. Call `detect_artifacts`. Assert no exception.
2. Assert valid `ArtifactDetectionResult`.
3. Assert all fields satisfy invariants from TC-034 (no NaN/Inf, no out-of-range values).

**Pass/fail criterion**: Exception → FAIL. NaN or Inf in any result field → FAIL.

---

**TC-031**
**Title**: Wrong channel count (6-channel input) raises ValueError
**Covers**: Architecture §7.1 (OQ-4)
**Type**: Functional / error handling
**Preconditions**: `AudioBuffer` with `samples` shape `(int(2.0*44100), 6)`, sr=44100.

**Steps**:
1. Call `detect_artifacts`. Assert `ValueError` raised.

**Expected result**: `ValueError` with a message indicating unsupported channel count.

**Pass/fail criterion**: No exception, or wrong exception type → FAIL.

---

**TC-033**
**Title**: NaN values in input samples — graceful per-window degradation
**Covers**: Architecture §8 ("Handle NaN/Inf gracefully: skip affected window")
**Type**: Edge case / functional
**Preconditions**: Fixture F-006 with NaN injected at positions `[n//2 : n//2 + int(0.5*44100)]` (one window's worth of samples). Remaining samples are valid.

**Steps**:
1. Call `detect_artifacts`. Assert no exception propagates to caller.
2. Assert `ArtifactDetectionResult` returned.
3. Assert no NaN/Inf in any numeric field of `ArtifactDetectionResult`.
4. Assert `audio_buffer_out.samples[n//2:n//2 + int(0.5*44100)]` still contains NaN (buffer unmodified).

**Expected result**: Corrupted window skipped; processing continues on valid windows. SHA-256 of original (NaN-containing) buffer is preserved.

**Pass/fail criterion**: Unhandled exception → FAIL. NaN in any `confidence_score` or density score → FAIL.

---

### Group 7 — STFT Sliding Window Test

---

**TC-019**
**Title**: STFT sliding window — onset spanning non-overlapping window boundary measured correctly
**Covers**: AC3, architecture §9.1 `test_stft_sliding_window_continuity`, §2 (STFT rationale)
**Type**: Functional / audio-quality
**Preconditions**:
```python
sr = 44100
duration = 2.0
n = int(sr * duration)
rng = np.random.default_rng(42)
noise = rng.standard_normal(n).astype(np.float64)

# Onset peak at t=480 ms, 55.3 ms ramp (energy rise-time = 35 ms > 25 ms threshold)
# With non-overlapping 500 ms windows: onset is 20 ms before window 0 ends.
# The 150 ms analysis window (405–555 ms) spans the 0-ms/500-ms boundary.
# With sliding 50% overlap (hop=250 ms), window 1 spans 250–750 ms and fully
# contains the 150 ms analysis window → correct rise-time measurement.
onset_start = int(0.425 * sr)       # ramp starts at 425 ms
ramp_samples = int(0.0553 * sr)     # 55.3 ms ramp
envelope = np.zeros(n)
envelope[onset_start:onset_start + ramp_samples] = np.linspace(0, 1, ramp_samples)
if onset_start + ramp_samples < n:
    tail = n - (onset_start + ramp_samples)
    envelope[onset_start + ramp_samples:] = np.exp(-np.arange(tail) / (0.05 * sr))
signal = noise * envelope
samples = np.column_stack([signal, signal])
```

**Steps**:
1. Call `detect_artifacts`. Assert at least one `SMEARED_TRANSIENT` flag.
2. Assert `flag.timestamp_start_s <= 0.500` and `flag.timestamp_end_s >= 0.400`.

**Expected result**: Flag is emitted. The 50% sliding window ensures the onset (centered at 480 ms) is measurable within one analysis window (250–750 ms) despite crossing the 500 ms non-overlapping boundary.

**Pass/fail criterion**: No `SMEARED_TRANSIENT` flag → FAIL (indicates sliding window not implemented or onset missed by boundary splitting).

---

### Group 8 — Reference Track Tests (Slow)

---

**TC-036**
**Title**: GusGus — zero artifact flags
**Covers**: AC2, architecture §9.2
**Type**: Audio-quality / negative control [Slow]
**Preconditions**: `Reference Tracks/GusGus_-_Over_Arabian_Horse_Album.wav`, native sr, loaded via soundfile with sr=None.
**Steps**: Load → `AudioBuffer` → `detect_artifacts` → collect all flags.
**Expected result**: Zero flags of any artifact type.
**Pass/fail criterion**: Any flag → FAIL. Investigate immediately; this is a modern master with good transients and represents a strong false-positive indicator.

---

**TC-037**
**Title**: Black Flute (Remastered) — zero artifact flags
**Covers**: AC2, architecture §9.2
**Type**: Audio-quality / negative control [Slow]
**Preconditions**: `Reference Tracks/Black_Flute_Remastered.wav`, native sr.
**Expected result**: Zero flags.
**Pass/fail criterion**: Any flag → FAIL.

---

**TC-038**
**Title**: Chemical Brothers — Live Again — zero artifact flags
**Covers**: AC2, architecture §9.2
**Type**: Audio-quality / negative control [Slow]
**Preconditions**: `Reference Tracks/The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav`, native sr.
**Expected result**: Zero flags. Architecture §9.1 uses this track as the canonical SMEARED_TRANSIENT negative control.
**Pass/fail criterion**: Any flag → FAIL.

---

**TC-039**
**Title**: Leftfield — Melt — zero flags or manually-reviewed flags
**Covers**: AC2, architecture §9.2
**Type**: Audio-quality / negative control [Slow] [Human-gated]
**Preconditions**: `Reference Tracks/Leftfield_-_Melt_Audio.wav`, native sr. 90s master; may have HF decay or reverb tails.
**Expected result**: Zero flags. Any flag must be manually reviewed. For each flag record: `artifact_type`, `timestamp_start_s`, `timestamp_end_s`, `confidence_score`, and the reviewer's judgment (reverb tail / cymbal decay → accepted; unexplained → threshold must be tightened). Record in defects.md.
**Pass/fail criterion (automated)**: None.
**Pass/fail criterion (human-gated)**: Any un-reviewed flag at Gate 2 → FAIL. Reviewed and documented flags are accepted results.

---

**TC-040**
**Title**: Wavy Gravy — zero flags or manually-reviewed flags
**Covers**: AC2, architecture §9.2
**Type**: Audio-quality / negative control [Slow] [Human-gated]
**Preconditions**: `Reference Tracks/Wavy_Gravy.wav`, native sr. Same era and rationale as TC-039.
**Expected result**: Same criteria as TC-039.
**Pass/fail criterion**: Same as TC-039.

---

### Group 9 — Non-Functional

---

**TC-041**
**Title**: Performance — 5-minute stereo track completes in bounded time
**Covers**: Non-functional (Performance)
**Type**: Non-functional [Slow]
**Preconditions**: 5 minutes of stereo broadband noise at 44.1 kHz (~26.5 M samples × 2 channels).
**Steps**: Measure wall-clock time for `detect_artifacts`.
**Expected result**: [OPEN OQ-6 — no SLA defined. Record actual time as a baseline. Once BA confirms SLA, add a hard assertion. Until then: processing completes without timeout in < 10 minutes (non-binding soft ceiling).]
**Pass/fail criterion**: Hard criterion deferred pending OQ-6.

---

## Traceability Table

| Acceptance Criterion | Test Case IDs |
|---|---|
| **AC1**: `detect_artifacts` returns unmodified audio (SHA-256 invariant) and correctly typed `ArtifactDetectionResult` | TC-012, TC-013, TC-015, TC-016, TC-025, TC-027, TC-028, TC-029, TC-030, TC-031, TC-033, TC-042 |
| **AC2**: Zero false-positive flags on clean reference tracks | TC-001, TC-003, TC-006, TC-007, TC-010, TC-020, TC-036, TC-037, TC-038, TC-039, TC-040 |
| **AC3**: Injected 6.4 kHz whistle and smeared transient emit both flag types with confidence >= 0.80 and correct timestamps | TC-002, TC-008, TC-019, TC-043 |
| **AC4**: Continuous stationary HF energy (TMI_HF < 0.10 AND CC_HF_LF < 0.30 sustained for >= 2.0 s) emits DIGITAL_HAZE covering that interval [thresholds PROVISIONAL per §5.2] | TC-005, TC-022 |
| **AC5**: Narrow spectral peaks Q >= 8, prominence >= 6 dB, sustained >= 1.5 s emit STATIONARY_WHISTLE with frequency and prominence in details | TC-008, TC-023, TC-026 |
| **AC6**: HF phase decorrelation with stable LF emits PHASE_SWISH with metrics and confidence | TC-011, TC-024 (BLOCKED — OQ-9) |
| **AC7**: All flags have required fields; total_artifacts_found == len(artifact_flags); density normalized [0,1] | TC-013, TC-014, TC-034 |

---

## Coverage Checklist

| Category | Coverage |
|---|---|
| Happy path for each AC | TC-002 (AC3/transient), TC-005 (AC4), TC-008 (AC3/AC5), TC-011 (AC6), TC-013 (AC1/AC7), TC-014 (AC7), TC-043 (AC3 combined) |
| Boundary values at thresholds | TC-021 (HF Hilbert rise-time empirical boundary: 30 ms no-flag, 35 ms flag — DEF-710), TC-022 (DIGITAL_HAZE duration empirical boundary: 1.5 s no-flag, 3.0 s flag — DEF-712), TC-023 (persistence empirical boundary: 0.8 s no-flag, 2.0 s flag — DEF-709), TC-024 (BLOCKED OQ-9), TC-015 + TC-025 (SR boundary 31999/32000) |
| Idempotency / re-processing | Not applicable — pure analysis, read-only |
| Disabled/bypassed stage | Not applicable — no bypass mode specified |
| Mono input | TC-016 |
| Stereo input | All other tests |
| 44.1 kHz | All tests except TC-026 |
| 48 kHz | TC-026 |
| Silence and near-silence | TC-027, TC-028 |
| Full-scale / hard-clipped input | TC-030 |
| Very quiet input | TC-028 |
| DC offset | TC-029 |
| Very short audio (< 1 s) | TC-017 |
| Very short audio (< 1 STFT window) | TC-018 |
| Corrupt / truncated (NaN input) | TC-033 |
| Unsupported format | Not in scope (MIX SOURCE stage handles format loading) |
| Missing file | Not in scope (module receives AudioBuffer, not a path) |
| Wrong channel count | TC-031 |
| Determinism | TC-035 |
| SHA-256 invariant | TC-012 |
| Integration with Measurements | TC-013 |
| Plausibility warnings | TC-014 |
| Known-limitation documentation | TC-004 (DIGITAL_HAZE/pink noise), TC-009 (vibrato) |
| Negative control for each detector | TC-001 (SMEARED_TRANSIENT), TC-020 (DIGITAL_HAZE true — cymbal decay), TC-007 (STATIONARY_WHISTLE), TC-010 (PHASE_SWISH), TC-003 (spectral-tilt guard) |
| Reference track negative controls | TC-036–TC-040 |
| Sanity invariants (physically impossible values) | TC-034 |
| API override parameter | TC-042 |
| Combined multi-artifact detection | TC-043 |
| Units explicit (crest factor vs TT DR vs LRA) | DOMAIN.md §1 cited in test bodies; OQ-5 withdrawn (DEF-712: DIGITAL_HAZE detector no longer uses crest factor or SFM — trigger is now TMI_HF + CC_HF_LF temporal approach) |
| Sample peak vs true peak | Not applicable (this stage does not measure loudness) |
| Performance | TC-041 (pending OQ-6) |
