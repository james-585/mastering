# STORY-F2 Requirements — HF Extension Cliff Detection

## Contract
```
Consumes:  AudioBuffer (analysis input, 44.1 kHz / 48 kHz sample rate)
Produces:  Corrected hf_extension measurement in ReferenceMeasurements schema
Consumed by: Reference reporting (report/reference_render.py), future stories requiring validated HF extension targets
```

---

## Restated Intent

Replace the threshold-based HF extension detection (which measures spectral tilt and produces physically impossible results) with cliff-detection that identifies the actual band-limit boundary imposed by codec/generation constraints. The method must return stable, plausible measurements for all five reference tracks, resolving the DEF-609 recurrence of the DEF-201 method error.

**User value:** Credible reference analysis reporting. While no current mastering decision depends on HF extension (air band is informational-only per STORY-006), this measurement is visible in reference reports and future stories may derive air-band correction targets from it. A method reporting 5 kHz cutoffs on commercial CD masters undermines trust in the entire analysis pipeline.

---

## Acceptance Criteria

### AC-F2-1: Method implementation
**Given** the cliff-detection algorithm is implemented in `analysis/hf_extension.py`  
**When** analyzing any audio file  
**Then** the method must:
- Detect sustained slopes of ≥24 dB/octave across adjacent spectral bins
- Verify the slope is followed by a noise floor持续ing for at least one full octave
- Return `rolloff_hz = null` if no cliff meeting the criterion is found
- Never fall back to threshold-based tilt measurement

### AC-F2-2: Stability on reference set
**Given** all five reference tracks (Chemical Brothers, GusGus, Black Flute, Leftfield, Wavy Gravy)  
**When** analyzed with the new cliff-detection method  
**Then** all five tracks must report `stable = true` with zero per-segment variation in `rolloff_hz`

### AC-F2-3: Plausibility — commercial CD masters
**Given** Leftfield — Melt, Wavy Gravy (1995 CD masters)  
**When** analyzed  
**Then** each must report either:
- `rolloff_hz` in range [18000, 22050] Hz (expected for CD lossless), OR
- `rolloff_hz = null` (no cliff detected)
**And** must NOT report any value below 10000 Hz

### AC-F2-4: Plausibility — modern masters
**Given** Chemical Brothers, GusGus, Black Flute (contemporary masters)  
**When** analyzed  
**Then** each must report either:
- `rolloff_hz` in range [16000, 22050] Hz, OR
- `rolloff_hz = null`
**And** must NOT report any value below 10000 Hz

### AC-F2-5: Leftfield specific validation (DEF-609 closure evidence)
**Given** Leftfield — Melt (the track that reported 5131 Hz segments under the broken method)  
**When** analyzed with cliff-detection  
**Then** must report:
- `rolloff_hz` ≥ 18000 Hz OR `rolloff_hz = null`
- `stable = true`
**And** must NOT report 5131 Hz, 8170 Hz, or any value indicating mid-frequency spectral tilt

### AC-F2-6: Pink noise negative control (H3)
**Given** a synthetic pink noise signal (−3 dB/octave tilt, no band limit, 10 s duration, 44.1 kHz)  
**When** analyzed  
**Then** must report:
- `rolloff_hz = null` (no cliff exists)
- `stable = true`
- `method = "cliff_detection"`
- `hf_band_limit_confidence = "none"`

### AC-F2-7: Brick-wall filter positive control
**Given** synthetic pink noise → brick-wall Butterworth LP filter (order ≥8) at 16000 Hz, 10 s, 44.1 kHz  
**When** analyzed  
**Then** must report:
- `rolloff_hz` in range [15500, 16500] Hz (±500 Hz tolerance for filter transition band)
- `stable = true`
- `method = "cliff_detection"`
- `hf_band_limit_confidence = "high"` (clean synthetic cliff)

