# STORY-007: Suno Artifact Detection — Architecture

**Status**: Closed for implemented detector work. The defect and calibration work is complete and QA-validated. Remaining BA/spec items are formally deferred as follow-on backlog work rather than active defects. DEF-701, DEF-702, DEF-703, DEF-705, DEF-712, and the Gate 2 blockers were resolved in the architecture and defect ledger; §5.1 HF-presence gate revised from crest factor to energy-level test 2026-08-14.

---

## 1. Overview

Artifact detection is a **pure analysis stage** that appends diagnostic flags to the `Measurements` structure without modifying the audio buffer. It runs as part of the Stage 2 analysis pass (per `docs/ARCHITECTURE.md` §2), consuming the same audio array that feeds loudness and spectral analysis, and returns the audio array byte-identical to the input.

The module applies four targeted heuristic detectors over a sliding-window STFT to flag transient smearing, high-frequency digital haze, stationary whistles, and inter-channel phase decorrelation. Flags carry timestamps, confidence scores, and diagnostic details. High-confidence findings are forwarded to the `plausibility_warnings` list in `Measurements` for human review.

**Story closeout note**: The implemented artifact-detection work is complete and QA-verified. The remaining items in this architecture are deferred BA/requirements follow-ups and optional enhancements, not active defects in the detector itself.

---

## 2. Pipeline Design

```
Artifact Detection Stage (pure analysis)

Input: (audio: np.ndarray [float64, shape (n_samples, n_channels)], sr: int)
  ▼
┌─ Pre-flight checks ─────────────────┐
│ • Validate sample rate              │
│ • Confirm channel count (1 or 2)    │
│ • Assert audio unmodified (hash)    │
└─────────────────┬───────────────────┘
                  ▼
┌─ STFT preparation ─────────────────┐
│ • Window duration: 500 ms (default) │
│ • FFT size: nfft = nperseg (1×)     │
│ • Hop: 250 ms (50% overlap)         │
│ • Window function: Hann             │
│ • Magnitude + phase extraction      │
└─────────────────┬───────────────────┘
                  ▼
┌─ Four parallel detectors ──────────┐
│ 1. Transient smearing (attack time)│
│ 2. Digital haze (HF temporal stat) │
│ 3. Stationary whistle (persistence)│
│ 4. Phase swish (HF decorrelation)  │
└─────────────────┬───────────────────┘
                  ▼
┌─ Aggregation & filtering ──────────┐
│ • Merge adjacent flags              │
│ • Compute overall artifact density  │
│ • Filter by confidence threshold    │
└─────────────────┬───────────────────┘
                  ▼
┌─ Output & reporting ───────────────┐
│ • Append ArtifactDetectionResult    │
│ to Measurements.artifact_detection  │
│ • Forward high-confidence to        │
│ plausibility_warnings               │
│ • Return audio (unmodified)         │
└─────────────────────────────────────┘
```

**STFT windowing rationale**: Sliding windows (50% overlap, hop = 250 ms) avoid boundary artifacts and permit accurate transient rise-time measurement across window edges. Non-overlapping windows would cause onsets spanning two frames to have ambiguous rise-time; sliding windows resolve this by allowing smooth tracking through the entire attack phase.

---

## 3. Library Choices & Justification

| Task | Library | Why | Not |
|---|---|---|---|
| **STFT & magnitude/phase** | `scipy.signal.stft()` | Mature, standard. Returns magnitude and phase in one call; efficient for real-time windowing with flexible hop size. | `librosa.stft()` resamples to 22050 Hz by default (silent data loss). |
| **Spectral peak detection** | `scipy.signal.find_peaks()` | Reliable peak/prominence extraction for whistle detection. | Hand-rolled peak search is fragile and slow. |
| **Resampling (for oversampling in phase analysis)** | `scipy.signal.resample_poly()` | Polyphase filter for high-quality resampling without distortion. | `numpy.interp` produces artifacts; direct FFT padding is slower. |
| **Loudness/dynamics reference** | Use existing `pyloudnorm` and `analysis/_psd.py` | Reuse existing calibration; no new dependency. | Do not re-implement LUFS or spectral analysis. |
| **Temporal windowing & persistence tracking** | NumPy — `_find_consecutive_runs()` helper (pure numpy run-length function) | `pandas` is **not** installed in this project and is not a listed dependency. Numpy loop with equivalent semantics to rolling window. DEF-703: pandas reference removed. | ~~`pandas.Series.rolling()`~~ — not available; do not add as a dependency. |

**Out of scope for this story**:
- `pedalboard` is **not** used here. Artifact detection measures and flags; it does not process audio (no Compressor, Limiter, filters applied to the signal path).
- VST3/AU plugin hosting (parked per `CLAUDE.md` §2).
- Reconstruction of the continuous waveform for inter-sample peak detection (handled by the loudness/true-peak stage).

---

## 4. Data Contracts

### 4.1 Input: Plain-array contract (DEF-701 resolution)

**DEF-701 resolution — Option (b) applied, conflict with `docs/ARCHITECTURE.md` raised**:

`docs/ARCHITECTURE.md` §3.1 defines `AudioBuffer` as the standard contract for the ANALYSIS stage input. However, the STORY-001 implementation (the existing analysis pipeline this story extends) uses plain `numpy.ndarray + int` arguments throughout, with signature `measure_all(audio, sr, config)`. This is a pre-existing deviation from `docs/ARCHITECTURE.md §3.1` in the codebase.

**This architecture adopts Option (b)** — plain-array contract — to remain consistent with the existing pipeline convention. Introducing `AudioBuffer` only for STORY-007 while the rest of the analysis code uses plain arrays would create an inconsistent calling convention within the same module.

