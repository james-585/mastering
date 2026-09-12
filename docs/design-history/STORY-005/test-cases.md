# STORY-005 — Test Cases: DEF-205 Per-Segment Gate False Positive (Chemical Brothers)

Governed by `CLAUDE.md`, `docs/DOMAIN.md`, `docs/ARCHITECTURE.md`,
`docs/HANDOFF.md` (H-rules). Derived from `stories/STORY-005/requirements.md`
(AC1–AC6) and `stories/STORY-005/architecture.md` (v1.2, post-Gate-1).

Resolution selected: **option (c)** — explicit documentation and machine-readable
caveat. Gate functions (`_gate_scan`, `_floor_onset_index`, `_detect_cliff`) are
unchanged. Two new optional fields added to `HfExtensionResult`:
`per_segment_reliability_caveat: Optional[str]` and
`hf_band_limit_whole_track_margin_db: Optional[float]`.
`SCHEMA_VERSION` bumped `"2.1"` → `"2.2"`.

No `defects.md` exists for STORY-005 at the time of writing; no gap-driven
revision was required. If one is added later that reveals a coverage gap, this
document's revision-history section must record it.

---

## Out-of-scope categories

The following mandatory-checklist categories are explicitly N/A for this story:

- **Corrupt/truncated file, missing file, unsupported format, wrong channel
  count**: `measure_hf_extension` accepts an in-memory `ndarray`, not a file
  path. File-I/O error handling is unchanged and belongs to the ingestion layer,
  not this story's test surface.
- **Loudness (LUFS/dBTP), clipping, dynamic range, DC offset**: this story is
  analysis-only; the mastering chain is untouched. No audio is written or
  mutated.
