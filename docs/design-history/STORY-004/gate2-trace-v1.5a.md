# Gate 2 Trace Dump — v1.5a

Date: 2026-08-08
Implementation: hf_extension.py v1.5a (_gate_scan / _floor_onset_index / freeze_index = i_max)

All five tracks: 48 kHz, stereo (confirmed via sf.info — relevant because band 90 at 20475.06 Hz
is well inside the 24000 Hz Nyquist, ruling out a near-Nyquist grid artifact).

---

## Track: Black_Flute_Remastered.wav

sr=48000, duration=226.3s

hf_band_limit_hz: 15788.43024400365
stable: True
confidence: 1.0
insufficient_duration: False
suspected_transcode: True (band 15500–16500 Hz)
per_segment_hf_band_limit_hz: [15788.43, 15788.43, 15788.43, 15788.43, 15788.43]

### Whole-track PSD

freeze_index: 75
passband_level: -74.2133 dB
j_star: 81
centers[j*]: 15788.43 Hz
L = passband_level - 8.0 = -82.2133 dB
margin at j* = L - suffix_max[j*] = -82.2133 - (-82.6015) = 0.39 dB

suffix_max window (bands 76..86):
  band 76: centers=13665.46 Hz, suffix_max=-75.8172 dB
  band 77: centers=14065.89 Hz, suffix_max=-76.9350 dB
  band 78: centers=14478.05 Hz, suffix_max=-78.7195 dB
  band 79: centers=14902.29 Hz, suffix_max=-79.9185 dB
  band 80: centers=15338.96 Hz, suffix_max=-80.8081 dB
  band 81: centers=15788.43 Hz, suffix_max=-82.6015 dB   <-- j*  (margin 0.39 dB below L)
  band 82: centers=16251.07 Hz, suffix_max=-82.6015 dB
  band 83: centers=16727.26 Hz, suffix_max=-82.6015 dB
  band 84: centers=17217.41 Hz, suffix_max=-82.6015 dB
  band 85: centers=17721.91 Hz, suffix_max=-82.6015 dB
  band 86: centers=18241.21 Hz, suffix_max=-84.6711 dB

### Per-segment traces

All five segments: freeze_index=75, j_star=81, centers[j*]=15788.43 Hz.
Per-segment L vs suffix_max[81] margins (minimum margin across the five segments is 0.08 dB):

  seg 1: passband=-74.6661, L=-82.6661, suffix_max[81]=-82.9630, margin=0.30 dB
  seg 2: passband=-73.2806, L=-81.2806, suffix_max[81]=-81.3631, margin=0.08 dB  <-- minimum
  seg 3: passband=-74.8137, L=-82.8137, suffix_max[81]=-83.1750, margin=0.36 dB
  seg 4: passband=-74.5161, L=-82.5161, suffix_max[81]=-82.9288, margin=0.41 dB
  seg 5: passband=-73.9654, L=-81.9654, suffix_max[81]=-82.0786, margin=0.11 dB

RISK NOTE (architecture.md §6 risk 1 — residual quantization): The 0.08 dB margin on segment 2 is
within Welch estimator noise. A margin this thin means the reported grid band (15788 Hz) could shift
to the adjacent band (16251 Hz) under re-measurement. However, confidence=1.0 because the
hf_stability_tolerance_hz=2000 Hz is too coarse to detect a 463 Hz shift. Confidence=1.0 here is not
evidence of localization robustness — it is evidence the confidence metric cannot see this quantization
risk at this tolerance. This is the §6 risk 1 finding Gate 2 was tasked with capturing.

---

## Track: GusGus_-_Over_Arabian_Horse_Album.wav

sr=48000, duration=354.5s

hf_band_limit_hz: 16251.06656324271
stable: True
confidence: 1.0
insufficient_duration: False
suspected_transcode: True (band 15500–16500 Hz)
per_segment_hf_band_limit_hz: [16251.07, 16251.07, 16251.07, 16251.07, 16251.07]

### Whole-track PSD

freeze_index: 80
passband_level: -81.7510 dB
j_star: 82
centers[j*]: 16251.07 Hz
L = passband_level - 8.0 = -89.7510 dB
margin at j* = L - suffix_max[j*] = -89.7510 - (-97.0987) = 7.35 dB

