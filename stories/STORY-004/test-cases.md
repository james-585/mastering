# STORY-004 — Test Cases: Measurement correctness (DEF-201, DEF-203, DEF-204)

Governed by `CLAUDE.md`, `docs/DOMAIN.md`, `docs/ARCHITECTURE.md`,
`docs/HANDOFF.md` (H-rules). Derived from `stories/STORY-004/requirements.md`
and `stories/STORY-004/architecture.md` (v1.3, post-Gate-1). Architecture.md
§5 ("Testability notes") is treated as authoritative for fixture
construction, expected values, and tolerances; no expected value in this
document is invented — each traces to a cited section of architecture.md,
DOMAIN.md, or is shown as analytically derived from the fixture's own
construction (H4). Where architecture.md's own stated evidence for a
pre-fix result did not check out against its own formulas, this is flagged
rather than asserted (see TC-407 below) — see "Ground truth, not regression
locks": expected values must be derivable, not copied from a document's
prose when the prose disagrees with the document's own arithmetic.

This story is analysis-only (no audio written/mutated/mastered). The
Definition of Done's human listening check applies vacuously — noted, not
tested.

No `defects.md` exists yet for STORY-004 at the time of writing; no
gap-driven revision was required. If one is added later that reveals a
coverage gap, this document's revision-history section must record it per
the standard process.

## ID mapping note

