# STORY-001: World-class streaming master for Suno tracks — Test Cases

Status: v2 — based on requirements.md v3 (all open questions, including
#11/#12, resolved) and architecture.md v5 (resolves the soft-LUFS-floor
solver redesign for high-crest-factor sources, the true-peak FIR filter
replacing `soxr`, and the v5 tiered true-peak passband-ripple envelope).
This revision updates TC-016 and TC-130 to match the v4 soft-LUFS-floor
solver contract and adds TC-025 to specify the v5 tiered ripple-envelope
frequency sweep, per defects.md DEF-001/DEF-002's 2026-08-01
qa-automation-engineer/python-developer verification notes. See "Revision
history" at the end of this document for the full change log of what
changed and why.

Scope note: per architecture.md §7, every `analysis/*` and `mastering/*`
module takes plain numpy arrays + sample rate (+ config), not file paths.
Test cases below are written so they can be executed either at the
module/function level (preferred for the DSP-heavy cases — faster, more
precise root-causing) or end-to-end through `pipeline.master()` (required
for the report/reproducibility/non-destructive cases, which are inherently
pipeline-level concerns). Each test case's "Level" is noted alongside its
Type where it matters.

All thresholds referenced below are the config.py defaults per
architecture.md §6: LUFS band [-14.5, -13.5] (a soft target band; -13.5 is
a hard ceiling never to be exceeded), -16 (`config.lufs_floor`) is a
**soft, report-escalation threshold only — not a hard solver constraint**
as of architecture.md v4 §1 (see requirements.md v3 §8 Open Question #11),
true-peak ceiling -1.0 dBTP, oversampling ≥4x (implementation target 8x),
DR floor DR8 / max-reduction 3 dB (stricter binds) — this DR floor and the
-1.0 dBTP ceiling are the solver's only two hard constraints — frequency-
band thresholds (thin low-end < -5.5 dB relative, muddiness > 0.0 dB
relative, harshness > -1.0 dB relative, EQ move cap ≤3 dB), phase
correlation floor 0.0 / target +0.3 on stereo-widened elements, output
24-bit / 44100 or 48000 Hz (default 44100), seeded TPDF dither.

---

## 1. AC1 — Pre-master analysis report

### TC-001 — Full six-criteria pre-master report on a representative track
- **Type**: functional
- **Level**: pipeline (stage [2] in isolation, or full `pipeline.master()`)
- **Covers**: AC1
- **Preconditions**: synthetic stereo WAV, 48 kHz / 24-bit PCM, ~3 minutes,
  constructed with deliberately non-neutral characteristics on all six
  criteria (moderate loudness, a few sample-peak clips, non-flat frequency
  balance, one out-of-phase stereo region, DR in the mid-teens) so every
  field in the report has a genuinely non-trivial value to check.
- **Steps**: Run pre-master analysis (stage [2]) against the untouched
  buffer only (no mastering stages invoked).
- **Expected result**: report/`Measurements` object contains a non-null
  value for each of: integrated LUFS, true peak (dBTP), DR (TT DR-meter
  value), frequency-balance flags (thin-low-end/muddiness/harshness,
  each True/False + measured dB relative to reference), stereo
  width/mono-compatibility correlation value, and clipping/distortion
  detection results (count + severity). No exceptions raised.

### TC-002 — Pre-master analysis runs against the *original* sample rate, before resample
- **Type**: functional (architecture stage-ordering guard)
- **Level**: pipeline
- **Covers**: AC1, architecture.md §1 stage-order note ("must run before
  stage [3]'s resample")
- **Preconditions**: synthetic stereo WAV at a non-standard sample rate
  (e.g. 32 kHz), containing a calibrated 1 kHz sine at a known dBFS level.
- **Steps**: Run the full pipeline with instrumentation/logging enabled on
  stage [2] and stage [3]; capture the sample rate and LUFS/true-peak
  values stage [2] actually measured against.
- **Expected result**: stage [2]'s reported sample rate equals the
  source's native 32 kHz (not 44.1 kHz), and its LUFS/true-peak values are
  computed against the native-rate buffer. The resample to 44.1 kHz is only
  observed to occur in stage [3], strictly after stage [2] has already
  produced its "before" measurements. If a build inverts this order, this
  test must fail (this is the specific regression guard for the ordering
  rule).

### TC-003 — Mono input still produces a complete report with stereo fields marked not-applicable
- **Type**: functional / edge case
- **Level**: pipeline
- **Covers**: AC1, requirements.md §6 "Mono source"
- **Preconditions**: synthetic mono (single-channel) WAV, 44.1 kHz/16-bit.
- **Steps**: Run pre-master analysis.
- **Expected result**: report is produced without error; stereo-width/mono-
  compatibility field is present but explicitly marked as "not applicable —
  mono input" (or equivalent), not a false correlation value, and not a
  crash from an assumed second channel.

---

## 2. AC2 — Loudness target (integrated LUFS, BS.1770-4)

### TC-010 — BS.1770 calibration: 1 kHz sine at known RMS reads correct LUFS
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/loudness.py`)
- **Covers**: AC2, architecture.md §7 ("use published ITU-R BS.1770/EBU
  Tech 3341 reference test signals")
- **Preconditions**: synthetic mono or dual-mono stereo 1 kHz sine tone,
  44.1 kHz, ≥10 s duration (long enough for BS.1770 integration/gating to
  settle), amplitude set so RMS = -20.00 dBFS (i.e. peak amplitude =
  10^(-20/20) × √2 ≈ 0.1414).
- **Steps**: Feed the buffer directly to `analysis.loudness.integrated_lufs()`.
- **Expected result**: measured integrated LUFS = -20.0 ± 0.1 LU. Rationale:
  K-weighting has ~0 dB gain in the vicinity of 1 kHz, so a 1 kHz tone's
  LUFS reading closely tracks its dBFS RMS level — this is the standard
  practical calibration check used to validate a BS.1770 implementation
  before trusting it on program material.
- **Notes**: recommend supplementing with the published EBU Tech 3341 /
  "EBU Loudness Test Set" (PLOUD) conformance signals if/when obtained —
  these carry publisher-verified target LUFS values and are a stronger
  calibration reference than a single hand-built tone. Flagged as a
  recommended acquisition, not a blocker.

### TC-011 — BS.1770 gating: quiet passage does not skew integrated loudness
- **Type**: audio-quality / edge case
- **Level**: module (`analysis/loudness.py`)
- **Covers**: AC2, requirements.md §6 "Silence/near-silence in long builds"
- **Preconditions**: synthetic stereo track, 4 minutes: first 60 s at a
  steady -13.0 LUFS-equivalent level (calibrated tone/pink noise), next
  180 s at -55 dBFS RMS (below the -70 LUFS absolute gate is not required
  here — this level should trip the *relative* gate, -10 LU below the
  ungated loudness, without approaching the absolute gate, to specifically
  exercise relative gating).
- **Steps**: Measure integrated LUFS over the full 4-minute buffer.
- **Expected result**: integrated LUFS is within 0.3 LU of the loud
  section's own LUFS value in isolation — i.e. the quiet 180 s does not
  pull the integrated figure down materially, because BS.1770 relative
  gating excludes it from the loudness calculation. Cross-check by also
  measuring the loud 60 s section alone and asserting the two figures are
  close.

### TC-012 — Silence-gated absolute floor: near-silent noise floor does not register as program content
- **Type**: audio-quality / edge case
- **Level**: module (`analysis/loudness.py`, `analysis/silence.py`)
- **Covers**: AC2, requirements.md §6
- **Preconditions**: synthetic stereo track with a 30 s section at -80
  dBFS RMS (below the -70 LUFS absolute gate) preceding a 90 s section at
  -13 LUFS.
- **Steps**: Measure integrated LUFS.
- **Expected result**: integrated LUFS reflects only the -13 LUFS section,
  within 0.3 LU; the -80 dBFS section is excluded by the absolute gate and
  contributes negligibly.

### TC-013 — Output lands within the [-14.5, -13.5] LUFS band (happy path)
- **Type**: audio-quality
- **Level**: pipeline
- **Covers**: AC2
- **Preconditions**: synthetic representative track that does *not*
  require dynamics-destroying limiting to reach -13.5 LUFS (moderate
  source DR, e.g. DR14 pre-master, source loudness around -20 LUFS).
- **Steps**: Run full pipeline; measure post-master integrated LUFS (per
  architecture §3, from the file actually re-read off disk at stage [9]).
- **Expected result**: post-master LUFS ∈ [-14.5, -13.5]. Report's
  rationale-text field for "why -13.5 wasn't reached" is absent/empty
  (since the target band was reached cleanly).

### TC-014 — Hard ceiling never exceeded, across varied source loudness
- **Type**: audio-quality
- **Level**: pipeline (parametrized)
- **Covers**: AC2
- **Preconditions**: parametrized set of synthetic sources at very
  different starting loudness: (a) very quiet source (-30 LUFS), (b)
  moderate (-18 LUFS), (c) already hot/loud (-9 LUFS, near-brickwalled).
- **Steps**: Run full pipeline on each; measure post-master LUFS.
- **Expected result**: for every case, post-master integrated LUFS ≤ -13.5
  LUFS, with zero exceptions (this is a hard ceiling, not a soft target —
  test should assert strictly, allowing no more than 0.01 LU of
  measurement-precision slack).

### TC-015 — Rationale text produced when the solver backs off below -14.5 LUFS
- **Type**: audio-quality / functional
- **Level**: pipeline
- **Covers**: AC2, AC8 (rationale logging)
- **Preconditions**: synthetic source deliberately constructed so that
  reaching -13.5 LUFS via broadband gain would force true peak over -1
  dBTP or DR under its floor — e.g. a track with an already-high crest
  factor spike (single very loud, very brief transient near 0 dBFS) sitting
  over a comparatively quiet body, at source DR just at DR8+3dB margin,
  such that any further gain to reach -13.5 would push DR below
  max(DR8, source_DR-3dB).
- **Steps**: Run full pipeline.
- **Expected result** (updated per architecture.md v4 §1, "Solver
  resolution for high-crest-factor sources", resolves DEF-001 residual):
  post-master LUFS is below -14.5, and for a fixture of this shape (quiet
  sustained body, brief near-ceiling transients, high source DR) may land
  below -16 LUFS as well — -16 is now a **soft, report-escalation
  threshold**, not a hard solver constraint. The -1 dBTP ceiling and the DR
  floor (`max(DR8, source_DR-3dB)`) remain the solver's only hard
  constraints and must both still be respected exactly.
  `UnresolvableMasteringConstraintError` must **not** be raised for this
  fixture (it resolves to a real, reported LUFS value, however low).
  `MasteringResult.below_documented_lufs_floor` must be `True` when the
  achieved LUFS lands below -16. The report contains explicit rationale
  text naming the DR floor as the specific binding constraint that
  prevented -13.5 (and, when applicable, -16) LUFS from being reached — per
  AC2's explicit allowance and architecture.md §1 point 5's escalated
  rationale requirement. Rationale text is present and non-generic.
  **Verified (defects.md DEF-001, 2026-08-01 python-developer pass)**:
  against the current fixture, the implementation lands at
  `achieved_lufs=-19.80`, `achieved_dr=16.0` (== `dr_required`, exactly at
  the floor), `achieved_true_peak_dbtp=-1.00`,
  `below_documented_lufs_floor=True`, rationale present and names the DR
  floor with correct numbers, no exception raised — matches this contract
  exactly.

### TC-016 — Below-floor-threshold boundary: solver lands below -14.5 but *above* -16 LUFS (the untested middle tier)
- **Type**: audio-quality / boundary
- **Level**: pipeline
- **Covers**: AC2
- **Preconditions** (revised per architecture.md v4 §1, resolves DEF-001
  residual — see "Revision history" below for why the original
  "clamp-at-16-or-raise" contract this TC tested no longer applies):
  synthetic source constructed, similarly to TC-015, so the solver cannot
  reach the [-14.5, -13.5] band without violating a hard constraint, but
  tuned (lower crest factor / less severe body-vs-transient gap than
  TC-015/TC-130's fixtures, which land around -19.5/-20.9) so the
  DR/peak-feasible optimum lands somewhere in the **untested middle
  tier**: below -14.5 (so AC2's baseline rationale requirement applies) but
  still above -16.0 (i.e. `below_documented_lufs_floor` should read
  `False`, unlike TC-015/TC-130/TC-131). **Flag**: landing inside this
  narrow (-16, -14.5) window is not guaranteed purely by construction —
  tune the fixture's crest factor empirically and confirm the achieved
  LUFS actually falls in this range before treating the fixture as fixed;
  if the achievable optimum keeps missing the window, that's a fixture-
  tuning task for QA, not evidence the contract is wrong.
- **Steps**: Run full pipeline.
- **Expected result**: `MasteringResult.below_documented_lufs_floor` is
  `True` **if and only if** `achieved_lufs < config.lufs_floor` (-16.0) —
  for this fixture, since achieved LUFS lands above -16, the flag must be
  `False`. Rationale text is still present (AC2 requires rationale text for
  any result below -14.5, not only below -16), but is the *baseline*
  "why -13.5 wasn't reached" tier, not the second, more prominent
  escalation tier architecture.md §1 point 5 reserves for the below-16
  case. `UnresolvableMasteringConstraintError` is **not** raised. The DR
  floor (`max(DR8, source_DR-3dB)`) and the -1.0 dBTP ceiling are both held
  exactly. **Note on what this TC no longer tests**: v1–v3 treated -16 as a
  hard clamp point ("post-master LUFS is clamped at exactly -16.0 LUFS...
  or the pipeline raises `UnresolvableMasteringConstraintError`"); per
  architecture.md v4 §1, -16 is no longer a clamp point at all — the
  solver simply continues selecting the highest DR/peak-feasible LUFS with
  no lower bound, and -16 only changes which rationale tier/flag value is
  reported. The genuinely-unresolvable-at-any-gain half of the old
  contract (where `UnresolvableMasteringConstraintError` **should** still
  fire) is now covered by **TC-131**, not this test case — cross-reference
  TC-131 for that branch.

### TC-017 — Silence-only input does not crash the loudness/solver path
- **Type**: edge case / robustness
- **Level**: pipeline
- **Covers**: AC2, robustness NFR
- **Preconditions**: synthetic stereo WAV, all-zero samples, 60 s, 44.1
  kHz/24-bit.
- **Steps**: Run full pipeline.
- **Expected result**: no unhandled exception/crash. `analysis.loudness`
  returns a well-defined result for "no gated blocks" (implementation-
  defined sentinel, e.g. `-inf` or `None` — the specific representation is
  an implementation choice not fixed by requirements.md, so this test
  should assert *whichever* sentinel the implementation defines is
  returned consistently and handled downstream, not that a specific numeric
  value must be used). The solver must not attempt to divide/normalize
  against a `-inf`/`NaN` loudness value; either the pipeline raises a
  typed `MasteringError`/`UnresolvableMasteringConstraintError` with a
  clear message ("input contains no measurable program content"), or it
  completes with an explicit no-op/pass-through and a report note. **Flag**:
  an entirely-silent full track is not explicitly addressed in
  requirements.md (only "near-silence in long builds" is) — this test
  exists purely for robustness (NFR: must not crash) rather than to
  enforce one specific documented behavior; if the two acceptable
  behaviors above diverge from what's implemented, that's a product
  decision for the BA to confirm, not a test failure by default.

---

## 3. AC3 — True peak ceiling (safety-critical, zero exceptions)

### TC-020 — Inter-sample peak exceeds sample-peak reading (naive metering blind spot)
- **Type**: audio-quality (calibration) — safety-critical
- **Level**: module (`analysis/true_peak.py`)
- **Covers**: AC3, architecture.md §2/§9 risk #3
- **Preconditions**: synthetic mono signal: `x[n] = A * cos(2π·(fs/4)·n/fs + π/4)`
  at fs = 44100 Hz — i.e. a quarter-Nyquist sinusoid with a 45° phase
  offset, chosen so its continuous-time peaks fall exactly between
  samples. With this construction, the **sample-peak** equals
  `A·cos(π/4) = A/√2` (3.01 dB below A), while the **true (reconstructed)
  peak** equals `A`. Set `A = 10^(-1.0/20) ≈ 0.891` so the true peak sits
  exactly at -1.0 dBTP while the sample-peak reads ≈ -4.01 dBFS.
- **Steps**: (1) Compute a naive sample-peak (max abs sample) on the raw
  buffer. (2) Compute the oversampled true peak via
  `analysis.true_peak.measure()` (≥4x oversampling per config).
- **Expected result**: naive sample-peak ≈ -4.0 dBFS (looks "safe" to a
  sample-only check). Oversampled true-peak measurement ≈ -1.0 dBTP ±0.1 dB
  — correctly revealing the inter-sample peak the naive check misses. This
  is the core proof that the true-peak module is doing real oversampled
  reconstruction, not just scanning sample values.

### TC-021 — True peak exceeding -1.0 dBTP is detected even though sample peak looks safe
- **Type**: audio-quality — safety-critical
- **Level**: module (`analysis/true_peak.py`)
- **Covers**: AC3, AC6
- **Preconditions**: same construction as TC-020, but with
  `A = 10^(-0.5/20) ≈ 0.944` — true peak ≈ -0.5 dBTP (violates the -1.0
  dBTP ceiling), sample-peak ≈ -3.51 dBFS (still looks comfortably safe to
  a naive check).
- **Steps**: Run pre-master true-peak analysis on this buffer as if it were
  a mastered output candidate.
- **Expected result**: true-peak measurement reports ≈ -0.5 dBTP, correctly
  flagged as exceeding the -1.0 dBTP ceiling, despite every individual
  sample value being well under -1.0 dBFS.

### TC-022 — Oversampling factor sensitivity: ≥4x catches what 2x misses
- **Type**: audio-quality — safety-critical
- **Level**: module (`analysis/true_peak.py`)
- **Covers**: AC3, architecture.md §2 (oversampling factor as config value)
- **Preconditions**: a signal with near-Nyquist content engineered so that
  a 2x-oversampled measurement under-reports the true peak relative to an
  8x-oversampled measurement (e.g. content close to fs/2 with peak
  positions requiring finer reconstruction resolution to resolve
  accurately — construct using the same quarter/near-Nyquist sinusoid
  approach as TC-020 but tuned closer to fs/2).
- **Steps**: Measure true peak at oversampling factors 1x (sample-peak),
  2x, 4x, and 8x (the configured default) on the same buffer.
- **Expected result**: measured true-peak value increases monotonically
  (or at least does not decrease) as oversampling factor increases from 1x
  toward 8x, and the 4x/8x readings converge closely (within ~0.05 dB of
  each other), while 1x/2x under-read relative to 4x/8x — demonstrating
  the implementation genuinely reconstructs at the configured factor
  rather than applying a fixed, frequency-independent "fudge factor." Use
  `config.true_peak_monotonicity_tolerance_db` (default 0.05 dB) as the
  documented slack on this specific cross-factor self-consistency
  assertion only — never as a relaxation of the actual -1.0 dBTP ceiling
  enforcement (see TC-023/TC-053), which must remain exact.

### TC-023 — Mastered output true peak: zero exceptions across a battery of sources
- **Type**: audio-quality — safety-critical, non-regression
- **Level**: pipeline (parametrized)
- **Covers**: AC3
- **Preconditions**: parametrized battery: (a) already very loud/hot
  source (near 0 dBFS sample peaks pre-master), (b) quiet source needing
  significant makeup gain, (c) source containing the TC-020/TC-021 style
  inter-sample-peak-prone content, (d) normal mid-loudness source.
- **Steps**: Run full pipeline on each; scan the entire mastered output
  buffer (re-read from disk per stage [9]) with the oversampled true-peak
  meter, not just a single global max — check for *any* window across the
  whole file exceeding the ceiling.
- **Expected result**: for every case, maximum true peak anywhere in the
  file ≤ -1.0 dBTP, with zero exceptions tolerated (allow ≤0.01 dB
  numerical slack for floating-point rounding only).

### TC-024 — Cross-validation against an independent true-peak meter
- **Type**: audio-quality (external validation) — flagged dependency
- **Level**: integration
- **Covers**: AC3, architecture.md §9 risk #3
- **Preconditions**: a small set of representative WAV files (synthetic +,
  once available, a real Suno export).
- **Steps**: Measure true peak with `analysis.true_peak.py` and,
  independently, with a trusted external true-peak meter (e.g. `ffmpeg`'s
  `ebur128` filter with true-peak reporting enabled, or another
  independently-validated BS.1770 Annex 2 implementation). Compare results
  on the same files.
- **Expected result**: readings agree within 0.1 dB. **Flag**: this is an
  explicit residual validation dependency called out in architecture.md
  §9 risk #3 ("safety-critical... needs cross-validation against an
  independent, known-good true-peak meter before the -1 dBTP guarantee can
  be trusted in production, not just unit-tested against synthetic
  signals"). This test case should be run before AC3 is treated as
  production-trustworthy, not skipped as merely a nice-to-have.
  **Updated per architecture.md v5**: this is also now the recommended
  real-world closure path for the tiered near-Nyquist ripple residual
  formalized in TC-025 below — if this cross-validation eventually shows
  the documented near-Nyquist under-read actually causes a real ceiling
  miss in practice, architecture.md §2 recommends a measured-HF-energy-
  conditioned enforcement margin as the next mitigation, not a further
  FIR tap-count increase (already verified infeasible within the 5-minute
  NFR budget).

### TC-025 — True-peak FIR filter: tiered passband-ripple envelope frequency sweep
- **Type**: audio-quality (calibration) — safety-critical
- **Level**: module (`analysis/true_peak.py`); implemented today as
  `tests/test_smoke_true_peak_fir.py`
- **Covers**: AC3, architecture.md §2 "True-peak passband ripple target —
  revised (v5, resolves DEF-002 second residual)" and §7's frequency-sweep
  testability note, defects.md DEF-002 (second residual, 2026-08-01
  qa-automation-engineer re-verification + 2026-08-01 software-architect
  architecture.md v5 resolution)
- **Background**: architecture.md v4 originally set an aspirational,
  unbounded verification target of <0.01 dB passband ripple "across a
  sweep of frequencies approaching Nyquist." Re-verification found the
  *implemented* filter (`numtaps=32×factor`, `beta=9.0`, cutoff fixed at
  exactly original Nyquist for image-safety — this cutoff placement is not
  negotiable; pushing it past Nyquist to flatten the passband was tried
  and rejected for reintroducing worse, 5-6 dB time-domain image-leakage
  errors) only holds <0.01 dB up to ~80% of original Nyquist, degrading
  beyond that. architecture.md v5 replaces the single flat target with a
  **tiered envelope matching the verified, already-implemented behavior**,
  so this frequency-sweep test is a meaningful regression guard rather
  than a permanently-red assertion against an unreachable target. No code
  change was required for this revision — only this test-spec entry, per
  DEF-002's "awaiting test-spec update (not awaiting implementation)"
  status.
- **Preconditions**: calibrated sine tones swept from ~0.5× to ~0.999× of
  the original (pre-oversampling) Nyquist frequency, at a fixed, known
  amplitude (e.g. amplitude set so the tone's true peak would read exactly
  0.0 dBTP if the filter were perfectly flat), at the configured default
  oversampling factor (8x). The 0.80×/0.01 dB tier is already implemented
  and passing in `tests/test_smoke_true_peak_fir.py`; this test case
  specifies the remaining four tiers as an extension of that existing file,
  not a new file.
- **Steps**: For each swept frequency `f` (expressed as a fraction of
  original Nyquist), measure two distinct quantities and check each
  against the tiered envelope independently — these are not
  interchangeable and must not be conflated:
  1. **Filter magnitude response** via `scipy.signal.freqz` on the FIR
     filter coefficients directly (the existing implemented approach) —
     ripple = |unity_gain_dB − filter_magnitude_dB(f)|.
  2. **End-to-end metering** via `measure_true_peak()` on the actual swept
     sine-tone buffer — deviation = |expected_true_peak_dBTP −
     measured_true_peak_dBTP|. Note the documented discrete-grid
     phase-alignment artifact on this leg (a real, bounded effect
     independent of filter ripple, already handled in the existing test
     file by choosing tone phase to avoid it, and separately bounded
     against its own closed-form prediction in its own test) — do not
     attribute phase-alignment-artifact deviation to filter ripple when
     interpreting a failure on this leg.
- **Expected result**: for both legs, treat the envelope as a **step
  function of frequency, not five independent boundary-point checks** —
  i.e. for every swept `f`, deviation(f) must be ≤ the envelope value for
  the *tightest* tier `f` falls into (bands are cumulative/nested, so a
  bump in the middle of a band must still satisfy that band's bound, not
  just the bound at the band's own edge frequency):

  | Fraction of original Nyquist | Ripple/deviation bound |
  |---|---|
  | f ≤ 0.80× | ≤ 0.01 dB (verified-flat region; already implemented/passing) |
  | 0.80× < f ≤ 0.85× | ≤ 0.05 dB (measured ~0.02 dB) |
  | 0.85× < f ≤ 0.90× | ≤ 0.5 dB (measured ~0.4 dB) |
  | 0.90× < f ≤ 0.95× | ≤ 2.5 dB (measured ~1.5-2 dB) |
  | 0.95× < f ≤ 0.999× | ≤ 6.5 dB (measured ~5.9 dB) |

  Additionally: (a) **assert the sign of the deviation is always
  attenuation (under-read), never gain** — i.e. `filter_magnitude_dB(f) ≤
  unity_gain_dB` for every swept `f` — since architecture.md's entire
  composite-peak safety argument for accepting this residual depends on
  the error direction being under-read, not over-read; this reuses/extends
  the existing `test_fir_filter_image_rejection_beyond_nyquist` attenuation-
  sign check but should be asserted explicitly across the swept range in
  this test too, not only just above Nyquist. (b) This tiered envelope is
  a **distinct property from `config.true_peak_monotonicity_tolerance_db`**
  (default 0.05 dB, which happens to numerically coincide with this
  envelope's 0.85× tier bound — do not conflate the two): the monotonicity
  tolerance governs only TC-022-style cross-oversampling-factor
  self-consistency assertions at a single frequency, a different, narrower
  question than this test's absolute passband-flatness-vs-frequency
  question at a single (8x, default) factor. (c) Per architecture.md §6
  (v5), this tiered envelope is a **test-spec constant only** — it does not
  need, and should not be added as, a `config.py` runtime value; it governs
  `tests/test_smoke_true_peak_fir.py` assertions only, never a pipeline
  decision.
- **Flag**: this residual (near-Nyquist under-read, bounded per the
  composite-peak argument in architecture.md §2/§9 risk #3) is accepted as
  a documented, safety-relevant-direction-but-narrow-in-practice gap, not
  eliminated — TC-024's external cross-validation remains the real-world
  closure path if it turns out to matter for actual tracks in this genre.

---

## 4. AC4 — Dynamic range preservation (TT DR-meter scale)

> Construction note (applies to TC-030–TC-034): the TT DR-meter spec
> (3-second RMS blocks, exclude loudest 20%, ratio of remaining-block RMS
> to the 2nd-highest true peak) can be approximated with a simple two-level
> synthetic signal for deterministic, calculable boundary testing: a
> continuous "body" tone at amplitude `A` filling the great majority of the
> track (so per-block RMS ≈ `A` under the DR-meter's RMS convention), plus
> a handful of brief (few-sample) transients at amplitude `P > A` inserted
> sparingly so they don't materially affect block RMS but do establish the
> 2nd-highest sample peak. Under this construction, `DR ≈ 20·log10(P/A)`.
> **This is a restated approximation of the published algorithm for test
> fixture design, not a substitute for validating `dynamic_range.py`
> against the actual published Pleasurize Music Foundation spec and
> independently-verified reference tracks** — flagged per architecture.md
> §9 risk #2. Treat the exact numeric fixtures below as a starting point to
> be confirmed against the real implementation/reference tracks, not as
> unquestionable ground truth.

### TC-030 — DR8-boundary construction: exactly at the floor
- **Type**: audio-quality / boundary
- **Level**: module (`analysis/dynamic_range.py`)
- **Covers**: AC4
- **Preconditions**: synthetic stereo track, body amplitude `A = 0.1`
  (-20 dBFS), sparse transient peaks at `P = A·10^(8/20) ≈ 0.2512`
  (targeting DR ≈ 8.0 by the approximation above), 5 minutes duration.
- **Steps**: Measure DR via `analysis.dynamic_range.measure()`.
- **Expected result**: measured DR = 8 ± the module's own documented
  rounding rule (e.g. floor-to-integer per TT convention). Use this fixture
  to test the pipeline's boundary logic: a source already at DR8 must not
  be pushed *below* DR8 by any downstream mastering stage — assert
  post-master DR ≥ 8 for this specific fixture once run through the full
  pipeline.

### TC-031 — DR14 source: 3 dB-reduction constraint binds (must land ≥ DR11)
- **Type**: audio-quality
- **Level**: pipeline
- **Covers**: AC4 (uses the requirements.md §2 worked example directly)
- **Preconditions**: synthetic source constructed to measure DR14 pre-master
  (body amplitude `A`, transient `P = A·10^(14/20)`).
- **Steps**: Run full pipeline; measure post-master DR.
- **Expected result**: post-master DR ≥ 11 (since max(DR8, 14-3) = 11 is
  the binding, stricter constraint here). Report shows both the source DR
  (14) and the post-master DR side by side.

### TC-032 — DR9 source: DR8 floor binds (must land ≥ DR8, not DR6)
- **Type**: audio-quality
- **Level**: pipeline
- **Covers**: AC4 (uses the requirements.md §2 worked example directly)
- **Preconditions**: synthetic source constructed to measure DR9 pre-master.
- **Steps**: Run full pipeline; measure post-master DR.
- **Expected result**: post-master DR ≥ 8 (since max(DR8, 9-3=6) = 8 is the
  binding constraint — the naive "3 dB max reduction" reading of DR6 would
  be wrong here; the DR8 floor must win). This test specifically catches
  an implementation that only checks the 3 dB-reduction rule and forgets
  the DR8 floor is the stricter one in this case.

### TC-033 — Solver backs off loudness to protect DR (three-way interaction)
- **Type**: audio-quality
- **Level**: pipeline
- **Covers**: AC2, AC3, AC4 (solver interaction)
- **Preconditions**: a source at the DR8 boundary (as in TC-030) combined
  with a starting loudness far enough below -13.5 LUFS that reaching the
  ceiling via broadband gain plus limiting would erode DR below 8.
- **Steps**: Run full pipeline.
- **Expected result**: final DR ≥ 8 is preserved even at the cost of not
  reaching -13.5 LUFS; report shows the resulting LUFS (< -13.5, possibly
  < -14.5) with rationale text attributing the shortfall to DR protection
  specifically (not a generic message — should reference DR).

### TC-034 — AC4 baseline correctness: comparison must use the *original* pre-processing DR, not stage-6-entry DR
- **Type**: audio-quality — correctness/regression guard
- **Level**: pipeline (with stage-level instrumentation)
- **Covers**: AC4, architecture.md §1 note + §9 risk #7 (explicitly flagged
  as "an easy place to introduce a subtle correctness bug")
- **Preconditions**: synthetic source where the corrective EQ stage ([4])
  is guaranteed to measurably shift DR by a detectable margin (≥0.5 dB) —
  e.g. a source that triggers a maximal (3 dB) muddiness-correction EQ cut
  in a way that changes the block-RMS profile enough to shift the DR-meter
  reading, engineered so that: DR measured at stage [2] (true original) =
  `D0`; DR measured at stage-6-entry (i.e. immediately after EQ + stereo
  correction, before the loudness/limiting solver runs) = `D1`, with
  `D1 ≠ D0` by at least 0.5 dB.
- **Steps**: (1) Run the pipeline with instrumentation capturing DR at
  stage [2] (`D0`), immediately before stage [6] (`D1`), and the DR floor
  the solver actually enforces during stage [6] (`D_floor_used`). (2)
  Independently compute what the floor *would* be if the solver had
  (incorrectly) used `D1` instead of `D0`: `max(DR8, D1 - 3dB)` vs. the
  correct `max(DR8, D0 - 3dB)`.
- **Expected result**: `D_floor_used` equals `max(DR8, D0 - 3dB)` (the
  floor computed from the *true original* source DR), not
  `max(DR8, D1 - 3dB)` (the stage-6-entry DR). Construct `D0` and `D1` far
  enough apart that these two candidate floors differ by a value larger
  than measurement tolerance (e.g. ≥0.5 dB), so this test would reliably
  fail against an implementation that made the flagged mistake. Also assert
  the report's displayed "source DR" field for AC4's before/after display
  equals `D0`, not `D1`.

### TC-035 — Report shows both source and output DR values explicitly
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC4 ("report must show both values so a human can verify")
- **Preconditions**: any of the fixtures above.
- **Steps**: Inspect the rendered report.
- **Expected result**: report contains clearly labeled source-DR and
  output-DR values (not just a pass/fail flag), so a human reviewer can
  verify the track wasn't over-limited without re-running analysis.

---

## 5. AC5 — Mono compatibility (stereo phase correlation)

> Construction note: for stereo signals built from a single underlying
> mono waveform split into mid/side components `L = M + S`, `R = M - S`,
> the exact phase-correlation coefficient is `ρ = (E[M²] - E[S²]) /
> (E[M²] + E[S²])`, where `E[M²]`/`E[S²]` are the mid/side signal energies.
> This gives closed-form, calculable fixtures for exact correlation targets
> — solve for the side/mid amplitude ratio `r` via `E[S²]/E[M²] = r²`,
> and `r² = (1-ρ)/(1+ρ)`.

### TC-040 — Fully out-of-phase stereo pair reads correlation = -1.0
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/stereo_phase.py`)
- **Covers**: AC5
- **Preconditions**: synthetic stereo signal, `L(t) = sin(2π·440·t)`,
  `R(t) = -L(t)` (exact phase inversion), 10 s, 44.1 kHz.
- **Steps**: Compute phase correlation over the full buffer.
- **Expected result**: correlation = -1.0 ± 0.01 (this is `M=0`, i.e. pure
  side content — the exact-inversion case of the closed-form above).

### TC-041 — Stereo-widened element with correlation exactly at the -0.3 boundary, requiring correction to ≥0.0
- **Type**: audio-quality
- **Level**: module (`analysis/stereo_phase.py`, `mastering/stereo_correct.py`)
- **Covers**: AC5
- **Preconditions**: synthetic stereo region ≥750 ms long (so it survives
  the 2-consecutive-window debounce), constructed with mid amplitude
  `A_mid = 0.3` and side amplitude `A_side = A_mid · r`, where
  `r = sqrt((1-(-0.3))/(1+(-0.3))) = sqrt(1.3/0.7) ≈ 1.363`, i.e.
  `A_side ≈ 0.409`. This gives `ρ ≈ -0.3` and a side/mid energy ratio of
  `r² ≈ 1.857 > 0.6` (so it also passes the stereo-widened-element
  classification threshold).
- **Steps**: (1) Confirm pre-correction classification: window(s) flagged
  as stereo-widened (side/mid ratio > 0.6, sustained ≥2 consecutive
  windows). (2) Confirm pre-correction correlation ≈ -0.3 (below the 0.0
  floor). (3) Run stage [5] stereo correction. (4) Re-measure correlation
  post-correction.
- **Expected result**: post-correction correlation ≥ 0.0 (corrected
  region brought back to at least the floor). Correction is the *minimum*
  side-channel scaling needed — verify the corrected region's side energy
  is reduced by no more than necessary to reach ρ=0.0 (not fully summed to
  mono), i.e. side amplitude after correction should be close to
  `A_mid` (the ρ=0.0 boundary case, `r=1`), not near-zero.

### TC-042 — Stereo-widened element within [0.0, +0.3) is classified but not force-corrected
- **Type**: audio-quality / boundary
- **Level**: module (`analysis/stereo_phase.py`, `mastering/stereo_correct.py`)
- **Covers**: AC5
- **Preconditions**: same construction style as TC-041 but with `ρ ≈ +0.15`
  (`r = sqrt(0.85/1.15) ≈ 0.859`, side/mid ratio `r² ≈ 0.739 > 0.6`, so
  still classified as a stereo-widened element per the 0.6 threshold, but
  its correlation already sits above the hard 0.0 floor).
- **Steps**: Run detection then stage [5] correction.
- **Expected result**: element is classified as stereo-widened (side/mid
  ratio check passes), but since its correlation (+0.15) is already ≥ 0.0,
  no mandatory narrowing is applied — per AC5's wording, only elements
  "dipping below 0.0" must be narrowed; the +0.3 figure is a target, not an
  enforced floor for correction. Confirm the audio is unchanged in this
  region (or, if the implementation does choose to nudge toward +0.3
  anyway, confirm that behavior is explicitly logged as a deliberate
  design choice — this test exists to make the intended boundary behavior
  explicit and catch an accidental over-correction of compliant material).

### TC-043 — Single-transient false positive is NOT classified as a sustained element (debounce)
- **Type**: audio-quality / edge case
- **Level**: module (`analysis/stereo_phase.py`)
- **Covers**: AC5, architecture.md §8 #2 (debounce design)
- **Preconditions**: synthetic stereo signal, mostly narrow/mono-compatible
  content, with a single hard-panned transient (e.g. one drum hit,
  ~200 ms — spans only one 500 ms analysis window when aligned to the hop
  grid) with side/mid ratio > 0.6 within that single window only, and
  normal (<0.6 ratio) content immediately before/after.
- **Steps**: Run stereo-widened-element detection.
- **Expected result**: the single window is individually flagged as
  exceeding the 0.6 side/mid ratio, but since fewer than 2 consecutive
  windows meet the threshold, it does **not** qualify as a sustained
  stereo-widened "element" and is excluded from stage [5] correction and
  from the +0.3-target reporting.

### TC-044 — Exactly 2 consecutive windows qualifies as a sustained element (debounce boundary)
- **Type**: audio-quality / boundary
- **Level**: module (`analysis/stereo_phase.py`)
- **Covers**: AC5, architecture.md §8 #2
- **Preconditions**: synthetic stereo signal with side/mid ratio > 0.6
  sustained for exactly 750 ms (2 consecutive 500 ms windows at 250 ms hop
  — the minimum debounce-qualifying duration), flanked by normal content.
- **Steps**: Run detection.
- **Expected result**: the region is classified as a sustained
  stereo-widened element (unlike TC-043) and is subject to the +0.3 target
  / <0.0 correction logic.

### TC-045 — Mono input skips stereo checks without false-flagging
- **Type**: functional / edge case
- **Level**: pipeline
- **Covers**: AC5, requirements.md §6 "Mono source"
- **Preconditions**: synthetic mono WAV, 44.1 kHz/24-bit, 3 minutes.
- **Steps**: Run pre-master analysis and full pipeline.
- **Expected result**: stereo-width/mono-compatibility check is skipped or
  trivially reports full compatibility (e.g. correlation = 1.0 / N/A); no
  phase-cancellation flag is raised; no stereo-widened-element correction
  is attempted; report explicitly states the file was mono and why
  stereo-specific checks were not applicable (per requirements.md wording).
  No exception raised anywhere in the stereo-phase or stereo-correct
  modules from an assumed second channel.

### TC-046 — Crossfade boundary does not introduce audible zipper/pumping artifacts (numeric proxy)
- **Type**: audio-quality — numeric proxy for a listening-QA concern
- **Level**: module (`mastering/stereo_correct.py`)
- **Covers**: AC5, architecture.md §9 risk #5 (explicitly flagged as
  needing listening-based QA, not just numeric checks)