### AC-F2-8: MP3 192 kbps detection
**Given** a lossless reference track encoded to MP3 192 kbps (expected cutoff ≈18 kHz per DOMAIN.md §2)  
**When** analyzed  
**Then** must report:
- `rolloff_hz` in range [17000, 19000] Hz
- `stable = true`

### AC-F2-9: Return contract compliance
**Given** any analyzed track  
**When** measurement is serialized to `reference_set_report.json`  
**Then** the `hf_extension` object must contain exactly:
- `hf_band_limit_hz`: int or null
- `hf_band_limit_confidence`: "high" | "low" | "none"
- `stable`: bool (true for file-level measurements, false if per-segment variance detected — though false should never occur with correct cliff-detection)
- `method`: "cliff_detection"

### AC-F2-10: No threshold parameter (H6 compliance)
**Given** the implementation source code  
**When** grepped for threshold constants  
**Then** must NOT contain any constant of the form "threshold_db", "tilt_threshold", or "energy_drop_db" used to compare spectral energy levels  
**And** the ≥24 dB/octave slope criterion must be implemented as a slope measurement (dB change per octave), not a level threshold

### AC-F2-11: Reference report rendering
**Given** a regenerated `reference_set_report.json` with cliff-detection measurements  
**When** `report/reference_render.py` produces the reference analysis report  
**Then** the HF extension section must display:
- Reported `rolloff_hz` or "No cutoff detected"
- `stable` status
- `hf_band_limit_confidence` value
- `method` confirmation ("cliff_detection")
**And** the informational-only caveat (from STORY-006 requirements) must remain: "HF extension is not used as a correction target"

### AC-F2-12: Plausibility gate (H5)
**Given** the full regenerated reference set report with all five tracks analyzed  
**When** reviewed by the mastering-engineer agent (Gate 2)  
**Then** no measurement may be flagged as physically impossible, and the report must pass without HF extension credibility concerns

---

## Audio Quality Targets

These are **accuracy targets** for the detection algorithm, not mastering loudness/EQ targets:

| Source type | Expected `rolloff_hz` range | Rationale |
|---|---|---|
| CD lossless (44.1 kHz) | 18000–22050 Hz or null | Nyquist = 22050 Hz; most CD masters extend to ≥20 kHz unless deliberately filtered |
| MP3 320 kbps | 19000–21000 Hz | Per DOMAIN.md §2 |
| MP3 256 kbps | 18000–20000 Hz | Per DOMAIN.md §2 |
| MP3 192 kbps | 17000–19000 Hz | Per DOMAIN.md §2 |
| MP3 128 kbps | 15000–17000 Hz | Per DOMAIN.md §2 |
| Suno / AI-generated | 13000–16000 Hz, may drift within file | Per DOMAIN.md §2; drift is a property of the source, not a method error |

**Tolerance:** ±500 Hz on controlled synthetic fixtures (brick-wall filter test). ±1000 Hz on real programme material (filter transition bands vary by mastering chain).

**Stability criterion:** For any single file, all per-segment measurements must agree within ±500 Hz, OR the method must return `stable = false` and escalate for review (though correct cliff-detection on fixed-cutoff sources should always be stable).

---

## Input/Output Assumptions

### Input
- **AudioBuffer or file path**: Stereo or mono, any bit depth (converted to float64 internally)
- **Sample rate**: Primarily 44.1 kHz and 48 kHz (reference set). Must handle 32 kHz and above gracefully; below 32 kHz may return `null` (Nyquist too low to meaningfully detect music-range cliffs)
- **Duration**: Minimum 5 seconds for stable Welch PSD estimation (longer preferred for sub-Nyquist noise-floor measurement)
- **Content**: Any programme material (music, pink noise, sine sweeps)

### Output
- **ReferenceMeasurements.hf_extension** object (JSON-serializable) containing:
  - `hf_band_limit_hz`: integer (Hz) or `null`
  - `hf_band_limit_confidence`: string ("high" | "low" | "none")
  - `stable`: boolean
  - `method`: string (must be "cliff_detection" for this implementation)
