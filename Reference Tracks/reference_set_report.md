# Reference Track Set Analysis Report

- Schema version: 2.2
- Tool version: 0.1.0
- Generated (UTC): 2026-08-15T03:24:34.593581+00:00
- Decoder identity: {"wav": "libsndfile-1.2.2"}

> **Standing caveat**: true-peak (dBTP) and HF-extension figures in this report inherit a bounded, direction-known near-Nyquist under-read from the shared true-peak metering FIR filter (flat to <0.01 dB only up to ~80% of Nyquist, ~0.4 dB at 90%, ~1.5-2 dB at 94-95%, ~5.9 dB at 99.9% -- always attenuation, never over-read). These figures are report-only, not validated to target-setting precision (resolved open question #5). MP3-decoded true-peak figures additionally carry a SEPARATE, opposite-direction bias (inter-sample peaks introduced by lossy decoding push measured true peak UP) -- the two effects are stated separately here, never netted against each other.

## Per-track measurements

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\Black_Flute_Remastered.wav`

- Source format: WAV, lossless -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference) (decoder: libsndfile-1.2.2)
- Duration: 226.3 s, 48000 Hz, stereo
- Integrated loudness: -8.70 LUFS
- Loudness range (LRA): 6.25 LU (self-consistency check delta: 0.042 LU)
- True peak: 0.52 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR8 (exact: 8.26)
- Overall stereo correlation: 0.699
- Mono-sum level change: -0.80 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 15788 Hz, confidence 1.00 (stable across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - band limit at 15788 Hz falls within an encoder-typical cutoff band -- suspected lossy-source transcode, review before treating as a clean reference.
  - Per-segment localization robustness: 0.08 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise)
  - Whole-track j* margin: 0.39 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | -3.75 |
| low | 60-120 Hz | 8.62 |
| low_mid | 120-500 Hz | 8.52 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -1.24 |
| high | 5000-10000 Hz | -4.06 |
| air | 10000-24000 Hz | -11.44 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.040 |
| low | 60-120 Hz | 0.147 |
| low_mid | 120-500 Hz | 0.408 |
| mid | 500-2000 Hz | 0.420 |
| high_mid | 2000-5000 Hz | 0.579 |
| high | 5000-10000 Hz | 0.160 |
| air | 10000-24000 Hz | 0.127 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\Cavernous Rave (Edit).wav`

- Source format: WAV, lossless (decoder: libsndfile-1.2.2)
- Duration: 343.0 s, 48000 Hz, stereo
- Integrated loudness: -12.96 LUFS
- Loudness range (LRA): 6.90 LU (self-consistency check delta: 0.037 LU)
- True peak: -2.39 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR10 (exact: 9.80)
- Overall stereo correlation: 0.970
- Mono-sum level change: -0.11 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: No artificial band-limit detected (full-band / clean material, or not measurable in the top of the range near Nyquist -- see architecture.md Section 3.5), confidence 0.60 (stable)

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | 6.61 |
| low | 60-120 Hz | 3.93 |
| low_mid | 120-500 Hz | 2.89 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -4.89 |
| high | 5000-10000 Hz | -9.13 |
| air | 10000-24000 Hz | -14.36 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.000 |
| low | 60-120 Hz | 0.008 |
| low_mid | 120-500 Hz | 0.067 |
| mid | 500-2000 Hz | 0.118 |
| high_mid | 2000-5000 Hz | 0.085 |
| high | 5000-10000 Hz | 0.062 |
| air | 10000-24000 Hz | 0.128 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\GusGus_-_Over_Arabian_Horse_Album.wav`

- Source format: WAV, lossless -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference) (decoder: libsndfile-1.2.2)
- Duration: 354.5 s, 48000 Hz, stereo
- Integrated loudness: -7.56 LUFS
- Loudness range (LRA): 3.21 LU (self-consistency check delta: 0.039 LU)
- True peak: 0.61 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR7 (exact: 6.60)
- Overall stereo correlation: 0.849
- Mono-sum level change: -0.46 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 16251 Hz, confidence 1.00 (stable across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - band limit at 16251 Hz falls within an encoder-typical cutoff band -- suspected lossy-source transcode, review before treating as a clean reference.
  - Per-segment localization robustness: 2.12 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise)
  - Whole-track j* margin: 3.62 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | -3.09 |
| low | 60-120 Hz | 4.34 |
| low_mid | 120-500 Hz | 3.39 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -13.41 |
| high | 5000-10000 Hz | -17.06 |
| air | 10000-24000 Hz | -20.05 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.001 |
| low | 60-120 Hz | 0.001 |
| low_mid | 120-500 Hz | 0.173 |
| mid | 500-2000 Hz | 0.461 |
| high_mid | 2000-5000 Hz | 0.455 |
| high | 5000-10000 Hz | 0.657 |
| air | 10000-24000 Hz | 0.124 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\Leftfield_-_Melt_Audio.wav`

- Source format: WAV, lossless -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference) (decoder: libsndfile-1.2.2)
- Duration: 313.8 s, 48000 Hz, stereo
- Integrated loudness: -15.62 LUFS
- Loudness range (LRA): 11.26 LU (self-consistency check delta: 0.038 LU)
- True peak: -0.19 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR15 (exact: 14.86)
- Overall stereo correlation: 0.827
- Mono-sum level change: -0.52 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 20475 Hz, confidence 1.00 (stable across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - band limit at 20475 Hz falls within an encoder-typical cutoff band -- suspected lossy-source transcode, review before treating as a clean reference.
  - Per-segment localization robustness: 8.00 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise)
  - Whole-track j* margin: 8.00 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | -1.74 |
