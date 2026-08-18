# STORY-002: Reference track analysis — Test Cases

Status: v2. Based on requirements.md v2 (all ten open questions resolved,
2026-08-01) and architecture.md v3 (DEF-101/DEF-102/DEF-103 resolved in v2;
DEF-110 resolved in v3, not itself a test-case-writer concern). This
revision corrects staleness against the shipped implementation, per
defects.md DEF-106/DEF-107/DEF-108 — see "Revision history" at the end for
the full list of what changed and why.

Test IDs continue from STORY-001's `test-cases.md` (which used TC-001–
TC-152) starting at **TC-200**, so IDs stay globally unique across both
stories, since both implementations live in the same
`stories/STORY-001/implementation/` codebase and could share a test run.

## Governing rule for expected values in this document

Requirements.md is explicit that this story **derives** mastering targets
from real reference tracks — it does not itself impose any LUFS/LRA/DR/
spectral-balance target. Consequently every expected value below is one of
three kinds, and nothing else:

1. **Detector recovers a known synthetic input** — a closed-form value
   because the test constructs the signal and can hand-calculate the
   answer (e.g. a Butterworth-filtered white-noise HF-rolloff fixture, a
   calibrated anti-phase pair).
2. **Structural/report assertions** — N present, format label rendered
   inline, exclusion reason-coded, `schema_version` present — checkable
   regardless of what any measurement value turns out to be.
3. **Rule behavior** — this track is excluded, that one is flagged-not-
   excluded, this subset is split from that one, per requirements.md's
   resolved open questions.

No test case asserts "reference set median LUFS should be approximately
X" or any equivalent invented target. Where architecture.md §13 supplies a
config default (HF-rolloff −6 dB / 500 Hz test tolerance, LRA 1.0 LU
tolerance, mono-cancellation excess −3 dB — compared against each
formula's own decorrelated floor, not a raw dB reading; see the DEF-101/
DEF-106 correction in §9.4 below — transcode slope 24 dB/octave), it is
used as the expected value **only** for tests of the detector's own
correctness against a synthetic fixture built to that default, and is
explicitly labelled "architect-reasoned, not producer-verified" — the same
posture STORY-001's test-cases.md took toward its three-band reference
curve.