- **Preconditions**: synthetic stereo track with a single stereo-widened
  region (per TC-041's construction, correlation ≈ -0.3, ≥750 ms) embedded
  within otherwise normal-width, continuous-amplitude material, so the
  region's entry/exit boundaries are the only place gain changes.
- **Steps**: Run stage [5] correction. Examine the sample-by-sample side-
  channel gain trajectory across each of the two 50 ms raised-cosine
  crossfade boundaries (region entry and exit).
- **Expected result**: (a) the gain trajectory across each boundary is
  smooth and monotonic (raised-cosine shape, no discontinuity/step), (b)
  the maximum sample-to-sample delta within the crossfade window is no
  larger than what a raised-cosine ramp of that duration/amplitude change
  would produce (i.e., materially smaller than an abrupt hard-cut gain
  change of the same total magnitude would produce — compute and compare
  both explicitly), (c) no new inter-sample peaks or clipping are
  introduced at the boundary as a side effect of the crossfade. **Flag**:
  per architecture.md §9 risk #5, this numeric proxy does not replace
  listening-based QA of the correction — recommend a manual listening pass
  on real program material (pads/wide synths) before treating this
  correction as production-ready, in addition to this automatable check.

### TC-047 — Adjacent/close stereo-widened regions do not cause colliding crossfades
- **Type**: audio-quality / edge case
- **Level**- module (`mastering/stereo_correct.py`)
- **Covers**: AC5, architecture.md §9 risk #5
- **Preconditions**: synthetic stereo track with two separate
  stereo-widened, below-floor regions separated by less than 100 ms (i.e.
  less than the combined 50+50 ms crossfade width of the two regions'
  boundaries) — a case the architecture doesn't explicitly resolve.
- **Steps**: Run stage [5] correction.
- **Expected result**: no crash; both regions still end with correlation
  ≥ 0.0; no unintended full-track narrowing artifact from overlapping
  crossfade windows. **Flag**: exact expected crossfade-shape behavior in
  this overlap case is not specified in architecture.md — this test
  documents a genuine residual design gap (not a requirements gap) and
  should be confirmed with the architect/developer once implemented, in
  addition to a listening pass, rather than assuming one specific
  resolution is "correct" without confirmation.

---

## 6. AC6 — Clipping/distortion detection and non-regression

### TC-050 — Full-scale square wave: all clipped samples counted
- **Type**: audio-quality (calibration)
- **Level**: module (`analysis/clipping.py`)
- **Covers**: AC6
- **Preconditions**: synthetic mono/stereo full-scale square wave (samples
  alternating exactly at +1.0/-1.0, i.e. digital full-scale), 1 s, 44.1 kHz
  — 44100 samples, all at the ceiling.
- **Steps**: Run clipping detection.
- **Expected result**: reported clipped-sample count matches the known
  count (all samples at/above the configured clip threshold, e.g. ≥
  -0.1 dBFS or exact 0 dBFS depending on config's clip-detection
  threshold), with severity flagged as high/sustained (not a single
  isolated sample).

### TC-051 — Already-clipped source is detected and reported without erroring
- **Type**: edge case / functional
- **Level**: pipeline
- **Covers**: AC6, requirements.md §6 "Already-clipped input"
- **Preconditions**: synthetic stereo track, otherwise normal, with a 2 s
  region of hard-clipped (flat-topped at ±1.0) samples inserted.
- **Steps**: Run pre-master analysis, then full pipeline.
- **Expected result**: pre-master report shows a non-zero clipped-sample
  count/severity for the affected region; pipeline completes without
  error; mastering proceeds (per resolved Open Question #4, detect-and-
  report only, no repair attempted) — the clipped region's waveform shape
  is not "fixed"/interpolated, only gain-staged like the rest of the track.

### TC-052 — Mastering never amplifies existing clipping beyond the -1 dBTP ceiling
- **Type**: audio-quality — non-regression, safety-critical
- **Level**: pipeline
- **Covers**: AC6
- **Preconditions**: same fixture as TC-051.
- **Steps**: Run full pipeline; measure true peak specifically within and
  immediately around the previously-clipped region in the mastered output.
- **Expected result**: no new inter-sample overs or sample-peak values are
  introduced in that region beyond -1.0 dBTP; the clipped region does not
  read as *more* clipped (more samples at ceiling, longer duration at
  ceiling) than the source.

### TC-053 — Mastering does not introduce new clipping on a "just under ceiling" quiet source
- **Type**: audio-quality — non-regression
- **Level**: pipeline
- **Covers**: AC3, AC6
- **Preconditions**: synthetic source with pre-existing peaks sitting just
  under -1 dBFS (e.g. -0.8 dBFS sample peaks) but low overall loudness
  (e.g. -25 LUFS), such that the solver wants to apply significant gain to
  reach the loudness target.
- **Steps**: Run full pipeline; measure post-master true peak.
- **Expected result**: post-master true peak ≤ -1.0 dBTP everywhere — the
  limiter must catch and control these near-ceiling peaks even though they
  weren't clipping in the source, demonstrating gain-staging correctly
  accounts for true peak, not just target LUFS.

### TC-054 — Near-silent noise floor does not false-positive as clipping
- **Type**: edge case
- **Level**: module (`analysis/clipping.py`)
- **Covers**: AC6, requirements.md §6 "Silence/near-silence"
- **Preconditions**: synthetic near-silent region, low-level dithered
  noise at approximately -90 dBFS RMS, 30 s.
- **Steps**: Run clipping detection on this region alone.
- **Expected result**: reported clipped-sample count = 0.

---

## 7. AC7 — Frequency balance detection and correction

Reference curve (config default, `reference/progressive_house_124bpm.json`,
per architecture §8 #1): 20–120 Hz = -1.5 dB, 200–500 Hz = -3.0 dB,
2–5 kHz = -4.0 dB, all relative to the 500 Hz–2 kHz band average (0 dB
baseline). Trigger thresholds: thin low-end < -5.5 dB relative; muddiness
> 0.0 dB relative; harshness > -1.0 dB relative. EQ move cap: ≤3 dB/move,
zero-phase (`sosfiltfilt`).

### TC-060 — Thin low-end trigger and corrective boost
- **Type**: audio-quality
- **Level**: module (`analysis/frequency_balance.py`, `mastering/eq.py`)
- **Covers**: AC7
- **Preconditions**: synthetic broadband (e.g. shaped pink noise or
  multi-tone) track with 20–120 Hz band energy set to -6.0 dB relative to
  the 500 Hz–2 kHz baseline (i.e. below the -5.5 dB trigger).
- **Steps**: Run pre-master frequency-balance analysis; run stage [4]
  corrective EQ; re-measure post-EQ frequency balance.
- **Expected result**: pre-master report flags "thin low-end" = True with
  measured relative level ≈ -6.0 dB. A corrective low-end boost is applied,
  capped at ≤3 dB. Post-EQ measured low-end relative level moves toward
  the reference (i.e., closer to -1.5 dB, ideally landing at approximately
  -3.0 dB after a 3 dB boost from -6.0 dB) but never overshoots by more
  than the 3 dB cap in a single move.

### TC-061 — Muddiness trigger and corrective cut
- **Type**: audio-quality
- **Level**: module (`analysis/frequency_balance.py`, `mastering/eq.py`)
- **Covers**: AC7
- **Preconditions**: synthetic track with 200–500 Hz band energy at +1.0 dB
  relative (above the 0.0 dB trigger).
- **Steps**: Run analysis, then corrective EQ, then re-analysis.
- **Expected result**: pre-master flags muddiness = True at ≈ +1.0 dB
  relative; a corrective cut is applied (≤3 dB, sufficient here since only
  1 dB of correction is needed); post-EQ measured level moves to
  approximately -3.0 dB (the reference value) or at least back under the
  0.0 dB trigger threshold.

### TC-062 — Harshness trigger and corrective cut
- **Type**: audio-quality
- **Level**: module (`analysis/frequency_balance.py`, `mastering/eq.py`)
- **Covers**: AC7
- **Preconditions**: synthetic track with 2–5 kHz band energy at 0.0 dB
  relative (above the -1.0 dB trigger).
- **Steps**: Run analysis, corrective EQ, re-analysis.
- **Expected result**: pre-master flags harshness = True at 0.0 dB
  relative; corrective cut applied (≤3 dB); post-EQ level moves toward
  -4.0 dB reference / at least back under the -1.0 dB trigger.

### TC-063 — EQ move cap holds even when full correction would require more than 3 dB
- **Type**: audio-quality / boundary
- **Level**: module (`mastering/eq.py`)
- **Covers**: AC7 ("corrective EQ... capped at ≤3 dB per move")
- **Preconditions**: synthetic track with 200–500 Hz band energy at +8.0 dB
  relative (far beyond the 0.0 dB trigger — would need an 8 dB cut for a
  full correction to the 0 dB reference/-3.0dB target).
- **Steps**: Run corrective EQ.
- **Expected result**: the single corrective move applied does not exceed
  3 dB of cut. Post-EQ muddiness measurement still shows a residual flag
  (still above 0 dB relative, e.g. ≈ +5.0 dB) — report must show this
  residual flag honestly, not claim full correction. Assert the report
  does not overstate the correction (logged gain value matches actual
  applied filter gain, ≤3 dB).

### TC-064 — No spurious correction when signal already matches the reference curve
- **Type**: audio-quality / negative test
- **Level**: pipeline
- **Covers**: AC7
- **Preconditions**: synthetic track whose three band-energies sit exactly
  at the reference curve values (-1.5/-3.0/-4.0 dB relative) within
  measurement noise.
- **Steps**: Run pre-master analysis, stage [4], post-analysis.
- **Expected result**: no flags triggered; corrective-action log for EQ is
  empty; pre- and post-EQ frequency measurements are equal within
  measurement tolerance (e.g. ±0.1 dB, accounting for floating-point/FFT
  windowing noise).

### TC-065 — Logged EQ action matches actually-applied gain and band
- **Type**: functional / audio-quality — traceability
- **Level**: pipeline
- **Covers**: AC7, AC8
- **Preconditions**: any of TC-060/061/062's fixtures.
- **Steps**: Extract the report's corrective-action log entry for the
  triggered EQ move (band, gain in dB, reason). Independently recompute
  the actual band-energy delta between pre-EQ and post-EQ buffers for the
  same band.
- **Expected result**: the logged gain value matches the independently
  measured applied gain within ±0.2 dB, and the logged band matches the
  band the measured delta actually occurred in. This directly checks that
  the report is not just describing an intended correction but the one
  that was actually applied.

### TC-066 — Zero-phase EQ: no group-delay/asymmetric-ringing artifact
- **Type**: audio-quality
- **Level**: module (`mastering/eq.py`)
- **Covers**: AC7 (architecture's `sosfiltfilt` design choice, made
  specifically to avoid harming AC5 mono-compatibility)
- **Preconditions**: synthetic click/impulse test signal (single-sample
  or very short impulse) processed through the corrective EQ filter chain
  configured to apply a representative correction (e.g. a muddiness cut).
- **Steps**: Locate the impulse's peak position in the input and in the
  filtered output. Examine ringing symmetry around that position.
- **Expected result**: the impulse's peak position in the output is
  unchanged from the input (zero net group delay) and any filter ringing
  is symmetric around that position (both before and after), consistent
  with zero-phase (`sosfiltfilt`) filtering — as opposed to a causal
  single-pass filter, which would show delay and ringing only *after* the
  impulse.

### TC-067 — Genre reference curve is a calibration default, not producer-verified — flagged
- **Type**: audio-quality — flagged validation dependency
- **Level**: N/A (documentation/process test)
- **Covers**: AC7, architecture.md §8 #1 / §9 risk #1
- **Preconditions**: N/A.
- **Steps**: N/A — this is a process check, not a code test: confirm
  whether `scripts/build_reference_curve.py` has been run against
  producer-nominated reference tracks for this genre before frequency-
  balance flags/corrections are treated as final/production-trustworthy.
- **Expected result**: recorded as an open validation item. **Flag**: the
  -1.5/-3.0/-4.0 dB default curve is explicitly a "reasoned placeholder,
  not producer-verified" per architecture.md §9 risk #1. Test cases
  TC-060–066 are valid and automatable against the *current default
  curve*, but their pass/fail thresholds should be re-derived and re-run
  once a producer-calibrated curve is in place — do not treat the current
  numeric thresholds as permanently fixed ground truth.

### TC-068 — Near-silent passages do not skew overall frequency-balance measurement
- **Type**: edge case
- **Level**: module (`analysis/frequency_balance.py`)
- **Covers**: AC7, requirements.md §6 "Silence/near-silence"
- **Preconditions**: synthetic track: 5 minutes of near-silent (-80 dBFS)
  low-level noise, followed by 10 s of a well-balanced (reference-curve-
  matching) loud section.
- **Steps**: Run frequency-balance analysis over the whole track.
- **Expected result**: overall measured balance reflects the 10 s loud,
  well-balanced section (no flags triggered), not skewed/diluted or made
  meaningless by averaging over the much longer near-silent portion —
  confirm the analysis uses energy-weighted averaging (or the shared
  `analysis/silence.py` gating utility) so near-zero-energy content does
  not distort the result.

---

## 8. AC8 — Before/after report

### TC-070 — Report covers all six criteria, before and after, side by side
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC8
- **Preconditions**: any representative full-pipeline run.
- **Steps**: Inspect the rendered report.
- **Expected result**: report contains, for each of loudness, true peak,
  DR, frequency balance, stereo/mono compatibility, and clipping/
  distortion — a clearly labeled pre-master and post-master value,
  presented so they can be compared without cross-referencing another
  document or re-running analysis.

### TC-071 — Corrective-action log completeness
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC8
- **Preconditions**: a source engineered to trigger all of: EQ correction,
  stereo narrowing, non-trivial gain/limiting, resample (non-standard
  source rate), and a below-target-band loudness rationale (i.e. combine
  elements of TC-015/TC-041/TC-060/etc. into one run, or run several
  targeted fixtures and check the union of logged fields across them).
- **Steps**: Inspect the report's corrective-action log.
- **Expected result**: the log includes, where applicable: EQ moves
  (band, gain, reason), stereo-narrowing correction windows (start/end
  time, amount of side-channel scaling applied), gain/limiting amount
  applied by the loudness solver, whether resampling occurred (and to what
  rate), the dither seed used, and — specifically when landed loudness is
  below -14.5 LUFS — the rationale text. Every field that architecture.md
  §1 (stage [10]) specifies as required is present when its triggering
  condition occurred.

### TC-072 — Rationale text absent when target band is reached cleanly
- **Type**: functional / negative test
- **Level**: pipeline
- **Covers**: AC8, AC2
- **Preconditions**: TC-013's happy-path fixture.
- **Steps**: Inspect report.
- **Expected result**: no rationale text is present/populated for "why
  -13.5 wasn't reached," since it was reached (or the field is explicitly
  empty/null, not a stale/leftover message from another case).

### TC-073 — Source-file identity/hash record present and correct
- **Type**: functional — traceability
- **Level**: pipeline
- **Covers**: AC8, AC10, AC11
- **Preconditions**: any run.
- **Steps**: Independently compute SHA-256 of the input file before
  running the pipeline. Run the pipeline. Extract the report's recorded
  input-file hash.
- **Expected result**: recorded hash matches the independently-computed
  hash exactly. Report also records the output WAV's own hash, tool
  version, and the config/settings used for the run (per architecture §4).

### TC-074 — Report is human-readable without re-running analysis
- **Type**: functional (manual/checklist)
- **Level**: pipeline
- **Covers**: AC8
- **Preconditions**: rendered markdown (or equivalent human-readable)
  report from any run.
- **Steps**: Manual review: can a producer unfamiliar with the tool's
  internals identify, for each of the six criteria, what the before/after
  values were and what (if anything) was changed and why, using only the
  rendered report?
- **Expected result**: yes — labels are clear, units are stated (LUFS,
  dBTP, DR, dB relative, correlation coefficient), and corrective actions
  are described in plain terms, not just raw numbers/internal field names.

---

## 9. AC9 — Output file validity

### TC-080 — Output is valid 24-bit PCM WAV
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC9
- **Preconditions**: any supported input (44.1/48 kHz, 16/24-bit/float).
- **Steps**: Inspect the output WAV's format via `soundfile`/libsndfile
  format introspection.
- **Expected result**: output subtype is 24-bit PCM exactly, container is
  a valid WAV/RIFF file openable without warnings by a standard reader.

### TC-081 — Output sample rate matches source (44.1 kHz and 48 kHz cases)
- **Type**: functional (parametrized)
- **Level**: pipeline
- **Covers**: AC9
- **Preconditions**: (a) source at 44.1 kHz, (b) source at 48 kHz.
- **Steps**: Run pipeline; inspect output sample rate.
- **Expected result**: (a) output = 44100 Hz exactly; (b) output = 48000 Hz
  exactly — no unnecessary resample for already-standard rates.

### TC-082 — Non-standard source rate defaults to 44.1 kHz, logged
- **Type**: functional / edge case (parametrized)
- **Level**: pipeline
- **Covers**: AC9, requirements.md §6
- **Preconditions**: parametrized non-standard rates: 22050 Hz, 32000 Hz,
  88200 Hz, 96000 Hz.
- **Steps**: Run pipeline; inspect output sample rate and the report's
  logged resample step.
- **Expected result**: output sample rate = 44100 Hz for every case; the
  report explicitly records that a resample occurred (source rate →
  44100 Hz), consistent with AC8's requirement to log this step, not a
  silent resample.

### TC-083 — Standard BWF/metadata chunk is preserved byte-for-byte
- **Type**: functional
- **Level**: module (`io/wav_chunks.py`) + pipeline
- **Covers**: AC9
- **Preconditions**: synthetic WAV constructed with a standard `bext`
  (Broadcast Wave) chunk and a `LIST`/`INFO` chunk containing known,
  fixed byte content.
- **Steps**: Run full pipeline; extract the corresponding chunks from the
  output WAV.
- **Expected result**: `bext` and `LIST`/`INFO` chunk contents in the
  output are byte-identical to the source's (not regenerated/reformatted),
  confirming pass-through preservation rather than authoring new metadata
  (out of scope per requirements §5).

### TC-084 — Unrecognized/nonstandard chunk passes through with a warning, not an abort
- **Type**: edge case — robustness
- **Level**: module (`io/wav_chunks.py`) + pipeline
- **Covers**: AC9, architecture.md §9 risk #4 (explicitly flagged, no real
  Suno export inspected yet)