- **Nullable semantics**: `null` is a valid, correct result meaning "no band-limit cliff detected" — not an error condition

### Processing constraints
- **Non-destructive**: Analysis only; input audio never modified
- **Offline**: Welch PSD with overlapping windows; not real-time
- **Memory**: Must handle 5-minute stereo tracks at 48 kHz (~30 MB float64) without excessive memory consumption (avoid loading entire FFT matrices into RAM simultaneously)

---

## Explicit Out-of-Scope

| Not included | Reason |
|---|---|
| Air band correction in mastering | Still informational-only per STORY-006 architecture. This story fixes measurement accuracy, not mastering behavior. |
| Content recovery above band limit | Silence above the cliff, per DOMAIN.md §4. Not recoverable. |
| Multiple cliff detection (e.g. MP3 cascade artifacts) | Q3 open question unresolved. MVP reports the first/highest cliff only. |
| Adaptive `nperseg` by sample rate | Fixed `nperseg = 8192` adequate for 44.1/48 kHz. Lower sample rates may require adjustment in future story. |
| Psychoacoustic weighting of cliff sharpness | Binary detected/not-detected. "High" vs "low" confidence (Q1) deferred to architecture phase. |
| Suno drift quantification | DOMAIN.md §2 notes Suno may drift within file. Story establishes this is a property of the source (report `stable = false` + mean), not a method error. Drift *rate* or *span* quantification is out of scope. |

---

## Non-Functional Requirements

