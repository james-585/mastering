# STORY-003 Test Cases: Ground-Truth Test Harness

## 0. Scope, conventions, and how to read this document

This document translates architecture.md §7's per-measurement
ground-truth specifications (and §2-6's DEF-201/DEF-203 fix designs)
into test-case form, traceable to requirements.md's numbered
acceptance criteria (AC1-AC13). Architecture.md's fixture generator
names/signatures, formulas, and tolerances are treated as authoritative
and reused verbatim; this document does not invent new numbers where
architecture.md already derived one.

**Files.** Per architecture.md §5, these test cases map onto:
`test_ground_truth_loudness.py`, `test_ground_truth_true_peak.py`,
`test_ground_truth_hf_extension.py`, `test_ground_truth_dynamic_range.py`,
`test_ground_truth_spectral_balance.py`, `test_ground_truth_stereo_width.py`,
`test_ground_truth_sanity_assertions.py`, `test_ground_truth_kweight_oversample.py`,
all under `stories/STORY-001/implementation/tests/`, each marked
`pytestmark = pytest.mark.ground_truth`. A few test cases are process/
documentation checks (AC1-AC3, AC11, AC13) rather than pytest assertions;
these are marked **Type: non-functional (process)** and say so explicitly.

**Ground truth vs. regression, stated per test case.** Every test case
below states whether its expected value is analytically derived from
the signal's construction (**ground-truth**) or, where architecture.md
itself flags a figure as reasoned-but-not-empirically-verified (e.g.
the AC8a 20 dB gap, the AC9c width>=0.8 floor), that is stated as
**directional/relational, architect-reasoned, not yet tightened** — this
is not a regression test (the direction is still derived from
construction, not from running the tool), but the exact tolerance
number is provisional and flagged, per architecture.md §10.

**Config field names** used throughout (from `reference_analysis/config.py`
/ `config.py`, confirmed by reading the shipped code, not assumed):
`hf_rolloff_threshold_db` (6.0 pre-fix / 40.0 post-fix, AC6),
`hf_rolloff_test_tolerance_hz` (500.0), `hf_stability_tolerance_hz`
(2000.0), `hf_min_duration_s` (30.0 default, override via
`ref_config(hf_min_duration_s=2.0)`), `hf_stability_segment_count` (5),
`lra_tolerance_lu` (1.0), `lra_relative_gate_lu` (-20.0),
`dr_block_seconds` (3.0), `dr_exclude_fraction` (0.2),
`clip_sample_threshold` (0.999), `phase_correlation_floor` (0.0),
`freq_reference_band_hz` (500-2000 Hz), `freq_low_band_hz` (20-120 Hz),
`freq_mud_band_hz` (200-500 Hz), `freq_presence_band_hz` (2000-5000 Hz),
`mono_band_cancellation_excess_db` (-3.0).

**Pre-existing production code, confirmed by reading the shipped code
before writing these test cases**: `analysis/sanity.py` (the four
`check_*` functions), the `sanity_warnings` fields on `Measurements`/
`ReferenceMeasurements`, the wiring in `analysis/__init__.py::measure_all`
and `reference_analysis/pipeline.py::analyze_track`, both renderers, and
`SCHEMA_VERSION = "1.2"` in `report/reference_builder.py` **already
exist on disk** — AC10/AC13's production-code design is implemented.
What is confirmed **not yet done**: `hf_rolloff_threshold_db` is still
`6.0` (DEF-201 unfixed), and no `test_ground_truth_*.py` files exist yet.
Test cases below are written against this actual state, not an assumed
one.

---

## 1. Loudness (LUFS) — AC4, `test_ground_truth_loudness.py`

### TC-001 — 1 kHz sine at known dBFS amplitude → known LUFS (AC4a)
- **Covers**: AC4a
- **Type**: audio-quality (ground-truth) — **already satisfied by existing `test_tc010`** (`tests/test_ac2_loudness.py`); this entry records it in this suite's traceability rather than duplicating it.
- **Preconditions**: mono, 1 kHz sine, -20 dBFS RMS (`rms_amplitude_for_dbfs_sine(-20.0)`), 3-5 s, 44.1 kHz.
- **Steps**: `measure_integrated_lufs(sine, sr)`.
- **Expected result**: `abs(lufs - (-20.0)) < 0.1` LU.
- **Derivation**: 1 kHz is BS.1770's calibration-neutral frequency — the K-weighting high-shelf's gain at 1 kHz (shelf center ≈1682 Hz, Q≈0.707, so the shelf's rise has only barely begun at 1 kHz) combines with the standard's fixed -0.691 dB offset to net ≈0 dB total, so LUFS ≈ input dBFS RMS directly. Not a coincidence specific to this implementation — this is the standard, published reason 1 kHz is BS.1770's own calibration tone.
- **Note**: recommend adding this derivation to `test_tc010`'s docstring per architecture.md §7.1 (it currently states the number without the "why," which AC3 requires for every ground-truth test — this is a gap-closing action, not a new test).

### TC-002 — 6 dB gain change moves integrated loudness by exactly 6 LU (AC4b)
- **Covers**: AC4b
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: two mono 1 kHz sines, 3-5 s, 44.1 kHz, at an *exact* 6.000 dB linear amplitude ratio: `amplitude2 = amplitude1 * 10**(6/20)` — **not** `amplitude1 * 2.0` (which is 6.0206 dB, not 6.0). `amplitude1` any convenient level, e.g. -20 dBFS RMS.
- **Steps**: measure both; compute `lufs2 - lufs1`.
- **Expected result**: `abs((lufs2 - lufs1) - 6.0) < 0.1` LU.
- **Derivation**: LUFS is a log-power measure; a fixed linear gain of `10**(6/20)` applied uniformly to a signal whose K-weighted gate/threshold behavior is unaffected (both signals well above the -70/-10 LU gates and short-term-stationary) shifts every gated block's log-power by exactly the same additive 6.0 dB, hence the integrated result too.

### TC-003 — Below the absolute gate floor → integrated LUFS is exactly -inf (near-silence / very quiet input)
- **Covers**: story.md's silence/near-silence requirement; requirements.md's "Known degenerate cases" section; edge-case checklist item "very quiet input" and "silence/near-silence"
- **Type**: audio-quality (ground-truth), edge case
- **Preconditions**: mono 1 kHz sine, RMS = -80 dBFS (well below the absolute gate), 3-5 s.
- **Steps**: `measure_integrated_lufs(sine, sr)`.
- **Expected result**: return value is exactly `float("-inf")`.
- **Derivation**: block loudness for this 1 kHz signal ≈ -80 dBFS + (≈-0.0354 dB net offset at 1 kHz, per TC-001's calibration-neutral derivation — **not** the naive, uncancelled -0.691 dB fixed offset this test case's own derivation previously used) ≈ -80.04 LUFS, which is comfortably below the BS.1770 absolute gate of -70 LUFS — every block fails the absolute gate, so no block ever reaches the relative-gate/integration step, and pyloudnorm returns `-inf` by its own documented, spec-conformant behavior (already exercised by STORY-001's existing `test_silence_dynamics.py` for the pure-silence case; this test is the "quiet but not literally zero" variant of the same gate). At -80 dBFS the fixture sits so far below the gate that this arithmetic correction does not change the -inf conclusion either way — only the intermediate number is corrected here, per `stories/STORY-002/defects.md` DEF-207 item 1.
- **Negative control pairing**: see TC-004 for the "just above the gate" case, confirming the tool does not spuriously report `-inf` (or blow up) for legitimately quiet-but-measurable audio.

### TC-004 — Just above the absolute gate floor → finite LUFS close to the RMS-derived value (negative control for TC-003)
- **Covers**: same as TC-003; negative control
- **Type**: audio-quality (ground-truth), edge case, boundary
- **Preconditions**: mono 1 kHz sine, RMS = -68 dBFS (above the -70 LUFS absolute gate by ≈1.96 dB, using the ≈-0.0354 dB net offset that applies at 1 kHz — see Derivation — not the naive, uncancelled -0.691 dB fixed offset), 3-5 s.
- **Steps**: `measure_integrated_lufs(sine, sr)`.
- **Expected result**: finite value, `abs(lufs - (-68.04)) < 0.1` LU — specifically **not** `-inf` and **not** a wildly different number ("gain-staging blows up" failure mode this checklist item targets).
- **Derivation**: per TC-001's own calibration-neutral reasoning, 1 kHz's net offset (K-weighting shelf gain combined with BS.1770's separate -0.691 dB fixed offset) is ≈0 dB, not -0.691 dB uncancelled — so `LUFS ≈ input dBFS RMS` directly, giving an expected value of ≈-68.0 LUFS for a -68 dBFS RMS input, not the previously-stated -68.69. The absolute-gate boundary this fixture sits above is therefore ≈-69.96 dBFS RMS (the RMS level whose block loudness first reaches the -70 LUFS floor once the ≈-0.0354 dB net offset is applied), not this test case's original, uncorrected ≈-69.3 dBFS implied boundary. This correction — and the underlying arithmetic error in this test case's original derivation, which had treated the -0.691 dB offset as uncancelled at 1 kHz, directly contradicting TC-001's own stated reasoning one section earlier — is recorded in `stories/STORY-002/defects.md` DEF-207 item 1, confirmed there empirically against seven RMS levels (-80 to -20 dBFS, all at 1 kHz), every one showing the same fixed, level-independent ≈-0.0354 dB net offset. Tolerance is kept at the original `±0.1` LU (generous relative to the ≈0.0354 dB residual) — the residual is cited only as justification that the existing tolerance is adequate, not adopted as a tighter expected value.

### TC-005 — DC offset does not materially move LUFS
- **Covers**: edge-case checklist item "DC offset present"
- **Type**: audio-quality (ground-truth), edge case
- **Preconditions**: mono 1 kHz sine at -20 dBFS RMS (as TC-001) plus a constant DC offset added to every sample (e.g. `+0.2`, well below clipping for a -20 dBFS tone).
- **Steps**: measure LUFS on (a) the plain sine (TC-001's fixture) and (b) the same sine with DC offset added.
- **Expected result**: `abs(lufs_with_dc - lufs_without_dc) < 0.1` LU (i.e. within TC-001's own tolerance — DC offset should not be visible in the result at all).
- **Derivation**: BS.1770-4 Annex 1's K-weighting stage includes a high-pass filter (corner ≈38 Hz per `loudness_range.py`'s own coefficients) whose response at 0 Hz is a deep, specification-mandated null — DC content is removed before power integration by design. pyloudnorm implements the same published filter. This is a standards-derived expectation, not an invented number.

---

## 2. True peak (dBTP) — AC5, `test_ground_truth_true_peak.py`

### TC-010 — Nyquist-adjacent sine: exact, known inter-sample-overshoot margin (AC5a)
- **Covers**: AC5a
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `nyquist_adjacent_sine(sr, duration_s=2.0)` — `x[n] = sin(pi*n/2 + pi/4)`, i.e. exactly `sr/4` Hz with a 45-degree phase offset (`conftest.py` addition per architecture.md §1.2), amplitude 1.0, converted to stereo via `to_stereo`.
- **Steps**: (a) compute the plain sample peak: `20*log10(max(abs(audio)))`. (b) `measure_true_peak(to_stereo(fixture), sr, config).dbtp`.
- **Expected result**: (a) sample peak = `-3.0103 dBFS` exactly (every sample lands at exactly `±1/sqrt(2)`). (b) `dbtp` within `0.05 dB` of `0.0` (the true continuous-time peak), and `dbtp - sample_peak_dbfs >= 2.9` dB.
- **Derivation**: at exactly `sr/4` Hz with a 45-degree phase offset, every discrete sample lands at `±1/sqrt(2)` (sample peak exactly `-3.0103 dBFS`), while the continuous-time signal's true peak of `1.0` (`0 dBTP` exactly) occurs at instants that fall exactly halfway between consecutive samples — the classic, *exact* (not approximate) inter-sample-overshoot construction, giving an analytically known `3.0103 dB` margin.
- **Note**: deliberately **not** a near-Nyquist frequency — `true_peak.py`'s own documented FIR droop (~1.5 dB at 94% Nyquist) would corrupt the expected value there. `sr/4` sits well inside the FIR's flat passband regardless of oversample factor.

### TC-011 — True peak and sample peak return genuinely different values (AC5b, direct regression guard)
- **Covers**: AC5b
- **Type**: audio-quality (ground-truth), regression guard, **new**
- **Preconditions**: same fixture as TC-010.
- **Steps**: assert `measure_true_peak(...).dbtp != pytest.approx(sample_peak_dbfs, abs=0.5)`.
- **Expected result**: the assertion **must fail** if `dbtp` and sample peak agree within 0.5 dB — write this as the literal test. This is the direct guard against true peak silently degrading into a sample-peak computation (AC5b's explicit purpose).

### TC-012 — Negative control: low-frequency sine shows no meaningful inter-sample overshoot
- **Covers**: AC5 (negative control, not explicitly numbered but required by this document's own "Ground truth" rule — a true-peak detector tested only on the classic overshoot case would pass even if it *always* reported a large fixed offset)
- **Type**: audio-quality (ground-truth), negative control, **new**
- **Preconditions**: mono 100 Hz sine, amplitude 0.5, 2-3 s, converted to stereo.
- **Steps**: compute sample peak and `measure_true_peak(...).dbtp`.
- **Expected result**: `abs(dbtp - sample_peak_dbfs) < 0.1 dB`.
- **Derivation**: a low-frequency sine (100 Hz, far below Nyquist at any typical sample rate) is smooth relative to the sample interval — its peak is already well-represented by the sampled points, so no genuine inter-sample overshoot exists. A detector that reports a large true-peak/sample-peak gap regardless of input would fail this test; this is what proves TC-010's positive result is measuring a real effect, not a fixed bias.

### TC-013 — Inter-sample-over count is nonzero with zero sample-level clipping (true-peak-vs-clipping separation)
- **Covers**: AC5, `detect_clipping`'s `inter_sample_over_count` field (one of the 11 AC1 functions)
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `nyquist_adjacent_sine(sr, 2.0, amplitude=1.05)`, stereo.
- **Steps**: `detect_clipping(audio, sr, config)`.
- **Expected result**: `sample_peak_clipped_count == 0` (sample values are `±1.05/sqrt(2) ≈ ±0.742`, well below `clip_sample_threshold=0.999`); `inter_sample_over_count > 0`; `inter_sample_peak_dbtp ≈ 20*log10(1.05) ≈ 0.42 dB` (±0.1 dB, same flat-passband tolerance as TC-010); `severity == "minor"` (per `_severity`'s own logic: `fraction_clipped==0.0` but `has_inter_sample_over` is `True`, so the "none" branch is skipped and the minor-fraction bucket is taken).
- **Derivation**: amplitude 1.05 at the exact `sr/4` inter-sample-overshoot construction pushes the *continuous* peak to `1.05` (above full scale) while every *sampled* value stays at `1.05/sqrt(2) ≈ 0.742` (comfortably under the clip threshold) — a clean, real "true-peak over, no visible sample clip" case, exactly the scenario the true-peak/clipping distinction exists to catch.

### TC-014 — DC offset shifts sample peak by exactly the offset amount (edge case)
- **Covers**: edge-case checklist item "DC offset present"
- **Type**: audio-quality (ground-truth), edge case
- **Preconditions**: mono 100 Hz sine, amplitude 0.3, plus constant DC offset `+0.5` added to every sample (peak now `0.8`), 2-3 s.
- **Steps**: compute sample peak dBFS.
- **Expected result**: `sample_peak_dbfs == pytest.approx(20*log10(0.8), abs=0.01)` = `-1.938 dBFS`.
- **Derivation**: pure arithmetic — `max(sine + dc) = amplitude + dc = 0.3 + 0.5 = 0.8` by construction; no measurement uncertainty involved.

---

## 3. Clipping — AC1 (`detect_clipping`), `test_ground_truth_true_peak.py` or a dedicated file

### TC-016 — Exact clipped-sample count from a known-K contiguous run
- **Covers**: AC1 (`detect_clipping` ground-truth coverage — not otherwise named by an AC6-style story.md bullet, but required for AC1's "every public measurement function" claim)
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: mono -20 dBFS 1 kHz sine, 3 s, with exactly `K=50` consecutive samples (indices `[1000:1050]`) overwritten to exactly `1.0`.
- **Steps**: `detect_clipping(audio, sr, config)`.
- **Expected result**: `sample_peak_clipped_count == 50` exactly; `sample_peak_clip_events == 1` exactly.
- **Derivation**: `clip_sample_threshold = 0.999`; the background -20 dBFS sine (amplitude ≈0.1) never approaches this threshold, so every one of the 50 forced full-scale samples — and only those 50 — is counted, and since they are contiguous, `_count_clip_events` (a single run → one boundary crossing) returns exactly 1.

### TC-017 — Clip-event grouping distinguishes one run from K isolated spikes
- **Covers**: AC1 (`detect_clipping`, event-grouping logic specifically — distinct from the count logic TC-016 already exercises)
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: same base sine as TC-016, but 50 samples set to `1.0` at 50 widely-spaced, non-adjacent indices (e.g. every 500th sample) instead of one contiguous run.
- **Steps**: `detect_clipping(audio, sr, config)`.
- **Expected result**: `sample_peak_clipped_count == 50` (same as TC-016 — count logic is unaffected by arrangement); `sample_peak_clip_events == 50` (each isolated sample is its own contiguous run of length 1).
- **Derivation**: `_count_clip_events` counts contiguous `True` runs in the boolean clip mask — 50 isolated `True` samples with `False` gaps between every one of them is, by definition, 50 separate runs.

### TC-018 — Negative control: clean signal reports zero clips, zero events, severity "none"
- **Covers**: AC1 (`detect_clipping`), negative control
- **Type**: audio-quality (ground-truth), negative control
- **Preconditions**: plain -20 dBFS 1 kHz sine, no modification, 3 s, stereo.
- **Steps**: `detect_clipping(audio, sr, config)`.
- **Expected result**: `sample_peak_clipped_count == 0`, `sample_peak_clip_events == 0`, `inter_sample_over_count == 0` (peak well inside the FIR's flat region, no overshoot), `severity == "none"`.
- **Derivation**: a -20 dBFS sine's sample values (≈±0.1) and reconstructed inter-sample peak are both far below any clip-relevant threshold — this is the baseline every clipping test above must be contrasted against; a detector that always reports clipping (or never distinguishes clean audio) would be caught here.

### TC-019 — Stereo linking: a clip on either channel counts
- **Covers**: AC1 (`detect_clipping`, `flat = np.max(np.abs(audio), axis=1)` linking logic), edge case (stereo-specific behavior)
- **Type**: audio-quality (ground-truth), edge case, **new**
- **Preconditions**: stereo signal, left channel = clean -20 dBFS sine (as TC-018), right channel = same sine with 20 samples forced to `1.0`.
- **Steps**: `detect_clipping(audio, sr, config)`.
- **Expected result**: `sample_peak_clipped_count == 20` (linked across channels — a right-channel-only clip is still counted, not silently missed because the left channel is clean).
- **Derivation**: `detect_clipping`'s own linking logic takes `max(|L|, |R|)` per sample before thresholding — this is a direct read of the shipped code, and the expected count follows exactly from the 20 forced samples on one channel.

---

## 4. HF extension / rolloff — AC6, `test_ground_truth_hf_extension.py` (DEF-201's defect surface)

**Every test in this section uses `ref_config(hf_min_duration_s=2.0)`**
(architecture.md §1.3/§7.3) so that 2-5 s fixtures reach the real scan
path instead of the `insufficient_duration` fallback. **Expected-fail-
then-pass status is stated explicitly per test case** — do not infer it
from one test's outcome; per architecture.md §6, only AC6d (TC-024) is
the designated DEF-201 failing-test-first case. **TC-023 (below)
additionally probes a distinct risk from DEF-201's own false-positive
bug**: whether the deepened 40 dB threshold is itself well-calibrated
against realistic, non-infinite lossy-encoder stopband floors — this is
not proven safe merely because TC-020/TC-021/TC-024 pass, since all
three of those fixtures have an infinitely deep (silent) stopband. See
TC-023 for why.

### TC-020 — Brickwall noise at exactly 15 kHz → detected rolloff within tolerance (AC6a)
- **Covers**: AC6a
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `brickwall_lowpass_noise_mono(sr, duration_s=3.0, cutoff_hz=15000.0, seed=1, amplitude=0.3)` (architecture.md §1.2 — genuine spectral-zero brickwall via FFT-domain zeroing above cutoff, **not** `lowpassed_white_noise`), mono, `ref_config(hf_min_duration_s=2.0)`.
- **Steps**: `measure_hf_extension(audio, sr, config)`.
- **Expected result**: `rolloff_hz == pytest.approx(15000.0, abs=config.hf_rolloff_test_tolerance_hz)` (500 Hz), `stable is True`.
- **Derivation**: a true brickwall (spectral-domain rectangular cutoff, zero energy above `cutoff_hz`) has a threshold-crossing frequency that is **independent of how deep the threshold is** — both a 6 dB and a 40 dB crossing sit at `cutoff_hz` to within a few Welch-PSD leakage bins (a few Hz at these fixture lengths — negligible against the 500 Hz tolerance). Only a finite-slope filter's crossing frequency moves with the threshold (architecture.md §2.5).
- **Pre-/post-fix status**: **expected to PASS both before and after the DEF-201 threshold fix** (`hf_rolloff_threshold_db` 6.0 or 40.0) — this is *not* the defect's regression fixture; do not read an early pass here as evidence the fix has landed.

### TC-021 — Brickwall noise at exactly 8 kHz → detected rolloff within tolerance (AC6b)
- **Covers**: AC6b
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: same construction as TC-020, `cutoff_hz=8000.0`.
- **Steps/Expected/Derivation**: identical to TC-020, target `8000.0 ± 500` Hz.
- **Pre-/post-fix status**: same as TC-020 — passes both before and after the fix.

### TC-022 — Full-band white noise (no cutoff) → reported rolloff is near-Nyquist, not mid-band (AC6c, negative control)
- **Covers**: AC6c
- **Type**: audio-quality (ground-truth), negative control, **new**
- **Preconditions**: `white_noise_mono(sr, duration_s=3.0, seed=1, amplitude=0.2)` (architecture.md §1.2, plain `rng.normal`), `ref_config(hf_min_duration_s=2.0)`.
- **Steps**: `measure_hf_extension(audio, sr, config)`.
- **Expected result**: `rolloff_hz >= 0.9 * (sr/2)` AND `insufficient_duration is False`.
- **Derivation**: white noise's expected spectral density is flat by definition; with the scan logic unchanged (architecture.md §2.3), the loop's first iteration from the top of the spectrum already satisfies the "still above threshold" condition once the threshold is deep enough, so it returns a near-Nyquist frequency immediately — no new sentinel/enum value is needed.
- **Pre-/post-fix status**: **not the designated DEF-201 failing-test-first fixture** (architecture.md §6 names only AC6d/pink noise for that role). White noise's flat expected density means it is *likely* to pass even under the old 6.0 dB threshold most of the time, but this is not guaranteed by construction (a single-Welch-average realization can show several dB of statistical variance near the top of the band) — run this once against unmodified code and record the actual outcome; if it also fails pre-fix, that is a useful additional finding but is not required by AC6/AC11 the way AC6d's failure is.

### TC-023 — Finite (non-silent) stopband floor ~27 dB below reference: does the deepened 40 dB threshold still catch a realistic lossy-encoder cutoff?
- **Covers**: AC6 (extends AC6a/AC6b's coverage to a case they structurally cannot probe — see "why the existing brickwall fixtures do not already cover this" below); STORY-002 AC5 (lossy-source HF-cutoff detection, which the reference-analysis pipeline depends on `measure_hf_extension` to serve) — directly at risk if the DEF-201 fix's threshold depth is miscalibrated in the direction opposite DEF-201's own bug.
- **Type**: audio-quality (ground-truth, exact-by-construction floor depth), **new — added after this document's first draft, in response to a specific gap identified in review. Not present in architecture.md §7.3, which specifies only true-brickwall (infinite-floor) fixtures for AC6a/AC6b/AC6e.**
- **Why the existing brickwall fixtures (TC-020/TC-021) do not already cover this**: `brickwall_lowpass_noise_mono` zeroes the FFT spectrum above `cutoff_hz` exactly — its stopband floor is not merely deep, it is exactly silent (`-inf` dB relative) above cutoff. Against a threshold of *any* finite depth — 6 dB or 40 dB — an infinitely-deep stopband crosses below threshold at the very first bin past the cutoff edge, so TC-020/TC-021 prove only that the detector finds a genuinely-silent-above-cutoff edge. They cannot distinguish "the 40 dB threshold is deep enough to avoid DEF-201's false positive on tilted material" from "the 40 dB threshold is now so deep it introduces a false *negative* on real, finite-floor lossy-encoder material" — a real MP3/AAC anti-aliasing filter's stopband is commonly only ~20-40 dB down, not silent. This test closes exactly that gap with a fixture whose stopband floor sits at a known, finite, shallower depth.
- **Preconditions**: a new generator, `brickwall_lowpass_noise_with_floor_mono(sr, duration_s, cutoff_hz, floor_below_db, seed=0, passband_sigma=0.15)`, constructed as:
  1. `passband` = independent white noise `rng.normal(0.0, passband_sigma, n)`, brickwall-filtered in the frequency domain to `[0, cutoff_hz]` (same FFT-zero-above-cutoff method as `brickwall_lowpass_noise_mono` — **but without that generator's post-filter peak renormalization**: this fixture is sigma-controlled throughout, not peak-controlled, specifically so the dB ratio derived below is exact and not disturbed by an arbitrary post-hoc rescale).
  2. `floor` = an independent (different seed), **unfiltered, full-band** white noise `rng.normal(0.0, floor_sigma, n)` — present above `cutoff_hz` as well as below it, unlike every other HF-extension fixture in this suite.
  3. `audio = passband + floor`.
  4. `floor_sigma = passband_sigma * 10 ** (-floor_below_db / 20.0)`.
  Use `cutoff_hz=16000.0`, `floor_below_db=27.0` (mid of the 25-30 dB range specified as realistic for a mid-quality lossy encoder), `passband_sigma=0.15` (→ `floor_sigma ≈ 0.15 * 0.04467 ≈ 0.0067`), `duration_s=3.0`, `ref_config(hf_min_duration_s=2.0)`.
- **Derivation of the exact floor depth (by construction, not measured)**: for white noise `rng.normal(0, sigma, n)`, the single-sided power spectral density is flat at `sigma**2 / (sr/2)` across `[0, sr/2]` (Parseval: total variance `sigma**2` spread uniformly over bandwidth `sr/2`). Brickwall-filtering in the frequency domain (zeroing bins above `cutoff_hz`, leaving the rest untouched) does not change the density level of the bins it keeps — it only zeroes the others. So:
  - **Passband** (`f < cutoff_hz`): density = `passband_sigma**2/(sr/2)` (from `passband`) `+ floor_sigma**2/(sr/2)` (from `floor`, present everywhere) `≈ passband_sigma**2/(sr/2)` to within `10*log10(1 + 10**(-27/10)) ≈ 0.009 dB` — stated explicitly as a correction rather than silently ignored, and negligible against the 500 Hz/dB tolerances used elsewhere in this section.
  - **Stopband** (`f > cutoff_hz`): density = `floor_sigma**2/(sr/2)` exactly (`passband` is exactly zero here by the brickwall construction — not attenuated, zero).
  - Ratio: `10*log10(density_stopband/density_passband) = 20*log10(floor_sigma/passband_sigma) = -floor_below_db` exactly, by the `floor_sigma` formula above. **The stopband floor sits `27.0 dB` below the passband/reference-band density, by construction, not by measurement.**
- **Steps**: `measure_hf_extension(audio, sr, ref_config(hf_min_duration_s=2.0))`.
- **Expected result**: `rolloff_hz == pytest.approx(16000.0, abs=config.hf_rolloff_test_tolerance_hz)` (500 Hz) — the detector should still find the real cutoff despite the shallower, non-silent floor.
- **Analytically predicted outcome, stated as a function of whatever `hf_rolloff_threshold_db` the config carries at run time — not hardcoded to any one value, since this fixture's entire purpose is to test whether a given threshold depth is well-calibrated against a realistic (non-infinite) stopband floor**: per architecture.md §2.1/§2.3's own documented scan algorithm (scan down from Nyquist; report the first bin whose density is still within `threshold_level_db` of the reference-band density), this fixture's stopband floor is flat and sits at a fixed, known `-27 dB` relative to the passband/reference density (by construction, per the derivation above). The scan's outcome is therefore a direct function of how the configured `hf_rolloff_threshold_db` compares to that fixed `27.0 dB` floor depth:
  - If `hf_rolloff_threshold_db >= 27.0` (the configured threshold line sits at or below the floor's own depth — i.e. the threshold is *deeper than or equal to* the floor), the flat `-27 dB` floor never drops below the threshold line anywhere in the stopband, all the way to Nyquist. The scan's very first (highest-frequency) bin therefore already satisfies "still above threshold," and the documented algorithm returns a near-Nyquist frequency immediately. **This test is analytically predicted to FAIL** in this regime — reporting `rolloff_hz` near Nyquist instead of near `16000 Hz`.
  - If `hf_rolloff_threshold_db < 27.0` (the configured threshold is *shallower* than the floor), the floor's `-27 dB` reading exceeds (drops below) the threshold line as soon as the scan enters the stopband at the real cutoff edge, so the scan crosses there. **This test is analytically predicted to PASS** in this regime — reporting `rolloff_hz ≈ 16000 Hz`.
  - As of this document's Section 0, the shipped `hf_rolloff_threshold_db` is still `6.0` (DEF-201 unfixed) — `6.0 < 27.0`, so **at the current actual configured value, this test is predicted to PASS**. The FAIL regime above only becomes live once a DEF-201 fix lands at a threshold depth `>= 27.0` dB — the originally-proposed `40.0` would trigger it; software-architect's revised figure (previously `40.0`, now trending toward `20.0` per this same test's own finding — `20.0 < 27.0`, still predicted PASS — as of this pass, still under review) would not. This is exactly why the test must assert against the configured value at run time rather than a hardcoded number: its own pass/fail outcome is the calibration signal the architect needs, and hardcoding either 6.0 or 40.0 into this prediction would make the prediction stale the moment the config changes (this correction itself is recorded in `stories/STORY-002/defects.md` DEF-207 item 3, which found an earlier draft of this paragraph hardcoded `40.0` while this document's own Section 0 stated the shipped value was still `6.0` — two mutually exclusive claims in the same document).
- **Steps (continued)**: run this test as written, against whatever `hf_rolloff_threshold_db` is actually configured at run time, and record the actual result together with the configured value used.
- **Explicit instruction, per the reason this test exists — do not silently narrow the fixture to force a pass, and do not silently pick a config value to test against**: if a *future* DEF-201 fix value at or above `27.0` dB makes this test fail (reporting `rolloff_hz` near Nyquist instead of near `16000 Hz`), that is direct, concrete evidence that the chosen depth — while deep enough to eliminate DEF-201's false positive on tilted/pink-noise material (TC-024) — is too deep to catch a real lossy-encoder cutoff whose stopband floor is shallower than that depth below reference. That would mean the fix trades one defect (false-positive cutoff detection on ordinary tilted material) for another (false-negative cutoff detection on genuinely-transcoded material), directly undermining STORY-002 AC5's lossy-source-detection purpose. **Route this finding back to the architect** — a threshold retuned to sit below this fixture's `27.0` dB floor (e.g. DEF-201's originally-proposed range, or the revised `20.0` figure currently under review), or a corroborating mechanism such as the existing `_transcode_slope_check` secondary check, are both plausible responses; this test does not prescribe which. **Deepening `floor_below_db` beyond whatever threshold depth is configured, purely to force a pass, would defeat the entire purpose of this test and must not be done.**
- **If the actual result disagrees with the prediction above for the configured value in use**: also worth recording, not silently accepted — it would mean either Welch-PSD averaging noise pushed some stopband estimate across the threshold line by chance (re-run with a different seed to check robustness before trusting the result) or the scan algorithm's actual behavior differs from architecture.md §2.1/§2.3's documented description in some way this derivation did not anticipate — either outcome is itself a finding worth a follow-up note, not something to accept silently.

### TC-024 — Pink noise with no cutoff → reported rolloff is near-Nyquist (AC6d, the literal DEF-201 regression fixture)
- **Covers**: AC6d
- **Type**: audio-quality (ground-truth), negative control, **the DEF-201 regression guard**
- **Preconditions**: `pink_noise_mono(sr, duration_s=3.0, seed=1)` (existing `ref_helpers.py` function, reused as-is), `ref_config(hf_min_duration_s=2.0)`.
- **Steps**: `measure_hf_extension(audio, sr, config)`.
- **Expected result**: `rolloff_hz >= 0.9 * (sr/2)` (same assertion shape as AC6c).
- **Derivation**: pink noise has a naturally declining (-3 dB/octave) spectrum by construction, but this decline is a smooth tilt, not a cutoff — a correct detector must not mistake ordinary spectral tilt for a real high-frequency rolloff. This is exactly DEF-201's defect surface: a shallow threshold (6 dB) crosses within the first octave or two above the reference band on any material with ordinary tilt, reporting a false mid-band "cutoff."
- **Pre-/post-fix status — REQUIRED sequencing (architecture.md §6, AC6, AC11)**:
  1. Run this test against the **unmodified** code (`hf_rolloff_threshold_db=6.0`). **Expected: FAILS.** Record in `stories/STORY-002/defects.md`'s DEF-201 entry the exact test name (`test_ground_truth_hf_extension.py::test_ac6d_pink_noise_no_cutoff`), the failing assertion, and the actual numeric `rolloff_hz` value returned versus the `>= 0.9*(sr/2)` expectation — **do not assume or copy architecture.md's illustrative "~2143 Hz" example figure; that was explicitly stated as an "e.g." placeholder, not a predicted value. Record whatever the real run actually reports.**
  2. Apply the DEF-201 fix (`hf_rolloff_threshold_db: float = 6.0` → `40.0` in `reference_analysis/config.py`).
  3. Re-run. **Expected: PASSES.** Record the post-fix `rolloff_hz` value in the same defects.md entry.
  4. Mark DEF-201 **Fixed** in defects.md per the existing DEF-101/DEF-103 fix-notes format.
- **Status note (DEF-201 was subsequently reopened — see the new section immediately after TC-029, below)**: the sequence above is the historical record of the *first* DEF-201 pass, which landed at `hf_rolloff_threshold_db=20.0` (not the `40.0` this test case's step 2 originally named — see architecture.md §2.2's own v2 correction) and closed DEF-201. That fix has since been **reopened** — real reference-track evidence shows it changed the numbers but not the (still threshold-based) method, and TC-024 as written here continues to pass at the current shipped `20.0` value. **This is not a contradiction**: TC-024 remains a correct, valid negative control for "ordinary tilt alone, with no real cutoff anywhere, must not be misreported as a cutoff" — and it correctly continues to hold. It was never designed to test, and structurally cannot test, whether the detector still finds a **real** cutoff correctly when tilt is *also* present below it — that is a different property, covered by the new TC-090/TC-091, not by this test. Do not read TC-024's continued pass as evidence the reopened defect is unfounded, and do not read it as evidence this test is "not wired to the function that produced the real reference-set measurements" (a possibility the reopening explicitly asked to be checked) — it is wired correctly; its fixture simply never contained a real cutoff to get wrong in the first place.

### TC-025 — Drift detection fires when cutoff changes partway through (AC6e)
- **Covers**: AC6e
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `brickwall_lowpass_noise_with_drift(sr, first_s=2.0, second_s=2.0, cutoff1_hz=15000.0, cutoff2_hz=8000.0, seed=1, amplitude=0.3)` (4 s total; `hf_stability_segment_count=5` default gives 5 segments of ~0.8 s each — segments 1-2 fall in the first half, segments 4-5 in the second, segment 3 straddles the transition), `ref_config(hf_min_duration_s=2.0)`.
- **Steps**: `measure_hf_extension(audio, sr, config)`.
- **Expected result**: `stable is False`; `rolloff_hz is not None` (median still reported, not withheld).
- **Derivation**: per-segment rolloff estimates split ~15000 Hz / ~8000 Hz; the spread (~7000 Hz) comfortably exceeds `hf_stability_tolerance_hz=2000`, so the stability flag must trip. Matches the existing `test_tc308`'s assertion pattern for the same scenario.
- **Pre-/post-fix status**: unaffected by the threshold depth (brickwall edges are threshold-independent per TC-020's derivation) — expected to pass both before and after the DEF-201 fix.

### TC-026 — Migration regression: `test_tc304` (16 kHz) must be re-fixtured, not left on `lowpassed_white_noise`
- **Covers**: DEF-201 blast-radius (architecture.md §2.5), regression guard
- **Type**: regression, **required action, not merely observational**
- **Preconditions**: existing `test_tc304` in `test_ref_ac10_verification_bars.py`, currently built on `lowpassed_white_noise(sr, ..., cutoff_hz=16000.0, ...)` (a Butterworth+`sosfiltfilt` filter, finite slope).
- **Steps**: (a) confirm that, if left unmodified, re-running `test_tc304` after the DEF-201 fix reports `rolloff_hz ≈ 21,340 Hz` against an expected `16000 ± 500 Hz` — i.e. it **fails**. (b) re-fixture `test_tc304` onto `brickwall_lowpass_noise_mono(sr, ..., cutoff_hz=16000.0, ...)`, keeping the existing expected value (`16000.0`) and tolerance (`500.0 Hz`) unchanged.
- **Expected result**: (a) confirms the fail (this is the "why re-fixturing is required" evidence, not optional cleanup). (b) after re-fixturing, `test_tc304` passes with the same tolerance.
- **Derivation**: `sosfiltfilt`'s composite (forward+backward) attenuation in the deep stopband is approximately `A(f) ≈ 320*log10(f/fc)` for this fixture's order-8 Butterworth; solving `A=40` gives `f = fc * 10^(40/320) = fc * 1.334 ≈ 21,340 Hz` for `fc=16000` — a finite-slope filter's threshold-crossing frequency genuinely moves when the threshold moves (architecture.md §2.5's own worked correction). A brickwall's does not (TC-020's derivation).

### TC-027 — Migration regression: `test_tc305` (12 kHz), same requirement
- **Covers**: DEF-201 blast-radius, regression guard
- **Type**: regression, required action
- **Preconditions/Steps/Expected/Derivation**: identical structure to TC-026, `cutoff_hz=12000.0`; pre-migration failure lands at `≈16,010 Hz` (`12000 * 1.334`) against `12000 ± 500`; post-migration (onto `brickwall_lowpass_noise_mono`) passes.

### TC-028 — Confirmed unaffected: `test_tc307`/`test_tc308` need no re-fixturing
- **Covers**: DEF-201 blast-radius due-diligence, negative control (confirms the fix's blast radius is bounded, not "everything HF-related breaks")
- **Type**: regression, verification-only
- **Steps**: re-run `test_tc307` (asserts only `insufficient_duration`, no specific `rolloff_hz`) and `test_tc308` (asserts `stable is False` from an 8000 Hz spread that still comfortably exceeds `hf_stability_tolerance_hz=2000` even after the threshold-shift math) after the DEF-201 fix.
- **Expected result**: both continue to pass, unmodified.

### TC-029 — `suspected_transcode` newly firing on real reference tracks post-fix is an expected output change, not a regression
- **Covers**: DEF-201 blast-radius (architecture.md §2.5, item 2)
- **Type**: regression (documentation/expectation-setting test case, not a numeric assertion)
- **Preconditions**: the project's real five-track reference set (if available in this environment), run through `analyze_track` before and after the DEF-201 fix.
- **Steps**: compare `suspected_transcode` flags pre- vs. post-fix for lossy (MP3) reference tracks.
- **Expected result**: some previously-`False` flags may become `True` for tracks whose true rolloff lands inside a `transcode_suspect_bands_hz` window (15.5-16.5 / 18.5-19.5 / 19.5-20.5 kHz) now that the underlying `rolloff_hz` is meaningful. **QA must treat this as the fix working correctly, not as a newly-introduced defect** — under the old 6.0 dB threshold, `rolloff_hz` reported low-mid-band values that never fell inside any suspect-band window, so `suspected_transcode` was very likely never `True` regardless of the actual source material.
- **Note**: grep `tests/` for `rolloff_hz` and `suspected_transcode` beyond the files named above and re-run every hit, per architecture.md §2.5's explicit due-diligence instruction; also re-run the full `test_ref_*.py` suite (§2.5, §6 step 5).

---

## 4.1 DEF-201 REOPENED — coverage-gap note and two new ground-truth test cases

`stories/STORY-002/defects.md`'s DEF-201 entry was **reopened** (status
changed from Closed back to Open; james, review of
`Reference Tracks/reference_set_report.md`) after the already-landed
first fix (`hf_rolloff_threshold_db` 6.0 → 20.0 — TC-020 through TC-029
above, all still accurate as the historical record of *that* fix) was
found to have changed the numbers but not the method: it is still a
fixed-dB-threshold-below-a-mid-band-reference detector, and real
reference tracks now report implausible, universally-unstable rolloffs
(e.g. `Leftfield_-_Melt_Audio.wav`, a 1995 CD master, reporting
8170 Hz). The reopened entry requires four ground-truth test cases,
checked against what already exists in this document before any
slope-based redesign lands:

1. **Full-band pink noise, no cutoff → NO CUTOFF.** Already covered by
   **TC-024** above (AC6d). TC-024 continues to pass at the current
   `hf_rolloff_threshold_db=20.0` (per the threshold-sweep evidence
   recorded in architecture.md §2.2/§2.5) — **this is not a
   contradiction of the reopening, and it is not evidence TC-024 is
   unwired to the function under test.** This is the single most
   important thing to get right about this gap, so it is stated
   plainly: TC-024's own fixture (`pink_noise_mono`, 1/√f amplitude
   shaping → a −3.01 dB/octave density decline) has **no real cutoff
   anywhere in it** — its only job is confirming that ordinary tilt
   alone does not falsely trigger a cutoff report, and it correctly
   does not. It is structurally incapable of testing the different,
   now-confirmed-real failure mode the reopening describes: whether the
   detector still finds a **real** cutoff correctly when natural tilt
   is *also* present below it. Those are two different properties
   requiring two different fixtures; TC-024 was always the negative
   control (no cutoff anywhere → none should be found), never the
   positive analogue (a real cutoff, buried under tilt, should still be
   found). See TC-090 below for that missing positive case, including a
   worked derivation of exactly why TC-024's own −3.01 dB/octave tilt is
   analytically too shallow, at the currently shipped threshold depth,
   to have ever reproduced this bug even if it had been built with a
   cutoff in it.
2. **White noise brickwalled at 15 kHz → ~15 kHz.** Already covered by
   **TC-020** above (AC6a). Unaffected by the reopening — a true
   spectral-zero brickwall's threshold-crossing frequency is
   independent of both the threshold depth and the pre-cutoff spectral
   shape (flat/white, in TC-020's case), so this remains a valid,
   passing ground-truth case regardless of which detection method is
   eventually shipped.
3. **White noise brickwalled at 8 kHz → ~8 kHz.** Already covered by
   **TC-021** above (AC6b). Same reasoning as item 2.
4. **Pink noise brickwalled at 15 kHz → ~15 kHz — genuinely new.** Not
   present anywhere in this document before this revision. See
   **TC-090** below.

**Beyond the four**, per the coordinating instruction that motivated
this revision: **TC-091** below adds a second, closely related fixture
that exercises the actual segmented, silence-gated code path
(`silence.extract_active_audio` feeding `measure_hf_extension`'s
per-segment loop) at a real-track-scale duration, rather than a short,
continuous, never-gated 2-5 s buffer.

**A correction to how this second gap was originally framed, found by
reading the shipped code directly rather than accepting the framing as
given** (`stories/STORY-001/implementation/suno_mastering/analysis/
hf_extension.py::measure_hf_extension`): the "single-segment fallback"
this gap was originally described against (`n_segments` reduced to `1`
when `active.size // hf_stability_segment_count < 8` samples) does
**not** actually apply to TC-020/TC-021/TC-024/TC-025's existing 3-4 s
fixtures — at 44.1 kHz, `active.size // 5` for a 3 s buffer is
~26,460 samples, far above the 8-sample fallback floor, so those tests
already exercise the `n_segments == 5` branch and always have. **The
literal "these fixtures only ever hit the n_segments==1 branch" framing
does not hold against the shipped code, and this document does not
repeat it as fact.**

The real, confirmed gap is narrower but still genuine: every existing
HF-extension fixture in this document (TC-020 through TC-029) is a
single continuous span of never-near-silent audio, so
`extract_active_audio`'s block gate is `True` for every 400 ms block
and removes nothing — `active` is bit-identical to the input, and each
of the 5 segments is a plain contiguous 1/5th slice of one unbroken
signal. Real reference tracks' active audio is instead a
**concatenation of several non-contiguous spans**, with quiet
intro/breakdown/outro material actually removed by the gate, at
durations (minutes, not seconds) that give each segment vastly more
Welch averages than the "1-2 Welch averages per segment" architecture.md
§2.2/§2.7 flags for this story's short synthetic fixtures, plus genuine
splice discontinuities between the concatenated spans. No existing
fixture in this document (including TC-090) exercises either of those
two properties. TC-091 closes that specific, verified gap — it is not
a duplicate of TC-090.

### TC-090 — Pink noise with a real cutoff at 15 kHz (steep tilt + brickwall) → detector must find the cliff, not the tilt (AC6, DEF-201 REOPENED, item 4 — genuinely new)
- **Covers**: AC6 (extends AC6a/AC6d's coverage to the combination neither one tests alone); `stories/STORY-002/defects.md` DEF-201 REOPENED, required case 4 ("Pink noise brickwalled at 15 kHz -> ~15 kHz (declining spectrum AND a real cutoff -- must find the cutoff, not the tilt)").
- **Type**: audio-quality (ground-truth, exact by construction) — **written to demonstrate a currently-real failure; expected to FAIL against the shipped pre-redesign detector.** Do not write or read this as if the slope-based redesign has already landed. A pass here, before the redesign ships, would itself be a finding worth investigating (see the last bullet below), not a result to accept quietly.
- **Preconditions**: a new generator, `pink_brickwall_lowpass_noise_mono(sr, duration_s, cutoff_hz, tilt_exponent=2.0, seed=0, amplitude=0.3)`, constructed as: (1) generate white noise `rng.normal(0,1,n)`; (2) `spectrum = rfft(white)`, `freqs = rfftfreq(n, 1/sr)`; (3) scale the amplitude spectrum by `freqs ** (-tilt_exponent/2)` for `freqs>0` (leave the DC bin unscaled) — this produces a power spectral density `S(f) ∝ f^-tilt_exponent`, i.e. a `10*log10(2**tilt_exponent)` dB/octave decline; (4) zero every bin with `freqs > cutoff_hz` (identical brickwall step to the existing `brickwall_lowpass_noise_mono`); (5) `irfft`, then normalize peak amplitude the same way the existing generators do. Use `sr=44100`, `duration_s=3.0`, `cutoff_hz=15000.0`, `tilt_exponent=2.0`, `seed=90`, `amplitude=0.3`, `ref_config(hf_min_duration_s=2.0)` (the established override pattern used by every other test in this section).
- **Why `tilt_exponent=2.0` (a −6.02 dB/octave density decline), not `1.0` (−3.01 dB/octave, the existing `pink_noise_mono`/TC-024 shaping)**: chosen at the steep end of the "~-3 to -6 dB/octave" natural-tilt range the reopened defect itself cites (`stories/STORY-002/defects.md`, DEF-201 REOPENED, evidence item 3: "Programme material has a naturally declining spectrum (~-3 to -6 dB/octave)") — not an arbitrary parameter. **This choice is load-bearing, not decorative**, worked out below: `tilt_exponent=1.0` analytically does **not** reproduce a failure at the currently shipped threshold depth, which is exactly why simply reusing the existing `pink_noise_mono` shape combined with a brickwall would not have demonstrated this bug, and is the concrete answer to "why didn't TC-024 catch this."
- **Derivation of the ground-truth expected value (independent of tilt, by construction)**: the signal's true spectral content is exactly zero above `15000.0 Hz` (construction step 4) and nonzero (declining but present) below it — the identical "zeroed above cutoff" construction `brickwall_lowpass_noise_mono` already uses for TC-020/TC-021, and TC-020's own derivation (a genuine spectral-zero edge's threshold-crossing frequency is independent of both the absolute threshold depth *and* the pre-cutoff spectral shape) applies unchanged here regardless of what the tilt below cutoff looks like. **Ground truth: `rolloff_hz == pytest.approx(15000.0, abs=config.hf_rolloff_test_tolerance_hz)`** (500 Hz) — this is what any correct detector, threshold-based or slope-based, must report.
- **Derivation of the analytically-predicted actual (wrong) result against the shipped scan algorithm** — read directly from `analysis/hf_extension.py::_segment_rolloff_hz` (`threshold_level_db = ref_density_db - config.hf_rolloff_threshold_db`, reference band `freq_reference_band_hz = (500, 2000)`; `_psd.band_mean_density` = a plain arithmetic mean of Welch PSD bin values over the band, confirmed by reading `_psd.py` directly — bin spacing at this fixture's length is a fraction of a Hz, far finer than the 1500 Hz reference band, so the arithmetic mean closely approximates the continuous average used below):
  - For `S(f) = C·f^-2` (this fixture's `tilt_exponent=2.0` construction), the reference-band mean density is `mean_ref = C·(1/(f2-f1))·∫_{500}^{2000} f^-2 df = C·(1/f1 - 1/f2)/(f2-f1) = C/(f1·f2) = C/(500·2000) = C·10^-6`.
  - The scan reports the highest frequency `f` (scanning down from Nyquist) where `S(f) ≥ mean_ref · 10^(-hf_rolloff_threshold_db/10)`. Solving `C·f_cross^-2 = C·10^-6·10^(-threshold/10)` for the crossing frequency gives `f_cross = sqrt(500·2000·10^(threshold/10)) = 1000·10^(threshold/20)`.
  - At the **currently shipped** `hf_rolloff_threshold_db = 20.0` (`reference_analysis/config.py` line 52 — confirmed by direct read; this is the value the *first*, now-reopened DEF-201 fix landed at, not the pre-DEF-201 `6.0`, and not a hypothetical future redesign value): `f_cross = 1000·10^(20/20) = 10,000 Hz` — **exactly, by this construction** — comfortably below the true `15,000 Hz` cutoff and well outside the `500 Hz` tolerance around it.
  - **Cross-check showing why `tilt_exponent=1.0` (plain pink, TC-024's own shaping) would not have caught this**: repeating the same derivation for `S(f) = C·f^-1` gives `mean_ref = C·(1/1500)·ln(2000/500) ≈ C·9.242×10^-4`, and the relative density at `f=15000` works out to `10·log10((C/15000)/(9.242×10^-4·C)) ≈ -11.42 dB` — **above** (less negative than) the `-20 dB` threshold line, so a plain-pink-shaped brickwall at 15 kHz would still be found correctly at the currently shipped threshold depth. This is exactly why this test case requires a distinct, steeper-tilt generator rather than reusing `pink_noise_mono`, and it is the concrete, worked answer to "why didn't the existing pink-noise ground-truth test (TC-024) catch the real-world bug": TC-024's tilt is real but analytically too shallow, at this reference-band/threshold combination, to move the crossing point below any real high-frequency cutoff a commercial master would plausibly have.
- **Steps**: `measure_hf_extension(pink_brickwall_lowpass_noise_mono(44100, 3.0, 15000.0, tilt_exponent=2.0, seed=90, amplitude=0.3), 44100, ref_config(hf_min_duration_s=2.0))`.
- **Expected result — stated as a required failure, not a normal pass/fail**: the ground-truth assertion `rolloff_hz == pytest.approx(15000.0, abs=500.0)` is expected to **FAIL** against the current, unmodified, pre-redesign shipped code, with the run analytically predicted to report approximately `10,000 Hz` instead. **Run this once against the unmodified code and record the actual `rolloff_hz`/`stable` values in `stories/STORY-002/defects.md`'s DEF-201 (REOPENED) entry** — per this document's own established AC6/AC11 discipline (the same sequence TC-024 originally used for the first DEF-201 pass). **Do not assume the analytically predicted `~10,000 Hz` is what the real run reports; record the actual number.** If the actual result disagrees with the `~10,000 Hz` prediction by more than a small margin, that is itself a finding worth recording explicitly (either the `band_mean_density` averaging assumption above needs revisiting, or the scan's median-filter smoothing step interacts with this construction in a way this derivation did not anticipate) — not something to silently reconcile.
- **Explicit instruction, matching this document's existing TC-023/TC-024 discipline**: do not narrow the tilt, shift the cutoff, or loosen the tolerance to force this test to pass before the redesign lands.

### TC-091 — Same construction, exercised through the real segmented + silence-gated pipeline at real-track-scale duration (AC6, DEF-201 REOPENED — closes the "did the ground-truth suite even exercise this code path" gap, per the reopened entry's own explicit request to investigate this)
- **Covers**: AC6 (extends TC-090 to the actual multi-segment/silence-gated code path real reference-set analysis uses); `stories/STORY-002/defects.md` DEF-201 REOPENED's explicit instruction to "investigate why STORY-003's ground-truth tests did not catch this, and report that as a finding" — this test case is the concrete, reusable answer to that instruction, not just a one-off investigation note.
- **Type**: audio-quality (ground-truth, exact by construction, same derivation basis as TC-090) — **also written to FAIL against the shipped pre-redesign detector.** Not a duplicate of TC-090: TC-090 proves the *scan formula itself* mishandles tilt-plus-cutoff on a short, continuous, ungapped buffer; TC-091 proves the same failure survives contact with the actual real-pipeline code path (`silence.extract_active_audio` genuinely removing near-silent spans, and `measure_hf_extension`'s 5-way segment split running on concatenated, non-contiguous, real-track-length active audio).
- **Why this fixture is needed and not just a re-run of TC-090**: per the coverage-gap note above (§4.1), no existing HF-extension ground-truth fixture in this document — including TC-090 — ever exercises `extract_active_audio` actually removing anything (every one is one continuous, never-near-silent buffer), and none run at a duration remotely close to a real reference track's (all are 2-5 s; real tracks are minutes). Both properties are structurally different from anything any prior fixture in this document reaches, and the reopened defect's own real-world evidence (universal instability across segments, observed on actual reference tracks) was seen specifically on real, silence-gated, multi-minute material — not on anything this suite had tested before this revision.
- **Preconditions**: built from six independent, 24 s calls to `pink_brickwall_lowpass_noise_mono(44100, 24.0, 15000.0, tilt_exponent=2.0, seed=91+i, amplitude=0.3)` for `i` in `0..5` (identical construction to TC-090, only the seed differs per call — the cutoff/tilt spectral shape is exactly the same across all six spans, deliberately, to model "different sections of one track sharing one real band-limit"), interleaved with six independent 6 s near-silent blocks (`rng.normal(0, 0.0001, n)`, a different seed per block; RMS ≈ -80 dBFS, far below the shipped `silence_gate_threshold_db = -60.0` default gate), concatenated in `active, silent, active, silent, ...` order into one 180 s (3-minute, real-track-scale) mono buffer — 144 s active total, 36 s near-silent total. **Every sub-block boundary is an exact multiple of the shipped `silence_block_ms = 400 ms`** (24 s = 60 blocks, 6 s = 15 blocks), so the gate's own 400 ms block edges land exactly on this construction's splice points, leaving no ambiguous partial-block classification. `ref_config(hf_min_duration_s=2.0)` still applies (180 s already clears the default 30 s floor on its own, but kept for consistency with every other test in this section).
- **Confirms the multi-segment/silence-gated path is actually reached, not assumed** — worked through against the shipped `measure_hf_extension`/`silence.extract_active_audio` code directly: `extract_active_audio` removes every 400 ms block whose RMS is below the gate — the six near-silent 6 s spans (RMS ≈ -80 dBFS, ~20 dB under the -60 dB gate) are removed; the six 24 s active spans (RMS at `amplitude=0.3`'s level, far above the gate) are kept, concatenated into a 144 s active buffer built from six genuinely non-contiguous original spans (a real splice discontinuity — independent noise realizations either side — at five internal seams). `n_segments = max(1, config.hf_stability_segment_count) = 5`; `seg_len = active.size // 5 = (144·44100)//5 = 1,270,080` samples (≈28.8 s per segment) — comfortably above the `< 8`-sample single-segment fallback (confirming, concretely for this fixture, that the fallback the original gap description worried about is not what actually distinguishes this test from TC-090/TC-020 — the distinguishing properties are the genuine gating and the real-track-scale duration, as stated in §4.1's correction above). Because each ≈28.8 s segment is longer than any one of the six 24 s active spans, most of the 5 resegmented spans straddle at least one of the five original splice points — a property no other fixture in this document has.
- **Derivation of the ground-truth expected value**: identical to TC-090 — every active span, on both sides of every splice, is independently constructed with the same exact-zero-above-15000 Hz brickwall, so the true rolloff is `15,000 Hz` everywhere in the active signal, splices included. **Ground truth: `rolloff_hz == pytest.approx(15000.0, abs=config.hf_rolloff_test_tolerance_hz)`.**
- **Derivation of the analytically-predicted actual (wrong) per-segment result**: each segment's own local PSD is computed from material drawn from the identical `S(f) ∝ f^-2` construction as TC-090 (only the noise realization differs from segment to segment and across splices — the spectral law and the reference-band/cutoff relationship are unchanged), so TC-090's own worked derivation (`f_cross = 1000·10^(hf_rolloff_threshold_db/20) = 10,000 Hz` at the shipped `hf_rolloff_threshold_db=20.0`) applies independently to each of the 5 segments. A splice discontinuity's own broadband transient energy is negligible against a ≈28.8 s window's average power (the same reasoning TC-035 already uses for a 5 ms glitch against a much shorter 3 s LRA window — an even larger duration ratio applies here: a single-sample discontinuity contributes vanishingly little energy to a window with `welch_nperseg` capped at 65,536 samples, ≈1.49 s at 44.1 kHz), so it should not materially shift any individual segment's own rolloff estimate away from the same ≈10,000 Hz prediction. **Predicted: `median(per_segment_rolloff_hz) ≈ 10,000 Hz`, failing the `15,000 ± 500 Hz` ground-truth assertion by the same wide, unambiguous margin as TC-090.**
- **`stable` is explicitly left as an open empirical question, not asserted, unlike the `rolloff_hz` prediction above**: because every segment is analytically predicted to converge on approximately the same wrong value (~10,000 Hz), a naive reading of this derivation would predict `stable=True` (a *confidently wrong* result) — but the reopened defect's own real-world evidence shows the opposite on actual reference tracks (universal *instability*, not a stable-wrong answer). This test case does not resolve that discrepancy by assumption: it may mean real material's instability comes from genuine section-to-section spectral variation this deliberately-uniform synthetic fixture does not model, or it may mean the five splice discontinuities (or Welch-window edge effects at each 400 ms gated-block boundary) introduce more per-segment variance than the negligible-energy argument above predicts. **Record the actual `stable` value alongside `rolloff_hz` and `per_segment_rolloff_hz` when this test is run — do not assume either outcome, and do not treat a `stable=True` result as invalidating the test if `rolloff_hz` is still wrong; the ground-truth failure is on `rolloff_hz`, not on `stable`.**
- **Steps**: build the 180 s buffer as specified; `measure_hf_extension(buffer, 44100, ref_config(hf_min_duration_s=2.0))`.
- **Expected result**: `rolloff_hz == pytest.approx(15000.0, abs=500.0)` is expected to **FAIL** against the current, unmodified, pre-redesign shipped code (`hf_rolloff_threshold_db=20.0`), analytically predicted to report `rolloff_hz ≈ 10,000 Hz` (or a value in that neighborhood — run and record the exact figure, per the same discipline as TC-090). **Run this once against the unmodified code and record the actual `rolloff_hz`, `stable`, and `per_segment_rolloff_hz` values in `stories/STORY-002/defects.md`'s DEF-201 (REOPENED) entry, alongside TC-090's own recorded result** — this is the direct evidence that the tilt-vs-cutoff confusion TC-090 demonstrates on a short, continuous, ungapped buffer also survives the real segmented, silence-gated pipeline at realistic duration, which is the specific gap the coordinating instruction and the reopened defect both flag.
- **Runtime note**: 180 s mono at 44.1 kHz is ≈7.94M samples — every operation here (FFT construction, Welch/median-filter per segment) is vectorized over sample count, not wall-clock audio duration (architecture.md §1.3's own reasoning for this story's other duration-floor exceptions applies identically here); this fixture is not expected to meaningfully threaten AC12's 30 s ground-truth-suite runtime budget, but whoever implements it should still measure and report the actual wall time for this specific test, per §1.3's own instruction not to assume rather than measure.

---

## 5. Dynamic range / LRA — AC7, `test_ground_truth_dynamic_range.py`

**Fixture-length floors (architecture.md §1.3, a deliberate, derived
deviation from the story's "2-5 s" NFR for these two functions
specifically)**: `measure_dynamic_range` needs `n_blocks >= 5` to
exercise its sort/exclude/2nd-peak logic (`n_blocks==5` exactly at
`dr_block_seconds * 5 = 15 s`) — a shorter signal silently takes the
single-block crest-factor fallback instead. `measure_loudness_range`'s
AC7a (constant level) needs enough windows to be meaningful (≥5 s);
AC7b/7c's two-level case must reuse the DEF-107-calibrated 30 s + 30 s,
18 LU fixture pattern (STORY-002's `test_tc302`), not an invented
shorter separation — a naive "loud/quiet dB difference" fixture does
not discriminate a correct gate implementation from a miscopied one
(DEF-107, STORY-002 `defects.md`).

### TC-030 — Constant-level sine → dynamic range near zero (AC7a, DR)
- **Covers**: AC7a (`measure_dynamic_range`)
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: mono 1 kHz sine, constant amplitude (any level, e.g. -12 dBFS peak), **≥15 s** duration (`n_blocks==5` at the default `dr_block_seconds=3.0`), 44.1 kHz.
- **Steps**: (a) `measure_dynamic_range(audio, sr, config)` — the public, integer-rounded entry point. (b) the unrounded internal value, read via `dynamic_range._measure_dynamic_range_unrounded(audio, sr, config)` (or, in the reference-analysis path, `ReferenceMeasurements.dynamic_range_db_exact`, the one public field that exposes the unrounded figure) — **the public `measure_dynamic_range()` itself only returns the rounded integer; do not attempt to read an unrounded value from it directly.**
- **Expected result**: (a) rounded result is `0`. (b) unrounded value is within `0.1 dB` of `0.0`.
- **Derivation**: the module's own "RMS" definition rescales by `sqrt(2)` specifically to make an ideal sine's peak-to-"RMS" ratio equal 1 (`sqrt(2)*RMS_sine = sqrt(2)*(A/sqrt(2)) = A = peak`). For a constant-amplitude sine, every 3 s block has (to within negligible finite-block-boundary phase effects — order `1/(3s * f_Hz)`, far under 0.01 dB for any audio-range frequency) the same rescaled-RMS and the same peak, so both the "2nd RMS" (post-exclusion) and "2nd peak" computations converge to that same value: `DR = 20*log10(peak/rms) ≈ 0`.

### TC-031 — Very short file → DR falls back to the single-block crest-factor path, same analytic answer via a different code branch (boundary)
- **Covers**: edge-case checklist item "very short file (shorter than any analysis window)"; boundary value for `measure_dynamic_range`
- **Type**: audio-quality (ground-truth), boundary/edge case
- **Preconditions**: same constant 1 kHz sine as TC-030, but **1 s** duration (`n_blocks=0` at `dr_block_seconds=3.0` → triggers the `n_blocks < 1` fallback branch in `_channel_dr`).
- **Steps**: `measure_dynamic_range(audio, sr, config)`.
- **Expected result**: rounded result is `0`, unrounded ≈ `0.0 dB` — same numeric answer as TC-030, for the same reason (peak == rescaled-RMS for an ideal sine), but reached via the documented single-block crest-factor fallback (`rms = sqrt(2*mean(x**2))`, `peak = max(abs(x))`) rather than the sort/exclude path. This test's purpose is to confirm the fallback branch is itself correct, not merely that the two branches happen to agree at this particular signal.

### TC-032 — Constant-level sine → LRA near zero (AC7a, LRA)
- **Covers**: AC7a (`measure_loudness_range`)
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: mono 1 kHz sine, constant amplitude, ≥5 s duration.
- **Steps**: `measure_loudness_range(audio, sr, config).lra_lu`.
- **Expected result**: `lra_lu` within `0.2 LU` of `0.0` (architect-reasoned, generous tolerance — flagged as such, not a tight published figure).
- **Derivation**: K-weighted per-window mean-square power for a constant-amplitude sine is essentially identical across every full 3 s window (edge effects from window-boundary phase are of the same negligible order as TC-030's derivation), so the doubly-gated P95-P10 spread should be near-zero.

### TC-033 — Two-level signal, 18 LU separation → LRA approximates the calibrated separation under the default gate (AC7b)
- **Covers**: AC7b
- **Type**: audio-quality (ground-truth), **reuses the DEF-107-calibrated fixture**
- **Preconditions**: stereo (or mono — function accepts either) signal built from `calibrated_tone_mono(sr, 30.0, dbfs_rms=-14.0, freq=1000)` concatenated with `calibrated_tone_mono(sr, 30.0, dbfs_rms=-32.0, freq=1000)` — the exact 18 LU two-level construction STORY-002's `test_tc302` established (defects.md DEF-107).
- **Steps**: `measure_loudness_range(audio, sr, ref_config())` (default `lra_relative_gate_lu=-20.0`).
- **Expected result**: `lra_lu == pytest.approx(18.0, abs=config.lra_tolerance_lu)` (1.0 LU).
- **Derivation (per DEF-107, not re-derived here — cited, not re-guessed)**: the relative gate compares each block's loudness against the **mean of all absolute-gate-passing blocks**, not directly against either cluster's own level. An 18 LU separation was specifically chosen (over a naively-simpler 25 LU or 12 LU figure) because it sits between the correct-gate exclusion boundary (~23.01 LU) and the incorrect `-10 LU`-gate exclusion boundary (~13.01 LU) — see TC-034 for why this specific number matters, not merely that *some* two-level signal produces *some* LRA reading.

### TC-034 — Same fixture, forced incorrect `-10 LU` gate → LRA collapses (AC7b's discrimination purpose, regression guard)
- **Covers**: AC7b (the gate-discrimination half of the requirement — this is *why* 18 LU was chosen, not incidental)
- **Type**: regression guard (the single most common LRA implementation bug — miscopying the `-10 LU` integrated-loudness relative gate onto the LRA statistic, which uses a deliberately wider `-20 LU` gate)
- **Preconditions**: same fixture as TC-033.
- **Steps**: `measure_loudness_range(audio, sr, ref_config(lra_relative_gate_lu=-10.0))`.
- **Expected result**: `lra_lu` collapses toward `≈0 LU` (well below the 18 LU seen under the correct gate) — assert e.g. `lra_lu < 5.0` (architect-reasoned bound, generous; tighten empirically once run).
- **Derivation**: under the incorrect, narrower `-10 LU` gate, the quiet cluster (32 dB below the loud cluster) is excluded entirely, leaving only the loud cluster's own internal (near-zero) spread — this is TC-033/TC-034's *combined* purpose: assert both cases, not just the default-config one, since the contrast between them is the actual regression guard.

### TC-035 — LRA is measurably different from a naive whole-file peak-to-trough computation (AC7c)
- **Covers**: AC7c
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: mono, constant -20 dBFS 1 kHz sine, 30 s, with a single 5 ms full-scale (`amplitude=1.0`) glitch spliced into the array at `t=15s` (replace, not add, those samples). **Mutation-hazard note (architecture.md §8)**: if the base 30 s tone is drawn from a session-scoped fixture, `.copy()` it before splicing — an in-place edit would corrupt the shared array for every other test using it.
- **Steps**: (a) `measure_loudness_range(audio, sr, config).lra_lu`. (b) compute a naive "peak-to-trough of the whole file" figure: `peak_dbfs = 20*log10(max(abs(audio)))` minus the background region's RMS-derived dBFS level (the constant -20 dBFS the tone was built at).
- **Expected result**: (a) `lra_lu` stays small — assert `lra_lu < 3.0 LU` (architect-reasoned, generous; the 5 ms glitch is ~1/600th of one 3 s LRA window's duration, contributing only a small, bounded elevation — roughly 0.6-0.7 LU — to the ~30 (of ~271) overlapping windows whose 3 s span includes it, not to the majority of windows). (b) naive peak-to-trough ≈ `0 - (-20) = 20 dB`. Assert `(b) - (a) > 10` — i.e. the two metrics disagree by a wide, unambiguous margin.
- **Derivation**: a transient far shorter than one LRA analysis window (3 s) contributes negligible additional power to that window's mean-square, so it cannot meaningfully move the K-weighted, doubly-gated, percentile-based LRA statistic — this is the entire point of using a windowed/gated/percentile statistic instead of raw peak-to-trough, and this fixture is constructed specifically to make that difference show up as a large, unambiguous gap rather than a subtle one.

### TC-036 — Very short file → LRA returns the documented zero-result, not a crash (boundary/edge case)
- **Covers**: edge-case checklist item "very short file"; `measure_loudness_range`'s own documented early-return behavior
- **Type**: audio-quality (ground-truth — the expected behavior is defined by the function's own coded/documented contract, read directly, not inferred), edge case
- **Preconditions**: empty array (`audio.size == 0`), and separately, an array shorter than one 3 s LRA window (e.g. 1 s at 44.1 kHz).
- **Steps**: `measure_loudness_range(audio, sr, config)`.
- **Expected result**: `LraResult(lra_lu=0.0, n_gated_blocks=0, self_consistency_delta_lu=0.0)` exactly, for both cases (the empty-array early return, and the "`short_term.shape[0]==0`" early return once no window fits).
- **Derivation**: direct read of the shipped code's two explicit early-return branches — this is exact by construction of the function's own documented contract, not an approximation.

---

## 6. Spectral balance — AC8, `test_ground_truth_spectral_balance.py`

Covers both `seven_band_balance.py` (STORY-002's seven-band scheme) and
`frequency_balance.py` (STORY-001's three-band scheme) — both share the
identical `_psd.py` boundary convention and the same
`relative_db = 10*log10(power_band / power_ref)` formula.

### TC-040 — Band-limited noise confined to one band → that band dominates (AC8a)
- **Covers**: AC8a
- **Type**: audio-quality (ground-truth, directional/relational — see note), **new**
- **Preconditions**: `band_limited_noise_mono(sr, duration_s=4.0, band_hz=(2000,5000), seed=1, amplitude=0.2, floor_amplitude=0.005)` (architecture.md §1.2 — bandpassed component **plus** an independent low-amplitude broadband noise floor; the floor is required, not decorative, so every other band's power stays finite rather than sitting at `_MIN_POWER=1e-20`).
- **Steps**: `measure_seven_band_balance(audio, sr, config)`.
- **Expected result**: `high_mid.relative_db` is the maximum among all seven bands, and exceeds every other band's `relative_db` by at least `20 dB`.
- **Derivation**: the bandpass confines the dominant signal component to the `high_mid` (2000-5000 Hz) band by construction; this is a directional assertion (not a fabricated precise gap number), which is the honest ground truth here per architecture.md §7.4 — the exact numeric gap depends on filter order/floor-amplitude choices.
- **Flagged (architecture.md §10 risk #2)**: the `floor_amplitude=0.005` value has **not been empirically verified** to keep every other band's power away from the `1e-20` floor for this specific fixture. Whoever implements this test must confirm no band sits at the floor before finalizing — if one does, the near-silent-band comparison becomes a floor/floor ratio (numerically unstable, not a meaningful "near-silent" reading), and `floor_amplitude` needs adjustment.

### TC-041 — Equal-energy white noise → band distribution matches geometric (width-derived) prediction, exactly (AC8b)
- **Covers**: AC8b
- **Type**: audio-quality (ground-truth, exact closed-form), **new**
- **Preconditions**: `white_noise_mono(sr, duration_s=5.0, seed=1, amplitude=0.1)`, 44.1 kHz **and separately** 48 kHz (both sample rates required — see mandatory-checklist "multiple sample rates"). Session-scoped: this same fixture is reused by TC-042 and TC-044.
- **Steps**: `measure_seven_band_balance(audio, sr, config)`.
- **Expected result** (44.1 kHz, tolerance `±1.0 dB` per band, generous relative to finite-length Welch estimation variance):

  | band | range (Hz) | width (Hz) | predicted `relative_db` |
  |---|---|---|---|
  | sub | 20-60 | 40 | -15.74 |
  | low | 60-120 | 60 | -13.98 |
  | low_mid | 120-500 | 380 | -5.96 |
  | mid (reference) | 500-2000 | 1500 | 0.00 |
  | high_mid | 2000-5000 | 3000 | +3.01 |
  | high | 5000-10000 | 5000 | +5.23 |
  | air | 10000-22050 | 12050 | +9.05 |

  At 48 kHz, air's open upper edge is 24000 Hz (width 14000): `relative_db = +9.70` — recompute per actual sample rate at implementation time, do not hardcode the 44.1 kHz figure.
- **Derivation**: for genuinely flat white noise, `_psd.band_power`'s trapezoidal integral of a constant density over `[lo, hi]` is `density * (hi - lo)` to a very good approximation (band widths here are all far larger than the PSD bin spacing), so `relative_db(band) = 10*log10(width_band / width_ref)` **independent of the actual noise realization** — a purely geometric prediction, not obtained by running the tool.
- **See TC-044** for the runtime assertion that this exact table also produces zero `seven_band_adjacent_delta` sanity warnings — the negative control for the AC10 seven-band sanity check, using this test's own fixture and computed table.

### TC-042 — Three-band scheme (`frequency_balance.py`): same white-noise fixture, same closed-form prediction
- **Covers**: AC1 (`measure_frequency_balance` ground-truth coverage — not explicitly split out by story.md's AC8, which is written against the seven-band scheme, but required for AC1's full 11-function coverage since `frequency_balance` is one of STORY-001's core six)
- **Type**: audio-quality (ground-truth, exact closed-form), **new**
- **Preconditions**: same `white_noise_mono(sr, 5.0, seed=1, amplitude=0.1)` fixture as TC-041 (reusable — session-scoped), 44.1 kHz and 48 kHz.
- **Steps**: `measure_frequency_balance(audio, sr, config)`.
- **Expected result** (tolerance `±1.0 dB`, same basis as TC-041; identical at both sample rates since none of these three bands touch the sample-rate-dependent Nyquist edge):

  | band | range (Hz) | width (Hz) | predicted `relative_db` |
  |---|---|---|---|
  | low_end | 20-120 | 100 | -11.76 |
  | low_mid_mud | 200-500 | 300 | -6.99 |
  | mid (reference) | 500-2000 | 1500 | 0.00 |
  | presence_harsh | 2000-5000 | 3000 | +3.01 |

- **Derivation**: identical formula and reasoning to TC-041 (`relative_db(band) = 10*log10(width_band/width_ref)`), applied to `frequency_balance.py`'s own configured band edges (`freq_low_band_hz`, `freq_mud_band_hz`, `freq_presence_band_hz`, `freq_reference_band_hz` — read directly from `config.py`, not assumed).

### TC-043 — Boundary-frequency energy is attributed to both adjacent bands (AC8c, direct unit test of `_psd.band_power`)
- **Covers**: AC8c
- **Type**: audio-quality (ground-truth, exact — no audio synthesis involved), **new**
- **Preconditions**: none (no signal generator — a hand-built `freqs`/`psd` array pair, per architecture.md §7.4's own revised design).
- **Steps**: `freqs = np.array([100.0, 120.0, 140.0])`; `psd = np.array([1e-20, 1.0, 1e-20])` (all real energy concentrated at exactly the shared low/low_mid boundary bin, 120 Hz). Call `_psd.band_power(freqs, psd, (60.0, 120.0))` and `_psd.band_power(freqs, psd, (120.0, 500.0))` directly.
- **Expected result**: `power_low > 1e-10` AND `power_low_mid > 1e-10` — the boundary bin's energy is included in **both** adjacent bands.
- **Derivation**: confirmed by reading `_psd.py` directly — its mask is `(freqs >= lo) & (freqs <= hi)`, inclusive on both ends. **This must be a direct unit test of the function, not a synthesized-tone test through the full pipeline** — a real Welch PSD spreads a single tone's energy across several neighboring bins via spectral leakage regardless of which boundary convention `band_power`'s mask actually uses, so a tone-based approach cannot distinguish inclusive from exclusive; "both adjacent bands show elevated energy" would pass under every possible convention, proving nothing. Hand-building the array is what actually isolates the convention.

### TC-044 — Negative control: flat white noise produces zero seven-band adjacent-delta sanity warnings
- **Covers**: AC8b (negative control), AC10 (`check_seven_band_adjacent_deltas`)
- **Type**: audio-quality (ground-truth, exact — derived from TC-041's own closed-form table), negative control, **new**
- **Preconditions**: TC-041's `SevenBandResult` (same fixture, same run — do not regenerate).
- **Steps**: `check_seven_band_adjacent_deltas(seven_band.bands)`.
- **Expected result**: returns `[]` (no warnings).
- **Derivation**: from TC-041's own exact table, the adjacent deltas at 44.1 kHz are `|sub-low|=1.76`, `|low-low_mid|=8.02`, `|low_mid-mid|=5.96`, `|mid-high_mid|=3.01`, `|high_mid-high|=2.22`, `|high-air|=3.82` dB — all well under both the `25.0 dB` non-air threshold and the `40.0 dB` air threshold (at 48 kHz, `|high-air|=4.47`, still comfortably under 40.0). This is the direct false-positive guard for the provisional 25/40 dB thresholds (TC-063): ordinary flat/broadband material must not trip the seven-band plausibility check.

---

## 7. Stereo width / correlation / mono-sum — AC9, `test_ground_truth_stereo_width.py`

**All fixtures here require genuine stereo (samples, 2) arrays** —
`mono_sum` and `per_band_stereo_width` are documented as caller-
responsible for not being invoked on mono input; every fixture below is
built with `to_stereo`/`inverted_stereo`/`independent_noise_stereo`
explicitly, not mono broadcasting.

### TC-050 — Identical L and R: correlation = 1.0 exactly, per-band width ≈0 (AC9a)
- **Covers**: AC9a
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `to_stereo(pink_noise_mono(sr, 3.0, seed=1))` — L and R bit-identical.
- **Steps**: (a) `correlation_coefficient(left, right)`. (b) `measure_per_band_stereo_width(audio, sr, config)`.
- **Expected result**: (a) `pytest.approx(1.0, abs=1e-6)` — the epsilon is required, not a bare exact-equality check (see derivation). (b) every band's `width < 0.05`.
- **Derivation**: for `L=R`, the cross-spectral density `S_LR = S_LL = S_RR` exactly (real, in-phase), so `width = 1 - |S_LL|/sqrt(S_LL*S_LL) = 1 - 1 = 0` in every band, by the formula's own algebra. The `1e-6` epsilon on the correlation result is required because `correlation_coefficient` computes numerator/denominator from two independently-rounded floating-point sums (`sqrt(sum(L**2)*sum(R**2))` vs. `sum(L*R)`, different operation sequences on bit-identical inputs) — this can read fractionally over `1.0` (e.g. `1.0000000000000002`) as a pure floating-point artifact on the single MOST correct possible input; a bare `[-1,1]` bound (no epsilon) would false-positive exactly here.

### TC-051 — Inverted R (L = -R): correlation = -1.0 exactly, mono-sum is exactly silent (AC9b)
- **Covers**: AC9b
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `inverted_stereo(pink_noise_mono(sr, 3.0, seed=1))` (architecture.md §1.2 — `np.stack([mono, -mono], axis=1)`).
- **Steps**: (a) `correlation_coefficient(left, right)`. (b) `measure_mono_sum(audio, sr, config)`.
- **Expected result**: (a) `pytest.approx(-1.0, abs=1e-6)`. (b) `mono_sum` is identically the zero array (`L + R == 0` sample-for-sample), so `measure_integrated_lufs` on it returns exactly `float("-inf")` (per the same mechanism as STORY-001's existing `test_tc017`) — assert `level_change_db == float("-inf")` and `excess_cancellation_db == float("-inf")` **exactly**, not approximately.
- **Note (avoiding a false "regression" report)**: `per_band_stereo_width` is magnitude-based (phase-blind, using `|Re{S_LR}|`) by design — it reads `≈0` for **both** ρ=+1 (TC-050) and ρ=-1 here, since both are "fully correlated in magnitude," just opposite sign. Do not write an assertion claiming `per_band_stereo_width` distinguishes this case from TC-050 — that would assert incorrect behavior against the formula's own design (architecture.md §7.5).

### TC-052 — Uncorrelated noise L and R: correlation near 0.0, per-band width high (AC9c)
- **Covers**: AC9c
- **Type**: audio-quality (ground-truth, directional/relational for the width bound — see note), **new**
- **Preconditions**: `independent_noise_stereo(sr, 5.0, sigma=0.05, seed=3)` (existing `ref_helpers.py` function, the DEF-101 case-2 fixture — independent generators, equal power).
- **Steps**: (a) `correlation_coefficient(left, right)`. (b) `measure_per_band_stereo_width(audio, sr, config)`.
- **Expected result**: (a) within `±0.05` of `0.0` (finite-sample noise tolerance, not a tight bound — two independent Gaussian generators of finite length do not have exactly zero sample correlation). (b) `width >= 0.8` in every band.
- **Derivation**: independent, equal-power noise drives `S_LR → 0` in expectation as sample count grows, so `width = 1 - |S_LR|/sqrt(S_LL*S_RR) → 1`.
- **Flagged (architecture.md §10 risk #1)**: `width >= 0.8` is a generous starting figure, architect-reasoned but **not yet empirically verified** against this codebase's actual Welch-averaging depth at this fixture length — run once, inspect the actual measured value, tighten the bound closer to observed-plus-margin.

### TC-053 — Negative control: uncorrelated stereo must not false-positive as cancellation
- **Covers**: AC9c / AC9d boundary (this is the direct DEF-101 false-positive guard, already partially shipped as `test_tc313`)
- **Type**: regression guard, negative control — **already satisfied by existing `test_tc313`**, recorded here for traceability
- **Preconditions**: same as TC-052.
- **Steps**: `measure_mono_sum(audio, sr, config)`.
- **Expected result**: `excess_cancellation_db ≈ 0` (i.e. no worse than the expected rho=0 floor), `any_cancellation is False` for every band — ordinary decorrelated stereo is healthy, not flagged.

### TC-054 — DEF-203 resolution: mono-sum floors derived from first principles for ρ ∈ {+1, 0, -1} (AC9d)
- **Covers**: AC9d, DEF-203's required derivation
- **Type**: audio-quality (ground-truth), **the DEF-203 derivation-of-record test**
- **Preconditions**: three sub-cases, all stereo:
  - ρ=+1: `to_stereo(pink_noise_mono(sr, 5.0, seed=1))` (identical L=R).
  - ρ=0: `independent_noise_stereo(sr, 8.0, sigma=0.05, seed=1)`.
  - ρ=-1: `inverted_stereo(pink_noise_mono(sr, 5.0, seed=1))`.
- **Steps**: `measure_mono_sum(audio, sr, ref_config())` for each case; inspect `level_change_db` (broadband) and every `band_cancellations[i].delta_db` (per-band).
- **Expected result**:

  | ρ | `level_change_db` (broadband) | `delta_db` (per-band, each) |
  |---|---|---|
  | +1 | `pytest.approx(-3.0103, abs=0.1)` | `pytest.approx(0.0, abs=1.0)` |
  | 0 | `pytest.approx(-6.0206, abs=0.1)` | `pytest.approx(-3.0103, abs=1.0)` |
  | -1 | `== float("-inf")` (exact) | (not separately asserted — dominated by noise-floor artifacts in the shipped ~5 s fixture; the broadband -inf is the clean, exact assertion for this case) |

- **Derivation, stated explicitly per requirements.md's own requirement (this is the load-bearing "why," not just the numbers)**: let L, R be zero-mean, equal-power (`Var(L)=Var(R)=σ²`) channels with correlation ρ. `mono_sum=(L+R)/2`, so `Var(mono_sum)=σ²(1+ρ)/2`.
  - **Broadband `level_change_db`** uses BS.1770's **channel-summed** convention (both `stereo_lufs` and `mono_lufs` come from `measure_integrated_lufs`): `LUFS_stereo = -0.691+10log10(2σ²)`, `LUFS_mono = -0.691+10log10(σ²(1+ρ)/2)`, so `level_change_db = 10*log10((1+ρ)/4)`.
  - **Per-band `delta_db`** uses the **per-channel-mean** band-power denominator (`power_channel_mean=(P_L+P_R)/2=σ²`), numerator `power_sum=Var(mono_sum)=σ²(1+ρ)/2`: `delta_db = 10*log10((1+ρ)/2)`.
  - These are genuinely different formulas with genuinely different denominators — not two candidate answers to one question. At ρ=+1: `(1+1)/4=0.5 → -3.0103 dB` (broadband) vs. `(1+1)/2=1.0 → 0.0 dB` (per-band). At ρ=0: `1/4 → -6.0206 dB` vs. `1/2 → -3.0103 dB`. At ρ=-1: both `→ 10*log10(0) = -inf`.
- **Tolerance basis**: broadband `±0.1 dB` (matches existing `test_tc311`/`test_tc313`, generous against the ~0.01-0.02 dB expected finite-sample noise floor, `O(1/sqrt(N))` in ρ). Per-band `±1.0 dB` (wider — Welch/CSD band-power estimates from a few seconds of audio have materially more variance than the full-signal time-domain LUFS computation; matches DEF-101's own observed per-band spread of -0.26 to +0.32 dB on an 8 s fixture).
- **This confirms the shipped constants are already correct** (`_BROADBAND_DECORRELATED_FLOOR_DB=-6.0206`, `_PERBAND_DECORRELATED_FLOOR_DB=-3.0103`) — see the "AC6 branch" note below.
- **AC6/AC11 branch, stated explicitly per architecture.md §3.4/§6**: this test is **expected to PASS on first run against the current, unmodified code** — DEF-203 is resolved as **not-a-defect** by this derivation, so there is no fix and therefore no "failing test first" sequence for it (unlike DEF-201's AC6d, TC-024). This is a deliberate, documented exception to AC6's ordering requirement, not a silent gap. Record the full derivation (not just a status change) in `stories/STORY-002/defects.md`'s DEF-203 entry, closing it not-a-defect, and state explicitly that AC6's failing-test-first requirement does not apply here and why.
- **Extends, does not merely duplicate, existing coverage**: `test_tc311` (ρ=+1) and `test_tc313` (ρ=0) already exist and assert the derived boolean/`excess_*` fields; what is genuinely new here is the raw `delta_db`/`level_change_db` values with the denominator distinction stated inline, plus the ρ=-1 case (not covered at all previously).

### TC-055 — Both channels silent: correlation reads exactly 1.0 by design (documented degenerate case)
- **Covers**: requirements.md's "Known degenerate cases" section
- **Type**: audio-quality (ground-truth — behavior defined by the function's own documented design), edge case, silence
- **Preconditions**: stereo, all-zero array (both channels silent/null).
- **Steps**: `correlation_coefficient(left, right)`.
- **Expected result**: `pytest.approx(1.0)` exactly — **not** `NaN`, **not** an error.
- **Derivation**: by the module's own explicit design comment ("treat as compatible, not undefined") — a `correlation outside [-1,1] -> fail` sanity rule is satisfied by this design already (1.0 is in-range), but this test asserts the specific degenerate-input behavior directly so a future change to the null-handling doesn't silently drift without a test noticing.

### TC-056 — End-to-end: `analyze_stereo_phase`'s public `overall_correlation` on the same fixtures (public-API coverage, not just the internal helper)
- **Covers**: AC9a/AC9b (extended to the public function, not only the `correlation_coefficient` helper §7.5 ground-truths)
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: TC-050's (identical L=R) and TC-051's (inverted) fixtures.
- **Steps**: `analyze_stereo_phase(audio, sr, config)`.
- **Expected result**: identical-L=R case: `overall_correlation ≈ 1.0` (±1e-6), `mono_compatible is True` (since `1.0 >= phase_correlation_floor=0.0`). Inverted case: `overall_correlation ≈ -1.0` (±1e-6), `mono_compatible is False` (since `-1.0 < 0.0`).
- **Derivation**: same underlying formula as `correlation_coefficient` (`analyze_stereo_phase` is the public, windowed/aggregated entry point that calls it) plus the documented `mono_compatible` threshold comparison against `config.phase_correlation_floor` — both are direct, exact consequences of the fixture's construction. This closes the gap that architecture.md §7.5 ground-truths only the internal helper, not the public function AC1 actually requires coverage of.

### TC-057 — Mono-sum on the both-silent degenerate case does not crash
- **Covers**: requirements.md's degenerate-case section, extended to `mono_sum` (not explicitly named there, but the same "does not crash on the input that produces -inf" concern applies)
- **Type**: edge case, silence
- **Preconditions**: stereo, all-zero array.
- **Steps**: `measure_mono_sum(audio, sr, config)`.
- **Expected result**: completes without raising; `level_change_db` and `excess_cancellation_db` are both `float("-inf")` (mono_sum of two zero channels is zero; stereo LUFS is also `-inf`; `-inf - (-inf)` is undefined arithmetically, so the actual returned value must be inspected and recorded rather than assumed — **flagged as an open question**: whether the shipped code guards this specific double-`-inf` case explicitly or lets Python's float arithmetic produce `nan`. If it produces `nan`, `check_lufs_plausible`/`check_correlation_range`-style guarding does not currently cover `MonoSumResult` fields — note this as a finding, not a pre-assumed pass/fail.)

---

## 8. Sanity assertions — AC10, `test_ground_truth_sanity_assertions.py`

Per architecture.md §7.6, **two layers, not one** — a population-only
test suite does not satisfy AC10, since the report-builder layer might
not thread the new field even if the dataclass change is correct
(architecture.md §4.4's flagged risk).

### 8.1 Unit level — plain values against the four pure functions directly

### TC-060 — `check_correlation_range`: boundary and epsilon cases
- **Covers**: AC10 (correlation sanity check)
- **Type**: audio-quality (ground-truth, exact predicate boundaries), boundary values
- **Steps/Expected** (table form — each row is one assertion):

  | input | expected |
  |---|---|
  | `1.0` | `None` (pass) |
  | `1.0000000000000002` (floating-point artifact on identical channels) | `None` — **this is the case the epsilon exists for; without it, the single MOST correct possible input would false-positive** |
  | `1.0 + 1e-6` (exactly at the epsilon boundary) | `None` (predicate is strictly `>`, so exactly-at-boundary passes) |
  | `1.0 + 2e-6` (just over) | `SanityWarning("correlation_range", "fail", ...)` |
  | `-1.0`, `-1.0 - 1e-6` | `None` (symmetric lower boundary) |
  | `-1.0 - 2e-6`, `1.5`, `-2.0` | `fail` |
  | `float("nan")` | `fail`, message mentions NaN — **checked first**, since `NaN` compares `False` against every numeric bound and would otherwise sail through silently |

### TC-061 — `check_lufs_plausible`: boundary, exemption, and impossibility cases
- **Covers**: AC10 (LUFS sanity check), requirements.md's degenerate-case exemption requirement
- **Type**: audio-quality (ground-truth, exact predicate boundaries — the -70 floor derivation is a proof, not an estimate, per architecture.md §4.2's own docstring), boundary values
- **Steps/Expected**:

  | input | expected |
  |---|---|
  | `float("-inf")` | `None` — **the legitimate, documented BS.1770-gated silence result; exempt exactly `-inf`, not any "looks quiet" heuristic** (this is the "known degenerate case" requirements.md explicitly requires not be misflagged) |
  | `-70.0` exactly | `None` (predicate is strictly `<`, so exactly at the floor passes — the proof in architecture.md §4.2 shows a passing gate can never produce a value *below* -70, but exactly -70 is not itself excluded by the predicate as written) |
  | `-70.01` (just under) | `fail` |
  | `0.0` exactly | `None` (predicate strictly `>`, boundary passes) |
  | `0.01` (just over) | `fail` |
  | `-40.0` (ordinary, ok) | `None` |
  | `float("nan")` | `fail`, mentions NaN |

- **Derivation**: BS.1770 integrated loudness is a power-mean (not plain average) of per-block mean-squares that individually passed the -70 LUFS absolute gate; each surviving block's mean-square `x_i` satisfies `x_i > 10**((-70+0.691)/10)`, and the arithmetic mean of positive values is `>=` any individual value's own floor — so a finite value below -70 is mathematically impossible for a correct implementation whenever the gate let anything through, not merely suspicious. This is a proof, reused directly from `analysis/sanity.py`'s own docstring (already shipped).

### TC-062 — `check_hf_rolloff_vs_air_band`: boundary and None-degradation cases
- **Covers**: AC10 (HF-rolloff-vs-air-band sanity check), the DEF-201 report-review finding restated as a standing invariant
- **Type**: audio-quality (ground-truth, exact predicate boundaries), boundary values
- **Steps/Expected**:

  | `rolloff_hz` | `insufficient_duration` | `air_relative_db` | expected |
  |---|---|---|---|
  | `None` | `False` | `-10.0` | `None` (skipped — no rolloff to check) |
  | `2000.0` | `True` | `-10.0` | `None` (skipped — result already marked unreliable) |
  | `2000.0` | `False` | `None` | `None` (skipped — no seven-band air figure available, e.g. non-default band config) |
  | `5000.0` exactly | `False` | `-10.0` | `None` (predicate strictly `<`, boundary passes — not flagged) |
  | `4999.0` | `False` | `-40.0` exactly | `None` (predicate strictly `>`, boundary passes — the air-energy condition is false exactly at -40) |
  | `4999.0` | `False` | `-39.9` (just over -40) | `fail`, message includes both the rolloff and air-band figures |
  | `1979.0`, air `-20.05` | `False` | (n/a) | `fail` — **this is literally DEF-201's own reported numbers** (GusGus: 1979 Hz rolloff, -20.05 dB air-band), the concrete case that motivated this check |

- **Derivation**: predicate is `rolloff_hz < 5000.0 and air_relative_db > -40.0` (both from story.md's own stated figures, restated unaltered) — the unit is deliberately `SevenBandMeasurement.relative_db` (power-integrated), the same figure already surfaced in every report and the one DEF-201's own report review quoted, avoiding a density-vs-power unit conversion (architecture.md §2.4).

### TC-063 — `check_seven_band_adjacent_deltas`: boundary cases, two-threshold structure
- **Covers**: AC10 (seven-band adjacent-delta sanity check)
- **Type**: audio-quality (ground-truth, exact predicate boundaries; the 25/40 dB thresholds themselves are architect-reasoned/provisional, flagged below), boundary values
- **Steps/Expected**:

  | pair | delta | expected |
  |---|---|---|
  | non-air pair, delta `25.0` exactly | `None` (boundary passes, predicate strictly `>`) |
  | non-air pair, delta `25.01` | one `warn` |
  | pair involving `air`, delta `40.0` exactly | `None` |
  | pair involving `air`, delta `40.01` | one `warn` |

- **Flagged, provisional (architecture.md §9 item 1)**: `25.0`/`40.0` dB are an explicit architectural judgment call, not a derived invariant like the LUFS floor — requirements.md's own open question 3 routed this to the architect, who proceeded with these values pending calibration against real reference-track data. **Instruction to whoever runs this suite against the project's real five-track reference set**: report the observed maximum adjacent-band delta for every pair (including air) across all five tracks, so these numbers can be tightened or loosened without another architecture round-trip.
- **See TC-044** for the exact-value negative control (flat white noise's own closed-form adjacent-delta table) that exercises this function end-to-end rather than with boundary-only synthetic values.

### 8.2 Rendered-output level — closes architecture.md §4.4's flagged risk

### TC-064 — Reference-path renderer surfaces a real sanity fail (DEF-201-shaped scenario)
- **Covers**: AC10, AC13 (rendered-output, not merely population — architecture.md §4.4/§7.6's explicitly-required check, since `build_reference_set_report()` might not thread `ReferenceMeasurements.sanity_warnings` even if the dataclass change is correct)
- **Type**: functional, **new**
- **Preconditions**: **`make_stub_measurements()` hand-constructs `ReferenceMeasurements` directly and does not itself call any `check_*` function — its `sanity_warnings` defaults to an empty list. The warning must be injected explicitly, not assumed to appear from the `hf_rolloff_hz`/`air`-band-value overrides alone.** Two acceptable ways to do this, either is fine: (a) extend `make_stub_measurements` to accept a `sanity_warnings` override and pass `[check_hf_rolloff_vs_air_band(2000.0, False, -10.0)]` (the DEF-201-shaped values: rolloff 2000 Hz, air-band relative_db -10.0 dB, both consistent with the seven-band/HF overrides already passed to the stub); or (b) construct the stub via `make_stub_measurements(hf_rolloff_hz=2000.0, hf_insufficient_duration=False, seven_band_relative_db=-10.0)`, then explicitly compute and assign `warning = check_hf_rolloff_vs_air_band(2000.0, False, -10.0)` onto the result's `sanity_warnings` list before rendering.
- **Steps**: `build_reference_set_report()` then `render_markdown()` and `render_json()`.
- **Expected result**: the FAIL text (or the `sanity_warnings` content) appears in both rendered outputs — not just present on the intermediate dataclass.
- **Derivation**: this directly exercises whatever `reference_builder.py` actually does with the field, closing the specific risk architecture.md §4.4 flags: a population-only assertion would still pass even if `build_reference_set_report()` reconstructs its own per-track output shape without threading `sanity_warnings` through. **Injecting the warning explicitly (rather than relying on the stub helper to produce it) is what isolates "does the renderer thread the field" from "does the check function fire" — conflating the two would make a renderer-threading bug indistinguishable from a check-predicate bug.**

### TC-065 — Mastering-path renderer surfaces a manufactured sanity warning
- **Covers**: AC10, AC13 (rendered-output, mastering pre/post path)
- **Type**: functional, **new**
- **Preconditions**: hand-constructed `Measurements` (or `ReportData`) with a manufactured `sanity_warnings` list (e.g. a correlation-out-of-range warning).
- **Steps**: call `report/render.py`'s `render_markdown()` directly.
- **Expected result**: the warning text appears in the rendered markdown.

### TC-066 — Integration: `measure_all()` and `analyze_track()` populate `sanity_warnings` end-to-end, including the correct negative result on clean audio
- **Covers**: AC10
- **Type**: functional
- **Preconditions**: (a) a small, real (if tiny) synthetic buffer with nothing wrong with it, run through both entry points. (b) TC-050's identical-L=R stereo fixture specifically — the case whose correlation can read `1.0000000000000002` due to floating-point artifacts (TC-060's epsilon row) — run through `measure_all()`.
- **Steps**: `measure_all(...)`, `analyze_track(...)` for (a); `measure_all(...)` for (b).
- **Expected result**: (a) `sanity_warnings` is populated (a list, possibly empty) on both result objects — confirms wiring. (b) `sanity_warnings == []` **specifically** — this is the end-to-end counterpart of TC-060's epsilon row: it confirms the always-on `check_correlation_range` call inside `measure_all()` does not false-positive on the single most likely real-world trigger for the floating-point artifact the epsilon exists to absorb. **This negative-result check is required, not optional** — per architecture.md §4.3, sanity checks now run inside every `measure_all()` call, and no existing `test_ac*`/`test_ref_*` test inspects `sanity_warnings` at all, so without this assertion a false positive here would currently be invisible to the whole test suite.

### TC-067 — Hard rule: a fail-severity sanity warning never raises or aborts the pipeline run
- **Covers**: AC10's hard rule (architecture.md §4.1) — an implicit requirement no §7.6 worked example directly tests
- **Type**: functional, **new**
- **Preconditions**: a fixture deliberately engineered to trip a `"fail"`-severity check (e.g. TC-064's DEF-201-shaped scenario, or a manufactured out-of-range correlation).
- **Steps**: run the full pipeline (`measure_all` or `analyze_track`) end-to-end against this fixture.
- **Expected result**: the run **completes normally** and returns a result object with the `fail`-severity warning present in `sanity_warnings` — no exception is raised, no run aborts. This is `story.md`'s own language ("-> fail") explicitly *not* meaning "raise an exception" (architecture.md §4.1's stated hard rule) — a false positive on genuine, unusual-but-real audio must degrade to an odd report annotation, never a crashed run.

### TC-068 — Golden-file / reproducibility check before regenerating any stored fixture
- **Covers**: AC13 (schema-change consequence)
- **Type**: regression, process check
- **Preconditions**: `test_ac10_reproducibility.py` (referenced in DEF-103's fix notes as part of a "reproducibility/golden-file suite") or any other file doing an exact stored-JSON/report-text diff.
- **Steps**: before adding `sanity_warnings` to any dataclass rendering path used by such a test, check whether it does an exact-shape diff.
- **Expected result**: if it does, golden-file regeneration is a **deliberate, reviewed step** (confirm the new content is correct, then regenerate) — not a silent overwrite that could mask an unrelated regression. Flag this explicitly in the PR/commit, per architecture.md §4.4.
- **Note**: since `sanity_warnings`/`SCHEMA_VERSION="1.2"` are **already present in the shipped code** (confirmed by reading `reference_builder.py` directly before writing this document), this check should be run against whatever golden files currently exist to confirm they already reflect the additive field, not assumed to be already correct.

### TC-069 — Boundary values as a set: verify every predicate's edge is a genuine boundary, not an off-by-one
- **Covers**: AC10 (cross-cutting)
- **Type**: audio-quality (ground-truth), meta/coverage check
- **Steps**: confirm TC-060/TC-061/TC-062/TC-063 collectively exercise, for every numeric threshold in `analysis/sanity.py`: the exact value, one representative unit just inside, and one just outside. (This is a coverage-completeness check on the sanity-assertion test set itself, not a new runtime assertion.)
- **Expected result**: every threshold (`±1e-6` correlation epsilon, `-70.0`/`0.0` LUFS bounds, `5000.0`/`−40.0` HF-vs-air bounds, `25.0`/`40.0` seven-band deltas) has all three cases present somewhere in TC-060 through TC-063.

---

## 9. `k_weight` / `oversample` — recommended additional coverage, `test_ground_truth_kweight_oversample.py`

Per requirements.md's own flagged recommendation, confirmed in-scope by
architecture.md §9 item 3: both are load-bearing internal machinery
(every LRA measurement depends on `k_weight`; every true-peak
measurement depends on `oversample`) where a silent bug would corrupt
every downstream measurement calling them, and both have cheap ground
truth available.

### TC-070 — `oversample` in isolation recovers the known inter-sample peak
- **Covers**: requirements.md's recommended additional coverage
- **Type**: audio-quality (ground-truth), **new**
- **Preconditions**: `nyquist_adjacent_sine(sr, 2.0)` (TC-010's fixture, reused).
- **Steps**: `oversample(fixture, sr, factor=8)` directly (no guard-region trimming — that is `measure_true_peak`'s own addition, not `oversample`'s).
- **Expected result**: `max(abs(oversampled))` within `0.05` of `1.0`.
- **Derivation**: same `sr/4` construction as TC-010 guarantees a continuous-time peak of exactly `1.0` at inter-sample points; this test ground-truths the interpolation filter in isolation from the peak-search/guard-region logic layered on top of it in `measure_true_peak`.

### TC-071 — `k_weight`'s 10 kHz shelf-plateau gain matches BS.1770's published anchor point; 1 kHz filter-only gain cross-checked against TC-001's net-offset finding
- **Covers**: requirements.md's recommended additional coverage
- **Type**: audio-quality (ground-truth) for the 10 kHz row; derived cross-check (not an independently-published anchor) for the 1 kHz row — see note below, the same class of distinction TC-072 already draws for its own figure.
- **Preconditions**: sines at 1 kHz and at 10 kHz (well above the shelf's ~1.7 kHz center, on its plateau), known amplitude, 2-3 s each.
- **Steps**: apply `k_weight`, compare input/output RMS ratio in dB.
- **Expected result**:
  - 10 kHz (shelf plateau): `≈+4 dB` (`±1.0 dB`) — a genuine BS.1770-4 Annex 1 published anchor point (`g_db≈3.9998` in the shipped coefficients, matching the standard's ~+4 dB figure). Tolerance generous since published figures vary slightly by source/rounding.
  - 1 kHz: filter-only gain is small and **positive**, in the range `+0.5 dB` to `+0.9 dB` — **not** `≈0 dB`, and **not itself a published anchor**.
- **Derivation, and why the 1 kHz figure changed from an earlier draft of this test case**: TC-001's "1 kHz is calibration-neutral" claim is a statement about the **combined system** — the K-weighting filter's own gain at 1 kHz, plus BS.1770's separate, fixed `-0.691 dB` offset applied later in the loudness formula — netting to ≈0 dB (within TC-001's own `±0.1` LU tolerance), not a claim about the filter's isolated gain. An earlier draft of this test case conflated the two and asserted the filter's own 1 kHz gain should also read `≈0 dB` (`±0.5 dB`); measured directly against the shipped `k_weight` (filter applied alone, input/output RMS ratio, no BS.1770 offset involved), the actual filter-only gain at 1 kHz is `≈+0.70 dB` — outside that draft's stated tolerance (`stories/STORY-002/defects.md` DEF-207 item 2). This is not adopted here as a newly-pinned ground-truth number, though: it is bounded instead as a **cross-check derived from TC-001's own tolerance plus the published `-0.691 dB` fixed offset** — if the combined net offset at 1 kHz is within `±0.1 dB` of `0` (TC-001's own assertion), then `filter_gain_db = 0.691 + net_offset_db` must fall within `[0.591, 0.791] dB`, which this test case widens slightly to `[0.5, 0.9] dB` for fixture-measurement margin. DEF-207's own empirical cross-check (`0.691 - 0.0354 ≈ 0.656 dB`, implied by TC-001/TC-004's corrected `-0.0354 dB` net-offset finding) falls inside this derived band, consistent with the `≈0.70 dB` direct filter-only measurement — the same underlying number found two independent ways, not two unrelated findings.
- **Note — do not read the 1 kHz row as a ground-truth-by-run assertion**: per this document's own Section 0 rule, an expected value is only "ground-truth" if it is derivable from the signal's construction and known standards, not from having run the implementation and recorded what it said. The `[0.5, 0.9] dB` band here is derived from TC-001's own stated tolerance and BS.1770's published `-0.691 dB` offset — both independent of any run of `k_weight` itself — so it remains a legitimate correctness bound, not a regression lock, but it is explicitly **not** a BS.1770-published anchor point the way the 10 kHz plateau figure is; the title and this note say so to avoid the ambiguity the earlier draft's title created.

### TC-072 — `k_weight` low-frequency attenuation — sanity floor only, exact figure flagged as an open question
- **Covers**: requirements.md's recommended additional coverage
- **Type**: audio-quality (sanity assertion only — **not a full ground-truth test**, see flag), **new**
- **Preconditions**: sine at 20 Hz (well below the high-pass corner, ~38 Hz per the shipped coefficients).
- **Steps**: apply `k_weight`, compare input/output RMS ratio in dB.
- **Expected result (sanity floor only)**: attenuation is strictly negative (the filter attenuates, does not amplify, at 20 Hz) and larger in magnitude than at any frequency closer to the corner (monotonic trend toward DC) — this distinguishes a correctly-implemented high-pass from a null/no-op filter without needing the precise published figure.
- **Open question, not guessed (architecture.md §10 risk #3)**: the exact literature-sourced attenuation figure at 20 Hz is **not pinned down by architecture.md** — whoever implements this test needs an authoritative source (BS.1770-4 Annex 1's own published response curve, or a known-good independent implementation's test vectors, e.g. libebur128's) before adding a precise numeric assertion. Deriving the number solely from this project's own filter coefficients would make the test circular against its own implementation. **Do not invent a figure here** — record this as an open item until sourced.

---

## 10. Process / coverage / documentation checks — AC1, AC2, AC3, AC11, AC12, AC13, NFRs

These are not runtime pytest assertions in the usual sense — they are
checks against the test suite's own source and against
`stories/STORY-002/defects.md`'s content. Listed here because AC1-AC3,
AC11, and AC12-AC13 are acceptance criteria in their own right and are
easy to silently skip if only numeric-assertion test cases are written.

### TC-080 — AC1 coverage audit: all 11 measurement functions have ≥1 analytically-derived ground-truth test
- **Covers**: AC1
- **Type**: non-functional (process/documentation audit)
- **Steps**: cross-reference the traceability table (§11 below) against the 11-function inventory from requirements.md: `measure_integrated_lufs`, `measure_true_peak`, `measure_dynamic_range`, `measure_frequency_balance`, `analyze_stereo_phase`, `detect_clipping` (STORY-001's six); `measure_loudness_range`, `measure_mono_sum`, `measure_hf_extension`, `measure_seven_band_balance`, `measure_per_band_stereo_width` (STORY-002's five).
- **Expected result**: every one of the 11 has at least one linked TC ID in §11 whose expected value is derived analytically (marked "ground-truth" in this document, not only "regression guard").
- **Note**: this audit also distinguishes **new** ground-truth tests from **existing-extended** ones (TC-001 = existing `test_tc010`; TC-054 extends `test_tc311`/`test_tc313`) so the audit is honest about what this story actually adds versus what it inherits.

### TC-081 — AC2 audit: no `.wav`/`.flac`/`.mp3` fixture files loaded by the ground-truth suite
- **Covers**: AC2
- **Type**: non-functional (source inspection)
- **Steps**: grep every `test_ground_truth_*.py` file for file-loading calls (`sf.read`, `soundfile.read`, `open(...` on audio paths, `librosa.load`, etc.).
- **Expected result**: zero matches — every signal is generated in-process via numpy/scipy.

### TC-082 — AC3 audit: every ground-truth test states its derivation inline
- **Covers**: AC3
- **Type**: non-functional (source inspection/code review checklist)
- **Steps**: for each ground-truth test function in the suite, confirm a docstring or comment states *why* the expected value is correct — the derivation, not just the number (e.g. "1 kHz is BS.1770's calibration-neutral frequency because...", not merely "expect -20.0").
- **Expected result**: every ground-truth test (as opposed to a purely relational/directional or process-level test) has this comment present.

### TC-083 — AC11 evidence check: DEF-201's pre-fix failure is recorded with actual-vs-expected numeric values
- **Covers**: AC11
- **Type**: non-functional (process compliance)
- **Steps**: inspect `stories/STORY-002/defects.md`'s DEF-201 entry after TC-024's sequencing protocol (§4 above) has been run.
- **Expected result**: the entry records, before any production-code change: the failing test's name, the failing assertion, and the actual numeric `rolloff_hz` value returned versus the expected `>= 0.9*(sr/2)` bound — not merely "it failed." After the fix: the post-fix value, plus pass counts from the full `test_ref_*.py`/`test_ac*.py` re-run, plus DEF-201 marked **Fixed**.

### TC-084 — AC11 branch check: DEF-203's derivation and not-a-defect closure are recorded, with the ordering exception stated
- **Covers**: AC11 (DEF-203 branch)
- **Type**: non-functional (process compliance)
- **Steps**: inspect `stories/STORY-002/defects.md`'s DEF-203 entry after TC-054 has been run.
- **Expected result**: the entry records the full first-principles derivation inline (both denominators, the ρ=+1/0/-1 table — not merely a pointer to architecture.md), closes DEF-203 as **not-a-defect**, and explicitly states that AC6's "failing-test-first" requirement does not apply to this defect and why (the derivation confirms the shipped constant was already correct, so there is no fix to precede with a failing test).

### TC-085 — AC12: ground-truth subset runtime is measured, not assumed
- **Covers**: AC12
- **Type**: non-functional (performance)
- **Preconditions**: the full `pytest -m ground_truth` (or equivalent filename-convention) subset, including the longer-than-2-5s DR/LRA fixtures (TC-030's 15 s, TC-033/034's 30s+30s).
- **Steps**: run `pytest -m ground_truth`, time the wall-clock duration.
- **Expected result**: `< 30` seconds, **measured directly, not assumed from architecture.md's own reasoning** — architecture.md §1.3 explicitly states its vectorized-operations argument is a reason to expect this, not a substitute for measuring it; record the actual figure.

### TC-086 — AC13: schema version and both renderers are consistently updated
- **Covers**: AC13
- **Type**: regression / non-functional
- **Steps**: confirm `report/reference_builder.py::SCHEMA_VERSION == "1.2"` (already shipped, confirmed by direct read); confirm both `report/reference_render.py` and `report/render.py` render `sanity_warnings` (TC-064/TC-065 already exercise this at the rendered-output level — this entry cross-references rather than duplicates).
- **Expected result**: consistent `[FAIL]`/`[WARN]` convention in both renderers, one `sanity_warnings` field per result type (not two scattered lists — `ReferenceMeasurements.sanity_warnings` is a superset of `core.sanity_warnings`, confirmed by reading `pipeline.py` directly).

### TC-087 — NFR: full existing suite has no regression beyond documented, expected changes
- **Covers**: non-functional requirement ("No regression")
- **Type**: regression
- **Steps**: after the DEF-201 config change and the TC-026/TC-027 re-fixturing, re-run the full `test_ac*.py` and `test_ref_*.py` suites.
- **Expected result**: zero new failures **except** the intentionally-changed HF-related fixtures (TC-026/TC-027, deliberately migrated) and any newly-`True` `suspected_transcode` flags on real lossy reference tracks (TC-029, an expected output change per the fix's own purpose, not a regression).

### TC-088 — NFR: reproducibility — fixed seeds produce deterministic results across repeated runs
- **Covers**: non-functional requirement ("Reproducibility")
- **Type**: non-functional (determinism)
- **Steps**: run the full ground-truth suite twice in succession.
- **Expected result**: bit-identical (or value-identical within each test's own stated tolerance, applied deterministically) results both runs — every noise-based generator takes an explicit `seed` parameter; no bare unseeded `np.random` calls anywhere in the suite.

### TC-089 — NFR: session-scoped fixture mutation hazard — shared arrays are not corrupted across tests
- **Covers**: non-functional requirement ("Session-scoped fixtures"), architecture.md §8's explicitly-flagged mutation hazard
- **Type**: regression (test-suite-quality guard)
- **Steps**: for every test that derives a modified variant of a session-scoped fixture (e.g. TC-035's glitch-splice on a 30 s tone, any duration-slicing), snapshot the session-scoped array's values (or a hash) at session start and re-check identity after the full suite runs.
- **Expected result**: the original session-scoped array is bit-identical to its session-start snapshot after every test that uses it has run — a test that mutates in place (e.g. `audio *= 2.0`, a slice-assignment dropout) without first calling `.copy()` would corrupt the array for every later-running test in the session; this test catches that class of bug directly rather than relying on test-order luck.

---

## 11. Traceability table (requirements.md acceptance criteria → test case IDs)

| AC | Description | Test case IDs |
|---|---|---|
| AC1 | Coverage: all 11 measurement functions have ≥1 analytically-derived TC | TC-080 (audit); satisfied by TC-001/002 (loudness), TC-010-013 (true peak), TC-016-019 (clipping), TC-020-025 & TC-023 (HF ext.), TC-030-036 (DR/LRA), TC-040-044 (spectral balance), TC-050-057 (stereo/mono-sum) |
| AC2 | Programmatic signals only, no file fixtures | TC-081 |
| AC3 | Derivation stated inline in every ground-truth test | TC-082 |
| AC4a | 1 kHz sine → known LUFS | TC-001 |
| AC4b | 6 dB gain → 6 LU loudness change | TC-002 |
| AC5a | Inter-sample peak exceeds sample peak by a known margin | TC-010 |
| AC5b | True peak and sample peak return different values (regression guard) | TC-011 |
| AC6a | Brickwall @15 kHz → detected within one bin | TC-020 |
| AC6b | Brickwall @8 kHz → detected within one bin | TC-021 |
| AC6c | Full-band white noise → no cutoff / near-Nyquist | TC-022 |
| AC6d | Pink noise → no cutoff (the DEF-201 regression case) | TC-024 |
| AC6e | Drift/instability detection | TC-025 |
| AC6 (DEF-201 REOPENED, required case 4 — see §4.1) | Pink noise (steep, -6 dB/octave tilt) + real cutoff at 15 kHz — detector must find the cliff, not the tilt; **written to FAIL against the shipped pre-redesign (`hf_rolloff_threshold_db=20.0`) detector, analytically predicted at ≈10,000 Hz** | TC-090 |
| AC6 (DEF-201 REOPENED, coordinator-requested gap closure — see §4.1) | Same construction through the real segmented (`hf_stability_segment_count`) + silence-gated (`extract_active_audio`) pipeline at real-track-scale (180 s) duration; **also written to FAIL against the shipped pre-redesign detector** | TC-091 |
| AC7a | Constant-level signal → DR and LRA near zero | TC-030, TC-032 |
| AC7b | Two-level, gate-calibrated separation → LRA approximates it | TC-033, TC-034 |
| AC7c | LRA differs from naive peak-to-trough | TC-035 |
| AC8a | Band-limited noise in one band dominates | TC-040 |
| AC8b | Equal-energy noise → derived band distribution | TC-041 (seven-band), TC-042 (three-band), TC-044 (negative-control cross-check) |
| AC8c | Boundary-frequency attribution | TC-043 |
| AC9a | Identical L/R → correlation 1.0, width ≈0 | TC-050, TC-056 |
| AC9b | Inverted R → correlation -1.0, mono-sum silent | TC-051, TC-056 |
| AC9c | Uncorrelated noise → correlation ≈0 | TC-052, TC-053 |
| AC9d | Mono-sum level change per case + DEF-203 resolution | TC-054 |
| AC10 | Sanity assertions run in production code, surface in reports | TC-060-069, TC-044 (seven-band negative control) |
| AC11 | Ordering evidence for DEF-201/DEF-203 recorded in defects.md | TC-083, TC-084 |
| AC12 | Ground-truth suite runtime < 30 s | TC-085 |
| AC13 | Additive schema/report consequences, both renderers updated | TC-064, TC-065, TC-086 |
| (NFR) | No regression | TC-087 |
| (NFR) | Reproducibility (fixed seeds) | TC-088 |
| (NFR) | Session-scoped fixture mutation safety | TC-089 |
| (recommended, not a numbered AC) | `k_weight`/`oversample` internal ground truth | TC-070, TC-071, TC-072 |
| (edge case, not a numbered AC) | DC offset | TC-005, TC-014 |
| (edge case, not a numbered AC) | Very quiet input / near-silence gate boundary | TC-003, TC-004 |
| (edge case, not a numbered AC) | Very short file | TC-031, TC-036 |
| (DEF-201 blast radius) | Migration + due-diligence | TC-026, TC-027, TC-028, TC-029 |
| (gap-closing, added post-review — see Revision history v1.2) | Finite (non-silent) stopband floor — probes whether the 40 dB threshold is deep enough for realistic lossy-encoder cutoffs (STORY-002 AC5 relevance) | TC-023 |
| (gap-closing, added post-review — see Revision history v1.4) | DEF-201 REOPENED — tilt+cutoff combination on a short, continuous, ungapped fixture | TC-090 |
| (gap-closing, added post-review — see Revision history v1.4) | DEF-201 REOPENED — same, through the real segmented + silence-gated pipeline at real-track-scale duration | TC-091 |

---

## 12. Mandatory coverage checklist

**Correctness**
- Happy path for each AC: covered throughout §1-9 (one primary ground-truth TC per AC at minimum, per §11's traceability table).
- Boundary values (exactly at threshold, just under, just over): TC-060/TC-061/TC-062/TC-063 (sanity-check predicates, exhaustively per TC-069), TC-020/TC-021 vs. TC-024 (HF threshold-independence boundary for brickwall vs. tilt), TC-003/TC-004 (LUFS absolute-gate boundary).
- Idempotency: this story adds a verification layer and two defect fixes, not a new processing stage — "does processing already-processed audio behave sensibly" (a mastering-pipeline concern) is **not applicable** here. The measurement-layer analogue — do pure measurement functions return identical results when called twice on the same input, and do they leave the input unmutated — is covered by TC-088 (determinism) and TC-089 (non-mutation).
- Bypass/disabled: there is no "disable sanity checks" toggle in this story's design (sanity checks are always-on, advisory metadata per architecture.md §4.1's hard rule) — **not applicable** as a bit-identical-bypass test. The adjacent concept — a fail-severity warning never aborts a run — is covered by TC-067.

**Audio-specific**
- Mono input and stereo input, both: loudness/true-peak/DR are exercised mono (TC-001-003, TC-030) and stereo (TC-010, TC-013, TC-050-057); `mono_sum`/`per_band_stereo_width` are stereo-only by contract and every fixture for them is built explicitly stereo (§7's preamble states this as a rule, not an assumption).
- Multiple sample rates (44.1 kHz and 48 kHz minimum): TC-041/TC-042 explicitly compute and assert both; the HF-extension and true-peak fixtures are sample-rate-parametric by construction (`sr/4`, `sr/2`-relative assertions) and should be run at both rates as part of normal parametrization, though only the spectral-balance tests carry an explicit worked 48 kHz table in this document.
- Silence and near-silence: TC-003 (below absolute gate → `-inf`), TC-055 (both-channels-silent correlation = 1.0), TC-036/TC-057 (empty/degenerate inputs don't crash).
- Full-scale / already-clipping input: TC-016-019 (clipping section).
- Very quiet input (gain-staging blow-up check): TC-003/TC-004 (gate boundary).
- DC offset present: TC-005 (LUFS unaffected), TC-014 (sample peak shifts exactly by the offset).
- Very short file (shorter than any analysis window): TC-031 (DR fallback branch), TC-036 (LRA empty/short-circuit).
- Realistic (non-infinite) lossy-encoder stopband floor, as distinct from an idealized/infinite brickwall floor — the case that determines whether a threshold tuned to fix a false positive (DEF-201) accidentally introduces a false negative on real transcoded material: TC-023.

**Failure modes**
- Corrupt or truncated file, unsupported format, missing file: **not applicable to this suite.** Per AC2, the ground-truth suite loads no `.wav`/`.flac`/`.mp3` files at all — every signal is synthetic and in-memory. File-I/O failure modes belong to STORY-001's own loader-layer test coverage (`errors.py`/`InvalidWavError` and friends), not to this measurement-ground-truth harness. TC-081 audits that this suite indeed contains no file loading, which is the concrete evidence for this exclusion rather than an assumption.
- Wrong channel count than expected: covered indirectly — `mono_sum`/`per_band_stereo_width` are documented as caller-responsible for stereo-only input (not a runtime-guarded error path in the shipped code), so there is no "wrong channel count raises X" behavior to ground-truth here; this is noted as a design property, not a gap, per requirements.md's own statement that "callers are documented as responsible for not calling them on mono."

**Units and precision**
- Every test case above states its unit explicitly (LUFS/LU vs. dBFS vs. dBTP are never conflated) — see in particular TC-010/TC-013 (sample peak, a dBFS quantity, vs. true peak, a dBTP quantity, asserted as genuinely different values) and TC-001-005 (LUFS/LU only, never dBFS used as a stand-in).

---

## 13. Open questions (flagged, not guessed — carried forward from requirements.md/architecture.md, not resolved by this document)

1. **HF rolloff detection numeric tolerance beyond one Welch-PSD bin**: this document reuses the existing `hf_rolloff_test_tolerance_hz=500.0` config figure (already a derived floor per architecture.md), not a new invented number — but requirements.md's open question 2 (whether a wider multiple than one bin is warranted to absorb window/leakage effects) remains open beyond what the shipped config already encodes.
2. **Seven-band adjacent-delta thresholds (25.0/40.0 dB)**: explicitly provisional, per architecture.md §9 item 1 and TC-063's own flag — calibrate against the real five-track reference set before treating as final.
3. **`k_weight`'s exact 20 Hz attenuation figure (TC-072), and its exact 1 kHz filter-only gain (TC-071)**: neither is sourced by this document or by architecture.md as an independently-published BS.1770 anchor point. TC-072's 20 Hz figure needs an authoritative BS.1770-4 Annex 1 or libebur128 reference value before a precise numeric assertion can replace its current sanity-floor-only assertion. TC-071's 1 kHz filter-only gain is bounded (`[0.5, 0.9] dB`) via a cross-check derived from TC-001's own tolerance plus the published `-0.691 dB` fixed offset (see TC-071's revised derivation, `stories/STORY-002/defects.md` DEF-207 item 2) — this is a legitimate derived bound, not a published anchor itself, and a tighter figure would still need an authoritative source of its own before being adopted as ground truth.
4. **AC8a's 20 dB gap and AC9c's `width>=0.8` floor (TC-040, TC-052)**: architect-reasoned, not yet empirically verified against this codebase's actual Welch-averaging depth at the chosen fixture lengths — run once, tighten toward observed-plus-margin.
5. **`band_limited_noise_mono`'s `floor_amplitude=0.005` (TC-040)**: not yet confirmed to keep every non-target band's power away from the `_MIN_POWER=1e-20` floor — verify before finalizing the fixture (architecture.md §10 risk #2).
6. **TC-057's both-silent mono-sum arithmetic**: whether the shipped code guards the double-`-inf` broadband subtraction explicitly or produces `nan` is not confirmed by this document — recorded as a finding to make during implementation, not assumed. (Confirmed empirically since this document's v1.2 pass, per `stories/STORY-002/defects.md`'s "Minor finding, not filed as a defect" entry: the shipped code returns `nan`, does not crash, and `analysis/sanity.py` currently has no check covering `MonoSumResult` fields — left here as-is, since resolving it is a scope question for the architect, not a test-cases.md correction.)
7. **DEF-201's actual pre-fix `rolloff_hz` value for TC-024**: architecture.md's "~2143 Hz" figure is explicitly an illustrative "e.g.," not a prediction — the real value must come from actually running the test, per AC11's own requirement not to record an assumed number.
8. **TC-023's actual result against whatever `hf_rolloff_threshold_db` is configured at run time** is itself an open question this test exists to answer empirically — this document's structural prediction (PASS if the configured threshold is shallower than this fixture's 27.0 dB stopband floor, e.g. the current shipped `6.0`; FAIL if the configured threshold is at or deeper than 27.0 dB, e.g. the originally-proposed `40.0`) is derived from the documented scan algorithm, not a value obtained by running the tool, but the *actual* run — at whatever value is actually configured, including after software-architect's pending DEF-201 revision (previously `40.0`, now trending toward `20.0` per this same test's own finding) — must still be performed and the real number recorded (same discipline as open question 7 above) before routing anything back to the architect.

---

## Revision history

v1 (2026-08-02) — first version of this document. No prior version
existed; no `defects.md` exists yet in `stories/STORY-003/` (checked,
not found) so there was no defect-driven coverage gap to close in this
pass. `stories/STORY-002/defects.md`'s DEF-201/DEF-203 entries are
referenced throughout but not themselves modified by this document —
recording the required evidence in that file (TC-083/TC-084) is
implementation-phase work this document specifies but does not perform.

v1.1 (2026-08-02, same-day correction pass, per advisor review before
finalizing) — four fixes: (1) TC-064's precondition corrected —
`make_stub_measurements()` does not itself call any `check_*` function,
so the warning must be injected explicitly (via a `sanity_warnings`
override or direct assignment), not assumed to appear from the
`hf_rolloff_hz`/`air`-band overrides alone; the original wording would
have made TC-064 fail for a reason unrelated to the renderer-threading
risk it exists to isolate. (2) Added TC-044, a dedicated negative-
control test case that actually calls `check_seven_band_adjacent_deltas`
against TC-041's closed-form white-noise table and asserts `[]` —
previously this assertion existed only as a note on TC-041 with no
runtime check attached, and the note pointed at TC-065 (the wrong test)
instead of a real seven-band-delta assertion. (3) Deleted the empty
TC-023 placeholder (had no fixture/steps/expected-result and was never
in the traceability table); TC-022 and TC-024 already carry the
negative-control role for AC6c/AC6d. (4) Fixed a copy-paste error in
TC-054 referring to "DEF-024" where "DEF-201" was meant. Also upgraded
TC-030 to name the correct entry point for the unrounded DR value
(`_measure_dynamic_range_unrounded` / `dynamic_range_db_exact` —
`measure_dynamic_range()` itself only returns the rounded integer) and
upgraded TC-066 with an explicit negative-result assertion
(`sanity_warnings == []` on TC-050's identical-L=R fixture through
`measure_all()`), since the always-on production sanity checks had no
existing end-to-end negative control anywhere in the current test
suite.

v1.2 (2026-08-02, coordinator-requested gap closure) — added TC-023
(now reusing the ID freed by v1.1's deletion of the empty placeholder),
a new ground-truth test for `measure_hf_extension` using a finite
(non-silent, ~27 dB down) stopband floor rather than the true-brickwall
(infinite/silent floor) construction every other AC6 fixture uses. **The
gap this closes**: TC-020/TC-021/TC-024/TC-025 all use
`brickwall_lowpass_noise_mono` (or its drift variant), whose stopband is
exactly `-inf` dB relative — against any finite threshold, an infinitely
deep stopband crosses below that threshold immediately, so those tests
prove the DEF-201 fix eliminates the *false positive* (ordinary tilted/
pink-noise material wrongly reported as having a cutoff) but prove
nothing about whether the deepened 40 dB threshold introduces a *false
negative* on real-world lossy-encoder material, whose anti-aliasing
stopband is typically only ~20-40 dB down, not silent. This directly
bears on STORY-002 AC5 (using HF-extension rolloff detection to flag/
exclude lossy-source reference tracks) — a threshold too deep to catch a
real encoder's shallower cutoff would silently defeat that purpose.
TC-023's fixture (`brickwall_lowpass_noise_with_floor_mono`, a new
generator) is constructed with an exact, sigma-ratio-derived floor depth
(27 dB below the passband/reference density, by construction, not
measurement) and the test states an explicit, structurally-derived
prediction that it will **fail** against the current shipped 40 dB
threshold — with an explicit instruction not to narrow the fixture to
force a pass, since a forced pass here would hide the exact risk the
test exists to surface. Both the traceability table (§11, new row plus
the AC1/AC10-adjacent HF-ext range updated to include TC-023) and the
mandatory coverage checklist (§12, new "Audio-specific" bullet) were
updated accordingly, and open question 8 was added noting that TC-023's
actual outcome must still be empirically confirmed and recorded, not
assumed from the structural prediction alone.

v1.3 (2026-08-02, defect-driven correction pass — qa-automation-engineer
found these while automating the suite into pytest against this
document's own stated derivations; see `stories/STORY-002/defects.md`
DEF-205 and DEF-207) — four corrections, all documentation/derivation-
arithmetic errors in this test-spec, the same class as the earlier
DEF-106/107/108 precedent, none a production-code defect:

1. **DEF-205 (schema_version "1.1" → "1.2"): no change made to this
   document.** DEF-205 concerns `TC-292`, which lives in **STORY-002's**
   `test-cases.md` (v2, line ~629), not this document — this document
   (STORY-003) has no `TC-292` entry and already states
   `SCHEMA_VERSION == "1.2"` correctly at every point it appears (lines
   in Section 0's "Pre-existing production code" note, TC-068's note,
   and TC-086's steps) — confirmed by grepping this file for `1.1`/`292`
   before making any edit; the only `1.1` hits were this document's own
   `v1.1` revision-label. **This document was already correct on this
   point and required no fix.** The actual DEF-205 target — STORY-002's
   `test-cases.md` TC-292 — remains uncorrected and DEF-205 remains
   **Open**; that correction is explicitly out of scope for this pass
   per the coordinating instruction not to touch STORY-002's
   `test-cases.md` in this revision. Flagging this explicitly so DEF-205
   is not mistakenly assumed closed by this pass.

2. **DEF-207 item 1 (TC-003/TC-004 contradicted TC-001's own stated
   reasoning)**: TC-003 and TC-004 computed their expected LUFS values
   using the naive, uncancelled `dbfs - 0.691` arithmetic, directly
   contradicting TC-001's own derivation one section earlier (that 1 kHz
   is BS.1770's calibration-neutral frequency, where the K-weighting
   shelf gain and the -0.691 dB fixed offset net to ≈0 dB, not -0.691 dB
   uncancelled). Corrected TC-003's derivation prose (block loudness for
   its -80 dBFS fixture now stated as ≈-80.04 LUFS, not ≈-80.69 LUFS —
   its `-inf` pass/fail conclusion is unaffected either way, since -80
   dBFS sits far below the gate under both arithmetics). Corrected
   TC-004's expected value from `-68.69` to `-68.04` LUFS (tolerance kept
   at the original `±0.1` LU, not tightened), its preconditions' "≈1.3 dB
   above the gate" figure to "≈1.96 dB," and added an explicit Derivation
   paragraph stating the corrected ≈-69.96 dBFS RMS absolute-gate
   boundary (not the previously-implied ≈-69.3 dBFS). Both corrections
   trace to `stories/STORY-002/defects.md` DEF-207 item 1's own empirical
   cross-check (a fixed, level-independent ≈-0.0354 dB net offset at 1
   kHz, measured across seven RMS levels from -80 to -20 dBFS) — cited as
   justification for the existing tolerance's adequacy, not adopted as a
   tighter expected value.

3. **DEF-207 item 2 (TC-071's 1 kHz figure conflated the combined-system
   calibration-neutrality with the K-weighting filter's own isolated
   gain)**: TC-071 previously asserted the filter's own gain at 1 kHz
   should read `≈0 dB (±0.5 dB)`, using "same basis as TC-001" as its
   derivation — but TC-001's calibration-neutrality claim is about the
   filter gain *combined with* BS.1770's separate `-0.691 dB` offset, not
   about the filter in isolation; measured directly, the filter-only gain
   at 1 kHz is `≈+0.70 dB`, outside the stated tolerance. Retitled TC-071
   to distinguish the two rows explicitly, kept the 10 kHz shelf-plateau
   row unchanged (a genuine BS.1770-4 published anchor, unaffected by
   this error), and reframed the 1 kHz row as a **derived cross-check
   bound** (`[0.5, 0.9] dB`, from TC-001's own `±0.1` LU tolerance plus
   the published `-0.691 dB` offset), not a re-pinned ground-truth
   number obtained by running the tool — explicitly labelled as such,
   per this document's own Section 0 rule against letting a regression
   lock stand in for a correctness test. Extended open question 3 (§13)
   to cover this bound alongside TC-072's existing 20 Hz open item.

4. **DEF-207 item 3 (TC-023's "current shipped config" sentence
   contradicted this document's own Section 0)**: TC-023's "Analytically
   predicted outcome" paragraph previously stated it was reasoning
   "against the current shipped config (`hf_rolloff_threshold_db=40.0`)"
   while Section 0 states elsewhere that the shipped value is still
   `6.0` (DEF-201 unfixed) — two mutually exclusive claims in the same
   document. Rewrote the paragraph as an explicit function of whatever
   `hf_rolloff_threshold_db` is configured at run time relative to this
   fixture's fixed, by-construction `27.0` dB stopband floor (`>= 27.0`
   dB configured → predicted FAIL; `< 27.0` dB configured → predicted
   PASS), stated that the current shipped `6.0` value predicts a PASS
   (not the previous draft's unconditional FAIL), and noted that the
   architect's DEF-201 fix target is itself under revision (previously
   `40.0`, now trending toward `20.0`) without hardcoding either number
   into the prediction — matching what the automated test already
   asserts against (per DEF-207's own note that the automated test was
   already written value-agnostic). Propagated the same fix to the
   instruction and "if the result disagrees" paragraphs immediately
   following (removed hardcoded `40 dB`/`40+ dB` language in favor of
   "the configured threshold depth"), and to open question 8 (§13),
   which carried the identical stale-`40.0` phrasing.

No other content was changed in v1.3, per the coordinating instruction
to make targeted corrections only.

v1.4 (2026-08-03, DEF-201 REOPENED — HF-extension ground-truth gap
closure) — `stories/STORY-002/defects.md`'s DEF-201 entry was reopened
(james, review of `Reference Tracks/reference_set_report.md`): the first
fix (`hf_rolloff_threshold_db` 6.0 → 20.0) changed the numbers but not
the method, and real reference tracks now report implausible,
universally-unstable rolloffs. The reopened entry requires four
ground-truth test cases be confirmed against what already exists in
this document, plus (per the coordinating instruction for this
revision) a fifth, closely related fixture, before any slope-based
redesign lands. **Per the coordinating instruction for this revision,
only the HF-extension section (§4/§4.1), the traceability table (§11),
and this Revision history entry were modified — no other section of
this document was touched.**

1. **Checked which of the four required cases already existed, rather
   than assuming**: (a) full-band pink noise, no cutoff — already
   **TC-024** (AC6d), continues to pass at the current shipped
   `hf_rolloff_threshold_db=20.0`; (b) white noise brickwalled at
   15 kHz — already **TC-020** (AC6a); (c) white noise brickwalled at
   8 kHz — already **TC-021** (AC6b); (d) pink noise brickwalled at
   15 kHz — **genuinely new, not present anywhere in v1.3** — added as
   **TC-090**.
2. **The wiring-gap question, answered explicitly, per the reopened
   entry's own instruction to investigate it — this is the single most
   important correction in this revision**: TC-024 passing at the
   current threshold does **not** mean it is unwired from the function
   that produced the real, wrong reference-set measurements, and does
   **not** contradict the reopening. TC-024's fixture has no real cutoff
   anywhere in it — it tests only that ordinary tilt alone is not
   mistaken for a cutoff, which correctly holds. It cannot test, and was
   never designed to test, whether a **real** cutoff is still found
   correctly when tilt is *also* present below it — a structurally
   different property. TC-090 adds that missing positive case, with a
   worked derivation (§4.1, TC-090) showing precisely why TC-024's own
   shallow `-3.01 dB/octave` tilt (the existing `pink_noise_mono`
   shaping) is analytically too shallow, at the current `20.0` dB
   threshold depth, to have ever reproduced this bug — only a steeper
   `-6.02 dB/octave` tilt (the steep end of the "~-3 to -6 dB/octave"
   range the reopened entry itself cites) does, and the derivation shows
   exactly where it does (`f_cross = 1000·10^(hf_rolloff_threshold_db/20)
   = 10,000 Hz` at the shipped `20.0` dB threshold). A short status note
   to this same effect was also added directly to TC-024 itself (§4,
   within the HF-extension section), since that is where a reader
   encountering TC-024 would need it.
3. **Added TC-090** (§4.1) — `pink_brickwall_lowpass_noise_mono`, a new
   generator combining a `-6.02 dB/octave` power-law tilt with a genuine
   FFT-domain brickwall at 15 kHz, on a short (3 s), continuous,
   `ref_config(hf_min_duration_s=2.0)` fixture matching every other AC6
   test's construction pattern. Ground truth (ex-construction): `rolloff_hz
   ≈ 15,000 Hz`. Analytically predicted actual result against the shipped
   detector: `≈10,000 Hz` — **stated explicitly as required to FAIL**
   against the current, unmodified, pre-redesign code, not written as if
   a slope-based redesign has already landed. Instructs recording the
   actual run result in `stories/STORY-002/defects.md`'s DEF-201
   (REOPENED) entry before any fix, per this document's own established
   AC6/AC11 discipline.
4. **Added TC-091** (§4.1), beyond the reopened entry's literal four
   items, per the coordinating instruction — the same TC-090 construction
   built at real-track scale (180 s total: six 24 s active spans sharing
   the identical 15 kHz/−6.02 dB/octave construction, interleaved with
   six 6 s genuinely near-silent blocks that `extract_active_audio`
   actually removes) so the multi-segment (`hf_stability_segment_count=5`)
   split runs on real, non-contiguous, concatenated active audio with
   genuine splice discontinuities, rather than a single continuous
   buffer. **A correction to how this second gap was originally framed
   is stated explicitly in §4.1**: direct reading of the shipped
   `analysis/hf_extension.py` shows the "n_segments reduced to 1" fallback
   does **not** actually apply to any existing 3-4 s HF-extension fixture
   (including TC-090) — `active.size // 5` for a 3 s buffer is far above
   the 8-sample fallback floor, so those fixtures already exercise the
   `n_segments==5` branch and always have. The literal "only ever hits
   the n_segments==1 branch" framing is not repeated as fact in this
   document; the real, verified gap is narrower (no existing fixture's
   `extract_active_audio` call ever actually removes anything, and none
   run at real-track-scale duration/Welch-averaging depth per segment),
   and TC-091 is built specifically to close that verified gap, not the
   originally-assumed one. TC-091's `rolloff_hz` prediction (`≈10,000 Hz`,
   same derivation as TC-090, also required to FAIL) is stated with the
   same evidentiary discipline; its `stable` prediction is explicitly
   left open within TC-091 itself, since the reopened entry's own
   real-world evidence (universal instability) does not obviously match
   this fixture's naive prediction of a stable-but-wrong result, and
   this document does not paper over that discrepancy.
5. **Traceability table (§11)**: added two new rows, one each for
   TC-090 and TC-091 (both explicitly labelled "written to FAIL against
   the shipped pre-redesign detector"), placed adjacent to the existing
   AC6a-AC6e rows, plus a corresponding pair of rows in the table's
   existing "gap-closing, added post-review" grouping at the bottom
   (matching the pattern already established there for TC-023). No
   existing traceability-table row's text was altered.

Per the task instruction for this revision, no content outside
Section 4/4.1 (HF extension), the traceability table (§11), and this
Revision history section was modified — all other sections above are
reproduced unchanged from v1.3.
