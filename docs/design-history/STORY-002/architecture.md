# STORY-002: Reference track analysis — Architecture

Status: v3 (see Section 15 revision history — v2 resolved three
Architectural defects from the python-developer's first implementation pass
(DEF-101 mono-sum baseline math, DEF-102 whole-set time budget, DEF-103
memory estimate); v3 resolves a fourth, DEF-110, a re-triaged Architectural
defect surfaced by QA's STORY-001 non-regression check — see Section 16).
Originally based on requirements.md v2 (all ten open questions resolved,
2026-08-01). This document was written after reading STORY-001's
architecture.md (v5) and its implementation in full (`analysis/types.py`,
`loudness.py`, `true_peak.py`, `dynamic_range.py`, `frequency_balance.py`,
`stereo_phase.py`, `io/ingest.py`, `io/wav_chunks.py`, `report/builder.py`,
`report/render.py`, `config.py`, `pipeline.py`, `errors.py`), and — for v2 —
after reading STORY-002's own first-pass implementation
(`analysis/mono_sum.py`, `analysis/reference_types.py`,
`analysis/clipping.py`, `analysis/true_peak.py`, `analysis/__init__.py`,
`reference_analysis/config.py`) and `defects.md` in full.

This document is the build contract for the python-developer and the
reference frame for the test-case-writer/QA agent, matching the role
STORY-001's architecture.md played for that story. Where requirements.md
left a genuine engineering decision to the architect, it's made here
concretely, with reasoning. No product-level judgment calls are re-litigated
— requirements.md resolved all ten of those already.

**Hard constraint governing every decision below**: this story modifies
`stories/STORY-001/implementation/` in place. There is no separate
implementation tree. New modules live alongside STORY-001's existing ones in
the same `suno_mastering` package; existing `analysis/*` measurement
functions are called, not forked, wherever STORY-002 needs a metric
STORY-001 already computes.

---

## 1. Pipeline design

This is a **read-only, analysis-and-reporting** pipeline — no DSP, no
export, no mutation. Structurally it is two independent runs of a
per-track analysis stage (one for the reference set, one optionally for a
Suno-export comparison track) followed by a set-level aggregation stage and
a report stage:

```
[R1] Discover & Ingest (per file in the reference folder)
        ↓
[R2] Per-Track Analysis   ──────► ReferenceMeasurements (per track)
        ↓
[R3] Set Aggregation      ──────► AggregateReport (median/min/max, N, exclusions)
        ↓
[R4] Suno-Export Comparison (optional, single track, same [R2] path)
        ↓
[R5] Report Generation (per-track + aggregate + comparison, MD + JSON)
```

Stage responsibilities:

- **[R1] Discover & Ingest** — enumerates every audio file in the supplied
  folder (WAV/FLAC/MP3 by extension + content sniff), computes its input
  SHA-256 hash, decodes it to a float64 numpy array + sample rate via the
  **new**, lighter-weight `io/reference_ingest.py` (§6), and records
  format/provenance (container, lossless/lossy, bitrate where applicable,
  decoder identity). A file that fails to decode is recorded as a per-file
  failure (path + reason) and the run **continues** with the remaining
  files — "given a folder of reference tracks" is a batch operation and one
  bad file must not abort the set (this is not stated explicitly by
  requirements.md but follows directly from its best-effort posture
  elsewhere — flagged as an architecture-level inference, not invented
  product behavior, since it changes no acceptance number).
- **[R2] Per-Track Analysis** — owns AC1: computes every measurement listed
  in AC1 for one track, calling STORY-001's existing `analysis/loudness.py`,
  `analysis/true_peak.py`, `analysis/dynamic_range.py`,
  `analysis/frequency_balance.py`, `analysis/stereo_phase.py` **unmodified
  in their public call contract** (plain numpy array + sample rate + config
  in, typed result out — architecture.md v5 §7's existing convention),
  plus five **new** measurement functions for LRA, seven-band balance, HF
  rolloff, per-band stereo width, and mono-sum level change/cancellation
  (§4). Produces one `ReferenceMeasurements` per track (§3) — never mutates
  or writes back to the source file. Runs strictly **sequentially, one
  track at a time**, releasing that track's audio buffer (and, critically,
  never retaining `true_peak.py`'s `.oversampled` buffer — see §7 memory
  note) before the next file is loaded. This is a load-bearing performance
  decision, not a style preference — see §7.
- **[R3] Set Aggregation** — owns AC2/AC5/AC6(resolved q6)/AC12: computes
  median/min/max across the reference set for every AC1 metric, each
  carrying its own N and the identity of contributing tracks (AC12). Applies
  the three resolved exclusion/subsetting rules: lossy tracks excluded from
  the HF-extension aggregate (source format point 2), HF-extension
  aggregated per sample-rate subset never blended (open question #6), and
  mono tracks excluded from stereo-width/mono-compatibility aggregates
  specifically (Input/output assumptions, mono note). Every exclusion is a
  visible, reason-coded entry in the aggregate output (`excluded: [{track,
  reason}]`), not a silent drop — matching AC12's own "N is not
  optional" framing applied consistently to every subsetting rule in this
  story, not just AC5's.
- **[R4] Suno-Export Comparison** — owns AC3: runs the **identical** [R2]
  path against a Suno-export WAV (STORY-001-scope input, no format
  asymmetry here — Input/output assumptions section is explicit the lossy
  handling is reference-side only) and assembles it alongside the [R3]
  aggregate for direct side-by-side presentation. This is report-assembly
  only, not a new measurement — AC11's code-path-identity requirement is
  what makes "identical" here a checkable claim rather than an assertion
  (§8).
- **[R5] Report Generation** — owns AC9: renders per-track measurements,
  per-set aggregates (with N/contributing-tracks/exclusions), and the
  optional comparison, to both a human-readable Markdown document and a
  versioned-schema JSON document (§9). Every per-track figure carries its
  format-provenance label inline (source format handling point 5) — not
  relegated to a separate table a reader could view out of context.

There is no stage numbering that reuses STORY-001's `[1]`–`[10]` — this is a
deliberately separate top-level pipeline (`reference_analysis.py`), not an
insertion into STORY-001's `pipeline.py`. STORY-001's `pipeline.run()`/
`master()` entry point is untouched.

---

## 2. Library choices

No new heavyweight dependency is required for any measurement. Two new
lightweight dependencies are proposed for format-provenance handling only
(§6); both are optional/best-effort in the sense that their absence
degrades a report field to "unknown," never breaks a run.

| Concern | Library | Rationale |
|---|---|---|
| Integrated LUFS | `pyloudnorm` (existing) | Reused as-is via `analysis/loudness.py`, called against decoded reference-track audio exactly like STORY-001 calls it against a Suno export. |
| True peak (dBTP) | custom `analysis/true_peak.py` (existing) | Reused as-is — same FIR/`upfirdn` oversampling, same tiered ripple envelope and caveats (architecture.md v5 §2/§9 risk #3) apply, now explicitly restated per-track in the reference report (§4). One internal (non-public-behavior) allocation fix in v2 — see §7. |
| Dynamic range (TT DR) | custom `analysis/dynamic_range.py` (existing, **one internal refactor**) | Reused; the block-RMS/2nd-peak algorithm is unchanged. See §5 for the float-exposure refactor (extract-don't-fork). |
| Seven-band + LRA + HF-rolloff + per-band width Welch/CSD machinery | `scipy.signal.welch`, `scipy.signal.csd`, `numpy` | Same tool STORY-001 already uses for its three-band `frequency_balance.py`. LRA's short-term/momentary loudness windows are hand-rolled K-weighted RMS over `pyloudnorm`'s own filter design (§4), not a new PSD technique. |
| Reference-track decode (WAV/FLAC, and MP3 where the runtime supports it) | `soundfile` (existing, libsndfile) | Reused for WAV/FLAC unconditionally. For MP3, gated behind a **runtime capability probe** (`"MP3" in sf.available_formats()`), not a static version assumption — see §6 tier 1. |
| MP3 decode fallback (only if the probe in tier 1 fails) | FFmpeg subprocess, stdout-only PCM pipe (`-f f32le -ac N -`), read via `np.frombuffer` | Fully in-memory, no temp file, matches the project's own "FFmpeg at the I/O boundary only" convention (see role brief). See §6 tier 2 for the full contract and why this is chosen over `pydub`/`audioread`. |
| MP3 bitrate (best-effort) | `mutagen` (**new dependency**, tier-1-only — see §6) or `ffprobe` output already available if tier 2's subprocess path is in use | Tier-dependent, not a flat pick — §6 spells out which applies when. `mutagen` is a pure-Python, no-compiled-extension tag reader; adds negligible install weight for a best-effort field. |
| Aggregation statistics (median/min/max) | `numpy` (`np.median`, `np.min`, `np.max`) | No library gap; standard vectorized numpy over the per-track value arrays. |
| Machine-readable report | stdlib `dataclasses` + `json` (matching STORY-001's `report/render.py` pattern) | No schema-validation library is added for v1 — the versioned-schema requirement (§9) is met by a `schema_version` field plus a documented shape, not by e.g. `pydantic`/`jsonschema` validation. Flagged as a v1 minimalism choice, not a gap — see §11 risk. |

**Deliberate non-use: `pydub` for MP3 decode.** `pydub.AudioSegment.from_file`
(via its ffmpeg codec path) does not stream ffmpeg's stdout in memory — it
invokes ffmpeg to write its decoded output to a `NamedTemporaryFile` on disk
and reads that file back. This is a **harder disqualification than
STORY-001's precision argument**: requirements.md's out-of-scope section is
explicit that "no decoded buffer, temporary WAV, or any other derived audio
artifact from a reference track may be written to disk at any point in the
pipeline, including as an implementation convenience for MP3 decode." `pydub`
violates this structurally, regardless of whether its `audioop`-based
precision concerns (STORY-001's original rejection reason) would otherwise
have been judged acceptable for a read-only lossy decode. It is excluded on
this narrower, harder ground, not re-litigated on the precision one.
`audioread` (already installed, `audioread==3.1.0`) is noted as a
no-new-dependency alternative to the FFmpeg-subprocess tier-2 path: its
`ffdec` backend pipes ffmpeg's stdout rather than temp-filing, satisfying the
no-disk-artifact constraint, but decodes to 16-bit PCM internally — a
precision ceiling acceptable for a lossy source (MP3 itself has no more than
~16-bit-equivalent useful resolution at typical bitrates) but not preferred
over the tier-2 float32 pipe. Use tier-2's direct FFmpeg float32 pipe as the
primary fallback; treat `audioread`'s ffdec path as a documented alternative
if a developer needs to avoid a raw subprocess call for some environment
reason.

---

## 3. Data model — compose, don't extend `Measurements`

**Decision: `Measurements` (analysis/types.py) is not modified.** A new,
separate dataclass wraps it:

```python
@dataclass
class ReferenceMeasurements:
    core: Measurements              # STORY-001's exact shape, unmodified
    dynamic_range_db_exact: float   # unrounded DR, see §5
    lra_lu: LraResult
    seven_band: SevenBandResult
    hf_extension: HfExtensionResult
    per_band_stereo_width: PerBandWidthResult   # None if mono
    mono_sum: MonoSumResult                     # None if mono
    provenance: ProvenanceResult
    label: Optional[str] = None      # forward-compat free-text tag (open q #2)
```

Rationale (this is the single highest-leverage structural decision in this
document, worth stating plainly): if `Measurements` were extended directly
with a dozen new optional fields, three things break that are each avoidable
by composing instead:

1. **STORY-001's own golden-file/report-shape regression tests** (NFR: "No
   regression to STORY-001's existing test suite or report shape") would see
   every existing `Measurements` instance grow new `None`-valued fields —
   `report/render.py`'s `render_json()` calls `dataclasses.asdict(report)`
   directly, so any change to `Measurements`'s shape changes STORY-001's JSON
   output shape, which is exactly the regression the NFR prohibits.
2. **AC11 (code-path identity)** becomes testable *by construction* rather
   than by convention: because `ReferenceMeasurements.core` is produced by
   literally calling the same `analysis/loudness.py`,
   `analysis/true_peak.py`, `analysis/dynamic_range.py` (rounded value),
   `analysis/frequency_balance.py`, and `analysis/stereo_phase.py` functions
   STORY-001's pipeline stage [2] calls, a test can assert
   `reference_measurements.core == story001_stage2_measurements` field-by-
   field for the same WAV input and get a real answer, not an inference from
   "the code looks the same."
3. **The new-vs-reused split stays visually explicit** in the type itself —
   anyone reading `ReferenceMeasurements` sees exactly which fields are
   STORY-001's untouched output (`core`) and which are this story's new
   measurements, mirroring requirements.md's own "Reused as-is / with a
   caveat / genuinely new" structure in the code.

Mirror the same composition pattern for configuration: a new
`ReferenceAnalysisConfig` dataclass in `analysis_config.py` (not
`config.py`) that **wraps** a `MasteringConfig` instance (reusing its
existing frequency-band constants, silence-gate threshold, etc. where they
overlap) and adds this story's new config surface — seven-band edges, LRA
gating parameters, HF-rolloff thresholds, lossless-confidence-N thresholds,
transcode-suspicion thresholds. `MasteringConfig` itself gains **zero new
fields**.

(Implemented shape note, v2: the actual `reference_types.py` names the LRA
field `lra` not `lra_lu`, and adds a `track_path: str` field to
`ReferenceMeasurements` — both harmless, sensible naming/completeness
deltas from this document's illustrative sketch, not flagged as defects.
This document is not updated to match field-for-field; treat the
implementation's dataclass as authoritative for exact field names, this
section as authoritative for the composition *pattern* and rationale.)

---

## 4. Genuinely new measurements — concrete algorithms

Each of these is new logic per requirements.md's own "Genuinely new"
section. Every one is specified here concretely enough that no design
decision is left to the implementer, and every one is built to be testable
against a few seconds of synthetic signal per AC10/§8's testability
discipline.

### 4.1 Loudness range (LRA)

No existing LRA computation exists; `pyloudnorm.Meter` doesn't expose
short-term loudness. Implement directly per EBU Tech 3342 / BS.1770,
**not** by reaching into `pyloudnorm`'s private internals (`Meter._filters`
is not a public API and must not be relied on) — instead, build a small,
independently-verifiable K-weighting + gating primitive in a new
`analysis/loudness_range.py`, cross-checked for correctness against
`pyloudnorm`'s own integrated-loudness output (a free self-consistency
check, see below):

1. **K-weighting**: apply BS.1770's two-stage K-weighting filter (a
   high-shelf + a high-pass biquad, both with published coefficients that
   are sample-rate-dependent) via `scipy.signal.lfilter`. Coefficients
   computed directly from the published BS.1770-4 Annex 1 formulas (the
   same category of "no mature package, implement from spec" gap
   STORY-001's `dynamic_range.py` and `true_peak.py` already accepted) —
   this is the one piece of genuinely new DSP in this story with no
   existing STORY-001 building block, so it gets its own dedicated,
   spec-referenced implementation and its own test fixture.
2. **Short-term loudness**: mean-square power over 3-second overlapping
   windows, **100 ms hop** (per EBU Tech 3342), converted to LUFS
   (`-0.691 + 10*log10(mean_square)` per BS.1770's channel-summed
   convention, matching `pyloudnorm`'s own constant).
3. **Absolute gate**: discard short-term blocks below **-70 LUFS** (same
   absolute gate value as integrated loudness).
4. **Relative gate**: compute the mean of the remaining (post-absolute-gate)
   blocks, then discard any block more than **20 LU below that mean**.
   **This is deliberately -20 LU, not -10 LU** — EBU Tech 3342's relative
   gate for loudness *range* is a wider, looser gate than BS.1770's -10 LU
   *integrated*-loudness relative gate; copying the -10 LU integrated-gate
   value here is the single most common LRA implementation bug and is
   called out explicitly so it isn't silently miscopied from
   `loudness.py`'s neighboring logic.
5. **LRA** = 95th percentile − 10th percentile of the doubly-gated
   short-term values (linear interpolation percentile, `numpy.percentile`
   default).

**Self-consistency check (free correctness signal, not a substitute for
external validation)**: the same K-weighted, 3-second-block machinery,
if instead ungated-and-averaged across the *entire* gated block set exactly
per BS.1770's own algorithm, must reproduce `measure_integrated_lufs()`'s
result on the same buffer to within a tight tolerance (config'd, default
0.1 LU). This doesn't validate LRA's own correctness (a genuinely different
statistic) but does validate that the K-weighting filter and gating logic
are implemented correctly, since integrated LUFS is independently verified
already. Recommend the test-case-writer build this as a dedicated unit
test, separate from the AC10 LRA-tolerance-against-published-material test.

**AC10 verification bar**: verify against EBU Tech 3342's published
reference test signals (the standard ships worked LRA examples for
conformance testing) to a stated tolerance — **default 1.0 LU**, config'd
as `lra_tolerance_lu` in `ReferenceAnalysisConfig`, chosen because EBU
conformance suites themselves generally report tolerances in that range for
LRA (a coarser statistic than integrated LUFS by construction, since it's a
percentile spread rather than a single gated mean). Also add a synthetic
two-level fixture (e.g. 30s at one calibrated level, 30s at a second,
calculable transition) with an analytically-derivable LRA for a
fast/deterministic unit test independent of external reference material.

### 4.2 Seven-band spectral balance

Directly reuses `frequency_balance.py`'s Welch PSD + `_band_power`
machinery — this is a genuine "extend the pattern, not fork the code" case.
New function `analysis/seven_band_balance.py::measure_seven_band_balance()`
imports and calls `frequency_balance._band_power` and a shared
`_welch_nperseg`/PSD-computation helper (promoted out of
`frequency_balance.py` into a small shared utility, `analysis/_psd.py`, so
neither module duplicates Welch-parameter logic — a minor, safe refactor of
STORY-001 code that changes no existing behavior, only extracts a private
helper for reuse; `frequency_balance.py`'s own public function and output
are unchanged).

Band edges (config-driven, per resolved open question #3):

```python
SEVEN_BANDS_HZ = {
    "sub":       (20.0, 60.0),
    "low":       (60.0, 120.0),
    "low_mid":   (120.0, 500.0),
    "mid":       (500.0, 2000.0),
    "high_mid":  (2000.0, 5000.0),
    "high":      (5000.0, 10000.0),
    "air":       (10000.0, None),   # None = Nyquist, resolved per-track at call time
}
```

Each band is reported as measured relative-dB (relative to the same
500 Hz–2 kHz reference band both schemes already share, per resolved open
question #3's alignment note) — **no threshold/flag logic** is attached
here, since this scheme is descriptive/comparison-only (resolved open
question #4: runs alongside, never triggers correction). The `air` band's
upper edge is resolved to the track's own Nyquist at measurement time
(`sr / 2`), not hardcoded — this is also why the aggregate for this band
specifically (like HF-extension) should be read with the same sample-rate-
comparability caution as §4.3, though the resolved open question set only
mandates per-sample-rate subsetting for HF-*extension* specifically, not for
seven-band energy. See §7 "Air band aggregation" for why energy (a ratio)
tolerates this where a rolloff frequency doesn't, and why no further
subsetting is added for `air` band-energy aggregation beyond what AC12
already requires (visible N).

### 4.3 HF extension / rolloff detection, with stability check

New `analysis/hf_extension.py`. Algorithm:

1. Split the track into `config.hf_stability_segment_count` (default 5)
   roughly-equal-duration, non-overlapping segments (skip the analysis
   entirely, report "insufficient duration," for tracks shorter than
   `config.hf_min_duration_s`, default 30s, since 5 segments of a very
   short track would each be too short for a stable PSD estimate).
2. Per segment: compute a Welch PSD (reusing the same `analysis/_psd.py`
   helper as §4.2), anchor a reference level on the same 500 Hz–2 kHz band
   average used by both the three-band and seven-band schemes (keeps this
   measurement's baseline consistent with everything else in the report,
   not a third independent reference convention).
3. **Rolloff point** = the highest frequency, scanning downward from
   Nyquist, at which the PSD first rises back above
   `reference_db - config.hf_rolloff_threshold_db` (default **-6 dB**
   relative — resolved as the architect's own numeric call per AC10's
   "the tolerance value itself is for the architect/QA to set," chosen as
   the conventional "-6 dB point" used in audio-bandwidth-limiting
   discussions generally, distinct from and not to be confused with the
   3-band/7-band scheme's own flag thresholds). Implemented as a downward
   scan from the top bin rather than an upward scan from DC, since rolloff
   is specifically about where high-frequency content *stops*, and a
   downward scan is robust to a single noisy bin below the real knee.
4. **Stability check**: rolloff point computed per-segment; the track's
   reported HF-extension value is the **median** of the per-segment
   rolloff points, and a `stable: bool` field is set true iff the spread
   (max − min of per-segment rolloff points) is within
   `config.hf_stability_tolerance_hz` (default 2000 Hz) — an unstable
   rolloff (e.g. a track with an intro/outro that fades differently in the
   top end, or an edit) is reported with `stable=False` rather than
   silently averaged into a misleading single figure.
5. **AC10 verification bar**: a synthetic band-limited signal (white/pink
   noise lowpassed at a known, deliberately engineered cutoff via
   `scipy.signal.butter` + `sosfiltfilt`, high order for a steep, clean
   knee) with the detector required to recover that cutoff to within
   `config.hf_rolloff_test_tolerance_hz` (default 500 Hz, config'd
   separately from the stability tolerance above since they answer
   different questions — one is "how precise is the detector," the other
   is "how consistent is the measurement across segments of the same real
   track").

**Transcode-suspicion logic (source-format point 6)**: a lossless-container
file is flagged `suspected_transcode: True` when **all three** hold (per
requirements.md's explicit "corroborating evidence, not certain proof" —
all three, not any one, to avoid over-flagging a legitimately
band-limited master):
- rolloff point falls within `config.transcode_suspect_bands_hz` (default
  `[(15500, 16500), (18500, 19500), (19500, 20500)]` — the 16/19/20 kHz-class
  encoder-typical cutoffs named in requirements.md), and
- the knee is steep: PSD drops by at least
  `config.transcode_suspect_slope_db_per_octave` (default 24 dB/octave,
  consistent with a typical lossy-encoder brickwall/near-brickwall lowpass,
  well beyond what a musical mix's natural rolloff usually produces) between
  the rolloff point and one octave above it, and
- `stable=True` (a steep, encoder-typical knee that is *also* stable across
  the whole track is corroborating; an unstable one is more likely a mix
  artifact than an encoder cutoff and should not compound the suspicion
  score).

Flagged, never auto-excluded, per resolved open question #10 — the flag is
a boolean field plus a human-readable reason string on the per-track
provenance result, surfaced prominently in both report renderings.

### 4.4 Per-band stereo width

New `analysis/per_band_stereo_width.py`. Does **not** build a filter bank
(the advisor review flagged this as unnecessary complexity, and it is
right: a filter-bank design would need its own coefficient-design
justification, exactly the kind of new DSP surface this story should avoid
where a cheaper equivalent exists). Instead, per seven-band-scheme band,
compute a frequency-domain coherence-style estimate directly from Welch/CSD
outputs:

```
S_LL, S_RR   = welch(L), welch(R)             # PSDs
S_LR         = csd(L, R)                       # complex cross-spectral density
band_width[band] = 1 - |Re{∫_band S_LR}| / sqrt(∫_band S_LL · ∫_band S_RR)
```

(0 = fully correlated/mono in that band, approaching 1 = fully decorrelated
— expressed this way, rather than as a raw correlation number, so "low
band near 0, top band higher" reads directly as the expected genre-typical
shape a producer would recognize.) This reuses the same band-power
integration pattern as `_band_power` (§4.2) — `∫_band S_LL` etc. is exactly
`_band_power(freqs, S_LL, band_hz)`. Correlation (real part of normalized
cross-spectrum) is used rather than raw magnitude coherence specifically so
a band that's out-of-phase-and-decorrelated is not conflated with one
that's merely quiet in both channels.

**Stated caveat** (must appear in the report, not just this document): this
is a magnitude/frequency-domain estimate of per-band width, not the
time-domain per-band correlation of literally band-filtered L/R signals —
cheaper, no filter design needed, but answers a very slightly different
question (energy-weighted spectral coherence vs. band-filtered time-domain
correlation). For this story's descriptive/comparison purpose (not
corrective, per requirements.md's explicit scope) this distinction does not
change the practical reading, but it must not be silently presented as
identical to `stereo_phase.py`'s broadband time-domain correlation figure.

**AC10 verification bar**: synthetic signal with mono low band (identical
L=R content below, say, 200 Hz) and fully decorrelated high band
(independent noise above, say, 5 kHz), asserting the low-band width reads
near 0 and the high-band width reads near 1 to a stated tolerance (default
0.1, config'd).

### 4.5 Mono-sum level change + band-specific cancellation

**v2 rewrite — DEF-101 resolution.** v1's worked example ("a
perfectly-correlated signal reads ~0 dB change... as expected") was
mathematically wrong for the formula this section itself specified, and
that error propagated into the shipped `excess_cancellation_db` field's
reference baseline and (more seriously) into the per-band cancellation
flag's threshold, which as first implemented **false-positives on
ordinary, healthy decorrelated wide-stereo material** — confirmed against
the actual `analysis/mono_sum.py` v1 code during this v2 pass, not merely
asserted. This subsection is now the authoritative specification,
superseding v1's prose entirely; the underlying `level_change_db` and
per-band `delta_db` formulas python-developer implemented in v1 are
**numerically correct as written and need no change** — only the two
*derived*, threshold-facing fields built on top of them do.

**Root cause: two different formulas, two different ρ=0 floors, previously
conflated as if they shared one "expected -3 dB" intuition.** Let ρ be the
per-band (or broadband) correlation coefficient between L and R,
`Re{S_LR}/sqrt(S_LL·S_RR)`, for equal per-channel power P:

- **Broadband `level_change_db`** divides the mono-sum's single-channel
  mean-square power against BS.1770's channel-*summed* stereo power
  (`P_L + P_R`, two full channels added, no cross term):
  `mono-sum power = P(1+ρ)/2`, `stereo power = 2P`, so
  `level_change_db = 10·log10((1+ρ)/4)`.
- **Per-band `delta_db`** divides the mono-sum's band power against the
  **mean** (not summed) of the two channels' own band power:
  `channel-mean power = P`, so `delta_db = 10·log10((1+ρ)/2)` — offset by
  exactly +3.01 dB from the broadband formula at every ρ.

| ρ | broadband `level_change_db` | per-band `delta_db` |
|---|---|---|
| +1 (fully correlated / mono-like) | **-3.0103 dB** | **0 dB** |
| 0 (fully decorrelated — ordinary healthy wide stereo) | **-6.0206 dB** | **-3.0103 dB** |
| -1 (fully anti-correlated / cancelling) | -inf | -inf |

(The `-3.0103 dB` broadband figure at ρ=+1 is exactly what python-developer
measured empirically for an L=R pair in defects.md DEF-101 — `10*log10(0.5)`
— and is **correct**, confirming `level_change_db`'s formula was never the
bug. The bug is that v1 also used this same `-3.0103` number as the
reference floor for `excess_cancellation_db` *and* for the per-band
threshold comparison, when — per the table above — `-3.0103` is actually
the per-band ρ=0 floor, not the broadband one, and is not any per-band ρ=+1
value at all. Conflating the two is exactly how a threshold tuned against
one formula's floor ends up firing on the other formula's ordinary,
healthy-material output.)

**The fix: reference each field's threshold to its own ρ=0 (fully
decorrelated) floor, not to the ρ=+1 (correlated) case.** ρ=0 is *ordinary,
healthy* wide-stereo material — independent, roughly-equal-power content in
both channels, with no phase relationship at all. It is the correct
"nothing wrong here" anchor for a cancellation detector, because genuine
destructive interference requires ρ<0, and only a floor set at ρ=0 makes
"below the floor" synonymous with "some genuine anti-correlation is
present," for *either* formula, independent of how wide/mono-like the
otherwise-healthy material is:

```python
_BROADBAND_DECORRELATED_FLOOR_DB = 10.0 * math.log10(0.25)  # -6.0206 dB (rho=0)
_PERBAND_DECORRELATED_FLOOR_DB   = 10.0 * math.log10(0.5)   # -3.0103 dB (rho=0)
```

- **Level change (dB, broadband)** — `level_change_db = LUFS(mono_sum) -
  LUFS(stereo_original)`, `mono_sum = (L+R)/2`. **Unchanged from v1.**
  `excess_cancellation_db = level_change_db - _BROADBAND_DECORRELATED_FLOOR_DB`
  (**changed from v1's incorrect `-3.0103` reference to the correct
  `-6.0206`**). Now: ordinary decorrelated wide stereo (ρ≈0) reads
  `excess_cancellation_db ≈ 0`; correlated/mono-like material (ρ≈+1) reads
  `≈ +3.01` (positive — further from the cancellation floor than even
  ordinary wide stereo, which is right: correlated material carries no
  cancellation risk at all); only genuine anti-correlation (ρ<0) reads
  negative. Informational field only — no automatic flag is attached to it
  in this story (matching v1's scope).
- **Band-specific cancellation** — `delta_db` (mono-sum band power vs.
  per-channel-mean band power, in dB) is **unchanged from v1**. **New
  field**, `excess_delta_db = delta_db - _PERBAND_DECORRELATED_FLOOR_DB`,
  added to `BandCancellation`. The cancellation flag changes from v1's raw
  comparison (`delta_db < config.mono_cancellation_threshold_db`, which
  fires on ordinary decorrelated content — confirmed false-positive, since
  `-3.0103 < -3.0` is true for essentially any healthy wide band) to
  **`excess_delta_db < config.mono_band_cancellation_excess_db`**. The
  config field is **renamed** (`mono_cancellation_threshold_db` →
  `mono_band_cancellation_excess_db`) deliberately, so the semantic change
  from "a raw dB reading" to "excess beyond the decorrelated floor" cannot
  be silently misread as the same knob at every call site. Default value
  **-3.0** (the number is unchanged; only its meaning is corrected): a band
  now flags only when `delta_db < -6.0206` dB, i.e. only when ρ < -0.5 for
  that band — a defensible "meaningfully anti-correlated, not merely
  decorrelated" bar. `BandCancellation.cancellation` and
  `MonoSumResult.any_cancellation`'s meanings are otherwise unchanged.

**What this changes in the shipped code (concrete, for python-developer)**:
1. `analysis/mono_sum.py`: rename/redefine `_CORRELATED_SUM_BASELINE_DB` to
   `_BROADBAND_DECORRELATED_FLOOR_DB = 10.0 * math.log10(0.25)`; add
   `_PERBAND_DECORRELATED_FLOOR_DB = 10.0 * math.log10(0.5)`; update
   `excess_cancellation_db`'s computation to use the broadband floor; add
   `excess_delta_db` computation per band and change the `cancellation`
   comparison to use it against the renamed config field; replace the v1
   module docstring's "DEVIATION NOTE" with a pointer to this section and
   defects.md's DEF-101 resolution.
2. `analysis/reference_types.py`: add `excess_delta_db: float` to
   `BandCancellation`; update `MonoSumResult`'s field-comment for
   `excess_cancellation_db` to reflect the corrected `-6.0206` floor.
3. `reference_analysis/config.py`: rename `mono_cancellation_threshold_db`
   to `mono_band_cancellation_excess_db` (default unchanged, `-3.0`);
   update `report/reference_builder.py`'s reference to the renamed field.
4. Re-run/extend the existing mono-sum unit test(s): the out-of-phase
   1 kHz fixture (L=+sin, R=-sin, small decorrelated noise floor) reported
   in defects.md (`level_change_db=-49.44 dB`, old
   `excess_cancellation_db=-46.43 dB`) should now read
   `excess_cancellation_db ≈ -43.42 dB` (referenced to `-6.0206` instead of
   `-3.0103`) — still large and clearly cancellation-driven, just against
   the corrected floor. **Add a new fixture the v1 test suite did not
   have**: an ordinary decorrelated stereo pair (independent noise in L and
   R, equal power, no phase relationship) must assert
   `excess_cancellation_db ≈ 0` and every band's `cancellation == False` —
   this is the direct regression test for the false-positive DEF-101 found,
   and its absence in v1's test coverage is exactly how the bug shipped
   undetected.

**AC10 verification bar (updated)**: the out-of-phase synthetic fixture
above remains the primary cancellation-detection test; add the ordinary-
decorrelated-stereo fixture as a required companion (asserting *no*
cancellation is flagged) so AC10 coverage includes both the true-positive
and the false-positive-guard case.

---

## 5. `dynamic_range.py`'s float-exposure change — extract, don't fork

**Decision**: `measure_dynamic_range()`'s public signature and return value
(the rounded float, e.g. `9.0` for "DR9") are **unchanged** — this is a hard
non-regression requirement (STORY-001's existing tests and call sites, e.g.
the solver in `mastering/loudness_limit.py`, depend on the rounded
convention and must not need to change).

The internal body of `measure_dynamic_range()` (currently: compute
per-channel DR via `_channel_dr`, average, round) is refactored into a new
private helper, `_measure_dynamic_range_unrounded(audio, sr, config) ->
float`, which does everything up to and *excluding* the final
`math.floor(dr + 0.5)` rounding step. `measure_dynamic_range()` becomes a
one-line wrapper: `return float(math.floor(_measure_dynamic_range_unrounded(audio, sr, config) + 0.5))`.

STORY-002's reference-analysis path calls `_measure_dynamic_range_unrounded()`
directly for `ReferenceMeasurements.dynamic_range_db_exact`, and separately
calls the unchanged public `measure_dynamic_range()` for
`ReferenceMeasurements.core.dynamic_range_db` (the rounded, display-
convention value STORY-001's `Measurements` shape already expects) — **one
computation** underneath (both paths call `_channel_dr` identically), not a
forked calculation. This satisfies AC11's code-path-identity requirement for
DR specifically (the rounded value in `core` is produced by literally the
same function STORY-001's stage [2] calls) while resolving the aggregation-
precision caveat (exact float available for median/min/max, per requirements
.md's own "too coarse to usefully describe the territory the set occupies"
complaint about integer-only aggregation).

This is the only change to any existing STORY-001 `analysis/*` file's
*public* behavior in this story — every other existing function
(`measure_integrated_lufs`, `measure_true_peak`, `measure_frequency_balance`,
`analyze_stereo_phase`) is called with zero modification to its public
contract. (v2 note: §7 below authorizes one further *internal*,
output-preserving allocation fix inside `true_peak.py`/`clipping.py` —
DEF-103 — which is a memory optimization, not a public-behavior change; see
§7 for why it does not violate this "zero modification" framing.) The one
`frequency_balance.py` internal refactor noted in §4.2 (promoting Welch/PSD
helper logic to a shared `analysis/_psd.py`) is also a pure extraction with
no behavior change to `frequency_balance.py`'s existing public function or
output.

---

## 6. Reference-track ingest — a separate, lighter-weight read path

**Decision: `io/reference_ingest.py` is a new module, not a modified
`io/ingest.py`.** Concrete reasons, each already surfaced by requirements.md
and confirmed against the actual `ingest.py` source:

- `ingest()`'s `_SUPPORTED_SUBTYPES` whitelist (`PCM_16`, `PCM_24`, `PCM_32`,
  `FLOAT`, `DOUBLE`) would **reject** an MP3 file outright (libsndfile
  reports MP3 content's subtype as `MPEG_LAYER_III`, not in that set), while
  a FLAC file would pass through the subtype check today (libsndfile
  natively reads FLAC) but drag along `_validate_data_chunk_not_truncated()`
  (a RIFF-specific parser that's meaningless for a FLAC/Ogg-style container)
  and `extract_preserved_chunks()` (an export-oriented BWF/metadata
  preservation layer this read-only story has no use for and no obligation
  to keep working for non-WAV input).
- Reusing `ingest()` unmodified for reference input risks exactly the
  failure mode requirements.md names: `extract_preserved_chunks` choking on
  a non-RIFF file, or dead code being carried along for no reason.
- Per the "given this story's important, but concretely narrower, need for
  code-path fidelity" requirement, the split is scoped precisely: the
  **file-reading layer** (chunk preservation, truncation checks, WAV-specific
  error types) may differ; the **measurement functions** must not.

`io/reference_ingest.py` contract:

```python
@dataclass
class ReferenceIngestResult:
    audio: np.ndarray            # float64, (samples,) mono or (samples, 2) stereo
    sample_rate: int
    channels: int
    duration_seconds: float
    input_hash: str
    input_path: str
    provenance: ProvenanceResult  # container/lossless-lossy/bitrate/decoder id


def ingest_reference_track(path: str, config: ReferenceAnalysisConfig) -> ReferenceIngestResult: ...
```

**AC11 trap, stated explicitly so it isn't silently mis-implemented**: for
this function's output to be usable as an input to the *identical*
`analysis/*` functions STORY-001's stage [2] calls, it must replicate
`ingest.py`'s exact array-shape convention — `sf.read(dtype="float64",
always_2d=True)` followed by squeezing to 1-D for genuinely mono content
(`audio = audio[:, 0]` when `channels == 1`). `dynamic_range.py`,
`stereo_phase.py`, and `frequency_balance.py`'s `_to_mono` all branch on
`audio.ndim`, so a shape mismatch between the two ingest paths would
silently produce *different* measurement values for the same underlying
audio content, breaking AC11 in a way that would not raise an exception —
it would just quietly disagree. This is called out explicitly as the
single most likely place to introduce an AC11 regression.

### Decode tiering (WAV/FLAC/MP3)

**Tier 0 — WAV/FLAC**: `soundfile.read()`, identical call shape to
`ingest.py`'s own read call (no truncation check, no chunk extraction). No
open question here — libsndfile's FLAC support is long-standing and stable.

**Tier 1 — MP3, if the runtime supports it**: gate behind a **runtime
capability probe**, `"MP3" in soundfile.available_formats()`, evaluated
once at module import or at the start of a run (and logged into the
machine-readable report's decoder-identity field, §7). If present,
`sf.read(path, dtype="float64", always_2d=True)` handles MP3 through the
exact same call as WAV/FLAC — no subprocess, no temp file, and `sf.info()`
gives `format`/`subtype` for the provenance record in the same code path.
This resolves the "verify against the actual installed environment, not
assumed either way" instruction by converting an unverifiable-at-
architecture-time fact into a documented, testable runtime branch rather
than a guess. (The project's installed `soundfile==0.14.0` most likely
bundles a libsndfile build recent enough to include MP3 read support, added
upstream in libsndfile 1.1.0, but this document does not assert that as
fact — the probe is the actual answer, and python-developer/QA should log
which branch a given environment takes.)

**Tier 2 — MP3, if the tier-1 probe fails**: decode via an FFmpeg
subprocess writing raw PCM to **stdout only**, never to a file:

```
ffmpeg -i <path> -f f32le -ac <channels> -ar <native_rate> -
```

read via `np.frombuffer(proc.stdout_bytes, dtype="<f4").reshape(-1, channels)`,
then up-cast to float64. This is fully in-memory (no `NamedTemporaryFile`,
no intermediate WAV) and matches the house convention of using FFmpeg only
at the format I/O boundary, never mid-pipeline. `<native_rate>` is queried
first via `ffprobe -show_streams` (also stdout-only, no file writes) so the
decode does not force an unwanted resample — this story has no resample
stage and must not introduce one as a decode side-effect. The decode
function's signature must make "never receives a writable path" a
structural property: it takes only `path: str` (read) and returns an
in-memory array; there is no output-path parameter anywhere in tier 2's
call chain, so "no derived artifact on disk" is enforceable by code review/
static inspection, not just by promise — and QA can assert it empirically
by snapshotting the temp directory's contents before/after a tier-2 decode
run.

`audioread` (already installed, no new dependency) is noted as an
alternative to a raw `subprocess` call for tier 2: its `ffdec` backend also
pipes ffmpeg's stdout rather than temp-filing, satisfying the same
no-disk-artifact constraint, at the cost of an internal 16-bit-PCM decode
ceiling (see §2's non-use note on `pydub` for why 16-bit is judged
acceptable specifically for an already-lossy MP3 source, unlike STORY-001's
precision-critical mastering path). Either implementation satisfies this
architecture's constraint; the raw-subprocess float32 pipe is the
recommended default for the extra precision headroom at negligible extra
implementation cost.

### MP3 bitrate (best-effort, resolved open question #9)

Coupled to which decode tier is active, not a flat library pick:

- **If tier 2 (FFmpeg subprocess) is in use**: `ffprobe`'s own JSON output
  (already being invoked for the native-rate query above) includes a
  `bit_rate` field for most MP3s — read it from the same subprocess call,
  no additional dependency needed.
- **If tier 1 (libsndfile direct read) is in use**: libsndfile does not
  expose source bitrate through `soundfile`. Add `mutagen` (**new
  dependency**, not currently in `requirements.txt` — flagged explicitly)
  as a dedicated, pure-Python ID3/MP3-frame-header tag reader used *only*
  for this one field. `mutagen.mp3.MP3(path).info.bitrate` gives an average
  bitrate for CBR and a computed average for many VBR files; where it
  cannot produce a clean value (e.g. a VBR file with no reliable
  Xing/VBRI header), the field is reported as `"bitrate unknown"` per the
  resolved best-effort posture — never fabricated, never a blocking error.

### Format/provenance detection

```python
@dataclass
class ProvenanceResult:
    container: str              # "wav" | "flac" | "mp3"
    lossless: bool               # container-declared, not corroborated
    bitrate_kbps: Optional[int]  # None => "bitrate unknown"
    decoder: str                 # e.g. "libsndfile-<version>" | "ffmpeg-<version>"
    suspected_transcode: bool    # see §4.3 — corroborated by HF-rolloff shape
    suspected_transcode_reason: Optional[str]
```

Container-declared `lossless` is `True` for WAV/FLAC, `False` for MP3 — this
is the point-1/point-2 mechanical detection requirements.md asks for.
`suspected_transcode` is populated later, after §4.3's HF-rolloff analysis
runs (it is a corroborated, not a purely container-level, signal) — the
`ProvenanceResult` object is constructed in [R1] with `suspected_transcode`
left `False`/pending and updated once [R2]'s HF-extension measurement
completes for that track, within the same per-track analysis step (not a
second pass over the file).

---

## 7. Data flow, memory, and the whole-set time budget

**Sequential, single-track-in-memory-at-a-time, no intermediate files** —
same "in-memory, no streaming needed" posture as STORY-001 (architecture.md
v5 §3), but with one addition specific to processing a *set* rather than one
file: **a track's audio buffer, and specifically `true_peak.py`'s
`TruePeakResult.oversampled` buffer, must be released before the next
track is loaded.**

This is not a style preference — it is a binding memory constraint inherited
directly from STORY-001's own unresolved §9 risk #8 benchmark, now made
load-bearing by this story's batch nature: STORY-001 measured ~1.1s per
true-peak call on a 60-second stereo buffer at the default 8x oversample
factor; a 7-minute reference track is roughly 7x that duration, and
`TruePeakResult` **retains** the full oversampled buffer (8x the sample
count, both channels, float64) for reuse by `clipping.py`. For a 7-minute
stereo track at 44.1 kHz, 8x oversampled float64 is on the order of
**~2.4 GB** for that one buffer alone. Holding six such buffers in memory
simultaneously (a 6-track reference set processed non-sequentially, or with
results accumulated before being summarized) is untenable on "typical
consumer hardware," the same standard STORY-001 held itself to.

Concretely: `ReferenceMeasurements` construction for each track must **not**
retain `TruePeakResult.oversampled` past the point where `measure_true_peak`
returns its `.dbtp` value — this story's AC1 has no clipping/inter-sample-
over line item (unlike STORY-001's six-criterion set), so there is no
downstream consumer for that buffer here at all; discard it immediately
(`del result.oversampled` or simply extract `.dbtp` and let the
`TruePeakResult` object go out of scope) rather than plumbing it through to
the per-track report object. Do **not** lower the oversample factor or
chunk the true-peak call to save memory — either would break AC11's
code-path-identity requirement (the reference measurement must use the same
`config.true_peak_oversample_factor` STORY-001's stage [2] uses for the same
metric on the same file).

### 7.1 Memory — v2 correction (DEF-103 resolution)

**What v1 missed, confirmed against the actual code this pass**: the ~2.4 GB
figure above accounts only for `TruePeakResult.oversampled` itself. It does
not account for two *further* full-size temporary allocations that occur
**inside** `analysis.measure_all()` (STORY-001's own unmodified stage-[2]
function, which `[R2]` calls verbatim for AC11 reasons) before that buffer
is released:

1. `true_peak.py`'s own peak-search line, `np.max(np.abs(scan_region))`,
   allocates a full-size float64 **copy** of the (already ~2.4 GB) scan
   region via `np.abs()` before reducing it to a scalar.
2. `clipping.py`'s `detect_clipping()` — called by `measure_all()`
   immediately afterward, reusing the same `TruePeakResult` — does
   `np.abs(tp_result.oversampled) > 1.0`, which likewise allocates a second
   full-size float64 **copy** via `np.abs()` before the boolean comparison,
   in addition to the boolean result array itself.

Measured peak Python-heap memory (`tracemalloc`) for a single
`measure_all()` call on a synthetic 7-minute stereo 44.1 kHz track was
reported at **~5.5 GB**, consistent with these two extra float64-sized
copies stacking transiently on top of the original ~2.4 GB buffer before
either is freed.

**Resolution: fix both allocations, not the documented number.** Both are
internal, output-preserving rewrites — neither changes `measure_all()`'s
public return value for any input, including edge cases (NaN, exactly
±1.0), so neither touches AC11's code-path-identity guarantee or requires
any change to `[R2]`'s call contract. This is judged the right call over
either "accept 5.5 GB" or "skip clipping detection for reference tracks"
(both product/architecture trade-offs this document should not need to
make when a strictly-better, behavior-preserving fix is available):

1. **`true_peak.py`**, peak-search line: replace
   `float(np.max(np.abs(scan_region)))` with
   `float(max(scan_region.max(), -scan_region.min()))` — mathematically
   identical for real-valued arrays (`max(abs(x))` over a real array equals
   `max(max(x), -min(x))`), and allocates no new array; `scan_region.max()`
   and `.min()` are in-place reductions.
2. **`clipping.py`**, inter-sample-over line: replace
   `np.abs(tp_result.oversampled) > 1.0` with
   `(tp_result.oversampled > 1.0) | (tp_result.oversampled < -1.0)` —
   identical boolean output for every finite value and for NaN
   (`abs(nan) > 1` is `False`; `nan > 1 | nan < -1` is also `False`), and
   replaces one full-size float64 copy with two full-size boolean
   temporaries (each ~1/8th the byte size of the float64 array they
   replace) plus the OR result.

After both fixes, expected peak per track is approximately the original
~2.4 GB buffer plus ~0.3–0.9 GB of boolean temporaries — **roughly 2.7–3.3
GB**, materially closer to (if still somewhat above) the v1 estimate, and
well below the measured 5.5 GB. This is stated as a corrected *estimate*,
not a re-measured fact — re-running `tracemalloc` against the fixed code is
the concrete next step, called out in the revision history (§15) as a
follow-up for python-developer to confirm before this figure is treated as
settled.

**Scope note**: this touches two lines inside STORY-001's own
`analysis/true_peak.py` and `analysis/clipping.py` — files STORY-002 was
otherwise told not to modify beyond the one `dynamic_range.py`/
`frequency_balance.py` extractions already authorized in §4.2/§5. This is
authorized here as a third, narrowly-scoped exception, on the same
"extract/optimize, don't fork, no public-behavior change" basis as those
two. **STORY-001's own clipping/true-peak regression tests and golden-file
tests must be re-run against both fixes** before this is considered closed
— confirming bit-identical output (dBTP values, clip counts, severity
buckets, inter-sample-over counts) across STORY-001's existing fixture set,
not just STORY-002's new ones.

**Per-track speed budget (resolved, per NFR)**: seconds, not minutes — a
materially tighter bar than STORY-001's 5-minute-per-track budget, stated
explicitly as a *change*, not an inheritance, since this story runs
analysis-only (no EQ/limiting/dither/export stages, and critically no
solver — STORY-001's dozens-of-calls-per-run true-peak/DR/LUFS iteration
loop does not exist here; each metric is computed **once** per track). This
materially changes the arithmetic against STORY-001's own benchmark note:
where STORY-001's 5-minute budget had to absorb dozens of true-peak calls
from the solver, this story makes exactly one true-peak call (plus one per
new per-band-width/HF-rolloff-segment sub-computation, all Welch-based and
cheap relative to FIR oversampling) per track.

### 7.2 Whole-set time budget — v2 correction (DEF-102 resolution)

**v1's "under two minutes for 7 tracks" target is revised upward, based on
real measurement rather than extrapolation.** python-developer's
implementation pass, after fixing a genuine LRA-windowing performance bug
(an O(n²)-shaped explicit-array construction that has since been replaced
with an O(n) cumulative-sum sliding-window computation — a real
implementation fix, correctly resolved in v1's implementation pass and not
revisited here), measured a **33.3 s** `analyze_track()` call on a
synthetic **7-minute stereo 44.1 kHz** fixture, with this per-stage
breakdown:

```
measure_all (STORY-001's stage [2], unmodified, incl. clipping.py):  16.39 s
_measure_dynamic_range_unrounded:                                     0.19 s
measure_loudness_range (LRA):                                         3.03 s
measure_seven_band_balance:                                           1.80 s
measure_hf_extension (5 segments + 1 whole-track slope check):        1.53 s
measure_per_band_stereo_width (welch x2 + csd x1, 7 bands):           5.17 s
measure_mono_sum (welch x3, 7 bands):                                 6.12 s
```

**Why v1's target was unachievable by construction, not just by
implementation quality**: `measure_all` alone — STORY-001's own unmodified
code, which AC11 explicitly forbids optimizing here (no lowering the
true-peak oversample factor, no chunking) — costs 16.39 s/track on this
fixture. Seven tracks through `measure_all` alone is `7 × 16.39s ≈ 1.9
minutes`, consumed entirely by the reused STORY-001 path *before* any of
this story's five new measurements run. v1's "under two minutes for 7
tracks" target left essentially no room for the ~17 s/track the five new
measurements add on top, once real fixture timing existed to check the
extrapolation against. This reframes the finding: it is not that the new
code is too slow, it is that the v1 budget number was set before the reused
`measure_all` cost was known precisely enough to leave headroom for it.

**Revised target: under 5 minutes for a 7-track set of 7-minute-average-
duration tracks.** This states the workload assumption explicitly, since a
bare time figure is meaningless without it: `33.3 s/track × 7 tracks ≈ 3.9
minutes`, and 5 minutes gives roughly 25% headroom over that measured
figure for slower hardware or less favorable fixture content. **For more
realistic reference material** — most reference tracks in practice run
3–4 minutes, not 7 — the per-track cost scales down roughly proportionally
with duration for every stage in the table above (all are O(duration) or
O(duration·log(duration)) computations, no fixed per-track overhead
dominates), extrapolating to roughly **~20 s/track, ~2.3 minutes for a
7-track set** — comfortably inside even v1's original 2-minute target for
realistically-sized reference material. Both figures are stated so the
5-minute number is not read as a pessimistic general expectation: it is a
worst-case bound for unusually long reference tracks, not the typical case.

**No code change required for this resolution** — this is a documentation/
target correction. Reducing PSD fidelity, Welch window size, or the number
of independent Welch/CSD calls to force the number down further would be
exactly the kind of undocumented workaround this project's standing
convention prohibits, especially now that the true bottleneck (AC11-frozen
`measure_all`, not the new measurements) is identified precisely rather
than guessed at.

**Optional, non-blocking follow-up, explicitly not required for this
story**: five of the new measurement modules (`seven_band_balance.py`,
`hf_extension.py`, `per_band_stereo_width.py`, `mono_sum.py`) each
independently call `scipy.signal.welch`/`csd` over the full track via the
shared `_psd.py` helper, rather than sharing one PSD computation per track.
A shared per-track PSD cache in `reference_analysis/pipeline.py` could
reduce the ~17 s/track these five modules collectively cost, but its
**ceiling benefit is bounded by that same ~17 s/track** (it cannot touch
the AC11-frozen 16.39 s `measure_all` cost, which is roughly half the
total either way) — at best this buys back something under 2 minutes off
the 7-track/7-minute worst case, not a multiple-x speedup. Given the
revised 5-minute budget is already met with headroom, and realistic-length
reference material already lands near 2.3 minutes, this is left as an
optional future performance pass, not authorized or required here. If
pursued later, it would change each of the four modules' independently-
testable "plain array in, typed result out" contract (§12's testability
requirement) and should get its own explicit architectural review at that
time, per python-developer's own correct instinct not to make that call
unilaterally under a budget document that was, at the time, unconfirmed.
**Note (v3, DEF-110): this cache is explicitly irrelevant to STORY-001's
own `test_tc150`/DEF-110 — `pipeline.master()` never calls any of
STORY-002's new measurement modules, so a PSD cache inside
`reference_analysis/` cannot affect that test's timing in any way. Closed
off as an option for DEF-110 specifically; see §16.**

**One unreadable file must not abort the set.** [R1]'s per-file try/except
records a failure entry (path, exception message) in the run's output and
the loop continues to the next file — the folder-of-files batch nature of
AC1, combined with this story's best-effort posture on bitrate/provenance
detection elsewhere, implies the same tolerance at the file-discovery level.
This is an architecture-level inference (not a number requirements.md
states), flagged as such rather than silently assumed, but it changes no
acceptance criterion — a failed file is absent from the aggregate (visible
via N, same as any other exclusion) rather than crashing the whole report.

**Air-band aggregation vs. HF-extension aggregation — why the two differ**:
requirements.md's resolved open question #6 mandates per-sample-rate
subsetting specifically for HF-*extension* (a **frequency** — 19 kHz vs.
20.7 kHz are not comparable numbers across sample rates approaching their
respective Nyquist limits). The seven-band `air` band's measurement, by
contrast, is a **relative-energy ratio** (dB relative to the 500 Hz–2 kHz
band), not a frequency — a 44.1 kHz track's air-band energy ratio and a
48 kHz track's air-band energy ratio both describe "how much energy sits in
the top part of the spectrum relative to the midrange," a comparable
question even though the two tracks' `air` bands span slightly different
absolute ranges (10 kHz–22.05 kHz vs. 10 kHz–24 kHz). The extra ~1.95 kHz at
the very top of a 48 kHz track's `air` band is a small fraction of that
band's own ~2-octave span and is not expected to meaningfully bias an energy
ratio the way it would bias a rolloff-point comparison. **This is a
judgment call, stated explicitly rather than silently decided**: no further
per-sample-rate subsetting is added for `air`-band energy aggregation beyond
AC12's blanket N-visibility requirement. If QA's eventual real-reference-set
testing shows the two sample-rate populations' `air`-band figures diverge
enough to be misleading when blended, the fix is the same pattern already
built for HF-extension (subset per sample rate) — flagged here as the first
place to look if that turns out to matter, not implemented preemptively
without evidence it's needed.

---

## 8. Code-path identity (AC11) — what "identical" concretely guarantees

AC11 requires that for any given WAV file, STORY-002's measurements be
bit-identical (or identical within floating-point noise appropriate to the
metric) to what STORY-001's stage [2] would produce, for every shared
metric. Concretely, this is guaranteed by construction, not by convention,
via:

1. **Same functions, same signatures, same config values.** `[R2]` calls
   `analysis.loudness.measure_integrated_lufs`,
   `analysis.true_peak.measure_true_peak`,
   `analysis.dynamic_range.measure_dynamic_range`,
   `analysis.frequency_balance.measure_frequency_balance`, and
   `analysis.stereo_phase.analyze_stereo_phase` with the **same
   `MasteringConfig`-derived values** (`ReferenceAnalysisConfig` wraps
   rather than re-specifies these — see §3) that STORY-001's stage [2]
   uses for the equivalent thresholds/factors (true-peak oversample factor,
   DR block seconds/exclude fraction, frequency-band edges/reference band,
   stereo window/hop/ratio-threshold). No STORY-002-specific override of
   any of these five functions' inputs is permitted for a shared metric.
2. **Same array shape/dtype convention at the ingest boundary** — see §6's
   explicit "AC11 trap" callout: `reference_ingest.py` must replicate
   `ingest.py`'s `float64`/`always_2d`-then-squeeze convention exactly for a
   WAV input, or the two paths can silently diverge on mono handling
   without either raising an error.
3. **A dedicated cross-path regression test** (recommended for
   test-case-writer, not built here): given one WAV fixture, run it through
   both `io/ingest.py` → STORY-001's stage-[2]-equivalent analysis calls,
   and through `io/reference_ingest.py` → `[R2]`'s analysis calls, and
   assert field-by-field equality (LUFS, dBTP, DR rounded, all three
   three-band `FrequencyBalanceResult` fields, `overall_correlation`,
   `mono_compatible`) to appropriate floating-point tolerances (exact for
   integer/boolean fields, `1e-9`-class tolerance for float fields computed
   via the same deterministic numpy/scipy operations on the same input
   array). This is the concrete, automated form of AC11 and should live in
   this story's own test suite as its own dedicated test module (e.g.
   `test_ac11_code_path_identity.py`), not folded into a general regression
   test. **v2 addendum**: this test must be re-run after the §7.1
   `true_peak.py`/`clipping.py` allocation fixes to confirm they are
   genuinely output-preserving, not just theoretically so.

---

## 9. Machine-readable output — schema and report-layer design

`report/render.py`'s existing pattern (`render_json`/`render_markdown`
against a `ReportData` object, `dataclasses.asdict` + `json.dumps`) is the
right pattern to follow, but the shape itself is new — this is a
multi-track/aggregate/comparison report, not STORY-001's single-track
before/after shape, and building it as a separate module keeps STORY-001's
`report/builder.py`/`report/render.py` completely untouched (per the NFR's
non-regression requirement).

New `report/reference_builder.py` + `report/reference_render.py`:

```python
@dataclass
class AggregateStat:
    metric: str
    median: float
    min: float
    max: float
    n: int
    contributing_tracks: List[str]     # AC12
    excluded: List[dict]               # [{"track": ..., "reason": ...}], AC5/mono/lossless-N

@dataclass
class ReferenceSetReport:
    schema_version: str = "1.0"        # NFR: stable, versioned machine-readable schema
    generated_at_utc: str
    decoder_identity: dict             # {"libsndfile": "...", "ffmpeg": "..." or None}
    tool_version: str
    config_summary: dict
    per_track: List[ReferenceMeasurements]
    aggregates: List[AggregateStat]    # one entry per AC1 metric (or per sample-rate
                                        # subset for HF-extension, per resolved q#6)
    comparison: Optional[dict]         # populated only when a Suno-export path is given
    failures: List[dict]               # [{"path": ..., "reason": ...}] — §7 per-file tolerance
```

`schema_version` is the concrete answer to the NFR's "so later stories can
consume the targets programmatically" requirement — a later story reading
this JSON can branch on `schema_version` rather than assume an implicit,
unversioned shape. Any future field addition/removal bumps this string
(minor version for additive/backward-compatible changes, major for anything
that removes or reshapes an existing field) — this convention itself should
be stated in a module docstring so python-developer/QA have a shared rule
for when to bump it, rather than each future story guessing independently.
(v2 note: adding `BandCancellation.excess_delta_db` per §4.5 and renaming
`mono_cancellation_threshold_db` per the same section are exactly the kind
of additive/renamed changes this convention exists for — bump
`schema_version` to `"1.1"` for this revision.)

`decoder_identity` records the actual decode path taken per §6's tiering
(libsndfile version string when tier 0/1 is used, ffmpeg version string
when tier 2 is used) — this is the concrete, cheap answer to the
reproducibility NFR's MP3-decoder-version-sensitivity flag: a later run can
compare `decoder_identity` and know immediately whether a measurement
difference might be attributable to a decoder change, rather than having to
infer it.

**AC12 concretely**: every `AggregateStat` carries `n` and
`contributing_tracks` unconditionally — there is no aggregate figure in
either rendering (Markdown or JSON) presented without its N adjacent to it.
The Markdown renderer's aggregate table must show N as a column, not a
footnote, so a reader cannot miss which aggregates are computed over a
different subset than others (e.g. "HF extension (44.1kHz subset, N=4,
low-confidence)" is rendered as one legible row, not split across a table
and a caveat paragraph elsewhere).

---

## 10. Non-destructive handling and reproducibility

Directly reuses STORY-001's SHA-256 pre/post-hash pattern (architecture.md
v5 §4), extended per requirements.md's explicit ask:

- Every reference file (WAV, FLAC, MP3) is opened read-only; `[R1]` computes
  its input hash before decode, `[R5]`'s run-completion step re-hashes every
  file that was successfully ingested and asserts the set matches — a
  `NonDestructiveIntegrityError` (reused from STORY-001's `errors.py`,
  imported not duplicated) is raised if any mismatch is found.
- **No decoded/intermediate audio artifact is ever written to disk** — this
  is the structural property §6 tier 2's "no writable path parameter"
  design enforces for the MP3 fallback path specifically, and is trivially
  true for tiers 0/1 (`soundfile.read()` never writes). Recommend a QA-level
  test that snapshots the OS temp directory's contents before and after a
  full reference-set run (including at least one MP3 fixture routed through
  whichever tier the runtime's probe selects) and asserts no new files
  persisted.
- **Reproducibility**: no new randomness source is introduced by any of
  §4's five new measurements — LRA, seven-band balance, HF-rolloff,
  per-band width, and mono-sum/cancellation are all deterministic functions
  of the input array and config (Welch/CSD parameters, K-weighting filter
  coefficients, and segment boundaries are all fixed, non-adaptive
  computations, matching STORY-001's own AC10 discipline). The one
  genuinely environment-dependent piece is **MP3 decoder version**
  (different libsndfile or ffmpeg builds can, in principle, decode the same
  MP3 file to very slightly different sample values) — this is flagged, per
  requirements.md's own instruction, as a risk to note rather than solve,
  and is made checkable (not just documented) via the `decoder_identity`
  field in §9's schema: a later re-run on a different machine can compare
  decoder identity and attribute any observed measurement drift to that,
  rather than to a code regression.

---

## 11. Constraints for implementation

### Module layout (additions to the existing `suno_mastering` package)

```
suno_mastering/
  analysis/
    types.py                    # UNCHANGED
    loudness.py                  # UNCHANGED
    true_peak.py                  # v2: one internal allocation fix (§7.1, DEF-103); public API/output unchanged
    dynamic_range.py               # one internal extraction (§5); public API unchanged
    frequency_balance.py            # PSD/Welch helper extracted to _psd.py (§4.2); public API/output unchanged
    stereo_phase.py                  # UNCHANGED
    clipping.py                       # v2: one internal allocation fix (§7.1, DEF-103); public API/output unchanged
    silence.py                         # UNCHANGED, reused by seven_band_balance.py
    _psd.py                              # NEW: shared Welch/nperseg helper, extracted from frequency_balance.py
    loudness_range.py                     # NEW: LRA (§4.1)
    seven_band_balance.py                  # NEW: seven-band scheme (§4.2)
    hf_extension.py                         # NEW: rolloff/stability/transcode-suspicion (§4.3)
    per_band_stereo_width.py                 # NEW: per-band width (§4.4)
    mono_sum.py                               # NEW: level change + cancellation (§4.5, v2 formula corrections)
    reference_types.py                         # NEW: ReferenceMeasurements + sub-result dataclasses (§3, v2: + BandCancellation.excess_delta_db)
  io/
    ingest.py                    # UNCHANGED
    wav_chunks.py                 # UNCHANGED, unused by this story
    export.py                      # UNCHANGED, unused by this story
    reference_ingest.py             # NEW: WAV/FLAC/MP3 read path (§6)
    mp3_decode.py                    # NEW: tier-0/1/2 decode dispatch + provenance (§6)
  reference_analysis/
    config.py                    # NEW: ReferenceAnalysisConfig (wraps MasteringConfig, §3; v2: mono_cancellation_threshold_db renamed to mono_band_cancellation_excess_db)
    pipeline.py                   # NEW: [R1]-[R5] orchestration, analyze_set()/analyze_track() entry points
    aggregate.py                   # NEW: [R3] median/min/max + exclusion logic (§1, §7)
  report/
    builder.py                   # UNCHANGED
    render.py                     # UNCHANGED
    reference_builder.py           # NEW: ReferenceSetReport assembly (§9); v2: renamed config field reference
    reference_render.py             # NEW: Markdown + JSON rendering for the reference report (§9)
```

`reference_analysis/` is a new top-level package sibling to `mastering/`,
not a subpackage of it — this story does no mastering, and nesting it under
`mastering/` would misrepresent its scope.

### CLI vs. library API

Mirror STORY-001's pattern:

- **Library API**: `suno_mastering.reference_analysis.pipeline.analyze_set(reference_dir: str, suno_export_path: Optional[str] = None, config: Optional[ReferenceAnalysisConfig] = None) -> ReferenceSetReport`. Exceptions from per-file decode/ingest failures are caught internally and recorded in `ReferenceSetReport.failures` (§7) — this is a deliberate, narrow exception to STORY-001's "exceptions propagate, no swallowed errors" rule, justified explicitly here: it is the concrete implementation of the "one bad file must not abort the set" requirement, scoped to exactly the per-file ingest/decode boundary and nowhere else in the pipeline (a bug inside `[R2]`'s measurement logic, for example, still propagates as a real exception — only "this specific file could not be read" is caught and recorded).
- **CLI**: `python -m suno_mastering.reference_analysis <reference_dir> [--suno-export PATH] [--output-dir DIR] [--config PATH]`, a thin wrapper writing both renderings to disk alongside catching the exception hierarchy at the top level, matching STORY-001's `cli.py` pattern.

### Error handling

No new exception types are needed beyond what `errors.py` already defines
(`InvalidWavError`, `UnsupportedFormatError` are both directly applicable to
a reference-track ingest failure — reused, not duplicated). One new
exception is warranted: `errors.EmptyReferenceSetError` (raised by
`analyze_set()` if, after per-file failures are excluded, zero tracks
remain to analyze — a genuinely different condition from "one file failed"
and one that should stop the run rather than silently produce an empty
aggregate).

### Config as single source of truth (extends the existing pattern)

Every new numeric/threshold value introduced by §4 lives in
`ReferenceAnalysisConfig`, not hardcoded: seven-band edges, LRA's absolute/
relative gate values and window/hop, HF-rolloff's threshold-dB/stability-
tolerance/segment-count, per-band-width's own test tolerance, mono-sum's
cancellation excess threshold (**v2: `mono_band_cancellation_excess_db`,
renamed from `mono_cancellation_threshold_db` — see §4.5**), the
lossless-confidence-N thresholds (0/1-2/3+, per resolved open question #7),
and the transcode-suspicion band list/slope threshold (per resolved open
question #10). This mirrors architecture.md v5 §6's "config as single
source of truth" discipline exactly, and serves the same test-case-writer
purpose: constructing a boundary-condition config (e.g. a lossless-count-N
config set to exactly 2, to test the low-confidence flag boundary) without
touching pipeline code.

---

## 12. Testability notes

- Every new `analysis/*` function in §4 takes plain numpy arrays + sample
  rate + config, following architecture.md v5 §7's existing convention
  exactly — this was a design requirement (AC10), not a nice-to-have, and
  is satisfied by construction for all five new measurements (§4.1–§4.5
  each specify their own synthetic-signal AC10 verification bar).
- `io/reference_ingest.py`'s tier-1/tier-2 MP3 decode branch (§6) should be
  tested against **both** branches where the test environment allows —
  recommend the test-case-writer add an environment-conditional test (skip
  gracefully, do not fail, if the runtime's `soundfile.available_formats()`
  probe means only one branch is actually reachable on a given CI machine)
  plus a unit test of `mp3_decode.py`'s dispatch logic itself with the
  probe result injected/mocked, so the branch-selection logic is tested
  independently of which branch happens to be live on any given machine.
- The AC11 cross-path regression test (§8, item 3) is the single most
  important test in this story's suite — recommend it be written early,
  since a failure there indicates a structural ingest-path divergence (most
  likely the array-shape trap named in §6) that would otherwise surface
  much later and more confusingly as a mysterious aggregate-statistic
  discrepancy.
- `[R3]`'s aggregation/exclusion logic (§1, §7) should be tested with a
  small, fully-synthetic "reference set" (3-5 short synthetic tracks with
  known, hand-computed per-track values) so the median/min/max/N/exclusion
  logic can be verified against arithmetic a human can check by hand,
  independent of any real commercial reference material — including at
  least one fixture each for: a lossy track correctly excluded from the HF
  aggregate (AC5), a mono track correctly excluded from stereo-width/mono-
  compat aggregates (Input/output assumptions), and a mixed-sample-rate set
  correctly producing two separate HF-extension subsets (resolved open
  question #6).
- Recommend one golden-file-style regression test at the `analyze_set()`
  level, mirroring STORY-001's own recommended golden-file test
  (architecture.md v5 §7): a fixed small synthetic reference folder + fixed
  config, asserting the full `ReferenceSetReport` JSON is stable across
  runs — the concrete implementation of this story's own reproducibility
  NFR.
- Performance: as with STORY-001, every per-sample/per-window computation
  in the five new measurement modules must be vectorized (numpy/scipy), not
  a Python-level loop — worth an explicit note here since LRA's short-term
  windowing (3s window, 100ms hop — far more windows per track than
  `stereo_phase.py`'s 500ms/no-overlap tiling) is the new computation most
  at risk of an accidentally-scalar implementation blowing the "seconds,
  not minutes" per-track budget. (v2: this risk materialized once, was
  found and correctly fixed by python-developer during the v1 pass — see
  §7.2 — and is retained here as a standing caution for any future
  windowed computation added to this story's scope, not as an open item.)
- **v2 addition (DEF-101 test-coverage gap)**: `mono_sum.py`'s test suite
  must include an ordinary-decorrelated-stereo fixture (independent,
  equal-power noise in L/R, no phase relationship) asserting
  `excess_cancellation_db ≈ 0` and no band flagged `cancellation=True` — the
  absence of exactly this fixture in v1's test coverage is how the DEF-101
  false-positive shipped without being caught by the existing AC10 test
  (which only covered the true-positive out-of-phase case). See §4.5 for
  the full specification.
- **v2 addition (DEF-103 test-coverage gap)**: after the `true_peak.py`/
  `clipping.py` allocation fixes (§7.1), STORY-001's own clipping/true-peak
  test suites (not just STORY-002's) must be re-run and confirmed
  unchanged in output — this is a fix to files outside this story's own new
  module set, and the regression surface is STORY-001's, not STORY-002's.
- **v3 addition (DEF-110)**: STORY-001's own `test_tc150_processing_time_
  budget` and STORY-002's `test_ref_nfr.py::test_tc381` are both genuine
  wall-clock NFR gates with thin margin against their budgets even in
  isolation (`test_tc150`: ~290-294s isolated vs. a 300s budget). Both
  **must be run in a dedicated, isolated pytest invocation**, never appended
  to the tail of a large combined test session — see §16 for the full
  reasoning and the concrete CI instruction. A test-runner change that
  silently folds these back into one giant combined session (e.g. a "run
  everything in one pytest invocation" CI simplification) would reintroduce
  exactly the false-failure pattern DEF-110 diagnosed, without changing any
  actual pipeline behavior.

---

## 13. Assumptions pending confirmation

Requirements.md v2 resolved all ten of its own open questions, so this
section is short — these are engineering judgment calls within the scope
requirements.md explicitly left to the architect, not product-level
ambiguity:

1. **HF-rolloff threshold (-6 dB relative) and its test tolerance (500 Hz),
   the LRA tolerance (1.0 LU), the mono-cancellation excess threshold
   (-3 dB, v2: now interpreted as excess-beyond-the-decorrelated-floor per
   §4.5, not a raw dB reading), and the transcode-suspicion band
   list/slope (24 dB/octave)** are all reasoned architect defaults
   (§4.1/§4.3/§4.5), not producer-verified — same category of "reasoned
   placeholder" as STORY-001's own three-band reference curve
   (architecture.md v5 §9 risk #1). All are config-driven specifically so
   they can be recalibrated without a code change once real reference-set
   results are available to sanity-check against.
2. **The whole-set time budget (§7.2, v2: "under five minutes for a
   7-track/7-minute-track worst case, ~2.3 minutes for realistic
   3-4-minute reference material") is now a measured extrapolation, not a
   pure guess** — a real improvement over v1's fully-unbenchmarked "under
   two minutes" figure, but still an extrapolation from one synthetic
   fixture rather than a real multi-track reference-set run. Confirming it
   against an actual heterogeneous reference folder (mixed durations,
   formats, sample rates) remains open, same spirit as STORY-001's own §9
   risk #8.
3. **The `air`-band aggregation decision (§7) — energy ratio tolerates
   cross-sample-rate blending where a rolloff frequency does not — is a
   judgment call, not directly stated by any resolved open question.**
   Flagged explicitly with the reasoning and the concrete fallback (subset
   per sample rate, matching HF-extension's existing pattern) if QA's
   eventual real-data testing shows it matters.
4. **`mutagen` as a new dependency** (§2, §6) is a concrete library
   addition beyond the currently-installed set — flagged since it is not in
   `requirements.txt` today. It is a narrow, pure-Python, optional-path
   addition (only exercised on the tier-1-MP3-with-libsndfile-support
   branch, and only for the best-effort bitrate field specifically), not a
   change to any precision-critical or safety-critical code path.
5. **The revised ~2.7-3.3 GB/track memory estimate (§7.1) is a corrected
   estimate, not a re-measurement** — the DEF-103 fixes are specified
   precisely enough to be low-risk, but python-developer should re-run
   `tracemalloc` against the fixed `true_peak.py`/`clipping.py` before this
   figure is treated as confirmed, the same way the original ~2.4 GB v1
   figure needed (and got) empirical correction this pass.
6. **v3, new**: STORY-001's own product-level NFR ("under 5 minutes
   wall-clock for a 7-10 minute track," requirements.md §7/Open Question
   #8) is confirmed, by this pass's isolated-run measurements (289-294s),
   to genuinely hold on the reference-benchmark machine — but with only
   ~2-3% margin, not the wide margin the requirements language's plain
   reading might suggest. This is now visible and worth flagging to the
   product owner/BA as a standing fact about the current implementation's
   real headroom, not something this architecture document is authorized to
   loosen unilaterally (see §16) — recorded here per this role's "flag
   rather than silently assert" discipline for a BA-specified target.

---

## 14. Open architectural risks

1. **Whether the installed environment's `soundfile` actually exposes MP3
   read support is genuinely unknown at architecture time** (§6) — resolved
   here as a runtime probe rather than a guess, but the probe's result (and
   therefore which decode tier most reference-set MP3s in practice take)
   is unverified until python-developer runs it. If tier 2 (FFmpeg
   subprocess) turns out to be the live path, its wall-clock cost per file
   (subprocess spawn + full-track pipe-decode) is unbenchmarked and could
   materially affect the §7.2 whole-set budget — worth an early benchmark
   pass specifically on whichever tier is live, before the budget number is
   treated as reliable.
2. **LRA's K-weighting filter is new, from-spec DSP with no existing
   STORY-001 building block and no direct library implementation to lean
   on** (§4.1) — the same category of risk STORY-001 flagged for
   `dynamic_range.py` and `true_peak.py` (architecture.md v5 §9 risks #2/#3:
   "no mature Python library, needs validation against known reference
   values"). The self-consistency check against `pyloudnorm`'s integrated
   LUFS (§4.1) provides real but partial confidence — it validates the
   K-weighting/gating machinery, not LRA's own percentile-spread logic
   specifically. External EBU Tech 3342 reference-material validation
   (§4.1's AC10 bar) is the actual closure path and should be prioritized
   early in QA, mirroring how STORY-001 treated TC-024's cross-validation
   as its own single highest-stakes unresolved verification gap.
3. **Per-band stereo width's frequency-domain (Welch/CSD) approach is a
   deliberate simplification versus a literal band-filtered time-domain
   correlation** (§4.4) — flagged as a stated caveat in the report itself,
   but worth restating here as an open risk: if QA's listening-based or
   numeric cross-checking later finds this approach's per-band figures
   diverge meaningfully from what a band-filtered time-domain correlation
   would report for the same content, revisiting toward an actual filter-
   bank design (with its own coefficient-design justification, deliberately
   avoided in this pass per the advisor-review discussion during this
   document's own drafting) would be the concrete next step.
4. **The seven-band scheme's edge frequencies are BA-resolved (requirements
   .md open question #3) but, like STORY-001's three-band curve, carry no
   producer-verified reference values yet** — this story's own purpose is
   to *derive* those values from real reference-track measurement, so this
   is explicitly not a gap in this pass (requirements.md is explicit no
   target numbers are being invented here), but it's worth stating plainly
   that the seven-band report is only as useful as the reference set it's
   run against — a thin, unrepresentative reference folder produces a thin,
   unrepresentative "territory," and no amount of correct DSP downstream of
   that folder-selection step corrects for it. Track-set curation quality is
   entirely outside this architecture's control (requirements.md's own
   resolved open question #1).
5. **Transcode-suspicion's three-condition heuristic (§4.3) has no
   empirical validation against any known-transcoded real file yet** — it
   is a reasoned construction from the requirement's own named encoder-
   typical cutoff bands, not a tuned/tested detector. Flagged the same way
   STORY-001 flagged its stereo-widened-element debounce parameters before
   listening-based QA (architecture.md v5 §9 risk #5): a reasonable default,
   not a validated one, and may need threshold tuning once run against a
   real file known to be a lossless-container transcode.
6. **v2, new**: the §4.5 mono-sum correction was derived and cross-checked
   algebraically (against the actual `mono_sum.py` PSD/band-power code) and
   against one existing empirical measurement (the L=R -3.0103 dB figure
   already measured by python-developer), but the *new* required test
   fixture (ordinary decorrelated stereo, §4.5/§12) has not yet been run
   against the corrected formula by this architecture pass — it is
   specified precisely enough to implement directly, but "excess_delta_db
   ≈ 0 and no band flags for ordinary decorrelated stereo" should be
   confirmed empirically by python-developer as the first verification step
   of the DEF-101 fix, before broader QA testing proceeds on top of it.
7. **v3, new (DEF-110)**: STORY-001's product-level "under 5 minutes for a
   7-10 minute track" NFR is confirmed to hold on the reference-benchmark
   machine, but with only ~2-3% measured margin in isolation (289-294s vs.
   300s). This is thin enough that ordinary machine-to-machine variance
   (slower consumer hardware than the benchmark machine, thermal state, a
   busier OS at the moment of a real user's run) could plausibly push a
   genuine single production run over budget on some machines, independent
   of the DEF-110 test-session-tail-load artifact this pass diagnosed and
   resolved. Flagged here as a standing product-level risk worth the BA's
   awareness — not treated as resolved, since this architecture pass has no
   mandate to either loosen the BA-specified figure or to open a new
   performance-optimization pass against STORY-001's frozen implementation
   unilaterally. See §16 for the full reasoning and why no code-level or
   budget-number fix is applied here.

---

## 15. Revision history

- v1 (2026-08-01): Initial architecture, based on requirements.md v2 (all
  ten open questions resolved). Read STORY-001's architecture.md (v5) and
  implementation (`analysis/types.py`, `loudness.py`, `true_peak.py`,
  `dynamic_range.py`, `frequency_balance.py`, `stereo_phase.py`,
  `io/ingest.py`, `io/wav_chunks.py`, `report/builder.py`, `report/
  render.py`, `config.py`, `pipeline.py`, `errors.py`) in full before
  writing, per this story's explicit "reuse the existing analysis stage, do
  not duplicate" instruction. Key decisions: compose a new
  `ReferenceMeasurements` type wrapping the unmodified `Measurements`
  dataclass rather than extending it (§3), extract-don't-fork
  `dynamic_range.py`'s unrounded value via a private helper (§5), a
  separate `io/reference_ingest.py` read path with a runtime-probed
  MP3-decode tiering (soundfile direct read, then FFmpeg-stdout-pipe
  fallback — never `pydub`, which writes ffmpeg output to a temp file and
  so structurally violates the no-disk-artifact constraint) (§6), five new
  `analysis/*` measurement modules with concrete algorithms and AC10
  verification bars for LRA, seven-band balance, HF-rolloff/transcode-
  suspicion, per-band stereo width, and mono-sum level change/cancellation
  (§4), and an explicit memory-discipline requirement (release
  `true_peak.py`'s oversampled buffer per track, process the set strictly
  sequentially) inherited from and now made load-bearing by STORY-001's own
  previously-unbenchmarked §9 risk #8. No architecture-level open questions
  remain blocking implementation; §13/§14 flag engineering judgment calls
  and residual risks for QA/production-use confirmation, not blockers.

- **v2 (2026-08-01)**: Revision in response to three Architectural defects
  filed by python-developer after the first implementation pass
  (defects.md DEF-101/DEF-102/DEF-103), each independently verified against
  the actual shipped code (`analysis/mono_sum.py`, `analysis/
  reference_types.py`, `analysis/clipping.py`, `analysis/true_peak.py`,
  `analysis/__init__.py::measure_all`, `reference_analysis/config.py`)
  before being resolved here, not accepted on the report's word alone.

  - **DEF-101 (mono-sum baseline math)** — §4.5 fully rewritten. Root cause
    is more specific than either python-developer's report or this
    architect's own first pass at reviewing it: the broadband
    `level_change_db` formula and the per-band `delta_db` formula divide by
    different denominators (channel-*summed* vs. channel-*mean* power)
    and so have different ρ=0 (fully-decorrelated) floors — **-6.0206 dB**
    broadband, **-3.0103 dB** per-band — and v1's code referenced *both*
    derived fields to the same (wrong, and in one case merely
    coincidentally-numerically-similar) `-3.0103` constant. This is a
    **code change**, not a documentation-only fix: `mono_sum.py`'s
    `excess_cancellation_db` baseline and the per-band `cancellation` flag's
    comparison both need correcting (concrete diff specified in §4.5),
    `reference_types.py`'s `BandCancellation` needs a new `excess_delta_db`
    field, and `reference_analysis/config.py`'s
    `mono_cancellation_threshold_db` is renamed to
    `mono_band_cancellation_excess_db` (default value unchanged, `-3.0`,
    only its meaning is corrected) so the semantic change is visible at
    every call site. A new required test fixture (ordinary decorrelated
    stereo, asserting no false-positive) is specified — its absence in v1's
    test coverage is exactly how the false-positive would have shipped
    undetected. **Downstream impact for python-developer**: `mono_sum.py`,
    `reference_types.py`, `reference_analysis/config.py`, and
    `report/reference_builder.py` (renamed config field reference) all need
    the changes itemized in §4.5's "What this changes in the shipped code"
    list; `schema_version` bumps to `"1.1"` per §9.
  - **DEF-102 (whole-set time budget)** — §7.2 rewritten.
    Documentation-only correction, no code change: the measured 33.3s/track
    figure is accepted as real (python-developer's LRA-windowing fix that
    produced it was itself a correct, appropriately-scoped implementation
    fix, not revisited). Root cause reframed: `measure_all` alone (STORY-001's
    AC11-frozen code) costs 16.39s/track, consuming ~1.9 minutes of any
    7-track budget before this story's own new measurements run at all —
    v1's "under two minutes" target was set without that figure and so was
    unachievable by construction, not under-delivered by this story's new
    code. Whole-set target revised to **under 5 minutes for a 7-track set of
    7-minute-average tracks** (worst case), with realistic 3-4 minute
    reference material extrapolated at **~2.3 minutes for 7 tracks** (stated
    explicitly so the 5-minute figure isn't read as the typical case). A
    shared per-track PSD cache is noted as an optional, non-blocking future
    optimization (bounded benefit — it cannot touch the AC11-frozen
    `measure_all` half of the cost) — not authorized or required now.
    **Downstream impact for python-developer**: none — no code change
    required for this item.
  - **DEF-103 (memory)** — new §7.1. python-developer's ~5.5 GB measurement
    is confirmed as real and its root cause is identified precisely (and
    found to be one line more than what was reported: both `true_peak.py`'s
    own peak-search line, `np.max(np.abs(scan_region))`, and `clipping.py`'s
    `np.abs(tp_result.oversampled) > 1.0` each allocate a redundant
    full-size float64 copy via `np.abs()` rather than computing the same
    result without one). Resolved as an authorized, narrowly-scoped,
    behavior-preserving **code fix** to both lines (concrete replacement
    expressions specified in §7.1), not a documentation-only acceptance of
    5.5 GB and not a product-level "skip clipping for reference tracks"
    compromise — a genuinely better option was available and is specified
    precisely enough to implement directly. Expected post-fix peak is
    ~2.7-3.3 GB/track (a corrected estimate, flagged in §13 as needing
    re-measurement, not yet re-measured by this architecture pass).
    **Downstream impact for python-developer**: `true_peak.py` and
    `clipping.py` (STORY-001 files, exception explicitly authorized on the
    same "extract/optimize, don't fork" basis as this story's other two
    internal-refactor exceptions) need the two one-line changes in §7.1;
    STORY-001's own existing clipping/true-peak regression and golden-file
    tests must be re-run and confirmed bit-identical before this is closed,
    not just STORY-002's new tests.

- **v3 (2026-08-02)**: Revision in response to one further Architectural
  defect (defects.md DEF-110), re-triaged by python-developer from
  "Code-level, investigation" to Architectural after profiling ruled out
  every code-level cause. Full reasoning in the new §16. Summary: **no code
  change, no production budget-number change** — the 300s per-track budget
  in STORY-001's `test_tc150` directly implements a BA-specified product
  NFR (requirements.md §7/Open Question #8, "under 5 minutes wall-clock for
  a 7-10 minute track") and this architecture pass has no mandate to
  unilaterally loosen a BA-specified figure, unlike DEF-102 (which revised
  a figure this document itself had originated). Resolved instead as a
  **test-execution-process correction**: both `test_tc150` and STORY-002's
  own `test_ref_nfr.py::test_tc381` measure genuine wall-clock NFR gates
  correctly in isolation (~289-294s and well under 300s respectively) but
  were being run at the tail of a very large combined pytest session, where
  ordinary session-level resource accumulation (not a code regression —
  every candidate code cause was checked and ruled out, see defects.md)
  pushes elapsed time over budget. **Downstream impact for
  qa-automation-engineer**: both tests must be run in a dedicated, isolated
  pytest invocation (not appended to a combined multi-suite session) as a
  standing CI/test-execution rule — see §16 for the concrete instruction.
  **Downstream impact for python-developer**: none — no code change.
  **Separately flagged, not resolved as part of DEF-110 itself**: the
  underlying BA-specified budget has only ~2-3% real margin even in
  isolation on the reference-benchmark machine — recorded as a new §13
  assumption and §14 risk for BA/product-owner visibility, not silently
  loosened.

---

## 16. DEF-110 resolution — NFR test-execution correction (v3)

**What DEF-110 found (python-developer's investigation, defects.md)**: on
four data points, `test_tc150_processing_time_budget`'s wall-clock cost
scales with how much prior test-suite work already ran in the same Python
process session before it executed — 289.99s/293.47s in two genuinely
isolated runs (PASS against the 300s budget), 310.3s at the tail of
STORY-001's own 118-test suite (FAIL), 318.4s at the tail of an even larger
combined STORY-001+STORY-002 session (FAIL). A comparable STORY-002 fixture,
`test_ref_nfr.py::test_tc381`, showed the same signature far more
dramatically: 1129.6s (a 3.8x miss) at the tail of an oversized combined
run, but a clean pass well under 300s when `test_ref_*.py` was run as its
own isolated suite (92 passed, 0 failed, 659.71s total for the whole
16-file/94-test suite). This monotonic isolated-vs-tail-of-suite pattern is
the opposite signature of a deterministic, per-call code regression, which
would cost the same fixed amount whether run first or four thousandth in a
session.

**Every code-level candidate cause was checked directly against the shipped
code and ruled out, not merely assumed clear**: DEF-103's `true_peak.py`/
`clipping.py` allocation fixes are confirmed bit-identical in output and are
allocation-*reducing*, mechanically incapable of being a slowdown source;
the `dynamic_range.py`/`frequency_balance.py` extractions are confirmed
single-computation, non-duplicating refactors, and `frequency_balance.py`
specifically is not even on the solver's hot path (`loudness_limit.py`
never imports it); a separate, unrelated `loudness_limit.py` v4 solver
lower-bound change was A/B tested directly and does not consistently cost
more wall-clock time (the *iteration count* was independently confirmed
fully deterministic across three repeated runs, ruling out solver
nondeterminism as a contributor to the spread). No plausible code-level
cause remains unchecked.

### 16.1 Root cause, sharpened beyond "environmental"

Stating this precisely, not just as "the machine was under load," because
the imprecise version is too easy to misread as a shrug: `test_tc150`'s own
docstring records that python-developer's original smoke test measured
**~102s** for a "comparable 8.5-minute fixture," and the 300s budget was set
assuming that figure scaled to "the same order of magnitude" for the actual
shipped 8-minute/48kHz/24-bit `make_dynamic_track` fixture. The actual
isolated cost of the shipped fixture is **~290-294s** — essentially 3x the
smoke-test figure, not "the same order of magnitude" in the sense the
budget's headroom assumed. Independently, `test_ref_nfr.py::test_tc380`
(measured this same QA session, in isolation: 34.1s vs. architecture.md's
own documented 33.3s benchmark for the same fixture class) rules out
"this machine is generally slower than the benchmark machine" as an
explanation — the machine matches the benchmark closely. So the gap between
102s and ~290s is a **fixture-cost/smoke-test divergence**: the shipped
`make_dynamic_track` fixture costs roughly 2.9x whatever fixture produced
the 102s smoke-test figure. **What exactly drives that divergence is not
established here and is stated as such, not assumed** — the smoke-test
fixture itself is not described anywhere available to this pass (no
fixture-generation code or docstring for it was found in the repo), so
whether the gap traces to `make_dynamic_track`'s specific transient shape
driving more solver inner-loop iterations, a difference in duration/sample
rate/bit depth between the two fixtures, or some other factor cannot be
determined from what this pass measured; only the magnitude of the
divergence (real, ~2.9x, not noise, not general machine slowness per the
tc380 cross-check) is established. This is reported as unexplained-but-real,
per this role's own "flag rather than assert" discipline for a mechanism
this pass did not directly measure. **The isolated margin was always thin —
289-294s against 300s is ~2-3% headroom — not the wide margin "same order of
magnitude as 102s" would suggest.** This is the DEF-102-shaped root cause
(a budget number's real margin only becomes knowable once the actual shipped
fixture is benchmarked precisely, not extrapolated from a lighter proxy)
applied to a STORY-001 NFR test, not a new category of problem.

**Separately and additively**, the *specific* observed test failures (310s,
318s, 1129s) are explained by ordinary session-level resource effects
(memory/page-cache pressure, OS scheduler contention, thermal/frequency
throttling) accumulating once 20-45+ minutes of other heavy numeric test
work has already run in the same process/session — this is the mechanism
DEF-110's own four data points and the independent `test_tc381`
corroboration both demonstrate directly. The thin baseline margin from
16.1's first paragraph is *why* this session-level noise is enough to flip
the result from PASS to FAIL; it would not be visible at all against a
budget with real headroom.

### 16.2 Why the budget number is not revised here (unlike DEF-102)

**DEF-102 revised a whole-set budget that this architecture document itself
originated** (§7.2's "under two minutes for 7 tracks" was an
architect-authored, unbenchmarked v1 estimate) — correcting it against real
measurement was squarely within this document's authority and matched its
own "reasoned defaults are config'd and revisable" posture (§13).

`test_tc150`'s 300s figure is different in kind: it directly implements
**requirements.md's own product-level NFR** — "Processing time: target
under 5 minutes wall-clock (analysis + mastering combined) for a 7-10
minute track on typical consumer hardware" (requirements.md §7, and Open
Question #8, "RESOLVED... Target under 5 minutes wall-clock for a 7-10
minute track on typical consumer hardware"). This is a BA-specified target,
resolved by the product owner in conversation per requirements.md's own
Section 8 framing — not a number this architecture document is free to
raise. Per this role's own standing rule ("never contradict [a] target the
BA specified without saying so explicitly and why"), the correct move when
a BA-specified figure turns out to have thin real margin is to **flag it
for BA visibility** (§13 item 6, §14 risk #7), not to silently widen the
test's assertion past it. Confirming empirically that the isolated-run cost
(289-294s) genuinely satisfies "under 5 minutes" for the fixture class in
question means the product requirement **is currently met** — this is not a
case where the requirement is provably unachievable (unlike DEF-102's
"measure_all alone consumes the whole budget" finding), so there is no
DEF-102-style "the target was unachievable by construction" argument
available here to justify a revision.

### 16.3 What is authorized: a test-execution-process fix, not a code or budget fix

The observed FAIL results (310.3s, 318.4s, 1129.6s) are an artifact of
**how** the test was being run — appended to the tail of an oversized
combined pytest session — not evidence that a real, single production
`pipeline.master()` run (the only scenario the product NFR actually
describes) exceeds budget. A real user invoking this tool never runs
STORY-001's full 118-test suite plus STORY-002's full 94-test suite in the
same Python process immediately beforehand; that is purely a test-authoring/
CI-invocation artifact, not a product usage pattern the NFR is making a
claim about.

**Concrete instruction for qa-automation-engineer**: `test_tc150_processing_
time_budget` (STORY-001, `tests/test_nfr_performance.py`) and `test_ref_nfr.
py::test_tc381_whole_set_budget_under_5_minutes_worst_case` (STORY-002) must
each be run in a **dedicated, isolated pytest invocation** — a separate
`pytest -k test_tc150` / `pytest -k test_tc381`-style invocation, its own
CI job step, or equivalent process isolation — never folded into one large
combined-suite pytest run alongside dozens of other tests ahead of it in the
same session. This is a **standing CI/test-execution rule**, not a one-time
workaround: any future test-runner change that re-combines all suites into
one giant invocation would silently reintroduce this exact false-failure
pattern without any pipeline code having changed. Both `[pytest.mark.slow]`
markers already exist on these tests (confirmed in `test_ref_nfr.py`'s own
source) — recommend qa-automation-engineer's CI configuration run
`-m slow`-marked NFR/wall-clock tests as their own isolated job/step
specifically for this reason, distinct from why they're already segregated
by the `slow` marker (long individual runtime) — the isolation requirement
here is about *session position*, not just *individual duration*.

**Explicitly ruled out, not left as a live option**: the previously-flagged
optional shared-PSD-cache idea (§7.2) is irrelevant to `test_tc150`
specifically — `pipeline.master()` (STORY-001's own entry point, which
`test_tc150` calls) never imports or calls any of STORY-002's new
measurement modules, so a PSD cache inside `reference_analysis/` cannot
affect `test_tc150`'s timing in any way. It remains a live, bounded-benefit
option for `test_tc381`'s own whole-set cost specifically (§7.2), but is not
a candidate fix for DEF-110's `test_tc150` finding and should not be
pursued under DEF-110's name.

### 16.4 What is flagged, not resolved, for the BA/product owner

Recorded in §13 item 6 and §14 risk #7, restated here because it is the one
genuinely new piece of information this investigation surfaced beyond the
DEF-110 diagnosis itself: the BA-specified "under 5 minutes for a 7-10
minute track" NFR is **currently met** (289-294s isolated, comfortably
under 300s) but with only **~2-3% real margin** on the reference-benchmark
machine, not the wide margin the plain English of the requirement might
suggest to a reader who hasn't seen the actual measurement. This
architecture pass takes no action on it beyond flagging it visibly in two
places, per this role's explicit "flag rather than assert" instruction for
exactly this situation — a genuine product-level judgment call (accept the
thin margin as-is, invest in a scoped STORY-001 performance pass to build
real headroom, or revise the requirement's stated target) belongs to the
product owner, not to this architecture document.

**Downstream impact summary**:
- **python-developer**: no action required. No code in `true_peak.py`,
  `clipping.py`, `dynamic_range.py`, `frequency_balance.py`, or
  `loudness_limit.py` needs to change as a result of DEF-110 — all were
  checked and cleared.
- **qa-automation-engineer**: run `test_tc150` and `test_tc381` as isolated,
  dedicated pytest invocations going forward (§16.3) — this is the concrete
  fix that resolves DEF-110's observed failures without touching the budget
  number or any production code. Update defects.md's DEF-110 entry to
  record this resolution (done, see defects.md).
- **BA/product owner**: no action required by this pass, but §13 item 6/§14
  risk #7's thin-margin finding is now visible for a future product-level
  decision, should one be wanted.
