# STORY-002: Reference track analysis — Requirements

## Restated intent

Given a folder of commercially-released reference tracks (deep/melodic
progressive house and melodic techno — e.g. Anjunadeep, Lost & Found) plus
optionally a Suno export, measure every file with the same analysis code
already built for STORY-001, and produce a per-track and aggregate
(median/min/max) report so that mastering targets for this genre can be
derived from real records rather than generic streaming-compliance numbers.
This story is analysis-and-reporting only — it changes no audio and adds no
processing.

## Relationship to STORY-001 — what already exists vs. what is new

This story's own text is explicit: modify `stories/STORY-001/implementation/`
directly; do not create a separate implementation folder or duplicate
analysis logic. The split below is what makes that instruction concrete for
the architect.

### Reused as-is (no new measurement logic required)

- **Integrated loudness (LUFS, BS.1770-4, gated)** — `analysis/loudness.py`,
  via `pyloudnorm`. Already correct for AC1's "integrated loudness" line.
- **True peak (dBTP, oversampled)** — `analysis/true_peak.py`. Already
  built, already the subject of extensive v4/v5 architectural work on the
  FIR oversampling filter. See "Reused with a caveat" below — this is not a
  clean, no-comment reuse for reference-track material.
- **Stereo phase correlation (overall correlation coefficient, mono
  compatibility flag)** — `analysis/stereo_phase.py`'s
  `overall_correlation`/`mono_compatible` fields. Reusable directly for
  AC's "stereo width — correlation coefficient" line.
- **Dynamic range (TT DR-meter)** — `analysis/dynamic_range.py` — reusable
  for crest-factor/dynamic-range reporting, with one caveat below (rounding).

### Reused with a caveat — flagged for the architect, not silently assumed away

- **DR precision for aggregation.** `measure_dynamic_range()` currently
  returns an **integer**-rounded value (`math.floor(dr + 0.5)`, matching the
  conventional "DR9"/"DR14" display convention). Median/min/max across a
  5+-track reference set computed from integer inputs is too coarse to
  usefully describe "the territory the set occupies" (story.md's own
  framing). **Requirement:** expose the unrounded (float) DR value for
  aggregation and internal comparison purposes, while retaining the
  integer-rounded value for the existing human-readable DR8/DR14-style
  display. This is a signature/return-shape change to
  `measure_dynamic_range()` or an additional field — the architect decides
  which.
- **"Crest factor / dynamic range" — story.md names both; only one is
  built.** `dynamic_range.py` implements the TT DR-meter algorithm (published
  Pleasurize Music Foundation spec: 3-second RMS blocks, exclude loudest
  20%, ratio to 2nd-highest peak). Simple broadband crest factor (peak/RMS
  over the whole track, no blocking/exclusion) is a different, simpler
  statistic and does not currently exist anywhere in the codebase.
  **Open question** (see below): does "crest factor / dynamic range" mean
  "report the TT DR value, using the term loosely," or does the reference
  report need both TT DR *and* a separate broadband crest-factor figure?
  Do not silently pick one — flag for product owner.
- **True-peak metering's known near-Nyquist under-read applies here too,
  and the risk profile is different from STORY-001's.** Architecture.md v5
  §2/§9 risk #3 documents a bounded, direction-known passband ripple in
  `true_peak.py`'s oversampling FIR filter: flat to <0.01 dB only up to
  ~80% of original Nyquist, degrading to ~0.4 dB at 90%, ~1.5–2 dB at
  94–95%, and ~5.9 dB at 99.9% — always as attenuation (under-read), never
  over-read. That residual was judged **acceptable for STORY-001's specific
  material class** on the explicit argument that Suno-generated,
  streaming-target-compliant masters "do not carry meaningful full-scale
  energy" that high in the spectrum. **Reference tracks are exactly the
  opposite case**: commercial masters routinely carry real air-band content
  and are measured near their own -1 dBTP-region ceiling by construction —
  the composite-peak argument that made the residual acceptable for
  STORY-001 does not automatically transfer. **Requirement:** the report
  must state plainly, wherever a reference track's true-peak figure is
  shown, that it inherits this same bounded near-Nyquist under-read, and
  must not present reference dBTP figures as more precise than STORY-001's
  own documented tolerance allows. See open questions below — whether
  reference true-peak figures are trustworthy enough to become a *target*
  (as opposed to just a reported measurement) is a genuine open question,
  not something this document resolves.
- **Loudness (LUFS) and true peak from MP3-decoded audio carry a documented,
  format-specific error direction that this story's own text already names**
  (see "Source format handling" below) — true peak in particular compounds
  with the near-Nyquist under-read above: a lossy source pushes true peak
  *up* (inter-sample peaks introduced by decoding), while the metering
  filter's own residual pushes it *down* near Nyquist. Both directions must
  be stated in the report, not netted against each other or silently
  dropped.