- **Preconditions**: synthetic WAV containing a fabricated, non-standard
  FourCC chunk (e.g. a made-up `"XTRA"` chunk with arbitrary payload) in
  addition to standard `fmt `/`data` chunks.
- **Steps**: Run full pipeline.
- **Expected result**: pipeline completes successfully (does not abort);
  a warning is logged noting the unrecognized chunk was encountered;
  either the chunk is preserved through to the output, or, if it genuinely
  cannot be preserved, the warning explicitly says so — but in no case
  does an unrecognized chunk cause a hard failure or crash. **Flag**: per
  architecture §9 risk #4, this should be re-validated against a real
  Suno export once one is available — the synthetic construction here is
  a reasonable stand-in but not a substitute for testing against actual
  Suno export quirks.

### TC-085 — Malformed chunk structures fail gracefully, not with a raw crash
- **Type**: edge case — robustness (parametrized)
- **Level**: module (`io/wav_chunks.py`) + pipeline
- **Covers**: AC9, robustness NFR
- **Preconditions**: parametrized malformed variants: (a) a chunk whose
  declared size exceeds the actual remaining file bytes (truncated data),
  (b) an odd-length chunk missing its required RIFF pad byte, (c) a chunk
  with declared size 0.
- **Steps**: Attempt to run the pipeline on each variant.
- **Expected result**: for each variant, the pipeline either (i) handles
  it gracefully — logs a warning and proceeds, treating the malformed
  chunk as unpreservable rather than fatal — or (ii) raises a typed
  `InvalidWavError` with a clear message; in no case does it crash with an
  unhandled low-level exception (`struct.error`, `IndexError`, etc.)
  propagating to the caller/CLI.