**Conflict requiring project-level resolution**: `docs/ARCHITECTURE.md §3.1` specifies `AudioBuffer` as the stage contract. The actual codebase uses `(np.ndarray, int)`. This conflict should be resolved at the project level (either migrate STORY-001's analysis code to accept `AudioBuffer`, or update `docs/ARCHITECTURE.md §3.1` to reflect the plain-array convention). This architecture does not resolve the project-level conflict; it merely adopts the existing codebase convention to avoid adding a new inconsistency.

**Plain-array contract for this stage**:

```python
# Input contract (consistent with analysis/measure_all(audio, sr, config))
audio: np.ndarray   # float64, shape (n_samples, n_channels); n_channels in {1, 2}
sr: int             # sample rate in Hz; must be >= 32000

# Guarantees:
# - audio is read-only; no in-place modifications permitted
# - input array SHA-256 hash is identical on return
# - channel count must be 1 (mono) or 2 (stereo); > 2 channels raises ValueError
```

### 4.2 Output: ArtifactDetectionResult (appended to Measurements)

**Dataclass additions to `analysis/types.py`** (already implemented, no changes needed):

```python
@dataclass
class ArtifactFlag:
    """A single detected artifact with time window and diagnostic."""
    timestamp_start_s: float      # Window start, seconds
    timestamp_end_s: float        # Window end, seconds
    artifact_type: str            # "SMEARED_TRANSIENT" | "DIGITAL_HAZE" | "STATIONARY_WHISTLE" | "PHASE_SWISH"
    confidence_score: float       # 0.0 to 1.0
    details: dict                 # Type-specific: {"frequency_hz": float, "prominence_db": float, "q_factor": float, ...}

@dataclass
class ArtifactDetectionResult:
    """Summary and list of detected artifacts."""
    total_artifacts_found: int
    artifact_flags: list[ArtifactFlag]
    overall_artifact_density_score: float  # 0.0 (clean) to 1.0 (heavily degraded)
    detected_at: datetime
```

**Integration into Measurements** (already implemented, no changes needed):

```python
@dataclass
class Measurements:
    # ... existing fields ...
    artifact_detection: ArtifactDetectionResult | None  # Added field
    plausibility_warnings: List[str]                     # High-confidence flags forwarded here
```

- If artifact detection is skipped (e.g., unsupported sample rate), `artifact_detection` is `None`.
- High-confidence flags (confidence >= threshold, default 0.8) are formatted and added to `plausibility_warnings` as human-readable strings (e.g., `"STATIONARY_WHISTLE detected at 01:14 (6.4 kHz, confidence 0.88) — consider re-generating track"`).

---

## 5. Detector Specifications

### 5.1 SMEARED_TRANSIENT (Attack Sharpness — HF-Bearing Onsets)

**Rationale**: Transient smearing is a characteristic Suno artifact — percussive onsets lack high-frequency detail and onset rise-time is unnaturally slow. The detector gates on HF energy presence first (to exclude kick drums and other events with no significant HF content), then uses the rise-time measurement as the sole discriminator between normal and smeared onsets.

**Important design constraint**: the HF-presence gate does **not** discriminate between percussive and vocal onsets. It is a level test: events whose HF-band RMS in the 30 ms anchor window exceeds the local HF noise floor by a sufficient margin pass; events with near-silent HF energy (kicks, low-frequency-only content) fail because their HF-band RMS is indistinguishable from the local noise floor. The gate therefore only excludes events with no meaningful HF energy; the rise-time measurement alone carries the full discrimination burden between normal and smeared onsets. If the 25 ms rise-time threshold produces false positives on reference tracks (vocal sibilants or other natural HF content), the threshold must be raised — not the gate ratio.

**DEF-705 Issue A resolution — Method change**: Added HF-presence gate before rise-time measurement. The previous implementation applied rise-time measurement to ALL spectral flux peaks regardless of onset type, causing false positives on vocal phrase starts (Chemical Brothers: 8 remaining SMEARED_TRANSIENT flags at vocal phrase starts). This is a **method change**, not a parameter change: the method now gates on HF energy presence before measuring rise-time. `requirements.md` line 22 specifies "use spectral flux + local crest factor on percussive onsets." This architecture deviates from that literal criterion: crest factor is not implemented because CF is scale-invariant and cannot detect absence of HF energy regardless of threshold value (per `mastering-review-lcf-haze.md` §5.1 BLOCKER). The energy-level gate serves the intent of the criterion — gating onsets before rise-time measurement — but not its specified metric. The BA must update requirements.md line 22 to specify the HF-presence energy test; see §10.3 item 9.

**Note on rise-time window geometry**: The 150 ms analysis window centred on the anchor provides approximately 75 ms of backward runway before the anchor. `_measure_risetime()` walks backward from the HF envelope peak; any onset whose 10% crossing falls more than ~75 ms before the peak returns `None` and is silently excluded (not measured, not flagged). This is acceptable behaviour — excluded onsets lie well outside the Suno smearing range (25–50 ms), and Suno-smeared transients with rise-time above ~75 ms would not represent the typical artifact. The effective maximum measurable rise-time is **~75 ms**, not 150 ms.

**Method**:
1. Compute spectral flux from STFT magnitude frames: `flux[t] = mean(max(|X[t]| − |X[t-1]|, 0))` in dB. Identify onset candidates as local maxima of `flux_db` with prominence >= 6 dB.
   - Edge handling: the first and last flux entries have no neighbours and are not returned by `scipy.signal.find_peaks`. Apply an explicit first-frame threshold check: if `flux_db[0] > 6 dB` treat it as an onset candidate (DEF-711 fix). Same at the tail.
2. For each onset candidate at flux peak frame `t_onset`:
   a. **HF-presence gate** — compare HF-band RMS energy in a 30 ms window against the local HF noise floor.
      - **Onset localisation**: within the flux frame's time span, find the sample of maximum HF envelope amplitude by applying the same 6–16 kHz bandpass filter used by `_hf_envelope()` to isolate the band, then locating the sample index of the peak envelope amplitude. Centre the 30 ms gate window on this sample — not on the frame midpoint. The rise-time measurement window (Step 3) must use the same sample as its anchor. Both the HF-presence gate and the rise-time measurement are localised to the same HF envelope peak.
      - **HF-band RMS in window**: `HF_RMS_window = rms(hf_audio[30ms_window])` where `hf_audio` is the 6–16 kHz bandpassed time-domain signal, and the 30 ms window is centred on the localisation anchor found above. This 30 ms window is tile 0.
      - **Local HF noise floor**: tile non-overlapping 30 ms sub-windows outward from the anchor in both directions — tile 0 is the anchor window (numerator). Extend to approximately ±16 tiles (±480 ms), giving approximately 32 floor tiles spanning ~960 ms total. `local_hf_floor = median(rms(hf_audio[tile_k]) for k in floor_tiles)` — tile 0 is **excluded** from the median to prevent the onset from contaminating the floor estimate. At track boundaries (fewer tiles available in one direction), use all available tiles in both directions combined — minimum 1 floor tile required. Guard against all-zero audio: `local_hf_floor = max(raw_median, numpy.finfo(numpy.float64).tiny)` to prevent division by zero.
      - **Estimator note — do not reuse `E_HF` from §5.2**: §5.2 defines `E_HF[t]` over the 8–16 kHz band at 250 ms hop granularity (STFT-magnitude domain). The gate band here is 6–16 kHz, and the sub-window granularity is 30 ms (time-domain). Reusing §5.2's `E_HF` would reintroduce the band mismatch that was the §5.1 BLOCKER resolved in the prior revision. Compute the 6–16 kHz time-domain RMS independently for this gate.
      - **Estimator compatibility requirement**: numerator (`HF_RMS_window`) and denominator (`local_hf_floor`) must be the same quantity — time-domain RMS of the 6–16 kHz bandpassed signal, differing only in the span of audio they cover. This ensures the ratio `HF_RMS_window / local_hf_floor` is dimensionless and meaningful. Do not mix time-domain RMS (numerator) with STFT-magnitude energy (denominator).
      - If `HF_RMS_window <= local_hf_floor * _ONSET_HF_PRESENCE_RATIO`: skip this onset — **not an HF-bearing event** (HF energy indistinguishable from local noise floor). Do not measure rise-time.
      - If `HF_RMS_window > local_hf_floor * _ONSET_HF_PRESENCE_RATIO`: HF energy is present above the local noise floor. Proceed to rise-time measurement. This includes both percussive and vocal onsets with meaningful HF content.
3. For each onset passing the HF-presence gate:
   - Extract a 150 ms window centred on the HF envelope peak sample identified in Step 2a (the same localisation anchor used for the HF-presence gate). The window provides ~75 ms of backward runway before the anchor; onsets whose 10% envelope crossing is more than ~75 ms before the anchor return `None` from `_measure_risetime()` and are silently excluded.
   - Pre-pad by `smooth_n` samples of prior audio before calling `_hf_envelope()` to avoid edge saturation (DEF-707 fix). Trim pre-padding before calling `_measure_risetime()`.
   - Compute energy evolution in the high-frequency band (6–16 kHz) within this window using Hilbert amplitude envelope.
   - Measure **onset rise-time**: elapsed time from 10% to 90% of peak HF envelope energy.
4. **Trigger**: flag if HF-presence gate passed AND onset rise-time > 25 ms.

**Constants derivation**:
- **_ONSET_HF_PRESENCE_RATIO = 3.0 (linear amplitude ratio; `20·log10(3.0) = 9.5 dB` above local HF noise floor — the mastering-engineer review specifies "approximately +10 dB")**: Derivation — the gate must separate two classes:
  - Near-silent HF (kick drum): no signal energy in 6–16 kHz → `HF_RMS_window` is dominated by the local noise floor → `HF_RMS_window ≈ local_hf_floor` → ratio ≈ 1.0.
  - HF-bearing onset (vocal sibilant, snare, cymbal, synth): signal energy well above the noise floor → `HF_RMS_window >> local_hf_floor` → ratio >> 1.0.
  - Derivation of margin adequacy: the relative standard deviation of an RMS estimate computed over N independent samples is approximately `1/sqrt(2N)`. For a 30 ms sub-window at 6–16 kHz bandwidth (BW = 10 kHz), the number of approximately independent samples is N ≈ 2·BW·T = 2 × 10000 × 0.030 = 600, giving relative std ≈ `1/sqrt(1200)` ≈ 2.9% ≈ 3%. A kick drum's `HF_RMS_window / local_hf_floor` ratio will therefore be approximately 1.0 ± a few percent — far below 3.0. A ratio of 3.0 (≈ +9.5 dB) provides more than 10 standard deviations of separation from the noise-floor estimator noise for the kick-drum class.
  - This is a self-normalising level comparison — the local floor estimate adapts to the track's actual noise floor, making the gate robust across tracks with different absolute noise levels.
  - **HF-dense passage limitation**: in passages with sustained broadband HF activity (e.g., hi-hat-heavy sixteenths, open cymbal wash), the ~1 s tile neighbourhood median reflects the sustained HF signal level rather than a noise floor. A snare onset within such a passage must produce `HF_RMS_window > 3 × (sustained HF activity level)`, which it may not achieve at moderate attack levels relative to the wash. This is a **false-negative risk only** — kick drum rejection still functions correctly regardless, because kicks have near-zero HF energy in all contexts. See §10.1 item 8. The PROVISIONAL validation step must include measurement in HF-dense passages to determine whether the ratio or the floor-estimation window requires adjustment.
  - **PROVISIONAL — requires validation**: after implementation, measure `HF_RMS_window / local_hf_floor` for kick drum onsets (expected ≈ 1.0) and for HF-bearing onsets (expected > 3.0) on the reference tracks. Measure the ratio distribution in HF-dense passages (hi-hat patterns, cymbal washes) as well as isolated onsets to assess false-negative rate. If HF-bearing onsets within dense HF contexts fall below 3.0, the ratio must be lowered or the floor-estimation window widened. Flag for mastering engineer.
- **25 ms rise-time threshold**: Measured on synthetic percussive attacks:
  - Normal acoustic transients: rise-time 5–15 ms (sharp energy envelope buildup)
  - Suno-generated onsets: rise-time 25–50 ms (decoder produces inherent blur on fast transients)
  - 25 ms chosen as clean separation. Empirical; requires validation on reference set.
  - Note: boundary at 30–35 ms ramp duration in terms of HF Hilbert envelope (DEF-710 finding). The HF Hilbert metric is not identical to STE rise-time; the 25 ms target is the HF Hilbert 10%–90% time, not the STE 10%–90% time.
  - **Escalation rule**: if post-implementation reference track measurement shows false positives on vocal onsets or sustained HF content, raise `ONSET_RISETIME_THRESHOLD_MS`. Do not raise `_ONSET_HF_PRESENCE_RATIO` — the 3.0 ratio already sits well above the noise-floor estimator noise (§ derivation above). Raising the ratio risks excluding genuine HF-bearing onsets at modest signal levels above the floor.

**Confidence calculation**:
- rise-time 25–30 ms: confidence 0.75
- rise-time 30–40 ms: confidence 0.85
- rise-time > 40 ms: confidence 0.95

**Testability**:
- **Negative control (no HF energy — gate rejection)**: Synthetic vocal-like onset with energy concentrated in 200–3000 Hz formants, near-zero energy in 6–16 kHz. Expected: `HF_RMS_window ≈ local_hf_floor` → ratio ≈ 1.0 << `_ONSET_HF_PRESENCE_RATIO` → HF-presence gate fails → no rise-time measurement → 0 flags. Note: this control tests gate rejection of events with no HF energy. It does **not** test percussive-vs-vocal discrimination — that is carried by the rise-time threshold.
- **Negative control (vocal sibilant — gate pass, rise-time discriminates)**: Synthetic /s/ onset with broadband HF content in 6–16 kHz at natural rise-time (< 25 ms). Expected: `HF_RMS_window >> local_hf_floor` → ratio >> `_ONSET_HF_PRESENCE_RATIO` → HF-presence gate passes; rise-time < 25 ms → 0 flags. This is the control that verifies the rise-time threshold carries the discrimination burden.
- **Negative control (kick drum — gate rejection)**: Kick drum equivalent: sharp impulse with energy concentrated below 5 kHz, near-zero energy in 6–16 kHz. Expected: `HF_RMS_window ≈ local_hf_floor` → ratio ≈ 1.0 → gate fails → no rise-time measurement → 0 flags.
- **Negative control (sharp percussive HF transient)**: Snare or cymbal equivalent: sharp HF-band impulse with strong HF energy (8 ms HF rise-time). Expected: `HF_RMS_window >> local_hf_floor` → ratio >> `_ONSET_HF_PRESENCE_RATIO` → gate passes, rise-time < 25 ms → 0 flags.
- **Positive control**: Synthetic percussive onset with broadband HF content (HF RMS well above local noise floor) and 35 ms HF Hilbert rise-time. Expected: gate passes, flag with confidence 0.85.
- **Stale-count notice**: Chemical Brothers DEF-705 counts (8 SMEARED_TRANSIENT post DEF-707 fix) are pre-discrimination-gate. All reference tracks must be re-measured after this fix (Gate 2 §Finding 4). GusGus and Leftfield counts are pre-fix figures.

---

### 5.2 DIGITAL_HAZE (HF Temporal Stationarity + LF Decoupling)

**Rationale**: Suno's generative model produces an independent, stationary noise floor in the high-frequency band. This differs fundamentally from natural HF content (cymbal decay, reverb tails), which is time-locked to musical events below it and has temporal modulation following the source's transient and decay shape.

**DEF-712 resolution — Method change**: The SFM (Spectral Flatness Measure) method is removed and replaced with a temporal approach. This is a **method change**, not a parameter change. The SFM method is fundamentally broken for this purpose: empirical evidence in DEF-712 shows that bandlimited white noise in the 8–16 kHz range produces SFM mean ≈ 0.847, consistent with the theoretical Rayleigh-distribution asymptote for STFT magnitudes under Gaussian input. DEF-712 records the closed form as `exp(-γ/2) / (√π/2) ≈ 0.8455`, where γ is the Euler–Mascheroni constant (≈ 0.5772). **Note on derivation ambiguity**: the denominator `√π/2 ≈ 0.886` yields 0.8455, consistent with the empirical result; an alternative reading `√(π/2) ≈ 1.253` yields ≈ 0.598, which does not match the empirical probe. The mastering engineer should verify the correct closed form. Regardless of which expression is exact, the empirical probe (per-frame SFM range [0.840, 0.851], mean 0.847, only 4/11 frames above the 0.85 threshold, longest consecutive run 2 frames) independently confirms that the canonical positive case (genuine broadband HF noise) cannot reliably trigger the SFM detector at 0.85. Furthermore, SFM and spectral entropy share the same discriminability failure: both measure spectral flatness in the frequency domain and cannot distinguish Suno-generated HF noise from a natural cymbal decay or reverb tail (both are spectrally flat and broadband). The discriminating axis is **temporal**, not spectral.

**Physical justification for temporal approach**:
- Natural HF content is **episodic**: a cymbal strike produces a burst of HF energy that decays, modulated by the physical resonance of the instrument. HF energy tracks and follows the source event. The HF amplitude envelope is temporally modulated (CV > 0.10 typically) and correlates with the LF events that triggered it.
- Suno HF generation noise is **stationary**: it is produced by the generative model independently of the musical content, persists across multiple bars as a continuous noise floor, and shows near-zero temporal correlation with the LF musical activity below it.

**Conflict with requirements.md AC4**: `requirements.md` Acceptance Criterion 4 specifies "SFM in 8–16 kHz exceeds 0.85." The method change in this section renders AC4 as written invalid — SFM is no longer the metric. AC4 must be updated by the BA to specify the temporal approach instead. Test case fixture F-004 (bin-aligned sinusoids designed to game SFM specifically) and TC-005 as currently specified are also invalidated and must be redesigned.

**Method**:
1. Compute per-frame HF band RMS energy: `E_HF[t] = sqrt(mean(|X_k|²))` for k ∈ 8–16 kHz range, for each STFT frame.
2. Compute per-frame LF band RMS energy: `E_LF[t] = sqrt(mean(|X_k|²))` for k ∈ 200–2000 Hz range, for each STFT frame.
3. Over a sliding 2 s window (8 frames at 250 ms hop), compute:
   - **HF Temporal Modulation Index (TMI_HF)**: `TMI_HF = std(E_HF) / mean(E_HF)` — coefficient of variation of HF energy over the window. Low TMI_HF = stationary (constant noise floor); high TMI_HF = temporally modulated natural content.
   - **HF-LF temporal decoupling (CC_HF_LF)**: Pearson correlation between `E_HF[t]` and `E_LF[t]` over the same 8 frames. Near-zero or negative CC_HF_LF = HF independent of musical events; positive CC_HF_LF = HF correlated with music (natural).
4. **Trigger**: flag when `_HAZE_MIN_CONSECUTIVE_WINDOWS` (default 4) **consecutive** sliding-window positions each satisfy BOTH:
   - `TMI_HF < TMI_HF_THRESHOLD` (stationary HF energy), AND
   - `CC_HF_LF < CC_HF_LF_THRESHOLD` (HF decoupled from LF activity)

   A single qualifying 2 s window is a candidate; DIGITAL_HAZE is emitted only when 4 adjacent positions in the sliding window scan all qualify.

   **Window geometry derivation**: Each window covers 8 frames at 250 ms hop = 2.0 s span. Consecutive positions in the sliding scan advance by one frame (250 ms). Four consecutive qualifying positions span frames *i* through *i*+10 = 11 frames, corresponding to a signal duration of approximately 2.75 s (0.25 × 11 = 2.75 s). This is the minimum signal length for which the positive control must trigger. The design intent is to require continuously stationary decoupled HF for at least ~2.75 s rather than accepting a single 2 s snapshot. Note: the 4-window requirement does not imply 8 s of sustained HF — with one-frame advancing, adjacent windows share 7/8 of their frames. If the mastering engineer intends a 8 s non-overlapping requirement, `_HAZE_MIN_CONSECUTIVE_WINDOWS` must be raised or the stride changed; flag as open item.

   Use the existing `_find_consecutive_runs()` numpy helper (§3) to identify runs of qualifying window positions. Emit one `ArtifactFlag` per qualifying run; the flag's time span covers the start of the first qualifying window to the end of the last.

**Threshold derivation — requires post-implementation measurement**:

Both thresholds are **empirical** and must be derived by the mastering engineer after implementation, by measuring TMI_HF and CC_HF_LF on:
1. All five reference tracks (expected: high TMI_HF and/or high CC_HF_LF in HF-active regions → should not trigger)
2. Suno outputs with confirmed HF haze (expected: low TMI_HF and low CC_HF_LF → should trigger)

The separating thresholds from these measurements become TMI_HF_THRESHOLD and CC_HF_LF_THRESHOLD. **Thresholds must not be asserted without this measurement.**

Provisional directional estimates for implementation scaffold only (labeled `PROVISIONAL — REQUIRES MEASUREMENT` in code):
- `TMI_HF_THRESHOLD ≈ 0.10`: TMI_HF = `std(E_HF[0..7]) / mean(E_HF[0..7])` — a coefficient of variation computed across only **8 time frames** (50% overlapping). The within-frame estimate E_HF[t] averages over N_bins ≈ 4000 frequency bins, giving a low within-frame estimator variance (relative std ≈ 1/sqrt(N_bins/2) ≈ 0.022). However, this within-frame estimator error is **not** the floor of TMI_HF. TMI_HF is the sample CV of a sequence of only 8 observations, and those 8 frames share 50% of their samples with adjacent frames due to STFT overlap — they are not independent. The distribution of TMI_HF for truly stationary noise requires simulation to characterise: generate stationary Gaussian bandlimited noise, compute TMI_HF across 8 overlapping frames, and measure the resulting distribution. The 0.10 provisional threshold is a directional estimate based on the expectation that (a) natural cymbal decay produces frame-to-frame amplitude variation with CV well above 0.10 due to physical resonance decay, and (b) 0.10 is expected to be clearly above the simulated stationary-noise floor even with frame correlation accounted for. **This estimate has not been validated by simulation and must not be treated as derived.** Simulation and reference-track measurement are required before accepting this threshold (see §9.3). **Must be measured and replaced.**
- `CC_HF_LF_THRESHOLD ≈ 0.30`: Natural HF content correlates with LF events (CC > 0.30 expected). Suno independent HF noise: CC near zero. **Must be measured and replaced.**

**Confidence calculation**:
- Both conditions met for qualifying run: base 0.70.
- TMI_HF < 0.05 (strongly stationary): increment by 0.10.
- CC_HF_LF < 0.10 (strongly decoupled): increment by 0.10.
- Cap at 0.90 (single metric; max confidence 1.0 reserved for conjunction with additional evidence).

**Testability**:
- **Positive control**: Synthetic audio with HF band (8–16 kHz) filled with stationary white noise at constant amplitude (TMI_HF ≈ 0.02), sustained **5 s**, while LF band (200–2000 Hz) is a different independent noise signal (CC_HF_LF ≈ 0). At 250 ms hop, 5 s produces approximately 20 STFT frames and multiple overlapping qualifying 2 s windows. The minimum signal length for 4 consecutive qualifying windows is approximately 3.0 s (0.25 × (4 + 8 − 1) = 2.75 s of frame coverage; rounded up to 3.0 s for the 500 ms first-window span); 5 s provides safe margin above this floor. Expected: flag with confidence >= 0.70.
- **Negative control (cymbal decay)**: Synthetic HF burst with exponential decay (TMI_HF ≈ 0.25–0.35 due to decay modulation). Expected: 0 flags (high TMI_HF fails the stationarity condition).
- **Negative control (correlated content)**: HF noise whose amplitude envelope is derived from the LF envelope (CC_HF_LF ≈ 0.8). Expected: 0 flags (high correlation fails the decoupling condition).
- **Reference control**: All five reference tracks must be re-measured after threshold calibration (Gate 2 §Finding 4). The pre-fix reference measurements referenced in earlier passes are stale.

---

### 5.3 STATIONARY_WHISTLE (Narrow Spectral Peak Persistence, with Harmonic Stack Suppression)

**Rationale**: Suno sometimes produces stationary tonal artifacts (vocoder whines, grid-line artifacts) — narrow spectral peaks that persist across multiple seconds. Musical sustained tones (sung notes, sustained synth) also produce persistent narrow peaks and were causing false positives (DEF-705 Issue B). The key distinguishing property: Suno artifact tones are **isolated** (no harmonics); musical tones are **harmonic** (presence of 2f, 3f, f/2, f/3).

**DEF-705 Issue B resolution — Method change**: Added harmonic stack check after identifying persistent peaks. A persistent peak is suppressed (classified as musical content) if a harmonic stack is detected. This is a **method change**, not a parameter change: the method now applies a suppression step that was absent before.

**Method**:
1. In each STFT window, background-subtract the magnitude spectrum to suppress the broadband floor: `residual = mag_frame_dB − medfilt(mag_frame_dB, kernel=WHISTLE_BACKGROUND_KERNEL_HZ)`. Find peaks using `scipy.signal.find_peaks(residual, height=PROMINENCE_THRESHOLD_DB, distance=WHISTLE_MIN_PEAK_DISTANCE_BINS)`.
   - Note: `WHISTLE_BACKGROUND_KERNEL_HZ` and `WHISTLE_MIN_PEAK_DISTANCE_HZ` are specified in Hz; convert to bins at runtime as `kernel_bins = round(WHISTLE_BACKGROUND_KERNEL_HZ / bin_hz)` (odd-rounded), `distance_bins = round(WHISTLE_MIN_PEAK_DISTANCE_HZ / bin_hz)` where `bin_hz = sr / nfft`. This ensures the detector behaviour is decoupled from the FFT size (DEF-702 coupling note). **Required implementation change**: the prior implementation hard-coded `kernel_size=51` and `distance=25` (bin counts from DEF-704 fix) rather than deriving them from Hz constants. These hard-coded values must be replaced with the runtime Hz-to-bin conversion described above.
2. Build a per-bin occupancy matrix `peak_present[bin, frame]` tracking which bins have qualifying peaks in each frame.
3. For each bin, find all consecutive runs where `peak_present[bin, frame] == True` lasting >= `MIN_PERSISTENCE_FRAMES` frames. Collect as proto-flags `(bin, start_frame, end_frame, max_prominence_dB, max_q)`.
4. **Harmonic stack suppression** (DEF-705 Issue B):

   **4a. Independent per-flag check (first pass)**: For each proto-flag at primary frequency `f_0 = bin * bin_hz`:
   - Compute candidate harmonic positions: `H = {2*f_0, 3*f_0, f_0/2, f_0/3}`.
   - For each position `h_k` in H:
     - If `h_k < bin_hz` or `h_k > sr/2`: mark as **not evaluated** (out of range; excluded from count, does not count as absent). This handles near-Nyquist primaries gracefully.
     - Otherwise: search within ±FREQUENCY_TOLERANCE_HZ (50 Hz) of `h_k`; take the bin with maximum prominence within that range. Check if `peak_present[best_bin, :]` shows >= 1 consecutive run that overlaps the primary proto-flag's time range by >= 50% of the primary's frame count AND has prominence >= HARMONIC_MATCH_PROMINENCE_DB.
     - If such a run exists: mark `h_k` as **matched**.
   - Count `n_matched = number of H positions marked "matched"` (excluding "not evaluated" positions).
   - If `n_matched >= HARMONIC_MATCH_MIN_COUNT`: **suppress the flag** — classify as musical tone, not Suno artifact.
   - If `n_matched < HARMONIC_MATCH_MIN_COUNT`: **retain the flag** — likely isolated artifact tone (pending cascade check).

   **4b. Cascade suppression (second pass — DEF-705 Issue B fix)**: After the first-pass independent check is complete for all proto-flags, perform one cascade pass. For each proto-flag suppressed in the first pass (at frequency `f_supp`), examine every proto-flag that was NOT suppressed and whose frequency falls within ±FREQUENCY_TOLERANCE_HZ of any position in `{2*f_supp, 3*f_supp, f_supp/2, f_supp/3}`. If that retained proto-flag's time range overlaps the suppressed flag's time range by ≥50% of the retained flag's frame count: **suppress it** (cascade suppression). One iteration of this pass suffices for any harmonic stack found in practice — the fundamental always accumulates the most harmonic matches and is suppressed first; all of its overtones lie at `{2*f_supp, 3*f_supp, ...}` and are covered by the cascade. Example: in a 440 + 880 + 1320 Hz stack, the first pass suppresses 440 Hz (n_matched=2: 880 Hz = 2f, 1320 Hz = 3f). The cascade pass then suppresses 880 Hz (= 2×440, within 50 Hz, ≥50% time overlap) and 1320 Hz (= 3×440, within 50 Hz, ≥50% time overlap) — both had n_matched=1 in the first pass and would otherwise be retained. AC3 cascade invariant: 6.4 kHz pure sine has no suppressed fundamental; the cascade pass adds zero suppressions.

5. Merge adjacent retained proto-flags: two proto-flags merge if they BOTH overlap in time AND are within `FREQUENCY_TOLERANCE_HZ` in frequency.
6. Emit one `ArtifactFlag` per resulting cluster.

**AC3 invariant**: The 6.4 kHz pure sine positive-control test (requirements.md AC3) has no harmonic stack — by construction, the fixture contains no energy at 3.2 kHz, 12.8 kHz, 2.13 kHz, or 19.2 kHz. Harmonic check finds zero matched positions. Flag is NOT suppressed by the first pass. No suppressed fundamental exists, so the cascade pass also adds zero suppressions. AC3 continues to pass. This must be explicitly verified in the test for this fixture.

**Constants derivation**:
- **Q >= 8.0, prominence >= 6.0 dB, persistence >= 1.5 s**: Unchanged from prior architecture. Suno whines show Q 10–30, prominence 8–18 dB. Normal harmonic content shows Q 2–5, prominence 3–6 dB. 1.5 s persistence; Suno artifacts of this type persist for the duration of a sung note or phrase.
- **HARMONIC_MATCH_PROMINENCE_DB = 3 dB**: Lower than the primary threshold (6 dB). Harmonics of musical tones are lower in prominence than the fundamental; 3 dB is sufficient to detect a real harmonic without requiring it to stand out as strongly as the primary artifact.
- **HARMONIC_MATCH_MIN_COUNT = 2**: At least 2 of the 4 harmonic positions must match. Rationale: musical tones always have a fundamental plus at least a 2nd and 3rd harmonic. A match at 2 positions (e.g., 2f and 3f) is a strong indicator of a harmonic series. Suno isolated artifacts: expected 0 matches.
- **50% time-overlap requirement**: The harmonic peak must be present during the same time interval as the primary. This prevents suppression by incidental content at a harmonic frequency from a different musical event at a different time.

**Testability**:
- **Negative control (sine sweep)**: Sine wave sweep 1 Hz–20 kHz over 5 s. Expected: zero flags (no stationary peaks).
- **Positive control (isolated sine)**: Sustained 6.4 kHz sine, prominence 8 dB, duration 2 s. No other energy at 3.2 kHz, 12.8 kHz, 2.13 kHz, 19.2 kHz. Expected: flag with confidence 0.80–0.85, harmonic check returns 0 matches, flag NOT suppressed by first pass or cascade. This is AC3.
- **Suppression control (musical tone)**: Fundamental at 440 Hz with overtones at 880, 1320 Hz, all persistent for 2 s. Expected: 440 Hz suppressed in the first pass (n_matched=2: 880 Hz = 2f, 1320 Hz = 3f). 880 Hz has n_matched=1 in the first pass (only 440 Hz = f/2 matched) — not suppressed by the independent check. 1320 Hz has n_matched=1 in the first pass (only 440 Hz = f/3) — not suppressed by the independent check. Cascade pass: 440 Hz is suppressed, so 880 Hz (= 2×440, within 50 Hz, ≥50% time overlap) and 1320 Hz (= 3×440, within 50 Hz, ≥50% time overlap) are cascade-suppressed. Zero artifact flags emitted.
- **Near-Nyquist control**: Sustained tone at 7000 Hz, 2 s. Harmonic position 3f = 21000 Hz exceeds sr/2 at 44.1 kHz. 3f marked "not evaluated". If 2f = 14000 Hz has no matching peak, n_matched = 0 (< 2), flag NOT suppressed. Verify this is correct behaviour.
- **GusGus / Chemical Brothers re-measurement**: stale — re-measure after this fix (Gate 2 §Finding 4).

---

### 5.4 PHASE_SWISH (High-Frequency Phase Decorrelation)

**Rationale**: Suno exhibits high-frequency phase artifacts where the left and right channels decorrelate rapidly in the HF band, producing audible "swish" on panned elements.

**Method** (unchanged from prior revision):
1. For each STFT window, extract phase matrices for L and R channels.
2. Partition into LF (< 8 kHz) and HF (>= 8 kHz) bands.
3. For the HF band: compute inter-channel phase variance and cross-correlation.
4. For the LF band: compute cross-correlation coefficient.
5. **Trigger**: flag if:
   - HF phase variance > 0.5 rad² (rapid, uncorrelated phase fluctuations), AND
   - HF cross-correlation < 0.4 (low coherence), AND
   - LF cross-correlation >= 0.7 (stable low-frequency relationship).

**Confidence calculation** (unchanged):
- Baseline 0.70 for meeting all three conditions.
- Increment by 0.1 if HF phase variance > 1.0 rad².
- Increment by 0.1 if HF correlation drops below 0.2.
- Decrement by 0.1 if LF correlation drops below 0.8.
- Final confidence = clamp to [0.0, 1.0].

**Gate 2 §Finding 5 — Validation gap (noted, validation required)**:
The three-way conjunction (all three conditions simultaneously true) has not been verified to occur on real material. If the three conditions never co-occur naturally:
- The detector is effectively dead code on real tracks (never fires)
- A conservative detector that never fires is not conservative — it is a false negative machine

**Required validation step post-implementation**: Measure each of the three conditions **independently** on all five reference tracks and on suspected Suno tracks:
1. Report the frequency with which each condition fires alone across the corpus.
2. Report the frequency with which pairs fire together.
3. Report the frequency with which all three fire together (the actual trigger condition).

If the three-way conjunction never co-occurs on any tested material, the thresholds must be loosened or the conjunction relaxed to a weighted combination. The validation result must be recorded in a post-implementation measurement note before Gate 2 can close this item.

**Constants derivation** (empirical, requires reference measurement):
- **HF phase variance > 0.5 rad²**: Suno problem tracks show HF phase variance 0.6–2.0 rad². Normal stereo electronic material: 0.1–0.3 rad². Threshold 0.5 provides ~0.2 rad² margin.
- **HF cross-correlation < 0.4**: Stereo width is intentional, but CC < 0.4 indicates near-independence in the HF band.
- **LF cross-correlation >= 0.7**: Normal stereo mixes maintain LF coherence (kick, bass mono or near-mono).
- All three thresholds are empirical and pending Gate 2 §Finding 5 validation.

**Mono input handling**: Mono input → set R = L. PHASE_SWISH is skipped (no inter-channel decorrelation possible). Append note to report.

**Testability**:
- **Positive control**: Synthetic stereo with L and R independent above 8 kHz (phase uncorrelated, CC ~0.2), LF channels identical (CC = 1.0), sustained 2 s. Expected: flag with confidence 0.75–0.85.
- **Validation step**: Run independently on all five reference tracks and report per-condition and conjunction frequencies.

---

## 6. Configuration & Thresholds

All detector thresholds are **constants in `analysis/artifact_detection.py`** with inline comments referencing their derivation (per `CLAUDE.md` §5: "Every constant must have its derivation shown").

Constants marked `PROVISIONAL — REQUIRES MEASUREMENT` must be replaced with measured values after reference track validation.

```python
# ── STFT parameters ──────────────────────────────────────────────────────────
WINDOW_DURATION_S = 0.5           # STFT window size
HOP_SIZE_S = 0.25                 # Hop size (50% overlap)
# FFT_SCALE_FACTOR: DEF-702 — 4× zero-padding (nfft = 4 * nperseg) was specified
# but would consume ~1.7 GB for a 5-min stereo track at 44.1 kHz.
# nfft = nperseg (1×, no zero-padding). Bin spacing = sr / nfft = 2 Hz at 44.1 kHz
# with 500 ms window. This is sufficient for all detectors: Q ≥ 8 means bandwidth
# = f/8 >> 2 Hz for any frequency of interest. Zero-padding interpolates bins but
# does not improve frequency resolution (which is set by window length alone).
# DEF-702 resolution: confirm nfft = nperseg acceptable. Method unchanged; parameter
# was premature — 4× was never necessary for any detector's correctness.
FFT_NFFT_EQUAL_NPERSEG = True     # nfft = nperseg (no zero-padding)

CONFIDENCE_THRESHOLD_TO_WARN = 0.8  # Confidence floor for plausibility_warnings

# ── SMEARED_TRANSIENT ─────────────────────────────────────────────────────────
# Derivation: §5.1
# HF-presence gate: compares HF-band (6–16 kHz) RMS in a 30 ms window (tile 0,
# centred on onset anchor) against the local HF noise floor (median of ~32 adjacent
# 30 ms tiles tiled outward from the anchor, tile 0 excluded, time-domain RMS).
# Gate passes if HF_RMS_window > local_hf_floor * _ONSET_HF_PRESENCE_RATIO.
# Ratio 3.0 = 20·log10(3.0) = 9.5 dB above floor (mastering review: "≈ +10 dB").
# Self-normalising: adapts to the track's actual noise floor per onset.
# Does NOT discriminate percussive from vocal — both pass if HF RMS > floor × ratio.
# False-negative risk in HF-dense passages — see §10.1 item 8.
# PROVISIONAL — REQUIRES MEASUREMENT on reference tracks (see §5.1).
_ONSET_HF_PRESENCE_RATIO = 3.0    # Gate: HF_RMS_window must exceed local_hf_floor by this factor
ONSET_RISETIME_THRESHOLD_MS = 25   # HF Hilbert 10%-90% rise-time threshold
# 150 ms window centred on anchor → ~75 ms of backward runway before anchor.
# _measure_risetime() walks backward; effective max measurable rise-time ≈ 75 ms.
# Onsets with rise-time > ~75 ms return None and are silently excluded (acceptable:
# outside Suno smearing range of 25–50 ms).
ONSET_RISE_ANALYSIS_WINDOW_MS = 150  # Window for rise-time measurement (effective max ~75 ms backward)
ONSET_HF_WINDOW_MS = 30           # Window for HF-band RMS gate measurement (30 ms tiles)

# ── DIGITAL_HAZE ──────────────────────────────────────────────────────────────
# Method change from SFM (DEF-712). See §5.2 derivation.
# SFM_THRESHOLD = 0.85 is REMOVED — SFM method is fundamentally broken (ceiling ~0.846).
TMI_HF_THRESHOLD = 0.10           # HF temporal modulation index; below = stationary
                                   # PROVISIONAL — REQUIRES MEASUREMENT (see §5.2)
CC_HF_LF_THRESHOLD = 0.30         # HF-LF temporal correlation; below = decoupled
                                   # PROVISIONAL — REQUIRES MEASUREMENT (see §5.2)
HAZE_DURATION_THRESHOLD_S = 2.0   # Metric computation window size (8 frames)
# Number of consecutive qualifying windows required to trigger DIGITAL_HAZE.
# 4 consecutive positions in the sliding scan (one frame apart = 250 ms stride)
# span frames i..i+10 = 2.75 s of signal at minimum.
# Prevents single-window false positives (reverb tail over sustained bass, etc.)
# Use _find_consecutive_runs() helper to identify qualifying runs.
_HAZE_MIN_CONSECUTIVE_WINDOWS = 4  # Consecutive qualifying windows required to flag
HAZE_HF_BAND_HZ = (8000, 16000)   # High-frequency analysis band
HAZE_LF_BAND_HZ = (200, 2000)     # Low-frequency reference band

# ── STATIONARY_WHISTLE ────────────────────────────────────────────────────────
# Derivation: §5.3
Q_THRESHOLD = 8.0
PROMINENCE_THRESHOLD_DB = 6.0
PERSISTENCE_THRESHOLD_S = 1.5
FREQUENCY_TOLERANCE_HZ = 50
# Hz-specified constants — converted to bins at runtime (see §5.3 note on DEF-702 coupling)
_WHISTLE_BACKGROUND_KERNEL_HZ = 100.0   # Spectral background smoothing window in Hz
_WHISTLE_MIN_PEAK_DISTANCE_HZ = 50.0    # Minimum Hz between candidate peaks
# Harmonic suppression (DEF-705 Issue B)
HARMONIC_MATCH_PROMINENCE_DB = 3.0      # Minimum prominence for a harmonic match
HARMONIC_MATCH_MIN_COUNT = 2            # Minimum matched harmonic positions to suppress

# ── PHASE_SWISH ───────────────────────────────────────────────────────────────
# Derivation: §5.4; all empirical, pending Gate 2 §Finding 5 validation
HF_PHASE_VARIANCE_THRESHOLD = 0.5      # rad²
HF_CORRELATION_THRESHOLD = 0.4
LF_CORRELATION_MINIMUM = 0.7
```

No configuration file is used for thresholds; they are detector tuning constants, not targets (per `docs/ARCHITECTURE.md` §1.2).

---

## 7. Integration Points

### 7.1 Module Path & Exports

```
analysis/
  artifact_detection.py          # New module
  types.py                        # Extend Measurements with artifact_detection field
  __init__.py                     # Import and expose detect_artifacts()
```

**Public API** (DEF-701 resolution — plain-array contract, consistent with existing analysis conventions):
```python
def detect_artifacts(
    audio: np.ndarray,   # float64, shape (n_samples,) or (n_samples, n_channels)
    sr: int,             # sample rate in Hz
) -> tuple[np.ndarray, ArtifactDetectionResult]:
    """
    Detect Suno generation artifacts in audio.
    Returns (audio_unmodified, detection_result).
    Audio array is byte-identical before/after (SHA-256 hash invariant).
    Raises ValueError if sr < 32000.
    Raises ValueError if audio.ndim == 2 and audio.shape[1] > 2 (DEF-708).
    Mono input (ndim == 1 or shape[1] == 1): processed; PHASE_SWISH skipped.
    """
```

**Note on AudioBuffer**: The prior architecture specified `AudioBuffer` as the input type, but this dataclass does not exist in the codebase. The existing pipeline (STORY-001 `analysis.measure_all()`) uses plain arrays. The plain-array contract above matches the existing convention. See §4.1 for the conflict note with `docs/ARCHITECTURE.md §3.1`.

### 7.2 Orchestration in `analysis/__init__.measure_all()`

Artifact detection is called **after** standard loudness/spectral analysis but **before** returning `Measurements`:

```python
def measure_all(audio, sr, config) -> Measurements:
    """Stage 2 analysis pass: loudness, spectral, and artifacts."""
    measurements = Measurements(...)
    
    # Existing measures
    measurements.integrated_lufs = ...
    measurements.true_peak_dbtp = ...
    # ... etc ...
    
    # NEW: Artifact detection
    audio_unmodified, artifact_result = detect_artifacts(audio, sr)
    measurements.artifact_detection = artifact_result
    # audio_unmodified is discarded (equals input); hash verified inside detect_artifacts()
    
    return measurements
```

### 7.3 Report Generation

The `Reporting` stage (per `docs/ARCHITECTURE.md` §3.5) must include a section for artifact detection:

**Markdown output**:
```markdown
## Suno Generation Artifacts

| Type | Time Range | Frequency | Confidence | Details |
|---|---|---|---|---|
| STATIONARY_WHISTLE | 01:14.5 – 01:18.2 | 6.4 kHz | 0.88 | Q=12, prominence=7.2 dB |
| SMEARED_TRANSIENT | 00:45.1 – 00:45.3 | n/a | 0.82 | rise-time=28 ms |

**Note**: This analysis is report-only. Flagged artifacts cannot be corrected at the master stage (DOMAIN.md §4). Re-generation is recommended for high-confidence flags.
```

**JSON output**:
```json
{
  "artifact_detection": {
    "total_artifacts_found": 2,
    "overall_artifact_density_score": 0.45,
    "artifact_flags": [
      {
        "timestamp_start_s": 74.5,
        "timestamp_end_s": 78.2,
        "artifact_type": "STATIONARY_WHISTLE",
        "confidence_score": 0.88,
        "details": {"frequency_hz": 6400, "prominence_db": 7.2, "q_factor": 12}
      }
    ]
  }
}
```

---

## 8. Error Handling & Edge Cases

| Case | Behavior |
|---|---|
| **Sample rate < 32 kHz** | Raise `ValueError`. Detectors require >= 16 kHz Nyquist to measure 8–16 kHz band reliably. |
| **Mono input** | Process as stereo with R = L; skip PHASE_SWISH (no inter-channel decorrelation). Append note to report. |
| **More than 2 channels** | Raise `ValueError` (DEF-708). |
| **Very short audio (< 1 s)** | Skip persistence-based detectors (DIGITAL_HAZE, STATIONARY_WHISTLE); run SMEARED_TRANSIENT and PHASE_SWISH only if they do not require multi-window state. |
| **All-zero audio** | Artifact detection returns zero flags (silence has no artifacts). |
| **Numerical issues in spectral computation** | Handle NaN/Inf gracefully: skip affected window, log warning, continue. |

---

## 9. Testability & Verification

### 9.1 Unit Test Structure

```
tests/analysis/
  test_artifact_detection.py
    # SMEARED_TRANSIENT
    test_smeared_transient_no_hf_energy_gate_rejection()  # Low-formant vocal onset (near-zero HF) → HF RMS ≈ noise floor → gate fails → 0 flags
    test_smeared_transient_sibilant_gate_pass_short_risetime()  # Vocal sibilant (broadband HF, RMS >> noise floor, short rise-time) → gate passes, rise-time < 25 ms → 0 flags
    test_smeared_transient_negative_control()        # Sharp percussive HF, RMS >> noise floor, rise-time < 25 ms → 0 flags
    test_smeared_transient_positive_control()        # HF-bearing onset, RMS >> noise floor, 35 ms HF rise-time → flag
    test_smeared_transient_dark_material()           # Dark kick (spectral tilt) with sharp 8 ms rise-time → 0 flags
    test_smeared_transient_onset_at_track_start()   # Onset at t=0.2 s (DEF-711 edge case) → flag if gate passes
    # DIGITAL_HAZE (revised for temporal method + consecutive-window trigger)
    test_digital_haze_stationary_decoupled()        # 5 s constant HF noise, decoupled from LF → flag (4+ consecutive qualifying windows)
    test_digital_haze_stationary_short()            # < 3 s stationary HF noise → 0 flags (fewer than 4 consecutive qualifying windows)
    test_digital_haze_cymbal_decay()                # HF burst with exponential decay (high TMI_HF) → 0 flags
    test_digital_haze_correlated_hf()               # HF amplitude tracks LF (high CC_HF_LF) → 0 flags
    test_digital_haze_threshold_validation()        # (BLOCKED: thresholds provisional) document as blocked pending measurement
    # STATIONARY_WHISTLE
    test_stationary_whistle_negative_control()      # Sine sweep → 0 flags
    test_stationary_whistle_positive_control()      # Sustained 6.4 kHz sine → flag; verify AC3 and harmonic-check invariant
    test_stationary_whistle_harmonic_suppression()  # 440 Hz + overtones 880/1320 Hz → 0 flags (suppressed)
    test_stationary_whistle_near_nyquist()          # 7 kHz tone, 3f out of band → not evaluated; 2f absent → flag not suppressed
    test_stationary_whistle_time_coincidence()      # f/2 peak in different time range → not matched; flag not suppressed
    test_stationary_whistle_gaussian_noise()        # DEF-704 regression: Gaussian noise 5 s → 0 flags
    test_stationary_whistle_two_bursts()            # DEF-706 regression: 2 separate bursts → 2 flags
    # PHASE_SWISH
    test_phase_swish_positive_control()             # Uncorrelated HF, coherent LF → flag
    test_phase_swish_conjunction_measurement()      # Measure all 3 conditions independently (validation step §5.4)
    # System-level
    test_sha256_invariant()
    test_measurements_appended()
    test_plausibility_warnings_populated()
    test_sample_rate_validation()                   # SR < 32 kHz → ValueError
    test_mono_channel_handling()                    # Mono → PHASE_SWISH skipped
    test_multichannel_rejection()                   # 6-channel input → ValueError (DEF-708)
    test_very_short_audio()
    test_stft_sliding_window_continuity()
    test_def704_gaussian_noise_no_whistle()         # Regression: closed
    test_def706_two_separate_whistle_bursts()       # Regression: closed
    test_def707_preonset_hf_bed_no_saturation()     # Regression: closed
```

### 9.2 Reference Track Re-Measurement Requirement (Gate 2 §Finding 4)

**All prior reference track measurements are stale.** The DEF-705, DEF-706, DEF-707 fixes each changed the method, and the DEF-705 discrimination gate changes the scope of what the SMEARED_TRANSIENT detector fires on. Pre-fix counts (GusGus: ~25 SMEARED_TRANSIENT + ~7 STATIONARY_WHISTLE; Leftfield: ~36 SMEARED_TRANSIENT + ~24 STATIONARY_WHISTLE) are pre-fix figures from before the discrimination gate and harmonic check were applied. These counts do not reflect what the revised detector will produce.

**Required post-implementation**: After all fixes are implemented, measure all five reference tracks and record results in the defects file. This is a Gate 2 acceptance condition.

| Track | Expected (post-fix) | Prior count (pre-fix — stale) |
|---|---|---|
| GusGus — Over (Arabian Horse) | 0 | ~25 SMEARED_T + ~7 STATIONARY_W (stale) |
| Black Flute (Remastered) | 0 | Not measured |
| Chemical Brothers — Live Again | 0 | 8 SMEARED_T + 14 STATIONARY_W (post-707, pre-705 gate fix) |
| Leftfield — Melt | 0 pending temporal-method calibration | ~36 SMEARED_T + ~24 STATIONARY_W (stale; prior "0–2" estimate was based on SFM characteristics — not applicable to temporal method) |
| Wavy Gravy | 0 pending temporal-method calibration | Not measured (prior "0–2" estimate based on SFM characteristics — not applicable to temporal method) |

Any reference track that still flags after all fixes must be manually reviewed and documented.

### 9.3 DIGITAL_HAZE Threshold Validation Protocol

Since TMI_HF_THRESHOLD and CC_HF_LF_THRESHOLD are provisional, implement a measurement mode:
- Run detector in "measurement mode" (no triggering) on all five reference tracks
- Log TMI_HF and CC_HF_LF values for all 2 s windows where HF energy is present
- Run on any available Suno tracks with confirmed HF haze
- Report distributions; choose thresholds that separate the two populations
- **Additionally**: simulate stationary Gaussian bandlimited noise at 8–16 kHz, compute TMI_HF across 8 overlapping frames (50% overlap), and measure the resulting distribution. The empirical 5th-percentile of this distribution is the effective floor. The chosen TMI_HF_THRESHOLD must be well above this floor. Report the floor alongside the reference-track distributions.

Until this validation is complete, the DIGITAL_HAZE unit tests must use synthetic signals (positive and negative controls) with analytically-known TMI_HF and CC_HF_LF values, not measured values from real tracks.

---

## 10. Known Limitations & Open Questions

### 10.1 Known Limitations

1. **Temporal approach for DIGITAL_HAZE**: A sustained white-noise pad or sound-design element (intentional, decoupled from musical events) will trigger DIGITAL_HAZE. The temporal discriminator narrows but does not eliminate this class of false positives. Human review remains necessary for any DIGITAL_HAZE flag.

2. **DIGITAL_HAZE thresholds are provisional**: TMI_HF_THRESHOLD and CC_HF_LF_THRESHOLD must be calibrated from real Suno outputs and reference tracks before the detector can be considered production-ready. Shipping with provisional values means the detector may have a high false-positive or false-negative rate.

3. **Transient smearing is unfixable at master stage** (per `DOMAIN.md` §4). Detection is for triage only; users must re-generate.

4. **Phase decorrelation may be intentional stereo technique**: the PHASE_SWISH detector assumes HF decorrelation is an artifact, but panned elements with delay/reverb produce similar signatures. The confidence score is conservative (0.70–0.85 max) to reduce false positives, but flags on stereo-mixed material should be expected. The three-way conjunction may mitigate this; see §5.4 validation requirement.

5. **Harmonic stack suppression has sensitivity tradeoff**: if a Suno artifact tone happens to coincide (in frequency and time) with a musical harmonic, it may be suppressed. This is acceptable — the reporting goal is triage, not exhaustive detection.

6. **PHASE_SWISH conjunction unvalidated**: the three-way AND condition has not been confirmed to fire on real Suno material. See §5.4 validation requirement.

7. **SMEARED_TRANSIENT HF-presence gate does not discriminate vocal from percussive onsets**: the gate is a level test — it excludes only events whose HF-band RMS in the 30 ms window is indistinguishable from the local HF noise floor (kick drums, low-frequency-only content). All onsets with meaningful HF energy — vocal sibilants, cymbals, snare, vocoder — produce `HF_RMS_window > local_hf_floor * _ONSET_HF_PRESENCE_RATIO` and pass the gate. They are then evaluated by the rise-time threshold. If false positives appear on vocal or sustained HF content in reference track re-measurement, the correct response is to raise `ONSET_RISETIME_THRESHOLD_MS`. Raising `_ONSET_HF_PRESENCE_RATIO` risks excluding genuine low-level HF-bearing onsets and must not be done without new measurement evidence.

8. **SMEARED_TRANSIENT HF-presence gate false-negative risk in HF-dense passages**: in passages with sustained broadband HF activity (e.g., hi-hat-heavy sixteenths, open cymbal wash), the ~1 s tile neighbourhood median reflects the sustained HF signal level rather than a noise floor. A snare or other HF-bearing onset embedded in such a passage must produce `HF_RMS_window > 3 × (surrounding HF activity)`, which may not hold if the onset's HF transient is only moderately louder than the background wash. This is a **false-negative path only** — kick drum rejection is unaffected (kicks have near-zero HF energy regardless of context). Validation must include measurement of `HF_RMS_window / local_hf_floor` ratios in HF-dense passages to characterise this risk; adjust the ratio or widen the floor-estimation window if necessary.

### 10.2 Conflict with requirements.md AC4

`requirements.md` Acceptance Criterion 4 reads: "Given a file containing continuous HF flatness, when SFM in 8–16 kHz exceeds 0.85 for >= 2.0 s and overall dynamic range is low, then the module emits DIGITAL_HAZE."

**This architecture contradicts AC4 as written.** The SFM method is removed (DEF-712 — method change). The replacement method (TMI_HF + CC_HF_LF temporal approach) does not compute SFM at all. AC4 must be updated by the BA to specify the temporal approach.

Additionally, test fixture F-004 (bin-aligned sinusoids designed to produce SFM > 0.85 reliably) and test case TC-005 as currently specified are invalidated and must be redesigned against the temporal method.

**No implementation should attempt to preserve SFM computation to pass the old AC4.** That would be fixing a wrong method by retaining a wrong method.

### 10.3 Open Questions for BA

1. **AC4 update**: Requirements.md AC4 must be revised to specify the temporal DIGITAL_HAZE method (TMI_HF + CC_HF_LF), not SFM. BA action needed.

2. **Sample rate support**: Minimum and maximum sample rates to support. Current minimum assumed 32 kHz. What about 22.05 kHz, 24 kHz, or > 48 kHz?

3. **Confidence threshold for warnings**: Default 0.80 for adding to `plausibility_warnings`. Should this be configurable via CLI flag?

4. **DIGITAL_HAZE threshold measurement**: Mastering engineer should measure TMI_HF and CC_HF_LF on all five reference tracks and available Suno tracks to calibrate the provisional thresholds before the story is accepted.

5. **PHASE_SWISH conjunction validation**: Post-implementation measurement (§5.4) — mastering engineer should review the per-condition frequency results and determine whether thresholds need adjustment.

6. **Rise-time threshold validation**: After HF-presence gate is added, measure actual rise-times on Chemical Brothers and GusGus HF-bearing onsets that pass the HF-presence gate. Confirm all reference-track onsets < 25 ms. If any are above 25 ms, raise `ONSET_RISETIME_THRESHOLD_MS`.

7. **Per-track output**: Should `artifact_detection` results be stored per-track or only in the final report? Current design appends to `Measurements` (per-track).

8. **DIGITAL_HAZE consecutive-window stride**: The current design advances the sliding window by one STFT frame (250 ms); 4 consecutive qualifying windows therefore span ~2.75 s of signal. If the mastering engineer intends a requirement of ~8 s of non-overlapping HF stationarity, `_HAZE_MIN_CONSECUTIVE_WINDOWS` must be raised to approximately 24, or the window stride changed to non-overlapping. Confirm intent.

9. **requirements.md line 22 update**: Line 22 specifies "use spectral flux + local crest factor on percussive onsets." This architecture does not implement crest factor — the gate uses HF-band RMS compared against a local noise floor (`_ONSET_HF_PRESENCE_RATIO`), because CF is scale-invariant and cannot detect absence of HF energy (per `mastering-review-lcf-haze.md` §5.1 BLOCKER). BA must update line 22 to specify the HF-presence energy-level gate, consistent with the AC4 update required in item 1.

---

## 11. Revision History

- **2026-08-14 — §5.1 SMEARED_TRANSIENT: HF-presence gate replaced from crest factor metric to energy-level test (mastering-review-lcf-haze.md §5.1 BLOCKER)**:

  **Source**: `mastering-review-lcf-haze.md` §5.1 verdict, 2026-08-14.

  **Root cause**: The prior gate computed `LCF = 20 * log10(peak / rms)` on the 6–16 kHz band signal and compared against `HF_CREST_FACTOR_THRESHOLD_DB = 4.0 dB`. Crest factor is a shape metric (peak-to-RMS ratio), not a level metric — it is scale-invariant. A kick drum's 6–16 kHz band containing only quantisation noise still reads approximately 10–13 dB CF (Gaussian noise, N ≈ 1323 samples at 44.1 kHz, 30 ms: `E[max|x|]/RMS ≈ sqrt(2·ln(1323)) ≈ 3.79 ≈ 11.6 dB`). A genuine HF-bearing onset also reads approximately 10–13 dB. Both classes land in the same range. No threshold on CF can separate them because CF does not measure energy level — it measures waveform shape. The architecture's prior claim that "near-silent HF → LCF approaches 0 dB" was wrong on both counts: (a) attenuation does not lower CF — the ratio is unchanged regardless of absolute level; (b) a sparse waveform produces *high* CF (high peak relative to RMS), not low. The 4.0 dB threshold admitted both the event class it was designed to reject (kick drums, near-silent HF) and the event class it was designed to pass (HF-bearing onsets) indistinguishably.

  **Fix**: gate criterion replaced with a self-normalising HF energy level test:
  - Tile non-overlapping 30 ms sub-windows outward from the onset anchor; anchor window is tile 0 (numerator). `HF_RMS_window = rms(hf_audio[tile_0])` (6–16 kHz band, time-domain).
  - `local_hf_floor` = median of rms values of approximately ±16 surrounding tiles (~32 tiles, tile 0 excluded), same 6–16 kHz band, time-domain.
  - Gate passes if `HF_RMS_window > local_hf_floor * _ONSET_HF_PRESENCE_RATIO`
  - `_ONSET_HF_PRESENCE_RATIO = 3.0` (`20·log10(3.0) = 9.5 dB` above local floor; mastering review specifies "approximately +10 dB")

  **Derivation of ratio adequacy**: relative std of an RMS estimate over N ≈ 2·BW·T = 2×10000×0.030 = 600 independent samples ≈ `1/sqrt(1200)` ≈ 3%. A kick drum's ratio will be approximately 1.0 ± a few percent; 3.0 is more than 10 standard deviations above this. PROVISIONAL — requires validation on reference tracks, including HF-dense passages (see §10.1 item 8).

  **Band reuse prohibition**: §5.2 `E_HF[t]` covers 8–16 kHz at 250 ms hop granularity in the STFT-magnitude domain. Reusing it here would reintroduce the band mismatch (6–16 kHz vs 8–16 kHz) resolved in the prior §5.1 revision. The 6–16 kHz floor must be computed independently in the time domain.

  **Sub-window tiling**: Tiling outward from the anchor (tile 0 = anchor window) ensures numerator and denominator are the same estimator type at the same granularity, and eliminates ambiguity about whether the numerator window straddles a tile boundary.

  **Track-boundary handling**: for onsets within 500 ms of the track start or end, fewer than ±16 tiles are available in one direction; use all available tiles in both directions combined. Minimum 1 floor tile required. Epsilon guard: `local_hf_floor = max(raw_median, numpy.finfo(numpy.float64).tiny)` to prevent division by zero on digital silence.

  **requirements.md line 22 deviation**: line 22 specifies "local crest factor on percussive onsets." Crest factor is not implemented because it is scale-invariant (see root cause above). This is a BA-visible deviation requiring line 22 to be updated; see §10.3 item 9.

  **Changes to this document**:
  - §5.1 DEF-705 Issue A paragraph: rewritten to state deviation from requirements.md line 22 (energy-level gate rather than crest factor)
  - §5.1 Step 2a: CF gate replaced with energy-level gate; tile-outward floor estimation specified; tile 0 exclusion stated; E_HF reuse prohibition and estimator compatibility requirement stated; "or extract the Hilbert envelope amplitude ... compute peak/RMS from it" alternative removed (Hilbert envelope CF also reads ~9.6 dB on noise floor alone per the mastering review)
  - §5.1 "Important design constraint" paragraph: CF/LCF language removed; replaced with energy-level framing
  - §5.1 Constants derivation: `HF_CREST_FACTOR_THRESHOLD_DB = 4 dB` section replaced with `_ONSET_HF_PRESENCE_RATIO = 3.0` derivation including N≈600 estimator-noise derivation and HF-dense passage limitation
  - §5.1 Escalation rule: "0–4 dB no-HF region" CF language replaced with energy-level framing
  - §5.1 Testability: LCF/dB references replaced with HF-RMS/noise-floor ratio language in all four negative and positive controls
  - §6: `HF_CREST_FACTOR_THRESHOLD_DB = 4.0` → `_ONSET_HF_PRESENCE_RATIO = 3.0`; `ONSET_CREST_WINDOW_MS` → `ONSET_HF_WINDOW_MS`; comment updated to describe energy-level gate with tiling
  - §9.1 test comments: LCF dB values replaced with RMS/floor ratio language; `test_smeared_transient_onset_at_track_start` comment updated from "if LCF passes" to "if gate passes"
  - §10.1 item 7: `HF_CREST_FACTOR_THRESHOLD_DB` replaced with `_ONSET_HF_PRESENCE_RATIO`; CF language replaced with energy-level framing
  - §10.1 item 8 added: HF-dense passage false-negative risk documented
  - §10.3 item 9 added: BA action required — requirements.md line 22 must be updated

  **Downstream impact on implementation**: `_detect_smeared_transient()` gate logic must be rewritten — replace `_local_crest_factor()` computation with: (a) time-domain 6–16 kHz bandpass; (b) tile the signal outward in non-overlapping 30 ms sub-windows from the anchor; (c) `HF_RMS_window = rms(tile_0)`; (d) `local_hf_floor = median(rms(tile_k) for k != 0)`; (e) gate passes if ratio > `_ONSET_HF_PRESENCE_RATIO`. The constant `HF_CREST_FACTOR_THRESHOLD_DB` must be removed and `_ONSET_HF_PRESENCE_RATIO` used throughout. The existing implementation using `_local_crest_factor()` is stale and must be replaced. Do not reuse `_detect_digital_haze()`'s `E_HF` array — band and granularity differ.

- **2026-08-14 — Gate 2 final blockers: LCF gate semantics corrected (§5.1); DIGITAL_HAZE consecutive-window trigger added (§5.2)**:

  **Source note**: `mastering-review-gate2-final.md` was not present in the story directory at the time of this revision. Both blockers were sourced from the invoking agent's task description. Provenance recorded per the project precedent established in the 2026-08-13 first-pass entry (which similarly recorded missing-file sourcing). If a file-based mastering-engineer review exists, it should be checked for any additional findings.

  **Fix 1 — SMEARED_TRANSIENT §5.1: LCF gate changed from discriminator to HF-presence gate**:

  Root cause: The prior architecture derived `HF_CREST_FACTOR_THRESHOLD_DB = 6 dB` from Hilbert envelope crest factor ranges (vocal sibilant envelope: 1–3 dB; snare/cymbal envelope: 8–15 dB). The code computes raw bandpassed signal CF, not Hilbert envelope CF. In the raw signal domain, all broadband HF content — vocoder, sibilants, cymbals, snare — produces CF of approximately 10–13 dB from carrier oscillations. Only events with near-silent HF (kicks) produce CF approaching 0 dB. The 6 dB threshold therefore provided no discriminative power between vocal and percussive onsets: both pass.

  Fix (Option A): The gate is redefined as an HF-presence gate. Its sole purpose is to exclude events with near-zero HF energy (kicks). It makes no claim about discriminating percussive from vocal. Threshold lowered to 4.0 dB: sits well clear of the 0 dB floor for near-silent HF and ~6 dB below the 10 dB lower bound for any HF-bearing event. The rise-time measurement alone now carries the discrimination burden. `HF_CREST_FACTOR_THRESHOLD_DB` updated 6.0 → 4.0 in §6.

  The previously cited 100–122 ms rise-time figures for Chemical Brothers vocal flags (from the DEF-705 Issue A resolution paragraph) are removed. These figures are unreproducible under the actual window geometry: the 150 ms analysis window centred on the anchor provides only ~75 ms of backward runway. `_measure_risetime()` walks backward from the peak and returns `None` for onsets whose 10% crossing is more than ~75 ms before the peak. The effective maximum measurable rise-time is ~75 ms, not 150 ms. This is acceptable — Suno smearing falls in the 25–50 ms range, comfortably within the cap. A note on the ~75 ms cap has been added to Step 3 (§5.1) and to the `ONSET_RISE_ANALYSIS_WINDOW_MS` comment in §6.

  Testability changes: `test_smeared_transient_vocal_onset_gate()` renamed and rewritten as two tests — `test_smeared_transient_no_hf_energy_gate_rejection()` (formant-only onset, gate fails) and `test_smeared_transient_sibilant_gate_pass_short_risetime()` (vocal sibilant, gate passes, rise-time < 25 ms → 0 flags). The second test is new and verifies that the discrimination burden has moved to the rise-time threshold.

  Known limitation §10.1 item 7 added: documents the gate's non-discriminating nature and states the escalation rule (vocal false positives → raise `ONSET_RISETIME_THRESHOLD_MS`, not the gate threshold).

  **Fix 2 — DIGITAL_HAZE §5.2: single-window trigger replaced with consecutive-window trigger**:

  Root cause: With provisional thresholds (TMI_HF < 0.10, CC_HF_LF < 0.30), a single qualifying 8-frame window out of ~1,200 windows in a 5-minute track is sufficient to fire DIGITAL_HAZE. Any 2-second passage of stable reverb tail over sustained bass can satisfy both conditions, generating a false positive on tracks with no Suno HF haze.

  Fix: `_HAZE_MIN_CONSECUTIVE_WINDOWS = 4` added. DIGITAL_HAZE now fires only when 4 adjacent positions in the sliding window scan (each position advancing one STFT frame = 250 ms) each satisfy both TMI_HF and CC_HF_LF conditions. Geometry: 4 consecutive positions span frames *i* through *i*+10 = approximately 2.75 s of continuously stationary decoupled HF. This is consistent with the DIGITAL_HAZE requirement (continuous HF flatness), applied at the window level. Use `_find_consecutive_runs()` (existing numpy helper, §3) to identify qualifying runs. `_HAZE_MIN_CONSECUTIVE_WINDOWS` constant added to §6.

  Testability changes: positive control extended from 3 s to **5 s**. Minimum signal length for 4 consecutive qualifying windows is approximately 3.0 s (0.25 × (4 + 8 − 1) = 2.75 s frame coverage; ~3.0 s with the 500 ms first-window span). 5 s provides safe margin. A new negative control `test_digital_haze_stationary_short()` verifies that < 3 s of stationary HF does not trigger (fewer than 4 consecutive qualifying windows).

  Open question §10.3 item 8 added: the mastering engineer should confirm whether the ~2.75 s consecutive-window interpretation matches intent, or whether a longer non-overlapping duration was intended.

  **Downstream impact on implementation**:
  - `_detect_smeared_transient()`: gate constant `HF_CREST_FACTOR_THRESHOLD_DB` changes 6.0 → 4.0; the gate comment/semantics change from "percussive gate" to "HF-presence gate"; no change to the LCF computation algorithm itself.
  - `_detect_digital_haze()`: trigger logic changes from per-window evaluation to run-length counting using `_find_consecutive_runs()`; a qualifying-window counter replaces the single-window flag.
  - Test fixtures: DIGITAL_HAZE positive control extends 3 s → 5 s; `test_smeared_transient_vocal_onset_gate()` split into two tests with different semantics; new `test_digital_haze_stationary_short()` added.
  - Chemical Brothers 100–122 ms rise-time baseline is withdrawn from §5.1 as unreproducible under the ~75 ms window cap.

- **2026-08-14 — DEF-705 Issue B cascade suppression (§5.3 Step 4)**:

  The harmonic stack suppression specification (Step 4) checked {2f₀, 3f₀, f₀/2, f₀/3} independently for each proto-flag. In a stack such as 440 + 880 + 1320 Hz, only the fundamental (440 Hz) accumulated ≥2 harmonic matches; overtones (880, 1320 Hz) each found at most 1 match and were not suppressed. The implementation correctly followed the spec — the spec was the defect (confirmed by QA retest: 1 STATIONARY_WHISTLE flag at 880 Hz, expected 0).

  Fix: Step 4 is now split into two sub-steps. **4a (unchanged)**: per-flag independent check — each proto-flag checks its own {2f, 3f, f/2, f/3} and is suppressed if n_matched ≥ 2. **4b (new — cascade pass)**: after all first-pass suppressions are determined, examine every retained proto-flag whose frequency falls within ±FREQUENCY_TOLERANCE_HZ of {2*f_supp, 3*f_supp, f_supp/2, f_supp/3} for any suppressed flag at f_supp. If that retained flag's time range overlaps the suppressed fundamental's time range by ≥50% of the retained flag's frame count: suppress it. One pass suffices — the fundamental is always suppressed first (it accumulates the most matches), and all overtones are at {2*f_supp, 3*f_supp, ...}. In the 440 + 880 + 1320 Hz example: 440 Hz suppressed in 4a; cascade 4b suppresses 880 Hz (= 2×440) and 1320 Hz (= 3×440). Zero flags emitted.

  AC3 cascade invariant added: 6.4 kHz pure sine has no suppressed fundamental; cascade pass adds zero suppressions. The "Suppression control (musical tone)" testability entry has been updated to document that 880 Hz and 1320 Hz are suppressed by cascade (not by the independent check), and to show the per-flag n_matched values for each partial.

  Downstream impact on implementation: `_detect_stationary_whistle()` must add a cascade pass loop after the per-flag independent check loop, iterating over suppressed flags and suppressing their harmonics in the retained set. No changes to constants, the merge step, or other detectors.

- **2026-08-13 (third pass — targeted blocker fixes from mastering-review-arch-revision.md)**:

  **Fix 1 — SMEARED_TRANSIENT §5.1: LCF gate band-limited to 6–16 kHz (mastering-engineer Findings 1 and 2)**:
  The LCF gate previously computed crest factor on full-band audio while the rise-time measurement evaluates the 6–16 kHz HF band. A kick drum has no HF energy — it passes the full-band gate and the rise-time measurement then evaluates whatever unrelated HF content follows, producing false positives by the same mechanism as DEF-707. The gate now computes LCF on the same 6–16 kHz band used by `_hf_envelope()`. Step 2a updated: `hf_audio` (6–16 kHz bandpass applied before crest factor computation). Onset localisation added: within the flux frame's time span, the sample of maximum HF envelope amplitude is identified; the 30 ms LCF window and the 150 ms rise-time window in Step 3 are both anchored to this sample — not to the frame midpoint. Threshold re-derived for the HF band: snare/cymbal HF crest 8–15 dB, kick ≈ 0 dB (correctly excluded by gate), vocal sibilant (/s/) 1–3 dB; threshold 6 dB sits in the gap (3–8 dB). Constant renamed `CREST_FACTOR_THRESHOLD_DB` → `HF_CREST_FACTOR_THRESHOLD_DB` in §5.1, §6. Testability controls updated to match: kick drum is now a gate-rejection negative control (HF-LCF ≈ 0 dB → gate fails); snare/cymbal is the gate-passing negative control (HF-LCF > 10 dB, short rise-time → gate passes, 0 flags). Label remains PROVISIONAL; requires validation on reference tracks.

  **Fix 2 — DIGITAL_HAZE §5.2: Duration trigger ambiguity resolved as Option a (mastering-engineer Finding 1)**:
  Prior text "sustained for >= 2.0 s (8 consecutive STFT frames)" was internally contradictory: if "8 consecutive frames" meant 8 consecutive qualifying 2 s windows, the positive control (3 s stationary noise, ≈ 5 overlapping windows) could not trigger. Resolved as Option a: the 2 s / 8-frame requirement describes the metric computation window only, not a consecutive-windows run. One qualifying window is sufficient to trigger DIGITAL_HAZE. Step 4 rewritten to state this explicitly. Testability positive control updated: 3 s signal produces ≈ 12 STFT frames and multiple overlapping qualifying 2 s windows; one window triggers.

  **Fix 3 — STATIONARY_WHISTLE §5.3: Frequency tolerance applied to harmonic position matching (mastering-engineer Finding 1)**:
  Prior Step 4 searched for "the nearest bin to h_k" — a single 2 Hz bin. Real sustained tones have vibrato and pitch drift that move harmonics across several bins over a 1.5 s phrase; single-bin matching would fail to suppress musical tones containing vibrato, leaving DEF-705 Issue B open on the Chemical Brothers vocal content for which it was raised. Step 4 updated: search within ±FREQUENCY_TOLERANCE_HZ (50 Hz) of `h_k`; take the bin with maximum prominence within that range. The `FREQUENCY_TOLERANCE_HZ` constant (already defined for flag merging in Step 5) is now also applied to harmonic position matching in Step 4.

  **Downstream impact on implementation**: `_detect_smeared_transient()` must bandpass-filter to 6–16 kHz before computing LCF, and must localise the window anchor to the sample of maximum HF envelope amplitude within the flux frame rather than the frame midpoint. Constant reference `CREST_FACTOR_THRESHOLD_DB` must be renamed `HF_CREST_FACTOR_THRESHOLD_DB` throughout the implementation. `_detect_digital_haze()` trigger logic must fire on a single qualifying window (no consecutive-window accumulation). `_detect_stationary_whistle()` harmonic search must use a ±50 Hz bin range with maximum-prominence selection instead of nearest-bin lookup.

- **2026-08-13 (second pass — advisor corrections to TMI_HF derivation, SFM asymptote, LCF estimate scope, §9.2 expected counts)**:

  **TMI_HF derivation corrected (§5.2 and §9.3)**: The prior text stated "Theoretical lower bound for stationary Gaussian noise in N_bins independent bins is CV ≈ 1/sqrt(N_bins/2) ≈ 0.022" as the basis for the 0.10 provisional threshold. This was factually wrong: that formula describes the within-frame estimator variance of a single E_HF[t] estimate averaged over N_bins frequency bins, not the floor of TMI_HF. TMI_HF is a coefficient of variation across only 8 time frames, and those frames are 50% correlated due to STFT overlap. The distribution of TMI_HF under stationary noise cannot be derived from the single-frame estimator error alone; it requires simulation. The provisional 0.10 figure is retained as a directional estimate but is now correctly labelled as unvalidated and requiring simulation to characterise. §9.3 updated to specify the required simulation step alongside reference-track measurement.

  **SFM asymptote closed form cited (§5.2)**: DEF-712 records the theoretical asymptote for STFT magnitudes under Gaussian input as `exp(-γ/2) / (√π/2) ≈ 0.8455`, where γ is the Euler–Mascheroni constant. This is consistent with the empirical probe (mean 0.847). A derivation ambiguity is noted: `√π/2 ≈ 0.886` gives 0.8455 (matching empirical); `√(π/2) ≈ 1.253` gives ≈ 0.598 (not matching). Mastering engineer should verify the correct closed form. Both the closed form citation and the empirical confirmation are now cited in §5.2 per H4.

  **LCF 6 dB threshold: estimate scope clarified (§5.1)**: The prior text presented a shape-based derivation (vocal 2–4 dB, percussive 8–20 dB, midpoint 6 dB) without noting that the actual measured LCF depends on window position relative to the onset centre, pre-onset energy, and surrounding dynamics — not solely on the attack shape. The threshold is now explicitly labelled as a shape-based estimate only, with the window-position caveat stated. The PROVISIONAL label in §6 already reflected this; §5.1 now matches.

  **§9.2 expected counts for Leftfield and Wavy Gravy updated**: The prior "0–2 expected" entries were justified under the SFM-based DIGITAL_HAZE method (reverb tails, HF loss characteristics). That rationale does not apply to the temporal method (TMI_HF + CC_HF_LF). Both entries are now set to "0 pending temporal-method calibration" with the stale-rationale note, pending actual measurement after implementation.

  **DEF-702 Hz-to-bin conversion clarified as required implementation change (§5.3)**: The DEF-702 resolution note previously stated the Hz-to-bin conversion "if not already present, must be added." The prior DEF-704 fix hard-coded `kernel_size=51` and `distance=25` (bin counts) in the implementation; the conversion is therefore not present. This is stated as a required implementation change in §5.3.

- **2026-08-13 (DEF-701, DEF-702, DEF-703, DEF-705, DEF-712, Gate 2 findings)**:

  **Source note**: `mastering-review-gate2.md` was not present in the story directory. Gate 2 findings (Finding 1, 3, 4, 5) were sourced from the invoking agent's task description. This provenance is recorded here because this project previously shipped a wrong constant that survived two reviews on asserted evidence (DEF-203); agent-sourced findings carry less authority than a file-based mastering-engineer review document and should be verified if a Gate 2 review file exists.

  **DEF-701 — AudioBuffer → plain-array contract (option b, method change)**:
  Removed `AudioBuffer` from §4.1 and §7.1. Updated public API to `detect_artifacts(audio: np.ndarray, sr: int)`, consistent with existing `analysis.measure_all(audio, sr, config)` convention. Raised explicit conflict with `docs/ARCHITECTURE.md §3.1` (which defines `AudioBuffer` as the ANALYSIS stage input). That conflict is pre-existing and predates STORY-007; requires project-level resolution. Implementation (plain arrays) is now consistent with what was shipped.

  **DEF-702 — FFT scale factor 4× → 1× (parameter change confirmed correct)**:
  Confirmed `nfft = nperseg` (no zero-padding) is correct. Bin spacing = 2 Hz at 500 ms window / 44.1 kHz, sufficient for all detectors. Zero-padding adds interpolated bins but no real frequency resolution. 4× would have consumed ~1.7 GB for a 5-min stereo track — impractical. Added note that Hz-specified constants (WHISTLE_BACKGROUND_KERNEL_HZ, WHISTLE_MIN_PEAK_DISTANCE_HZ) must be converted to bin counts at runtime from `sr` and `nfft`, to avoid coupling detector behaviour to the FFT size.

  **DEF-703 — pandas removed (method change)**:
  Removed `pandas.Series.rolling()` from §3 library table. Confirmed `_find_consecutive_runs()` (pure numpy) is the correct approach. Pandas is not installed and must not be added as a dependency for this purpose.

  **DEF-705 Issue A — SMEARED_TRANSIENT percussive gate (method change)**:
  Added local crest factor gate (LCF >= 6 dB) before rise-time measurement in §5.1. This gates on onset type — only impulsive (percussive) onsets proceed to rise-time measurement. Vocal phrase starts have lower LCF (2–4 dB) and are excluded. This also repairs a requirements.md conformance gap: `requirements.md` line 22 specifies "spectral flux + local crest factor on percussive onsets"; the prior architecture dropped the crest factor criterion. Threshold 6 dB is provisional — must be validated on Chemical Brothers and GusGus after implementation.

  **DEF-705 Issue B — STATIONARY_WHISTLE harmonic stack suppression (method change)**:
  Added harmonic relationship check in §5.3 step 4. For each persistent peak at f, checks {2f, 3f, f/2, f/3} for matching persistent peaks with >= 3 dB prominence over the same time range. If >= 2 positions match, flag is suppressed (musical tone). Out-of-band positions (< bin_hz or > Nyquist) are excluded from count ("not evaluated"), not treated as absent. Time-coincidence requirement: harmonic peak must overlap primary by >= 50% of duration. AC3 invariant: 6.4 kHz pure sine has no harmonic stack, zero matches, flag not suppressed.

  **DEF-712 — DIGITAL_HAZE: SFM replaced with temporal approach (method change)**:
  SFM removed. Physical ceiling of SFM for Rayleigh-distributed STFT magnitudes confirmed empirically (DEF-712): mean 0.847, 4/11 frames above 0.85 threshold, longest run 2 frames. The canonical positive case (genuine broadband HF noise) cannot reliably trigger the SFM detector. Additionally, SFM cannot discriminate Suno HF noise from natural cymbal/reverb content (same spectral flatness axis). Replacement: HF Temporal Modulation Index (TMI_HF) + HF-LF temporal decoupling (CC_HF_LF). The discriminating axis is temporal, not spectral: Suno HF noise is stationary and decoupled from musical events; natural HF is modulated and time-locked to its source. Both TMI_HF_THRESHOLD and CC_HF_LF_THRESHOLD are provisional and must be calibrated by the mastering engineer from actual Suno outputs and reference tracks. Conflict with requirements.md AC4 noted in §10.2.

  **Gate 2 §Finding 4 — Reference track re-measurement required**:
  All prior reference track measurements are stale (pre-fix figures). Required post-implementation re-measurement of all five reference tracks noted in §9.2.

  **Gate 2 §Finding 5 — PHASE_SWISH conjunction validation required**:
  Added validation step in §5.4: post-implementation, measure each of the three conjunction conditions independently on reference material and report co-occurrence frequencies. If the three-way AND never co-occurs, the detector is untested and thresholds must be revised.

  **Downstream impact on implementation**:
  - `detect_artifacts()` function signature is now plain-array `(audio, sr)` — any implementation using `AudioBuffer` must be updated.
  - `_detect_smeared_transient()` gains a percussive gate step — implementation requires `_local_crest_factor()` helper.
  - `_detect_digital_haze()` is a near-complete rewrite — all SFM computation removed; new TMI_HF and CC_HF_LF computation required.
  - `_detect_stationary_whistle()` gains a harmonic-check step — implementation requires `_check_harmonic_stack()` helper using the existing occupancy matrix.
  - `_detect_stationary_whistle()` Hz-to-bin conversion: hard-coded `kernel_size=51` and `distance=25` must be replaced with runtime computation from Hz constants and `sr/nfft`.
  - Test fixture F-004 and TC-005 are invalidated by the DIGITAL_HAZE method change; test-case-writer must redesign these.

- **2026-08-12 (Revised — Gate 1 blockers resolved)**:
  - Removed HF/LM ratio detector branch. Simplified SMEARED_TRANSIENT to rise-time only.
  - Changed from non-overlapping to sliding-window STFT (hop = 250 ms, 50% overlap).
  - Updated threshold constants; added HOP_SIZE_S; removed HF_LM_RATIO_THRESHOLD_DB.
  - Updated API to return tuple `(AudioBuffer, ArtifactDetectionResult)`.
  - Added reference-track validation tests and drift-rate detector question.

- **2026-08-12 (Initial)**:
  - Architecture created for STORY-007. Aligned with docs/ARCHITECTURE.md stage contracts. Thresholds derived and justified. Known limitations and open questions documented. Gate 1 review identified blockers.