### Genuinely new — no existing measurement logic to reuse

- **Loudness range (LRA).** No LRA computation exists anywhere in
  STORY-001's implementation. `pyloudnorm.Meter` exposes only integrated
  loudness — it does not expose short-term/momentary loudness or LRA.
  **Requirement:** implement per the published standard — EBU Tech 3342 /
  ITU-R BS.1770 loudness range (short-term loudness measured over
  overlapping windows, relative gating, LRA = difference between the 95th
  and 10th percentile of gated short-term loudness values). This document
  names the standard to build against; it does not invent an algorithm or
  a target LRA value — implementation detail is for the architect.
- **Per-band spectral balance expressed for cross-track comparison, across
  seven named bands (sub, low, low-mid, mid, high-mid, high, air).**
  `frequency_balance.py` currently implements exactly **three** bands
  (20–120 Hz low-end, 200–500 Hz low-mid/mud, 2–5 kHz presence/harsh),
  each expressed relative to a 500 Hz–2 kHz reference band, with fixed
  thresholds used to drive STORY-001's corrective-EQ flags. Story.md's
  seven-band list is a materially different band scheme aimed at
  descriptive cross-track comparison, not correction-triggering. **Open
  question** (below): edge frequencies for the seven bands are not given by
  story.md and there is no single industry-standard definition — must not
  be invented here. Also open: whether the seven-band scheme replaces,
  extends, or runs alongside STORY-001's three-band correction scheme (see
  "reference-curve interaction" open question below) — both cannot silently
  diverge without one of them becoming stale.
- **High-frequency extension / rolloff detection**, including a stability
  check across the track. No rolloff-point detection exists in the
  codebase; `frequency_balance.py`'s Welch PSD machinery is a plausible
  building block but the rolloff-finding logic itself (e.g. -3 dB/-6 dB
  point relative to a reference level, checked for stability across
  multiple track segments) does not exist and needs building.
- **Per-band stereo width.** `stereo_phase.py` computes overall correlation
  and a broadband (not per-frequency-band) side/mid energy ratio per
  500ms window, purpose-built for detecting *sustained widened elements to
  correct* — a different question from "how does stereo width vary by
  frequency band for a finished, uncorrected commercial master." Measuring
  correlation/width per band (e.g. low band should read near-mono, top
  band should read wide) requires new logic: band-split the signal (or
  reuse `frequency_balance.py`'s Welch/band-power machinery) and compute
  correlation or a side/mid ratio within each band, not just broadband.
- **Mono compatibility beyond correlation — level change when summed to
  mono.** `stereo_phase.py` currently reports `overall_correlation` and a
  derived `mono_compatible` boolean, but does not compute or report the
  loudness/level change (in dB) that results from actually summing L+R to
  mono, nor does it check for band-specific cancellation. Story.md's
  "Mono compatibility" line explicitly asks for both "level change" and
  "any cancellation when summed to mono" — this is new logic, not a
  reuse of the existing correlation check.
- **Lossy-vs-lossless source format detection, and its downstream
  handling.** No format-provenance detection exists in `io/ingest.py`
  today — see "Source format handling" section below for the full
  requirement.
- **Aggregate statistics across a reference set** (median/min/max per
  metric, across 5+ tracks) — new reporting logic; no per-set aggregation
  exists anywhere in STORY-001 (which reports one track's before/after,
  not a multi-track set).
- **Side-by-side reference-vs-Suno-export comparison** — new report-layer
  logic assembling one Suno-export `Measurements` result alongside the
  reference-set aggregate. AC3 requires this use the *identical* analysis
  code path as the reference tracks — i.e. this is a report-assembly
  requirement, not a new measurement. See "Code-path identity" requirement
  below for what "identical" must guarantee concretely.
- **FLAC input support (and MP3 for lossy references)** — see next section.
  New ingest-path logic, not new DSP/measurement logic.
- **Dual human-readable and machine-readable output** — `report/render.py`
  exists for STORY-001's single-track before/after report; a comparable
  renderer for the multi-track/aggregate/comparison shape described above
  does not exist and needs building. See "Machine-readable output" NFR
  below for what "machine-readable" must mean here specifically.

## Source format handling — explicit requirement, not an implicit assumption

Story.md is explicit that source format materially affects results and must
be surfaced, not silently handled. Concretely:

1. **Format/provenance detection is required per file**: lossless (WAV,
   FLAC) vs. lossy (MP3), and bitrate where the format carries one
   (MP3). This must be recorded against every measurement in the report,
   not just logged internally.
2. **HF-extension measurements from a lossy (MP3) source must be excluded
   from, or explicitly flagged out of, the HF-aggregate** (AC5) — an
   MP3 encoder's own lowpass (roughly 20 kHz at 320 kbps, lower at lower
   bitrates) is not the mastering engineer's decision and must not be
   reported as if it were a target-worthy value.