suffix_max window (bands 77..87):
  band 77: centers=14065.89 Hz, suffix_max=-79.9268 dB
  band 78: centers=14478.05 Hz, suffix_max=-79.9268 dB
  band 79: centers=14902.29 Hz, suffix_max=-80.3441 dB
  band 80: centers=15338.96 Hz, suffix_max=-81.7510 dB
  band 81: centers=15788.43 Hz, suffix_max=-86.1349 dB   (still above L: -86.13 > -89.75)
  band 82: centers=16251.07 Hz, suffix_max=-97.0987 dB   <-- j*  (margin 7.35 dB below L)
  band 83: centers=16727.26 Hz, suffix_max=-97.4524 dB
  band 84: centers=17217.41 Hz, suffix_max=-97.8110 dB
  band 85: centers=17721.91 Hz, suffix_max=-98.6778 dB
  band 86: centers=18241.21 Hz, suffix_max=-99.4226 dB
  band 87: centers=18775.71 Hz, suffix_max=-99.4226 dB

### Per-segment traces

All five segments: freeze_index=80, j_star=82, centers[j*]=16251.07 Hz (identical grid band across
all segments). Margin robust (7+ dB) across all segments.

---

## Track: Leftfield_-_Melt_Audio.wav

sr=48000, duration=313.8s

hf_band_limit_hz: 20475.060846272223
stable: True
confidence: 1.0
insufficient_duration: False
suspected_transcode: True (band 19500–20500 Hz)
per_segment_hf_band_limit_hz: [20475.06, 20475.06, 20475.06, 20475.06, 20475.06]

### Whole-track PSD

freeze_index: 89
passband_level: -94.6703 dB
j_star: 90
centers[j*]: 20475.06 Hz
L = passband_level - 8.0 = -102.6703 dB
margin at j* = L - suffix_max[j*] = -102.6703 - (-125.6561) = 22.99 dB

suffix_max window (bands 85..95):
  band 85: centers=17721.91 Hz, suffix_max=-90.4130 dB
  band 86: centers=18241.21 Hz, suffix_max=-91.6407 dB
  band 87: centers=18775.71 Hz, suffix_max=-92.5939 dB
  band 88: centers=19325.88 Hz, suffix_max=-93.1984 dB
  band 89: centers=19892.18 Hz, suffix_max=-94.6703 dB
  band 90: centers=20475.06 Hz, suffix_max=-125.6561 dB   <-- j*  (margin 22.99 dB below L)
  band 91: centers=21075.03 Hz, suffix_max=-147.0969 dB
  band 92: centers=21692.57 Hz, suffix_max=-147.8274 dB
  band 93: centers=22328.21 Hz, suffix_max=-147.8894 dB
  band 94: centers=22982.48 Hz, suffix_max=-147.8894 dB
  band 95: centers=23655.92 Hz, suffix_max=-147.8894 dB

Architecture prediction confirmed: architecture.md §3.5 worked derivation predicted centers[90] ≈ 20475.1 Hz.
Measured: 20475.06 Hz. CONFIRMED. Per-segment: all five segments also land at 20475.06 Hz.

---

## Track: The_Chemical_Brothers_-_Live_Again_ft_Halo_Maud.wav

sr=48000, duration=254.2s

hf_band_limit_hz: 20475.060846272223
stable: False
confidence: 0.4
insufficient_duration: False
suspected_transcode: True (band 19500–20500 Hz)
per_segment_hf_band_limit_hz: [14065.89, None, 20475.06, 20475.06, None]

### Whole-track PSD

freeze_index: 85
passband_level: -78.5431 dB
j_star: 90
centers[j*]: 20475.06 Hz
L = passband_level - 8.0 = -86.5431 dB
margin at j* = L - suffix_max[j*] = -86.5431 - (-112.3320) = 25.79 dB

suffix_max window (bands 85..95):
  band 85: centers=17721.91 Hz, suffix_max=-78.5431 dB
  band 86: centers=18241.21 Hz, suffix_max=-80.4814 dB
  band 87: centers=18775.71 Hz, suffix_max=-80.4814 dB
  band 88: centers=19325.88 Hz, suffix_max=-80.4814 dB
  band 89: centers=19892.18 Hz, suffix_max=-83.3231 dB
  band 90: centers=20475.06 Hz, suffix_max=-112.3320 dB   <-- j*  (margin 25.79 dB below L)
  band 91: centers=21075.03 Hz, suffix_max=-120.7630 dB
  band 92: centers=21692.57 Hz, suffix_max=-120.8831 dB
  band 93: centers=22328.21 Hz, suffix_max=-120.8831 dB
  band 94: centers=22982.48 Hz, suffix_max=-120.9347 dB
  band 95: centers=23655.92 Hz, suffix_max=-121.5247 dB

### Per-segment traces