### TC-086 — Multiple interleaved standard and unknown chunks all survive or are warned about individually
- **Type**: functional / edge case
- **Level**: module (`io/wav_chunks.py`)
- **Covers**: AC9
- **Preconditions**: synthetic WAV with `fmt `, an unknown chunk, `bext`,
  another unknown chunk, `data`, in that sequence.
- **Steps**: Run full pipeline.
- **Expected result**: `bext` preserved byte-for-byte; both unknown chunks
  individually trigger their own warning (not a single combined/opaque
  warning that obscures which chunk had an issue) and are passed through
  where possible.

---

## 10. AC10 — Reproducibility

### TC-090 — Identical input + config produces byte-identical output and report (excluding explicitly time-based fields)
- **Type**: functional / regression
- **Level**: pipeline
- **Covers**: AC10
- **Preconditions**: fixed synthetic input, fixed config including a fixed
  dither seed.
- **Steps**: Run the pipeline twice, back to back, with identical
  input/config. Compare the two output WAV files (byte-for-byte / hash)
  and the two reports (structured comparison, field by field).
- **Expected result**: output WAV files are byte-identical (same SHA-256
  hash). Report contents are identical except for any field explicitly
  documented as run-specific (e.g. a wall-clock timestamp field, if one
  exists) — every measurement value, corrective-action log entry, and
  rationale text must match exactly between the two runs.