### Performance
- **Throughput target**: Analyze one 5-minute stereo track (44.1 kHz) in ≤ 3 seconds on reference hardware (developer's Windows machine)
- **Batch processing**: Five reference tracks analyzed sequentially in ≤ 15 seconds total
- **No regression**: Must not slow down existing `measure_all()` pipeline by more than 10%

### Reliability
- **Deterministic**: Same input file → same `rolloff_hz` every run (no randomness in cliff detection)
- **Robustness**: Must not crash or return NaN on:
  - Silence
  - DC offset
  - Clipped audio
  - Non-finite samples (Inf, NaN) → should validate and raise clear error before analysis
- **Graceful degradation**: If sample rate < 32 kHz, return `rolloff_hz = null`, `confidence = "none"`, log warning (Nyquist too low for meaningful detection)

### Maintainability
- **No magic numbers**: All constants (≥24 dB/oct criterion, one-octave noise-floor span, `nperseg` choice, frequency resolution) must be named and commented with derivation or source (CLAUDE.md, DOMAIN.md, or engineering rationale)
- **Testability**: Cliff-detection logic separated into pure function accepting PSD array → detects cliff → returns (frequency, confidence) for unit testing without full audio I/O
- **Logging**: Must log at INFO level: detected cliff frequency, confidence, stable/unstable status, and `null` results with reason (no cliff found, Nyquist too low, etc.)

### Compatibility
- **Existing schema**: `ReferenceMeasurements` in `analysis/reference_types.py` already supports `hf_extension` as optional dict; no breaking schema change
- **Backward compatibility**: Old threshold-based measurements in existing `reference_set_report.json` files will be replaced when regenerated; no migration script required (one-way upgrade)

---

## Open Questions

### Q1: Confidence levels
**Question:** Should `hf_band_limit_confidence` use a three-level scale ("high" | "low" | "none"), or binary ("detected" | "none")?

**Context:** A "clean" cliff (e.g. brick-wall filter) has a narrow transition band (1–2 bins). A "soft" cliff (e.g. analog tape, heavy shelving EQ) may have a wider transition (10+ bins) making exact frequency ambiguous.

**Deferred to architect:** Specify the criterion for "high" vs "low" (e.g., transition band width threshold in Hz, slope sharpness exceeding 40 dB/oct for "high"). If binary is sufficient, collapse to "detected" | "none".

### Q2: Noise-floor span requirement
**Question:** Should the "one full octave above transition" noise-floor criterion be configurable, or hardcoded to 1.0 octave?

**Context:** Suno-generated audio may have noise-floor modulation or artifacts near Nyquist. A shorter span (e.g. 0.5 octave) may reduce false negatives but increase false positives on noisy material.

**Deferred to architect:** Specify the octave span, or make it a named constant with clear rationale.

### Q3: Multiple cliffs
**Question:** If a track has multiple cliffs (e.g. MP3 128 kbps artifact at 8 kHz + generation limit at 15 kHz), which should be reported?

**Options:**
- (a) Report the **first** (lowest frequency) cliff only
- (b) Report the **highest** cliff only (closest to Nyquist)
- (c) Report **all** cliffs as an array
- (d) Report the **last** cliff before Nyquist that meets the one-octave noise-floor criterion

**Context:** DOMAIN.md §2 expected ranges assume a single band limit per file. Multiple cliffs suggest cascade encoding (MP3 of MP3) or generative model trained on lossy data — rare on the reference set but plausible on Suno exports.

**Deferred to architect:** Specify the policy. Option (b) is simplest and aligns with "report the generation/codec limit, not intermediate artifacts."

### Q4: `stable = false` handling
**Question:** If per-segment cliff measurements vary by >500 Hz (indicating the method is still measuring content, not a fixed property), should the implementation:
- (a) Return `stable = false` + mean `rolloff_hz` + flag for manual review
- (b) Return `rolloff_hz = null` + `stable = false` (reject the measurement as unreliable)
- (c) Raise an error (method validation failure)

**Context:** DOMAIN.md §2 states instability means the method is wrong. However, Suno sources *may* genuinely drift (variable generation band limit within one export). Distinguishing "method error" from "source property" requires ground truth.

**Deferred to architect:** Specify the action. Option (a) preserves the measurement for inspection; option (b) is conservative.

---

## Revision History

### v1.0 — 2026-08-15
Initial requirements following DEF-609 deferral from STORY-006 architecture.md §23. Open questions Q1–Q4 flagged for architect resolution before implementation.

---

## Notes for Architect

1. **Cliff slope measurement approach**: Recommend using a sliding window (e.g. 5 adjacent bins) to compute dB/octave slope across the PSD. A sustained slope ≥24 dB/oct for at least 3 consecutive windows qualifies as a cliff. This avoids false positives from single-bin noise spikes.

2. **Noise-floor detection**: After detecting a cliff candidate, verify the mean PSD level in the octave above the cliff frequency is within 3 dB of the minimum (i.e., a stable floor, not a brief dip followed by more content).

3. **Welch parameters**: `nperseg = 8192`, `noverlap = nperseg // 2`, `window = 'hann'` provides good frequency resolution (~5 Hz at 44.1 kHz) and averaging for stable noise-floor estimation. Per-segment PSDs should be averaged (mean or median) for the file-level spectrum before cliff detection.

4. **Integration with existing analysis**: The function signature should match the existing `measure_hf_extension(audio, sr)` in `analysis/hf_extension.py` to minimize pipeline.py changes. Return type: `HFExtension` dataclass or dict matching the schema in AC-F2-9.

5. **Test fixtures**:
   - Pink noise (no cliff): `scipy.signal.pink()` or hand-rolled (cumsum of white noise)
   - Brick-wall LP filter: `scipy.signal.butter(order=10, Wn=16000, btype='low', fs=44100)` for sharp cliff
   - MP3 encoding: use `pydub` or `ffmpeg` subprocess (outside critical path; fixture generation only)

6. **H6 compliance evidence**: The ≥24 dB/octave criterion is a *method* property (slope-based cliff detection), not a *parameter* of a threshold-based method. This is a method change, not a parameter tuning, satisfying CLAUDE.md §5.

---

## Assumptions Pending BA Confirmation

None. All open questions flagged above (Q1–Q4) are architectural decisions requiring software-architect input, not business-analyst clarification. Story is ready for architect handoff once BA approves scope and acceptance criteria as written.