Segment 1: freeze_index=71, j_star=77, centers[j*]=14065.89 Hz
  (gate found i_max=71 ≈ 12502 Hz; localization found floor onset at band 77 ≈ 14066 Hz — a 6409 Hz
   disagreement with the whole-track result, well outside the 2000 Hz tolerance)

  suffix_max window (bands 72..82):
    band 72: centers=12174.54 Hz, suffix_max=-83.1416 dB
    band 73: centers=12531.29 Hz, suffix_max=-84.9172 dB
    band 74: centers=12898.48 Hz, suffix_max=-85.7145 dB
    band 75: centers=13276.43 Hz, suffix_max=-88.3432 dB
    band 76: centers=13665.46 Hz, suffix_max=-88.6873 dB
    band 77: centers=14065.89 Hz, suffix_max=-89.9574 dB   <-- j*
    band 78: centers=14478.05 Hz, suffix_max=-89.9574 dB
    band 79: centers=14902.29 Hz, suffix_max=-90.7744 dB
    band 80: centers=15338.96 Hz, suffix_max=-90.7744 dB
    band 81: centers=15788.43 Hz, suffix_max=-92.2340 dB
    band 82: centers=16251.07 Hz, suffix_max=-97.0731 dB

Segment 2: gate returned None (_gate_scan found no qualifying window — Step 0)

Segment 3: freeze_index=88, j_star=90, centers[j*]=20475.06 Hz (agrees with whole-track)

  suffix_max window (bands 85..95):
    band 85: centers=17721.91 Hz, suffix_max=-76.2984 dB
    band 86: centers=18241.21 Hz, suffix_max=-77.8380 dB
    band 87: centers=18775.71 Hz, suffix_max=-77.8380 dB
    band 88: centers=19325.88 Hz, suffix_max=-77.8380 dB
    band 89: centers=19892.18 Hz, suffix_max=-80.6368 dB
    band 90: centers=20475.06 Hz, suffix_max=-109.5676 dB   <-- j*
    band 91: centers=21075.03 Hz, suffix_max=-118.5482 dB
    band 92: centers=21692.57 Hz, suffix_max=-118.5482 dB
    band 93: centers=22328.21 Hz, suffix_max=-118.5482 dB
    band 94: centers=22982.48 Hz, suffix_max=-118.8041 dB
    band 95: centers=23655.92 Hz, suffix_max=-119.4973 dB

Segment 4: freeze_index=85, j_star=90, centers[j*]=20475.06 Hz (agrees with whole-track)

  suffix_max window (bands 85..95):
    band 85: centers=17721.91 Hz, suffix_max=-79.6535 dB
    band 86: centers=18241.21 Hz, suffix_max=-82.1341 dB
    band 87: centers=18775.71 Hz, suffix_max=-82.1341 dB
    band 88: centers=19325.88 Hz, suffix_max=-82.1341 dB
    band 89: centers=19892.18 Hz, suffix_max=-84.6668 dB
    band 90: centers=20475.06 Hz, suffix_max=-114.0524 dB   <-- j*
    band 91: centers=21075.03 Hz, suffix_max=-122.8581 dB
    band 92: centers=21692.57 Hz, suffix_max=-122.8581 dB
    band 93: centers=22328.21 Hz, suffix_max=-122.8581 dB
    band 94: centers=22982.48 Hz, suffix_max=-122.8581 dB
    band 95: centers=23655.92 Hz, suffix_max=-123.4888 dB

Segment 5: gate returned None (_gate_scan found no qualifying window — Step 0)

### Chemical Brothers stability finding — architecture prediction FAILED

Architecture.md §3.7 explicitly predicted: "Chemical Brothers must be re-measured under v1.5, not assumed
fixed by construction alone." The prediction was that v1.5a's tie-free localization would fix the
confidence/stable finding. It did not. v1.4: confidence=0.40, stable=False. v1.5a: confidence=0.40,
stable=False.

The mechanism differs from v1.4:
- v1.4: argmax saturation causing per-segment disagreement through indeterminate candidate ranking
- v1.5a: (a) segments 2 and 5 — _gate_scan returned None (no qualifying window found at all on those
  segments); (b) segment 1 — gate fired early at i_max=71 and localized to 14066 Hz, a 6409 Hz
  disagreement with the whole-track value

The instability is real and driven by genuine per-segment dynamics differences (the wall at ~20 kHz is
not visible to the gate in every segment), not by the argmax-saturation mechanism that v1.5a eliminated.
This is a confirmed failed prediction by the architecture. It should be raised as a defect-grade finding.

---

## Track: Wavy_Gravy.wav

sr=48000, duration=449.6s