### TC-091 — Golden-file pipeline regression test
- **Type**: regression
- **Level**: pipeline
- **Covers**: AC10, architecture.md §7 (explicitly recommended)
- **Preconditions**: one fixed, checked-in reference input WAV (recommend
  sourcing a real anonymized/synthetic-but-representative Suno-style
  export once available) + fixed config + fixed dither seed.
- **Steps**: Process the reference input once to establish a golden output
  hash and golden report content (committed as test fixtures). On every
  subsequent test run (including across otherwise-unrelated code changes),
  reprocess the same input/config and compare against the golden fixtures.
- **Expected result**: output hash and full report contents match the
  golden fixtures exactly, for every run, until a deliberate, reviewed
  fixture update is made. Any drift is a regression signal requiring
  investigation before merge. **Flag**: requires a concrete reference
  input file to be checked in — recommend prioritizing acquisition of a
  real Suno export for this purpose (also serves AC9's chunk-preservation
  validation, TC-084).

### TC-092 — Different dither seed changes output but not measured values
- **Type**: functional / sanity check
- **Level**: pipeline
- **Covers**: AC10 (proves determinism is genuine, not a hardcoded/trivial
  pass)
- **Preconditions**: fixed input/config, but two different explicit dither
  seeds.
- **Steps**: Run pipeline twice with seed A, then seed B. Compare outputs.
- **Expected result**: the two output files differ (at least in their
  low-order/dither-affected bits) — confirming the seed genuinely affects
  the dither noise applied — while integrated LUFS/true-peak/DR
  measurements on both outputs remain equivalent within measurement
  tolerance (the seed should not materially change the audible/measurable
  mastering result, only the dither noise realization).