| low | 60-120 Hz | 3.27 |
| low_mid | 120-500 Hz | 0.93 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -12.59 |
| high | 5000-10000 Hz | -20.68 |
| air | 10000-24000 Hz | -25.10 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.067 |
| low | 60-120 Hz | 0.074 |
| low_mid | 120-500 Hz | 0.258 |
| mid | 500-2000 Hz | 0.301 |
| high_mid | 2000-5000 Hz | 0.530 |
| high | 5000-10000 Hz | 0.285 |
| air | 10000-24000 Hz | 0.247 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\Sunday Club.wav`

- Source format: WAV, lossless -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference) (decoder: libsndfile-1.2.2)
- Duration: 254.7 s, 48000 Hz, stereo
- Integrated loudness: -13.90 LUFS
- Loudness range (LRA): 3.75 LU (self-consistency check delta: 0.038 LU)
- True peak: -3.83 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR9 (exact: 8.55)
- Overall stereo correlation: 0.905
- Mono-sum level change: -0.34 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 19892 Hz, confidence 0.80 (stable across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - band limit at 19892 Hz falls within an encoder-typical cutoff band -- suspected lossy-source transcode, review before treating as a clean reference.
  - Per-segment localization robustness: 0.35 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise)
  - Per-segment reliability caveat: per-segment gate false positive detected: one or more segments returned a non-None value disagreeing with the whole-track result by more than 2000 Hz. This indicates the per-segment gate fired on programme-content spectral decline, not a band-limit wall. Per-segment values on complex material must not be used as alternative band-limit estimates. None on a segment is an honest abstention (insufficient spectral evidence) and is distinct from this false-positive condition: None does not indicate the gate misfired. stable=False with low confidence and a strong whole-track margin is the correct honest report under current gate parameters.
  - Whole-track j* margin: 0.67 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | 6.83 |
| low | 60-120 Hz | 8.12 |
| low_mid | 120-500 Hz | 6.54 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -4.16 |
| high | 5000-10000 Hz | -6.93 |
| air | 10000-24000 Hz | -10.36 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.067 |
| low | 60-120 Hz | 0.017 |
| low_mid | 120-500 Hz | 0.117 |
| mid | 500-2000 Hz | 0.276 |
| high_mid | 2000-5000 Hz | 0.510 |
| high | 5000-10000 Hz | 0.453 |
| air | 10000-24000 Hz | 0.395 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav`

