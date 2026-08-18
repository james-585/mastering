# Mastering Report

## At a glance

- Overall result: PASS
- Loudness: -13.90 LUFS -> -13.55 LUFS (target -13.55 LUFS)
- True peak: -3.83 dBTP -> -1.00 dBTP (ceiling -1.00 dBTP)
- Demuddification: low-mid energy improved from 0.58 dB to -4.88 dB relative to reference, and the muddiness flag changed from FLAGGED to clear.

- Tool version: 0.1.0
- Generated (UTC): 2026-08-18T13:23:21.163760+00:00
- Input: `Reference Tracks\Sunday Club.wav`
- Output: `C:\Users\james\Documents\suno-mastering\artifacts\Sunday Club_mastered.wav`
- Input SHA-256: `215d7fde4ae18444677094e26c87f915f1e445ffb493fc7bbd2eebbcfbf5708d`
- Output SHA-256: `8e5db3f92105013b36f2478bbac36ee3e8d48a88d123834ca5e4439dfaab771b`
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
- Integrated loudness: -13.55 LUFS
- True peak: -1.00 dBTP
- Dynamic range (TT DR): DR11
- Clipping: 0 sample(s) clipped (0 event(s)), 0 inter-sample over(s), severity: none
- Stereo/mono compatibility: overall correlation 0.910 (compatible), 3 stereo-widened region(s) identified

| Band | Range | Measured (rel. dB) | Reference (rel. dB) | Deviation | Flag |
|---|---|---|---|---|---|
| Low-end | 20-120 Hz | 11.39 dB | -1.50 dB | 12.89 dB | ok |
| Low-mid/mud | 200-500 Hz | -4.88 dB | -3.00 dB | -1.88 dB | ok |
| Presence/harsh | 2000-5000 Hz | -2.82 dB | -4.00 dB | 1.18 dB | ok |

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

- Density score: 0.7360
- Total flags: 93
- Highest-confidence issue: 1.00
- Most common issue types:
  - STATIONARY_WHISTLE: 85
  - SMEARED_TRANSIENT: 7
  - PHASE_SWISH: 1

- Summary warnings:
  - PHASE_SWISH detected at 04:14.00 (confidence 0.80) — HF phase decorrelation; may be intentional stereo width
  - SMEARED_TRANSIENT detected at 03:23.12 (rise-time 34.35 ms, confidence 0.85) — transient blur artifact
  - SMEARED_TRANSIENT detected at 03:42.92 (rise-time 44.71 ms, confidence 0.95) — transient blur artifact
  - ... and 87 more warning(s)

## Corrective actions taken