### TC-093 — Solver's bounded iteration is deterministic regardless of wall-clock timing
- **Type**: functional / regression
- **Level**: pipeline (with a timing-perturbation test harness)
- **Covers**: AC10, architecture.md §1/§9 risk #6 ("fixed max iteration
  count, no wall-clock-based cutoffs")
- **Preconditions**: fixed input/config; a test harness capable of
  injecting artificial delay into the solver's iteration loop (e.g. a
  monkeypatched sleep or slowed environment) without changing its logic.
- **Steps**: Run the pipeline twice with identical input/config — once at
  normal speed, once with injected iteration delay — and compare outputs.
- **Expected result**: outputs are identical regardless of how long the
  solver actually took to converge, confirming the solver's stopping
  condition is a fixed iteration count / deterministic convergence
  criterion, not a wall-clock timeout that could vary run to run.

---

## 11. AC11 — Non-destructive processing

### TC-100 — Input file hash unchanged before and after a run
- **Type**: functional — safety-critical
- **Level**: pipeline
- **Covers**: AC11
- **Preconditions**: any valid input file.
- **Steps**: Compute SHA-256 of the input file before running the
  pipeline. Run the pipeline (successful completion). Compute SHA-256 of
  the same input file path again afterward.
- **Expected result**: hashes are identical. Additionally assert file
  length in bytes is unchanged (cheap extra check beyond the hash).

### TC-101 — Output path equal to input path is hard-rejected before any write
- **Type**: functional — safety-critical / negative test
- **Level**: pipeline
- **Covers**: AC11 ("hard-fails... not just a convention")
- **Preconditions**: valid input file; explicitly configure/force the
  resolved output path to equal the input path (e.g. point `output_dir`
  at the input file's own directory with a naming override that collides,
  or directly pass output path == input path if the API allows it).
- **Steps**: Attempt to run the pipeline with this configuration.
- **Expected result**: pipeline raises a typed error (`MasteringError` or
  a subclass) *before* any write occurs; the input file is confirmed
  byte-identical (hash match) after the failed attempt; no partial/corrupt
  file is left at the input path.

### TC-102 — Input file never opened in a write-capable mode
- **Type**: functional — safety-critical
- **Level**: pipeline (black-box proxy)
- **Covers**: AC11
- **Preconditions**: valid input file; set the input file's filesystem
  permissions to read-only (e.g. Windows read-only attribute / chmod 444
  equivalent).
- **Steps**: Run the pipeline against this read-only input file.
- **Expected result**: the pipeline completes successfully — proving it
  never requires write access to the input path at any stage (ingest,
  pre-master analysis, or otherwise).

### TC-103 — Output always written to a new location, never overwriting input
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC11
- **Preconditions**: valid input file at a known path.
- **Steps**: Run the pipeline with default output-path derivation (no
  explicit override). Inspect the resolved output path.
- **Expected result**: resolved output path is a distinct file (e.g.
  `<name>_mastered.wav` in the configured output directory), never the
  same path as the input, by construction — not merely by the input
  happening to differ.

### TC-104 — Re-running with different settings against the same original input produces independent outputs
- **Type**: functional
- **Level**: pipeline
- **Covers**: AC11, resolved Open Question #10 (no dedicated versioning
  needed)
- **Preconditions**: valid input file.
- **Steps**: Run the pipeline twice against the same input with two
  different configs (e.g. different dither seeds or output directories).
- **Expected result**: two independent output files are produced without
  conflict, error, or requiring any "restore" step; the original input
  remains untouched and identical (hash check) throughout both runs.

---

## 12. Solver "give-up" path and typed error hierarchy