- **AC4 (eliminate Chemical Brothers segment-1 false positive)**: explicitly
  scoped to options (a) and (b) by requirements.md §Effect 1 ("Left in place by
  option (c) — documented as a known limitation") and by AC4's own "(options a
  and b)" label. Under option (c), Chemical Brothers segment 1 retaining 14066 Hz
  is **expected and disclosed via `per_segment_reliability_caveat`**, not a
  defect. Any future story selecting option (a) must re-open this AC and supply
  the 25-segment pre-slope instrumented run that AC1 requires before any
  parameter value can be proposed. See gate1-review F5.
- **AC6(b) ("For options (a) and (b): assert `per_segment_hf_band_limit_hz`
  contains no false positives")**: scoped to options (a) and (b) by requirements.md
  AC6 clause (b) and by architecture §3.5. Under option (c), Chemical Brothers
  segment 1 retaining 14066 Hz is expected; AC6(b)'s assertion of zero per-segment
  false positives does not apply. The applicable clause is AC6(c) — caveat field
  is present and non-empty — which TC-501, TC-505, TC-506, and TC-507 cover.

---

## Fixture legend

Unless stated otherwise, all fixtures are short synthetic buffers reusing the
existing helpers in `tests/ref_helpers.py` and count toward the 60-second
fast-suite bound. Tests marked **Slow** (`@pytest.mark.slow`) are isolated from
that bound per DEF-106 / STORY-002 precedent; the slow marker is registered as
`"slow: longer-running pipeline-level tests"` in `pyproject.toml`.

Signal helpers referenced below:
- `brickwall_lowpass_noise_mono(SR, duration_s, cutoff_hz, seed, amplitude)` —
  white noise, digital-zero stopband above cutoff.
- `brickwall_lowpass_noise_with_floor_mono(SR, duration_s, cutoff_hz,
  floor_below_db, seed, passband_sigma)` — as above with a finite stopband floor.
- `white_noise_mono`, `pink_noise_mono` — full-band signals, no cliff.
- `to_stereo(mono)` — duplicates mono to two-channel.
- `ref_config(...)` — constructs config with test-appropriate overrides.

Functions under test:
- `suno_mastering.analysis.hf_extension.measure_hf_extension`
- `suno_mastering.report.reference_render.render_markdown`
- `suno_mastering.report.reference_render.render_json`
- `suno_mastering.report.reference_builder.SCHEMA_VERSION`

---

## A. Schema version (AC6 — structural correctness)

### TC-500 — Schema version constant is "2.2"

- **Preconditions**: `reference_builder.py` is the version produced by this
  story's implementation.
- **Steps**:
  1. Import `suno_mastering.report.reference_builder`.
  2. Assert `reference_builder.SCHEMA_VERSION == "2.2"`.
  3. Construct a `ReferenceSetReport` via `build_reference_set_report` (or
     instantiate `ReferenceSetReport` directly with `schema_version` defaulting
     from the module constant) and assert `report.schema_version == "2.2"`.
  4. In `tests/test_ref_ac9_output.py`, update
     `test_tc292_schema_version_matches_current_shipped_value` to assert
     `report.schema_version == "2.2"` (from `"2.1"`). This supersedes the
     TC-508 action from the parent's prompt; TC-508 is folded into this test.
     The test provides the regression lock that detects any future unintentional
     bump or rollback.
- **Expected result**: both assertions pass. The constant and the
  report field are `"2.2"`.
- **Pass/fail criterion**: fails if either asserts `"2.1"` or any value other
  than `"2.2"`. The `test_tc292` update is a prerequisite to the full test
  suite running green; it is a **regression lock** (change-detection only),
  not a correctness test — the version string's ground truth is requirements.md
  NFR §Schema version ("additive fields → MINOR bump").
- **Covers**: requirements.md NFR §Schema version. AC6 (structural completeness
  of the schema change). TC-508 (parent prompt) folded here.
- **Type**: functional / regression lock.

---

## B. `per_segment_reliability_caveat` field (AC5, AC6)

### TC-501 — Caveat fires on a fast drift-detection fixture (positive control)

- **Preconditions**: the existing three-step drift fixture from `test_tc025`:
  white noise brickwalled at 15 kHz for 1.5 s, then 12 kHz for 1.5 s, then
  8 kHz for 1.5 s (total 4.5 s, SR=44100). The caveat must fire on this
  fixture. Proof by construction: `test_tc025` already asserts
  `len(non_none_segs) >= 2` and `max(non_none_segs) - min(non_none_segs) >
  hf_stability_tolerance_hz`. The whole-track gate selects `i_max` at the
  highest qualifying candidate, so WT ≈ 15 000 Hz. Therefore
  `min(non_none_segs) ≤ WT − tolerance_hz` (i.e., ≤ 13 000 Hz), meaning at
  least one non-None per-segment value disagrees with WT by more than the 2 000 Hz
  default tolerance. The caveat's population condition is satisfied
  by the same TC-025 construction, not by a separate claim. Note: the fixture
  contains segments near both 12 000 Hz and 8 000 Hz, giving maximum
  per-segment disagreements of ≈ 3 000 Hz and ≈ 7 000 Hz respectively; the
  largest disagreement is 7 000 Hz by design. TC-517 uses this value.
- **Steps**:
  1. Generate the TC-025 three-step audio (see `test_tc025_drift_detection_fires_on_changing_cutoff`).
  2. Run `measure_hf_extension(audio, SR, config)` with `ref_config(hf_min_duration_s=2.0)`.
  3. Assert `result.per_segment_reliability_caveat is not None`.
  4. Assert `len(result.per_segment_reliability_caveat) > 0`.
  5. Assert the caveat string contains the substring `"false positive"` (or
     equivalent per AC5(a): that per-segment values may fire on programme-content
     spectral decline unrelated to a band-limit wall).
  6. Assert the caveat string contains a reference to the actual tolerance value
     from config, not a hardcoded literal — see TC-516 for the config-interpolation
     proof.
- **Expected result**: `per_segment_reliability_caveat` is a non-empty string
  satisfying all four keyword assertions.
- **Note**: this uses the same fast fixture as the existing TC-025 test; no new
  fixture is required for the caveat's positive path. TC-507 is a separate
  slow geometry-faithful test.
- **Pass/fail criterion**: fails if the field is `None` or the string is empty
  or lacks the required content.
- **Covers**: AC5(a), AC6(c).
- **Type**: functional / audio-quality.

### TC-502 — Caveat is None for a clean detection (negative control — non-regression)

- **Preconditions**: brickwall at 15 kHz, white noise, SR=44100, 3 s
  (`brickwall_lowpass_noise_mono`). All per-segment values ≈ 15 000 Hz, all
  within 2 000 Hz of the whole-track value. Analytically: a stationary brickwall
  signal produces the same cliff in every segment.
- **Steps**:
  1. Generate the stationary brickwall fixture (TC-020's signal).
  2. Run `measure_hf_extension` with `ref_config(hf_min_duration_s=2.0)`.
  3. Assert `result.per_segment_reliability_caveat is None`.
- **Expected result**: caveat field is `None`.
- **Pass/fail criterion**: any non-None value is an over-fire defect (see
  architecture §11 R2 risk).
- **Covers**: AC5, AC6(c), non-regression check (architecture R2 mitigated).
- **Type**: functional / negative control.

### TC-513 — Caveat is None when segments abstain but no non-None disagreement (Wavy Gravy analogue)

**This test covers the most dangerous implementation error**: a developer writing
`if s is None or abs(s - WT) > tol` (OR instead of AND) would fire the caveat
on any track where some segments returned `None` — including the four honest
abstentions in the baseline (Chemical Brothers segs 2/5, Wavy Gravy segs 2/3).
TC-502 does not catch this because its brickwall signal produces all-agreeing
non-None values. This test provides a fast synthetic discriminating fixture.

If the synthetic construction fails to produce per-segment `None` values, the
fast coverage fallback is TC-512 (Slow) — which exercises the identical failure
mode on real data: Wavy Gravy has two `None` abstentions and all non-None values
exactly at 20 475 Hz (|diff| = 0 < tolerance). An OR-instead-of-AND implementation
fires the caveat on Wavy Gravy and TC-512 catches it. If TC-513's precondition
cannot be met synthetically, document that TC-512 provides the coverage and
leave TC-513 as a best-effort fast supplement.

- **Preconditions**: five-segment-split audio where some segments return `None`
  and the non-None values all agree with the whole-track result. Construct: 2.5 s
  of brickwall noise at 15 kHz (segments 1, 3, 5 receive wall) + 2.5 s of
  full-band white noise (segments 2, 4 lack sufficient spectral structure →
  likely return `None`). SR=44100. The non-None per-segment values are all near
  15 000 Hz; none disagrees with the whole-track by more than 2 000 Hz.
  The developer must verify `per_segment_hf_band_limit_hz` contains at least one
  `None` before asserting on the caveat, and log a note if the construction
  fails to produce any abstentions (fall back to TC-512 coverage, noted above).
- **Steps**:
  1. Generate the 5 s alternating fixture.
  2. Run `measure_hf_extension`.
  3. Assert `result.per_segment_reliability_caveat is None`.
- **Expected result**: `None`. The population condition requires a non-None
  per-segment value that disagrees; `None` abstentions do not satisfy it.
- **Covers**: AC5(b) (None is an honest abstention, distinct from a false
  positive), AC6(c). Fast-suite coverage of the OR-instead-of-AND defect
  class, supplemented by TC-512 on real data.
- **Type**: functional / negative control. Highest-value negative control in
  this story (fast path); TC-512 is the real-data fallback.

### TC-514 — Caveat is None when whole-track result is None

- **Preconditions**: any input that produces `hf_band_limit_hz = None`. Use
  white noise (3 s, `white_noise_mono`) or pink noise (`pink_noise_mono`) —
  both already verified to return `None` by TC-022 / TC-024.
- **Steps**:
  1. Generate white-noise or pink-noise fixture.
  2. Run `measure_hf_extension`.
  3. Assert `result.hf_band_limit_hz is None`.
  4. Assert `result.per_segment_reliability_caveat is None`.
- **Expected result**: both fields `None`. The population condition has an
  explicit `whole_track_hz is not None` guard (architecture §5.1); this test
  exercises that guard.
- **Covers**: AC5, AC6(c), sanity assertion.
- **Type**: functional / edge case.

### TC-515 — Both new fields are None when `insufficient_duration = True`

- **Preconditions**: audio shorter than `hf_min_duration_s`. Use any signal ≤
  the configured minimum (architecture §9.3 confirms the insufficient-duration
  path short-circuits before the cliff detector runs).
- **Steps**:
  1. Generate a 0.5 s noise burst.
  2. Run `measure_hf_extension` with `ref_config(hf_min_duration_s=2.0)`.
  3. Assert `result.insufficient_duration is True`.
  4. Assert `result.per_segment_reliability_caveat is None`.
  5. Assert `result.hf_band_limit_whole_track_margin_db is None`.
- **Expected result**: both new fields `None`; `insufficient_duration True`.
- **Covers**: AC5, AC6(c), edge case (very short file).
- **Type**: functional / edge case.

### TC-516 — Caveat string interpolates config tolerance, not hardcoded "2000"

The architecture §5.1 explicitly requires `config.hf_stability_tolerance_hz`
to be interpolated into the caveat string so the text stays consistent with the
threshold actually applied. Asserting only the default-config output passes a
hardcoded implementation. This test uses a non-default tolerance value to
distinguish interpolation from a literal string.

- **Preconditions**: the TC-025 three-step drift fixture (same signal as TC-501).
  The largest per-segment disagreement is ≈ 7 000 Hz (8 kHz segment vs. WT 15 000 Hz),
  so a tolerance of 1 500 Hz is comfortably exceeded and the caveat fires.
- **Steps**:
  1. Run `measure_hf_extension` with `ref_config(hf_min_duration_s=2.0,
     hf_stability_tolerance_hz=1500)`.
  2. Assert `result.per_segment_reliability_caveat is not None`.
  3. Assert `"1500"` (or `"1500 Hz"` / `"1500.0"`) appears in the caveat string.
  4. Assert `"2000"` does NOT appear in the caveat string (rules out hardcoding
     the default value).
- **Expected result**: caveat string contains the tolerance value that was
  passed in config, not the default 2 000 Hz.
- **Covers**: AC5(b) content requirement; architecture §5.1 interpolation note.
- **Type**: functional.

### TC-517 — Caveat fires just above the tolerance boundary, not just below

Boundary-value test on the `> hf_stability_tolerance_hz` comparison.

The TC-025 fixture contains per-segment values near both 12 000 Hz and 8 000 Hz.
With WT ≈ 15 000 Hz, the maximum disagreement `d` is approximately 7 000 Hz
(the 8 kHz segment). The boundary must be tested against `d`, not against the
3 000 Hz intermediate. Hardcoding 3 000 Hz as the boundary is wrong because the
7 000 Hz segment still fires the caveat at any tolerance < 7 000 Hz.

The recommended approach derives the boundary from a runtime measurement rather
than a hardcoded value, making the test immune to ±500 Hz Welch drift on
per-segment values:

- **Preconditions**: TC-025 three-step drift fixture.
- **Steps**:
  1. Run `measure_hf_extension` with the default config to obtain the actual
     `per_segment_hf_band_limit_hz` values. Compute the maximum disagreement:
     ```python
     d = max(
         abs(s - result.hf_band_limit_hz)
         for s in result.per_segment_hf_band_limit_hz
         if s is not None
     )
     ```
     Assert `d > 2000.0` (validates the fixture has the required disagreement).
  2. **No-fire run**: re-run `measure_hf_extension` with
     `ref_config(hf_stability_tolerance_hz=d + 500)`. The largest disagreement
     `d` now falls strictly below the threshold. Assert
     `result.per_segment_reliability_caveat is None`.
  3. **Fire run**: re-run with
     `ref_config(hf_stability_tolerance_hz=d - 500)`. The largest disagreement
     `d` now exceeds the threshold. Assert
     `result.per_segment_reliability_caveat is not None`.
- **Expected result**: caveat absent when threshold exceeds every disagreement;
  caveat present when threshold is below the maximum disagreement. The ± 500 Hz
  bracket is wide enough to survive Welch-level drift in `d` across runs.
- **Covers**: AC5, AC6(c); boundary-value correctness.
- **Type**: functional / boundary value.

### TC-519 — Determinism: both new fields are bit-identical across two identical runs

- **Preconditions**: TC-025 three-step drift fixture (caveat expected non-None).
- **Steps**:
  1. Run `measure_hf_extension` twice with identical audio buffer and config.
  2. Assert `result1.per_segment_reliability_caveat == result2.per_segment_reliability_caveat`.
  3. Assert `result1.hf_band_limit_whole_track_margin_db == result2.hf_band_limit_whole_track_margin_db`.
- **Expected result**: exact equality on both fields. Requirements.md NFR
  §Reproducibility: given the same input and config, output must be bit-identical.
- **Covers**: requirements.md NFR §Reproducibility.
- **Type**: non-functional.

---

## C. AC5 content requirements — all three clauses

### TC-521 — AC5 caveat string covers all three required clauses

- **Preconditions**: caveat string produced by TC-501 (any non-None caveat).
- **Steps**: read `result.per_segment_reliability_caveat` and check all three
  AC5 clauses are substantively present:
  1. AC5(a): assert the string asserts that per-segment values on complex
     material may be **false positives** where the gate fires on spectral
     content unrelated to a band-limit wall. Keyword check: `"false positive"`
     (case-insensitive).
  2. AC5(b): assert the string asserts that a non-None value outside the
     tolerance is a false positive that must **not be treated as an alternative
     band-limit estimate**, and that `None` is an **honest abstention** — a
     distinct state. Keyword checks: `"alternative"` or `"estimate"`, and
     `"abstention"` or `"honest"`.
  3. AC5(c): assert the string asserts that `stable=False` with low confidence
     and a strong whole-track margin is the **correct report** under current
     gate parameters, not a detector failure. Keyword check: `"correct"`.
- **Expected result**: all keyword checks pass.
- **Note**: keyword substring checks are necessary but not sufficient. A human
  reviewer must read the caveat string against AC5(a)(b)(c) verbatim as part
  of Gate 1 sign-off. This test prevents silent omission; it cannot prevent
  technically-present-but-misleading phrasing.
- **Covers**: AC5(a)(b)(c).
- **Type**: functional / content correctness.

---

## D. `hf_band_limit_whole_track_margin_db` field (AC5, AC6)

### TC-503 — Margin field populated when cliff detected, by-construction values

Two sub-cases with analytically derived expected margins.

**Sub-case A — digital-zero brickwall, leftward-dominated (TC-431 fixture)**

- **Preconditions**: `brickwall_lowpass_noise_mono(SR=44100, duration_s=3.0,
  cutoff_hz=16000.0, seed=1, amplitude=0.3)`. Digital-zero stopband:
  `suffix_max[j*] ≈ −200 dBFS`. By construction (architecture §11.7 TC-431):
  j* = i_max + 1; leftward margin = `levels_db[i_max] − L = hf_cliff_required_drop_db = 8.0 dB`
  exactly; rightward margin ≈ 108 dB. Two-sided minimum = 8.0 dB.
- **Steps**:
  1. Generate mono fixture; wrap with `to_stereo`.
  2. Run `measure_hf_extension` with `ref_config(hf_min_duration_s=2.0,
     hf_stability_segment_count=1)`. `segment_count=1` so the single-segment
     Welch PSD processes the full audio, making `hf_band_limit_robustness_db`
     and `hf_band_limit_whole_track_margin_db` both derived from the same
     underlying computation — a wiring check.
  3. Assert `result.hf_band_limit_hz is not None`.
  4. Assert `result.hf_band_limit_whole_track_margin_db is not None`.
  5. Assert `result.hf_band_limit_whole_track_margin_db == pytest.approx(8.0, abs=1.0)`.
  6. Assert `result.hf_band_limit_whole_track_margin_db > 0.0` (sanity bound).
- **Expected result**: ≈ 8.0 ± 1.0 dB. Derivation: leftward = `hf_cliff_required_drop_db`
  algebraically when j* = i_max + 1 on a digital-zero stopband (architecture
  §11.7 TC-431 docstring). A value substantially below 7.0 dB indicates j*
  is not at i_max + 1.

**Sub-case B — finite-floor brickwall, rightward-dominated (TC-430 fixture)**

- **Preconditions**: `brickwall_lowpass_noise_with_floor_mono(SR=44100,
  duration_s=3.0, cutoff_hz=16000.0, floor_below_db=10.0, seed=1,
  passband_sigma=0.15)`. Rightward margin by construction = `floor_below_db −
  hf_cliff_required_drop_db = 10 − 8 = 2.0 dB`. Leftward margin ≈ 8.0 dB.
  Two-sided min = 2.0 dB.
- **Steps**: same as Sub-case A except assert
  `result.hf_band_limit_whole_track_margin_db == pytest.approx(2.0, abs=0.5)`.
- **Expected result**: ≈ 2.0 ± 0.5 dB. Derivation identical to TC-430
  (architecture §11.7 docstring). A value near 8.0 dB indicates the
  implementation returned the leftward margin rather than the two-sided minimum.

**Wiring assertion (Sub-case A only)**

At `segment_count=1`, the per-segment array contains one element whose
Welch PSD is derived from the full audio — nominally the same computation
as the whole-track detector. Assert:
```
abs(result.hf_band_limit_whole_track_margin_db
    - result.hf_band_limit_robustness_db) < 1.0
```
A large difference indicates the developer assigned the wrong variable to one
of the two fields (architecture R3 risk).

- **Covers**: AC5 (new field correctly populated), AC6(c), architecture R3.
- **Type**: audio-quality / correctness.

### TC-504 — Margin field is None when no cliff detected

- **Preconditions**: white noise, 3 s, SR=44100. No cliff → `hf_band_limit_hz = None`.
- **Steps**:
  1. Run `measure_hf_extension`.
  2. Assert `result.hf_band_limit_hz is None`.
  3. Assert `result.hf_band_limit_whole_track_margin_db is None`.
- **Expected result**: both `None`. The population condition requires
  `hf_band_limit_hz is not None` (architecture §5.1).
- **Covers**: AC5 (None-branch coverage), AC6(c).
- **Type**: functional / edge case.

---

## E. JSON and markdown propagation (AC5, AC6)

### TC-505 — Caveat propagates to JSON via `dataclasses.asdict`

Architecture §5.3: `render_json` uses `dataclasses.asdict(report)` (verified at
`reference_render.py` line 25). No explicit change to `render_json` is
specified; propagation is automatic. This test verifies the automatic path
actually carries the field.

- **Preconditions**: TC-025 drift fixture producing a non-None caveat (fast,
  no new fixture needed).
- **Steps**:
  1. Run `measure_hf_extension` to obtain `result`.
  2. Call `dataclasses.asdict(result)`.
  3. Assert `"per_segment_reliability_caveat"` key is present in the resulting
     dict.
  4. Assert `d["per_segment_reliability_caveat"] is not None`.
  5. Assert `d["per_segment_reliability_caveat"] == result.per_segment_reliability_caveat`.
  6. Also assert `"hf_band_limit_whole_track_margin_db"` key is present.
  7. Assert `d["hf_band_limit_whole_track_margin_db"] is not None`.
- **Expected result**: both keys present and equal to their in-memory values.
- **Covers**: AC5 (caveat in JSON), AC6(c).
- **Type**: functional.

### TC-506 — Caveat appears in markdown rendering

Architecture §5.3 adds a rendering block to `_track_section` (lines 116–117 of
`reference_render.py`): the literal string
`"  - Per-segment reliability caveat: {caveat_string}"`.
This test closes R4 (silent omission of the rendering block).

- **Preconditions**: TC-025 drift fixture (fast). A minimal `ReferenceSetReport`
  containing one track with the drift-fixture `HfExtensionResult`.
- **Steps**:
  1. Build a report object containing the drift-fixture result.
  2. Call `suno_mastering.report.reference_render.render_markdown(report)`.
  3. Assert `result.per_segment_reliability_caveat in md` (verbatim containment).
- **Expected result**: the caveat string appears verbatim in the markdown output.
- **Covers**: AC5 (caveat in markdown), AC6(c), R4 closure.
- **Type**: functional.

### TC-518 — Whole-track margin appears in markdown rendering

Architecture §5.3 also adds a second rendering block to `_track_section`
(lines 118–119 of `reference_render.py`), producing the literal prefix
`"  - Whole-track j* margin: "`. Parent's TC-506 and TC-507 both address the
caveat block only; neither covers this second new block. Uncovered until this
test.

- **Preconditions**: any fixture with a non-None `hf_band_limit_whole_track_margin_db`
  (e.g. the digital-zero brickwall from TC-503 Sub-case A). A minimal report
  containing that result.
- **Steps**:
  1. Call `render_markdown(report)`.
  2. Assert `"Whole-track j* margin"` appears in the markdown output. This is
     the exact prefix produced by `reference_render.py` line 119; no escaped
     variant is needed.
  3. Assert the formatted margin value (e.g., `"8.00 dB"` for the
     leftward-dominated brickwall case where the expected value is ≈ 8.0 dB)
     appears in the output near that prefix.
- **Expected result**: the rendering block for `hf_band_limit_whole_track_margin_db`
  is present in the markdown.
- **Covers**: AC5 (both new fields rendered), R4 (second block).
- **Type**: functional.

---

## F. AC6 geometry-faithful slow fixture

### TC-507 — Segment-level gate false positive, geometry-faithful (~250 s)

This is the primary AC6 fixture. It exercises the segment-level PSD geometry
that matches Chemical Brothers (~73 Welch windows per 50-second segment) and
directly verifies the false-positive detection mechanism without requiring the
real reference track.

- **Mark**: `@pytest.mark.slow`. Architecture §9.2: the developer must time
  the full fixture and apply the slow marker if it exceeds approximately
  20 seconds.
- **Preconditions**:

  **Signal design** (architecture §9.1 + gate1-review F4):

  1. Generate **mono** `float64` signal at SR=44100, total duration ≈ 250 s
     (`≈ 11 025 000 samples`). Use mono throughout — `measure_hf_extension`
     calls `_to_mono` as its first action; stereo provides no coverage benefit
     and doubles allocation cost.

  2. **Base signal**: white noise hard-brickwalled at `F_real ≈ 20 000 Hz`
     using `scipy.signal.firwin`. Stopband ≥ 50 dB below passband. This
     provides the real cliff that the whole-track detector must find.

  3. **Segment-1 overlay** (first `n_samples / 5` samples only):
     - Superimpose a secondary noise component filtered to produce a ≥ 8 dB
       drop in the 12–15 kHz region with a pre-slope < 12 dB/oct in the
       preceding octave. Target `F_false ≈ 12 500–14 000 Hz`. This replicates
       the mechanism of the Chemical Brothers segment-1 false positive.
     - Inject additional broadband noise **above F_real** in segment 1 only,
       at approximately `passband_level − 6 dBFS`. This fills in the stopband
       within the first-segment window so the real cliff at F_real does NOT
       produce an 8 dB drop in that window (the drop is ≈ 2 dB after injection;
       see gate1-review F4 level-calibration derivation). Above F_real noise at
       `passband_level − 6 dBFS` contributes `1/5` weight in the whole-track
       PSD (`passband_level − 6 − 7 dBFS`), still leaving ≥ 8 dB apparent cliff
       at F_real visible to the whole-track detector.

  4. **Constant broadband level throughout** all 250 seconds — not just the
     injected segment. This prevents `extract_active_audio` from gating out
     low-energy transitions and shifting the 1/5 segment boundary.

  5. **Construction-time verification** (before running full assertions):
     call `compute_psd` + `log_band_levels_db` on segment 1 only and verify:
     - The 12–15 kHz region shows a local drop ≥ 8 dB with local pre-slope
       < 12 dB/oct (gate-qualifying).
     - The F_real cliff in segment 1 is NOT gate-qualifying (the injection
       raised the stopband above the 8 dB drop threshold within the window).
     - The whole-track PSD still shows ≥ 8 dB cliff at F_real.
     Assert these in the test body before running `measure_hf_extension`
     so that a calibration failure produces a diagnostic about the signal,
     not a confusing failure on the caveat field. Mirror the construction-time
     slope verification pattern in `test_steep_air_band_brickwall_20k_48k`.

- **Steps**:
  1. Generate signal per preconditions.
  2. Run construction-time PSD verification (see above).
  3. Run `measure_hf_extension(audio, SR, config)` with
     `ref_config(hf_min_duration_s=2.0)`.
  4. Assert `result.hf_band_limit_hz is not None` (whole-track cliff detected
     at F_real).
  5. Assert `result.hf_band_limit_hz == pytest.approx(20000.0, abs=1000.0)`.
  6. Assert at least one per-segment value is non-None and disagrees with
     `result.hf_band_limit_hz` by more than `config.hf_stability_tolerance_hz`:
     ```python
     assert any(
         s is not None
         and abs(s - result.hf_band_limit_hz) > config.hf_stability_tolerance_hz
         for s in result.per_segment_hf_band_limit_hz
     )
     ```
  7. Assert `result.per_segment_reliability_caveat is not None`.
  8. Assert `len(result.per_segment_reliability_caveat) > 0`.
  9. Caveat propagates to JSON:
     ```python
     d = dataclasses.asdict(result)
     assert d["per_segment_reliability_caveat"] is not None
     ```
  10. Caveat appears in markdown report:
      ```python
      md = render_markdown(build_report_containing(result))
      assert result.per_segment_reliability_caveat in md
      ```
  11. **Do not assert a specific Hz value for the false-positive segment.** The
      per-segment false-positive value is specific to the synthesised stimulus
      and is not derivable analytically; asserting it locks in a regression
      value rather than testing correctness. Assert only that a false positive
      exists (step 6) and the caveat fires (step 7).

- **Expected result**: all assertions pass.
- **Pass/fail criterion**: fails if whole-track cliff is not detected, if no
  per-segment false positive is produced, or if the caveat field is absent.
  A construction-time failure on the PSD verification (step 2) indicates a
  level-calibration problem per gate1-review F4; the developer should iterate
  on the injection level before proceeding.
- **Covers**: AC6(a), AC6(c) (option c path), architecture §9.1.
- **Type**: audio-quality / edge case. **Slow**.

---

## G. AC1–AC3 reference-set regressions

These tests require the five real reference track files and are therefore
**Slow**. They verify that the option (c) architecture's "no gate parameters
changed" claim holds empirically across the full reference set.

### TC-509 — AC1: 25-segment audit reproduces 20 CORRECT / 4 ABSTAIN / 1 FALSE-POSITIVE

- **Preconditions**: all five reference WAV files available. The 25-segment
  classification scheme from architecture §4 (C/A/FP per segment, using
  whole-track `hf_band_limit_hz` as ground truth per track).
- **Steps**:
  1. Run `measure_hf_extension` on each of the five reference tracks using
     the default five-segment split (`hf_stability_segment_count=5`).
  2. For each of the 25 per-segment values, classify as:
     - **C (CORRECT)**: non-None value within 2 000 Hz of whole-track WT.
     - **A (ABSTAIN)**: `None`.
     - **FP (FALSE-POSITIVE)**: non-None and outside 2 000 Hz of WT.
  3. Assert the totals: CORRECT = 20, ABSTAIN = 4, FALSE-POSITIVE = 1.
  4. Assert the FP is localized to Chemical Brothers segment 1
     (`per_segment_hf_band_limit_hz[0] ≈ 14066 Hz`).
  5. Assert the four ABSTAINs are:
     Chemical Brothers segments 2 and 5 (`per_segment_hf_band_limit_hz[1]` and
     `[4]`), and Wavy Gravy segments 2 and 3 (`[1]` and `[2]`).
- **Expected result**: exact match to the architecture §4 before/after table
  (before = after under option c, per §4 "before state = after state"). Source:
  architecture §4 table, independently confirmed in gate1-review "Preliminary".
- **Note**: requirements.md AC1 literal language states "zero false positives"
  in the after state. Under option (c), the after state retains one false
  positive (Chemical Brothers seg 1). This is expected per architecture §3.5
  scoping and gate1-review F5. The test asserts the documented expected pattern,
  not zero FP; the scoping justification must be recorded in the test's docstring
  or comments so a future QA pass does not reopen AC1 as a defect.
- **Covers**: AC1 (under option c scoping per architecture §3.5).
- **Type**: audio-quality / regression. **Slow**.

### TC-510 — AC2: whole-track `hf_band_limit_hz` values match v1.5a baseline

- **Preconditions**: all five reference WAV files.
- **Steps**:
  1. Run `measure_hf_extension` on each track.
  2. Assert the whole-track values match exactly (within 1 Hz — Welch
     determinism on unchanged gate code):

     | Track | Expected `hf_band_limit_hz` |
     |---|---|
     | Black Flute | 15 788 Hz (± 1 Hz) |
     | GusGus | 16 251 Hz (± 1 Hz) |
     | Leftfield | 20 475 Hz (± 1 Hz) |
     | Chemical Brothers | 20 475 Hz (± 1 Hz) |
     | Wavy Gravy | 20 475 Hz (± 1 Hz) |

     Source: requirements.md AC2 verbatim. Architecture §4 table WT column.
     Gate1-review "Preliminary" cross-check.
- **Expected result**: all five pass.
- **Covers**: AC2 (whole-track no-regression), architecture §12 note ("whole-track
  detection path is not touched").
- **Type**: regression. **Slow**.

### TC-511 — AC3: stable/confidence values unchanged on all five reference tracks

- **Preconditions**: all five reference WAV files.
- **Steps**:
  1. Run `measure_hf_extension` on each track.
  2. Assert per architecture §4 table:

     | Track | `stable` | `hf_band_limit_confidence` |
     |---|---|---|
     | Black Flute | True | 1.0 |
     | GusGus | True | 1.0 |
     | Leftfield | True | 1.0 |
     | Chemical Brothers | **False** | **0.4** |
     | Wavy Gravy | True | 0.6 |

     Source: architecture §4 table. Gate1-review Q1 confirmation.
- **Expected result**: all five match.
- **Note**: Chemical Brothers `stable=False, confidence=0.4` is the **correct
  honest output** per gate1-review Q1. Requirements.md AC3 requires no flip of
  the four `stable=True` tracks; it does not require Chemical Brothers to become
  True. Any option (a)/(b) successor story that changes the gate must re-run
  this test before any parameter can be committed.
- **Covers**: AC3.
- **Type**: regression. **Slow**.

### TC-512 — F5: caveat fires on exactly 1 of 5 reference tracks (Chemical Brothers only)

Gate1-review F5: "exactly 1 of 5 reference tracks fires the caveat (Chemical
Brothers). Black Flute, GusGus, and Leftfield have all-agreeing per-segment
values; Wavy Gravy's non-None values are all exactly 20 475.06 Hz (|diff| = 0
< 2 000 Hz tolerance). Any other caveat firing pattern from the implementation
is a defect."

This test also provides the real-data coverage for the OR-instead-of-AND failure
mode (see TC-513): Wavy Gravy has two `None` abstentions and all non-None values
at 20 475 Hz; an OR-based implementation would fire the caveat on Wavy Gravy and
fail step 4 below.

- **Preconditions**: all five reference WAV files.
- **Steps**:
  1. Run `measure_hf_extension` on each track.
  2. Collect `per_segment_reliability_caveat` for each.
  3. Assert Chemical Brothers `per_segment_reliability_caveat is not None`.
  4. Assert Black Flute, GusGus, Leftfield, Wavy Gravy each have
     `per_segment_reliability_caveat is None`.
- **Expected result**: exactly 1 of 5 non-None.
- **Covers**: AC5 (caveat scoped correctly), architecture R2 (over-fire risk
  mitigated), gate1-review F5. Real-data fallback for TC-513's OR-instead-of-AND
  failure mode.
- **Type**: regression / correctness. **Slow**.

---

## H. Non-regression on existing test suite

### TC-520 — Existing tests in `test_ground_truth_hf_extension.py` pass unchanged

Architecture §9.3: all existing tests must continue to pass. Gate functions are
unchanged; the two new fields default to `None` (backward-compatible).

- **Preconditions**: the full `tests/test_ground_truth_hf_extension.py` suite.
- **Steps**: run the suite.
- **Expected result**: TC-020 through TC-432 (and all un-numbered tests in that
  file) pass with the same results as before this story's changes. No existing
  assertion is weakened or skipped.
- **Covers**: architecture §9.3 non-regression contract; requirements.md NFR
  §Reproducibility.
- **Type**: regression.

---

## Traceability table

| Acceptance criterion | Test case(s) | Notes |
|---|---|---|
| AC1 — 25-segment false-positive audit | TC-509 | Under option (c), after state retains 1 FP per §3.5 |
| AC2 — Whole-track values unchanged | TC-510 | Regression against requirements.md AC2 values |
| AC3 — Stable tracks not flipped | TC-511 | Chemical Brothers `stable=False` is expected |
| AC4 — Chemical Brothers FP eliminated | **N/A (option c)** | Scoped to options (a)/(b); see §Out-of-scope |
| AC5 — Machine-readable caveat | TC-501, TC-502, TC-513, TC-514, TC-515, TC-516, TC-517, TC-519, TC-521, TC-505, TC-506, TC-518, TC-503, TC-504, TC-512 | Full AC5(a)(b)(c) content, JSON, markdown |
| AC6(a) — Fixture produces the false-positive scenario | TC-507 | Geometry-faithful ~250 s slow fixture |
| AC6(b) — No false positives after fix | **N/A (option c)** | Scoped to options (a)/(b); option (c) retains 1 FP, disclosed via caveat; see §Out-of-scope |
| AC6(c) — Caveat field present and non-empty | TC-501, TC-505, TC-506, TC-507 | TC-507 is slow; TC-501/505/506 are fast |
| NFR — Schema version bump | TC-500 | Regression lock; updated `test_tc292`; TC-508 folded here |
| NFR — Reproducibility | TC-519 | Two identical runs, bit-identical output |
| NFR — Suite ≤ 60 s | TC-507 isolated under `@pytest.mark.slow` | TC-509/510/511/512 also Slow |
| gate1-review F5 — Caveat fires on exactly 1 track | TC-512 | Chemical Brothers only; any other pattern is a defect |
| TC-508 (parent prompt) | Folded into TC-500 step 4 | `test_tc292` update from "2.1" to "2.2" is step 4 of TC-500 |

---

## Revision history

| Version | Date | Change |
|---|---|---|
| v1 | 2026-08-09 | Initial test cases for STORY-005. Covers AC1–AC6 and NFR for option (c). First advisor review incorporated before writing: added AC1/AC2/AC3 Slow regression tests (TC-509–TC-511) missing from the parent's TC-500–TC-508 list; added gate1-review F5 test (TC-512); added Wavy-Gravy-analogue negative control (TC-513); added whole-track-None branch (TC-514), insufficient-duration branch (TC-515), config-interpolation test (TC-516), boundary-value test (TC-517), determinism test (TC-519), AC5-content-clauses test (TC-521), and second markdown-block test (TC-518); strengthened TC-503 with by-construction expected values; folded TC-508 into TC-500 with cross-reference; noted TC-507 uses mono per gate1-review F4. |
| v1.1 | 2026-08-09 | Second advisor review fixes: (1) TC-517 boundary case corrected — the TC-025 fixture's maximum per-segment disagreement is ≈ 7 000 Hz (8 kHz segment vs. WT 15 000 Hz), not 3 000 Hz; fixed by deriving the boundary from a runtime measurement `d = max(abs(s - WT) ...)` and bracketing with ± 500 Hz. (2) TC-501 preconditions now include a proof-by-construction that the caveat fires on this fixture (derives from `test_tc025`'s own assertions). (3) TC-513 now cross-references TC-512 as the real-data fallback for the OR-instead-of-AND failure mode if the synthetic precondition cannot be met. (4) AC6(b) N/A disposition added to §Out-of-scope. (5) TC-518 pins the exact markdown string `"Whole-track j* margin"` from `reference_render.py` line 119. (6) TC-508 added as folded-into-TC-500 row in traceability table. |