- No resample needed (source sample rate already supported).
- Spectral corrective EQ: band=sub, trigger=range_compliance, applied=-2.00 dB, resulting=+7.05 dB, cap_reached=True
- Spectral corrective EQ: band=low_mid, trigger=range_compliance, applied=+1.49 dB, resulting=-0.15 dB, cap_reached=False
- Stereo narrowing: 165.50s-167.00s, side scaled by 0.914 (correlation -0.050 -> 0.000)
- Whistle repair: 4666.0 Hz, confidence=1.00, prominence=+13.64 dB, window=0.25s-2.00s
- Whistle repair: 7484.0 Hz, confidence=1.00, prominence=+16.46 dB, window=0.25s-2.00s
- Whistle repair: 7816.0 Hz, confidence=1.00, prominence=+12.42 dB, window=0.25s-2.50s
- Whistle repair: 9600.0 Hz, confidence=1.00, prominence=+12.53 dB, window=0.25s-2.00s
- Whistle repair: 10784.0 Hz, confidence=1.00, prominence=+13.70 dB, window=0.25s-2.00s
- Whistle repair: 16200.0 Hz, confidence=1.00, prominence=+14.44 dB, window=0.25s-2.75s
- Whistle repair: 17184.0 Hz, confidence=1.00, prominence=+15.07 dB, window=0.25s-2.75s
- Whistle repair: 19116.0 Hz, confidence=1.00, prominence=+16.46 dB, window=0.25s-2.25s
- Whistle repair: 19484.0 Hz, confidence=1.00, prominence=+13.39 dB, window=0.25s-2.25s
- Whistle repair: 16816.0 Hz, confidence=1.00, prominence=+12.02 dB, window=0.50s-2.75s
- Whistle repair: 16416.0 Hz, confidence=1.00, prominence=+14.82 dB, window=0.75s-2.75s
- Whistle repair: 22400.0 Hz, confidence=1.00, prominence=+14.98 dB, window=0.75s-5.25s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+16.36 dB, window=1.25s-4.25s
- Whistle repair: 16550.0 Hz, confidence=1.00, prominence=+14.95 dB, window=1.25s-3.25s
- Whistle repair: 19900.0 Hz, confidence=1.00, prominence=+14.74 dB, window=1.25s-3.75s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+11.17 dB, window=2.25s-4.50s
- Whistle repair: 21600.0 Hz, confidence=1.00, prominence=+11.89 dB, window=3.25s-5.50s
- Whistle repair: 15050.0 Hz, confidence=1.00, prominence=+12.38 dB, window=4.00s-10.00s
- Whistle repair: 590.0 Hz, confidence=1.00, prominence=+31.11 dB, window=5.50s-7.25s
- Whistle repair: 15600.0 Hz, confidence=1.00, prominence=+13.90 dB, window=5.50s-8.25s
- Whistle repair: 10400.0 Hz, confidence=1.00, prominence=+14.76 dB, window=5.75s-8.50s
- Whistle repair: 7000.0 Hz, confidence=1.00, prominence=+12.81 dB, window=6.00s-9.75s
- Whistle repair: 15300.0 Hz, confidence=1.00, prominence=+13.54 dB, window=6.00s-9.75s
- Whistle repair: 19900.0 Hz, confidence=1.00, prominence=+15.15 dB, window=6.00s-9.75s
- Whistle repair: 20800.0 Hz, confidence=1.00, prominence=+13.69 dB, window=6.00s-8.00s
- Whistle repair: 6600.0 Hz, confidence=1.00, prominence=+14.39 dB, window=6.25s-8.50s
- Whistle repair: 21600.0 Hz, confidence=1.00, prominence=+13.54 dB, window=6.25s-10.25s
- Whistle repair: 22000.0 Hz, confidence=1.00, prominence=+14.38 dB, window=6.25s-8.50s
- Whistle repair: 16650.0 Hz, confidence=1.00, prominence=+11.70 dB, window=6.50s-9.50s
- Whistle repair: 13284.0 Hz, confidence=1.00, prominence=+13.08 dB, window=6.75s-9.00s
- Whistle repair: 22400.0 Hz, confidence=1.00, prominence=+14.95 dB, window=6.75s-10.00s
- Whistle repair: 8184.0 Hz, confidence=1.00, prominence=+11.37 dB, window=7.00s-8.75s
- Whistle repair: 13950.0 Hz, confidence=1.00, prominence=+13.57 dB, window=7.00s-9.75s
- Whistle repair: 17184.0 Hz, confidence=1.00, prominence=+14.72 dB, window=7.00s-8.75s
- Whistle repair: 17616.0 Hz, confidence=1.00, prominence=+11.01 dB, window=7.25s-9.00s
- Whistle repair: 3800.0 Hz, confidence=1.00, prominence=+13.94 dB, window=7.50s-9.75s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+13.80 dB, window=7.50s-9.50s
- Whistle repair: 4800.0 Hz, confidence=1.00, prominence=+14.58 dB, window=7.75s-9.75s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+13.02 dB, window=7.75s-10.00s
- Whistle repair: 14200.0 Hz, confidence=1.00, prominence=+13.66 dB, window=7.75s-9.75s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+12.54 dB, window=8.25s-10.50s
- Whistle repair: 166.0 Hz, confidence=1.00, prominence=+44.49 dB, window=8.50s-11.25s
- Whistle repair: 1182.0 Hz, confidence=1.00, prominence=+28.22 dB, window=12.50s-14.50s
- Whistle repair: 22000.0 Hz, confidence=1.00, prominence=+15.45 dB, window=13.00s-17.50s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+13.42 dB, window=13.75s-15.75s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+16.58 dB, window=13.75s-21.25s
- Whistle repair: 20800.0 Hz, confidence=1.00, prominence=+14.26 dB, window=14.00s-20.25s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+13.16 dB, window=14.50s-19.00s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+15.29 dB, window=14.75s-21.75s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+13.12 dB, window=14.75s-17.00s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+16.08 dB, window=15.00s-20.50s
- Whistle repair: 13400.0 Hz, confidence=1.00, prominence=+13.47 dB, window=15.75s-20.25s
- Whistle repair: 18400.0 Hz, confidence=1.00, prominence=+13.31 dB, window=16.00s-18.25s
- Whistle repair: 21600.0 Hz, confidence=1.00, prominence=+15.29 dB, window=16.00s-21.00s
- Whistle repair: 21800.0 Hz, confidence=1.00, prominence=+12.86 dB, window=16.25s-21.00s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+12.85 dB, window=16.50s-18.25s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+11.88 dB, window=16.75s-19.75s
- Whistle repair: 6400.0 Hz, confidence=1.00, prominence=+13.59 dB, window=17.25s-21.25s
- Whistle repair: 9400.0 Hz, confidence=1.00, prominence=+12.01 dB, window=17.50s-21.00s
- Whistle repair: 22800.0 Hz, confidence=1.00, prominence=+11.91 dB, window=18.25s-20.00s
- Whistle repair: 22000.0 Hz, confidence=1.00, prominence=+11.51 dB, window=18.50s-21.00s
- Whistle repair: 14400.0 Hz, confidence=1.00, prominence=+10.02 dB, window=19.25s-21.00s
- Whistle repair: 166.0 Hz, confidence=1.00, prominence=+28.19 dB, window=19.50s-21.25s
- Whistle repair: 21400.0 Hz, confidence=1.00, prominence=+11.68 dB, window=19.50s-21.25s
- Whistle repair: 3800.0 Hz, confidence=1.00, prominence=+15.94 dB, window=20.25s-22.25s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+14.33 dB, window=20.25s-22.00s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+11.57 dB, window=21.00s-23.25s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+14.53 dB, window=34.25s-47.75s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+13.54 dB, window=34.25s-37.00s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+10.00 dB, window=34.25s-36.00s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+10.79 dB, window=36.25s-38.50s
- Whistle repair: 5000.0 Hz, confidence=1.00, prominence=+10.56 dB, window=38.50s-40.25s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+14.24 dB, window=40.75s-48.25s
- Whistle repair: 19800.0 Hz, confidence=1.00, prominence=+13.01 dB, window=41.75s-74.75s
- Whistle repair: 3200.0 Hz, confidence=1.00, prominence=+13.90 dB, window=42.75s-45.00s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+14.38 dB, window=42.75s-47.25s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+13.35 dB, window=42.75s-62.00s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+10.99 dB, window=45.00s-49.50s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+11.88 dB, window=47.25s-49.25s
- Whistle repair: 15800.0 Hz, confidence=1.00, prominence=+11.71 dB, window=47.75s-49.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+16.68 dB, window=49.25s-54.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+14.93 dB, window=49.50s-54.50s
- Whistle repair: 19400.0 Hz, confidence=1.00, prominence=+11.42 dB, window=49.75s-53.75s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+11.83 dB, window=50.00s-52.25s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+12.90 dB, window=50.75s-53.50s
- Whistle repair: 19600.0 Hz, confidence=1.00, prominence=+11.41 dB, window=50.75s-53.25s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+12.39 dB, window=53.00s-54.75s
- Whistle repair: 8200.0 Hz, confidence=1.00, prominence=+15.19 dB, window=53.75s-56.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+12.04 dB, window=54.00s-56.50s
- Whistle repair: 3800.0 Hz, confidence=1.00, prominence=+18.41 dB, window=54.25s-56.50s
- Whistle repair: 8600.0 Hz, confidence=1.00, prominence=+10.98 dB, window=54.25s-56.00s
- Whistle repair: 9200.0 Hz, confidence=1.00, prominence=+10.85 dB, window=54.25s-56.25s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+11.39 dB, window=54.25s-56.25s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+16.41 dB, window=54.25s-56.50s
- Whistle repair: 9600.0 Hz, confidence=1.00, prominence=+13.15 dB, window=54.50s-56.50s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+13.67 dB, window=56.25s-58.25s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+17.12 dB, window=56.25s-61.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+15.96 dB, window=56.25s-60.25s
- Whistle repair: 3200.0 Hz, confidence=1.00, prominence=+13.54 dB, window=57.25s-59.75s
- Whistle repair: 8600.0 Hz, confidence=1.00, prominence=+11.03 dB, window=57.50s-59.75s
- Whistle repair: 17200.0 Hz, confidence=1.00, prominence=+10.27 dB, window=57.50s-59.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+13.81 dB, window=58.00s-60.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.41 dB, window=58.50s-60.25s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+12.31 dB, window=60.25s-63.00s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+12.52 dB, window=61.75s-64.25s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+14.81 dB, window=62.75s-75.00s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+17.22 dB, window=63.00s-69.50s
- Whistle repair: 8200.0 Hz, confidence=1.00, prominence=+13.25 dB, window=63.00s-65.50s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+13.16 dB, window=64.00s-68.75s
- Whistle repair: 3200.0 Hz, confidence=1.00, prominence=+12.69 dB, window=64.75s-67.50s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+12.95 dB, window=65.25s-69.00s
- Whistle repair: 15800.0 Hz, confidence=1.00, prominence=+11.62 dB, window=65.75s-69.25s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+11.41 dB, window=66.50s-70.75s
- Whistle repair: 9600.0 Hz, confidence=1.00, prominence=+15.87 dB, window=68.00s-69.75s
- Whistle repair: 8200.0 Hz, confidence=1.00, prominence=+14.31 dB, window=68.50s-70.75s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+15.26 dB, window=68.75s-71.00s
- Whistle repair: 15800.0 Hz, confidence=1.00, prominence=+10.66 dB, window=70.25s-72.25s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+11.92 dB, window=70.25s-72.00s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+16.16 dB, window=70.50s-79.75s
- Whistle repair: 3200.0 Hz, confidence=1.00, prominence=+13.44 dB, window=71.50s-73.25s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+13.47 dB, window=71.75s-74.25s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.85 dB, window=72.00s-76.00s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+11.48 dB, window=72.50s-74.50s
- Whistle repair: 15800.0 Hz, confidence=1.00, prominence=+12.81 dB, window=73.50s-76.50s
- Whistle repair: 8200.0 Hz, confidence=1.00, prominence=+14.05 dB, window=75.50s-81.50s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+14.81 dB, window=76.00s-77.75s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+13.23 dB, window=76.75s-78.75s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+13.34 dB, window=77.25s-79.75s
- Whistle repair: 8800.0 Hz, confidence=1.00, prominence=+12.21 dB, window=78.25s-80.00s
- Whistle repair: 10800.0 Hz, confidence=1.00, prominence=+15.37 dB, window=78.25s-80.50s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+13.27 dB, window=79.25s-81.50s
- Whistle repair: 14950.0 Hz, confidence=1.00, prominence=+13.03 dB, window=79.25s-81.25s
- Whistle repair: 18100.0 Hz, confidence=1.00, prominence=+10.19 dB, window=79.25s-81.25s
- Whistle repair: 5200.0 Hz, confidence=1.00, prominence=+12.96 dB, window=79.50s-81.25s
- Whistle repair: 11200.0 Hz, confidence=1.00, prominence=+11.57 dB, window=79.50s-81.25s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+17.94 dB, window=79.50s-81.75s
- Whistle repair: 19950.0 Hz, confidence=1.00, prominence=+14.07 dB, window=79.50s-82.00s
- Whistle repair: 3000.0 Hz, confidence=1.00, prominence=+15.31 dB, window=79.75s-81.75s
- Whistle repair: 9200.0 Hz, confidence=1.00, prominence=+16.51 dB, window=79.75s-81.50s
- Whistle repair: 14200.0 Hz, confidence=1.00, prominence=+15.31 dB, window=79.75s-81.75s
- Whistle repair: 14400.0 Hz, confidence=1.00, prominence=+12.97 dB, window=79.75s-81.50s
- Whistle repair: 15400.0 Hz, confidence=1.00, prominence=+11.47 dB, window=79.75s-82.00s
- Whistle repair: 12200.0 Hz, confidence=1.00, prominence=+11.04 dB, window=81.50s-83.25s
- Whistle repair: 16200.0 Hz, confidence=1.00, prominence=+12.08 dB, window=81.50s-83.50s
- Whistle repair: 22000.0 Hz, confidence=1.00, prominence=+14.50 dB, window=82.25s-84.75s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+14.97 dB, window=82.75s-86.50s
- Whistle repair: 196.0 Hz, confidence=1.00, prominence=+31.65 dB, window=83.00s-85.00s
- Whistle repair: 13400.0 Hz, confidence=1.00, prominence=+12.91 dB, window=83.25s-85.25s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+11.99 dB, window=83.50s-85.25s
- Whistle repair: 18600.0 Hz, confidence=1.00, prominence=+13.99 dB, window=84.00s-85.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+11.56 dB, window=85.00s-96.00s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+15.47 dB, window=87.50s-89.25s
- Whistle repair: 246.0 Hz, confidence=1.00, prominence=+28.40 dB, window=87.75s-89.75s
- Whistle repair: 330.0 Hz, confidence=1.00, prominence=+28.03 dB, window=87.75s-89.75s
- Whistle repair: 10400.0 Hz, confidence=1.00, prominence=+13.50 dB, window=88.50s-90.25s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+13.49 dB, window=92.00s-93.75s
- Whistle repair: 13600.0 Hz, confidence=1.00, prominence=+12.89 dB, window=92.75s-95.25s
- Whistle repair: 18600.0 Hz, confidence=1.00, prominence=+14.58 dB, window=93.00s-95.00s
- Whistle repair: 19900.0 Hz, confidence=1.00, prominence=+13.14 dB, window=93.00s-94.75s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+14.40 dB, window=93.75s-96.75s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+12.14 dB, window=93.75s-95.75s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+16.68 dB, window=93.75s-95.75s
- Whistle repair: 11800.0 Hz, confidence=1.00, prominence=+14.11 dB, window=94.00s-95.75s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+13.61 dB, window=94.00s-95.75s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+13.28 dB, window=94.00s-96.00s
- Whistle repair: 4600.0 Hz, confidence=1.00, prominence=+14.27 dB, window=94.25s-96.25s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+13.87 dB, window=94.75s-96.75s
- Whistle repair: 15600.0 Hz, confidence=1.00, prominence=+14.63 dB, window=95.50s-97.25s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+12.30 dB, window=97.25s-100.00s
- Whistle repair: 14400.0 Hz, confidence=1.00, prominence=+11.56 dB, window=97.25s-99.50s
- Whistle repair: 3800.0 Hz, confidence=1.00, prominence=+14.61 dB, window=97.75s-99.50s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+11.98 dB, window=97.75s-100.00s
- Whistle repair: 17200.0 Hz, confidence=1.00, prominence=+11.74 dB, window=97.75s-99.50s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+11.17 dB, window=98.25s-100.00s
- Whistle repair: 6600.0 Hz, confidence=1.00, prominence=+10.78 dB, window=101.00s-103.00s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+11.41 dB, window=101.00s-102.75s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+16.10 dB, window=101.00s-103.00s
- Whistle repair: 6400.0 Hz, confidence=1.00, prominence=+12.86 dB, window=102.75s-104.50s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+11.49 dB, window=103.50s-108.25s
- Whistle repair: 522.0 Hz, confidence=1.00, prominence=+28.37 dB, window=104.50s-106.25s
- Whistle repair: 3000.0 Hz, confidence=1.00, prominence=+14.42 dB, window=104.50s-106.25s
- Whistle repair: 3800.0 Hz, confidence=1.00, prominence=+17.75 dB, window=104.50s-106.25s
- Whistle repair: 11200.0 Hz, confidence=1.00, prominence=+12.17 dB, window=104.50s-106.25s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+13.43 dB, window=104.50s-106.75s
- Whistle repair: 18782.0 Hz, confidence=1.00, prominence=+11.17 dB, window=104.75s-106.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+11.76 dB, window=108.50s-110.75s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+10.89 dB, window=108.50s-114.25s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+11.13 dB, window=110.25s-112.75s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+12.00 dB, window=113.25s-115.00s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+13.67 dB, window=113.75s-121.75s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+13.57 dB, window=115.25s-117.00s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+10.37 dB, window=115.75s-118.25s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+13.18 dB, window=119.75s-122.25s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+12.59 dB, window=121.75s-124.25s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+13.89 dB, window=122.00s-125.50s
- Whistle repair: 16600.0 Hz, confidence=1.00, prominence=+10.05 dB, window=122.00s-123.75s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+10.33 dB, window=122.50s-124.75s
- Whistle repair: 7400.0 Hz, confidence=1.00, prominence=+14.10 dB, window=122.75s-124.50s
- Whistle repair: 4000.0 Hz, confidence=1.00, prominence=+13.89 dB, window=123.00s-125.25s
- Whistle repair: 4000.0 Hz, confidence=1.00, prominence=+10.36 dB, window=125.75s-127.50s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+13.78 dB, window=126.00s-132.00s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+10.42 dB, window=127.25s-131.75s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+12.93 dB, window=127.50s-129.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+13.35 dB, window=127.75s-132.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.39 dB, window=129.25s-131.50s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+12.02 dB, window=129.50s-131.25s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+13.73 dB, window=129.75s-133.50s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+10.83 dB, window=130.75s-133.50s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+13.26 dB, window=132.75s-137.00s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+10.20 dB, window=138.00s-139.75s
- Whistle repair: 8600.0 Hz, confidence=1.00, prominence=+10.16 dB, window=138.50s-140.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+10.29 dB, window=139.00s-140.75s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+14.82 dB, window=141.75s-144.00s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+10.93 dB, window=142.00s-143.75s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+14.71 dB, window=143.50s-145.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+11.41 dB, window=144.00s-146.00s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+12.35 dB, window=144.00s-146.00s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+11.73 dB, window=144.00s-147.75s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.85 dB, window=146.25s-148.00s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+10.59 dB, window=146.50s-151.00s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+14.07 dB, window=147.50s-149.25s
- Whistle repair: 6600.0 Hz, confidence=1.00, prominence=+15.09 dB, window=148.50s-150.25s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+12.05 dB, window=148.75s-150.50s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+15.24 dB, window=149.00s-150.75s
- Whistle repair: 5800.0 Hz, confidence=1.00, prominence=+14.16 dB, window=149.25s-151.00s
- Whistle repair: 290.0 Hz, confidence=1.00, prominence=+22.44 dB, window=149.50s-151.25s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+12.05 dB, window=150.25s-154.25s
- Whistle repair: 14000.0 Hz, confidence=1.00, prominence=+15.92 dB, window=150.75s-156.25s
- Whistle repair: 19950.0 Hz, confidence=1.00, prominence=+17.13 dB, window=150.75s-152.50s
- Whistle repair: 14200.0 Hz, confidence=1.00, prominence=+17.04 dB, window=151.00s-156.50s
- Whistle repair: 14400.0 Hz, confidence=1.00, prominence=+19.69 dB, window=151.00s-154.00s
- Whistle repair: 14900.0 Hz, confidence=1.00, prominence=+12.12 dB, window=151.00s-152.75s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+19.02 dB, window=151.00s-156.25s
- Whistle repair: 4000.0 Hz, confidence=1.00, prominence=+16.81 dB, window=151.25s-154.50s
- Whistle repair: 7000.0 Hz, confidence=1.00, prominence=+16.19 dB, window=151.25s-157.00s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+14.01 dB, window=151.25s-153.50s
- Whistle repair: 8800.0 Hz, confidence=1.00, prominence=+17.40 dB, window=151.25s-153.75s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+12.47 dB, window=151.25s-155.25s
- Whistle repair: 15600.0 Hz, confidence=1.00, prominence=+16.99 dB, window=151.25s-153.00s
- Whistle repair: 10200.0 Hz, confidence=1.00, prominence=+14.42 dB, window=151.50s-155.25s
- Whistle repair: 4400.0 Hz, confidence=1.00, prominence=+14.60 dB, window=151.75s-154.00s
- Whistle repair: 6600.0 Hz, confidence=1.00, prominence=+12.57 dB, window=151.75s-153.75s
- Whistle repair: 21400.0 Hz, confidence=1.00, prominence=+13.59 dB, window=151.75s-155.50s
- Whistle repair: 5400.0 Hz, confidence=1.00, prominence=+11.95 dB, window=152.00s-153.75s
- Whistle repair: 8200.0 Hz, confidence=1.00, prominence=+12.43 dB, window=152.00s-154.25s
- Whistle repair: 15800.0 Hz, confidence=1.00, prominence=+16.96 dB, window=152.00s-155.00s
- Whistle repair: 20800.0 Hz, confidence=1.00, prominence=+16.47 dB, window=152.00s-156.75s
- Whistle repair: 9200.0 Hz, confidence=1.00, prominence=+13.96 dB, window=152.25s-156.25s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+17.35 dB, window=152.25s-156.50s
- Whistle repair: 17800.0 Hz, confidence=1.00, prominence=+12.55 dB, window=152.25s-157.25s
- Whistle repair: 21600.0 Hz, confidence=1.00, prominence=+17.84 dB, window=152.25s-161.00s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+13.35 dB, window=152.25s-155.00s
- Whistle repair: 22400.0 Hz, confidence=1.00, prominence=+16.93 dB, window=152.25s-161.00s
- Whistle repair: 6400.0 Hz, confidence=1.00, prominence=+12.38 dB, window=152.50s-154.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+13.02 dB, window=152.50s-154.25s
- Whistle repair: 22600.0 Hz, confidence=1.00, prominence=+11.27 dB, window=152.50s-154.25s
- Whistle repair: 23000.0 Hz, confidence=1.00, prominence=+11.52 dB, window=152.50s-154.25s
- Whistle repair: 23200.0 Hz, confidence=1.00, prominence=+13.14 dB, window=152.50s-160.00s
- Whistle repair: 16400.0 Hz, confidence=1.00, prominence=+17.64 dB, window=152.75s-157.25s
- Whistle repair: 19800.0 Hz, confidence=1.00, prominence=+11.17 dB, window=152.75s-156.75s
- Whistle repair: 22000.0 Hz, confidence=1.00, prominence=+12.56 dB, window=152.75s-161.25s
- Whistle repair: 18100.0 Hz, confidence=1.00, prominence=+10.72 dB, window=153.25s-155.00s
- Whistle repair: 19600.0 Hz, confidence=1.00, prominence=+15.48 dB, window=153.25s-156.50s
- Whistle repair: 19000.0 Hz, confidence=1.00, prominence=+15.04 dB, window=153.50s-158.25s
- Whistle repair: 20600.0 Hz, confidence=1.00, prominence=+13.58 dB, window=153.50s-155.25s
- Whistle repair: 13400.0 Hz, confidence=1.00, prominence=+12.68 dB, window=153.75s-155.75s
- Whistle repair: 18600.0 Hz, confidence=1.00, prominence=+11.58 dB, window=154.00s-156.00s
- Whistle repair: 15300.0 Hz, confidence=1.00, prominence=+13.03 dB, window=154.25s-156.50s
- Whistle repair: 196.0 Hz, confidence=1.00, prominence=+37.07 dB, window=154.50s-158.50s
- Whistle repair: 4330.0 Hz, confidence=1.00, prominence=+16.99 dB, window=154.50s-156.25s
- Whistle repair: 5600.0 Hz, confidence=1.00, prominence=+16.26 dB, window=154.50s-156.25s
- Whistle repair: 130.0 Hz, confidence=0.95, prominence=+44.75 dB, window=154.75s-156.50s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+11.84 dB, window=154.75s-158.00s
- Whistle repair: 988.0 Hz, confidence=1.00, prominence=+31.18 dB, window=156.00s-158.25s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+11.66 dB, window=156.00s-157.75s
- Whistle repair: 494.0 Hz, confidence=1.00, prominence=+28.84 dB, window=156.50s-158.75s
- Whistle repair: 21400.0 Hz, confidence=1.00, prominence=+15.07 dB, window=157.50s-161.00s
- Whistle repair: 15670.0 Hz, confidence=1.00, prominence=+16.73 dB, window=158.00s-159.75s
- Whistle repair: 21800.0 Hz, confidence=1.00, prominence=+11.24 dB, window=158.00s-159.75s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+14.34 dB, window=159.25s-161.00s
- Whistle repair: 130.0 Hz, confidence=1.00, prominence=+42.63 dB, window=161.50s-163.50s
- Whistle repair: 196.0 Hz, confidence=1.00, prominence=+42.69 dB, window=161.50s-163.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+10.43 dB, window=162.25s-164.25s
- Whistle repair: 3000.0 Hz, confidence=1.00, prominence=+16.22 dB, window=165.50s-167.75s
- Whistle repair: 22200.0 Hz, confidence=1.00, prominence=+11.11 dB, window=166.00s-168.00s
- Whistle repair: 21600.0 Hz, confidence=1.00, prominence=+10.97 dB, window=166.75s-168.50s
- Whistle repair: 3000.0 Hz, confidence=1.00, prominence=+22.46 dB, window=168.75s-170.75s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+13.35 dB, window=171.25s-175.75s
- Whistle repair: 824.0 Hz, confidence=1.00, prominence=+31.70 dB, window=172.25s-174.00s
- Whistle repair: 6600.0 Hz, confidence=1.00, prominence=+12.67 dB, window=172.50s-175.75s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+14.79 dB, window=173.00s-175.50s
- Whistle repair: 7600.0 Hz, confidence=1.00, prominence=+12.79 dB, window=173.25s-175.50s
- Whistle repair: 4800.0 Hz, confidence=1.00, prominence=+15.06 dB, window=173.75s-175.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+14.68 dB, window=173.75s-175.50s
- Whistle repair: 6400.0 Hz, confidence=1.00, prominence=+14.75 dB, window=174.00s-176.50s
- Whistle repair: 9000.0 Hz, confidence=1.00, prominence=+13.26 dB, window=174.00s-176.25s
- Whistle repair: 11200.0 Hz, confidence=1.00, prominence=+13.55 dB, window=174.25s-179.25s
- Whistle repair: 14400.0 Hz, confidence=1.00, prominence=+14.16 dB, window=174.25s-179.50s
- Whistle repair: 19800.0 Hz, confidence=1.00, prominence=+16.43 dB, window=174.25s-177.75s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+15.90 dB, window=174.50s-179.50s
- Whistle repair: 9600.0 Hz, confidence=1.00, prominence=+16.30 dB, window=175.00s-179.00s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+16.38 dB, window=175.50s-177.75s
- Whistle repair: 18600.0 Hz, confidence=1.00, prominence=+14.18 dB, window=175.50s-177.75s
- Whistle repair: 262.0 Hz, confidence=1.00, prominence=+29.09 dB, window=175.75s-177.75s
- Whistle repair: 3000.0 Hz, confidence=1.00, prominence=+26.81 dB, window=175.75s-178.00s
- Whistle repair: 3800.0 Hz, confidence=1.00, prominence=+21.71 dB, window=175.75s-177.75s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+15.56 dB, window=175.75s-178.75s
- Whistle repair: 15000.0 Hz, confidence=1.00, prominence=+15.37 dB, window=175.75s-177.75s
- Whistle repair: 15400.0 Hz, confidence=1.00, prominence=+13.56 dB, window=175.75s-177.50s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+12.59 dB, window=175.75s-178.00s
- Whistle repair: 190.0 Hz, confidence=1.00, prominence=+18.56 dB, window=176.00s-177.75s
- Whistle repair: 13000.0 Hz, confidence=1.00, prominence=+13.50 dB, window=176.50s-178.50s
- Whistle repair: 9400.0 Hz, confidence=1.00, prominence=+13.14 dB, window=177.00s-178.75s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+14.26 dB, window=178.25s-180.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+14.42 dB, window=178.50s-181.00s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+14.41 dB, window=179.00s-182.75s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+11.82 dB, window=179.00s-194.25s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+12.27 dB, window=179.25s-181.25s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+12.93 dB, window=179.50s-194.50s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+11.16 dB, window=181.00s-184.75s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+12.00 dB, window=182.50s-185.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+10.46 dB, window=183.00s-191.25s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+12.52 dB, window=185.00s-190.25s
- Whistle repair: 17900.0 Hz, confidence=1.00, prominence=+11.86 dB, window=185.50s-187.50s
- Whistle repair: 20050.0 Hz, confidence=1.00, prominence=+10.72 dB, window=185.75s-187.50s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+12.08 dB, window=190.50s-193.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+12.28 dB, window=191.25s-193.25s
- Whistle repair: 10800.0 Hz, confidence=1.00, prominence=+12.67 dB, window=191.75s-193.50s
- Whistle repair: 20150.0 Hz, confidence=1.00, prominence=+12.19 dB, window=191.75s-195.00s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+12.41 dB, window=192.00s-196.25s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+15.12 dB, window=192.50s-194.25s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+12.30 dB, window=192.50s-195.00s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+11.78 dB, window=192.75s-195.25s
- Whistle repair: 17900.0 Hz, confidence=1.00, prominence=+11.77 dB, window=192.75s-196.25s
- Whistle repair: 18300.0 Hz, confidence=1.00, prominence=+11.23 dB, window=193.25s-195.00s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.06 dB, window=194.00s-197.75s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+13.06 dB, window=195.00s-196.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+14.04 dB, window=195.25s-197.00s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+12.28 dB, window=195.50s-197.25s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+10.96 dB, window=196.50s-199.25s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+12.48 dB, window=196.75s-199.00s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+10.93 dB, window=196.75s-198.50s
- Whistle repair: 18300.0 Hz, confidence=1.00, prominence=+11.61 dB, window=198.25s-200.75s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+11.87 dB, window=198.75s-201.50s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+12.15 dB, window=198.75s-203.75s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+13.43 dB, window=198.75s-204.25s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+11.48 dB, window=199.75s-203.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.72 dB, window=201.25s-206.25s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+13.68 dB, window=201.50s-203.25s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+12.47 dB, window=201.75s-209.25s
- Whistle repair: 17600.0 Hz, confidence=1.00, prominence=+10.08 dB, window=201.75s-203.50s
- Whistle repair: 408.0 Hz, confidence=1.00, prominence=+22.59 dB, window=202.00s-203.75s
- Whistle repair: 18100.0 Hz, confidence=1.00, prominence=+11.79 dB, window=204.00s-206.00s
- Whistle repair: 14150.0 Hz, confidence=1.00, prominence=+12.18 dB, window=204.75s-206.50s
- Whistle repair: 10320.0 Hz, confidence=1.00, prominence=+13.20 dB, window=205.75s-207.50s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+11.50 dB, window=206.50s-211.25s
- Whistle repair: 246.0 Hz, confidence=1.00, prominence=+25.37 dB, window=207.50s-209.25s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+12.87 dB, window=208.00s-211.25s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+12.70 dB, window=208.25s-214.00s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+13.40 dB, window=208.50s-211.75s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+10.86 dB, window=211.50s-214.50s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+14.13 dB, window=212.75s-216.00s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+12.94 dB, window=212.75s-218.00s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+13.35 dB, window=212.75s-214.50s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+11.33 dB, window=212.75s-214.50s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+10.42 dB, window=215.00s-216.75s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.02 dB, window=217.25s-220.00s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+11.43 dB, window=217.50s-219.25s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+15.02 dB, window=218.25s-220.75s
- Whistle repair: 16600.0 Hz, confidence=1.00, prominence=+12.36 dB, window=218.50s-222.00s
- Whistle repair: 15800.0 Hz, confidence=1.00, prominence=+14.15 dB, window=219.75s-222.00s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+12.96 dB, window=220.50s-223.75s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+13.33 dB, window=221.25s-224.25s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+10.81 dB, window=221.50s-225.25s
- Whistle repair: 13950.0 Hz, confidence=1.00, prominence=+12.81 dB, window=221.50s-223.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+11.71 dB, window=221.50s-236.00s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+12.82 dB, window=221.50s-225.00s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+13.29 dB, window=223.00s-225.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+12.43 dB, window=223.25s-225.50s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+10.39 dB, window=224.75s-226.50s
- Whistle repair: 18100.0 Hz, confidence=1.00, prominence=+12.80 dB, window=224.75s-227.00s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+13.43 dB, window=225.00s-227.25s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+14.31 dB, window=225.00s-227.00s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+13.12 dB, window=225.00s-226.75s
- Whistle repair: 7000.0 Hz, confidence=1.00, prominence=+11.40 dB, window=225.50s-227.25s
- Whistle repair: 16600.0 Hz, confidence=1.00, prominence=+10.72 dB, window=225.75s-228.50s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+12.52 dB, window=226.75s-232.50s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+15.77 dB, window=226.75s-228.75s
- Whistle repair: 16800.0 Hz, confidence=1.00, prominence=+11.22 dB, window=226.75s-231.50s
- Whistle repair: 17900.0 Hz, confidence=1.00, prominence=+10.84 dB, window=226.75s-228.75s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+13.28 dB, window=227.00s-231.50s
- Whistle repair: 19200.0 Hz, confidence=1.00, prominence=+12.63 dB, window=228.75s-230.50s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+12.93 dB, window=229.00s-230.75s
- Whistle repair: 18800.0 Hz, confidence=1.00, prominence=+12.97 dB, window=229.25s-232.00s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+12.13 dB, window=229.50s-232.00s
- Whistle repair: 20050.0 Hz, confidence=1.00, prominence=+11.27 dB, window=229.75s-232.00s
- Whistle repair: 16600.0 Hz, confidence=1.00, prominence=+12.55 dB, window=231.25s-236.25s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+12.89 dB, window=232.00s-234.25s
- Whistle repair: 10600.0 Hz, confidence=1.00, prominence=+12.69 dB, window=232.25s-234.00s
- Whistle repair: 12400.0 Hz, confidence=1.00, prominence=+14.35 dB, window=232.50s-238.50s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+10.25 dB, window=232.50s-234.25s
- Whistle repair: 13600.0 Hz, confidence=1.00, prominence=+11.63 dB, window=233.00s-235.00s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+14.91 dB, window=233.75s-240.00s
- Whistle repair: 1600.0 Hz, confidence=1.00, prominence=+10.83 dB, window=234.00s-235.75s
- Whistle repair: 7600.0 Hz, confidence=1.00, prominence=+12.84 dB, window=234.00s-236.00s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+14.37 dB, window=235.00s-238.00s
- Whistle repair: 12800.0 Hz, confidence=1.00, prominence=+10.85 dB, window=235.00s-237.00s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+14.25 dB, window=235.25s-238.00s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+12.88 dB, window=235.75s-241.25s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+11.59 dB, window=236.00s-238.00s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+11.62 dB, window=236.50s-240.00s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+14.64 dB, window=237.00s-243.00s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+12.26 dB, window=237.00s-243.50s
- Whistle repair: 5000.0 Hz, confidence=1.00, prominence=+12.02 dB, window=237.50s-239.25s
- Whistle repair: 7000.0 Hz, confidence=1.00, prominence=+11.29 dB, window=238.25s-241.25s
- Whistle repair: 3200.0 Hz, confidence=1.00, prominence=+10.79 dB, window=239.25s-241.00s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+11.82 dB, window=240.50s-242.50s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+11.14 dB, window=241.25s-243.00s
- Whistle repair: 18418.0 Hz, confidence=1.00, prominence=+11.71 dB, window=241.25s-243.00s
- Whistle repair: 7000.0 Hz, confidence=1.00, prominence=+12.52 dB, window=243.50s-246.25s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+11.44 dB, window=243.50s-245.25s
- Whistle repair: 6800.0 Hz, confidence=1.00, prominence=+12.27 dB, window=244.25s-246.75s
- Whistle repair: 10000.0 Hz, confidence=1.00, prominence=+13.03 dB, window=244.50s-248.00s
- Whistle repair: 16000.0 Hz, confidence=1.00, prominence=+11.43 dB, window=244.50s-247.50s
- Whistle repair: 8000.0 Hz, confidence=1.00, prominence=+13.55 dB, window=244.75s-253.00s
- Whistle repair: 6000.0 Hz, confidence=1.00, prominence=+13.33 dB, window=245.75s-248.50s
- Whistle repair: 7800.0 Hz, confidence=1.00, prominence=+11.85 dB, window=245.75s-248.50s
- Whistle repair: 14800.0 Hz, confidence=1.00, prominence=+10.10 dB, window=245.75s-248.50s
- Whistle repair: 20000.0 Hz, confidence=1.00, prominence=+11.26 dB, window=245.75s-250.50s
- Whistle repair: 16600.0 Hz, confidence=1.00, prominence=+12.07 dB, window=246.00s-249.75s
- Whistle repair: 6400.0 Hz, confidence=1.00, prominence=+12.17 dB, window=249.50s-252.25s
- Whistle repair: 13250.0 Hz, confidence=1.00, prominence=+14.20 dB, window=249.50s-253.25s
- Whistle repair: 15000.0 Hz, confidence=1.00, prominence=+10.29 dB, window=249.50s-251.25s
- Whistle repair: 9600.0 Hz, confidence=1.00, prominence=+14.36 dB, window=249.75s-253.25s
- Whistle repair: 15400.0 Hz, confidence=1.00, prominence=+11.73 dB, window=249.75s-252.25s
- Whistle repair: 8550.0 Hz, confidence=1.00, prominence=+11.97 dB, window=250.25s-252.00s
- Whistle repair: 17550.0 Hz, confidence=1.00, prominence=+16.90 dB, window=250.25s-252.25s
- Whistle repair: 12200.0 Hz, confidence=1.00, prominence=+12.37 dB, window=251.00s-253.00s
- Whistle repair: 21800.0 Hz, confidence=1.00, prominence=+10.99 dB, window=251.00s-253.00s
- Whistle repair summary: notched frequencies=[4666.0, 7484.0, 7816.0, 9600.0, 10784.0, 16200.0, 17184.0, 19116.0, 19484.0, 16816.0, 16416.0, 22400.0, 6800.0, 16550.0, 19900.0, 22200.0, 21600.0, 15050.0, 590.0, 15600.0, 10400.0, 7000.0, 15300.0, 19900.0, 20800.0, 6600.0, 21600.0, 22000.0, 16650.0, 13284.0, 22400.0, 8184.0, 13950.0, 17184.0, 17616.0, 3800.0, 10600.0, 4800.0, 6800.0, 14200.0, 22200.0, 166.0, 1182.0, 22000.0, 19200.0, 20000.0, 20800.0, 22200.0, 6800.0, 14800.0, 10600.0, 13400.0, 18400.0, 21600.0, 21800.0, 16000.0, 8000.0, 6400.0, 9400.0, 22800.0, 22000.0, 14400.0, 166.0, 21400.0, 3800.0, 16800.0, 8000.0, 8000.0, 10000.0, 14800.0, 16800.0, 5000.0, 19200.0, 19800.0, 3200.0, 6800.0, 16800.0, 14800.0, 10000.0, 15800.0, 6800.0, 19200.0, 19400.0, 18800.0, 10000.0, 19600.0, 8000.0, 8200.0, 14800.0, 3800.0, 8600.0, 9200.0, 10000.0, 10600.0, 9600.0, 7800.0, 8000.0, 19200.0, 3200.0, 8600.0, 17200.0, 6800.0, 14800.0, 10000.0, 10600.0, 16800.0, 8000.0, 8200.0, 7800.0, 3200.0, 19200.0, 15800.0, 10000.0, 9600.0, 8200.0, 10600.0, 15800.0, 20000.0, 8000.0, 3200.0, 19200.0, 14800.0, 18800.0, 15800.0, 8200.0, 10600.0, 7800.0, 16800.0, 8800.0, 10800.0, 12800.0, 14950.0, 18100.0, 5200.0, 11200.0, 16000.0, 19950.0, 3000.0, 9200.0, 14200.0, 14400.0, 15400.0, 12200.0, 16200.0, 22000.0, 12800.0, 196.0, 13400.0, 22200.0, 18600.0, 19200.0, 12800.0, 246.0, 330.0, 10400.0, 12800.0, 13600.0, 18600.0, 19900.0, 6800.0, 12400.0, 16000.0, 11800.0, 16800.0, 18800.0, 4600.0, 8000.0, 15600.0, 12800.0, 14400.0, 3800.0, 12400.0, 17200.0, 19200.0, 6600.0, 6800.0, 8000.0, 6400.0, 12400.0, 522.0, 3000.0, 3800.0, 11200.0, 16000.0, 18782.0, 6800.0, 16000.0, 19200.0, 8000.0, 19200.0, 6800.0, 16000.0, 8000.0, 16000.0, 12400.0, 16600.0, 14800.0, 7400.0, 4000.0, 4000.0, 8000.0, 12400.0, 7800.0, 19200.0, 14800.0, 16800.0, 6800.0, 16000.0, 8000.0, 12800.0, 8600.0, 14800.0, 7800.0, 6000.0, 8000.0, 6800.0, 16800.0, 19200.0, 14800.0, 12400.0, 10600.0, 6600.0, 7800.0, 8000.0, 5800.0, 290.0, 12800.0, 14000.0, 19950.0, 14200.0, 14400.0, 14900.0, 16000.0, 4000.0, 7000.0, 7800.0, 8800.0, 10000.0, 15600.0, 10200.0, 4400.0, 6600.0, 21400.0, 5400.0, 8200.0, 15800.0, 20800.0, 9200.0, 10600.0, 17800.0, 21600.0, 22200.0, 22400.0, 6400.0, 6800.0, 22600.0, 23000.0, 23200.0, 16400.0, 19800.0, 22000.0, 18100.0, 19600.0, 19000.0, 20600.0, 13400.0, 18600.0, 15300.0, 196.0, 4330.0, 5600.0, 130.0, 20000.0, 988.0, 22200.0, 494.0, 21400.0, 15670.0, 21800.0, 20000.0, 130.0, 196.0, 19200.0, 3000.0, 22200.0, 21600.0, 3000.0, 12400.0, 824.0, 6600.0, 8000.0, 7600.0, 4800.0, 6800.0, 6400.0, 9000.0, 11200.0, 14400.0, 19800.0, 12800.0, 9600.0, 10600.0, 18600.0, 262.0, 3000.0, 3800.0, 14800.0, 15000.0, 15400.0, 19200.0, 190.0, 13000.0, 9400.0, 12400.0, 6800.0, 16000.0, 16800.0, 20000.0, 19200.0, 12400.0, 14800.0, 6800.0, 16000.0, 17900.0, 20050.0, 7800.0, 14800.0, 10800.0, 20150.0, 20000.0, 12400.0, 18800.0, 16000.0, 17900.0, 18300.0, 14800.0, 16800.0, 19200.0, 6800.0, 12400.0, 10000.0, 18800.0, 18300.0, 7800.0, 16800.0, 19200.0, 6000.0, 14800.0, 6800.0, 12400.0, 17600.0, 408.0, 18100.0, 14150.0, 10320.0, 6000.0, 246.0, 19200.0, 14800.0, 16800.0, 12400.0, 7800.0, 16800.0, 19200.0, 20000.0, 12400.0, 14800.0, 10000.0, 12800.0, 16600.0, 15800.0, 12400.0, 20000.0, 6000.0, 13950.0, 14800.0, 18800.0, 8000.0, 6800.0, 12800.0, 18100.0, 10000.0, 10600.0, 12400.0, 7000.0, 16600.0, 6800.0, 16000.0, 16800.0, 17900.0, 7800.0, 19200.0, 8000.0, 18800.0, 6000.0, 20050.0, 16600.0, 10000.0, 10600.0, 12400.0, 20000.0, 13600.0, 8000.0, 1600.0, 7600.0, 10000.0, 12800.0, 7800.0, 16000.0, 6000.0, 20000.0, 6800.0, 14800.0, 5000.0, 7000.0, 3200.0, 7800.0, 10000.0, 18418.0, 7000.0, 20000.0, 6800.0, 10000.0, 16000.0, 8000.0, 6000.0, 7800.0, 14800.0, 20000.0, 16600.0, 6400.0, 13250.0, 15000.0, 9600.0, 15400.0, 8550.0, 17550.0, 12200.0, 21800.0], stage_ran=True
- Stem transient restoration [mix]: attack_boost, gain=+0.61 dB (requested +0.61 dB), onset peak 0.0631 -> 0.0677, severity=2.181 (transient attack restoration: gain 0.61 dB on local onset energy)
- Final bus glue [mix]: dynamic_balance, gain=-0.20 dB, peak 0.6202 -> 0.6061 (Dynamic balance trimmed a slightly over-energetic bus to preserve contour and keep the mix from feeling loose or unstable.)
- Loudness/limiting: target -13.55 LUFS, achieved -13.55 LUFS, true peak -1.00 dBTP, DR11 (source DR9, floor DR8), gain applied 3.04 dB over 7 solver iteration(s).

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