# STORY-003 Requirements: Ground-Truth Test Harness

## Restated intent

Every measurement function in the analysis layer (STORY-001's core six
plus STORY-002's five additions) must be checked against synthetic
signals whose correct output is known by construction — not against
values the tool itself previously produced. This closes DEF-204 (the
test-suite coverage gap that let DEF-201, DEF-202, DEF-203 ship
undetected) by modifying the *existing* implementation and test suite
in place; it does not create a parallel test tree, and it fixes
DEF-201 and DEF-203 as part of the same pass, with the fix for each
demonstrably preceded by a test that fails against the pre-fix code.

## Grounding — where this work happens

- **Implementation** lives at
  `stories/STORY-001/implementation/suno_mastering/analysis/` (11
  measurement modules: `loudness.py`, `true_peak.py`,
  `dynamic_range.py`, `frequency_balance.py`, `stereo_phase.py`,
  `clipping.py` from STORY-001; `loudness_range.py`, `mono_sum.py`,
  `hf_extension.py`, `seven_band_balance.py`,
  `per_band_stereo_width.py` from STORY-002), plus shared helpers in
  `_psd.py` and `silence.py`.
- **Tests** live at `stories/STORY-001/implementation/tests/` — this
  is where STORY-002's own `test_ref_*.py` files already live
  alongside STORY-001's `test_ac*.py` files. New ground-truth tests
  belong in this same directory (new files within it, e.g.
  `test_ground_truth_*.py`, or additions to the existing per-AC
  files — architect's call), **not** in a new
  `stories/STORY-003/implementation/` tree. The story is explicit on
  this point and it is easy to get wrong by default.
- **Defects DEF-201/202/203/204** are recorded in
  `stories/STORY-002/defects.md`, not this story's own folder. Any
  resolution this story reaches must update entries in that file
  (mark status, add fix notes) — per this project's standing
  convention, do not delete the original entries.

## Public measurement-function inventory (scope anchor for the architect)

Confirmed by reading the modules directly (function signatures as
shipped):

**STORY-001 core six** (wired together via `analysis/__init__.py::measure_all`):
1. `loudness.measure_integrated_lufs(audio, sr) -> float`
2. `true_peak.measure_true_peak(audio, sr, config) -> TruePeakResult`
3. `dynamic_range.measure_dynamic_range(audio, sr, config) -> float`
4. `frequency_balance.measure_frequency_balance(audio, sr, config) -> FrequencyBalanceResult`
5. `stereo_phase.analyze_stereo_phase(audio, sr, config) -> StereoPhaseResult`
6. `clipping.detect_clipping(audio, sr, config, true_peak_result=None) -> ClippingResult`

**STORY-002 additions** (not currently wired into `measure_all` — see
DEF-202, out of scope note below):
7. `loudness_range.measure_loudness_range(audio, sr, config) -> LraResult`
8. `mono_sum.measure_mono_sum(audio, sr, config) -> MonoSumResult` (stereo only)
9. `hf_extension.measure_hf_extension(audio, sr, config) -> HfExtensionResult`
10. `seven_band_balance.measure_seven_band_balance(audio, sr, config) -> SevenBandResult`
11. `per_band_stereo_width.measure_per_band_stereo_width(audio, sr, config) -> PerBandWidthResult` (stereo only)

**Boundary call, flagged not assumed**: several public functions are
transforms/helpers rather than end-to-end measurements —
`loudness_range.k_weight`, `true_peak.oversample`,
`stereo_phase.correlation_coefficient`,
`silence.block_rms_db`/`active_block_mask`/`extract_active_audio`.
AC1 ("every public measurement function") is written against the 11
functions above. Recommend also covering `k_weight` (ground truth is
cheap: apply to a known-frequency sine and check against BS.1770's
published K-weighting gain at that frequency) and `oversample` (ground
truth is cheap: known inter-sample-overshoot construction) directly,
since both are exactly the kind of load-bearing internal machinery a
wrong ground truth would silently corrupt every downstream measurement
that calls them — but this is a scope decision for the architect to
confirm, not an assumption this document makes for them.

## Acceptance criteria

Numbered as pass/fail conditions. Each corresponds to a requirement in
story.md's "Required ground-truth tests" / "Sanity assertions"
sections; nothing below invents a new engineering target that
story.md did not already state or that is not derived from ITU-R
BS.1770 / EBU Tech 3342's own published constants.

1. **Coverage.** Given the 11 measurement functions listed above, when
   the ground-truth suite runs, then each has at least one test whose
   expected value is derived analytically from the test signal's
   construction (not obtained by running the function under test) —
   satisfies story.md's AC1.
2. **Programmatic signals.** Given any ground-truth test, when its
   fixture is inspected, then the signal is generated via
   numpy/scipy in the test itself — no `.wav`/`.flac` fixture files
   are loaded by this suite.
3. **Derivation stated inline.** Given any ground-truth test, when its
   source is read, then a comment states *why* the expected value is
   correct (the derivation), not just the number.
4. **Loudness (LUFS).**
   - 4a. Given a 1 kHz sine at a known dBFS amplitude, when measured,
     then integrated LUFS is within ±0.1 LU of the value ITU-R
     BS.1770-4 predicts for that amplitude (K-weighting gain at 1 kHz
     is ≈0 dB, so the expected LUFS is directly derivable from the
     sine's RMS level plus the -0.691 dB BS.1770 offset — same
     derivation basis STORY-001's own `test_tc010` already uses;
     reuse/extend rather than re-derive from scratch).
   - 4b. Given the same signal at two gain levels 6 dB apart, when
     both are measured, then the integrated-loudness difference is
     6 ± 0.1 LU.
5. **True peak (dBTP).**
   - 5a. Given a signal engineered so the true (inter-sample) peak
     exceeds the sample peak by a known margin (e.g. a full-scale sine
     at a frequency chosen so its inter-sample maxima fall between
     sample positions — classic near-Nyquist construction), when
     measured, then `measure_true_peak`'s `dbtp` exceeds the plain
     sample-peak reading by approximately that known margin.
   - 5b. Given that same signal, when both a naive sample-peak
     computation and `measure_true_peak` are run, then they return
     *different* values — a test asserting they match must fail (this
     is the direct regression guard against true peak silently
     degrading to sample peak).
6. **HF extension / rolloff — DEF-201's defect surface.**
   - 6a. White noise brickwalled at exactly 15 kHz → detected rolloff
     within one Welch-PSD bin width of 15 kHz (bin width = `sr /
     welch_nperseg(...)`, from `_psd.py`; the exact tolerance figure
     is an open question below, but it cannot be tighter than one
     bin — that bound is derived from the shipped PSD parameters, not
     invented).
   - 6b. White noise brickwalled at exactly 8 kHz → same, within one
     bin of 8 kHz.
   - 6c. Full-band white noise (no cutoff) → reported rolloff is
     "no cutoff" or Nyquist — not a mid-band value.
   - 6d. **Pink noise with no cutoff → reported rolloff is "no
     cutoff."** This is the literal DEF-201 regression case: pink
     noise's natural spectral tilt must not trigger the detector.
   - 6e. Signal whose cutoff changes partway through (e.g. first half
     brickwalled at 15 kHz, second half at 8 kHz) → drift/instability
     is flagged (`stable=False` or equivalent).
7. **Dynamic range / LRA.**
   - 7a. Constant-level sine (no dynamics) → both `measure_dynamic_range`
     and `measure_loudness_range`'s `lra_lu` read near zero.
   - 7b. Two-level signal (loud block / quiet block) with a known,
     *correctly gate-calibrated* separation → LRA approximates that
     separation within a stated tolerance. Per STORY-002's own
     DEF-107 finding (already recorded in `stories/STORY-002/defects.md`):
     LRA's relative gate operates against the **mean of passing
     blocks**, not directly against the loud cluster's level, so a
     naive "loud/quiet dB difference" fixture does not simply
     reproduce that difference as LRA — the test must derive the
     expected LRA through the same gate-mean arithmetic DEF-107's fix
     used (or reuse the corrected 18 LU two-level fixture pattern
     STORY-002's own `test-cases.md` v2 / TC-302 already
     established), not invent a new uncalibrated separation.
   - 7c. Verify LRA is measurably different from a naive
     peak-to-trough-of-whole-file computation (i.e. the gating logic
     is actually exercised, not bypassed) — construct a case where the
     two would disagree if gating were absent.
8. **Spectral balance (`frequency_balance`, `seven_band_balance`).**
   - 8a. Band-limited noise confined to exactly one of the seven
     bands → that band's relative level dominates; all other bands
     read near the measurement floor.
   - 8b. Equal-energy (flat) white noise → relative levels across
     bands are derivable from each band's width in Hz (wider bands
     integrate more power) — assert against that derived distribution,
     not an arbitrary one.
   - 8c. Energy placed at exactly a band boundary frequency → assert
     it is attributed consistently with the boundary convention the
     code implements (inclusive/exclusive — read from `_psd.band_power`
     / the `seven_bands_hz` config, do not assume).
9. **Stereo width / correlation (`stereo_phase`, `per_band_stereo_width`, `mono_sum`).**
   - 9a. Identical L and R → `correlation_coefficient` returns 1.0;
     `per_band_stereo_width` reads ≈0 (fully correlated) in every band.
   - 9b. Inverted R (L = -R) → correlation -1.0; mono-sum level reads
     near-silent (→ -inf or the configured noise floor).
   - 9c. Uncorrelated noise in L and R (independent generators, equal
     power) → correlation near 0.0.
   - 9d. **Mono-sum level change for cases 9a-9c, and DEF-203's
     resolution** — see the dedicated section below. This is the
     test that AC6 requires be demonstrably failing (if it is a real
     defect) before any fix lands.
10. **Sanity assertions run in production code, not just tests.**
    Given any of the following physically-impossible outputs, when
    `measure_all`/the STORY-002 measurement functions run against any
    input, then the result is flagged/rejected and the flag surfaces
    in the human-readable report, not only in a test:
    - HF rolloff reported below 5 kHz while measured air-band
      (10-24 kHz) energy is above -40 dB relative to the reference
      band → fail/flag (this is DEF-201's own report-review finding,
      restated as a standing invariant).
    - Correlation coefficient outside [-1.0, 1.0] → fail.
    - Any seven-band relative level implausibly far from its
      neighbours → warn (exact "implausibly far" threshold is an open
      question below — flag, do not invent a dB figure).
    - **Explicit exemptions, required, not optional** (see "Known
      degenerate cases" below): LUFS below -70 is *not* automatically
      a failure — pyloudnorm legitimately returns `-inf` for
      silence/near-silence, and STORY-001's own
      `test_silence_dynamics.py` already exercises this. The sanity
      rule must distinguish "measured -inf on a silent/near-silent
      buffer" (expected, not a failure) from "measured a finite value
      below -70 LUFS on non-silent audio" (physically suspect,
      should fail) — or the story's literal "LUFS above 0 or below
      -70 -> fail" rule will produce false positives against existing,
      correct behavior.
11. **Ordering evidence for DEF-201 and DEF-203 (AC6).** For each of
    DEF-201 and DEF-203, the work must produce, before any production
    code changes: the new test's name, the assertion that fails, and
    the actual-vs-expected values at the point of failure — recorded
    in `stories/STORY-002/defects.md` under the relevant entry. A fix
    landing without this evidence on record does not satisfy AC6, even
    if the post-fix test passes. See the DEF-203 branch below: if
    first-principles derivation shows the shipped constant was already
    correct, this evidence requirement is satisfied differently (see
    that section) — it is not waived, its form changes.
12. **Runtime.** The ground-truth suite (the tests added by this
    story, run as a named/selectable subset — see Non-functional
    requirements) completes in under 30 seconds.
13. **Report/schema consequences of AC10 (sanity warnings) are
    surfaced, not silently absorbed.** If a sanity-check flag is added
    to any result type, this is an additive schema change under this
    project's existing convention (DEF-101 precedent: additive field →
    `SCHEMA_VERSION` bump, e.g. `"1.1"` → `"1.2"`). The exact
    version number and field placement are the architect's call;
    the requirement is that a bump happens and both renderers
    (`report/reference_render.py` for the reference-set path, and
    STORY-001's own report path for pre/post-master) are updated
    consistently, not just the analysis-layer dataclasses.

## DEF-203 — required derivation, not a presupposed fix

Story.md's brief (and the task that spawned this pass) describes
DEF-203 as: "mono-sum excess-cancellation baseline is suspected wrong
(uses -6.02 dB where -3.01 dB is the correct theoretical value)."
**This document does not adopt that framing as settled** — STORY-002's
own defects.md (DEF-101/DEF-104) previously investigated the same
mono-sum floor and arrived at -6.0206 dB for the broadband
`excess_cancellation_db` field specifically because the broadband
`level_change_db` formula and the per-band `delta_db` formula
normalize against *different* denominators (channel-summed stereo
power vs. per-channel-mean band power, respectively) and therefore
have two different, both-legitimate ρ=0 floors. DEF-203's report does
not appear to account for this distinction (it says "-3.01 dB is
correct" without specifying which of the two formulas it means), and
the "narrow spread across five references" observation it treats as
suspicious is also consistent with ordinary commercial masters simply
having a fairly consistent, moderately-high inter-channel correlation
(ρ roughly 0.5-0.8 is typical for center-heavy stereo mixes) —
that is a property of the reference material, not necessarily evidence
of a wrong constant.

**Requirement, not a resolution**: the ground-truth test for mono-sum
must derive `level_change_db`'s expected value from first principles
for ρ ∈ {+1, 0, -1} using synthetic L/R signals with *known,
constructed* correlation, and the derivation comment must state
explicitly which denominator (channel-summed stereo power, vs.
per-channel-mean band power) the formula being tested uses — this is
exactly the ambiguity that produced two candidate numbers in the first
place, and stating it explicitly is what prevents this defect
recurring a third time. Whichever of (a) the shipped `-6.0206 dB`
broadband constant, or (b) DEF-203's claimed `-3.0103 dB`, disagrees
with that derivation is what gets corrected.

**AC6 branch, stated explicitly so it does not surprise QA**: if the
derivation confirms the shipped `-6.0206 dB` constant was already
correct (i.e. DEF-203 is not a real defect), then a correctly-written
test for it will pass on first run against the *current*, unmodified
code — it cannot be "demonstrably failing before the fix," because
there is no fix. In that case:
- The ground-truth test is still added (it becomes the permanent
  derivation-of-record for this metric, satisfying story.md's core
  principle).
- DEF-203 is closed in `stories/STORY-002/defects.md` as
  **not-a-defect**, with the full derivation recorded inline (not
  just a status change) so a fourth investigation of this same
  question does not have to re-derive it.
- AC6's "write a failing test first" requirement is satisfied for
  DEF-201 only; this is a deliberate, documented exception, not a
  silent gap — record it as such in the same defects.md entry.
If instead the derivation finds the shipped constant *is* wrong (in
whole or in part — e.g. correct for the broadband case but not
propagated correctly to some downstream consumer), proceed per AC11
(write the failing test, confirm the failure, record it, then fix).

## Known degenerate cases the sanity assertions must not misfire on

Confirmed by reading the shipped code, not assumed:
- `loudness.measure_integrated_lufs` legitimately returns `-inf` for
  silence-only or extremely short buffers (documented in the module's
  own docstring; exercised by STORY-001's existing
  `test_silence_dynamics.py`). A blanket "LUFS below -70 → fail" rule
  must exempt this case or it regresses existing, correct behavior.
- `stereo_phase.correlation_coefficient` returns exactly `1.0` when
  both channels are silent/null (by design — "treat as compatible, not
  undefined," per the module's own comment), not `NaN` or an error.
  A "correlation outside [-1,1] → fail" rule is satisfied by this
  design already (1.0 is in-range) but the ground-truth test suite
  should assert this specific degenerate-input behavior explicitly so
  a future change to the null-handling doesn't silently drift.

## Audio-quality / correctness targets

This story is about the *measurement* layer's correctness, not about
mastering targets — but several of its ground-truth tolerances trace
to published standards, and this document states them explicitly
rather than leaving them implicit:

- **LUFS accuracy**: ±0.1 LU against ITU-R BS.1770-4-derived expected
  values (story.md's own figure; matches STORY-001's existing
  `test_tc010` tolerance).
- **6 dB gain → 6 LU loudness change**: ±0.1 LU (same basis).
- **HF rolloff tolerance**: bounded below by one Welch-PSD bin width
  (`sr / welch_nperseg(...)`, from the shipped `_psd.py`) — this is a
  derived floor, not an invented figure. The exact tolerance to use
  (one bin vs. some wider multiple, to absorb window/leakage effects)
  is an open question below.
- **HF rolloff sanity floor**: "below 5 kHz with air-band energy
  above -40 dB relative → fail" is story.md's own stated figure,
  restated here, not altered.
- **Mono-sum ρ=0 floors**: `-6.0206 dB` (broadband,
  `10*log10(0.25)`) and `-3.0103 dB` (per-band,
  `10*log10(0.5)`) — both are exact, closed-form values derivable
  from BS.1770's channel-summed convention given equal-power,
  zero-correlation channels; see the DEF-203 section above for which
  applies to which field, and the requirement that the ground-truth
  test re-derive this rather than take either number on trust.
- **Correlation range**: [-1.0, 1.0], exact by definition of a
  normalized cross-correlation — any value outside this range is a
  computation bug, not a measurement of real audio.
- **LRA gate calibration**: per DEF-107 (STORY-002 defects.md,
  closed), the relative gate compares against the mean of passing
  blocks, not the loud cluster's own level directly — any LRA
  ground-truth fixture must account for this or it will not
  discriminate a correct implementation from an incorrect one (this
  is exactly the failure DEF-107 found in the *test design*, not the
  implementation).

**Not stated because story.md does not state them and none of the
above derivations produce them** — flagged as open questions, not
guessed: the exact numeric tolerance for HF rolloff detection beyond
"at least one PSD bin," and the numeric threshold for "implausibly far
from other bands" in the seven-band sanity warning.

## Input/output assumptions

- Test signals are synthetic, generated in-process via numpy/scipy
  (sine waves, white/pink noise, band-limited noise, brickwall-
  filtered noise, engineered inter-sample-peak constructions). No
  `.wav`/`.flac`/`.mp3` fixture files are read by this suite (story.md
  NFR, restated as AC2).
- Signals are short: 2-5 seconds (story.md NFR), sufficient for the
  measurement functions' own minimum-duration requirements (e.g.
  `hf_extension`'s `config.hf_min_duration_s` floor — confirm the
  chosen signal lengths clear this, do not pick an arbitrary duration
  that silently trips the "insufficient duration" branch instead of
  exercising the real measurement path).
- Mono vs. stereo: `mono_sum` and `per_band_stereo_width` require
  genuine stereo (samples, 2) input — callers are documented as
  responsible for not calling them on mono; ground-truth tests for
  these two must construct stereo fixtures, not rely on mono
  broadcasting.
- Output: no new production output format is introduced by this
  story. Any new sanity-warning fields are additive to existing
  result dataclasses/report schema (see AC13).

## Explicit out-of-scope

- **DEF-202** (mastering stage not consuming STORY-002's reference
  measurements) is explicitly **not** addressed by this story. It is
  a pipeline-wiring/architectural connection between the mastering and
  reference-analysis stages, not a measurement-correctness defect, and
  story.md's own scope is the measurement layer's ground-truth
  verification. Do not let DEF-204's closure (item below) be read as
  implying DEF-202 is also closed — it remains open, tracked
  separately in `stories/STORY-002/defects.md`.
- **DEF-204 itself** is closed by virtue of this story's completion
  (the coverage gap it names is what the ground-truth suite fixes),
  but that closure should be recorded explicitly in
  `stories/STORY-002/defects.md` once the suite lands, not assumed.
- This story does not add new measurements, new audio processing
  stages, or new mastering behavior. It verifies existing measurement
  functions and fixes exactly two named code-level defects (DEF-201,
  and DEF-203 pending its derivation outcome above).
- No parallel test infrastructure, test runner, or CI configuration
  change is in scope beyond what's needed to select the 30-second
  ground-truth subset (see Non-functional requirements) — the
  mechanism for that selection is an architecture decision, not
  specified here.
- HF rolloff *detection method* (deeper threshold vs. slope-based
  cliff detection, per DEF-201's two suggested options) is not decided
  by this document — flagged for the architect below.

## Non-functional requirements

- **Runtime**: the ground-truth suite completes in under 30 seconds
  (story.md NFR / AC5). Given the existing test tree already contains
  multi-minute NFR tests (e.g. `test_tc150`'s 5-minute processing
  budget, `test_nfr_performance.py`), the 30-second figure is only
  meaningful if the ground-truth tests are selectable as a distinct
  subset (pytest marker, filename convention, or directory — the
  mechanism is the architect's call) so `pytest <ground-truth subset>`
  can be timed independently of the full suite.
- **Session-scoped fixtures**: any synthetic signal reused across
  multiple tests (e.g. a standard 1 kHz calibration tone, a standard
  pink-noise buffer) should be a session-scoped pytest fixture, not
  regenerated per test (story.md NFR).
- **No regression**: adding sanity assertions to production code paths
  must not change existing measurement *values* for any currently-
  passing STORY-001/STORY-002 test — only add flags/warnings alongside
  them. Re-run the full existing suite (`test_ac*.py`, `test_ref_*.py`)
  after any production-code change and confirm no regressions, per
  this project's standing convention (see e.g. DEF-103's own
  regression-testing practice in STORY-002 defects.md).
- **Reproducibility**: ground-truth tests use fixed random seeds for
  any noise-based fixture (white/pink noise generators), so failures
  are deterministic and reproducible, not flaky.

## Open questions (flagged, not guessed)

1. **HF rolloff detection method**: DEF-201 offers two concrete
   options — a much deeper threshold (-30 to -40 dB relative) or
   slope-based cliff detection (dB/octave sustained across adjacent
   bins). This document does not choose between them; it is an
   architecture-level decision with real implementation-cost
   differences. Routed to the architect.
2. **HF rolloff detection numeric tolerance**: bounded below by one
   Welch-PSD bin width (derived, stated above) but no upper figure is
   specified by story.md. Needs an architect/QA decision, informed by
   whichever detection method is chosen in (1).
3. **"Implausibly far from other bands" threshold** (seven-band sanity
   warning, story.md's own sanity-assertions section): no numeric
   value is given anywhere in story.md or the existing config. Needs
   a value before AC10's seven-band sanity check can be implemented as
   a concrete test, not just a placeholder.
4. **Sanity-warning schema placement and version bump target**: which
   result dataclass(es) carry the new flags, and what the new
   `SCHEMA_VERSION` string is (see AC13). Routed to the architect,
   following the DEF-101 additive-field precedent already in this
   codebase.
5. **`HfExtensionResult.rolloff_hz`'s "no cutoff" representation**:
   the field is currently `float | None`, where `None` already means
   "insufficient duration" (per the shipped `measure_hf_extension`
   code). Story.md's requirement that full-band/pink-noise material
   report "no cutoff, or Nyquist, NOT a mid-band value" needs a
   distinct representation from the existing `None`/insufficient-
   duration case, or the two will be conflated. Routed to the
   architect as a return-contract change.
6. **DEF-203's outcome** is itself an open question this story exists
   to resolve empirically (see the dedicated section above) — flagging
   here as a reminder that requirements.md deliberately does not
   pre-answer it.
7. **Ground-truth-subset selection mechanism** for the 30-second
   runtime budget (marker, filename convention, or directory) —
   routed to the architect; whichever is chosen should be consistent
   with how `test_ref_*.py` vs. `test_ac*.py` are already
   distinguished in this same test tree.
