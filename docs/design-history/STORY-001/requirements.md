# STORY-001: World-class streaming master for Suno tracks — Requirements

Status: v2 — all open questions resolved, unblocked for architecture
Source: stories/STORY-001/Story.md

## 1. Restated intent

Build a tool that takes a raw, quality-inconsistent Suno-generated WAV export
of a long-form (7+ minute), 124 BPM melodic progressive house/techno track,
analyses it against the measurable criteria a mastering engineer would use
(loudness, true peak, dynamic range, frequency balance, stereo/mono
compatibility, clipping), and automatically masters it to streaming-ready
targets — without flattening the track's dynamic build/payoff — producing a
mastered WAV suitable for LANDR/Spotify distribution plus a before/after
measurement report that proves the improvement.

## 2. Audio quality targets

Targets explicitly given in the story (treat as authoritative):

- **Integrated loudness**: -14 LUFS integrated. Explicitly must not be
  "significantly louder" than this — the story treats -14 LUFS as a ceiling
  as much as a target, not a value to exceed via aggressive limiting.
- **True peak ceiling**: -1 dBTP, to leave headroom for lossy transcoding
  (Spotify/streaming codecs).
- **Dynamic range**: preserve dynamic range "appropriate to a long-form,
  build-driven track" — explicitly *not* festival/EDM loudness-war
  processing. No numeric crest-factor/DR target is given in the story.
  **This is a gap — see Open Questions #1.** Do not invent a DR/crest-factor
  number to fill it.
- **Mono compatibility**: full check required specifically on
  stereo-widened elements (phase/correlation issues on wide pads, synths,
  etc.).

Targets assumed from industry-standard methodology (not invented — these
are measurement standards, not target values) but **not stated in the
story, so flagged for confirmation before the architect treats them as
fixed**:

- Loudness measured per ITU-R BS.1770-4 (the standard underlying LUFS/EBU
  R128), including its gating (absolute gate -70 LUFS, relative gate -10 LU)
  when computing integrated loudness.
- True peak measured per ITU-R BS.1770-4 Annex 2 (minimum 4x oversampling)
  to catch inter-sample peaks, not just sample-value peaks.

**Resolved 2026-07-31** (see Open Questions in Section 8 for full rationale;
these are now authoritative for architecture/implementation):

- **Loudness tolerance**: target band -14.5 to -13.5 LUFS integrated
  (±0.5 LU). -13.5 LUFS is a hard ceiling (never exceed). The tool may
  land as low as -16 LUFS if hitting -13.5 would require dynamics-destroying
  limiting — in that case the report must state why the ceiling wasn't
  reached, rather than force it via over-limiting.
- **Dynamic range / crest factor**: output must retain a TT DR-meter value
  of at least **DR8**, AND must not be reduced by more than **3 dB**
  relative to the source's pre-master DR — whichever constraint is
  stricter binds. (E.g. a DR14 source must land at ≥DR11; a DR9 source
  must land at ≥DR8, not DR6.)
- **Frequency-balance thresholds** (genre-referenced for melodic
  progressive house/techno): thin low-end = 20–120 Hz energy >4 dB below
  a genre-reference low-end curve; muddiness = 200–500 Hz energy >3 dB
  above reference; harshness = 2–5 kHz energy >3 dB above reference.
  Corrective EQ is applied automatically when a flag triggers, capped at
  ≤3 dB per corrective move, and every correction made must be logged in
  the before/after report.
- **Mono-compatibility threshold**: phase correlation coefficient
  (-1..+1) must stay ≥0.0 across the track when summed to mono (never net
  phase-cancelling); target ≥+0.3 specifically on identified
  stereo-widened elements. Any dip below 0.0 is flagged and corrected
  (narrowing the offending element) before final output.
- **Output sample rate/bit depth**: 24-bit WAV, sample rate matches
  source (44.1 or 48 kHz); non-standard source rates default to 44.1 kHz.
  Treated as the final master deliverable (see Open Question #7
  resolution) — not a pre-master for further remastering downstream.

## 3. Input / output assumptions

**Input:**
- Format: WAV, as exported directly from Suno.
- Sample rate and bit depth: variable/unknown — Suno exports have been
  observed to vary; the tool must not assume a fixed sample rate or bit
  depth on input and must handle at minimum 44.1kHz and 48kHz, 16-bit and
  24-bit PCM (and ideally 32-bit float, since some export paths produce
  float WAV).
- Channel count: assumed stereo (matches the "stereo-widened elements"
  requirement) but the tool must detect and correctly handle a mono input
  without erroring (see Edge Cases).
