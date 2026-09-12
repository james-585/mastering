```
## Contract
Consumes: Floating-point AudioBuffer (numpy float32 array) produced by the rendering stage (producer story not specified; see Open Questions)
Produces: ArtifactDetectionResult JSON + Markdown report section and appended ArtifactFlag entries in Measurements
Consumed by: terminal (human triage) and PlausibilityWarning aggregator
```

**Restated Intent**
- Implement a report-only analysis module that detects Suno-generation artifacts (smeared transients, high-frequency digital haze, stationary whistles, and high-frequency phase decorrelation) and emits timestamped ArtifactFlag entries with confidence and diagnostic details. The module must not modify the audio.

**Acceptance Criteria**
1. Given a rendered floating-point AudioBuffer and its sample rate, when the module runs, then it appends an ArtifactDetectionResult with correct datatypes and returns the unmodified audio array (byte-identical SHA-256 hash before/after).
2. Given clean reference commercial tracks (e.g., Chemical Brothers, GusGus), when analyzed, then zero false-positive flags are emitted for those references.
3. Given synthetic audio with an injected 6.4 kHz whistle and a smeared transient, when analyzed, then the module emits a `STATIONARY_WHISTLE` and `SMEARED_TRANSIENT` flag with correct timestamp boundaries and `confidence_score >= 0.80`.
4. Given a file containing continuous HF flatness, when SFM in 8–16 kHz exceeds 0.85 for >= 2.0 s and overall dynamic range is low, then the module emits `DIGITAL_HAZE` covering the same interval.
5. Given narrow spectral peaks with Q >= 8 and prominence >= 6 dB sustained >= 1.5 s, when detected, then emit `STATIONARY_WHISTLE` with `frequency_hz` and `prominence_db` in details.
6. When inter-channel HF phase variance and cross-correlation show rapid uncorrelated fluctuations with stable low-frequency correlation, then emit `PHASE_SWISH` with relevant metrics and confidence.
7. All flags include: `timestamp_start_s`, `timestamp_end_s`, `artifact_type`, `confidence_score` (0.0–1.0), and `details` dict; `ArtifactDetectionResult.total_artifacts_found` equals the length of `artifact_flags` and `overall_artifact_density_score` is normalized 0.0–1.0.

**Detectors & Thresholds (must be implemented as heuristics)**
- **Windowing**: non-overlapping STFT windows (default 500 ms) with configurable hop/FFT parameters.
- **SMEARED_TRANSIENT**: onset rise-time > 25 ms OR HF onset energy < 12 dB relative to lower-mid onset energy; use spectral flux + local crest factor on percussive onsets.
- **DIGITAL_HAZE**: spectral flatness measure (SFM) in 8–16 kHz > 0.85 continuously for >= 2.0 s while dynamic range remains low.
- **STATIONARY_WHISTLE**: narrow spectral peak persistence (Q >= 8, prominence >= 6.0 dB) sustained >= 1.5 s; report center frequency and prominence.
- **PHASE_SWISH**: inter-channel phase variance and cross-correlation computed for bins > 8 kHz; rapid HF phase variance with stable LF correlation triggers flag.

**Audio Quality & Format Targets (explicit / assumptions)**
- **Input types**: accept floating-point PCM arrays (numpy float32/float64), with an explicit `sample_rate` parameter and channel count (mono/stereo). The module must validate sample rate and channel metadata before processing.
- **No modifications**: The input audio array's SHA-256 hash must be identical after processing.
- **Frequency bins**: detectors reference Hz ranges (8 kHz–16 kHz) and frequencies reported in Hz; behaviour for sample rates < 32 kHz must be defined (see Open Questions).

**Integration & Outputs**
- **Module path**: analysis/artifact_detection.py (new)
- **Orchestration**: integrated into `analysis.__init__.measure_all()` Stage 2 pass and must append to the existing `Measurements` structure per `analysis/types.py`.
- **Dataclasses required**: `ArtifactFlag` and `ArtifactDetectionResult` as specified in the story.
- **Reports**: populate a `Suno Generation Artifacts` section in Markdown and emit equivalent JSON. High-confidence flags (confidence >= configurable threshold, default 0.8) are forwarded to the PlausibilityWarning list with concise human-readable text.

**Non-functional Requirements**
- **Determinism**: given identical input and configuration, results must be reproducible across runs.
- **Performance**: best-effort real-time is not required; module should process a 5-minute stereo track at 44.1 kHz in under N minutes (unbounded here — see Open Questions for exact throughput SLA).
- **Dependencies**: use `analysis/_psd.py`, `analysis/silence.py`, and `analysis/types.py` for existing helpers and datatypes.
- **Testing**: unit tests must include negative controls (clean percussion, reference tracks) and synthetic positive controls (injected whistle, smeared transient). The synthetic tests must verify timestamps and confidence thresholds.

**Rejected as out of scope**
- Any attempt to correct or repair detected artifacts (transient repair, de-noising, source separation) — detection only. Rationale: DOMAIN.md §4 forbids fixing transient smearing or recovering band-limited content.
- Claims that the module can reliably fix or restore content above the generation band limit or remove baked-in ambience.

**Open Questions**
- Which story/producer produces the consumed AudioBuffer artifact (the backlog maps artifact detection to STORY-008; incoming artifact filename and producer story ID are unspecified)?
- Required supported sample rates and minimum channel count (e.g., must support 44.1 kHz and 48 kHz; behaviour when sample_rate < 32000).
- Exact JSON schema for `ArtifactDetectionResult` and how Measurements integrates with existing report schema (field names/locations).
- Performance SLA (target processing time per minute of audio) and batch-size expectations.
- Which concrete reference tracks constitute the negative-control set for CI (names/paths).
- Default confidence-to-PlausibilityWarning threshold (suggested 0.80 but configurable).

**Revision History**
- 2026-08-12: Initial requirements derived from `STORY-007 Artifacts.md` attachment and project domain docs. Noted backlog ID mismatch with `docs/BACKLOG.md` (artifact detection listed as STORY-008); flagged in Open Questions.