3. **True peak from an MP3-decoded source is approximate and must be
   flagged as such** — decoding introduces inter-sample peaks not present
   in the original master, biasing dBTP high. This is a *separate*
   direction of error from the near-Nyquist metering under-read discussed
   above (that one biases low); both must be stated, not netted together.
4. **Loudness, LRA, DR/crest factor, spectral balance (the seven-band
   scheme), and stereo width are treated as reliable from 320 kbps MP3**
   per story.md and may be aggregated normally — no special flagging
   required for these specific metrics from a lossy source, beyond the
   general per-track format label required by point 1.
5. **The report must make source format visible per track** wherever that
   track's values appear (not just in a separate provenance table),
   so that an aggregate derived largely from lossy files is never
   presented indistinguishably from one derived from lossless files.
6. **Container format alone cannot catch a lossy-to-lossless transcode,
   and this is a real gap in the protection points 1–5 otherwise provide.**
   A WAV or FLAC file that was itself transcoded upstream from an MP3 (not
   uncommon in promo pools, label send-outs, or re-encoded purchases)
   reports as lossless via container/subtype detection and would pass
   straight into the HF aggregate carrying an encoder lowpass under a
   "clean" label — precisely the failure AC5 exists to prevent, arriving
   through the one door container-based detection alone does not watch.
   **Requirement:** the HF-rolloff measurement (itself new, see below)
   must be used as a corroborating signal, not just a reported output — a
   file declared lossless whose rolloff sits hard at an encoder-typical
   cutoff (~16/19/20 kHz-class rolloff, steep and stable across the
   track) must be flagged for producer review as suspect provenance,
   distinct from the point-2 lossy-container exclusion. Whether such a
   flagged file is then excluded from the aggregate outright or merely
   marked is a product decision — see open questions.

### Input format gap this creates for the architect

STORY-001's `io/ingest.py` reads via `soundfile` (libsndfile), and its
current subtype whitelist (`PCM_16`, `PCM_24`, `PCM_32`, `FLOAT`, `DOUBLE`)
and channel/error-handling logic do not check file extension — a FLAC file
routed through `sf.read()` may already work mechanically for the raw sample
data, since libsndfile natively supports FLAC. **However**, `ingest()` is
coupled end-to-end to WAV-specific concerns that are irrelevant to a
read-only analysis story and must not be silently carried over:

- `_validate_data_chunk_not_truncated()` parses a RIFF `data` chunk header
  directly — meaningless for a FLAC or MP3 container and must not be
  invoked (or must be made conditional) for non-WAV inputs.
