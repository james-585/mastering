# Mastering Report

## At a glance

- Overall result: PASS
- Loudness: -13.90 LUFS -> -13.54 LUFS (target -13.54 LUFS)
- True peak: -3.83 dBTP -> -2.77 dBTP (ceiling -1.00 dBTP)
- Demuddification: low-mid energy improved from 0.58 dB to -0.59 dB relative to reference, and the muddiness flag changed from FLAGGED to clear.

- Tool version: 0.1.0
- Generated (UTC): 2026-08-20T12:14:21.199730+00:00
- Input: `Reference Tracks\Sunday Club.wav`
- Output: `C:\Users\james\Documents\suno-mastering\artifacts\Sunday Club_mastered.wav`
- Input SHA-256: `215d7fde4ae18444677094e26c87f915f1e445ffb493fc7bbd2eebbcfbf5708d`
- Output SHA-256: `55d67b9eaaf528f9b8b3fa7d3a5d951d8c3561f7ae49e7579e6e04d03b8e4e5c`
- Non-destructive integrity check: PASSED

### Before (pre-master)

- Duration: 254.7 s
- Channels: 2 (stereo)
- Integrated loudness: -13.90 LUFS
- True peak: -3.83 dBTP
- Dynamic range (TT DR): DR9
- Clipping: 0 sample(s) clipped (0 event(s)), 0 inter-sample over(s), severity: none
- Stereo/mono compatibility: overall correlation 0.905 (compatible), 3 stereo-widened region(s) identified

| Band | Range | Measured (rel. dB) | Reference (rel. dB) | Deviation | Flag |
|---|---|---|---|---|---|
| Low-end | 20-120 Hz | 10.59 dB | -1.50 dB | 12.09 dB | ok |
| Low-mid/mud | 200-500 Hz | 0.58 dB | -3.00 dB | 3.58 dB | FLAGGED (muddiness) |
| Presence/harsh | 2000-5000 Hz | -4.16 dB | -4.00 dB | -0.16 dB | ok |

### After (post-master)

- Duration: 254.7 s
- Channels: 2 (stereo)
- Integrated loudness: -13.54 LUFS
- True peak: -2.77 dBTP
- Dynamic range (TT DR): DR9
- Clipping: 0 sample(s) clipped (0 event(s)), 0 inter-sample over(s), severity: none
- Stereo/mono compatibility: overall correlation 0.899 (compatible), 2 stereo-widened region(s) identified

| Band | Range | Measured (rel. dB) | Reference (rel. dB) | Deviation | Flag |
|---|---|---|---|---|---|
| Low-end | 20-120 Hz | 9.82 dB | -1.50 dB | 11.32 dB | ok |
| Low-mid/mud | 200-500 Hz | -0.59 dB | -3.00 dB | 2.41 dB | ok |
| Presence/harsh | 2000-5000 Hz | -3.73 dB | -4.00 dB | 0.27 dB | ok |

## Artifact summary
### Before (pre-master)

- Density score: 1.0000
- Total flags: 454
- Highest-confidence issue: 1.00
- Most common issue types:
  - STATIONARY_WHISTLE: 452
  - PHASE_SWISH: 1
  - SMEARED_TRANSIENT: 1

- Summary warnings:
  - PHASE_SWISH detected at 04:14.00 (confidence 0.80) — HF phase decorrelation; may be intentional stereo width
  - SMEARED_TRANSIENT detected at 04:14.64 (rise-time 41.29 ms, confidence 0.95) — transient blur artifact
  - STATIONARY_WHISTLE detected at 00:00.25 (4666.0 Hz, confidence 1.00) — consider re-generating track
  - ... and 451 more warning(s)

### After (post-master)

- Density score: 1.0000
- Total flags: 455
- Highest-confidence issue: 1.00
- Most common issue types:
  - STATIONARY_WHISTLE: 453
  - PHASE_SWISH: 1
  - SMEARED_TRANSIENT: 1

- Summary warnings:
  - PHASE_SWISH detected at 04:14.00 (confidence 0.80) — HF phase decorrelation; may be intentional stereo width
  - SMEARED_TRANSIENT detected at 04:14.64 (rise-time 41.29 ms, confidence 0.95) — transient blur artifact
  - STATIONARY_WHISTLE detected at 00:00.25 (4666.0 Hz, confidence 1.00) — consider re-generating track
  - ... and 452 more warning(s)

## Corrective actions taken

- No resample needed (source sample rate already supported).
- Spectral corrective EQ: band=sub, trigger=range_compliance, applied=-2.00 dB, resulting=+4.83 dB, cap_reached=True
- Spectral corrective EQ: band=low_mid, trigger=de_mud, applied=-2.00 dB, resulting=+4.54 dB, cap_reached=True
- Stereo narrowing: 165.50s-167.00s, side scaled by 0.986 (correlation -0.050 -> 0.000)
- Stem transient restoration [mix]: attack_boost, gain=+0.61 dB (requested +0.61 dB), onset peak 0.0631 -> 0.0677, severity=2.181 (transient attack restoration: gain 0.61 dB on local onset energy)
- Final bus glue [mix]: dynamic_balance, gain=-0.20 dB, peak 0.6202 -> 0.6061 (Dynamic balance trimmed a slightly over-energetic bus to preserve contour and keep the mix from feeling loose or unstable.)
- Loudness/limiting: target -13.54 LUFS, achieved -13.54 LUFS, true peak -2.77 dBTP, DR9 (source DR9, floor DR8), gain applied 1.55 dB over 7 solver iteration(s).

- Dither: TPDF, seed=42

## Config used

```json
{
  "lufs_target_band": [
    -14.5,
    -13.5
  ],
  "lufs_floor": -16.0,
  "true_peak_ceiling_dbtp": -1.0,
  "true_peak_oversample_factor": 8,
  "dr_floor": 8.0,
  "dr_max_reduction_db": 3.0,
  "eq_max_gain_db": 2.0,
  "phase_correlation_floor": 0.0,
  "phase_correlation_widened_target": 0.3,
  "output_bit_depth": 24,
  "supported_sample_rates": [
    44100,
    48000
  ],
  "dither_seed": 42,
  "solver_max_iterations": 32,
  "spectral_correction_scope": "sub and low_mid only; air/high/high_mid/low are informational"
}
```