This document numbers test cases TC-4xx at the story level. Several
fixtures are existing tests in `stories/STORY-001/implementation/tests/`
(e.g. `test_tc020_*` → TC-401, `test_tc021_*` → TC-402, `test_tc023_*` →
TC-403, `test_tc024_pink_noise_no_cutoff` → TC-406, `test_tc025_*` →
TC-410) — cited by their existing function names where architecture.md
itself does ("existing TC-020/021/023/024/025"). Whether
qa-automation-engineer renames the underlying `test_tcXXX_*` functions to
match this document's TC-4xx numbering, or keeps the existing names with
TC-4xx used only as this document's cross-reference ID, is an automation
decision this document does not make — but per architecture.md §4's own
opening instruction ("grep the full tests/ tree... this story's own
root-cause history (DEF-104, DEF-106) is entirely instances of a rename
shipping incompletely"), whichever mapping is chosen must be applied
completely, not partially. TC-458/TC-459 below are the direct test cases
for this.

---

## Fixture legend

Unless stated otherwise, all fixtures are short synthetic buffers (2–5 s),
per architecture.md §5.4, and count toward the 60-second fast-suite bound.
Only §5.3's real five-track reference-set re-run is marked **Slow** and
isolated from that bound, per the existing DEF-106 precedent.

---

## A. HF band-limit detection (DEF-201) — architecture.md §3, §5.1

### A1. Ground-truth positive fixtures (ties to AC2, AC3)

**TC-401 — Brickwall lowpass at 15 kHz, mono, 44.1 kHz (existing TC-020)**
- Preconditions: white/pink noise, brickwall-filtered at exactly 15 kHz,
  SR=44100, mono, 2–5 s.
- Steps: run `measure_hf_extension` on the fixture.
- Expected result: `hf_band_limit_hz == pytest.approx(15000, abs=500)` Hz;
  `stable is True`. Derivation: brickwall = infinite floor by construction,
  a canonical positive case (architecture.md §5.1 row 1).
- Type: audio-quality / regression-of-ground-truth (H2).

**TC-402 — Brickwall lowpass at 8 kHz, mono, 44.1 kHz (existing TC-021)**
- Same construction as TC-401 at 8 kHz cutoff.
- Expected: `hf_band_limit_hz == pytest.approx(8000, abs=500)` Hz; `stable is True`.
- Type: audio-quality (H2).

**TC-403 — Brickwall at 16 kHz with 27 dB finite floor, mono, 44.1 kHz (existing TC-023)**
- Preconditions: noise lowpassed at 16 kHz with a realistic finite stopband
  floor 27 dB below passband (codec-realistic case, not an infinite floor).
- Expected: `hf_band_limit_hz == pytest.approx(16000, abs=500)` Hz.
- **Calibration risk, stated per architecture.md §5.1 row 2 / §6 risk 6**: if
  this fails under the new detector, diagnose whether the *method* (log-grid
  + passband + fixed-bar floor check) is being applied correctly before
  touching `hf_cliff_floor_min_fraction`/`hf_cliff_floor_noise_margin_db` —
  tuning those into a still-wrong method repeats the H6 trap this story
  exists to close.
- Type: audio-quality (H2), calibration-flagged.

**TC-404 — Tilted (−6 dB/oct) then brickwalled at 20 kHz, SR=48000, mono (revised at Gate 1)**
- Preconditions: pink/tilted noise at −6 dB/octave from ~500 Hz up, then
  brickwall-filtered at exactly 20000 Hz. SR=48000, mono (must not be a bare
  brickwall — a 0 dB/octave pre-slope trivially clears the 12 dB/octave
  passband gate and does not exercise the gate→drop→floor interaction,
  architecture.md §5.1).
- Steps: run detector; also inspect `per_segment_hf_band_limit_hz` and
  `hf_band_limit_confidence`.
- Expected result: `hf_band_limit_hz == pytest.approx(20000, abs=1000)` Hz
  (tolerance **widened** from the interior-range ±500 Hz — architecture.md
  §3.5 derives the ≈20774 Hz ceiling with ≈774 Hz margin, comparable to one
  grid band's width at this frequency; §3.5 states this margin is
  "empirically unconfirmed until that fixture is run" — **open question,
  flag if this fails**, do not silently widen further). `stable is True`.
- Type: audio-quality (H2), near-Nyquist — **required, not optional** per
  architecture.md §5.1 (closes the near-Nyquist detectability gap that is
  the real 48 kHz reference set's operating range).

**TC-404b — Stereo variant of TC-404 (NEW — advisor-flagged gap)**
- Preconditions: same construction as TC-404 (tilt-then-brickwall at
  20 kHz, SR=48000), rendered as a genuine **stereo** buffer — two channels,
  either identical or mildly decorrelated (e.g. independently seeded noise
  through the same tilt+brickwall design), not mono.
- Steps: run `measure_hf_extension` on the stereo buffer.
- Expected: `hf_band_limit_hz == pytest.approx(20000, abs=1000)` Hz, same
  tolerance and derivation as TC-404.
- **Required — closes a coverage gap, not a formality.** Every HF fixture
  architecture.md §5.1 specifies is mono by construction, but every real
  reference track is stereo — the identical shape of gap DEF-204 was raised
  to close for sample rate (44.1 kHz-only fixtures vs. 48 kHz real tracks).
  **Open question, flagged in section F, not resolved here**: architecture.md
  §3 does not state how `measure_hf_extension` reduces a stereo input to a
  single PSD for the cliff detector (channel 0 only, mono sum, or
  channel-averaged PSD) — this test's expected value assumes the reduction
  preserves the cliff frequency under any of those choices (all three
  reduce to the same cliff on identical/near-identical channels), but the
  reduction method itself is undefined behaviour sitting directly on the
  real code path and must be confirmed at implementation time, not assumed.
- Type: audio-quality, mandatory-coverage checklist (stereo input).

**TC-405 — Pink noise brickwalled at 15 kHz (tilt + real cliff together, NEW)**
- Preconditions: pink noise (declining spectrum) additionally brickwalled
  at 15 kHz.
- Expected: `hf_band_limit_hz == pytest.approx(15000, abs=500)` Hz.
- Purpose: proves the passband precondition (§3.4) does not over-reject a
  genuine cliff riding on ordinary tilt — the control the REOPENED DEF-201
  entry explicitly asked for. Type: audio-quality (H2).

### A2. Negative controls (H3 — mandatory)

**TC-406 — Full-band pink noise, no cutoff, mono, 44.1 kHz (existing TC-024, rewritten)**
- Preconditions: stationary pink noise, no lowpass filter, full band to
  Nyquist.
- Steps: run detector against **current shipped code** first, confirm it
  passes there too (architecture.md §5.1 explicitly notes this fixture
  already passes under the current code's old assertion — its passing is
  not, by itself, evidence DEF-204 is closed; state this in the coverage
  writeup, not just the test). Then run against corrected code.
- Expected (corrected code): `hf_band_limit_hz is None`. No numeric
  fallback value permitted — asserting any numeric value here is itself a
  defect (requirements.md AC1). Also assert `hf_band_limit_confidence ==
  1.0` and `stable is True` — per architecture.md §3.7, when the
  whole-track result is `None`, confidence measures the fraction of
  segments *also independently reporting no cliff*; on stationary pink
  noise every segment should agree, giving 1.0, not 0.0 (easy to write
  backwards — flag §6 risk 7's unconfirmed judgment-call status).
- Type: audio-quality / negative control (H3). **This is the single test
  that would have caught DEF-201 in its original form** — but per
  architecture.md §5.1/§9, this exact fixture already passed against the
  shipped code (stationary, tilt too shallow to cross the old threshold),
  so it is a secondary regression control here, not the primary DEF-204
  evidence (see TC-408).

**TC-407 — Tilted (−6 dB/oct), full-band, NO cliff, SR=48000 (NEW, Gate 1 Blocker fixture)**
- Preconditions: spectrally tilted at exactly −6 dB/octave from low-mid up,
  full band, no lowpass filter applied anywhere — decline continues at the
  constant rate all the way to Nyquist. SR=48000. Must NOT be white noise
  (a flat spectrum has no ordinary top-end roll-off to test against and
  would pass for the wrong reason).
- **Confirmed-failing-first evidence, corrected against architecture.md's
  own arithmetic (flagged, not asserted from §5.1's prose alone) —**
  §5.1's table states this fixture "must be run against the pre-fix
  scaled-bar draft first (recording that it incorrectly reports a
  non-`None` value near ≈20.7 kHz)." Checked directly against §3.3's own
  formulas, this specific claim does not hold for a *constant* −6 dB/octave
  tilt: the v1.2 scaled bar is `required_drop_db = w × 1.0 dB`; the drop a
  constant 6 dB/octave decline produces across `w` bands of `1/24` octave
  is `6 × w/24 = 0.25w` dB — strictly less than the `1.0w` dB bar at every
  `w` from 3 to 8 (e.g. `0.75` dB vs. `3.0` required at `w=3`; `2.0` dB vs.
  `8.0` at `w=8`). A pure constant-tilt signal therefore cannot clear
  *either* the v1.2 scaled bar or the v1.3 fixed bar — it does not produce
  the ≈20.7 kHz false positive §5.1's prose predicts. **This is exactly the
  class of thing H2/H4 require flagging rather than copying**: architecture.md
  §5.1's stated pre-fix evidence for this specific fixture conflicts with
  §3.3's own drop-arithmetic; do not assert the "FAILS near ≈20.7 kHz"
  outcome as if it were confirmed.
  - Steps as actually satisfiable: (1) run this constant-tilt fixture
    against the corrected (v1.3) detector only — see Expected result below;
    a separate accelerating-slope construction (below) is needed to
    demonstrate the pre-fix vacuous-bar failure. (2) **Open question,
    flagged in section F**: architecture.md does not specify a concrete
    accelerating near-Nyquist "knee" construction (a candidate window whose
    local drop clears the v1.2 scaled bar — as little as 3.0 dB over a
    1/8-octave window at `w=3` — but stays under the v1.3 fixed 8.0 dB bar)
    with enough numeric detail (exact slope, exact onset frequency) to
    build without inventing a value not stated anywhere. Constructing that
    fixture and confirming it fails against v1.2 but passes (`None`)
    against v1.3 is the correct completion of the Gate 1 Blocker's H3/H7
    evidence trail; it is left as an explicit open item rather than
    fabricated here.
- Expected result (corrected v1.3 code, the part that IS directly
  derivable): `hf_band_limit_hz is None` at every candidate the search
  range admits. Derivation shown: the passband gate (§3.4, ≤12 dB/octave)
  admits every candidate since 6 dB/octave is well under the ceiling, but
  the fixed 8.0 dB drop bar (§3.3) cannot be satisfied by a constant 6
  dB/octave decline at any window size — max possible drop is `6 × w/24`
  dB, i.e. `2.0` dB even at `w=8` (note: architecture.md §3.3 itself states
  "1.5 dB even at w=8" for this same arithmetic — a second, independent
  arithmetic slip in that section; `6 × 8/24 = 2.0`, not `1.5`; flagged in
  section F, does not change the pass/fail outcome since both values are
  far under the 8.0 dB bar). Also assert `hf_band_limit_confidence == 1.0`,
  `stable is True` (§3.7 None-branch), and every entry of
  `per_segment_hf_band_limit_hz` is `None`.
- Type: audio-quality / negative control (H3), **mandatory per Gate 1
  Blocker resolution** for the corrected-code assertion. The **pre-fix
  "confirmed failing" evidence for this exact fixture is not obtainable as
  architecture.md describes it** — flagged as an open question (section F),
  not silently worked around.

**TC-408 — Tilt + non-stationarity, no real cutoff (NEW — primary DEF-204 negative control)**
- Preconditions: concatenation of several pink/brown-noise segments with
  deliberately *different* per-segment 500–2000 Hz reference-band energy
  (differing overall gain and/or spectral tilt exponent per segment;
  construction pattern analogous to `mono_low_decorrelated_high_stereo` in
  `ref_helpers.py`). No segment contains any band-limiting filter. True
  near-Nyquist absence of cutoff throughout.
- Steps (H3/H7 sequencing): 1) run against **current shipped code**, record
  the concrete numeric `rolloff_hz` value it returns (mid-band false
  positive expected, in the pattern of GusGus's 1979 Hz / Leftfield's 8170
  Hz) in a code comment/commit message, confirming failure; 2) implement
  the fix; 3) run against corrected code only for the shipped assertion.
- Expected result (corrected code): `hf_band_limit_hz is None`.
  `hf_band_limit_confidence == 1.0`, `stable is True`.
- Type: audio-quality / negative control (H3). **Primary DEF-204 evidence**
  — this is the fixture the wiring-gap investigation found missing; TC-406
  (stationary) cannot expose the passband-tilt confound and the existing
  drift fixture (TC-410, the rewritten former TC-025) cannot either (its
  non-stationarity is a genuine cutoff-frequency *change*, not a
  cutoff-free tilt change). **Confirmed failing first, mandatory** — this
  sequencing IS directly satisfiable here, unlike TC-407's, because the
  pre-fix detector's `rolloff_hz` field exists under the old schema and
  produces a concrete numeric (not an AttributeError) false positive.
- Type: audio-quality / negative control (H3).

**TC-409 — Recommended (not required): rising-toward-Nyquist noise-shaped signal, SR=48000**
- Preconditions: energy rising toward Nyquist (e.g. noise-shaped dither
  profile), no real cutoff.
- Expected: `hf_band_limit_hz is None`. Fails the monotonicity requirement
  (§3.3 test 2) by construction — a rising band cannot satisfy "non-
  increasing within +1 dB tolerance."
- Type: audio-quality / negative control (H3), **recommended, not required**
  per architecture.md §5.1 — a second independent line of defense; TC-407's
  corrected-code assertion and TC-408 already close the Gate 1 Blocker /
  DEF-204 requirements between them.

### A3. Stability / segmentation (AC3)

**TC-410 — `brickwall_lowpass_noise_with_drift` (existing TC-025)**
- Preconditions: cutoff frequency genuinely drifts across the file
  (existing fixture).
- Expected: `hf_band_limit_confidence < config.hf_cliff_confidence_stable_floor`
  (0.6) — rewritten from the old raw-Hz-spread assertion, since `stable`
  as a directly-set field no longer exists in that form; `stable` is now
  derived from confidence.
- Type: audio-quality (regression, rewritten assertion).

**TC-411 — Segmentation actually runs (NEW — advisor-flagged gap)**
- Preconditions: any 48 kHz fixture from A1/A2 (e.g. TC-404).
- Steps: inspect the full `HfExtensionResult`, not just `hf_band_limit_hz`.
- Expected: `insufficient_duration is False`; `len(per_segment_hf_band_limit_hz)
  == config.hf_stability_segment_count` (5, architecture.md §3.7 default).
- **Open question, flagged not resolved**: no duration floor below which
  the detector short-circuits to `insufficient_duration` is stated anywhere
  in architecture.md. Architecture.md §5.4 specifies 2–5 s fixtures; a 2 s
  buffer split 5 ways is 0.4 s/segment and may trip an undocumented floor.
  If any A1/A2 fixture unexpectedly reports `insufficient_duration is
  True`, this is the open question to raise, not a fixture bug to silently
  work around by lengthening the buffer without recording why.
- Type: functional, wiring/coverage (DEF-204).

**TC-412 — Real segmented, silence-gated code path exercised with silence gaps (NEW — advisor-flagged, closes DEF-204 core wiring gap)**
- Preconditions: take TC-404's 48 kHz tilt-then-brickwall-20 kHz fixture;
  insert digital-silence gaps between segments and/or a silent lead-in.
- Steps: run detector on both the unpadded (TC-404) and silence-padded
  versions.
- Expected: `hf_band_limit_hz` on the silence-padded version matches the
  unpadded TC-404 result within the same ±1000 Hz tolerance. Derivation:
  silence gating that works correctly excludes the silent regions from the
  active-audio PSD and must not change the measured cliff; a mis-wired
  gate (e.g. one that lets silence dilute band energy, or that isn't
  actually gating) will shift or null the answer.
- Type: audio-quality / regression, **required** — this is the specific
  gap DEF-204 names ("the synthetic fixtures do not exercise the real
  segmented, silence-gated code path", story.md).

### A4. Sample-rate coverage (48 kHz set, second DEF-204 gap)

**TC-413 — 48 kHz variant set: TC-401/TC-402-equivalent at SR=48000**
- Preconditions: same constructions as TC-401 (15 kHz brickwall) and
  TC-402 (8 kHz brickwall), re-rendered at SR=48000.
- Expected: same tolerances as TC-401/TC-402 (±500 Hz), `stable is True`.
- Type: audio-quality, closes the "every real reference track is 48 kHz;
  existing suite was 44.1 kHz only" gap (architecture.md §5.1 row "NEW —
  48 kHz variant set", §9).

**TC-414 — 48 kHz variant of TC-408 (tilt + non-stationarity, no cutoff)**
- As TC-408, at SR=48000.
- Expected: `hf_band_limit_hz is None`, confidence 1.0, stable True.
- Type: audio-quality / negative control, 48 kHz coverage.

**TC-415 — Sample-rate invariance, direct comparison (NEW — advisor-flagged)**
- Preconditions: the *same* brickwall cutoff (e.g. 15 kHz) rendered once at
  44.1 kHz (TC-401) and once at 48 kHz (TC-413's 15 kHz case).
- Steps: compare the two `hf_band_limit_hz` results directly.
- Expected: both report the same Hz value within the shared ±500 Hz
  tolerance, i.e. `abs(hz_44100 - hz_48000) <= 500 + 500` combined
  (or, tighter: both individually within ±500 Hz of 15000 and thus within
  1000 Hz of each other). Purpose: directly tests §3.2's log-frequency-grid
  sample-rate-invariance claim by construction — this is the structural
  half of the DEF-204 fix, not just "run fixtures at both rates
  separately."
- Type: audio-quality, structural regression guard.

### A5. Boundary / implementation-detail exercises

**TC-416 — Empty log-band fallback path (NEW — architecture.md §3.2, mandatory per prose)**
- Preconditions: a deliberately very short synthetic buffer such that the
  Welch PSD's linear bin spacing is coarser than a `1/24`-octave log band
  near the search floor (i.e. short enough that `log_band_levels_db` must
  take its "band containing zero linear PSD bins" fallback path at least
  once).
- Steps: run `log_band_levels_db` (directly, if testable at that unit
  level) or the full detector on the short buffer.
- Expected: no exception raised; `hf_band_limit_hz` is well-formed (either
  a finite Hz value or `None`, never `NaN` or a crash). Derivation: §3.2's
  own docstring states the fallback "falls back to the nearest single bin
  rather than raising" and that "the fallback exists for short synthetic
  test fixtures only, and must be exercised by at least one test with a
  short buffer" — this is an architecture-mandated test, not optional
  coverage.
- Type: edge case / boundary.

**TC-417 — Very short file (shorter than any analysis window)**
- Preconditions: e.g. 0.1 s mono buffer, well under any segment length.
- Expected: either a well-defined `hf_band_limit_hz` (None or finite) with
  `insufficient_duration is True` and `hf_band_limit_confidence == 0.0`
  (per §3.8's `HfExtensionResult` docstring: "0.0 iff
  insufficient_duration"), or a graceful no-crash `None` result — no
  exception, no NaN.
- Type: edge case.

**TC-418 — All-digital-silence buffer through HF detector**
- Preconditions: all-zero mono/stereo buffer, any SR.
- Expected: `hf_band_limit_hz is None` (flat/zero PSD everywhere — no
  slope, no cliff, by construction), no divide-by-zero, no crash.
- Type: edge case (silence handling, mandatory-coverage checklist item).

**TC-419 — DC offset present**
- Preconditions: brickwall-at-15kHz fixture (TC-401's construction) with a
  constant DC offset added (e.g. +0.05 full-scale).
- Expected: `hf_band_limit_hz` unaffected (still ≈15000 ± 500 Hz) — DC is a
  0 Hz component and must not perturb HF-band detection; no crash from the
  PSD computation.
- Type: edge case.

### A6. Plausibility gate / renamed-threshold coverage (AC6)

**TC-420 — `_HF_ROLLOFF_SUSPECT_HZ` raised 5000→10000 Hz (architecture.md §4 item 7b)**
- Preconditions: a fixture engineered to report a band limit around 7000 Hz
  (e.g. brickwall at 7000 Hz, analogous construction to TC-401/402).
- Steps: run `check_hf_rolloff_vs_air_band` (or the pipeline call site) on
  the resulting `hf_band_limit_hz`.
- Expected: a plausibility warning IS raised at 7000 Hz under the corrected
  `10000.0` threshold (previously, under `5000.0`, no warning would have
  fired — this is the exact gap architecture.md names as "not flagged...
  directly in scope for this story's own H5 plausibility gate," §4 item
  7b). **Caveat, stated explicitly**: this warning is emitted under the
  shipped `sanity_warnings` field name, not `plausibility_warnings` — see
  TC-490 below for why this naming gap is out of scope, not a defect in
  this test.
- Type: functional / plausibility (H5, AC6).

**TC-421 — No warning at a genuinely commercial-plausible band limit**
- Preconditions: brickwall at 16000 Hz (TC-403's construction).
- Expected: no `_HF_ROLLOFF_SUSPECT_HZ`-triggered warning (16 kHz is above
  the 10 kHz threshold).
- Type: functional / negative control on the plausibility check itself.

---

## B. Mono-sum derivation (DEF-203) — architecture.md §2, §5.2

### B1. Ground-truth verification points (AC4 — mandatory, all three)

**TC-450 — ρ = 1.0, L = R exactly (existing DEF-101 case-1 pattern)**
- Preconditions: dual-mono synthetic stereo, right channel identical to
  left, any stationary content (e.g. sine or noise), any SR.
- Expected: `mono_sum_level_change_db == pytest.approx(0.0, abs=0.05)` dB.
  Derivation (architecture.md §2.1/§2.2): `mono_sum = (L+L)/2 = L`, so
  `mono_lufs == left_lufs == channel_mean_lufs` exactly → 0 dB.
- Type: audio-quality (H2, ground truth, literal AC4 point 1).

**TC-451 — ρ = 0.0, independent equal-power noise (existing `independent_noise_stereo`)**
- Preconditions: L and R are independently generated, uncorrelated,
  equal-power noise.
- Expected: `mono_sum_level_change_db == pytest.approx(-3.0103, abs=0.1)` dB.
  Derivation shown (architecture.md §2.1): `ratio = (1 + kρ)/2` with `k=1`
  (equal power) and `ρ=0` → `ratio = 0.5` → `10·log10(0.5) = -3.0103 dB`.
  This is the literal H4 verification point AC4 requires.
- Type: audio-quality (H2, ground truth, literal AC4 point 2).

**TC-452 — ρ = −1.0, fully inverted (`R = −L`, existing `inverted_stereo`)**
- Preconditions: R is the exact negation of L.
- Expected: `mono_sum_level_change_db == float("-inf")`, no exception
  raised. Derivation: `mono_sum` is identically zero everywhere →
  `mono_lufs = -inf`; `channel_mean_lufs` is finite (both channels have
  real signal) → difference is `-inf`, a legitimate result per §2.1.
  Also confirms the §2.2 NaN-guard hardening does not spuriously fire on a
  genuinely-cancelling (not both-silent) signal.
- Type: audio-quality (H2, ground truth, literal AC4 point 3).

### B2. Both-channels-silent guard (Gate 1 advisory, closed in v1.3)

**TC-453 — Both channels exact digital silence (all-zero stereo buffer)**
- Preconditions: all-zero stereo buffer, any SR/duration.
- Steps (H7 sequencing — schema mismatch across pre/post-fix, stated
  explicitly per architecture.md §5.1's analogous process note applied
  here): pre-fix evidence must be recorded as `math.isnan(result.
  level_change_db)` against the **old field name** (`level_change_db`,
  pre-rename) on the pre-guard code — confirming the NaN hazard the Gate 1
  advisory found (`(-inf) - (-inf) = NaN` in IEEE arithmetic; `NaN < -4.5`
  is `False` in Python, so a silent file would silently fail to flag). The
  shipped test then asserts the new contract only, against corrected code —
  the two cannot share one assertion body, same reasoning as the HF
  fixtures' H7 note.
- Expected result (corrected code): `mono_sum_level_change_db ==
  pytest.approx(0.0, abs=0.001)` dB (the defined ρ=1 limit, per
  architecture.md §2.2's guard — NOT a NaN, NOT a crash);
  `mono_sum_excess_cancellation is False`; `mono_sum_both_channels_silent
  is True`.
- Type: audio-quality / edge case (silence handling), **required per Gate 1
  advisory closure**. Confirmed-failing-first: pre-fix code produces NaN,
  not the defined value.

**TC-454 — Exactly one channel silent (advisor/§6 risk 11 — non-blocking, documented gap, still worth a sanity test)**
- Preconditions: left channel all-zero, right channel real signal (any
  level).
- Expected: `mono_sum_level_change_db == pytest.approx(-3.0103, abs=0.1)`
  dB — well-defined and arithmetically correct (§2.2: with one channel's
  linear power at 0, `ratio = 1/2` regardless of ρ). **Explicitly NOT
  distinguishable from healthy ρ=0 stereo by this metric alone** — this
  test documents the known, accepted (non-blocking) limitation architecture
  §6 risk 11 flags, it does not assert a fix. `mono_sum_both_channels_silent
  is False` (only one channel is silent, not both).
- Type: edge case, documents an open architectural risk rather than a pass/
  fail correctness bar.

### B3. Excess-cancellation trigger (AC5, one-sided threshold)

**TC-455 — ρ ≈ 0.7 (DOMAIN.md §3's own "normal correlation" range) — negative control**
- Preconditions: R constructed as `ρ·L + sqrt(1-ρ²)·N` with `ρ=0.7`, N
  independent noise, L any stationary noise/tone. By construction,
  `Var(R) = ρ²·Var(L) + (1-ρ²)·Var(N)`; choosing `Var(N) = Var(L)` gives
  `Var(R) = Var(L)` exactly (equal power, k=1), so §2.1's equal-power
  formula `10·log10((1+ρ)/2)` applies directly.
- Expected: `mono_sum_excess_cancellation is False`. Derivation:
  `10·log10((1+0.7)/2) = 10·log10(0.85) ≈ -0.706` dB, well above the −4.5
  dB trigger.
- Type: audio-quality / negative control (H3) for the excess-cancellation
  trigger specifically — architecture.md §5.2 row 5.

**TC-456 — Boundary pair around −4.5 dB (NEW — derived from §2.1, not listed in §5.2)**
- Preconditions: two fixtures constructed as `R = ρ·L + sqrt(1-ρ²)·N`, with
  `Var(N) = Var(L)` chosen so `Var(R) = ρ²·Var(L) + (1-ρ²)·Var(L) =
  Var(L)` exactly — equal channel power by construction (`k=1`), so §2.1's
  equal-power formula applies directly rather than the general `k`-weighted
  one:
  - (a) ρ ≈ −0.204 (target −4.0 dB, just above/not-flagged side).
  - (b) ρ ≈ −0.368 (target −5.0 dB, just below/flagged side).
  Derivation shown: from §2.1's `ratio = (1+kρ)/2`, `k=1` (equal power
  construction), solve `ρ = 2·10^(target_db/10) − 1`. At −4.0 dB:
  `ρ = 2·10^(-0.4) − 1 ≈ -0.204`. At −5.0 dB: `ρ = 2·10^(-0.5) − 1 ≈
  -0.368`.
- Expected: (a) `mono_sum_level_change_db ≈ -4.0` dB (abs 0.15, widened
  slightly for the three-way BS.1770 gating divergence §2.2 flags),
  `mono_sum_excess_cancellation is False`. (b) `mono_sum_level_change_db ≈
  -5.0` dB, `mono_sum_excess_cancellation is True`.
- **Note on the exact-threshold case**: a fixture constructed for exactly
  ρ ≈ −0.290 (→ exactly −4.5 dB) is not specified as a separate test
  because architecture.md §2.2 itself flags that the three independent
  BS.1770 gate decisions (left/right/mono_sum) introduce unformalized
  divergence on the order of ~0.01 dB even on stationary fixtures — a
  boundary-exact assertion would be testing gating noise, not the
  threshold logic. The flanking pair above is the discriminating test; if
  it needs a wider tolerance than 0.15 dB in practice, that is new evidence
  about §2.2's open risk 5, not a defect in this test's construction.
- Type: boundary value (mandatory-coverage checklist item), derived per
  H4, not asserted from an invented number.

### B4. Internal consistency (structural check, H5 #1)

**TC-457 — Broadband/per-band ρ=0 agreement (architecture.md §2.1/§5.2 row 6)**
- Preconditions: a flat-spectrum synthetic ρ=0 signal (independent
  equal-power noise, flat PSD).
- Steps: compute both `mono_sum_level_change_db` (broadband) and the
  per-band `BandCancellation.delta_db` for a representative band on the
  same signal.
- Expected: both agree within `abs=0.2` dB. Derivation: both now share the
  single `_DECORRELATED_FLOOR_DB = -3.0103 dB` constant applied at
  different bandwidths (§2.1) — not two independently-tuned numbers, the
  same formula at two resolutions. This is a structural regression guard
  against future drift, not new discovery (architecture.md is explicit
  that this agreement, once true, should not need re-proving from scratch).
- Type: audio-quality / internal consistency (H5 #1), regression guard
  (explicitly labeled as such per H2 — the *fact* it must agree is
  ground-truth-derivable, but the specific 0.2 dB tolerance is a
  regression-detection band, not independently re-derived here).

### B5. Rename-completeness (H6/H4 — no stale constant may survive)

**TC-458 — No superseded `-6.0206` / `_BROADBAND_DECORRELATED_FLOOR_DB` constant survives (NEW — static check)**
- Preconditions: the full `suno_mastering/analysis/` tree post-fix.
- Steps: grep for `-6.0206`, `_BROADBAND_DECORRELATED_FLOOR_DB`,
  `excess_cancellation_db`, `headroom_db` across `analysis/` and
  `reference_analysis/`.
- Expected: zero matches. Derivation: requirements.md AC4 states "no
  constant referencing the superseded channel-summed comparator... may
  remain in the shipped code"; architecture.md §2.3 confirms
  `excess_cancellation_db` is removed, not renamed.
- Type: functional / static / regression (rename-completeness, per
  architecture.md §4's own instruction to grep the full `tests/` tree
  before/after for exactly this class of incomplete rename — DEF-104/
  DEF-106's own root cause).

**TC-459 — Rename-completeness across the full test tree (NEW)**
- Preconditions: `stories/STORY-001/implementation/tests/` post-fix.
- Steps: grep for `rolloff_hz`, `per_segment_rolloff_hz`, `level_change_db`
  (without the `mono_sum_` prefix), `excess_cancellation_db`,
  `hf_rolloff_threshold_db`, `transcode_suspect_slope_db_per_octave`,
  `mono_cancellation`.
- Expected: zero matches outside of historical comments/docstrings
  explicitly citing the old names for traceability (e.g. "supersedes
  `rolloff_hz`") — no live assertion or fixture kwarg uses the old names.
- Type: functional / static, mandated directly by architecture.md §4's
  opening instruction.

---

## C. Real reference-set re-run (AC2, AC3, AC5, AC6) — architecture.md §5.3 — **Slow**

**TC-480 — All five references: plausible band limit or `None`, ≥10 kHz**
- Preconditions: the five reference WAV files (`Reference Tracks/*.wav`,
  48 kHz), run through the corrected pipeline end to end.
- Steps: for each track, record `hf_band_limit_hz`.
- Expected: each value is either a plausible band limit per DOMAIN.md §2's
  table, or `None`; no value below 10000 Hz reported for any track without
  an explicitly noted lossy-sourced justification (requirements.md AC2 —
  do not assume CD-lossless provenance; a lower plausible value per
  DOMAIN.md §2's bitrate table is acceptable, not a defect). `None` is an
  accepted pass outcome (architecture.md §3.4's horn-(a) note).
- Type: audio-quality, **Slow**, expected-not-guaranteed (measurement, not
  a target) — record actual values, do not assume them.

**TC-481 — Stability on commercial/CD-sourced references (AC3)**
- Preconditions: same five-track set.
- Expected: for tracks with a genuine fixed band limit (the reference set's
  commercial/CD-sourced members), the reported limit is stable
  (`hf_band_limit_confidence` at/near 1.0) or `None` — never a wrong-but-
  stable value. Segment-to-segment disagreement on Suno/generative material
  is explicitly NOT treated as a defect (DOMAIN.md §2, "may drift within
  one file"; requirements.md AC3).
- Type: audio-quality, **Slow**.

**TC-482 — 10–20 kHz local-slope data collection (§3.4 horn-(a) — Gate 2 evidence, not pass/fail)**
- Preconditions: same five-track set.
- Steps: record each track's measured 10–20 kHz local slope
  (dB/octave).
- Expected: **no threshold is asserted here** — this is data collection
  for the mastering-engineer's Gate 2 review of the 12 dB/octave passband
  ceiling against real material (architecture.md §3.4, §5.3), not a
  pass/fail test. Attaching a threshold here would be inventing a number
  not in any governing document.
- Type: non-functional / data-collection, **Slow**, explicitly not a
  correctness assertion.

**TC-483 — No excess cancellation on any reference (AC5)**
- Preconditions: same five-track set.
- Expected: `mono_sum_excess_cancellation is False` for all five tracks,
  consistent with DOMAIN.md §3's 0.5–0.9 normal-correlation range for
  commercial electronic material. Expected, not guaranteed (measurement).
- Type: audio-quality, **Slow**.

**TC-484 — H5 plausibility gate on the full reference report (AC6)**
- Preconditions: full corrected reference report generated for all five
  tracks.
- Steps: run all four H5 checks (internal consistency, material
  plausibility, spread check, round-number check).
- Expected: report passes, or any failure appears as an entry in the
  shipped `sanity_warnings` field (**not** `plausibility_warnings` —
  architecture.md §3.9/§6 risk 9 explicitly leaves this rename out of
  scope for this story; a test asserting against `plausibility_warnings`
  cannot pass by design and must not be written that way). This mismatch
  between requirements.md AC6's wording and the shipped field name is
  flagged here explicitly, not silently reconciled.
- Type: functional / plausibility (H5), **Slow**.

---

## D. Non-functional and process (AC7, reproducibility, 60 s bound)

**TC-490 — `sanity_warnings`/`plausibility_warnings` naming gap (documentation of scope, not a bug)**
- Not a pass/fail test. Recorded here so a future reader does not treat
  AC6's `plausibility_warnings` wording as an unmet requirement: per
  architecture.md §3.9 and §6 risk 9, this rename is explicitly out of
  scope for STORY-004 ("Rejected as out of scope" in requirements.md).
  TC-420 and TC-484 above are written against the shipped `sanity_warnings`
  name intentionally.
- Type: N/A — documentation entry.

**TC-491 — Reproducibility: bit-identical output across runs**
- Preconditions: any single fixture (e.g. TC-404) and the real reference
  set.
- Steps: run the full analysis twice on identical input/config.
- Expected: bit-identical output (requirements.md, Non-functional
  requirements — "no non-determinism introduced by either method change").
- Type: non-functional / regression.

**TC-492 — Fast suite completes under 60 seconds**
- Preconditions: all fast fixtures (everything in sections A and B above,
  excluding section C).
- Steps: run the full fast suite, time it.
- Expected: total runtime < 60 s (HANDOFF.md Part 3 Definition of Done).
  Section C (real reference-set re-run) is isolated from this bound per
  DEF-106's existing precedent, confirmed unchanged by this story
  (architecture.md §5.4).
- Type: non-functional.

**TC-493 — AC7: Gate 1/Gate 2 review — not automatable**
- Not a test case in the executable sense. AC7 is a process criterion:
  Gate 1 review confirming the DEF-203 method-change reconciliation
  (already completed — `stories/STORY-004/gate1-review.md`, PASS-WITH-
  BLOCKERS, resolved in architecture.md v1.3) and Gate 2 review on real
  reference-set output with no unresolved Blockers (not yet performed at
  time of writing this document). Mapped in the traceability table below
  to the review artifacts, not to an executable test ID — an honest gap
  is preferable to inventing an automated proxy.
- Type: N/A — process / review artifact.

---

## E. Mandatory coverage checklist

**Correctness**
- Happy path per AC: TC-401–405 (HF positive), TC-450–452 (mono-sum three
  points), TC-480/483 (real-set).
- Boundary values: TC-456 (±0.5 dB either side of −4.5 dB trigger), TC-416
  (empty log-band boundary), TC-411 (segment-count boundary).
- Idempotency: N/A for this story's scope — analysis-only, no
  transformation to be idempotent over; **reproducibility** (TC-491) is the
  applicable analogue and is covered.
- Bypass/disabled: N/A — no config flag disables either detector in this
  story's scope; not introduced here.

**Audio-specific**
- Mono input: TC-401–403, TC-405–409 (HF, mono by construction).
- Stereo input: all of section B (mono-sum is inherently stereo-only);
  TC-404b (HF detector on genuine stereo input — closes a gap the first
  draft of this document left open, see advisor review).
- Multiple sample rates: TC-401/402 (44.1 kHz) vs TC-413 (48 kHz same
  cutoffs) vs TC-415 (direct comparison).
- Silence / near-silence: TC-418 (HF, all-silent), TC-453 (mono-sum,
  both-silent), TC-454 (mono-sum, one-channel-silent).
- Full-scale / already-clipping input: **not covered — open gap.** Neither
  architecture.md §5 nor requirements.md specifies an expected value for
  a full-scale/clipped HF or mono-sum fixture; flagged as an open question
  rather than inventing a tolerance. Recommend a future pass add this if
  clipping-robustness of the log-PSD/BS.1770 paths becomes a concern.
- Very quiet input: not separately specified by architecture.md beyond the
  silence cases (TC-418/453/454 cover the zero-amplitude extreme); no
  near-silence-but-not-silent fixture is specified with a derivable
  expected value — flagged as an open gap, not invented.
- DC offset: TC-419 (HF detector unaffected by DC).
- Very short file: TC-417 (HF, insufficient-duration path), TC-416 (empty
  log-band fallback, a related but distinct short-buffer case).

**Failure modes**
- Corrupt/truncated file, unsupported format, missing file, wrong channel
  count: **N/A for this story**, stated explicitly rather than dropped
  silently. Requirements.md's Input/output assumptions state "No new
  input format handling is in scope" and "this story does not read or
  write Suno raw exports specifically — it operates on whatever the
  existing analysis pipeline already consumes." File-level I/O error
  handling is pre-existing STORY-001/002 scope, not touched by this
  story's two method changes.

**Units and precision**
- Every expected result above states its unit explicitly: `hf_band_limit_hz`
  is Hz with Hz tolerance; `hf_band_limit_confidence` is a unitless
  fraction `[0,1]`; `mono_sum_level_change_db` is a **difference of two
  independently-gated LUFS values**, expressed in dB (not an absolute LUFS
  reading); the per-band `delta_db` (TC-457) is a PSD band-power ratio in
  dB; the 8.0 dB drop bar and 12/24 dB/octave figures (referenced in
  derivations, not directly asserted by test-case-writer-authored tests —
  they are architecture-internal constants exercised indirectly through
  TC-404–409) are slope units, dB per octave, not absolute dB.

---

## F. Open questions carried forward (not resolved here, per H4 — do not invent)

1. **§3.5's ≈20774 Hz (48 kHz) / ≈19087 Hz (44.1 kHz) near-Nyquist ceiling
   and the ±1000 Hz tolerance on TC-404/TC-404b**: architecture.md states
   this is "empirically unconfirmed until that fixture is run." If TC-404
   fails, this is the first thing to revisit — not the fixture's tolerance.
2. **TC-403's (16 kHz finite-floor) ±500 Hz tolerance** may need
   calibration against the new method — architecture.md §5.1/§6 risk 6
   instruct diagnosing method-correctness before number-correctness on any
   failure here.
3. **`hf_band_limit_confidence`'s None-branch semantics** (architecture.md
   §3.7, exercised by TC-406/407/408/409/414) is the architect's own
   judgment call, unconfirmed by any governing document — §6 risk 7 flags
   it for Gate 1 confirmation. If Gate 1 review revises this semantics, all
   negative-control confidence assertions in section A2 need re-checking,
   not just re-running.
4. **Duration floor for `insufficient_duration`** (TC-411/TC-417) — no
   document states the threshold; flagged, not guessed.
5. **Full-scale/clipping and very-quiet (non-silent) fixtures for both
   detectors** — no governing document specifies expected values; flagged
   as a coverage gap in section E rather than filled with invented
   tolerances.
6. **`sanity_warnings` vs `plausibility_warnings` naming** (TC-420, TC-484,
   TC-490) — explicitly out of scope per architecture.md §3.9/§6 risk 9;
   tests are written against the shipped name intentionally, and this is
   not an oversight.
7. **TC-407's pre-fix "confirmed failing" evidence is not obtainable as
   architecture.md §5.1 describes it.** A constant −6 dB/octave tilt
   produces at most `6 × w/24` dB of drop across any admissible window
   (`0.75`–`2.0` dB across `w=3..8`), which clears neither the v1.2 scaled
   bar (`w × 1.0` dB, `3.0`–`8.0` dB) nor the v1.3 fixed bar (`8.0` dB) —
   it cannot produce the ≈20.7 kHz false positive §5.1's prose claims as
   pre-fix evidence. Demonstrating v1.2's near-vacuous bar requires a
   distinct fixture: an accelerating near-Nyquist "knee" whose local drop
   clears the v1.2 minimum (as little as 3.0 dB over a 1/8-octave window at
   `w=3`) but stays under the v1.3 fixed 8.0 dB bar. Architecture.md does
   not specify this construction's exact slope or onset frequency
   numerically; inventing one here would violate H4. Left as an explicit
   open item for the architect or a follow-up pass, not fabricated.
8. **Architecture.md §3.3's own stated arithmetic has a second, independent
   slip** (separate from item 7's fixture-evidence issue): it states a
   constant 6 dB/octave decline yields "1.5 dB even at w=8," but
   `6 × 8/24 = 2.0` dB, not `1.5` dB. Noted in TC-407; does not change any
   pass/fail outcome (both values are far under the 8.0 dB bar), but should
   be corrected in architecture.md itself by whichever agent next has safe
   edit access.
9. **HF stereo-channel-reduction method is undefined** (TC-404b). No
   section of architecture.md §3 states whether `measure_hf_extension`
   reduces a stereo buffer to channel 0, a mono sum, or an averaged PSD
   before running the cliff detector. TC-404b's expected value assumes the
   reduction preserves the constructed cliff frequency under any of the
   plausible choices, but the actual choice is undefined behaviour on the
   real code path (every reference track is stereo) and should be
   confirmed and documented at implementation time.

---

## Traceability table

| Acceptance criterion | Test case IDs |
|---|---|
| AC1 — HF negative control, correctly targeted | TC-406 (pink noise, rewritten), TC-407 (tilted-Nyquist, primary Gate-1-Blocker control — see open question 7 on its pre-fix evidence), TC-408 (tilt+non-stationarity, primary DEF-204 control), TC-409 (recommended second control), TC-414 (48 kHz variant) |
| AC2 — Real reference set plausibility | TC-480 (Slow); supported by the H2 ground-truth anchors below |
| AC3 — Stability, scoped correctly | TC-410, TC-411, TC-481 (Slow) |
| AC4 — Mono-sum derivation (all 3 ρ points) | TC-450, TC-451, TC-452, TC-457 (structural consistency), TC-458/TC-459 (rename completeness) |
| AC5 — Excess cancellation threshold | TC-455, TC-456, TC-483 (Slow) |
| AC6 — H5 plausibility gate | TC-420, TC-421, TC-484 (Slow), TC-490 (naming-gap documentation) |
| AC7 — Gate 1 and Gate 2 review | TC-493 (process artifact, not executable — Gate 1 complete per `gate1-review.md`; Gate 2 pending) |
| H2 ground-truth anchors — HF method-change correctness (not tied to a single AC; underpin AC2/AC3/AC6 by proving the corrected method is right on known-construction material before it is trusted on real tracks) | TC-401, TC-402, TC-403, TC-404, TC-404b, TC-405 |
| Non-functional: 60 s bound | TC-492 |
| Non-functional: reproducibility | TC-491 |
| DEF-204 wiring-gap closure (segmented/silence-gated path) | TC-412, TC-413, TC-415 |
| Gate 1 Blocker (near-Nyquist drop-bar fix) | TC-404 (positive, tilt-then-brickwall), TC-407 (negative control, corrected-code assertion; pre-fix evidence flagged open, item 7) |
| Gate 1 Advisory (both-channels-silent NaN hazard) | TC-453 (confirmed-failing-first), TC-454 (documented non-blocking residual gap) |
| Architecture §3.2 mandated fallback test | TC-416 |
| Edge cases (silence, DC, short file) | TC-416, TC-417, TC-418, TC-419, TC-453, TC-454 |
| Stereo input coverage on the HF detector | TC-404b |

Every AC has at least one test case, and the HF method's positive
ground-truth anchors (TC-401–405, TC-404b) are now explicitly mapped rather
than left implicit. No AC is covered only by a Slow test without a
corresponding fast synthetic ground-truth or negative-control case
(AC2/AC3/AC5/AC6 each also have fast section A/B coverage feeding into the
same measurement functions the Slow real-set tests exercise end-to-end).

---

## Revision history

v1 (this document) — first pass, produced from `stories/STORY-004/
requirements.md` and `stories/STORY-004/architecture.md` v1.3. No
`defects.md` existed for STORY-004 at time of writing, so no gap-driven
revision was required. Incorporates architecture.md §5's fixture table
directly (fast suite: sections A, B; Slow real-set: section C) plus
several additions not listed in §5's tables but required by prose
elsewhere in architecture.md or by the mandatory coverage checklist:
the §3.2 empty-log-band fallback test (TC-416), the silence-gated
segmented-path test (TC-412), explicit segmentation-ran assertions
(TC-411), None-branch confidence assertions on every negative control,
rename-completeness static checks (TC-458/459), the −4.5 dB boundary pair
derived directly from §2.1's formula (TC-456), sample-rate-invariance as a
direct comparison (TC-415), and the `sanity_warnings`/`plausibility_
warnings` naming-gap documentation (TC-490) to prevent AC6 tests being
written against a field name this story does not create.

v1.1 (same pass, pre-delivery revision after advisor review) — four
findings addressed: (1) **TC-407's stated pre-fix "confirmed failing"
evidence did not check out against architecture.md §3.3's own drop-bar
arithmetic** — a constant −6 dB/octave tilt cannot clear either the v1.2
scaled bar or the v1.3 fixed bar, so it cannot produce the ≈20.7 kHz false
positive §5.1's prose claimed as pre-fix evidence; rewritten to assert only
the corrected-code result directly, with the unobtainable pre-fix evidence
flagged as open question 7 rather than fabricated (a second, independent
arithmetic slip in the same section of architecture.md — "1.5 dB" where
the formula gives 2.0 dB — is separately flagged as open question 8). (2)
**Added TC-404b**, a stereo variant of the HF near-Nyquist fixture — the
first draft's entire HF suite was mono-only despite every real reference
track being stereo, the same shape of gap DEF-204 already names for sample
rate; the undefined stereo-channel-reduction behaviour this exposes is
flagged as open question 9. (3) **Traceability table**: added an explicit
row for TC-401–405/TC-404b, the H2 positive ground-truth anchors for the
entire HF method change, which the first draft's table omitted while still
claiming full AC coverage. (4) Fixed an internal cross-reference error
(TC-408 cited "TC-409" for the drift fixture; corrected to TC-410) and
added the ID-mapping note clarifying how existing `test_tcXXX_*` function
names relate to this document's TC-4xx numbering, per architecture.md §4's
own rename-completeness warning. TC-456 gained an explicit line showing
the `Var(N)=Var(L) → Var(R)=Var(L)` equal-power construction step so the
`k=1` simplification is derived, not assumed.