- Source format: WAV, lossless -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference) (decoder: libsndfile-1.2.2)
- Duration: 254.2 s, 48000 Hz, stereo
- Integrated loudness: -8.53 LUFS
- Loudness range (LRA): 12.20 LU (self-consistency check delta: 0.041 LU)
- True peak: 0.68 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR9 (exact: 8.65)
- Overall stereo correlation: 0.703
- Mono-sum level change: -1.02 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 20475 Hz, confidence 0.40 (UNSTABLE across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - band limit at 20475 Hz falls within an encoder-typical cutoff band -- suspected lossy-source transcode, review before treating as a clean reference.
  - Per-segment localization robustness: 0.32 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise; if stable=False, this minimum may reflect a per-segment false positive rather than the whole-track wall's fragility -- see DEF-205)
  - Per-segment reliability caveat: per-segment gate false positive detected: one or more segments returned a non-None value disagreeing with the whole-track result by more than 2000 Hz. This indicates the per-segment gate fired on programme-content spectral decline, not a band-limit wall. Per-segment values on complex material must not be used as alternative band-limit estimates. None on a segment is an honest abstention (insufficient spectral evidence) and is distinct from this false-positive condition: None does not indicate the gate misfired. stable=False with low confidence and a strong whole-track margin is the correct honest report under current gate parameters.
  - Whole-track j* margin: 3.22 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | 1.94 |
| low | 60-120 Hz | 0.47 |
| low_mid | 120-500 Hz | -0.15 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -6.71 |
| high | 5000-10000 Hz | -9.77 |
| air | 10000-24000 Hz | -16.01 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.009 |
| low | 60-120 Hz | 0.017 |
| low_mid | 120-500 Hz | 0.416 |
| mid | 500-2000 Hz | 0.670 |
| high_mid | 2000-5000 Hz | 0.608 |
| high | 5000-10000 Hz | 0.129 |
| air | 10000-24000 Hz | 0.110 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\This one.wav`

- Source format: WAV, lossless (decoder: libsndfile-1.2.2)
- Duration: 243.3 s, 48000 Hz, stereo
- Integrated loudness: -13.33 LUFS
- Loudness range (LRA): 4.15 LU (self-consistency check delta: 0.038 LU)
- True peak: -3.93 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR8 (exact: 8.24)
- Overall stereo correlation: 0.890
- Mono-sum level change: -0.35 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 17722 Hz, confidence 1.00 (stable across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - Per-segment localization robustness: 0.16 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise)
  - Whole-track j* margin: 6.03 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | 5.73 |
| low | 60-120 Hz | 6.29 |
| low_mid | 120-500 Hz | 5.73 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -4.78 |
| high | 5000-10000 Hz | -6.04 |
| air | 10000-24000 Hz | -11.65 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.009 |
| low | 60-120 Hz | 0.046 |
| low_mid | 120-500 Hz | 0.195 |
| mid | 500-2000 Hz | 0.330 |
| high_mid | 2000-5000 Hz | 0.297 |
| high | 5000-10000 Hz | 0.038 |
| air | 10000-24000 Hz | 0.010 |

### `C:\Users\james\Documents\suno-mastering\Reference Tracks\Wavy_Gravy.wav`

- Source format: WAV, lossless -- SUSPECTED LOSSY-SOURCE TRANSCODE (review before treating as clean reference) (decoder: libsndfile-1.2.2)
- Duration: 449.6 s, 48000 Hz, stereo
- Integrated loudness: -13.11 LUFS
- Loudness range (LRA): 15.16 LU (self-consistency check delta: 0.039 LU)
- True peak: 0.62 dBTP (informational only -- see standing caveat below; not validated to target-setting precision)
- Dynamic range (TT DR): DR14 (exact: 13.91)
- Overall stereo correlation: 0.698
- Mono-sum level change: -0.95 dB (rho=0/fully-decorrelated floor: -3.01 dB, DOMAIN.md Section 3 / architecture.md Section 2.1; excess cancellation flagged: False)
- HF extension: 20475 Hz, confidence 0.60 (stable across segments) -- inherits true-peak-style near-Nyquist metering caveats; report-only, not target-setting
  - band limit at 20475 Hz falls within an encoder-typical cutoff band -- suspected lossy-source transcode, review before treating as a clean reference.
  - Per-segment localization robustness: 5.39 dB (minimum of rightward and leftward j* margins across segments that found a cliff; <0.5 dB within Welch estimator noise)
  - Whole-track j* margin: 8.00 dB

| Seven-band | Range | Relative dB |
|---|---|---|
| sub | 20-60 Hz | 1.65 |
| low | 60-120 Hz | 2.68 |
| low_mid | 120-500 Hz | -1.30 |
| mid | 500-2000 Hz | 0.00 |
| high_mid | 2000-5000 Hz | -7.21 |
| high | 5000-10000 Hz | -9.19 |
| air | 10000-24000 Hz | -13.15 |

| Per-band stereo width | Range | Width (0=mono, 1=decorrelated) |
|---|---|---|
| sub | 20-60 Hz | 0.002 |
| low | 60-120 Hz | 0.006 |
| low_mid | 120-500 Hz | 0.488 |
| mid | 500-2000 Hz | 0.766 |
| high_mid | 2000-5000 Hz | 0.617 |
| high | 5000-10000 Hz | 0.064 |
| air | 10000-24000 Hz | 0.730 |

## Aggregate statistics (median / min / max, N and contributing tracks per AC12)

| Metric | Median | Min | Max | N |
|---|---|---|---|---|
| integrated_lufs | -13.036 | -15.620 | -7.565 | N=8 |
| true_peak_dbtp | 0.169 | -3.933 | 0.679 | N=8 |
| dynamic_range_db_exact | 8.596 | 6.599 | 14.856 | N=8 |
| lra_lu | 6.573 | 3.211 | 15.162 | N=8 |
| seven_band.sub.relative_db | 1.799 | -3.747 | 6.835 | N=8 |
| seven_band.low.relative_db | 4.135 | 0.471 | 8.617 | N=8 |
| seven_band.low_mid.relative_db | 3.140 | -1.299 | 8.522 | N=8 |
| seven_band.mid.relative_db | 0.000 | 0.000 | 0.000 | N=8 |
| seven_band.high_mid.relative_db | -5.802 | -13.408 | -1.243 | N=8 |
| seven_band.high.relative_db | -9.157 | -20.676 | -4.060 | N=8 |
| seven_band.air.relative_db | -13.753 | -25.097 | -10.362 | N=8 |
| overall_correlation | 0.838 | 0.698 | 0.970 | N=8 |
| mono_sum.mono_sum_level_change_db | -0.492 | -1.023 | -0.112 | N=8 |
| per_band_stereo_width.sub | 0.009 | 0.000 | 0.067 | N=8 |
| per_band_stereo_width.low | 0.017 | 0.001 | 0.147 | N=8 |
| per_band_stereo_width.low_mid | 0.226 | 0.067 | 0.488 | N=8 |
| per_band_stereo_width.mid | 0.375 | 0.118 | 0.766 | N=8 |
| per_band_stereo_width.high_mid | 0.520 | 0.085 | 0.617 | N=8 |
| per_band_stereo_width.high | 0.145 | 0.038 | 0.657 | N=8 |
| per_band_stereo_width.air | 0.127 | 0.010 | 0.730 | N=8 |
| hf_extension_hf_band_limit_hz.48000hz | 19892.176 | 15788.430 | 20475.061 | N=7 |

**hf_extension_hf_band_limit_hz.48000hz** exclusions:
- `C:\Users\james\Documents\suno-mastering\Reference Tracks\Cavernous Rave (Edit).wav`: no band limit detected (confirmed absence of a cliff, or not measurable near Nyquist) - legitimate, not a defect

## Config used

```json
{
  "seven_bands_hz": {
    "sub": [
      20.0,
      60.0
    ],
    "low": [
      60.0,
      120.0
    ],
    "low_mid": [
      120.0,
      500.0
    ],
    "mid": [
      500.0,
      2000.0
    ],
    "high_mid": [
      2000.0,
      5000.0
    ],
    "high": [
      5000.0,
      10000.0
    ],
    "air": [
      10000.0,
      null
    ]
  },
  "lra_window_s": 3.0,
  "lra_hop_s": 0.1,
  "lra_relative_gate_lu": -20.0,
  "lra_tolerance_lu": 1.0,
  "hf_stability_segment_count": 5,
  "hf_min_duration_s": 30.0,
  "hf_stability_tolerance_hz": 2000.0,
  "hf_cliff_log_band_octave_fraction": 0.041666666666666664,
  "hf_cliff_target_window_octaves": 0.3333333333333333,
  "hf_cliff_required_drop_db": 8.0,
  "hf_cliff_min_window_bands": 3,
  "hf_cliff_min_floor_bands": 2,
  "hf_cliff_slope_db_per_octave": 24.0,
  "hf_cliff_passband_max_slope_db_per_octave": 12.0,
  "hf_cliff_floor_min_fraction": 0.8,
  "hf_cliff_floor_noise_margin_db": 3.0,
  "hf_cliff_search_min_hz": 3000.0,
  "hf_cliff_confidence_stable_floor": 0.6,
  "transcode_suspect_bands_hz": [
    [
      15500.0,
      16500.0
    ],
    [
      18500.0,
      19500.0
    ],
    [
      19500.0,
      20500.0
    ]
  ],
  "mono_band_cancellation_excess_db": -3.0,
  "mono_sum_excess_cancellation_threshold_db": -4.5,
  "hf_lossless_n_omit_below": 1,
  "hf_lossless_n_low_confidence_below": 3,
  "true_peak_oversample_factor": 8,
  "dr_block_seconds": 3.0,
  "dr_exclude_fraction": 0.2
}
```