Scope note (mirrors STORY-001's own scope note): per architecture.md §12,
every new `analysis/*` function takes plain numpy arrays + sample rate +
config, not file paths. Test cases are written to run at module level
(preferred for DSP correctness — faster, more precise root-causing) or at
the `reference_analysis.pipeline.analyze_set()` level where the concern is
inherently pipeline-level (aggregation, exclusion, report shape,
non-destructive guarantee, performance). Each case's **Level** is noted.

Numbering map:

| Range | Section |
|---|---|
| TC-200s | AC1 — per-track measurement report |
| TC-220s | AC2 — set aggregate statistics |
| TC-240s | AC3 — Suno-export side-by-side comparison |
| TC-250s | AC4 — source format/provenance detection |
| TC-260s | AC5 — lossy-source HF exclusion |
| TC-270s | AC6/AC7 — reused STORY-001 metrics against FLAC/MP3-decoded input |
| TC-280s | AC8 — non-destructive guarantee |
| TC-290s | AC9 — human- and machine-readable output |
| TC-300s | AC10 — verification bars for new measurements |
| TC-330s | AC11 — code-path identity with STORY-001 |
| TC-340s | AC12 — N / contributing-tracks on every aggregate |
| TC-350s | Edge case inputs |
| TC-370s | Failure modes |
| TC-380s | Non-functional requirements (performance, memory, reproducibility) |
| TC-390s | STORY-001 non-regression |

---

## 1. AC1 — Per-track measurement report

Covers: "Given a folder of reference tracks, the tool measures every file
and reports: integrated LUFS, LRA, true peak (dBTP), crest factor/dynamic
range, seven-band spectral balance, HF extension (with stability check),
stereo width (overall correlation + per-band width), and mono
compatibility (level change + cancellation check) per track."

### TC-200 — Full per-track report contains every AC1 field, stereo track
- **Type**: functional
- **Level**: pipeline (`reference_analysis.pipeline.analyze_track()` or
  `analyze_set()` with a one-file folder)
- **Covers**: AC1
- **Preconditions**: synthetic stereo WAV, 44.1 kHz/24-bit, 60 s, pink
  noise with non-trivial per-band energy so no field reads as a degenerate
  zero.
- **Steps**: Run per-track reference analysis.
- **Expected result**: `ReferenceMeasurements` is returned with non-null
  values for: `core.integrated_lufs`, `lra_lu.lra`, `core.true_peak_dbtp`,
  `dynamic_range_db_exact` and `core.dynamic_range_db`, `seven_band` (all
  seven band dB-relative values populated: sub, low, low_mid, mid,
  high_mid, high, air), `hf_extension.rolloff_hz` and `.stable`,
  `core.overall_correlation`, `per_band_stereo_width` (7 band values),
  `mono_sum.level_change_db` and per-band `.cancellation` flags,
  `provenance` (container/lossless/bitrate/decoder/suspected_transcode).
  No exception raised.

### TC-201 — Mono reference track produces a complete report with stereo-only fields explicitly null/N-A
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC1, Input/output assumptions "mono reference tracks" note
- **Preconditions**: synthetic mono WAV, 44.1 kHz, 60 s, pink noise.
- **Steps**: Run per-track reference analysis.
- **Expected result**: all non-stereo AC1 fields populate normally
  (LUFS, LRA, true peak, DR, seven-band, HF-extension). `per_band_stereo_width`
  and `mono_sum` are `None` (per §3's dataclass — "`None` if mono"), not a
  crash and not a degenerate `1.0`/"no change" value. `core.overall_correlation`
  follows STORY-001's existing mono short-circuit behavior (reused as-is,
  unmodified) — this test does not re-litigate that STORY-001 behavior,
  only confirms it surfaces unchanged through the reference report.

### TC-202 — 48 kHz stereo track, all AC1 fields populate correctly at the non-default sample rate
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC1, "must handle 44.1 kHz and 48 kHz" audio-quality target
- **Preconditions**: synthetic stereo WAV, 48 kHz/24-bit, 60 s, pink noise.
- **Steps**: Run per-track reference analysis.
- **Expected result**: same field-completeness assertion as TC-200; `air`
  band upper edge resolves to 24 000 Hz (not hardcoded to 22 050 Hz); no
  Nyquist-related exception or silent truncation.

### TC-203 — FLAC input produces the same field set as WAV input
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC1, "must handle ... WAV and FLAC"
- **Preconditions**: the TC-200 fixture, additionally encoded losslessly to
  FLAC (bit-identical decode expected).
- **Steps**: Run per-track reference analysis against the FLAC file.
- **Expected result**: identical field completeness to TC-200; measurement
  values equal to the WAV-sourced measurements within float tolerance
  (1e-6 relative — FLAC is lossless, so this is a decode-path check, not a
  format-tolerance check).

### TC-204 — MP3 (320 kbps) input produces the same field set as WAV input
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC1, source format handling point 4 ("loudness, LRA, DR,
  spectral balance, stereo width treated as reliable from 320 kbps MP3")
- **Preconditions**: the TC-200 fixture, encoded to MP3 CBR 320 kbps.
- **Steps**: Run per-track reference analysis against the MP3 file.
- **Expected result**: all AC1 fields populate (including HF-extension,
  which is measured and reported per-track even though it will be
  excluded from the aggregate per AC5 — exclusion is an aggregation-stage
  rule, not a per-track suppression). `provenance.lossless == False`,
  `provenance.container == "mp3"`.

---

## 2. AC2 — Set aggregate statistics

### TC-220 — Median/min/max computed correctly across a small hand-computable set
- **Type**: functional
- **Level**: pipeline (`[R3]` aggregation stage, or `aggregate.py` module
  level with hand-constructed per-track `ReferenceMeasurements` stand-ins)
- **Covers**: AC2
- **Preconditions**: 5 synthetic tracks with known, hand-computed
  integrated LUFS values (e.g. -18, -16, -14, -12, -10 LUFS via calibrated
  tone level).
- **Steps**: Run set aggregation.
- **Expected result**: LUFS aggregate reports median = -14.0, min = -18.0,
  max = -10.0 (exact, since the per-track inputs are exact by
  construction).

### TC-221 — Every AC1 metric has a corresponding aggregate entry
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC2
- **Preconditions**: 5-track synthetic set, all stereo, all lossless, all
  44.1 kHz (no exclusion rules triggered, so this isolates "does every
  metric get an aggregate" from "are exclusions correct" — see TC-25x/26x
  for exclusion-specific cases).
- **Steps**: Run `analyze_set()`.
- **Expected result**: `aggregates` list contains one `AggregateStat` per
  AC1 metric (LUFS, LRA, true peak, DR, each of the seven spectral bands,
  HF-extension, overall correlation, each of the seven per-band widths,
  mono-sum level change) — no metric silently missing an aggregate entry.

### TC-222 — Aggregate statistics are deterministic given the same input set
- **Type**: regression
- **Level**: pipeline
- **Covers**: AC2, reproducibility NFR
- **Preconditions**: TC-221's 5-track set, run twice.
- **Steps**: Run `analyze_set()` twice against the identical folder/config.
- **Expected result**: every `AggregateStat` field (median/min/max/n/
  contributing_tracks/excluded) is bit-identical across the two runs.

---

## 3. AC3 — Suno-export side-by-side comparison

### TC-240 — Suno-export WAV measured and compared against the reference aggregate
- **Type**: functional
- **Level**: pipeline (`analyze_set(reference_dir, suno_export_path=...)`)
- **Covers**: AC3
- **Preconditions**: 5-track lossless reference set (as TC-221) plus one
  synthetic Suno-export-style WAV (44.1 kHz/24-bit, deliberately at a
  different LUFS/DR than the reference set's median).
- **Steps**: Run `analyze_set()` with both arguments supplied.
- **Expected result**: `ReferenceSetReport.comparison` is populated
  (non-`None`) and contains the Suno-export track's own per-track
  `ReferenceMeasurements` alongside a reference to the `[R3]` aggregate,
  such that every AC1 metric can be read side by side (export value vs.
  reference median/min/max) directly from the comparison object without
  the report renderer needing extra lookups.

### TC-241 — Comparison omitted (not errored) when no Suno-export path is supplied
- **Type**: functional / edge case
- **Level**: pipeline
- **Covers**: AC3 (implicit "optional" framing), architecture.md §9
  (`comparison: Optional[dict]`)
- **Preconditions**: same 5-track reference set, no `suno_export_path`.
- **Steps**: Run `analyze_set(reference_dir)`.
- **Expected result**: `ReferenceSetReport.comparison is None`; the report
  otherwise completes normally with per-track and aggregate sections.

### TC-242 — Comparison track uses the identical [R2] analysis path (ties to AC11)
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC3, AC11
- **Preconditions**: the TC-240 Suno-export WAV.
- **Steps**: Measure the export WAV (a) via `[R4]`'s comparison path and
  (b) directly via `[R2]`'s per-track analysis function called standalone
  on the same file.
- **Expected result**: field-for-field identical `ReferenceMeasurements` —
  confirms `[R4]` is report-assembly only, introducing no measurement
  divergence of its own, per architecture.md §1's "this is report-assembly
  only, not a new measurement" framing.

---

## 4. AC4 — Source format/provenance detection

### TC-250 — WAV file reports lossless, no bitrate field
- **Type**: functional
- **Level**: module (`io/reference_ingest.py`)
- **Covers**: AC4, source format handling point 1
- **Preconditions**: synthetic WAV, any valid PCM subtype.
- **Steps**: Ingest via `ingest_reference_track()`.
- **Expected result**: `provenance.container == "wav"`,
  `provenance.lossless == True`, `provenance.bitrate_kbps is None`
  (bitrate is meaningless for lossless PCM — not "unknown," genuinely
  not-applicable; the report should render this distinctly from MP3's
  "bitrate unknown" case, see TC-253).

### TC-251 — FLAC file reports lossless
- **Type**: functional
- **Level**: module
- **Covers**: AC4
- **Preconditions**: synthetic FLAC file.
- **Steps**: Ingest.
- **Expected result**: `provenance.container == "flac"`,
  `provenance.lossless == True`.

### TC-252 — MP3 file (clean CBR tag) reports lossy with a bitrate value
- **Type**: functional
- **Level**: module
- **Covers**: AC4, resolved open question #9
- **Preconditions**: synthetic MP3, CBR 320 kbps, clean header/tag.
- **Steps**: Ingest.
- **Expected result**: `provenance.container == "mp3"`,
  `provenance.lossless == False`, `provenance.bitrate_kbps == 320`
  (± whatever rounding the active bitrate-reading path uses — assert
  exact 320 for a clean CBR tag; do not assert exactness for VBR, see
  TC-253).

### TC-253 — MP3 with no reliable bitrate tag (e.g. VBR, no Xing/VBRI header) reports "bitrate unknown", run does not fail
- **Type**: edge case
- **Level**: module
- **Covers**: AC4, resolved open question #9 (best-effort, never fabricated, never blocking)
- **Preconditions**: synthetic MP3 encoded VBR with its Xing/VBRI header
  stripped (or otherwise constructed so `mutagen`/`ffprobe` cannot report
  a clean average bitrate).
- **Steps**: Ingest.
- **Expected result**: `provenance.bitrate_kbps is None`, and the
  human-readable report renders this specific field as "bitrate unknown"
  (distinct string from the WAV/FLAC not-applicable case in TC-250 — open
  question: confirm with the architect/QA whether these two `None` cases
  should be schema-distinguishable, e.g. a separate
  `bitrate_status: "not_applicable" | "unknown"` field, since the
  machine-readable schema in §9 currently models both as the same
  `Optional[int]` — **flagged as an open question, not asserted either
  way**). Run completes without error; track is not excluded from any
  aggregate on account of unknown bitrate.

### TC-254 — Source format label renders inline with every per-track figure, not only in a separate table
- **Type**: functional (report-shape)
- **Level**: pipeline (Markdown renderer)
- **Covers**: AC4, source format handling point 5
- **Preconditions**: a 3-track set mixing WAV, FLAC, and MP3.
- **Steps**: Render the Markdown report; inspect the per-track section for
  each of the three tracks.
- **Expected result**: each track's own measurement block/row visibly
  carries its format label (e.g. "MP3, 320 kbps" / "WAV, lossless")
  adjacent to its values, not only in a separate provenance-only table —
  a reader looking at one track's numbers cannot miss its source format.

---

## 5. AC5 — Lossy-source HF exclusion

### TC-260 — MP3 track excluded from the HF-extension aggregate but still reported per-track
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC5
- **Preconditions**: 4 lossless (WAV/FLAC) + 1 MP3 track, all 44.1 kHz.
- **Steps**: Run `analyze_set()`.
- **Expected result**: the 44.1 kHz HF-extension `AggregateStat` has
  `n == 4` and `contributing_tracks` lists only the 4 lossless tracks; the
  MP3 track appears in `excluded` with a reason string identifying the
  lossy-source exclusion (distinct wording from the mono exclusion, see
  TC-262). The MP3 track's own per-track `hf_extension.rolloff_hz` is
  still populated in its individual report entry (AC1 requires it be
  reported per-track regardless of aggregate membership).

### TC-261 — MP3 track is NOT excluded from non-HF aggregates
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC5, source format handling point 4
- **Preconditions**: the TC-260 set.
- **Steps**: Run `analyze_set()`.
- **Expected result**: the LUFS, LRA, DR, seven-band, and mono-sum
  aggregates all show `n == 5` including the MP3 track — confirms the
  exclusion is scoped to HF-extension specifically, per requirements.md
  point 4's explicit "no special flagging required for these specific
  metrics from a lossy source."

### TC-262 — Lossless-count confidence thresholds: N=0 omits the aggregate entirely
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC5, resolved open question #7
- **Preconditions**: a set of 5 MP3-only tracks (0 lossless).
- **Steps**: Run `analyze_set()`.
- **Expected result**: no HF-extension `AggregateStat` entry is present
  for this sample-rate subset — or, if the schema always emits an entry,
  it is explicitly marked with a reason ("no lossless references
  available for HF extension") and no numeric median/min/max is
  presented. Test asserts whichever shape the implementation chose is
  unambiguous — no numeric figure derived from zero trustworthy sources.

### TC-263 — Lossless-count confidence thresholds: N=1 flags low-confidence
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC5, resolved open question #7
- **Preconditions**: 1 lossless + 4 MP3 tracks, all 44.1 kHz.
- **Steps**: Run `analyze_set()`.
- **Expected result**: HF-extension aggregate is present with `n == 1`
  and a `low_confidence: True`-equivalent flag; rendered Markdown text
  visibly states low confidence, not just a bare "N=1" a reader could
  overlook.

### TC-264 — Lossless-count confidence thresholds: N=2 flags low-confidence
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC5, resolved open question #7
- **Preconditions**: 2 lossless + 3 MP3 tracks, all 44.1 kHz.
- **Steps**: Run `analyze_set()`.
- **Expected result**: HF-extension aggregate present, `n == 2`,
  low-confidence flag set — confirms the boundary is inclusive of 2, per
  the "N=1–2" resolved range.

### TC-265 — Lossless-count confidence thresholds: N=3 reports normally, unflagged
- **Type**: functional (boundary)
- **Level**: pipeline
- **Covers**: AC5, resolved open question #7
- **Preconditions**: 3 lossless + 2 MP3 tracks, all 44.1 kHz.
- **Steps**: Run `analyze_set()`.
- **Expected result**: HF-extension aggregate present, `n == 3`, no
  low-confidence flag — confirms the N=2/N=3 boundary is drawn exactly
  where resolved open question #7 specifies, using the config-driven
  threshold (per architecture.md §11, this must be settable to exactly 2
  in test config to hit this boundary cheaply).

### TC-266 — Mixed sample rates: HF-extension aggregated per-rate subset, never blended
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC5 interaction with resolved open question #6
- **Preconditions**: 4 lossless tracks at 44.1 kHz + 2 lossless tracks at
  48 kHz (6 lossless total, no MP3).
- **Steps**: Run `analyze_set()`.
- **Expected result**: two separate HF-extension `AggregateStat` entries
  are produced — "44.1 kHz subset, N=4" and "48 kHz subset, N=2" — each
  with its own median/min/max and its own N; no single blended figure
  covering all 6 tracks exists anywhere in the output.

### TC-267 — Interaction fixture: mono MP3 track at a minority sample rate inside a mixed set
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC5, resolved open questions #6/#7, mono-exclusion note
  (Input/output assumptions) — exercising all three exclusion rules at once
- **Preconditions**: 4 lossless stereo 44.1 kHz tracks + 1 lossless stereo
  48 kHz track + 1 lossy (MP3) **mono** track at 48 kHz.
- **Steps**: Run `analyze_set()`.
- **Expected result**: the mono MP3 track (a) is excluded from the
  HF-extension aggregate on lossy grounds (not the 48 kHz subset, since
  it never qualifies as a lossless contributor to any subset), (b) is
  excluded from the stereo-width and mono-compatibility aggregates on
  mono grounds, (c) still contributes normally to LUFS/LRA/DR/seven-band
  aggregates, (d) appears in `excluded` with *two* distinct reason
  entries (lossy-HF and mono-stereo), not a single conflated reason
  string, and (e) all other exclusion/subsetting behavior for the
  remaining 5 tracks is unaffected by this track's presence.

---

## 6. AC6/AC7 — Reused STORY-001 metrics against FLAC/MP3-decoded input

Covers AC6 (loudness verifiable to ±0.1 LU) and AC7 (true peak
demonstrably different from sample peak via oversampled detection) —
these AC numbers are reused verbatim from STORY-001 but requirements.md
explicitly asks the tolerance be reconfirmed against FLAC/MP3-decoded
input specifically, not just WAV.

**Fixture note (v2, DEF-108 correction)**: TC-270–TC-273 below use a
genuinely **mono (single-channel)** calibration tone, not "dual-mono
stereo" as v1 specified. This matters because BS.1770's channel-*summed*
convention gives two different, both-correct answers for the same
per-channel RMS depending on channel count: STORY-001's own
`test_tc010` (`stories/STORY-001/implementation/tests/
test_ac2_loudness.py`) uses a genuinely mono buffer at -20 dBFS RMS and
gets -20.0 LUFS; STORY-001's separate `test_tc010b`
(`bs1770_dual_mono_stereo_reads_plus3db_channel_sum`, same file)
constructs a **dual-mono stereo** (L=R) buffer at the same -20 dBFS
per-channel RMS and correctly asserts it reads `-20.0 + 3.01 ≈ -16.99`
LUFS. v1 of this document named "dual-mono stereo" as the precondition
but quoted TC-010's mono-derived -20.0 LUFS expected value and rationale
— an internal contradiction, since TC-010's rationale does not transfer
to a dual-mono-stereo precondition. Fixed here by matching the
precondition to the stated expected value (mono), which is also what the
shipped `tests/test_ref_ac6_ac7_reused_metrics.py::test_tc270`–
`test_tc273` already use via their `calibrated_tone_mono()` helper —
**do not "fix" this back to dual-mono stereo**; if a dual-mono-stereo
fixture is ever wanted here, its expected value must be -16.99 LU, not
-20.0 LU, per `test_tc010b`'s own convention.

### TC-270 — Loudness calibration tone, WAV source, reproduces STORY-001's ±0.1 LU tolerance
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/loudness.py` via `reference_ingest.py`)
- **Covers**: AC6
- **Preconditions**: 1 kHz sine, **mono (single-channel)**, 44.1 kHz,
  RMS = -20.00 dBFS, ≥10 s, saved as WAV.
- **Steps**: Ingest via `reference_ingest.py`, measure integrated LUFS.
- **Expected result**: -20.0 ± 0.1 LU (matches STORY-001 `test_tc010`'s
  own tolerance and rationale — K-weighting ≈ 0 dB near 1 kHz; see the
  fixture note above for why this must be mono, not dual-mono stereo).

### TC-271 — Loudness calibration tone, FLAC source, same ±0.1 LU tolerance holds
- **Type**: audio-quality
- **Level**: module
- **Covers**: AC6
- **Preconditions**: TC-270's mono tone, losslessly encoded to FLAC.
- **Steps**: Ingest via `reference_ingest.py`, measure integrated LUFS.
- **Expected result**: -20.0 ± 0.1 LU — confirms lossless-container decode
  introduces no measurable loudness error, as expected for a lossless
  format, but stated as its own explicit test per requirements.md's ask
  rather than assumed from the WAV case.

### TC-272 — Loudness calibration tone, MP3 (320 kbps) source, tolerance re-verified
- **Type**: audio-quality
- **Level**: module
- **Covers**: AC6
- **Preconditions**: TC-270's mono tone, encoded MP3 CBR 320 kbps.
- **Steps**: Ingest via `reference_ingest.py` (whichever decode tier the
  runtime probe selects), measure integrated LUFS.
- **Expected result**: -20.0 ± 0.1 LU still holds at 320 kbps — confirmed
  empirically (defects.md DEF-109): measured 320 kbps deviation is 0.035
  LU, within tolerance. If a future re-measurement finds it does not hold,
  this is a genuine finding to report, not a test to silently loosen.

### TC-273 — Loudness calibration tone, MP3 (128 kbps) source, tolerance checked at a lower bitrate
- **Type**: audio-quality / edge case
- **Level**: module
- **Covers**: AC6
- **Preconditions**: TC-270's mono tone, encoded MP3 CBR 128 kbps.
- **Steps**: Ingest, measure integrated LUFS.
- **Expected result**: report the actual deviation from -20.0 LUFS; flag
  if it exceeds ±0.1 LU. **Already measured and recorded** (defects.md
  DEF-109, a finding not a defect): 128 kbps deviates 0.481 LU, exceeding
  the ±0.1 LU tolerance — confirms 128 kbps is outside the "reliable"
  bitrate range requirements.md names (320 kbps only), as this test was
  designed to check. No further action required; this is the expected,
  recorded outcome of the test, not an open result.

### TC-274 — True peak demonstrably differs from sample peak, WAV source (mechanism check, reused unmodified)
- **Type**: audio-quality
- **Level**: module (`analysis/true_peak.py` via `reference_ingest.py`)
- **Covers**: AC7
- **Preconditions**: synthetic signal engineered to have an inter-sample
  peak (e.g. a 15 kHz sine at 44.1 kHz timed so the true waveform peak
  falls between two sample points, per STORY-001's own equivalent
  fixture), saved as WAV.
- **Steps**: Measure both sample peak (plain `max(abs(x))` in dBFS) and
  true peak (oversampled, dBTP) on the same buffer.
- **Expected result**: dBTP > sample-peak dBFS by a measurable margin
  (mechanism check only — this AC is about oversampled-vs-sample-peak
  detection working, not about the near-Nyquist residual's magnitude,
  per requirements.md AC7's own scoping note).

### TC-275 — True peak from MP3-decoded source is flagged as approximate, with the correct error direction stated
- **Type**: functional (report-content)
- **Level**: pipeline
- **Covers**: AC7, "Reused with a caveat" (MP3 true-peak bias direction)
- **Preconditions**: any MP3 track in a reference set.
- **Steps**: Render the per-track report entry for the MP3 track's true
  peak figure.
- **Expected result**: the report text adjacent to that track's dBTP value
  states plainly that (a) MP3-decoded true peak carries a lossy-decode
  bias that pushes the reading *up* (inter-sample peaks introduced by
  decoding) and (b) the near-Nyquist metering residual biases readings
  *down*, and that these are stated as two separate, non-netted
  directions — not silently combined into a single adjusted figure.

---

## 7. AC8 — Non-destructive guarantee

### TC-280 — WAV input hash unchanged after a full reference-set run
- **Type**: functional (integrity)
- **Level**: pipeline
- **Covers**: AC8
- **Preconditions**: a reference folder containing at least one WAV file.
- **Steps**: Record SHA-256 of the WAV before the run; run `analyze_set()`;
  re-hash after.
- **Expected result**: hashes match exactly; no
  `NonDestructiveIntegrityError` raised.

### TC-281 — FLAC input hash unchanged after a full reference-set run
- **Type**: functional (integrity)
- **Level**: pipeline
- **Covers**: AC8
- **Preconditions**: a reference folder containing at least one FLAC file.
- **Steps**: as TC-280, for the FLAC file.
- **Expected result**: hashes match exactly.

### TC-282 — MP3 input hash unchanged after a full reference-set run
- **Type**: functional (integrity)
- **Level**: pipeline
- **Covers**: AC8
- **Preconditions**: a reference folder containing at least one MP3 file.
- **Steps**: as TC-280, for the MP3 file, run against whichever decode
  tier the runtime probe selects.
- **Expected result**: hashes match exactly.

### TC-283 — No decoded/intermediate audio artifact written to disk (temp-directory snapshot)
- **Type**: functional (integrity) / non-functional
- **Level**: pipeline
- **Covers**: AC8, requirements.md out-of-scope note ("no decoded buffer,
  temporary WAV, or any other derived audio artifact ... may be written to
  disk at any point")
- **Preconditions**: a reference set including at least one MP3 file,
  routed through whichever decode tier (0/1/2) is live in the test
  environment per §6's runtime probe.
- **Steps**: Snapshot the OS temp directory's contents (file list +
  mtimes) immediately before the run; run `analyze_set()`; snapshot again
  immediately after.
- **Expected result**: no new files persist in the temp directory
  attributable to this run. If the tier-2 FFmpeg subprocess path is not
  reachable on the current test machine (probe selects tier 0/1), mark
  this case for tier 2 as skipped-not-failed and note which tier was
  actually exercised (per architecture.md §12's testability guidance);
  do not treat an unreachable tier as a passing assertion about it.

### TC-284 — One corrupted file mid-set does not compromise integrity checking of the remaining files
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC8 interaction with the "one bad file must not abort the
  set" architecture-level inference (§1/§7)
- **Preconditions**: a 5-file folder where one file is truncated/corrupt.
- **Steps**: Run `analyze_set()`; re-hash the 4 good files after the run.
- **Expected result**: the 4 good files' hashes are unchanged; the corrupt
  file appears in `failures` with path + reason; no
  `NonDestructiveIntegrityError` is raised for the corrupt file (it was
  never successfully ingested, so there is nothing to re-verify against —
  confirm the implementation does not attempt to hash-check a file it
  never read).

**Note (v2)**: AC8's actual enforcement mechanism — a run-completion
re-hash of every successfully-ingested file — was found missing from the
shipped `reference_analysis/pipeline.py` (defects.md DEF-105) and has
since been fixed. TC-280/281/282/284 as written above assert "hash
unchanged after a normal run," which is necessary but was not, by itself,
sufficient to catch DEF-105 (it passes trivially whether or not any
re-verification mechanism exists, since nothing tampers with the file in
these tests). The actual regression guard for the re-hash mechanism
itself is `tests/test_ref_ac8_nondestructive.py::
test_ref_hash_reverification_mechanism_present` (a tamper-after-ingest
fixture, asserting `NonDestructiveIntegrityError` is raised) — this is
not itself renumbered into the TC-28x series here since it was added
directly as regression automation, but is flagged so a future reader of
this document knows the mechanism-presence check exists and where.

---

## 8. AC9 — Human- and machine-readable output

### TC-290 — Markdown report renders per-track, aggregate, and (when present) comparison sections
- **Type**: functional
- **Level**: pipeline (`reference_render.py`)
- **Covers**: AC9
- **Preconditions**: TC-240's 5-reference + 1-Suno-export set.
- **Steps**: Render Markdown.
- **Expected result**: document contains a per-track section (one block
  per track, each carrying inline format label per TC-254), an aggregate
  section (each row carrying N per TC-340s), and a comparison section
  (export figure vs. reference median/min/max, side by side).

### TC-291 — JSON report is valid, well-formed, and matches the documented schema shape
- **Type**: functional
- **Level**: pipeline (`reference_render.py`)
- **Covers**: AC9
- **Preconditions**: TC-240's set.
- **Steps**: Render JSON; parse it back with the stdlib `json` module.
- **Expected result**: parses without error; top-level keys present:
  `schema_version`, `generated_at_utc`, `decoder_identity`, `tool_version`,
  `config_summary`, `per_track`, `aggregates`, `comparison`, `failures` —
  matching `ReferenceSetReport`'s dataclass shape exactly (architecture.md
  §9).

### TC-292 — `schema_version` field is present and matches the documented value
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC9, "Machine-readable output must be a stable, versioned
  schema" NFR
- **Preconditions**: any successful run.
- **Steps**: Inspect the JSON output's `schema_version` field.
- **Expected result**: field is present and equals **`"1.2"`** (v3
  correction, defects.md DEF-205: bumped from `"1.1"` as part of
  STORY-003's AC13 work — the additive `sanity_warnings` field on
  `Measurements`/`ReferenceMeasurements` is a minor, additive schema
  change, same class as the DEF-106 bump this entry previously
  documented. Prior `"1.1"` value: v2 correction, defects.md DEF-106:
  bumped from the v1-documented `"1.0"` as part of the DEF-101 fix —
  architecture.md v2 §9's versioning convention treats the additive
  `BandCancellation.excess_delta_db` field plus the
  `mono_cancellation_threshold_db` → `mono_band_cancellation_excess_db`
  config-field rename as a minor, additive schema change. Confirmed directly against the shipped
  `report/reference_builder.py::SCHEMA_VERSION = "1.1"`). A later story's
  schema-version branching depends on this field existing and being
  accurate from the start, per the NFR.

### TC-293 — `decoder_identity` field records the actual decode path taken
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC9, reproducibility NFR (decoder-version sensitivity)
- **Preconditions**: a set including at least one MP3 file.
- **Steps**: Inspect the JSON output's `decoder_identity` field.
- **Expected result**: field is populated with a libsndfile version string
  if tier 0/1 handled the MP3, or an ffmpeg version string if tier 2 did
  — never both `None`/absent for a run that successfully decoded at least
  one MP3.

---

## 9. AC10 — Verification bars for newly-introduced measurements

This is the section requirements.md's own AC10 makes mandatory: every
genuinely new measurement (LRA, HF rolloff, per-band stereo width,
mono-sum level change/cancellation) must have a stated, testable
verification bar against a known signal, since none of them can lean on
STORY-001's existing verification work.

### 9.1 LRA (loudness range)

### TC-300 — LRA self-consistency check: ungated-average of the new K-weighting/gating machinery reproduces `measure_integrated_lufs()`
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/loudness_range.py`)
- **Covers**: AC10 (LRA), architecture.md §4.1 "free correctness signal"
- **Preconditions**: any ≥60 s stereo signal with genuine dynamic
  variation (e.g. pink noise with a 6 dB step change).
- **Steps**: Run the new K-weighting + block-averaging machinery in
  "ungated integrated" mode (per BS.1770's own gated-mean algorithm, not
  the LRA percentile-spread path) on the buffer; separately run
  `measure_integrated_lufs()` on the same buffer.
- **Expected result**: the two values agree within 0.1 LU (config
  default, architecture.md §4.1). This validates the K-weighting filter
  and gating logic specifically; it does not itself validate LRA's own
  percentile-spread statistic (see TC-301/TC-302).

### TC-301 — LRA baseline fixture: two-level signal with ~12 LU separation, both levels survive either gate value
- **Type**: audio-quality (calibration)
- **Level**: module
- **Covers**: AC10 (LRA)
- **Preconditions**: synthetic stereo signal, 3 s window / 100 ms hop
  short-term analysis: 30 s at a calibrated level A, 30 s at level B,
  |A - B| ≈ 12 LU (e.g. -14 LUFS then -26 LUFS pink noise, calibrated by
  RMS).
- **Steps**: Measure LRA.
- **Expected result**: LRA ≈ 12 LU (± the config'd `lra_tolerance_lu`,
  default 1.0 — architect-reasoned default, not producer-verified). This
  fixture does not discriminate a correctly-implemented -20 LU relative
  gate from an incorrectly-copied -10 LU gate — under the corrected gate
  math derived in TC-302 below, a 12 LU separation survives comfortably
  under *either* gate (12 < 13.01, the incorrect-gate exclusion boundary,
  and well under 23.01, the correct-gate boundary) — it establishes the
  baseline/happy-path only. See TC-302 for the gate-discriminating
  fixture.
- **Notes**: architect-reasoned tolerance (1.0 LU), flagged per this
  document's governing rule, not producer-verified.

### TC-302 — LRA gate-discrimination fixture: two-level signal with ~18 LU separation, discriminates a correct -20 LU relative gate from an incorrectly-copied -10 LU gate
- **Type**: audio-quality (regression guard for the single most common LRA
  implementation bug, per architecture.md §4.1's own explicit warning)
- **Level**: module
- **Covers**: AC10 (LRA)
- **Preconditions**: synthetic stereo signal, same windowing as TC-301:
  30 s at level A, 30 s at level B, |A - B| ≈ **18 LU** (v2 correction,
  defects.md DEF-107 — see derivation below; e.g. -14 LUFS then
  -32 LUFS).
- **Derivation (why 18 LU, not v1's 25 LU — required reading before
  changing this fixture again)**: the relative gate's threshold is
  computed against the **mean of all absolute-gate-passing blocks**, not
  directly against either cluster's own level. With a 50/50 duration
  split between the loud and quiet clusters, the loud cluster dominates
  that mean in linear power terms, but does not fully determine it —
  averaging the loud cluster's power with the quiet cluster's (negligible
  by comparison at any reasonable separation) pulls the mean down by
  approximately 3.01 dB from the loud cluster's own level alone (a power
  halving from two equal-duration contributors, not a vanishing). So for
  a **correct** -20 LU relative gate, the effective exclusion boundary
  sits at approximately `loud_level − 3.01 − 20 = loud_level − 23.01`; a
  quiet cluster more than ~23.01 LU below the loud cluster is excluded
  even under the *correct* gate. v1's 25 LU separation fell on the wrong
  side of that boundary (25 > 23.01), so it was excluded under the
  correct gate too and produced `lra_lu ≈ 0` regardless of which gate
  value was used — the fixture did not discriminate at all, confirmed
  directly against the shipped `analysis/loudness_range.py` code (both
  `-20.0` and a forced `-10.0` gate configuration produced `lra_lu`
  within numerical noise of 0 on the 25 LU construction). For the
  **incorrect** -10 LU gate, the equivalent boundary is
  `loud_level − 3.01 − 10 = loud_level − 13.01`; any separation above
  ~13.01 LU is excluded under the incorrect gate. An 18 LU separation
  sits cleanly between these two boundaries (13.01 < 18 < 23.01):
  survives the correct -20 LU gate, is excluded by the incorrect -10 LU
  gate. Verified empirically against the shipped code: `lra_lu ≈ 18.0`
  under the correct -20 LU gate, `lra_lu ≈ 0.0` under a forced -10 LU
  gate — a clean, real discrimination.
- **Steps**: Measure LRA under (a) the correct, default -20 LU relative
  gate and (b) a config forced to -10 LU.
- **Expected result**: (a) LRA ≈ 18 LU (± `lra_tolerance_lu`, default
  1.0). (b) LRA collapses to ≈ 0 LU. **This is the regression guard**: if
  the relative gate were ever miscopied as -10 LU (the neighboring
  integrated-loudness constant), this fixture reads a materially
  different, easily distinguished wrong answer under it. Assert LRA is
  close to the ~18 LU expectation under the default config and explicitly
  assert it collapses toward 0 under the forced -10 LU config — do not
  assert only the default-config case, since the whole point of this
  fixture is the contrast between the two.

### TC-303 — LRA verified against EBU Tech 3342 published reference material (external cross-validation)
- **Type**: audio-quality (external calibration) / **Slow** (depends on
  externally-sourced, potentially longer-duration conformance material)
- **Level**: module
- **Covers**: AC10 (LRA), requirements.md AC10's explicit ask
- **Preconditions**: EBU Tech 3342's published conformance test signals
  with known LRA values (**recommended acquisition, not yet in-repo** —
  same posture STORY-001's TC-010 took toward EBU Tech 3341 material: the
  synthetic fixtures TC-301/TC-302 carry primary suite coverage until this
  material is obtained).
- **Steps**: Measure LRA against each published conformance signal.
- **Expected result**: each measured LRA is within `lra_tolerance_lu`
  (default 1.0 LU) of its published value. **Open item**: this test
  cannot be executed until the conformance material is sourced; flagged
  here as a known gap in external validation, not silently skipped from
  the suite's documentation.

### 9.2 HF extension / rolloff detection

### TC-304 — HF-rolloff detector recovers a known Butterworth cutoff from white-noise input
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/hf_extension.py`)
- **Covers**: AC10 (HF rolloff)
- **Preconditions**: white noise, 44.1 kHz, ≥30 s (above
  `hf_min_duration_s`), lowpassed with an 8th-order Butterworth filter at
  fc = 16 000 Hz via `scipy.signal.butter` + `sosfiltfilt`. **White noise,
  not pink** — pink noise's own -3 dB/octave tilt would already be ~12 dB
  down by 16 kHz relative to the 500 Hz–2 kHz reference band, so the -6 dB
  crossing would be dominated by the source spectral tilt rather than the
  filter, invalidating the closed-form expectation. Using `sosfiltfilt`
  (zero-phase, forward-backward) squares the filter's magnitude response,
  so the composite -6 dB point coincides exactly with the design cutoff
  `fc` — this is the derivation that makes the expected value closed-form.
- **Steps**: Measure HF-extension rolloff.
- **Expected result**: recovered rolloff = 16 000 Hz ±
  `hf_rolloff_test_tolerance_hz` (default 500 Hz, architect-reasoned).
  `stable == True` (the filter is applied uniformly across the whole
  fixture, so all segments should agree).

### TC-305 — HF-rolloff detector recovers a second, different known cutoff (confirms the mechanism generalizes, not curve-fit to one value)
- **Type**: audio-quality (calibration)
- **Level**: module
- **Covers**: AC10 (HF rolloff)
- **Preconditions**: same construction as TC-304, fc = 12 000 Hz.
- **Steps**: Measure HF-extension rolloff.
- **Expected result**: recovered rolloff = 12 000 Hz ± 500 Hz.

### TC-306 — Insufficient duration: track shorter than `hf_min_duration_s` is skipped with a defined "insufficient duration" result, not a crash or a misleading value
- **Type**: edge case
- **Level**: module
- **Covers**: AC10 (HF rolloff), architecture.md §4.3 step 1
- **Preconditions**: the TC-304 fixture, truncated to 20 s (below the
  default 30 s `hf_min_duration_s`).
- **Steps**: Measure HF-extension rolloff.
- **Expected result**: result explicitly indicates "insufficient
  duration" (not a numeric rolloff value, not an unhandled exception).

### TC-307 — Boundary: track exactly at, just under, and just over `hf_min_duration_s`
- **Type**: edge case (boundary)
- **Level**: module
- **Covers**: AC10 (HF rolloff)
- **Preconditions**: three variants of the TC-304 fixture at 29.9 s,
  30.0 s, and 30.1 s.
- **Steps**: Measure HF-extension rolloff on each.
- **Expected result**: 29.9 s produces the "insufficient duration" result;
  30.0 s and 30.1 s both produce a numeric rolloff measurement (confirm
  the boundary is inclusive of exactly `hf_min_duration_s`, per whichever
  comparison operator the implementation uses — flag if `>=` vs `>` is
  ambiguous in architecture.md, since §4.3 does not state which).

### TC-308 — Stability flag: a track with a rolloff that shifts materially mid-track is reported unstable
- **Type**: audio-quality
- **Level**: module
- **Covers**: AC10 (HF rolloff), architecture.md §4.3 step 4
- **Preconditions**: synthetic track constructed as two concatenated
  halves: first half white noise lowpassed at 16 000 Hz, second half
  white noise lowpassed at 10 000 Hz (a >2000 Hz spread between segments,
  above the default `hf_stability_tolerance_hz`).
- **Steps**: Measure HF-extension rolloff (5-segment default).
- **Expected result**: `stable == False`; reported rolloff is the median
  of per-segment values, not a value that misrepresents either half as if
  it applied to the whole track.

### 9.3 Per-band stereo width

### TC-309 — Per-band width fixture: mono below 120 Hz, fully decorrelated above 5 kHz — low bands read near 0, high bands read near 1
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/per_band_stereo_width.py`)
- **Covers**: AC10 (per-band stereo width)
- **Preconditions**: synthetic stereo signal, 44.1 kHz, ≥10 s: content
  below 120 Hz is identical in L and R (mono, e.g. a 60 Hz tone or
  lowpassed noise present equally in both channels); content above
  5000 Hz is independently generated decorrelated noise in L and R.
  **Crossover frequencies deliberately chosen at 120 Hz and 5000 Hz** —
  clean edges of the `sub`/`low` boundary and the `high`/`air` boundary
  respectively (per resolved open question #3's seven-band edges), so
  each asserted band's expected value is unambiguous; a 200 Hz crossover
  (as architecture.md §4.4's illustrative prose suggests) would split the
  `low_mid` band (120–500 Hz) and leave its expected value undefined —
  not used here for that reason.
- **Steps**: Measure per-band stereo width for all seven bands.
- **Expected result**: `sub` and `low` band width ≈ 0 (± 0.1, config
  default per architecture.md §4.4); `high` and `air` band width ≈ 1
  (± 0.1). `low_mid`, `mid`, `high_mid` (which straddle or sit between the
  two crossover points and were not specifically engineered) are not
  asserted to a specific value in this test — at most asserted to lie
  between the low-band and high-band readings (monotonic-ish transition),
  documented as a soft check, not a hard pass/fail gate.

### TC-310 — Per-band width caveat is stated in the report, distinguishing this frequency-domain estimate from `stereo_phase.py`'s broadband time-domain correlation
- **Type**: functional (report-content)
- **Level**: pipeline
- **Covers**: AC10 (per-band width), architecture.md §4.4 "stated caveat"
- **Preconditions**: any stereo reference track.
- **Steps**: Render the per-track report section containing per-band
  width and `core.overall_correlation`.
- **Expected result**: the report text states, near the per-band-width
  figures, that this is a frequency-domain/spectral-coherence estimate,
  not a literal band-filtered time-domain correlation, and that it should
  not be read as identical in meaning to the broadband correlation figure
  reported alongside it.

### 9.4 Mono-sum level change + cancellation

**v2 rewrite (defects.md DEF-101/DEF-106)**: TC-311 and TC-313 below were
originally written as open-question framings against architecture.md v1's
ambiguous/incorrect prose. Both questions are now resolved — see
architecture.md v2 §4.5 for the full derivation (two different formulas,
two different ρ=0 floors, previously conflated) and defects.md DEF-101 for
the fix and its empirical verification. Rewritten here as direct
assertions against the resolved, shipped behavior, per defects.md
DEF-106's instruction.

### TC-311 — Mono-sum level change for a perfectly correlated (identical L=R) signal, single-channel convention
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/mono_sum.py`)
- **Covers**: AC10 (mono-sum level change)
- **Preconditions**: synthetic stereo signal with L == R exactly (e.g. a
  1 kHz tone, identical amplitude both channels), 44.1 kHz, ≥10 s.
- **Steps**: Measure mono-sum level change (`mono_sum.level_change_db`
  and `mono_sum.excess_cancellation_db`), and each band's `cancellation`
  flag.
- **Expected result**: the shipped convention (confirmed by reading
  `mono_sum.py` directly — `measure_integrated_lufs(mono_sum, sr)` is
  called on a genuinely single-channel 1-D array, `mono_sum = (L+R)/2`,
  not a dual-mono 2-channel array) gives, per BS.1770's channel-summed
  convention: `level_change_db = -3.0103 ± 0.1 dB` (measured directly
  against this exact fixture in defects.md DEF-101's own verification
  case 1). `excess_cancellation_db = level_change_db −
  _BROADBAND_DECORRELATED_FLOOR_DB (-6.0206) ≈ +3.0103 dB` — positive,
  meaning this correlated/mono-like material reads *further* from the
  cancellation floor than ordinary decorrelated wide stereo, correctly
  read as "no cancellation risk," not as a spurious "-3 dB of
  cancellation." Every band's `delta_db ≈ 0 dB`, `excess_delta_db ≈
  +3.010 dB`, and `cancellation == False` for all 7 bands. Because this
  single-channel convention means every fully mono-compatible reference
  track's `level_change_db` reads ~3 dB more negative than "summing to
  mono" might intuitively suggest, the human-readable report must state
  this plainly wherever the figure appears — this is satisfied by the
  DEF-104 fix to `report/reference_render.py::_track_section()`'s
  mono-sum text; do not treat this test case as also needing to assert
  that report-text requirement (see TC-310's pattern for the analogous
  report-content case, and DEF-104 in defects.md for the specific fix).

### TC-312 — Mono-sum anti-phase fixture: calculable large cancellation at 1 kHz
- **Type**: audio-quality (calibration)
- **Level**: module
- **Covers**: AC10 (mono-sum cancellation), architecture.md §4.5
- **Preconditions**: synthetic stereo signal, 44.1 kHz, ≥10 s: L = +sin(2π·1000·t),
  R = -sin(2π·1000·t), both at amplitude a; a small amount of independent,
  decorrelated broadband noise added to both channels at -20 dB relative
  to a (to avoid asserting an exact -inf dB null, which is numerically
  fragile).
- **Steps**: Measure mono-sum level change and the `mid`-band (500 Hz–
  2 kHz, containing the 1 kHz tone) cancellation flag.
- **Expected result**: broadband level change is a large negative value
  (the tone content nulls almost completely, leaving only the
  uncorrelated noise floor summed at half amplitude; hand-calculable
  bound given the -20 dB noise floor and the single-channel convention
  confirmed in TC-311 — assert the value is more negative than a stated
  bound, e.g. beyond -15 dB, rather than an exact figure, given the noise
  floor's own randomness; do not assert an exact dB figure — defects.md's
  own worked examples for a similarly-constructed fixture produced
  different exact values on different runs, -39.92 dB and -43.42 dB,
  depending on the specific noise-floor amplitude used, confirming this
  is fixture-sensitive, not a fixed constant). `mid`-band `cancellation`
  flag == `True` (v2 correction: the flag now fires on
  `excess_delta_db < config.mono_band_cancellation_excess_db` i.e.
  `delta_db < -6.0206 dB` i.e. only when the band's correlation ρ < -0.5
  — this fixture's near-total anti-phase cancellation is far beyond that
  bar, so the flag still fires as expected; the *threshold* itself moved
  in the DEF-101 fix, not the correctness of this particular fixture's
  positive result).

### TC-313 — Mono-cancellation regression guard: fully decorrelated (not anti-phase) stereo never false-positives as cancellation
- **Type**: audio-quality (regression guard — this is the direct,
  permanent guard against the DEF-101 false-positive; matches the shipped
  `tests/test_ref_ac10_verification_bars.py::
  test_tc313_def101_regression_ordinary_decorrelated_stereo_no_false_positive`)
- **Level**: module
- **Covers**: AC10 (mono-sum cancellation), architecture.md §4.5
- **Preconditions**: synthetic stereo signal with fully decorrelated
  (independent, not anti-phase) noise in both channels, equal power, no
  shared content — a legitimately "wide" but not destructively-
  interfering signal. Run at least two independent seed/sigma
  combinations (per the shipped test), since this is the worst-case
  healthy-material guard for this flag (see rationale below), not an
  easy case that only needs one draw.
- **Steps**: Measure `mono_sum.excess_cancellation_db` and every band's
  `cancellation` flag.
- **Expected result (v2 rewrite, defects.md DEF-101/DEF-106 — supersedes
  v1's "do not assert the boolean" instruction, which is now backwards)**:
  `excess_cancellation_db ≈ 0` (within measurement noise), and **every one
  of the 7 bands reads `cancellation == False`**. This is now the correct
  thing to assert, not merely a numeric-proximity observation: prior to
  the DEF-101 fix, this exact construction false-positived every band as
  `cancellation == True`, because the per-band cancellation flag compared
  raw `delta_db` (which sits at ≈ -3.01 dB for genuinely decorrelated,
  ρ≈0 content — a ratio of exactly 1/2 between the mono-summed and
  per-channel-mean band power) against a default threshold of -3.0,
  meaning essentially any healthy wide band tripped it by construction.
  The fix references the flag to `excess_delta_db` (= `delta_db −
  (-3.0103)`, the per-band ρ=0 floor) instead, so it now fires only when
  `delta_db < -6.0206 dB`, i.e. only for a band with correlation ρ < -0.5
  — a defensible "meaningfully anti-correlated" bar that ordinary
  decorrelated material sits well clear of. **Rationale for treating this
  as the worst case, not an easy one**: the cancellation flag fires at
  `excess_delta_db < -3.0`, i.e. `delta_db < -6.02`, i.e. only when
  per-band ρ < -0.5 — ordinary decorrelated material (ρ≈0) sits closer to
  that boundary than any positively-correlated healthy material would, so
  this fixture is the worst-case healthy-material guard for this flag,
  not a soft case; no further fixture is judged necessary beyond the
  two-seed repetition already specified.

---

## 10. AC11 — Code-path identity with STORY-001

### TC-330 — Stereo WAV: STORY-002's measurement equals STORY-001's stage-[2] measurement, field by field
- **Type**: regression (the single most important test in this suite, per
  architecture.md §8/§12's own explicit framing)
- **Level**: cross-path integration
- **Covers**: AC11
- **Preconditions**: one stereo WAV fixture, 44.1 kHz/24-bit, with
  non-trivial values across all shared metrics (not silence, not a
  degenerate signal).
- **Steps**: (a) Run the fixture through `io/ingest.py` →
  STORY-001's stage-[2]-equivalent calls to `measure_integrated_lufs`,
  `measure_true_peak`, `measure_dynamic_range`, `measure_frequency_balance`,
  `analyze_stereo_phase`. (b) Run the same fixture through
  `io/reference_ingest.py` → `[R2]`'s calls to the same five functions.
- **Expected result**: exact equality for integer/boolean fields
  (`dynamic_range_db` rounded, `mono_compatible`); float fields
  (`integrated_lufs`, `true_peak_dbtp`, all three three-band
  `FrequencyBalanceResult` values, `overall_correlation`) equal within
  1e-9 relative tolerance (same deterministic numpy/scipy operations on
  the same input array — any looser divergence indicates a real bug, not
  floating-point noise).

### TC-331 — Mono WAV: same field-by-field identity, specifically exercising the `always_2d`-then-squeeze convention trap
- **Type**: regression
- **Level**: cross-path integration
- **Covers**: AC11
- **Preconditions**: one mono WAV fixture, 44.1 kHz/16-bit.
- **Steps**: same as TC-330, mono variant.
- **Expected result**: same equality assertions as TC-330. This case
  exists specifically because architecture.md §6's "AC11 trap" callout
  names the mono `audio.ndim`/squeeze convention as "the single most
  likely place to introduce an AC11 regression" — a stereo-only identity
  test would not catch a shape mismatch that only manifests for mono
  input, since `dynamic_range.py`, `stereo_phase.py`, and
  `frequency_balance.py`'s `_to_mono` all branch on `audio.ndim`.

### TC-332 — DR float-exposure refactor: both the rounded public value and the new unrounded value trace to one underlying computation
- **Type**: regression
- **Level**: module (`analysis/dynamic_range.py`)
- **Covers**: AC11, architecture.md §5
- **Preconditions**: several fixtures spanning a range of DR values
  (e.g. DR6 through DR16-class synthetic material).
- **Steps**: For each fixture, call `measure_dynamic_range()` (public,
  rounded) and `_measure_dynamic_range_unrounded()` (private, exact)
  directly.
- **Expected result**: `measure_dynamic_range(x) ==
  math.floor(_measure_dynamic_range_unrounded(x) + 0.5)` for every
  fixture — confirms the refactor is extract-not-fork (one computation
  underneath both entry points), not a coincidentally-matching
  reimplementation.

### TC-333 — FLAC-sourced measurement equals WAV-sourced measurement of the same underlying audio (transitively strengthens AC11 for non-WAV formats)
- **Type**: regression
- **Level**: cross-path integration
- **Covers**: AC11 (extended — AC11's own text is WAV-scoped, but the
  lossless-decode-fidelity claim this test makes is a natural extension
  worth covering explicitly)
- **Preconditions**: TC-330's stereo WAV fixture, additionally encoded to
  FLAC.
- **Steps**: Measure via `reference_ingest.py` for both the WAV and the
  FLAC version.
- **Expected result**: field-for-field equality within the same
  tolerances as TC-330 — FLAC's lossless decode should introduce zero
  measurable difference.

---

## 11. AC12 — N / contributing-tracks on every aggregate

### TC-340 — Every `AggregateStat` in a full report carries `n` and non-empty `contributing_tracks`, and `n == len(contributing_tracks)`
- **Type**: functional (exhaustive structural check, not a spot check —
  per advisor guidance, a single spot-check on one aggregate does not
  cover AC12's "every" claim)
- **Level**: pipeline
- **Covers**: AC12
- **Preconditions**: a 6-track mixed set (mix of lossless/lossy, mono/
  stereo, 44.1/48 kHz) so multiple exclusion rules are simultaneously
  active, giving genuinely different N values across different metrics.
- **Steps**: Run `analyze_set()`; iterate every entry in
  `ReferenceSetReport.aggregates`.
- **Expected result**: for every single `AggregateStat` entry, `n` is
  present and `n >= 0`, `contributing_tracks` is present, and
  `n == len(contributing_tracks)` — no entry has a bare number with no
  visible N, and no entry's N is inconsistent with its own track list.

### TC-341 — `n` reflects actual post-exclusion membership, not the full set size
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC12
- **Preconditions**: TC-267's interaction fixture (mono MP3 at 48 kHz
  inside a mixed set of 6).
- **Steps**: Run `analyze_set()`; inspect the HF-extension (44.1 kHz
  subset), stereo-width, and LUFS aggregates.
- **Expected result**: LUFS aggregate `n == 6` (no exclusion applies);
  HF-extension 44.1 kHz subset `n == 4` (excludes the 48 kHz lossless
  track, the mono MP3 track, and — per its own subset scoping — the
  48 kHz subset's own membership); stereo-width aggregate `n == 5`
  (excludes only the mono track). Three different, individually-correct N
  values on the same underlying 6-track set, each traceable to its own
  exclusion rule.

### TC-342 — Markdown renders N as a table column, not a footnote
- **Type**: functional (report-shape)
- **Level**: pipeline (Markdown renderer)
- **Covers**: AC12, architecture.md §9 ("N as a column, not a footnote")
- **Preconditions**: TC-267's set.
- **Steps**: Render Markdown; inspect the aggregate table.
- **Expected result**: the aggregate table has a visible "N" column
  (or equivalent inline field) per row, including subset-qualified rows
  (e.g. "HF extension (44.1 kHz subset, N=4, low-confidence)" renders as
  one legible row) — N is not relegated to a separate caveat paragraph a
  reader could miss.

### TC-343 — `excluded` list carries a reason string for every excluded track, distinct per exclusion type
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC12, AC5's "visible, reason-coded entry" requirement
  extended to all three exclusion rules (§1)
- **Preconditions**: TC-267's set.
- **Steps**: Inspect `AggregateStat.excluded` for the HF-extension and
  stereo-width aggregates.
- **Expected result**: each excluded entry has a non-empty `reason`
  string; the lossy-HF exclusion reason and the mono-stereo exclusion
  reason are textually distinguishable from each other (not a shared
  generic "excluded" string) so a reader can tell *why* a given track is
  missing from a given aggregate.

---

## 12. Edge case inputs

### TC-350 — Near-silence: all short-term LRA blocks fall below the absolute gate
- **Type**: edge case
- **Level**: module (`analysis/loudness_range.py`)
- **Covers**: cross-cutting (silence handling), AC10 (LRA)
- **Preconditions**: synthetic stereo track, 60 s, uniform -85 dBFS RMS
  noise (below the -70 LUFS absolute gate throughout).
- **Steps**: Measure LRA.
- **Expected result**: defined behavior, not a crash or NaN propagating
  into the aggregate — e.g. LRA reported as "undefined — no blocks passed
  the absolute gate" or `0.0` with an explicit flag, whichever the
  implementation defines; test asserts the chosen behavior is
  deterministic and does not raise an unhandled exception or divide by
  zero in the percentile computation on an empty array.

### TC-351 — Full-scale / already-clipping reference input
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC1 (report completeness under an atypical but real input)
- **Preconditions**: synthetic stereo track, 60 s, deliberately clipped at
  ±1.0 full scale for a portion of its duration (e.g. a heavily
  brickwall-limited "loudness war" style reference).
- **Steps**: Run per-track reference analysis.
- **Expected result**: all AC1 fields populate without error or NaN; true
  peak reads at or above 0 dBTP (expected, given the input); DR is
  correspondingly low; no exception from any of the five new measurement
  functions on this atypical input.

### TC-352 — Very quiet reference input
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC1
- **Preconditions**: synthetic stereo track, 60 s, -45 dBFS RMS pink
  noise (quiet but above the absolute LUFS gate, so it should still
  register as program content, unlike TC-350).
- **Steps**: Run per-track reference analysis.
- **Expected result**: all AC1 fields populate with plausible (non-NaN,
  non-crashing) values; no gain-staging blow-up in any of the ratio-based
  new measurements (per-band width's normalization by
  `sqrt(∫S_LL · ∫S_RR)`, mono-sum's dB comparisons) — specifically check
  no division-by-near-zero instability in the per-band width or mono-sum
  calculations at this level.

### TC-353 — DC offset present
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC1, seven-band `sub` band, mono-sum
- **Preconditions**: synthetic stereo track with a deliberate +0.02 (≈
  -34 dBFS) DC offset added to both channels on top of normal program
  content.
- **Steps**: Run per-track reference analysis.
- **Expected result**: no crash; `sub`-band energy reflects the DC/near-DC
  content without destabilizing the seven-band or HF-rolloff Welch/CSD
  computations (DC offset should not, for example, cause a divide-by-zero
  in the reference-band-relative dB calculations). Report explicitly if
  DC offset visibly inflates the `sub` band reading — this is a real
  measurement-quality question worth surfacing, not asserting a specific
  numeric bound requirements.md does not give.

### TC-354 — Very short file, shorter than the 3-second LRA analysis window
- **Type**: edge case
- **Level**: module (`analysis/loudness_range.py`)
- **Covers**: AC10 (LRA), AC1 report completeness
- **Preconditions**: synthetic stereo WAV, 2.0 s duration.
- **Steps**: Measure LRA.
- **Expected result**: defined behavior — e.g. "insufficient duration for
  LRA" result, not a crash from an empty or malformed window array. Also
  confirm the per-track report as a whole still completes for this file
  (other AC1 fields that don't require a 3 s window, e.g. LUFS, still
  populate).

### TC-355 — Very short file, shorter than `hf_min_duration_s` but longer than the LRA window
- **Type**: edge case (boundary interaction)
- **Level**: pipeline
- **Covers**: AC1, AC10 (HF rolloff)
- **Preconditions**: synthetic stereo WAV, 15 s duration (above LRA's 3 s
  window, below HF-extension's default 30 s minimum).
- **Steps**: Run per-track reference analysis.
- **Expected result**: LRA populates normally; HF-extension reports
  "insufficient duration" per TC-306; both results coexist in the same
  per-track report without one field's insufficiency blocking the other's
  computation.

### TC-356 — Mono FLAC reference track
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC1, mono handling × FLAC format handling (combined)
- **Preconditions**: synthetic mono FLAC, 44.1 kHz, 60 s.
- **Steps**: Run per-track reference analysis.
- **Expected result**: same field-completeness/null-stereo-field
  assertions as TC-201, confirmed specifically through the FLAC decode
  path (not just WAV, per TC-203's format-coverage rationale).

---

## 13. Failure modes

### TC-370 — Corrupt/truncated file among otherwise-good files: run continues, failure recorded, remaining tracks aggregate correctly
- **Type**: edge case
- **Level**: pipeline
- **Covers**: architecture.md §1/§7 "one bad file must not abort the set"
  (architecture-level inference, not a numbered AC — flagged as such)
- **Preconditions**: 5-file folder, one file truncated mid-header.
- **Steps**: Run `analyze_set()`.
- **Expected result**: run completes; `ReferenceSetReport.failures`
  contains one entry with the file's path and a human-readable reason;
  all aggregates reflect `n == 4` (or fewer if other exclusion rules also
  apply to the 4 good files) with the corrupt file entirely absent from
  `contributing_tracks` anywhere; no unhandled exception propagates out
  of `analyze_set()`.

### TC-371 — Unsupported file extension present in the folder
- **Type**: edge case
- **Level**: pipeline
- **Covers**: architecture.md §1/§7 (same as TC-370)
- **Preconditions**: a folder containing 5 valid audio files plus one
  `.txt` or `.aiff` (genuinely unsupported) file.
- **Steps**: Run `analyze_set()`.
- **Expected result**: the unsupported file is recorded in `failures`
  with a reason identifying it as an unsupported format; the 5 valid
  files are analyzed and aggregated normally.

### TC-372 — Missing/nonexistent reference folder path
- **Type**: edge case
- **Level**: pipeline (CLI and library API)
- **Covers**: general robustness (not a numbered AC, but a normal
  failure-mode expectation)
- **Preconditions**: a path that does not exist on disk.
- **Steps**: Call `analyze_set(reference_dir="/does/not/exist")`.
- **Expected result**: a clear, typed error is raised at the start of the
  run (before any per-file processing is attempted) — not a silent empty
  report and not an unhandled OS-level exception with a confusing
  traceback.

### TC-373 — Empty folder (zero audio files) raises `EmptyReferenceSetError`
- **Type**: edge case
- **Level**: pipeline
- **Covers**: architecture.md §11 "Error handling"
- **Preconditions**: an existing, empty folder.
- **Steps**: Call `analyze_set()`.
- **Expected result**: `errors.EmptyReferenceSetError` is raised.

### TC-374 — All files fail to decode: zero tracks remain after per-file failures, `EmptyReferenceSetError` raised
- **Type**: edge case
- **Level**: pipeline
- **Covers**: architecture.md §11 "a genuinely different condition from
  'one file failed'"
- **Preconditions**: a folder containing only corrupt/unreadable files.
- **Steps**: Call `analyze_set()`.
- **Expected result**: `errors.EmptyReferenceSetError` is raised (distinct
  from TC-370's "some files fail, run continues" behavior — this test
  confirms the threshold where the run stops rather than producing a
  vacuous empty aggregate).

### TC-375 — Suno-export comparison path: missing/unreadable export file does not abort the reference-set analysis
- **Type**: edge case
- **Level**: pipeline
- **Covers**: AC3, general robustness
- **Preconditions**: a valid 5-track reference set, plus a
  `suno_export_path` pointing to a nonexistent file.
- **Steps**: Call `analyze_set(reference_dir, suno_export_path=bad_path)`.
- **Expected result**: **open question, not assumed**: does the run (a)
  fail the whole call since the comparison was explicitly requested, or
  (b) complete the reference-set analysis and report the comparison as
  unavailable with a reason? Neither requirements.md nor architecture.md
  states this explicitly. Flag for architect/product decision; write the
  test against whichever behavior is chosen once confirmed.

### TC-376 — Wrong channel count: a reference file with more than 2 channels
- **Type**: edge case
- **Level**: pipeline
- **Covers**: general robustness (STORY-001's `ingest.py` channel handling
  is not directly reused here, per §6's separate-ingest-path decision —
  this test confirms `reference_ingest.py` has its own defined behavior)
- **Preconditions**: a synthetic 4-channel (quad) WAV file.
- **Steps**: Ingest via `reference_ingest.py`.
- **Expected result**: a clear, typed error or an explicit
  "unsupported channel count" failure entry — not a silent
  channel-count assumption (e.g. silently using only the first 2
  channels) that would produce a misleading measurement. Flag if
  architecture.md does not state which behavior is intended (it does
  not, as read) — open question for the architect.

---

## 14. Non-functional requirements

### TC-380 — Per-track analysis completes in seconds, not minutes (7-minute stereo 44.1 kHz track)
- **Type**: non-functional / **Slow**
- **Level**: pipeline
- **Covers**: NFR "per-track analysis speed"
- **Preconditions**: a realistic-duration (7-minute) synthetic stereo
  44.1 kHz track — this specific case genuinely needs full-length
  material since the NFR itself is duration-scoped ("a 7-minute reference
  track should complete measurement in seconds, not minutes"); a 3-second
  fixture would not exercise the actual per-track cost profile (the
  8x-oversampled true-peak FIR convolution and the LRA short-term
  windowing pass both scale with track duration).
- **Steps**: Time a single-track `[R2]` analysis run.
- **Expected result**: completes in single-digit-to-low-double-digit
  seconds, materially under any "minutes" reading — measured directly
  against the shipped code at ~33.3 s for a 7-minute fixture
  (architecture.md v2 §7.2's own per-stage breakdown), well within the
  "seconds, not minutes" bar; record the actual wall-clock time as the
  concrete finding for any given run. Recommend running as an isolated
  pytest invocation, not folded into a large combined-suite run, per
  architecture.md v3 §16's finding that NFR/wall-clock tests run at the
  tail of a long combined session pick up session-level timing noise
  unrelated to the code under test.

### TC-381 — Whole-set budget: 6 reference tracks + 1 Suno-export comparison track complete under 5 minutes (worst case); realistic material comfortably faster
- **Type**: non-functional / **Slow**
- **Level**: pipeline
- **Covers**: NFR "per-set processing budget" (architect-set figure,
  architecture.md §7.2)
- **Preconditions**: 6 synthetic 7-minute stereo 44.1 kHz reference
  tracks + 1 synthetic 7-minute stereo 44.1 kHz Suno-export track (7
  files total) — the worst-case, 7-minute-average-duration workload
  architecture.md §7.2 states its budget against.
- **Steps**: Time a full `analyze_set()` run including the comparison.
- **Expected result**: completes in **under 300 seconds (5 minutes)** —
  v2 correction, defects.md DEF-106: v1's "under 120 seconds" figure was
  architecture.md v1's own unbenchmarked extrapolation and was revised
  upward once real per-stage timing existed to check it against
  (architecture.md v2 §7.2, DEF-102). The measured basis for the revised
  figure: `measure_all` (STORY-001's own reused, AC11-frozen stage)
  alone costs 16.39 s/track on a 7-minute fixture; the five new
  measurements add roughly another 17 s/track; the full `analyze_track()`
  call measures ~33.3 s/track, so `33.3 s × 7 tracks ≈ 3.9 minutes`, and
  the 300 s budget gives roughly 25% headroom over that measured figure.
  For more realistic 3–4 minute reference material, the same per-stage
  costs scale down roughly proportionally with duration, extrapolating to
  **~2.3 minutes for a 7-track set** — comfortably inside even the v1
  120-second target for realistically-sized material; the 5-minute figure
  is a worst-case bound for unusually long (7-minute) tracks, not a
  general expectation. Recommend running as an isolated pytest
  invocation per architecture.md v3 §16 (see TC-380's note) — a prior
  session observed this exact test read 1129.6 s when run at the tail of
  an oversized combined suite invocation, against a clean pass well under
  300 s when run as part of its own isolated `test_ref_*.py` suite.

### TC-382 — Memory: peak RSS across a 6-track sequential run stays bounded, does not grow per track
- **Type**: non-functional
- **Level**: pipeline
- **Covers**: NFR (§7's "release the oversampled buffer" memory
  discipline — a real failure mode with a concrete magnitude, ~2.4 GB per
  retained buffer, if violated)
- **Preconditions**: a 6-track synthetic set, each track 7 minutes,
  stereo, 44.1 kHz.
- **Steps**: Monitor process RSS (or equivalent) across the sequential
  run; record peak RSS and RSS at the start of each successive track's
  analysis.
- **Expected result**: RSS does not grow monotonically track-over-track
  in a pattern consistent with retained `TruePeakResult.oversampled`
  buffers (i.e. no ~2.4 GB-per-track accumulation); peak RSS stays within
  a bound appropriate for "typical consumer hardware" (no specific GB
  figure given by requirements.md beyond this qualitative bar — record
  the actual peak and flag if it appears to scale with track count rather
  than staying roughly flat). Note (v2): per-call peak is now expected in
  the ~2.7–4.4 GB range per the DEF-103 fix and its follow-up
  investigation (architecture.md §7.1) — this test is about growth across
  tracks (a leak/retention pattern), not about the single-track peak
  figure itself, which is covered separately by defects.md DEF-103's own
  memory verification.

### TC-383 — Reproducibility: identical input set + config produces identical per-track and aggregate output across repeated runs
- **Type**: regression
- **Level**: pipeline
- **Covers**: reproducibility NFR (mirrors STORY-001's AC10, and functions
  as this story's idempotency check per the mandatory-coverage checklist
  — there is no separate "already-processed audio" idempotency case,
  since this story performs no processing; re-running analysis on the
  same files is the applicable form of idempotency here)
- **Preconditions**: a 5-track synthetic set, fixed config.
- **Steps**: Run `analyze_set()` twice.
- **Expected result**: `ReferenceSetReport` (both Markdown and JSON
  renderings) is byte-identical across the two runs, except for the
  `generated_at_utc` timestamp field specifically (which is expected to
  differ) — every measurement value, aggregate statistic, N,
  contributing-tracks list, and exclusion entry matches exactly.

### TC-384 — Bypass/disabled-stage bit-identity: not applicable — explicitly stated
- **Type**: N/A (documented, per the mandatory coverage checklist)
- **Level**: n/a
- **Covers**: mandatory-coverage-checklist "Bypass/disabled" item
- **Note**: this story performs no audio processing or mastering of any
  kind (explicit out-of-scope) — there is no processing stage that could
  be bypassed or disabled, and therefore no bit-identical-output case to
  write. This is stated explicitly rather than silently omitted, per this
  document's own instructions.

### TC-385 — MP3 decode-tier branch logic tested independently of which tier is live on a given machine
- **Type**: functional / non-functional (environment robustness)
- **Level**: module (`io/mp3_decode.py` dispatch logic)
- **Covers**: architecture.md §12 testability note
- **Preconditions**: `soundfile.available_formats()` probe result
  injected/mocked to force each branch in turn (tier-1-available and
  tier-1-unavailable).
- **Steps**: Call the dispatch function under each mocked probe result.
- **Expected result**: tier-1-available routes to the `soundfile` direct
  read; tier-1-unavailable routes to the FFmpeg subprocess path — both
  branches selected correctly regardless of which one happens to be
  reachable on the current CI machine. Separately, run an
  environment-conditional integration test against whichever branch the
  real, unmocked probe selects on the current machine; skip (not fail)
  the untested branch and log which branch was actually exercised.

---

## 15. STORY-001 non-regression

None of these belong to a STORY-002 acceptance criterion directly — they
are the concrete, checkable form of the NFR "No regression to STORY-001's
existing test suite or report shape."

### TC-390 — STORY-001's existing test suite remains green after this story's changes
- **Type**: regression
- **Level**: n/a (whole-suite run)
- **Covers**: NFR (STORY-001 non-regression)
- **Preconditions**: STORY-001's full existing test suite (TC-001–
  TC-152-class tests, per `stories/STORY-001/test-cases.md`).
- **Steps**: Run STORY-001's test suite after this story's implementation
  lands.
- **Expected result**: 100% of previously-passing STORY-001 tests still
  pass — no regression from the `dynamic_range.py` extraction (§5), the
  `frequency_balance.py` `_psd.py` extraction (§4.2), or any other change
  made in service of this story. Note (v2): `test_tc150_processing_time_budget`
  specifically must be run as its own isolated pytest invocation, not
  folded into this whole-suite run, per architecture.md v3 §16 (DEF-110)
  — its ~2-3% real margin is thin enough that ordinary session-level
  timing noise from a long combined run can flip it to FAIL without any
  code regression having occurred; this is a STORY-001 NFR margin
  question tracked under DEF-110, not itself a test-case-writer action
  item.

### TC-391 — STORY-001's `Measurements` dataclass shape is unchanged (field set, types, order)
- **Type**: regression
- **Level**: module (`analysis/types.py`)
- **Covers**: NFR
- **Preconditions**: introspect `Measurements` via `dataclasses.fields()`.
- **Steps**: Compare the field set before/after this story's
  implementation.
- **Expected result**: identical field names, types, and declared order —
  confirms the architecture's "compose, don't extend" decision (§3) was
  actually followed, not just documented.

### TC-392 — STORY-001's `render_json()` output is byte-identical on a fixed golden fixture, before and after this story's changes
- **Type**: regression
- **Level**: pipeline (STORY-001's own `report/render.py`)
- **Covers**: NFR
- **Preconditions**: STORY-001's existing golden-file fixture (per
  architecture.md v5 §7's recommended golden-file test, if built) or a
  newly-fixed fixture if none exists yet.
- **Steps**: Run STORY-001's `pipeline.master()` on the fixture; compare
  the resulting JSON report to a pre-recorded baseline captured before
  this story's changes.
- **Expected result**: byte-identical output (excluding any timestamp
  field STORY-001's own report already varies run-to-run, consistent with
  its existing reproducibility test posture).

### TC-393 — `measure_dynamic_range()`'s rounded return values are unchanged across a battery of inputs after the §5 extraction
- **Type**: regression
- **Level**: module
- **Covers**: NFR, architecture.md §5
- **Preconditions**: a battery of fixtures spanning STORY-001's own
  existing DR test cases (reuse STORY-001's TC-030–TC-035-class fixtures
  if available).
- **Steps**: Compare `measure_dynamic_range()` output before/after the
  extraction refactor.
- **Expected result**: identical rounded DR values for every fixture —
  the refactor changed no observable behavior of the public function.

### TC-394 — `measure_frequency_balance()`'s output is unchanged after the `_psd.py` extraction
- **Type**: regression
- **Level**: module
- **Covers**: NFR, architecture.md §4.2
- **Preconditions**: a battery of fixtures spanning STORY-001's own
  existing frequency-balance test cases.
- **Steps**: Compare `measure_frequency_balance()` output before/after the
  Welch/PSD helper extraction.
- **Expected result**: identical three-band `FrequencyBalanceResult`
  values for every fixture.

### TC-395 — `progressive_house_124bpm.json` (STORY-001's three-band reference curve) is unmodified by this story
- **Type**: regression
- **Level**: n/a (file-content check)
- **Covers**: NFR, resolved open question #4
- **Preconditions**: `progressive_house_124bpm.json`'s content/hash
  recorded before this story's implementation lands.
- **Steps**: Compare the file's content/hash after implementation.
- **Expected result**: byte-identical — confirms this story's seven-band
  scheme did not, even inadvertently, touch STORY-001's correction-
  threshold source of truth.

---

## Open questions surfaced during test-case writing

These are genuine gaps between what requirements.md/architecture.md state
and what a concrete, unambiguous test needs — flagged per this document's
own instruction not to invent an expected value where one is missing, and
carried forward for the architect/product owner, not silently resolved
here.

**Resolved since v1 (see "Revision history" below for the full list):**

1. ~~Mono-sum channel convention (TC-311).~~ **Resolved, v2.** Confirmed
   by reading the shipped `analysis/mono_sum.py` directly: the
   single-channel convention is what shipped (`measure_integrated_lufs`
   called on a 1-D array, not dual-mono). TC-311 is rewritten as a direct
   assertion against `level_change_db = -3.0103 dB` for L=R. See
   architecture.md v2 §4.5 and defects.md DEF-101/DEF-106.
2. ~~Mono-cancellation threshold vs. ordinary decorrelation (TC-313).~~
   **Resolved, v2.** The cancellation flag now compares `excess_delta_db`
   (excess beyond the per-band ρ=0 decorrelated floor) against the
   threshold, not raw `delta_db` — ordinary decorrelated stereo no longer
   false-positives. TC-313 is rewritten to assert the boolean flag
   directly. See architecture.md v2 §4.5 and defects.md DEF-101/DEF-106.

**Still open:**

3. **Bitrate-unknown schema distinction (TC-253).** WAV/FLAC's
   not-applicable bitrate and MP3's unknown-bitrate both currently model
   as `Optional[int] = None` in `ProvenanceResult` — worth confirming
   whether these should be schema-distinguishable (e.g. a
   `bitrate_status` enum) so the human-readable report doesn't have to
   infer which case it's in from the container field alone.
4. **EBU Tech 3342 conformance material availability (TC-303).** Not yet
   sourced into the repository; this test cannot execute until it is.
   Recommend acquiring it early given architecture.md §14 risk #2 names
   this as the actual closure path for LRA correctness, beyond the
   synthetic fixtures' partial coverage.
5. **Air-band cross-sample-rate aggregation (architecture.md §13 item 3).**
   Explicitly flagged by the architect as a judgment call needing
   confirmation against real reference-set data, not resolvable from a
   synthetic fixture alone — no test case in this suite can close this;
   flagged here so it is not lost.
6. **HF-rolloff/LRA/mono-cancellation/transcode-slope numeric defaults
   (architecture.md §13 item 1).** All four are architect-reasoned, not
   producer-verified — every test case in §9 above that asserts against
   one of these defaults is explicitly labelled as testing "the detector
   against its own configured default," not "the default is the correct
   target," per this document's governing rule.
7. **Suno-export-comparison failure behavior (TC-375)** and **wrong
   channel-count handling (TC-376)** are not stated by either
   requirements.md or architecture.md — flagged for an explicit decision
   before those two tests can assert a specific expected behavior rather
   than "some defined behavior, not a crash."
8. **`hf_min_duration_s` boundary operator (TC-307)** — architecture.md
   §4.3 does not state whether the "shorter than" comparison is `<` or
   `<=`; needs confirmation so the exact-30.0s case has an unambiguous
   expected result.

---

## Traceability

| AC | Description | Test cases |
|---|---|---|
| AC1 | Per-track measurement report (all listed metrics) | TC-200–TC-204, TC-350–TC-356 |
| AC2 | Aggregate statistics (median/min/max) across the set | TC-220–TC-222 |
| AC3 | Suno-export side-by-side comparison, identical code path | TC-240–TC-242, TC-375 |
| AC4 | Source format/bitrate detection and per-track reporting | TC-250–TC-254 |
| AC5 | Lossy-source HF exclusion / lossless-confidence thresholds / per-rate subsetting | TC-260–TC-267 |
| AC6 | Loudness verifiable to ±0.1 LU (incl. FLAC/MP3-decoded input) | TC-270–TC-273 |
| AC7 | True peak oversampled-vs-sample-peak mechanism, incl. MP3 caveat | TC-274, TC-275 |
| AC8 | Non-destructive guarantee (WAV/FLAC/MP3, no disk artifacts) | TC-280–TC-284 |
| AC9 | Human- and machine-readable output, versioned schema | TC-290–TC-293, TC-342 |
| AC10 | Verification bars for LRA, HF rolloff, per-band width, mono-sum | TC-300–TC-313 |
| AC11 | Code-path identity with STORY-001 | TC-330–TC-333, TC-242 |
| AC12 | N / contributing-tracks on every aggregate | TC-340–TC-343 |
| (NFR) | Per-track / whole-set performance, memory, reproducibility | TC-380–TC-385 |
| (NFR) | STORY-001 non-regression | TC-390–TC-395 |
| (n/a) | Failure modes not tied to a specific AC | TC-370–TC-374, TC-376 |

---

## Mandatory coverage checklist — explicit confirmation

- **Happy path for each AC**: TC-200 (AC1), TC-220 (AC2), TC-240 (AC3),
  TC-250/252 (AC4), TC-260 (AC5), TC-270 (AC6), TC-274 (AC7), TC-280
  (AC8), TC-290/291 (AC9), TC-301/304/309/311 (AC10), TC-330 (AC11),
  TC-340 (AC12).
- **Boundary values**: TC-262–TC-265 (lossless-N 0/1/2/3), TC-306/307
  (HF-duration boundary), TC-301/302 (LRA gate-discrimination boundary —
  v2: TC-302's own separation is chosen to sit between the correct- and
  incorrect-gate exclusion boundaries, not "at" the mono-cancellation
  threshold as v1 mischaracterized it), TC-354/355 (short-file
  boundaries).
- **Idempotency**: covered as reproducibility, TC-383 (this story has no
  processing to make "already-processed" input meaningful — analysis
  is the operation, and re-running analysis is the applicable
  idempotency form).
- **Bypass/disabled**: N/A, explicitly stated at TC-384 (no processing
  stages exist in this story).
- **Mono and stereo**: TC-201/356 (mono), TC-200 (stereo), throughout.
- **Multiple sample rates (44.1/48 kHz)**: TC-200 (44.1), TC-202 (48),
  TC-266 (mixed-rate aggregation).
- **Silence/near-silence**: TC-350 (LRA absolute-gate edge).
- **Full-scale/clipping input**: TC-351.
- **Very quiet input**: TC-352.
- **DC offset**: TC-353.
- **Very short file**: TC-354, TC-355.
- **Corrupt/truncated file**: TC-370, TC-284.
- **Unsupported format**: TC-371.
- **Missing file**: TC-372.
- **Wrong channel count**: TC-376.
- **Units/precision explicit**: every AC10 case states LUFS vs. LU vs.
  dBTP vs. dB-relative explicitly per its own metric; TC-274/275
  specifically distinguish sample peak (dBFS) from true peak (dBTP).

---

## Revision history

- v1 (2026-08-01): Initial test-cases.md for STORY-002, based on
  requirements.md v2 (all ten open questions resolved) and architecture.md
  v1. No `defects.md` exists for this story — nothing to reconcile. Test
  IDs TC-200–TC-395, continuing from STORY-001's TC-001–TC-152 range for
  global uniqueness. Eight open questions surfaced during writing (see
  "Open questions surfaced during test-case writing" above) where
  requirements.md/architecture.md left a genuine ambiguity a concrete test
  needs resolved — most significantly the mono-sum channel convention
  (TC-311) and the mono-cancellation-threshold/decorrelation collision
  (TC-313), both flagged rather than guessed.
- v2 (2026-08-02): Corrected staleness against the shipped implementation
  and architecture.md v2/v3, per defects.md DEF-106/DEF-107/DEF-108 (all
  three routed to test-case-writer, none a code defect). Concretely:
  - **DEF-106** (four stale expected values against architecture v2 / the
    DEF-101 and DEF-102 fixes): TC-292's `schema_version` expected value
    corrected from `"1.0"` to `"1.1"`. TC-311 rewritten from an
    open-question framing to a direct assertion against the resolved
    single-channel convention (`level_change_db = -3.0103 dB` for L=R).
    TC-313 rewritten from an open-question/numeric-proximity-only framing
    to a direct assertion of the `cancellation` boolean flag, matching the
    shipped DEF-101 regression guard. TC-381's budget figure corrected
    from "under 120 seconds" to "under 5 minutes (300s) worst-case,
    ~2.3 minutes typical," per architecture.md v2 §7.2/DEF-102, with the
    measured per-stage basis for the figure stated inline. Also corrected,
    found while fixing the four named items (same staleness class, not
    separately numbered in DEF-106's text): the governing-rule paragraph's
    "mono-cancellation −3 dB" description (value unchanged, meaning
    corrected); TC-312's cancellation-flag description (now references
    `excess_delta_db`, not raw `delta_db`); the "Open questions" section's
    items 1/2 (marked resolved, cross-referenced to the fix); the
    mandatory coverage checklist's TC-313 boundary-value description
    (TC-313 is no longer a threshold-boundary case); TC-380/381's slow-test
    notes (recommend isolated pytest invocation, per architecture.md v3
    §16/DEF-110); TC-382's note pointing to the corrected DEF-103 memory
    range; TC-390's note on `test_tc150` isolation (DEF-110, not a
    test-case-writer action item, but relevant context for anyone running
    this suite).
  - **DEF-107** (TC-302's 25 LU fixture did not actually discriminate a
    correct -20 LU gate from an incorrectly-copied -10 LU gate, since both
    configurations excluded the quiet cluster given the gate's
    mean-of-passing-blocks definition): TC-302 rewritten with an 18 LU
    separation and the full derivation of why 25 LU failed and 18 LU
    works, matching the shipped
    `test_tc302_lra_gate_discriminates_correct_vs_incorrect_relative_gate`
    fixture. TC-301's 12 LU baseline claim re-checked against the
    corrected gate math and confirmed still valid (unchanged).
  - **DEF-108** (TC-270–273's "dual-mono stereo, RMS = -20.00 dBFS"
    precondition would not reproduce the stated -20.0 LUFS expected
    value, since BS.1770's channel-summed convention gives dual-mono
    stereo content a genuinely different reading, ~-16.99 LUFS, than
    mono content at the same per-channel RMS): TC-270–273's precondition
    corrected from "dual-mono stereo" to "mono," matching both the stated
    expected value (-20.0 LUFS, which only holds for mono per STORY-001's
    own `test_tc010`) and the shipped
    `tests/test_ref_ac6_ac7_reused_metrics.py`'s `calibrated_tone_mono()`
    fixture. A fixture note is added explaining the mono-vs-dual-mono-
    stereo distinction explicitly, citing STORY-001's `test_tc010`/
    `test_tc010b` pair, so this is not silently "fixed" back to
    dual-mono stereo in a future revision.