hf_band_limit_hz: 20475.060846272223
stable: True
confidence: 0.6
insufficient_duration: False
suspected_transcode: True (band 19500–20500 Hz)
per_segment_hf_band_limit_hz: [20475.06, None, None, 20475.06, 20475.06]

### Whole-track PSD

freeze_index: 89
passband_level: -79.5907 dB
j_star: 90
centers[j*]: 20475.06 Hz
L = passband_level - 8.0 = -87.5907 dB
margin at j* = L - suffix_max[j*] = -87.5907 - (-107.0671) = 19.48 dB

suffix_max window (bands 85..95):
  band 85: centers=17721.91 Hz, suffix_max=-74.3504 dB
  band 86: centers=18241.21 Hz, suffix_max=-74.3504 dB
  band 87: centers=18775.71 Hz, suffix_max=-74.3504 dB
  band 88: centers=19325.88 Hz, suffix_max=-78.8605 dB
  band 89: centers=19892.18 Hz, suffix_max=-79.5907 dB
  band 90: centers=20475.06 Hz, suffix_max=-107.0671 dB   <-- j*  (margin 19.48 dB below L)
  band 91: centers=21075.03 Hz, suffix_max=-130.5005 dB
  band 92: centers=21692.57 Hz, suffix_max=-131.1173 dB
  band 93: centers=22328.21 Hz, suffix_max=-131.3335 dB
  band 94: centers=22982.48 Hz, suffix_max=-131.3335 dB
  band 95: centers=23655.92 Hz, suffix_max=-131.3335 dB

### Per-segment traces

Segment 1: freeze_index=89, j_star=90, centers[j*]=20475.06 Hz
  passband_level=-77.1322 dB, L=-85.1322, suffix_max[90]=-104.3089, margin=19.18 dB

  suffix_max window (bands 85..95):
    band 85: centers=17721.91 Hz, suffix_max=-71.8369 dB
    band 86: centers=18241.21 Hz, suffix_max=-71.8369 dB
    band 87: centers=18775.71 Hz, suffix_max=-71.8369 dB
    band 88: centers=19325.88 Hz, suffix_max=-76.4413 dB
    band 89: centers=19892.18 Hz, suffix_max=-77.1322 dB
    band 90: centers=20475.06 Hz, suffix_max=-104.3089 dB   <-- j*
    band 91: centers=21075.03 Hz, suffix_max=-130.1446 dB
    band 92: centers=21692.57 Hz, suffix_max=-130.1588 dB
    band 93: centers=22328.21 Hz, suffix_max=-130.1588 dB
    band 94: centers=22982.48 Hz, suffix_max=-130.1588 dB
    band 95: centers=23655.92 Hz, suffix_max=-130.1588 dB

Segment 2: gate returned None (_gate_scan found no qualifying window)
Segment 3: gate returned None (_gate_scan found no qualifying window)

Segment 4: freeze_index=87, j_star=90, centers[j*]=20475.06 Hz
  passband_level=-82.1939 dB

  suffix_max window (bands 85..95):
    band 85: centers=17721.91 Hz, suffix_max=-77.3430 dB
    band 86: centers=18241.21 Hz, suffix_max=-82.1939 dB
    band 87: centers=18775.71 Hz, suffix_max=-82.1939 dB
    band 88: centers=19325.88 Hz, suffix_max=-83.2868 dB
    band 89: centers=19892.18 Hz, suffix_max=-84.8020 dB
    band 90: centers=20475.06 Hz, suffix_max=-112.1704 dB   <-- j*
    band 91: centers=21075.03 Hz, suffix_max=-126.5993 dB
    band 92: centers=21692.57 Hz, suffix_max=-126.6992 dB
    band 93: centers=22328.21 Hz, suffix_max=-127.2929 dB
    band 94: centers=22982.48 Hz, suffix_max=-127.2929 dB
    band 95: centers=23655.92 Hz, suffix_max=-127.2929 dB

Segment 5: freeze_index=89, j_star=90, centers[j*]=20475.06 Hz
  passband_level=-75.2270 dB

  suffix_max window (bands 85..95):
    band 85: centers=17721.91 Hz, suffix_max=-69.6615 dB
    band 86: centers=18241.21 Hz, suffix_max=-69.6615 dB
    band 87: centers=18775.71 Hz, suffix_max=-69.6615 dB
    band 88: centers=19325.88 Hz, suffix_max=-74.8922 dB
    band 89: centers=19892.18 Hz, suffix_max=-75.2270 dB
    band 90: centers=20475.06 Hz, suffix_max=-102.9526 dB   <-- j*
    band 91: centers=21075.03 Hz, suffix_max=-135.5515 dB
    band 92: centers=21692.57 Hz, suffix_max=-144.5513 dB
    band 93: centers=22328.21 Hz, suffix_max=-147.0468 dB
    band 94: centers=22982.48 Hz, suffix_max=-147.6729 dB
    band 95: centers=23655.92 Hz, suffix_max=-147.7623 dB