- `extract_preserved_chunks()` is a RIFF/BWF metadata-preservation layer
  that exists to support STORY-001's export path (re-injecting metadata
  into a written WAV) — this story writes no audio and needs no chunk
  preservation at all. Reusing `ingest()` unmodified for reference/FLAC
  input risks either a spurious failure (if `extract_preserved_chunks`
  chokes on a non-RIFF file and its `InvalidWavError` is re-raised rather
  than swallowed, per ingest.py's current exception handling) or dead
  code being carried along for no reason.
- Error messages, type names (`InvalidWavError`), and docstrings throughout
  the ingest path hardcode "WAV" — cosmetic, but worth the architect
  deciding whether reference-track ingest is a genuinely separate,
  lighter-weight read path (no chunk preservation, no truncation-header
  check, generic format-agnostic errors) rather than a strained reuse of
  the export-oriented WAV ingest path.
- **MP3 decode is a separate, unresolved gap**: whether the installed
  `soundfile`/libsndfile build supports MP3 read depends on the libsndfile
  version (MP3 read support was added in libsndfile 1.1.0) — this needs
  verifying against the actual installed environment, not assumed either
  way. If it is not available, a decoder needs choosing (e.g. `pydub`/
  `audioread` via `ffmpeg`, or another library) — note that STORY-001's
  architecture explicitly rejected `pydub` for the **precision-critical
  mastering signal path** (bit-depth/precision round-trip risk); that
  rejection does not necessarily apply to a read-only analysis-only
  decode of a lossy reference file that is already lossy by construction,
  but the choice and its justification is for the architect, not decided
  here.
- **MP3 bitrate is a separate gap from MP3 decode.** Even where decode
  works, libsndfile does not expose the source bitrate — AC4 requires
  bitrate to be reported "where applicable." This needs either a
  dedicated metadata/tag reader or a separate probing step (e.g. `mutagen`,
  or parsing frame headers directly) — flagged for the architect. Whether
  bitrate reporting is a hard acceptance requirement or best-effort
  (i.e. is it acceptable to report "MP3, bitrate unknown" if a given file's
  metadata doesn't carry it, such as a VBR file with no clean average) is
  an open question — see below.
- **Given this story's important, but concretely narrower, need for
  code-path fidelity back to STORY-001 (see "Code-path identity"
  requirement below), any separate/lighter ingest path built for
  reference material must still route through the same underlying
  `analysis/*` measurement functions STORY-001 uses** (plain numpy array +
  sample rate signatures, per architecture.md §7) — only the file-reading
  layer (chunk preservation, truncation checks) may differ; the
  measurement functions themselves must not be forked or duplicated.

## Acceptance criteria

Restated from story.md for completeness (this document is meant to be
self-contained), with three additions (AC10–AC12) surfaced during this
requirements pass; the architect and QA agents should treat all of these as
authoritative alongside story.md itself.

1. Given a folder of reference tracks, the tool measures every file and
   reports: integrated LUFS, LRA, true peak (dBTP), crest factor/dynamic
   range, seven-band spectral balance, HF extension (with stability check),
   stereo width (overall correlation + per-band width), and mono
   compatibility (level change + cancellation check) per track.
2. The tool produces aggregate statistics (median, min, max) across the
   set for each metric in AC1.
3. The tool can measure a Suno export using the identical analysis code
   path as the reference tracks and present it side by side against the
   reference aggregate, so the gap is directly visible.
4. Source format (lossless vs. lossy, and bitrate where applicable) is
   detected and reported alongside every track's measurements.
5. HF-extension measurements from lossy sources are excluded from, or
   explicitly flagged in, the aggregate.
6. Loudness measurement is verifiable against a known-loudness test signal
   to within ±0.1 LU. (This reuses STORY-001's existing `loudness.py` —
   no new tolerance work needed, but the test-case-writer should confirm
   this tolerance still holds when the same function is called against
   FLAC/MP3-decoded input, not just WAV.)
7. True peak measurement uses oversampled detection and is demonstrably
   different from sample peak on a signal engineered to have inter-sample
   peaks. (Reuses STORY-001's `true_peak.py` — see the caveat above about
   the near-Nyquist residual's different practical significance for
   reference material; this AC is about the oversampled-vs-sample-peak
   *mechanism*, which is unchanged, not about the residual.)
8. Analysis does not modify or overwrite any input file. Reuse STORY-001's
   §4 non-destructive-handling pattern (SHA-256 hash of the input,
   read-only file access, hash re-verified at end of run) as the concrete,
   checkable form of this requirement — including for any newly-added
   MP3/FLAC decode path, which additionally must not write any decoded or
   intermediate audio buffer to disk anywhere (see legal/scope note below).
9. Output is both human-readable and machine-readable, so later stories
   can consume the targets programmatically. See "Machine-readable output"
   NFR below for what this must guarantee beyond just "valid JSON."
10. **(New.) Newly-introduced measurements have a stated, testable
    verification bar, not just an implementation.** AC6/AC7 above already
    pin loudness and true peak to a concrete tolerance against known
    signals — that same discipline must extend to every genuinely new
    measurement this story introduces, since none of them can lean on
    STORY-001's existing verification work:
    - **LRA** must be verifiable against published EBU Tech 3342 reference
      test material with known LRA values, to a stated tolerance (the
      tolerance value itself is for the architect/QA to set — not invented
      here).
    - **HF rolloff/extension** must be verifiable against a synthetic
      band-limited signal with a known, deliberately-engineered cutoff
      frequency.
    - **Per-band stereo width** must be verifiable against a synthetic
      signal with a known, engineered per-band width (e.g. mono at low
      frequencies, fully decorrelated at high frequencies).
    - **Mono-sum level change/cancellation** must be verifiable against a
      synthetic out-of-phase stereo pair with a known, calculable
      cancellation amount.
    Architecture.md §7's existing convention (every `analysis/*` function
    takes plain numpy arrays + sample rate, making synthetic-signal unit
    testing straightforward) already supports building these tests; this
    AC makes doing so a requirement rather than an implied nice-to-have.
11. **(New.) Code-path identity between STORY-001 and STORY-002 for shared
    metrics.** For any given WAV file, the measurements STORY-002's
    analysis path produces must be bit-identical (or identical within
    floating-point noise appropriate to the metric) to those STORY-001's
    stage [2] (pre-master analysis) would produce for the same file, for
    every metric the two stories share (LUFS, true peak, DR, existing
    stereo correlation). This is what makes AC3's "identical code path"
    claim independently testable rather than an unverified assertion, and
    it directly constrains the ingest-path-split decision flagged above:
    whatever the architect decides about a separate/lighter reference
    ingest layer, the underlying `analysis/*` measurement functions
    themselves must not fork or diverge between the two stories.
12. **(New.) Every reported aggregate statistic must carry its own N and
    the identity of the tracks that contributed to it, in both the
    human-readable and machine-readable output.** Because AC5 removes
    lossy tracks from the HF aggregate specifically, different metrics in
    the same report can legitimately be computed over different subsets of
    the reference set (e.g. LUFS median over all 7 tracks, HF-rolloff
    median over only the 2 lossless tracks). A bare aggregate number with
    no visible N is not distinguishable between these cases and would
    misrepresent confidence — this directly serves story.md's own framing
    that "the territory the set occupies," not a single number, is the
    target, which requires knowing how much territory (how many tracks)
    each aggregate figure actually reflects.

## Audio quality targets

This story does not itself impose new audio quality *targets* — it exists
to **derive** them from measurement of the reference set. No specific LUFS,
LRA, DR, or spectral-balance target numbers are specified by story.md, and
none are invented here. What is explicit:

- **Loudness measurement standard**: ITU-R BS.1770 (integrated LUFS),
  matching STORY-001's already-resolved standard — no new standard is being
  introduced for this metric.
- **Loudness range standard**: to be measured per EBU Tech 3342 / ITU-R
  BS.1770 loudness range definition (named here as the standard to build
  against; not invented).
- **True peak standard**: BS.1770-4 Annex 2 oversampled true peak, same
  method as STORY-001, with the residual/format caveats above carried
  forward explicitly into this story's reporting.
- **Dynamic range**: TT DR-meter (Pleasurize Music Foundation published
  spec), same as STORY-001, pending resolution of the crest-factor-vs-DR
  naming question above.
- **Spectral balance / HF extension / per-band stereo width**: no fixed
  target values exist yet for any of these — deriving them (as a median/
  range across the reference set) is this story's entire purpose. Do not
  treat any number appearing elsewhere in the codebase (e.g. STORY-001's
  -1.5/-3.0/-4.0 dB three-band reference curve) as validated ground truth
  for the new seven-band scheme — that curve is itself a "reasoned
  placeholder, not producer-verified" per architecture.md v1 §9 risk #1,
  and is a different band scheme in any case.
- **Sample rate / bit depth / channel handling**: must handle 44.1 kHz and
  48 kHz, mono and stereo, WAV and FLAC (per story.md's explicit NFR).
  MP3's native sample rates/bit-depths are whatever the source file
  carries — no additional constraint is placed on lossy source rates
  beyond what the chosen decode path supports. See "Mono reference tracks"
  note below for how a mono reference file should be handled in the
  stereo-metric aggregates specifically.

## Input/output assumptions

- **Reference input**: a folder of commercially-released reference audio
  files, WAV/FLAC (lossless) or MP3 (lossy), representing deep/melodic
  progressive house and melodic techno in the target style. Files are
  long-form (7+ minutes typical). The reference set should be 5+ tracks;
  lossless references are strongly preferred, with "even two or three
  lossless tracks alongside lossy ones" stated by story.md as sufficient
  for a trustworthy HF picture — see open question below on whether this
  is a hard gate or a warning.
- **Suno-export input (for the comparison in AC3)**: WAV, per STORY-001's
  existing scope — the asymmetry (lossy handling) is explicitly on the
  reference side only, per story.md.
- **Output**: a report covering per-track measurements, per-set aggregate
  statistics (each carrying its own N per AC12), and (when a Suno export
  is supplied) a side-by-side comparison — rendered in both a
  human-readable form and a machine-readable form. No audio is written by
  this story under any circumstance.
- **Mono reference tracks skew stereo aggregates and must be excluded from
  them.** `stereo_phase.py` currently short-circuits mono input to
  `overall_correlation=1.0`/`mono_compatible=True` with no per-window
  data — a degenerate, not a genuinely measured, value. Story.md's NFR
  requires the tool handle mono input without erroring, but a mono
  reference track contributing a synthetic 1.0 correlation and a
  trivial "no change" mono-sum result into the stereo-width/mono-
  compatibility aggregates would silently distort those medians/ranges.
  **Requirement:** mono reference tracks are measured and reported
  individually (all applicable non-stereo metrics still populate
  normally), but excluded from the stereo-width and mono-compatibility
  aggregate statistics specifically, with that exclusion reported the same
  way AC5's lossy-HF exclusion is (i.e. visible N, not silent).

## Explicit out-of-scope

- **No audio processing or mastering of any kind.** This story measures;
  it does not correct, EQ, limit, or otherwise modify any signal. STORY-001
  owns all processing.
- **No changes to STORY-001's actual mastering decisions or thresholds**
  (the -14.5/-13.5 LUFS band, -1 dBTP ceiling, DR floor rule, three-band
  EQ correction thresholds) as a direct effect of this story. Whether this
  story's derived reference-set targets should ever feed back into those
  STORY-001 values is a separate, future decision explicitly not made here
  (see open questions).
- **No reproduction, redistribution, or derivation of audio from the
  commercially-released reference tracks.** The tool reads and measures
  them only, per story.md's own note. This constrains the architect's
  decoder/caching choices directly: no decoded buffer, temporary WAV, or
  any other derived audio artifact from a reference track may be written
  to disk at any point in the pipeline, including as an implementation
  convenience for MP3 decode.
- **No selection of which specific commercial tracks form the reference
  set.** That is a product-owner decision — see open questions.
- **No sub-style splitting logic** (e.g. hypnotic/minimal vs. driving/
  melodic) unless and until the product owner decides this is needed —
  see open questions.
- **No changes to STORY-001's export/report format for the single-track
  mastering pipeline** as a side effect of this story's own new report
  renderer, beyond whatever shared code (e.g. `Measurements` type) is
  deliberately and explicitly extended. See non-functional requirements
  below for the regression-safety requirement this implies.

## Non-functional requirements

- **Per-track analysis speed**: a 7-minute reference track should complete
  measurement in **seconds, not minutes** — this is a materially tighter
  bar than STORY-001's own 5-minute-per-track budget, because this story
  runs analysis-only (no EQ/limiting/dither/export stages) and is expected
  to be run against a multi-track set, not a single file. State this
  explicitly as a *change* from STORY-001's NFR, not an inherited one.
- **Per-set processing budget**: since AC1/AC2 operate over the whole
  reference set (5+ tracks) plus optionally one Suno-export comparison
  track, an explicit whole-set time budget should be set by the architect
  (e.g. "under one minute for a 6-track set" as a reasonable extrapolation
  from the per-track "seconds" bar) — not specified numerically here since
  story.md does not give one; flagged so it isn't silently left unbounded.
- **Non-destructive guarantee**: reuse STORY-001's SHA-256 pre/post-run
  input-hash-match pattern (architecture.md §4) as the concrete,
  automatically-checkable implementation of AC8, extended to cover every
  new input format (FLAC, MP3) and confirming no derived-audio artifact
  from a reference track is ever written to disk (see out-of-scope note
  above).
- **Reproducibility**: given the same input files and config, repeated
  runs must produce identical measurement values and identical aggregate
  statistics — this mirrors STORY-001's AC10 reproducibility bar and
  should extend to any newly-introduced randomness-free logic (none of the
  new measurements described here have an inherent randomness source, but
  this should be confirmed rather than assumed once implemented, especially
  for library-driven decode paths like MP3 decoding, which can vary subtly
  across decoder versions/builds).
- **Machine-readable output must be a stable, versioned schema** — story.md
  states the explicit purpose is "so later stories can consume the targets
  programmatically." This is a real requirement, not decoration: the
  machine-readable report format needs a schema version field from the
  start, so that a later story consuming these targets has a documented
  contract to code against rather than an implicit, unversioned JSON shape
  that can silently change out from under it. Per AC12, this schema must
  include per-aggregate N/contributing-track-identity fields, not just the
  statistic values themselves.
- **No regression to STORY-001's existing test suite or report shape.**
  `analysis/types.py`'s `Measurements` dataclass is the shared pre/post
  shape already consumed by STORY-001's `report/builder.py` and
  `report/render.py`, and STORY-001 has an existing test suite (AC1–AC11,
  including reproducibility and a recommended golden-file report test).
  Any extension to `Measurements`, or to modules it depends on
  (`frequency_balance.py`, `stereo_phase.py`, `dynamic_range.py`), must
  leave STORY-001's existing tests and report reproducibility green. This
  is a hard constraint on how the architect chooses to extend the shared
  analysis layer (e.g. extend `Measurements` directly vs. introduce a
  separate reference-measurement type) — the choice itself is for the
  architect, not this document, but the non-regression requirement is not
  optional. AC11 (code-path identity) above is the concrete, testable form
  of this same constraint as it applies to measurement *values*
  specifically, not just test-suite pass/fail.

## Open questions — resolved 2026-08-01

All ten questions below are now resolved. Two (#1, #2) are process
resolutions, not technical ones — they concern which real commercial
records to use and are correctly left to the producer's own musical
judgment, never invented by this document. The remaining eight are
concrete technical/product decisions made here so the architect is
unblocked.

1. **Which specific commercial tracks form the reference set?** RESOLVED
   as a process decision, not a technical one: this document does not name
   candidate tracks (it has no basis to judge what represents this genre's
   "good" for the product owner, and story.md's own scope note forbids
   this tool from reproducing/deriving audio from named commercial works
   in a way that would make a hardcoded list appropriate). **Requirement:**
   the reference set is supplied at run time as an arbitrary folder path
   (AC1's "given a folder of reference tracks"); no track list is
   hardcoded anywhere in the implementation. Track selection remains a
   task for the producer to do before each run, same as picking which WAV
   to master in STORY-001.
2. **Should the reference set be split by sub-style?** RESOLVED: not in
   v1. A single reference set produces a single aggregate. Rationale: the
   NFR already requires 5+ tracks for a meaningful aggregate; splitting by
   sub-style before that set is even assembled would fragment an already-
   thin sample further, and story.md itself frames this as an open
   question rather than a stated requirement. **Requirement (forward-
   compatibility only):** each track's per-track report entry should carry
   an optional free-text tag/label field (e.g. filename-derived or
   producer-supplied), left unused for aggregation in v1, so a future story
   can add sub-style grouping without a schema break. No grouping logic is
   built now.
3. **Seven-band edge frequencies.** RESOLVED — the following bands are
   the requirement, chosen to align with (not silently diverge from)
   STORY-001's existing three-band scheme, so both schemes agree about
   shared territory:
   - Sub: 20–60 Hz
   - Low: 60–120 Hz (Sub+Low together = STORY-001's existing 20–120 Hz
     "thin low-end" band)
   - Low-mid: 120–500 Hz (contains STORY-001's existing 200–500 Hz
     "muddiness" band as a sub-range)
   - Mid: 500 Hz–2 kHz (identical to STORY-001's existing 500 Hz–2 kHz
     reference/baseline band — the 0 dB anchor both schemes already use)
   - High-mid: 2–5 kHz (identical to STORY-001's existing 2–5 kHz
     "harshness" band)
   - High: 5–10 kHz
   - Air: 10 kHz–Nyquist (i.e. up to 22.05 kHz at 44.1 kHz, 24 kHz at
     48 kHz — not hardcoded to a fixed upper bound, since Nyquist varies
     by source sample rate)
   **Requirement:** these edges are config-driven values (matching
   architecture.md's existing config-as-single-source-of-truth pattern),
   not hardcoded, so they can be revisited without a code change.
4. **Does the seven-band output replace, extend, or run alongside
   STORY-001's three-band reference curve?** RESOLVED: alongside, not a
   replacement. STORY-001's `progressive_house_124bpm.json` three-band
   curve continues to drive STORY-001's automatic EQ-correction
   thresholds unchanged; this story's seven-band output is a separate,
   descriptive/comparison artifact only. **Requirement:** this story must
   not modify `progressive_house_124bpm.json` or any STORY-001
   correction-threshold value as a side effect. Whether reference-set
   findings should ever inform a future recalibration of that file (via
   the existing `scripts/build_reference_curve.py` process) is explicitly
   deferred to a future story requiring its own explicit go-ahead — this
   story's completion does not trigger that recalibration automatically.
5. **Are reference-track true-peak figures trustworthy enough to be a
   target?** RESOLVED: report-only in v1, not target-setting. True-peak
   figures are measured and shown per track and in aggregates like every
   other metric, but the report must carry a standing caveat (per the
   "Reused with a caveat" section above) that these figures are
   informational, not validated to target-setting precision, given the
   documented near-Nyquist residual. Revisit only once the TC-024-class
   external cross-validation already flagged as an open STORY-001 residual
   exists — not a blocker for this story.
6. **Mixed sample rates breaking HF-extension aggregation.** RESOLVED:
   report HF-extension aggregates **per sample-rate subset**, not blended
   across rates. A 44.1 kHz track's rolloff and a 48 kHz track's rolloff
   are not comparable on a single shared median/range once either
   approaches its own Nyquist ceiling. **Requirement:** the aggregate
   section reports HF-extension median/min/max separately per sample rate
   present in the set (e.g. "44.1 kHz subset (N=4): ..." / "48 kHz subset
   (N=2): ..."), each carrying its own N per AC12 — never a single
   figure silently mixing both. Normalizing rolloff to a fraction of
   Nyquist was considered and rejected: it would make a 44.1 kHz track's
   19 kHz rolloff and a 48 kHz track's 20.7 kHz rolloff appear
   artificially equivalent (both ~86% of Nyquist) when they are not the
   same absolute frequency, which is what a producer actually cares about.
7. **HF aggregate behavior when lossless N is 0 or low.** RESOLVED as a
   graduated warning, not a hard gate — story.md's own "even two or three
   lossless tracks is enough" phrasing implies a soft confidence bar, not
   a refusal threshold:
   - N=0 lossless tracks: omit the HF-extension aggregate entirely (report
     "no lossless references available for HF extension" rather than a
     number derived from zero trustworthy sources).
   - N=1–2 lossless tracks: report the aggregate, but flag it explicitly
     as low-confidence (below story.md's own stated "two or three" bar).
   - N≥3 lossless tracks: report normally, unflagged.
   These thresholds are config-driven, not hardcoded, so they can be
   tuned without a code change.
8. **"Crest factor / dynamic range" — one metric or two?** RESOLVED: one
   metric. Report TT DR only, using "crest factor / dynamic range" as
   story.md's own loose/interchangeable phrasing for it — consistent with
   how STORY-001's original story.md used the same two terms
   interchangeably for the same single measurement. **Requirement:** no
   separate broadband crest-factor statistic is built for v1; if a future
   story needs the distinction, that is a new, explicitly-scoped
   requirement, not an implicit gap in this one.
9. **MP3 bitrate: hard requirement or best-effort?** RESOLVED:
   best-effort. **Requirement:** where a clean bitrate value cannot be
   determined (e.g. a VBR file with no reliable average-bitrate tag), the
   report must show "bitrate unknown" rather than fail the run or fabricate
   a value. This matches the same non-blocking posture the rest of this
   story's format-detection logic takes — measurement proceeds, gaps are
   surfaced, nothing is silently invented.
10. **Suspected transcode (lossless container, encoder-typical rolloff):
    exclude or flag?** RESOLVED, and deliberately different from the
    known-lossy case for a stated reason: **flag, do not auto-exclude.**
    A declared-lossy (MP3) file is excluded from the HF aggregate outright
    (source format point 2) because its lossy status is a known fact, not
    a heuristic. A lossless-container file with an encoder-typical rolloff
    is only a *suspected* transcode — HF-rolloff shape is corroborating
    evidence, not certain proof (a legitimately mastered, deliberately
    band-limited track is possible, if unusual for this genre). Silently
    excluding it on a heuristic risks discarding a genuine lossless
    reference; the tool instead surfaces it prominently ("suspected
    lossy-source transcode — review before treating as a clean reference")
    and leaves it in the aggregate, so the producer makes the final call
    rather than the tool making it invisibly.

## Revision history

- v1 (2026-08-01): Initial requirements, based on story.md (STORY-002,
  no defects.md present for this story). Read STORY-001's architecture.md
  (v5) and implementation (`analysis/loudness.py`, `true_peak.py`,
  `dynamic_range.py`, `frequency_balance.py`, `stereo_phase.py`,
  `io/ingest.py`, `analysis/types.py`, `scripts/build_reference_curve.py`)
  in full before writing, per this story's explicit "reuse the existing
  analysis stage, do not duplicate" instruction. Incorporated advisor
  review before finalizing: added AC10 (verification bar for every
  genuinely new measurement — LRA, HF rolloff, per-band width, mono-sum
  level change), AC11 (code-path identity between STORY-001 and STORY-002
  for shared metrics), AC12 (every aggregate statistic must carry its N
  and contributing-track identity); added source-format-handling point 6
  (lossless-container transcode detection via HF-rolloff corroboration,
  with corresponding open question 10); added the mono-reference-track
  stereo-aggregate exclusion requirement under "Input/output assumptions."
- v2 (2026-08-01): All ten open questions resolved (see above). Seven-band
  edges chosen to align exactly with STORY-001's existing three-band
  scheme at their shared boundaries (500 Hz–2 kHz mid band, 2–5 kHz
  high-mid band). Seven-band output confirmed to run alongside, not
  replace, STORY-001's three-band correction curve. HF-extension
  aggregation resolved to per-sample-rate reporting, never blended.
  Lossless-count confidence thresholds set at N=0 (omit)/N=1–2
  (flag-low-confidence)/N≥3 (normal), config-driven. Crest-factor/DR
  resolved to a single TT DR metric. MP3 bitrate resolved to best-effort.
  Suspected-transcode handling resolved to flag-not-exclude, distinct from
  the known-lossy exclusion. Unblocked for architecture.
