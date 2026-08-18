# STORY-F2 — HF Extension Cliff Detection (DEF-609)

**Priority: Medium. Fixes reporting credibility in reference analysis; does not block mastering correctness.**

Source: Deferred from STORY-006 (architecture.md §23, DEF-609). Governed by `docs/CLAUDE.md`, `docs/DOMAIN.md`, `docs/HANDOFF.md` (H-rules).

## Contract (H1)
```
Consumes:    AudioBuffer (analysis input, any sample rate)
             reference_set_report.json schema (existing)
Produces:    Corrected hf_extension field in ReferenceMeasurements
             (hf_band_limit_hz: nullable, hf_band_limit_confidence: str,
              stable: bool, method: "cliff_detection")
Consumed by: Reference reporting (report/reference_render.py)
             Future stories requiring validated HF extension targets
```

## Background

The current HF extension detection uses threshold-based spectral tilt measurement (detect where energy drops N dB relative to lower-frequency content). This is a known-wrong pattern (CLAUDE.md §5) that has failed twice on this project:

1. **DEF-201** — first failure, threshold raised 6→20 dB (parameter change to wrong method)
2. **DEF-609** — recurrence. All five reference tracks report `stable=False`, with per-segment variation of 2–9 kHz within single files. Leftfield — Melt reports 8170 Hz overall with segments at 5131 Hz — physically impossible for a 1995 CD master extending to ~20 kHz.

**Root cause:** Music has a naturally declining spectrum (−3 to −6 dB/octave). Any fixed threshold is crossed by normal spectral tilt on dark or heavily filtered material thousands of Hz below the actual band limit. The method measures programme content, not a structural property.

**Current containment:** No STORY-006 mastering processing reads `hf_extension`. Wrong values remain in `reference_set_report.json` (reporting credibility problem) but do not influence correction decisions applied to Suno tracks.

## Scope

Replace the threshold-based detection in `analysis/hf_extension.py` with cliff-detection per CLAUDE.md §5 and DOMAIN.md §2.

### Required Method

**Cliff-detection:** Detect a sharp transition from broadband programme content to noise floor.

**Cliff criterion:**
- Sustained slope of **≥24 dB/octave across adjacent spectral bins**
- Followed by a noise floor that holds for at least one full octave above the transition frequency
- The ≥24 dB/oct figure is the project standard (CLAUDE.md §5, DOMAIN.md §2) — not a tunable parameter

**Frequency resolution:**
- Use Welch PSD with `nperseg` sufficient to resolve at minimum 1/3-octave bins at frequencies of interest
- At 44.1/48 kHz, `nperseg = 8192` gives ≈5 Hz bin width near 10 kHz (adequate)
- Per-segment PSD computation used for noise-floor estimation only
- Rolloff derived from ensemble-averaged spectrum

**No-cliff result:**
- If no cliff meeting the criterion is found: `rolloff_hz = null`, `stable = true`, `method = "cliff_detection"`
- Must not substitute a tilt-derived frequency
- DOMAIN.md §2: "No cliff → report NO CUTOFF"

**Stability requirement:**
- A band limit is a fixed property of a file (DOMAIN.md §2)
- Method must return a single file-level rolloff measurement
- If implementation reports different `rolloff_hz` across segments: implementation is wrong
- Per-segment instability means method is measuring programme content, not a structural band limit

### What This Story Does NOT Fix

- Air band correction in mastering (still informational-only; no change to STORY-006 targets)
- Content above the band limit (silence, not recoverable)
- Any non-reporting use of HF extension (none exists in current codebase)

## Acceptance Criteria

From STORY-006 architecture.md §23 closure condition and DOMAIN.md §2 plausibility ranges:

1. **Method change implemented**: Cliff-detection with ≥24 dB/octave sustained slope criterion replaces threshold-based detection
2. **All five reference tracks stable**: `stable = true` for every track (no per-segment variation)
3. **Plausible values**: All reported `rolloff_hz` either:
   - `null` (no cliff detected), OR
   - Within expected range for source type (10–22 kHz for commercial CD masters per DOMAIN.md §2)
4. **No impossible readings**: No commercial master reports cutoff below 10 kHz
5. **Leftfield — Melt specifically**: Reports plausible cutoff ≥18 kHz or `null` (not 5131 Hz, not 8170 Hz)
6. **Return contract**: Fields match requirements.md specification:
   - `hf_band_limit_hz` (nullable int)
   - `hf_band_limit_confidence` (str: "high" | "low" | "none")
   - `stable` (bool)
   - `method` (str: "cliff_detection")
7. **Pink-noise negative control** (H3): Synthetic pink noise with no band limit → `rolloff_hz = null`, `stable = true`
8. **Synthetic cliff positive control**: Pink noise + brick-wall LP filter at 16 kHz → detects 16 kHz ± 500 Hz, `stable = true`
9. **No threshold parameter remains**: Grep confirms no threshold-in-dB constant used for cliff detection (≥24 dB/oct is a slope criterion, not a level threshold)
10. **Reference report updated**: `report/reference_render.py` displays new fields correctly
11. **H5 plausibility gate**: Full reference report passes mastering-engineer review

## Open Questions for BA to Resolve

1. Should `hf_band_limit_confidence` distinguish between "high" (clean cliff, narrow transition) and "low" (ambiguous slope, wide transition), or is a binary detected/not-detected sufficient?
2. Should the one-octave noise-floor requirement above the transition be configurable, or hardcoded?
3. If a track has a cliff at 8 kHz (MP3 128 kbps artifact) but also has a second cliff at 16 kHz (generation limit), which should be reported — the first, the highest, or both?

## Definition of Done

Per HANDOFF.md Part 3:
- Architecture.md produced and Gate 1 passed
- Implementation complete with ground-truth tests
- QA automation passes all acceptance criteria above
- Gate 2 review passes
- Human listening check: n/a (analysis-only story, no audio altered)

## Coordinator Notes

- Implementation lives in `stories/STORY-001/implementation/suno_mastering/analysis/hf_extension.py` (shared tree)
- Tests go in `stories/STORY-001/implementation/tests/`
- Existing `reference_set_report.json` schema supports nullable `hf_band_limit_hz`; no schema change required
- DEF-609 remains **Open** until this story's QA confirms all five reference tracks stable and plausible