- Loudness/quality: explicitly inconsistent track-to-track — the tool
  cannot assume any particular starting LUFS, peak level, or DR going in.
- Important caveat to carry forward (not a requirement, but relevant
  context for the architect and QA): Suno's own generation pipeline may
  itself introduce artifacts (aliasing, phase smearing, prior lossy
  encoding baked into the "raw" WAV) that predate this tool. Mastering
  should not be expected to "fix" generation-level artifacts — only to
  correctly measure and address standard mastering-stage criteria listed
  in the story.

**Output:**
- Format: WAV, 24-bit, sample rate matching source (44.1/48 kHz; other
  source rates default to 44.1 kHz on output). Resolved 2026-07-31 — see
  Section 8, Open Question #5.
- Destination/use: suitable for upload to LANDR for distribution, and
  ultimately Spotify. Treated as the **final master** — this tool
  replaces the manual mastering pass entirely; -14 LUFS/-1 dBTP are the
  final delivered values, not an intermediate target for LANDR to
  remaster further. Resolved 2026-07-31 — see Section 8, Open Question #7.
- The original input file must remain untouched; the master is written as
  a new/separate file (non-destructive processing — see NFRs).

## 4. Acceptance criteria

Numbered, testable. Where the story leaves a number undefined, the
criterion is written with a placeholder and flagged rather than guessed.

1. **Pre-master analysis report.** Given a raw Suno WAV export (any
   supported sample rate/bit depth/channel count), when the tool analyses
   it, then it must report, before any processing: integrated LUFS, true
   peak (dBTP), a dynamic range/crest-factor value, frequency-balance
   flags (muddiness/harshness/thin low-end), a stereo width/mono
   compatibility measurement, and clipping/distortion detection results.