NOTE: confidence=0.6 is exactly at hf_cliff_confidence_stable_floor=0.6, so stable=True by zero margin.
3/5 segments agree; 2 returned None (gate missed the wall). Same segment-miss pattern as Chemical Brothers.

---

## Cross-checks and findings for main session

### Why three tracks at identical 20475.060846272223 Hz are not measuring-the-calculation

Band 90 spans edges 1500·2^(90/24) = 20181.5 Hz to 1500·2^(91/24) = 20773.4 Hz (width ≈ 592 Hz). Any
genuine wall anywhere in that ~592 Hz range will map to the same grid center. Evidence that these are
genuine independent measurements at the same grid band, not a calculation artifact:
- Floor depths at band 90 differ widely: Leftfield -125.7, Wavy -107.1, Chemical -112.3 (whole-track)
- freeze_index differs: Leftfield=89, Wavy=89, Chemical=85
- Per-segment None-return patterns differ between tracks
- The architecture's worked derivation independently predicted Leftfield at exactly this band before the run

### Summary table

| Track | v1.4 hz | v1.5a hz | stable | conf | freeze_idx | j* | margin_dB | suspected_transcode |
|---|---|---|---|---|---|---|---|---|
| Black_Flute | 16727.3 | **15788.4** | True | 1.0 | 75 | 81 | 0.39 (min 0.08) | **True** (15500–16500) |
| GusGus | 16727.3 | **16251.1** | True | 1.0 | 80 | 82 | 7.35 | **True** (15500–16500) |
| Leftfield | 22328.2 | **20475.1** | True | 1.0 | 89 | 90 | 22.99 | **True** (19500–20500) |
| Chemical_Bros | 21075.0 | **20475.1** | **False** | 0.4 | 85 | 90 | 25.79 | **True** (19500–20500) |
| Wavy_Gravy | 22982.5 | **20475.1** | True | 0.6 | 89 | 90 | 19.48 | **True** (19500–20500) |

Under v1.4, 0/5 tracks were flagged suspected_transcode. Under v1.5a, 5/5 are flagged.

### Segment-miss finding (gate returned None on real walls)

4 of 25 segment-level detector calls returned None on files whose whole-track trace shows a clear
wall (25–28 dB margin). Distribution: Chemical Brothers 2/5 missed, Wavy Gravy 2/5 missed.
This answers architecture.md §3.4 horn-(a) empirically: the gate at the current 8.0 dB /
12 dB/oct passband threshold misses genuinely real walls on 16% of segment-level calls, even where
the whole-track result is unambiguous. This is a Gate 2 empirical finding, not an assertion.

### Findings for main session to log as defects

1. **Chemical Brothers stable=False, confidence=0.4 — architecture prediction failed.**
   Architecture.md §3.7 predicted v1.5a would fix this. It did not. Mechanism differs from v1.4
   (gate-miss and early-fire on short segments, not argmax saturation), but result is identical.
   Triage recommendation: Architectural (the segment-level gate criterion or
   hf_cliff_confidence_stable_floor itself needs re-examination).

2. **5/5 reference tracks flagged suspected_transcode under v1.5a (0/5 under v1.4).**
   Band limits at 15788, 16251, 20475, 20475, 20475 Hz all fall in transcode_suspect_bands.
   This flag is passed through to STORY-005 which derives mastering targets from these tracks.
   If flagging is correct, the reference set has no clean masters. If the transcode bands are
   over-broad (e.g. 19500–20500 captures ordinary 20 kHz CD-quality ceiling), the flag is a
   false positive and STORY-005 targets derived from it would be miscalibrated.
   Triage recommendation: Architectural (requires reviewing transcode_suspect_bands_hz boundaries
   and whether a 48 kHz file with a 20 kHz wall is correctly classified as a transcode).

3. **Black Flute localization margin 0.08 dB on segment 2 — confidence metric too coarse to detect.**
   The 2000 Hz hf_stability_tolerance_hz cannot see a 463 Hz adjacent-band shift, so confidence=1.0
   does not bound localization robustness here. This is the §6 risk 1 finding.
   Triage recommendation: Code-level (confidence metric should incorporate a distance-weighted
   agreement measure, or the tolerance should be documented as deliberately coarse with a known
   lower-bound on visible shift).