### TC-130 — Peak ceiling wins over LUFS band when they conflict
- **Type**: audio-quality — hard-constraint ordering
- **Level**: pipeline
- **Covers**: AC2, AC3, architecture.md §1 (solver design: "peak ceiling
  and DR floor are hard constraints; the LUFS band is a soft target")
- **Preconditions**: source engineered so any gain sufficient to reach
  -13.5 LUFS would push true peak above -1.0 dBTP (e.g. a source with an
  already near-ceiling true peak and low integrated loudness — large gap
  between peak and loudness, i.e. very high crest factor).
- **Steps**: Run full pipeline.
- **Expected result** (revised per architecture.md v4 §1, "Solver
  resolution for high-crest-factor sources", resolves DEF-001 residual —
  see "Revision history" below for what changed and why): post-master
  true peak ≤ -1.0 dBTP is never violated — assert
  `achieved_true_peak_dbtp <= -1.0` explicitly as a first-class check, not
  just implicitly via the LUFS assertion, since holding the peak ceiling
  exactly while sacrificing LUFS is the specific hard-constraint-ordering
  property this test exists to prove. Post-master LUFS lands below -13.5
  (and, for a high-crest-factor fixture of this shape, may land below -16
  LUFS, since -16 is now a **soft, report-escalation threshold**, not a
  hard solver constraint). `UnresolvableMasteringConstraintError` must
  **not** be raised. When the achieved LUFS lands below -16,
  `MasteringResult.below_documented_lufs_floor` must be `True`, the DR
  floor (`max(DR8, source_DR-3dB)`) must still be held exactly, and the
  report's rationale text must name the DR floor as the binding hard
  constraint — per architecture.md §1 point 5, the peak ceiling is
  enforced *by construction* inside candidate rendering (the limiter
  always holds it), so it is never the feasibility check's discriminator
  and is not expected to be named in the rationale text, even though this
  fixture's *design intent* is a peak-dominated scenario.
- **Note (resolves the DEF-001/DEF-002 coverage gap flagged in
  defects.md's 2026-08-01 qa-automation-engineer verification notes)**:
  an earlier draft of this test case's written intent required the
  rationale text to *sometimes* attribute the below-floor landing
  specifically to the true-peak constraint rather than the DR floor. That
  clause has been **dropped** — it is structurally unsatisfiable under the
  v4 solver design, not merely untested. architecture.md §1 step 2 states
  the peak ceiling "is enforced by construction" (the limiter guarantees
  `achieved_true_peak_dbtp <= ceiling` for every rendered candidate), so
  the bisection's feasibility check tests only the DR floor — the peak
  ceiling is never the reason a candidate is excluded, and therefore never
  the fact the rationale-generation code has to cite. This is also
  empirically confirmed against the current fixture, not just structurally
  argued: the 2026-08-01 verification run shows this fixture's actual
  winning candidate landing at `achieved_dr=17.0` (exactly equal to
  `dr_required=17.0`) **and** `achieved_true_peak_dbtp=-1.00` (exactly at
  the ceiling) simultaneously — even this specific fixture cannot isolate
  a peak-only-binding case from a DR-floor-binding one, because both sit
  at their boundary together at the selected candidate. No separate
  peak-ceiling-attributed test case has been added for the same reason: a
  fixture that would force the rationale to name the peak ceiling instead
  of the DR floor has not been shown to be constructible under this
  design, since DR is the sole feasibility discriminator by architecture.

### TC-131 — Genuinely unresolvable case raises UnresolvableMasteringConstraintError, no partial output written
- **Type**: edge case / robustness
- **Level**: pipeline
- **Covers**: AC2, AC3, AC4, architecture.md's errors.py design
- **Preconditions**: pathological synthetic source engineered so that even
  at the -16 LUFS floor, it's impossible to simultaneously satisfy the
  -1 dBTP ceiling and the DR floor (e.g. an already near-DR8 source with
  an extreme, unavoidable near-ceiling transient that cannot be gain-
  staged down without also pulling integrated loudness below -16 in a way
  that still doesn't resolve the conflict — construct via extreme,
  deliberately contradictory parameters). **Note (v4)**: per
  architecture.md §1 point 4, the precise, currently-implemented condition
  is narrower and more literal than "even at -16" — the pipeline evaluates
  the most conservative (near-zero-gain) candidate first and raises only
  if *that* candidate cannot hold the DR floor, or if the peak ceiling
  cannot be held even at unity/near-unity gain. Construct the fixture so
  its source is already at or below its own DR floor pre-processing (not
  merely a fixture where -16 specifically fails to resolve things, which
  under v4 is no longer unresolvable at all — see TC-016).
- **Steps**: Run full pipeline.
- **Expected result**: pipeline raises `UnresolvableMasteringConstraintError`
  (a subclass of `MasteringError`) with a message identifying which
  constraints could not be jointly satisfied. No output WAV file is left
  on disk (or if a temp/partial file was ever created, it is cleaned up —
  no partially-written or misleadingly "complete-looking" output file
  should exist after a failed run).

### TC-132 — Typed exception hierarchy: every specific exception is a MasteringError
- **Type**: functional
- **Level**: unit (errors.py)
- **Covers**: robustness NFR, architecture.md errors.py design
- **Preconditions**: N/A.
- **Steps**: Inspect `errors.py`; confirm `InvalidWavError`,
  `UnsupportedFormatError`, and `UnresolvableMasteringConstraintError` are
  all subclasses of `MasteringError`.
- **Expected result**: `issubclass()` checks pass for all three; a caller
  catching only `MasteringError` at the CLI boundary catches every
  documented failure mode, per architecture.md's CLI design ("catches the
  exception hierarchy from errors.py at the top level").

### TC-133 — CLI prints a clear message and exits non-zero on a typed error, without a raw traceback
- **Type**: functional
- **Level**: CLI/integration
- **Covers**: robustness NFR
- **Preconditions**: a fixture guaranteed to raise `InvalidWavError` (e.g.
  a corrupt-header file, per TC-121).
- **Steps**: Invoke the CLI (`python -m suno_mastering <input.wav>`)
  against the fixture.
- **Expected result**: process exits with a non-zero exit code; stderr/
  stdout contains a clear, human-readable error message; no raw Python
  traceback is the only thing printed (traceback may be available in a
  verbose/debug mode, but the default output must be a clean message).

---

## 13. Edge cases (requirements.md §6) — sample rate/bit depth variability and malformed files

### TC-120 — Sample rate × bit depth matrix ingests and processes correctly
- **Type**: functional (parametrized matrix)
- **Level**: pipeline
- **Covers**: AC1, AC9, requirements.md §3/§6
- **Preconditions**: parametrized combinations: sample rate ∈ {44100,
  48000, 32000 (non-standard)} × bit depth/format ∈ {16-bit PCM, 24-bit
  PCM, 32-bit float}.
- **Steps**: Run the full pipeline against each combination.
- **Expected result**: every combination ingests without error, produces
  a complete report, and produces a valid 24-bit output at the correct
  target rate (matching source for 44.1/48 kHz, defaulting to 44.1 kHz for
  32 kHz). 32-bit float ingestion is treated as a "should support, ideally"
  case per requirements.md wording ("ideally 32-bit float") rather than an
  absolute must — if it fails, that's a priority-1 defect but the
  requirement's own phrasing is softer than the integer-PCM cases, and
  this test case flags that distinction rather than treating both as
  identically hard requirements.

### TC-121 — Corrupt RIFF header fails gracefully
- **Type**: edge case — robustness
- **Level**: pipeline
- **Covers**: requirements.md §6 "Extremely short or malformed files"
- **Preconditions**: a file with invalid/corrupted RIFF magic bytes at the
  start (e.g. first 4 bytes not `RIFF`).
- **Steps**: Run the pipeline against this file.
- **Expected result**: `InvalidWavError` raised with a clear message; no
  crash/unhandled traceback.

### TC-122 — Zero-length audio fails gracefully
- **Type**: edge case — robustness
- **Level**: pipeline
- **Covers**: requirements.md §6
- **Preconditions**: a syntactically valid WAV header describing zero audio
  frames (empty `data` chunk).
- **Steps**: Run the pipeline.
- **Expected result**: `InvalidWavError` raised with a clear message
  referencing zero-length audio; no crash, no divide-by-zero propagating
  as a raw exception.

### TC-123 — Truncated file (declared size exceeds actual bytes) fails gracefully
- **Type**: edge case — robustness
- **Level**: pipeline
- **Covers**: requirements.md §6
- **Preconditions**: a WAV file whose header/`data` chunk declares more
  bytes than are actually present in the file (simulated truncated
  download/export).
- **Steps**: Run the pipeline.
- **Expected result**: `InvalidWavError` raised with a clear message; no
  crash from reading past end-of-file.

### TC-124 — Unsupported codec (e.g. ADPCM/non-PCM, non-float format) is rejected with a specific error
- **Type**: edge case — robustness
- **Level**: pipeline
- **Covers**: requirements.md §6, architecture.md errors.py design
- **Preconditions**: a valid WAV container using a compressed/non-PCM
  codec (e.g. IMA ADPCM) rather than PCM or IEEE float.
- **Steps**: Run the pipeline.
- **Expected result**: `UnsupportedFormatError` raised (distinct from
  `InvalidWavError` — the file is structurally valid, just an unsupported
  format), with a message naming the unsupported format.

### TC-125 — Non-WAV file with a .wav extension is rejected, not silently misread
- **Type**: edge case — robustness
- **Level**: pipeline
- **Covers**: requirements.md §6
- **Preconditions**: an MP3 (or other non-WAV binary) file renamed with a
  `.wav` extension.
- **Steps**: Run the pipeline.
- **Expected result**: `InvalidWavError` or `UnsupportedFormatError`
  raised (not a crash, not a silent misinterpretation of MP3 bytes as PCM
  samples producing garbage/noise output).

### TC-126 — Extremely short but structurally valid file does not crash
- **Type**: edge case — robustness / boundary
- **Level**: pipeline
- **Covers**: requirements.md §6 ("files that don't match the expected
  long-form duration profile")
- **Preconditions**: a structurally valid WAV, ~50 ms duration, far shorter
  than the expected 7+ minute long-form profile.
- **Steps**: Run the pipeline.
- **Expected result**: no crash. Per requirements.md, this is a robustness
  expectation ("fail gracefully... rather than crash"), not a mandate to
  reject short files outright — the implementation may either (a) process
  it through to a (possibly low-confidence, e.g. BS.1770 integration
  window too short to gate meaningfully) report and output, or (b) raise a
  typed error (e.g. if a stage has a genuine hard minimum-length
  requirement, such as the DR-meter's 3-second block size needing at least
  one full block). Both are acceptable; only an unhandled crash is a
  failure of this test. **Flag**: exact behavior at this boundary isn't
  fully pinned down by requirements.md — confirm actual implemented
  behavior against this test rather than assuming a single specific
  outcome is "the" correct one.

---

## 14. Edge cases — silence/near-silence dynamics handling (cross-cutting)

### TC-140 — Quiet breakdown is not "filled up" or over-compressed relative to surrounding loud sections
- **Type**: audio-quality
- **Level**: pipeline
- **Covers**: requirements.md §6, NFR "fidelity vs. manual baseline",
  AC4's intent
- **Preconditions**: synthetic long-form track: loud intro/buildup section
  at approx. -13 LUFS momentary, followed by a quiet breakdown at approx.
  -40 dBFS RMS, followed by a loud payoff section similar to the intro.
- **Steps**: Run full pipeline. Measure the relative level difference (in
  dB) between the loud sections and the quiet breakdown, before and after
  mastering.
- **Expected result**: the relative level difference between loud and
  quiet sections is materially preserved after mastering (broadband gain
  ± limiter action on peaks only, not per-section dynamic-range
  compression) — assert the before/after relative-difference values are
  within a small tolerance (e.g. ±1 dB) of each other, demonstrating the
  quiet section was not selectively boosted/"filled up" to sound louder
  relative to the rest of the track.

### TC-141 — Near-silent passage does not trigger a false clipping flag
- **Type**: edge case
- **Level**: pipeline
- **Covers**: requirements.md §6 (duplicate of TC-054 at pipeline level for
  end-to-end confidence)
- **Preconditions**: TC-140's fixture (quiet breakdown section).
- **Steps**: Run pre- and post-master clipping analysis specifically on
  the quiet-breakdown time range.
- **Expected result**: zero clipped/distorted samples reported in that
  range, before and after mastering.

### TC-142 — Near-silent passage does not trigger a false frequency-balance flag
- **Type**: edge case
- **Level**: pipeline
- **Covers**: requirements.md §6 (duplicate of TC-068 at pipeline level)
- **Preconditions**: TC-140's fixture.
- **Steps**: Run frequency-balance analysis on the quiet-breakdown range in
  isolation vs. the whole-track measurement.
- **Expected result**: the low-level noise floor content in the quiet
  section does not itself trigger thin-low-end/muddiness/harshness flags
  in the overall track measurement (i.e. its negligible energy is
  correctly down-weighted, not treated as equally significant to the loud
  sections' spectral content).

---

## 15. Non-functional requirements

### TC-150 — Processing time budget: 7–10 minute track under 5 minutes wall-clock
- **Type**: non-functional (performance)
- **Level**: pipeline
- **Covers**: NFR "processing time"
- **Preconditions**: synthetic stereo track, 8 minutes, 48 kHz/24-bit
  (worst-case sample count per the NFR's own example), run on a defined
  reference machine spec.
- **Steps**: Run the full pipeline (analysis + mastering combined), time
  wall-clock duration end-to-end.
- **Expected result**: completes in under 5 minutes wall-clock on the
  reference hardware. **Flag**: "typical consumer hardware" is not
  precisely defined in requirements.md — recommend the team agree a
  concrete reference machine spec (CPU class, RAM) for this test to be a
  reliable gate rather than an environment-dependent flake; until then,
  treat this as a tracked benchmark/trend rather than a strict CI gate on
  arbitrary hardware.

### TC-151 — Vectorization regression guard (no accidental per-sample Python loop)
- **Type**: non-functional (performance) — regression guard
- **Level**: pipeline
- **Covers**: NFR "processing time", architecture.md §7 vectorization note
- **Preconditions**: same fixture as TC-150, plus a recorded historical
  baseline runtime.
- **Steps**: Run the pipeline; compare runtime against the historical
  baseline (e.g. from the last known-good vectorized implementation).
- **Expected result**: runtime does not regress by more than, e.g., 2x the
  historical baseline without an explicit, reviewed justification — a
  sudden large regression is a strong signal that a stage (commonly the
  DR-meter block loop or the limiter's envelope follower, per
  architecture's explicit note) was accidentally reimplemented as a
  sample-by-sample Python loop instead of vectorized numpy/scipy.

### TC-152 — Fidelity vs. manual baseline (qualitative comparison) — flagged as needing a real reference
- **Type**: non-functional — flagged, largely manual/listening-based
- **Level**: pipeline + manual review
- **Covers**: NFR "fidelity vs. manual baseline"
- **Preconditions**: a track manually mastered via the Audacity/
  bx_mastering workflow the story explicitly names as the baseline being
  replaced (not yet available in-repo).
- **Steps**: Run this tool's pipeline on the same source track used for
  the manual master. Compare the six measurable criteria (LUFS in band,
  true peak ≤ -1 dBTP, DR within the AC4 constraints, frequency-balance
  flags resolved, mono-compatibility ≥0.0/target +0.3, no new clipping)
  numerically between the manual master and this tool's output.
- **Expected result**: this tool's output is at least equivalent to the
  manual baseline on each of the six numeric criteria. **Flag**: no real
  manually-mastered reference track exists in-repo yet to run this test
  against — this is the same category of residual validation gap as the
  genre reference curve (TC-067) and true-peak cross-validation (TC-024):
  concrete and automatable in method, but blocked on acquiring a real
  reference asset, not on requirements/architecture ambiguity.

---

## Traceability

### Acceptance criteria → test cases

| AC | Description | Test cases |
|---|---|---|
| AC1 | Pre-master analysis report | TC-001, TC-002, TC-003 |
| AC2 | Loudness target (soft [-14.5, -13.5] LUFS band, -13.5 hard ceiling, -16 soft report-escalation threshold — see architecture.md v4 §1) | TC-010–TC-017 (band/ceiling/rationale/floor-tier boundary), TC-033, TC-130, TC-131 |
| AC3 | True peak ceiling (-1.0 dBTP, zero exceptions) | TC-020–TC-025, TC-053, TC-130, TC-131 |
| AC4 | Dynamic range preservation (≥DR8, ≤3 dB reduction, stricter binds) | TC-030–TC-035, TC-131 |
| AC5 | Mono compatibility (≥0.0 overall, +0.3 target on widened elements) | TC-040–TC-047 |
| AC6 | Clipping detection and non-regression | TC-050–TC-054 |
| AC7 | Frequency balance detection and correction | TC-060–TC-068 |
| AC8 | Before/after report | TC-070–TC-074, TC-035, TC-065 |
| AC9 | Output file validity (format, rate, chunk preservation) | TC-080–TC-086, TC-120 |
| AC10 | Reproducibility | TC-090–TC-093 |
| AC11 | Non-destructive processing | TC-100–TC-104, TC-073 |

### requirements.md §6 edge cases → test cases

| Edge case | Test cases |
|---|---|
| Already-clipped input | TC-051, TC-052 |
| Mono source | TC-003, TC-045 |
| Silence/near-silence in long builds | TC-011, TC-012, TC-017, TC-054, TC-068, TC-140, TC-141, TC-142 |
| Sample rate/bit depth variability | TC-002, TC-081, TC-082, TC-120 |
| Extremely short/malformed/corrupt files | TC-121, TC-122, TC-123, TC-124, TC-125, TC-126 |

### architecture.md §7 testability notes → test cases

| Note | Test cases |
|---|---|
| Plain numpy-array module signatures enable synthetic-signal unit testing | Applies throughout — all module-level test cases (TC-010, TC-020–022, TC-030, TC-040–044, TC-050, TC-060–064, TC-066) |
| BS.1770/EBU Tech 3341 reference signals for loudness/true-peak calibration | TC-010, TC-020, TC-024 |
| (v5) Dedicated true-peak FIR frequency-response sweep against the tiered ripple envelope, independent of any specific track fixture | TC-025 |
| Injectable, non-time-based dither seed | TC-092, TC-090 |
| Solver iteration bound/convergence exposed via config, "give-up" path testable, below-floor fixture + genuinely-unresolvable fixture both testable | TC-015, TC-016, TC-033, TC-093, TC-130, TC-131 |
| Golden-file pipeline regression test | TC-091 |
| Pipeline stages callable in isolation | Applies to all module-level test cases (see above) |
| Vectorization (no per-sample Python loops) | TC-150, TC-151 |

### architecture.md residual risks (§9) → test cases (flagged validation dependencies)

| Risk | Test cases |
|---|---|
| #1 Genre reference curve not producer-verified | TC-067 |
| #2 TT DR-meter needs validation against reference tracks | TC-030–TC-034 (construction note), TC-152 |
| #3 True-peak needs cross-validation against an independent meter; v5 tiered near-Nyquist ripple/under-read residual, bounded but not eliminated | TC-024, TC-025 |
| #4 WAV chunk preservation unverified against a real Suno export | TC-084 |
| #5 Stereo-widened segmentation is a fixed heuristic, needs listening QA | TC-046, TC-047 |
| #6 Solver "give-up" path and deterministic convergence; -16 LUFS soft-floor behavior across the full tier range (in-band / below-14.5-above-16 / below-16 / genuinely-unresolvable) | TC-015, TC-016, TC-093, TC-130, TC-131 |
| #7 DR comparison baseline must be true original DR, not stage-6-entry DR | TC-034 |

---

## Revision history

- v1 (2026-07-31): Initial version. Based on requirements.md v2 (all open
  questions resolved) and architecture.md v2 (both architecture-level gaps
  resolved). No defects.md existed for this story at the time of writing,
  so there was no defect-driven coverage gap to incorporate — all test
  cases derive directly from AC1–AC11, requirements.md §6 edge cases, and
  architecture.md §7 testability notes/§9 residual risks.
- v2 (2026-08-01): Updated against requirements.md v3 and architecture.md
  v5 to close three specific gaps surfaced by defects.md DEF-001/DEF-002's
  2026-08-01 verification passes:
  1. **TC-016 rewritten.** It previously encoded the removed v1–v3 hard
     "-16 LUFS floor, clamp at exactly -16.0 or raise
     `UnresolvableMasteringConstraintError`" solver contract
     (architecture.md v4 §1 removed this design — the DR floor and -1 dBTP
     ceiling are now the solver's only hard constraints, and LUFS is a
     fully soft, open-ended target with no lower bound). Rather than
     simply restating TC-015/TC-130's now-shared "lands below -16, flag
     True, rationale names DR floor" contract a third time, TC-016 was
     repointed at a genuinely untested gap: the middle tier where the
     solver backs off below -14.5 but lands *above* -16
     (`below_documented_lufs_floor` should read `False`, with the
     baseline, non-escalated rationale tier). The old contract's "or
     raises `UnresolvableMasteringConstraintError`" half is not deleted —
     it is now explicitly rehomed to TC-131 (the genuinely-unresolvable-
     at-any-gain case), which TC-016 cross-references.
  2. **TC-130's peak-ceiling-attributed-rationale clause dropped.**
     defects.md (qa-automation-engineer's 2026-08-01 note, in the
     "Verification pass" section) flagged that TC-130's original written
     intent expected the solver's rationale text to sometimes attribute a
     below-floor landing to the true-peak constraint specifically, but the
     v4 design always names the DR floor for the below-floor tier by
     construction: architecture.md §1 step 2 states the peak ceiling "is
     enforced by construction" via the limiter (every rendered candidate
     already satisfies it), so the bisection's feasibility check — the
     thing whose failure the rationale text describes — tests only the DR
     floor. This was confirmed both structurally (from architecture.md's
     own algorithm description) and empirically (the 2026-08-01
     verification run shows TC-130's actual winning candidate landing at
     `achieved_dr == dr_required` and `achieved_true_peak_dbtp == -1.00`
     simultaneously, so even this fixture cannot isolate a peak-only-
     binding case). The clause was dropped rather than replaced with a new
     test case, since no fixture has been shown constructible under this
     design that would force the rationale to name the peak ceiling
     instead of the DR floor. TC-130 otherwise keeps its original title
     and hard-constraint-ordering intent (peak ceiling held exactly while
     LUFS is sacrificed), now asserted as a first-class check.
  3. **TC-025 added.** architecture.md v5 (§2 "True-peak passband ripple
     target — revised" and §7's frequency-sweep testability note) replaced
     the v4 single flat <0.01 dB-to-~0.999×-Nyquist aspirational
     verification target — which two independent tuning attempts proved
     infeasible within the 5-minute NFR budget — with a tiered
     ripple-vs-frequency envelope matching the verified,
     already-implemented FIR filter's real behavior (defects.md DEF-002's
     second residual, 2026-08-01). TC-025 specifies this tiered envelope
     precisely (five nested frequency/tolerance bands, both the `freqz`
     filter-response leg and the end-to-end `measure_true_peak()` leg,
     the required attenuation-only sign check, and the explicit
     non-conflation with `config.true_peak_monotonicity_tolerance_db`) so
     `tests/test_smoke_true_peak_fir.py` can be extended to cover the four
     tiers beyond the already-implemented/passing 0.80×/0.01 dB tier. No
     TC-024 duplication: TC-024 is external-meter cross-validation on real
     files, TC-025 is an internal frequency-response sweep against a
     documented tiered target — the two are complementary and
     cross-reference each other.

  Also updated: the document header/status line and the config-defaults
  scope note (both previously described `-16` as a hard floor rather than
  a soft report-escalation threshold), and the Traceability tables (AC2,
  AC3, and both §7/§9 tables) to reflect the above.