2. **Loudness target.** Given the pre-master analysis, when mastering is
   applied, then the output integrated loudness must fall between -14.5
   and -13.5 LUFS (±0.5 LU), with -13.5 LUFS as a hard ceiling never to be
   exceeded (consistent with the story's "should not be significantly
   louder" instruction). The output may land as low as -16 LUFS if
   reaching -13.5 LUFS would require dynamics-destroying limiting, in
   which case the report must explain why. **Confirmed 2026-07-31 (see
   Section 8, Open Question #11)**: -16 LUFS is a soft, reported landing
   point, not an inviolable floor — the -1 dBTP ceiling and the dynamic
   range floor (AC4) are the two hard, never-violated constraints; if
   protecting both requires landing below -16 LUFS on a legitimate
   high-crest-factor track, the tool must do so and report the loudness
   value actually achieved plus the specific reason (in practice, the DR
   floor), rather than raise an error purely for landing under -16.

3. **True peak ceiling.** Given the mastered output, when true peak is
   measured with inter-sample-aware metering (4x+ oversampling), then no
   part of the file may exceed -1.0 dBTP. Zero exceptions tolerated on the
   delivered audio itself — this is the actual safety property and remains
   exact with no tolerance. **Confirmed 2026-07-31 (see Section 8, Open
   Question #12)**: this "zero exceptions" bar applies to the -1 dBTP
   ceiling on delivered audio, not to strict monotonicity of the metering
   implementation's own readings across different internal oversampling
   factors — a small documented tolerance (0.05 dB) on that internal
   self-consistency check is acceptable, since it reflects real
   filter-design limits in the measurement tool, not a relaxation of the
   delivered-audio guarantee.

4. **Dynamic range preservation.** Given the source track's pre-master
   DR/crest-factor measurement (TT DR-meter scale), when mastered, then
   the output DR must be at least DR8, AND must not be reduced by more
   than 3 dB relative to the source — whichever constraint is stricter
   binds. The report must show both values so a human can verify the
   track wasn't over-limited.

5. **Mono compatibility.** Given stereo-widened elements identified during
   analysis, when the mix is summed to mono, then the phase correlation
   coefficient must stay ≥0.0 across the track (never net phase-
   cancelling), with a target of ≥+0.3 on the identified stereo-widened
   elements specifically. Elements dipping below 0.0 must be narrowed
   until compliant. Report must show the before/after mono-compatibility
   measurement.

6. **Clipping/distortion detection and non-regression.** Given the source
   file, when analysed, then the tool must report the presence, count, and
   severity of clipped or distorted samples (sample-peak and inter-sample).
   Given the mastered output, the tool must guarantee zero additional
   clipping/inter-sample overs beyond the -1 dBTP ceiling — mastering must
   never introduce clipping that wasn't already present in the source.

7. **Frequency balance detection and correction.** Given the source and
   mastered files, when analysed, then the tool must report
   frequency-balance characteristics both before and after processing
   using these thresholds (genre-referenced for melodic progressive
   house/techno): thin low-end = 20–120 Hz >4 dB below reference;
   muddiness = 200–500 Hz >3 dB above reference; harshness = 2–5 kHz >3 dB
   above reference. When a flag triggers, the tool must apply corrective
   EQ automatically (capped at ≤3 dB per move) and log exactly what was
   changed in the before/after report.

8. **Before/after report.** Given a completed run, when it finishes, then
   the tool must produce a report covering all six assessment criteria
   from the story (loudness, true peak, dynamic range, frequency balance,
   stereo/mono compatibility, clipping/distortion) with both pre- and
   post-master values shown side by side, in a form a producer can read
   without needing to re-run analysis separately.

9. **Output file validity.** Given a successful mastering run, when the
   output WAV is produced, then it must be a valid 24-bit WAV file at the
   source's sample rate (44.1/48 kHz; other rates default to 44.1 kHz),
   suitable for LANDR/Spotify ingestion, and must not silently drop
   existing metadata/BWF chunks present in the source WAV (distinct from
   *authoring new* metadata, which is out of scope — see Section 5).

10. **Reproducibility.** Given the same input file processed twice with
    the same tool version and settings, when compared, then the
    measurement report and output audio must be effectively identical
    (deterministic processing — no unexplained run-to-run drift).

11. **Non-destructive processing.** Given any run, the original input file
    must remain unmodified on disk; all output (mastered WAV, report) must
    be written to new locations.

## 5. Explicit out-of-scope

- Metadata/ID3 tagging, artwork embedding, or authoring new metadata for
  distribution. (Not silently *destroying* existing metadata during
  processing is in scope per AC9 above — authoring/curating new metadata is
  not.)
- Multi-track/stem mastering — this story covers a single finished 2-mix
  WAV only, not individual stems.
- Creative/subjective remixing or arrangement changes — only corrective,
  mastering-stage processing against the six listed criteria.
- Uploading to LANDR or Spotify, or any distribution-platform interaction —
  the tool produces a file ready for that; the upload/distribution step
  itself is out of scope.
- Producing alternate delivery formats (MP3/AAC previews, etc.) — WAV
  output only unless a future story specifies otherwise.
- Batch processing of multiple tracks in a single run — the story describes
  a single-file workflow; batch is not addressed here (see Open Questions
  #7).
- Repairing/de-clipping already-clipped source audio (restoration) — not
  requested in the story; the story asks for detection/reporting of
  clipping, not audio repair. Flagged explicitly in Open Questions #5 in
  case this assumption is wrong.
- Platform-specific loudness variants beyond the -14 LUFS/-1 dBTP target
  given (e.g. Apple Music's own normalization at -16 LUFS, YouTube's
  algorithm) — only the target explicitly stated in the story is in scope.

## 6. Edge cases requiring explicit handling

- **Already-clipped input.** Source may already contain clipped/distorted
  samples. Tool must detect and report this (AC6) without erroring, and
  must not amplify or extend the clipping during mastering. Whether
  clipping should be repaired is an open question (#5); absent
  confirmation, assume detect-and-report only, mastering proceeds around
  it.
- **Mono source.** If a source WAV is mono (single channel) rather than
  stereo, the tool must detect this and skip/adjust stereo-width and
  mono-compatibility checks accordingly (trivially "compatible" since there
  is no stereo image to collapse) rather than erroring or reporting a
  false phase issue. Report should note the file was mono and why
  stereo-specific checks were not applicable.
- **Silence / near-silence in long builds.** Long-form builds in this genre
  routinely include quiet intros, breakdowns, or near-silent passages.
  Integrated loudness measurement must use standard BS.1770 gating so these
  sections don't improperly skew the LUFS reading, and the normalization/
  limiting stage must not attempt to "fill up" or over-compress quiet
  sections in a way that flattens the intended build/payoff dynamics
  (directly ties to the story's "preserve dynamic range" instruction).
  Analysis should also avoid false-positive clipping/distortion or
  frequency-balance flags triggered by very low-level noise floor content
  in near-silent passages.
- **Sample rate / bit depth variability from Suno exports.** As noted in
  Section 3, input sample rate and bit depth are not guaranteed consistent
  across exports. The tool must correctly read and process whatever
  combination it encounters (at minimum 44.1/48kHz, 16/24-bit, ideally
  32-bit float) and must not silently resample/truncate bit depth without
  it being a deliberate, reportable step (dithering must be applied if bit
  depth is reduced, to avoid introducing quantization distortion).
- **Extremely short or malformed files.** Tool should fail gracefully (with
  a clear error) rather than crash on corrupt WAV headers, zero-length
  audio, or files that don't match the expected long-form duration profile
  — this is a robustness expectation, not a story requirement change.

## 7. Non-functional requirements

- **Determinism/reproducibility**: identical input + settings must produce
  effectively identical output and report on every run (see AC10).
- **Non-destructive workflow**: original files are never modified in place
  (see AC11).
- **Fidelity vs. manual baseline**: since the story's explicit motivation is
  to replace "manual trial and error in Audacity/bx_mastering," the tool's
  output quality (on the six assessment criteria) should be at least
  equivalent to what a competent manual pass in that workflow would
  achieve. This is a quality bar, not a specific algorithm choice — the
  algorithm/plugin-chain choice is an architecture decision, not a
  requirements decision.
- **Processing time**: target under 5 minutes wall-clock (analysis +
  mastering combined) for a 7-10 minute track on typical consumer
  hardware. Offline/non-real-time processing; no faster-than-real-time
  requirement. Resolved 2026-07-31 — see Section 8, Open Question #8.
- **Robustness**: must not crash on the input variability described in
  Section 3 and the edge cases in Section 6; must report clear errors
  instead.
- **Traceability**: the before/after report must be retained and
  associated with the specific output file it describes, so results can be
  independently verified after the fact (supports the story's "improvement
  is visible and verifiable" requirement).

## 8. Open questions — resolved 2026-07-31

These were gaps the story left implicit or silent in v1. Each has now been
decided (by product owner, in conversation) using industry-standard
mastering practice and the story's own framing — an automated tool meant
to fully replace manual trial-and-error, not merely assist it. Decisions
are now authoritative for architecture/implementation; see Sections 2 and
4 for where each is applied.

1. **Tolerance bands** — RESOLVED. Loudness: -14.5 to -13.5 LUFS (±0.5 LU),
   -13.5 LUFS hard ceiling; may land as low as -16 LUFS rather than
   over-limit to hit the ceiling. Dynamic range: ≥DR8 (TT DR-meter scale)
   AND no more than 3 dB reduction from source DR, whichever is stricter.
   Mono compatibility: phase correlation ≥0.0 overall, ≥+0.3 target on
   stereo-widened elements specifically. Rationale: these are the
   conventional professional tolerances for streaming-targeted masters in
   non-EDM electronic genres, consistent with the story's explicit
   instruction not to over-limit a build-driven track.
2. **Measurement standard** — RESOLVED. ITU-R BS.1770-4 is the reference
   standard (absolute gate -70 LUFS, relative gate -10 LU for integrated
   loudness; ≥4x oversampling for true peak). This is the standard
   underlying Spotify's and virtually all streaming platforms' loudness
   normalization, and the correct basis given the story's "optimised for
   streaming platforms" goal. No proprietary/plugin-specific algorithm is
   to be treated as the reference.
3. **Frequency balance** — RESOLVED. Thresholds: thin low-end = 20–120 Hz
   >4 dB below a genre-reference curve; muddiness = 200–500 Hz >3 dB
   above reference; harshness = 2–5 kHz >3 dB above reference (genre:
   melodic progressive house/techno, 124 BPM). Corrective EQ **is**
   applied automatically when a flag triggers (capped ≤3 dB per move,
   fully logged in the before/after report) — not report-only. Rationale:
   the story's premise is a tool that masters "without manual trial and
   error," which implies automated correction, not merely flagging issues
   for the producer to fix by hand elsewhere.
4. **Clipping repair** — RESOLVED. Detect and report only; mastering
   proceeds around existing damage without attempting de-click/de-clip
   repair. Rationale: repair of already-damaged source audio is a
   materially different (and riskier) capability than mastering
   correction, not requested in the story, and out of scope per Section 5.
5. **Output sample rate/bit depth** — RESOLVED. 24-bit WAV, sample rate
   matches source (44.1/48 kHz), non-standard rates default to 44.1 kHz.
   Rationale: 24-bit preserves headroom/precision through the mastering
   chain and is accepted by both LANDR and Spotify; matching source rate
   avoids an unnecessary resampling step and its associated artifacts.
6. **Batch processing** — RESOLVED. Out of scope for this story;
   single-file processing only. Batch may be addressed in a future story
   if needed.
7. **LANDR relationship** — RESOLVED. Output is treated as the **final
   master** for direct distribution, not a pre-master for LANDR to
   remaster further — -14 LUFS/-1 dBTP (banded per #1) are the final
   delivered values. Rationale: the story's explicit goal is to replace
   the manual mastering workflow entirely; treating this tool's output as
   provisional would leave the "release-ready" requirement unmet.
8. **Processing time budget** — RESOLVED. Target under 5 minutes
   wall-clock for a 7-10 minute track on typical consumer hardware;
   offline processing, no faster-than-real-time requirement.
9. **Metadata preservation** — RESOLVED. Existing metadata/BWF chunks in
   the source WAV must be preserved through processing unchanged (see
   AC9). Authoring *new* metadata remains out of scope (Section 5).
10. **Safety copy / re-run support** — RESOLVED. No dedicated
    versioning/safety-copy feature is needed. AC11 (original input file
    always left untouched, non-destructive processing) already permits
    re-running mastering with different settings against the same
    original export; further file-management is the user's
    responsibility.
11. **-16 LUFS: hard floor or soft landing point?** — RESOLVED 2026-07-31.
    Architecture v4 surfaced a genuine conflict discovered during QA/dev:
    for legitimate high-crest-factor long-form tracks (the story's actual
    core use case — quiet sustained body, brief near-ceiling transients),
    no gain value can satisfy the DR floor (AC4) and a hard -16 LUFS floor
    simultaneously, because BS.1770 gating makes integrated loudness track
    the near-ceiling transients rather than the body, so raising gain
    toward -16 erodes DR below its floor first. **Decision: the DR floor
    and the -1 dBTP ceiling are the two hard, non-negotiable constraints;
    -16 LUFS is a soft, reported landing point, not an inviolable floor.**
    Rationale: the DR floor is the number most directly tied to the
    story's explicit "don't flatten the build/payoff" creative intent, and
    AC2's own original phrasing ("may land as low as -16 LUFS... report
    must explain why") already read as describing an expected landing
    point under adverse conditions rather than an absolute floor backed by
    an error condition. See AC2 above and architecture.md §1/§10/§12 (v4)
    for the full technical rationale and rejected alternatives (an
    upstream RMS/multiband leveler; recalibrating the DR-floor rule
    instead). If, in production use, tracks land below -16 LUFS more often
    than the "genuinely rare" expectation, that's a signal to revisit this
    decision, not something to silently tolerate.
12. **True-peak metering: does "zero exceptions" (AC3) extend to
    cross-oversampling-factor monotonicity?** — RESOLVED 2026-07-31.
    Architecture v4 (DEF-002 fix) found that soxr (and general resamplers
    generally) have real, unavoidable passband attenuation near Nyquist,
    which is the wrong optimization target for true-peak metering
    (correctly fixed via a purpose-built FIR filter — see
    architecture.md §2/§12 v4). Even a well-designed replacement filter
    won't be perfectly flat to floating-point precision at Nyquist, so a
    strict monotonicity assertion between oversampling factors (e.g. 4x
    reading must be ≥ 2x reading) is unreasonably tight for a synthetic
    near-Nyquist test tone. **Decision: AC3's "zero exceptions" bar applies
    to the -1 dBTP ceiling on delivered audio (which remains exact, no
    tolerance, no rounding toward "safe"); a small documented tolerance
    (0.05 dB) is acceptable specifically for cross-factor self-consistency
    test assertions**, since that's a property of the measurement tool's
    own internal precision, not of the delivered master's safety margin.

## 9. Revision history

- v1 (2026-07-31): Initial requirements produced from Story.md. No prior
  requirements.md or defects.md existed for this story.
- v2 (2026-07-31): All ten open questions from v1 resolved (Section 8);
  Sections 2, 3, 4, and NFRs updated with the resulting concrete
  numbers/decisions. Requirements are now unblocked for architecture work.
- v3 (2026-07-31): Resolved two new open questions (#11, #12) raised by
  architecture.md v4 during defect resolution (DEF-001, DEF-002): -16 LUFS
  confirmed as a soft, reported landing point rather than a hard floor
  (AC2 updated); AC3's "zero exceptions" bar confirmed to apply to the
  -1 dBTP delivered-audio ceiling, not to strict cross-oversampling-factor
  monotonicity in the metering implementation's own test assertions (AC3
  updated). Unblocks architecture.md v4's two "assumptions pending BA
  confirmation" (§10) for implementation.
