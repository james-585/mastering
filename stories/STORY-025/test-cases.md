# STORY-025 Test Cases — Grounded Quality Validation

**Story:** STORY-025
**Version:** 1.0
**Date:** 2026-08-17
**Covers:** AC1–AC9 from requirements.md
**Reads from:** requirements.md, architecture.md v1.1 (§4, §5, §7, §8, §12 Gate 1 disposition), DOMAIN.md §3, CLAUDE.md §6.3

---

## How to read these test cases

**No implementation was read.** These test cases are written against architecture.md's function
signatures and documented behavior (§4–§8) and requirements.md's acceptance criteria. Where
architecture.md does not fully specify an exact string, exception type, or return shape, this is
called out explicitly rather than guessed — see "Open Questions Affecting Expected Values" below.

**Every module under test in §7 (`compute_grounded_metrics`, `evaluate_quality_review`) delegates
to four already-implemented, already-tested functions** (`measure_seven_band_balance`,
`measure_dynamic_range`, `detect_artifacts`, `measure_integrated_lufs`) plus the new
`match_levels()`. Re-deriving analytical expected values for those four functions from raw audio
is STORY-001/STORY-002/STORY-007's job, not this story's — testing them again here would
duplicate coverage and violate architecture's "reuse, not reimplement" boundary. Instead, test
cases in §1–§2 **mock/monkeypatch these four dependencies** at the `grounded_quality_review`
module boundary, inject controlled return values, and assert the *aggregation, sign convention,
and audit-line arithmetic that STORY-025 actually adds* is correct — this is the part of the
system this story is responsible for getting right, and the part with no other test suite.

**`match_levels()` itself (§6) is tested without mocking measure_integrated_lufs where the
expected value can be derived from the construction of the signal** (a uniform linear gain
applied to a stationary, non-gated signal shifts BS.1770 integrated LUFS by exactly the gain in
dB — this follows from the ungated and gated block-power sums all scaling by the same factor,
so the relative −10 LU gate threshold is unaffected by a single uniform gain change). Where a
test needs to force a specific numeric residual to exercise a boundary (exactly at
`tolerance_lu`), `measure_integrated_lufs` is patched directly, since architecture.md does not
expose an injectable measurement function on `match_levels()` — this is called out per test.

**Mocking convention used throughout:** `monkeypatch.setattr("grounded_quality_review.<name>",
fake_fn)` for the four dependency functions imported into `grounded_quality_review.py`. This
mirrors the injectable-dependency precedent already established in this repo by
`stem_separation.py`'s `model_loader`/`apply_model_fn` parameters (STORY-001 §4), adapted to
monkeypatching since architecture.md's `compute_grounded_metrics()`/`evaluate_quality_review()`
signatures do not themselves expose injectable parameters for these four functions — flagged as
an open question below (OQ-A).

**Precision:** dB/LU assertions use ±0.01 unless a boundary test requires an exact comparison
(`<=`/`>=` at a threshold), in which case both sides of the boundary are tested explicitly.

---

## Open Questions Affecting Expected Values

Do not invent values for these. Each affected test case calls out the dependency; leave the
assertion as `[OPEN]` until resolved by python-developer/architect.

| OQ | Question | Affected TCs |
|---|---|---|
| OQ-A | `compute_grounded_metrics`/`evaluate_quality_review` expose no injectable parameters for `measure_seven_band_balance`/`measure_dynamic_range`/`detect_artifacts`/`match_levels` (unlike `stem_separation.py`'s `model_loader`/`apply_model_fn` precedent). Tests below assume `monkeypatch.setattr` on the names as imported into `grounded_quality_review.py`'s module namespace. If python-developer imports these with a different alias or via a wrapper, the patch target changes. | TC-2501–TC-2510, TC-2512–TC-2517 |
| OQ-B | Exact literal text of the `dynamic_range_regression` audit line is described but not given verbatim in architecture §7.3 ("states the raw `dr_delta` the same way, but without a PROVISIONAL caveat") — unlike the artifact/spectral lines, which are quoted exactly. TC-2513 asserts the substantive requirements (raw value present, no PROVISIONAL text) but cannot assert exact string equality until python-developer fixes the literal wording. | TC-2513 |
| OQ-C | Exception type raised by `verify_stem_separation_environment()` when `fixture_path` does not exist, versus when duration is too short for `clip_offset_seconds + clip_seconds`. Architecture §5.2 says the duration case "raises" without naming the exception class explicitly (module defines `EnvironmentVerificationError` for import/inference/degenerate-stem failures specifically). TC-2521/TC-2522 assume `EnvironmentVerificationError` for both; flag if python-developer instead uses `ValueError`/`FileNotFoundError` for these two precondition failures. | TC-2521, TC-2522 |
| OQ-D | `within_tolerance` boundary inclusivity: architecture §4.3 does not state whether exactly `tolerance_lu` residual counts as within tolerance (`<=`) or not (`<`). TC-2528 assumes inclusive (`<=`) as the conventional reading of "within tolerance," consistent with the flag-threshold conventions elsewhere in this story (`dr_delta <= -config.dr_regression_db` uses `<=`). Confirm with python-developer. | TC-2528, TC-2529 |
| OQ-E | Whether `capture_human_review()`'s CLI-prompt path on a non-TTY stdin raises immediately or only on first `input()` call — architecture §6.1 says "raises rather than silently defaulting" without specifying the raise point. TC-2531 tests only the externally observable contract (raises `HumanReviewRequiredError`-family exception before returning a record), not the exact call site. | TC-2531 |

Per requirements.md's own open questions (OQ2 in requirements.md: LUFS-matching tolerance —
now resolved to 0.5 LU by architecture §4.2, no longer open here) and (OQ3: artifact-density
regression magnitude — resolved PROVISIONAL at 0.05 by architecture §7.1, tested as the current
contract value in §2 below, not as a validated correctness target).

---

## Fixture Specifications

### Config defaults under test (architecture §7.1, `GroundedReviewConfig`)

```python
lufs_match_tolerance_lu = 0.5      # not a verdict threshold — match re-verification only
dr_regression_db = 3.0             # reused from MasteringConfig.dr_max_reduction_db
artifact_density_regression = 0.05 # PROVISIONAL
spectral_shift_flag_db = 2.0       # PROVISIONAL
```

### F-2501: Gain-scaled stationary tone pair (for `match_levels` — no LUFS value invented)

```python
import numpy as np

sr = 44100
duration_s = 5.0
n = int(sr * duration_s)
t = np.arange(n) / sr
original = 0.2 * np.sin(2 * np.pi * 440.0 * t)   # -20 dBFS-ish full-band tone, stationary

# By construction: processed is exactly `delta_db` dB louder than original.
# For a uniform linear gain on a stationary (non-transient, non-gated) signal, BS.1770
# integrated LUFS shifts by exactly delta_db — every ungated block's power scales by the
# same factor, and the relative -10 LU gate is computed from the (equally scaled) ungated
# mean, so the same set of blocks is gated in/out regardless of delta_db. This holds without
# needing to know original's absolute LUFS value.
def make_processed(delta_db: float) -> np.ndarray:
    return original * (10 ** (delta_db / 20.0))
```

Stereo variant: `original_stereo = np.column_stack([original, original])` (identical channels,
so mono-sum level and per-channel LUFS math are unaffected by channel count for this fixture).

### F-2502: Bimodal near-silent/loud signal (forces the gating-edge residual failure in §4.2)

```python
# Long near-silent passage (RMS well below the -70 LUFS absolute gate) followed by a short
# loud passage, so that a uniform gain shift changes which blocks pass the -10 LU relative
# gate relative to the loud section's ungated mean -- this is the "highly bimodal material"
# edge case architecture §4.2 names as the source of residual gating error.
sr = 44100
quiet = 0.0005 * rng.standard_normal(int(sr * 8.0))    # 8 s near-silent noise floor
loud = 0.5 * np.sin(2 * np.pi * 440.0 * np.arange(int(sr * 1.0)) / sr)  # 1 s loud tone
original = np.concatenate([quiet, loud])
# processed built by a large gain shift applied AFTER a nonlinear per-section change (not a
# single uniform gain), e.g. the quiet section gained +40 dB and the loud section unchanged,
# so the two sections' LUFS contributions shift by different amounts -- this is not
# constructible as "exact by uniform-gain arithmetic" and is used only to force
# LevelMatchError, not to assert a specific residual value.
processed = np.concatenate([quiet * (10 ** (40/20.0)), loud])
```

### F-2503: Silence (forces non-finite LUFS)

```python
original = np.zeros(int(44100 * 3.0))   # digital silence -> measure_integrated_lufs returns -inf
processed = 0.3 * np.sin(2 * np.pi * 440.0 * np.arange(int(44100 * 3.0)) / 44100)
```

### F-2504: Mocked seven-band deltas (for `spectral_rms_shift_db` aggregation)

```python
# Mock measure_seven_band_balance's return so that per-band relative_db values are fully
# controlled -- this is an aggregation-logic test, not a spectral-measurement test.
BANDS = ["sub", "low", "low_mid", "mid", "high_mid", "high", "air"]

original_relative_db = {b: 0.0 for b in BANDS}
processed_relative_db = {
    "sub": 2.0, "low": -1.0, "low_mid": 0.0, "mid": 0.0,
    "high_mid": 3.0, "high": -2.0, "air": 1.0,
}
# Per-band delta (processed - original), all bands: sub=+2, low=-1, low_mid=0, mid=0,
# high_mid=+3, high=-2, air=+1.
# Non-"mid" deltas: [2, -1, 0, 3, -2, 1] -> squares [4, 1, 0, 9, 4, 1] -> sum 19, mean 19/6.
# spectral_rms_shift_db = sqrt(19/6) = 1.7795... ~= 1.78 dB (excluding "mid").
# If "mid" were wrongly included: sqrt(19/7) = 1.6475... ~= 1.65 dB -- a materially
# different, wrong answer that TC-2501 distinguishes explicitly.
```

### F-2505: Mocked DR and artifact-density pairs

```python
# DR pair for boundary tests (dr_regression_db = 3.0):
dr_no_flag        = (10.0, 7.01)   # dr_delta = -2.99  -> NOT <= -3.0 -> no flag
dr_flag_boundary   = (10.0, 7.00)   # dr_delta = -3.00  -> <= -3.0    -> flag (exact boundary)
dr_flag_clear      = (10.0, 5.00)   # dr_delta = -5.00  -> flag, unambiguous

# Artifact-density pair for boundary tests (artifact_density_regression = 0.05):
art_no_flag       = (0.10, 0.149)   # delta = +0.049 -> NOT >= 0.05 -> no flag
art_flag_boundary = (0.10, 0.150)   # delta = +0.050 -> >= 0.05    -> flag (exact boundary)
art_flag_clear    = (0.10, 0.200)   # delta = +0.100 -> flag, unambiguous
```

---

## Section 1 — `compute_grounded_metrics()` / `GroundedMetrics` (AC1, AC2, AC4, AC5, AC6)

### TC-2501 — `spectral_rms_shift_db` excludes "mid" by definition

**Covers:** AC1, AC3
**Type:** Functional / audio-quality (aggregation logic)

**Preconditions:** F-2504 mocked into `measure_seven_band_balance` for both `original` and
`match.matched_processed` calls (patch returns the fixed `original_relative_db`/
`processed_relative_db` dicts regardless of the audio array passed in — this test targets
aggregation, not spectral measurement). `measure_dynamic_range` and `detect_artifacts` mocked
to return values that produce no flags (e.g. `dr_no_flag`, `art_no_flag`) so this test's
assertions are isolated to the spectral aggregation.

**Steps:**
1. Call `compute_grounded_metrics(original, processed, sr, config)` with the mocks above.
2. Read `metrics.spectral_band_delta_db["mid"]`.
3. Read `metrics.spectral_rms_shift_db`.

**Expected result:**
- `spectral_band_delta_db["mid"] == 0.0` exactly.
- `spectral_rms_shift_db == sqrt(19/6) ≈ 1.7795` dB (±0.001), **not** `sqrt(19/7) ≈ 1.6475`
  dB. An implementation that includes "mid" in the RMS aggregation produces the second
  (wrong) value — this test fails against that implementation.

---

### TC-2502 — `spectral_band_delta_db` reports all seven bands, deltas computed as processed − original

**Covers:** AC1
**Type:** Functional

**Preconditions:** Same as TC-2501.

**Steps:**
1. Call `compute_grounded_metrics(...)`.
2. Read `metrics.spectral_band_delta_db` as a dict.

**Expected result:**
- Dict has exactly 7 keys matching `BANDS`.
- `spectral_band_delta_db == {"sub": 2.0, "low": -1.0, "low_mid": 0.0, "mid": 0.0,
  "high_mid": 3.0, "high": -2.0, "air": 1.0}` (±0.001 each). Sign convention is
  processed-relative-db minus original-relative-db (positive = band got louder relative to
  mid after mastering).

---

### TC-2503 — `dr_delta` sign convention: negative means DR got worse (more compressed)

**Covers:** AC2
**Type:** Functional / audio-quality

**Preconditions:** `measure_dynamic_range` mocked to return `dr_original=10.0`,
`dr_processed=7.0` (`dr_no_flag`-style pair scaled to `dr_flag_clear`). Spectral/artifact
mocks produce no flags.

**Steps:**
1. Call `compute_grounded_metrics(...)`.
2. Read `metrics.dr_delta`.

**Expected result:**
- `dr_delta == dr_processed - dr_original == 7.0 - 10.0 == -3.0` exactly (float subtraction
  of the mocked inputs). Negative value must mean the processed audio's DR is *lower* than
  the original's — a positive `dr_delta` on this same input would indicate an implementation
  with the subtraction operands reversed.

---

### TC-2504 — `dr_delta` boundary: exactly at `dr_regression_db` flags, one hundredth under does not

**Covers:** AC2, Gate 1 Finding (dr_regression_db reuse)
**Type:** Edge case / boundary

**Preconditions:** Two runs — `dr_flag_boundary` (10.0, 7.00) and `dr_no_flag` (10.0, 7.01).

**Steps:**
1. Run A: `compute_grounded_metrics` with `dr_flag_boundary`. Read `metrics.dr_delta` and
   `"dynamic_range_regression" in metrics.flags`.
2. Run B: same with `dr_no_flag`.

**Expected result:**
- Run A: `dr_delta == -3.00`; `"dynamic_range_regression"` **is** in `flags` (architecture
  §7.2 step 6: flag condition is `dr_delta <= -config.dr_regression_db`, and `-3.00 <= -3.00`
  is true).
- Run B: `dr_delta == -2.99`; `"dynamic_range_regression"` is **not** in `flags`
  (`-2.99 <= -3.00` is false).

---

### TC-2505 — `artifact_density_delta` sign convention: positive means more artifacts after mastering

**Covers:** AC4
**Type:** Functional / audio-quality

**Preconditions:** `detect_artifacts` mocked so the original call returns an
`ArtifactDetectionResult`-like object with `overall_artifact_density_score=0.10`, and the
processed call returns one with `overall_artifact_density_score=0.20` (`art_flag_clear`).
Spectral/DR mocks produce no flags.

**Steps:**
1. Call `compute_grounded_metrics(...)`.
2. Read `metrics.artifact_density_delta`.

**Expected result:**
- `artifact_density_delta == 0.20 - 0.10 == 0.10` exactly. Positive sign means artifact
  density *increased* (regression). A negative value on this same input would indicate
  reversed subtraction operands.

---

### TC-2506 — `artifact_density_delta` boundary: exactly at threshold flags, one thousandth under does not

**Covers:** AC4, Gate 1 Finding 1
**Type:** Edge case / boundary

**Preconditions:** Two runs — `art_flag_boundary` (0.10, 0.150) and `art_no_flag`
(0.10, 0.149).

**Steps:**
1. Run A: `art_flag_boundary`. Read `artifact_density_delta` and flag presence.
2. Run B: `art_no_flag`.

**Expected result:**
- Run A: `artifact_density_delta == 0.050`; `"artifact_density_regression"` **is** in
  `flags` (`0.050 >= 0.05` true).
- Run B: `artifact_density_delta == 0.049`; flag **absent** (`0.049 >= 0.05` false).

---

### TC-2507 — `spectral_shift_significant` boundary at `spectral_shift_flag_db = 2.0`

**Covers:** AC1, Gate 1 Finding 2
**Type:** Edge case / boundary

**Preconditions:** Mock `measure_seven_band_balance` deltas for two runs such that
`spectral_rms_shift_db` lands at exactly 2.00 dB and at 1.99 dB. (Construction: with 6
non-mid bands, an RMS of exactly 2.0 is reached e.g. by setting all six band deltas to
exactly 2.0 — `sqrt(mean([2.0]*6)**... )`; simplest exact construction: all six deltas equal
to `x`, giving RMS `= |x|` exactly. Use `x = 2.00` for the boundary run and `x = 1.99` for
the under-boundary run.)

**Steps:**
1. Run A: all six non-mid band deltas = 2.00. Read `spectral_rms_shift_db` and flag
   presence.
2. Run B: all six = 1.99.

**Expected result:**
- Run A: `spectral_rms_shift_db == 2.00`; `"spectral_shift_significant"` **is** in `flags`
  (`2.00 >= 2.00` true).
- Run B: `spectral_rms_shift_db == 1.99`; flag absent.

---

### TC-2508 — `match_levels()` invoked before any of the three grounded measurements (structural, AC5/AC6)

**Covers:** AC5, AC6
**Type:** Functional (structural / not-bypassable)

**Preconditions:** Spy wrappers around `match_levels`, `measure_seven_band_balance`,
`measure_dynamic_range`, `detect_artifacts` that record call order into a shared list.
`match_levels` spy delegates to a real (non-raising) fake returning a valid
`LevelMatchResult`.

**Steps:**
1. Call `compute_grounded_metrics(original, processed, sr, config)`.
2. Inspect the recorded call-order list.

**Expected result:**
- `match_levels` is the first entry in the call-order list, before any call to
  `measure_seven_band_balance`, `measure_dynamic_range`, or `detect_artifacts`.
- `measure_seven_band_balance` and `measure_dynamic_range` and `detect_artifacts` (for the
  "processed" side) are called with `match.matched_processed`, **not** the raw `processed`
  array passed to `compute_grounded_metrics` (assert via identity/array-equality check on the
  argument actually received by the spy, comparing against the fake `LevelMatchResult`'s
  `matched_processed` array, not the original `processed` argument).

---

### TC-2509 — `match_levels()` failure is not swallowed: `LevelMatchError` propagates and no measurement is attempted

**Covers:** AC6
**Type:** Functional (negative / not-bypassable)

**Preconditions:** F-2503 (silence `original`). Spies on `measure_seven_band_balance`,
`measure_dynamic_range`, `detect_artifacts` record whether they were called at all. Real
(unmocked) `match_levels`/`measure_integrated_lufs` used, since silence genuinely produces
non-finite LUFS per BS.1770's absolute gate — no mock needed to prove this case.

**Steps:**
1. Call `compute_grounded_metrics(original, processed, sr, config)`.
2. Catch the raised exception.
3. Check whether the three measurement spies were called.

**Expected result:**
- `LevelMatchError` is raised (propagates out of `compute_grounded_metrics`, is not caught
  and converted into a "degraded" `GroundedMetrics` result).
- None of `measure_seven_band_balance`, `measure_dynamic_range`, `detect_artifacts` was
  called — no partial/unmatched delta is computed before the error surfaces.

---

### TC-2510 — `width_delta` / `peak_delta_db_unmatched` computed on the raw (unmatched) pair, not the LUFS-matched pair

**Covers:** Architecture §7.5 (peak/width stay unmatched)
**Type:** Functional

**Preconditions:** F-2501 with `delta_db = 6.0` (processed is 6 dB louder pre-match). Spies
record the actual array argument passed into whichever internal helper computes
`width_delta`/`peak_delta_db_unmatched` (ported `_stereo_width`/`_true_peak` logic per §7.4).

**Steps:**
1. Call `compute_grounded_metrics(original, processed, sr, config)`.
2. Inspect which array (`processed` raw vs. `match.matched_processed`) was passed to the
   peak/width computation.

**Expected result:**
- The peak/width computation receives the raw, pre-match `processed` array — its measured
  peak reflects the actual exported file's true level, not a level hypothetically matched to
  `original` for the purposes of the A/B comparison. (Architecture §7.5: matching before
  peak measurement would report a peak the exported file never actually has.)

---

## Section 2 — Flag audit-line format (Gate 1 action items, architecture §7.3)

### TC-2511 — All three flags fire simultaneously; audit lines match architecture's exact required format

**Covers:** Gate 1 Findings 1 and 2 (action items), architecture §7.3
**Type:** Functional

**Preconditions:** Mocks set so all three flags fire: `dr_flag_clear` (10.0, 5.0 →
`dr_delta = -5.0`), `art_flag_clear` (0.10, 0.20 → `artifact_density_delta = 0.10`), and
seven-band deltas giving `spectral_rms_shift_db` well above 2.0 dB (e.g. all six non-mid
deltas = 5.0 → RMS = 5.00). `human_review=None`.

**Steps:**
1. Call `evaluate_quality_review(original, processed, sr, human_review=None, config=config)`.
2. Read `result.audit` as a list of strings.

**Expected result:** the audit list contains, verbatim (values substituted per the mocked
metrics):

- `"artifact_density_regression flag (PROVISIONAL threshold 0.05, not calibrated against "
  "reference data): raw artifact_density_delta = +0.1000"`
- `"spectral_shift_significant flag (PROVISIONAL threshold 2.0 dB, not calibrated against "
  "reference data): raw spectral_rms_shift_db = 5.00 dB"`
- a `dynamic_range_regression` line containing the raw value `-5.00` (or equivalent
  formatting per architecture's `:+.2f`/`:.2f` convention) — see OQ-B for why exact string
  equality is not asserted here — **and** the substring `"PROVISIONAL"` must **not** appear
  anywhere in this line.

---

### TC-2512 — Flag audit lines appear identically whether `human_review` is `None` or populated

**Covers:** Gate 1 Findings 1/2 ("applies in both branches"), AC9
**Type:** Functional

**Preconditions:** Same flag-triggering mocks as TC-2511. Run A: `human_review=None`. Run B:
`human_review={"reviewer": "J. Doe", "decision": "refine", "note": "Kick still a bit thin
after gain matching."}`.

**Steps:**
1. Run both A and B.
2. Extract the flag-derived audit lines from each (i.e., all entries excluding the leading
   `"No human listening review..."` sentinel line in A, and excluding the leading
   `"Human review (...)"` line in B).

**Expected result:** the flag-derived audit lines (artifact, spectral, DR) are textually
identical between Run A and Run B — the human-review branch does not omit, reorder, or
reformat them.

---

### TC-2513 — `dynamic_range_regression` audit line carries no PROVISIONAL caveat (negative control)

**Covers:** Architecture §7.3 explicit distinction ("without a PROVISIONAL caveat"), Gate 1
v1.1 disposition item 1
**Type:** Negative control

**Preconditions:** Only `dynamic_range_regression` fires (`dr_flag_clear`); artifact/spectral
mocks produce no flags.

**Steps:**
1. Call `evaluate_quality_review(...)`.
2. Search `result.audit` for the line mentioning `dynamic_range_regression`.

**Expected result:**
- Exactly one audit line references `dynamic_range_regression`.
- That line contains the raw `dr_delta` value (`-5.00` or equivalent).
- That line does **not** contain the substring `"PROVISIONAL"` — this is the test that would
  catch an implementation that copy-pasted the artifact/spectral line template onto the DR
  flag by mistake. See OQ-B for the exact-wording caveat.

---

### TC-2514 — No flags fire: audit contains no flag-derived lines

**Covers:** Architecture §7.2/§7.3 (flags are additive, not always-present)
**Type:** Edge case (negative)

**Preconditions:** `dr_no_flag`, `art_no_flag`, spectral deltas all 0.0 (identical
before/after spectral balance). `human_review=None`.

**Steps:**
1. Call `evaluate_quality_review(...)`.
2. Read `result.flags` and `result.audit`.

**Expected result:** `result.flags == []`. `result.audit` contains only the
`"No human listening review..."` sentinel line (§3 below) — no flag-shaped lines are
present, and no flag text is fabricated when nothing regressed.

---

## Section 3 — `evaluate_quality_review()` decision authority and `pending_human_review` (AC8, AC9)

### TC-2515 — `human_review=None` produces `pending_human_review`, not a trusted verdict

**Covers:** AC8, AC9, architecture §7.3, §11 (assumption on 4th decision value)
**Type:** Functional

**Preconditions:** Any non-flag-triggering metrics mock (isolates this test from flag-line
content, covered separately in §2).

**Steps:**
1. Call `evaluate_quality_review(original, processed, sr, human_review=None, config=config)`.
2. Read `result.decision`, `result.human_decision`, `result.human_note`.

**Expected result:**
- `result.decision == "pending_human_review"` exactly — not `"pass"`, `"reject"`, or
  `"refine"`.
- `result.human_decision is None`.
- `result.human_note == ""`.
- `result.audit[0] == "No human listening review was supplied; this result is evidence only "
  "and must not be treated as a trusted pass/reject/refine verdict."` (verbatim, per
  architecture §7.3's pseudocode).

---

### TC-2516 — Populated `human_review` sets `decision`/`human_decision`/`human_note` from the human's input

**Covers:** AC8, AC9
**Type:** Functional

**Preconditions:** `human_review = {"reviewer": "A. Reviewer", "decision": "pass",
"note": "Clear improvement in low-end definition, no new artifacts audible."}`.

**Steps:**
1. Call `evaluate_quality_review(original, processed, sr, human_review=human_review,
   config=config)`.
2. Read `result.decision`, `result.human_decision`, `result.human_note`, `result.audit[0]`.

**Expected result:**
- `result.decision == "pass"` (equals `human_review["decision"]`, not independently derived
  from metrics).
- `result.human_decision == "pass"`.
- `result.human_note == "Clear improvement in low-end definition, no new artifacts audible."`
- `result.audit[0] == "Human review (A. Reviewer): Clear improvement in low-end definition, "
  "no new artifacts audible."`

---

### TC-2517 — Missing `reviewer` key defaults the audit line to "unspecified"

**Covers:** Architecture §7.3 (`human_review.get('reviewer', 'unspecified')`)
**Type:** Edge case

**Preconditions:** `human_review = {"decision": "refine", "note": "Needs another pass on the
top end, slightly harsh above 8 kHz."}` (no `"reviewer"` key).

**Steps:**
1. Call `evaluate_quality_review(...)`.
2. Read `result.audit[0]`.

**Expected result:** `result.audit[0] == "Human review (unspecified): Needs another pass on
the top end, slightly harsh above 8 kHz."`

---

### TC-2518 — Invalid `decision` string raises `ValueError`

**Covers:** Architecture §7.3 ("must be one of pass/reject/refine, else raise ValueError")
**Type:** Edge case / negative

**Preconditions:** `human_review = {"reviewer": "X", "decision": "maybe", "note": "Not sure,
needs a second listen."}`.

**Steps:**
1. Call `evaluate_quality_review(original, processed, sr, human_review=human_review,
   config=config)`.

**Expected result:** raises `ValueError`. No `QualityReviewResult` is returned. (Exact
message text not specified by architecture — assert only the exception type.)

---

### TC-2519 — Deterministic: identical inputs and `human_review` produce identical `GroundedMetrics`/`before_after` across two runs

**Covers:** Non-functional requirement (reproducibility), requirements.md NFR
**Type:** Non-functional

**Preconditions:** F-2501 with `delta_db = 3.0`, real (unmocked) `match_levels` +
`measure_integrated_lufs`, spectral/DR/artifact mocked to fixed deterministic values.

**Steps:**
1. Call `evaluate_quality_review(original, processed, sr, human_review=None, config=config)`
   twice with byte-identical `original`/`processed` arrays.
2. Compare `result1.before_after` to `result2.before_after` field by field.

**Expected result:** every scalar in `before_after` is bit-for-bit identical (or within
floating-point-noise tolerance ≤1e-9) across the two runs — no non-determinism (e.g. from
unseeded randomness, dict-ordering, or wall-clock-dependent branches) enters the grounded
metrics path.

---

### TC-2520 — `before_after` flattens `spectral_band_delta_db` as `spectral_band_delta_db.<band>` keys

**Covers:** Architecture §7.3 (`QualityReviewResult.before_after` shape)
**Type:** Functional

**Preconditions:** F-2504 mocks (as in TC-2501).

**Steps:**
1. Call `evaluate_quality_review(...)`.
2. Read `result.before_after` keys.

**Expected result:** `before_after` contains keys `spectral_band_delta_db.sub`,
`spectral_band_delta_db.low`, `spectral_band_delta_db.low_mid`, `spectral_band_delta_db.mid`,
`spectral_band_delta_db.high_mid`, `spectral_band_delta_db.high`,
`spectral_band_delta_db.air` (each a float, not a nested dict), alongside the other flattened
`GroundedMetrics` scalar fields (`dr_delta`, `artifact_density_delta`, `width_delta`,
`peak_delta_db_unmatched`, `spectral_rms_shift_db`, `lufs_gain_applied_db`, etc.).

---

## Section 4 — `verify_stem_separation_environment()` (architecture §5.2, Gate 1 Finding 4)

### TC-2521 — `clip_offset_seconds` default is `30.0`

**Covers:** Gate 1 Finding 4 (action item), architecture §5.2/§12
**Type:** Functional

**Steps:**
1. Inspect `inspect.signature(verify_stem_separation_environment).parameters
   ["clip_offset_seconds"].default`.

**Expected result:** default value `== 30.0` exactly.

---

### TC-2522 — Fixture shorter than `clip_offset_seconds + clip_seconds` raises rather than truncating

**Covers:** Gate 1 Finding 4 downstream-impact note (§12)
**Type:** Edge case / negative

**Preconditions:** A synthetic WAV fixture 20.0 s long (shorter than the default
`30.0 + 8.0 = 38.0` s required window). `torch`/`demucs` import mocked to succeed trivially
(this test is about the duration precondition, not inference) — see OQ-A-adjacent note:
architecture does not expose an injection point for the audio *loader*, so this test assumes
python-developer's duration check happens before any model-loading/inference call; if the
check happens only after inference is attempted, the mock must instead simulate a successful
model load and the assertion still holds at the duration-check boundary.

**Steps:**
1. Call `verify_stem_separation_environment(fixture_path=<20s fixture>, clip_seconds=8.0,
   clip_offset_seconds=30.0)`.

**Expected result:** raises (see OQ-C for exact exception type — assumed
`EnvironmentVerificationError`) with a message that names the required window
(`clip_offset_seconds + clip_seconds = 38.0s`) and the fixture's actual duration
(`20.0s`). The function must **not** silently clip its read window to whatever the fixture
actually contains and proceed with a shorter effective clip.

---

### TC-2523 — Clip is read starting at `clip_offset_seconds`, not from file start

**Covers:** Architecture §5.2 Gate 1 Finding 4 rationale (false negative on intro silence)
**Type:** Functional

**Preconditions:** A synthetic 45 s fixture: samples `[0, 30s)` are digital silence, samples
`[30s, 45s)` are a 0.3-amplitude 440 Hz tone (i.e., exactly the "silent intro, real content
after 30 s" scenario the Gate 1 finding describes). Inference mocked to return finite,
non-degenerate stems whenever called (this test asserts what's passed *into* inference, not
inference correctness).

**Steps:**
1. Call `verify_stem_separation_environment(fixture_path=<this fixture>, clip_seconds=8.0,
   clip_offset_seconds=30.0)`.
2. Capture the actual audio segment passed to the mocked inference call.

**Expected result:**
- The segment passed to inference is drawn from samples `[30s, 38s)` — the tone region —
  not `[0s, 8s)` (the silent region).
- With a correct offset, the check succeeds (`available=True`) even though the file's first
  30 s are silent; a naive from-file-start implementation would instead see the silent
  region, likely produce a degenerate/near-zero RMS stem, and raise
  `EnvironmentVerificationError` incorrectly — this is the exact false-negative the Gate 1
  finding was written to prevent.

---

### TC-2524 — Degenerate (all-zero / below-noise-floor) stem raises `EnvironmentVerificationError`

**Covers:** Architecture §5.2 ("non-degenerate... a model that silently returns zeros does
not pass")
**Type:** Edge case / negative

**Preconditions:** Inference mocked to return one or more stems that are all-zero arrays.

**Steps:**
1. Call `verify_stem_separation_environment(...)` with the mock above.

**Expected result:** raises `EnvironmentVerificationError`. `available=True` is never
returned for this input — a zero-output "success" must not pass the smoke test.

---

### TC-2525 — NaN/Inf in a returned stem raises `EnvironmentVerificationError`

**Covers:** Architecture §5.2 ("assert every returned stem is finite")
**Type:** Edge case / negative

**Preconditions:** Inference mocked to return one stem containing a single `NaN` sample
(rest finite, plausible RMS).

**Steps:**
1. Call `verify_stem_separation_environment(...)`.

**Expected result:** raises `EnvironmentVerificationError` — a single non-finite sample is
sufficient to fail the check; it must not be silently treated as acceptable because most of
the stem is finite.

---

### TC-2526 — Import failure (torch/demucs unavailable) raises with a clear message, no silent fallback

**Covers:** Architecture §5.2, NFR ("fail loudly")
**Type:** Failure mode

**Preconditions:** `torch`/`demucs` imports mocked to raise `ImportError` (module absent).

**Steps:**
1. Call `verify_stem_separation_environment(...)`.

**Expected result:** raises `EnvironmentVerificationError` whose message references the
underlying import failure (consistent with the `DependencyError` precedent in
`stem_separation.py`'s `_load_dependencies`). No `EnvironmentCheckResult` with
`available=False` is returned in its place — this is an exception-only failure path per
architecture §5.2's docstring.

---

### TC-2527 — Real Demucs environment smoke test (Slow, integration)

**Covers:** AC7 (real, non-mocked confirmation)
**Type:** Audio-quality / **Slow** (integration — mark `@pytest.mark.slow`)

**Preconditions:** Real `Reference Tracks/Sunday Club.wav` present, real Demucs 4.1.0 / torch
2.13.0+cpu installed (per `memories/repo/suno-mastering-status.md`'s confirmed environment
fact). No mocking of `torch`/`demucs`/inference.

**Steps:**
1. Call `verify_stem_separation_environment()` with all defaults (no path/offset/duration
   override).
2. Time the call.

**Expected result:**
- `result.available is True`.
- `result.stem_count == 6` (htdemucs_6s).
- Every returned stem (accessible via whatever field `EnvironmentCheckResult` — or an
  underlying call the test can also invoke directly — exposes the stems) is finite and has
  RMS above a plausible noise floor.
- `result.elapsed_s` is single-digit seconds (architecture §5.2: "well under the compute
  budget of the validation run itself" for an 8 s clip, versus the ~123 s/full-track
  reference data point) — assert `elapsed_s < 30.0` as a generous ceiling, not a tight
  performance SLA (none is specified).

---

## Section 5 — Negative controls: STORY-015 proxy metrics must not exist in the new module

### TC-2528 — `_spectral_tilt` is absent from `grounded_quality_review`'s public and private surface

**Covers:** AC1, AC3
**Type:** Negative control

**Steps:**
1. `import grounded_quality_review`.
2. Check `hasattr(grounded_quality_review, "_spectral_tilt")`.
3. Check `[f.name for f in dataclasses.fields(GroundedMetrics)]` and
   `[f.name for f in dataclasses.fields(QualityReviewResult)]`.

**Expected result:**
- `hasattr(grounded_quality_review, "_spectral_tilt") is False`.
- No field named `spectral_tilt`, `spectral_tilt_delta`, or similar exists on
  `GroundedMetrics` or `QualityReviewResult`.

---

### TC-2529 — `clarity_delta` (and `clarity_gain`) absent from `grounded_quality_review`'s public and private surface

**Covers:** AC1, AC2, AC3
**Type:** Negative control

**Steps:**
1. Check `hasattr(grounded_quality_review, "clarity_delta")` and
   `hasattr(grounded_quality_review, "clarity_gain")`.
2. Check `dataclasses.fields(GroundedMetrics)` and `dataclasses.fields(QualityReviewResult)`
   for any field named `clarity_delta`/`clarity_gain`.
3. Search `evaluate_quality_review`'s and `compute_grounded_metrics`'s source (via
   `inspect.getsource`) for the literal substrings `"clarity_delta"` and `"_spectral_tilt"`.

**Expected result:**
- Both `hasattr` checks are `False`.
- No such dataclass field exists.
- Neither literal substring appears in either function's source.

---

### TC-2530 — Old proxy metrics still exist, unmodified, in the deprecated `final_quality_review.py` (positive control for "retained, not deleted")

**Covers:** Architecture §2 ("existing files unchanged (retained, deprecated)")
**Type:** Regression (this is a lock on architecture's explicit retention decision, not a
correctness test — labeled per this repo's convention that a regression test must not be
mistaken for a correctness test)

**Steps:**
1. `import final_quality_review` (STORY-015's original module, `stories/STORY-015/
   implementation/final_quality_review.py`).
2. Check `hasattr(final_quality_review, "_spectral_tilt")` and the presence of
   `clarity_delta` computation in `_summary_metrics`'s source.

**Expected result:** both are still present — this story does not delete dead code from
`final_quality_review.py` (architecture §2 explicit non-goal). If this test fails because
the symbols are gone, either an out-of-scope deletion happened, or `final_quality_review.py`
itself changed unexpectedly — either warrants investigation, not a fix to this test.

---

## Section 6 — `match_levels()` (architecture §4)

### TC-2531 — No-op-like case: processed already within tolerance of original's LUFS

**Covers:** Architecture §4.2/§4.3
**Type:** Functional / boundary

**Preconditions:** F-2501, `delta_db = 0.3` (processed already only 0.3 dB louder than
original — inside the 0.5 LU tolerance before any correction is even applied).

**Steps:**
1. Call `match_levels(original, processed, sr, tolerance_lu=0.5)`.
2. Read `gain_applied_db`, `matched_processed_lufs`, `within_tolerance`.

**Expected result:**
- `gain_applied_db == original_lufs - processed_lufs == -0.3` (±0.01) — a small corrective
  gain is still computed and applied; there is no "skip correction, already close enough"
  branch per architecture §4.3's docstring ("apply a single linear gain... Never silently
  returns an unmatched result" — correction always runs).
- `matched_processed_lufs` equals `original_lufs` to within numerical precision (±0.01 LU),
  by the uniform-gain-on-stationary-signal argument in F-2501.
- `within_tolerance is True`.

---

### TC-2532 — Gain-correction case: processed requires a larger correction

**Covers:** Architecture §4.1/§4.3
**Type:** Functional

**Preconditions:** F-2501, `delta_db = 6.0` (processed 6 dB louder than original — a clearly
audible, clearly-outside-tolerance gap before matching).

**Steps:**
1. Call `match_levels(original, processed, sr, tolerance_lu=0.5)`.
2. Read `gain_applied_db`, `matched_processed_lufs`, `within_tolerance`.

**Expected result:**
- `gain_applied_db == -6.0` (±0.01) — processed must be turned down by 6 dB to match
  original.
- `matched_processed_lufs` equals `original_lufs` to within ±0.01 LU.
- `within_tolerance is True`.
- `matched_processed` (the returned array) equals `processed * 10**(-6.0/20.0)` element-wise
  (±1e-6) — confirms a single linear gain, not a dynamic/frequency-dependent process, was
  applied (per §4.1's "apply a single linear gain").

---

### TC-2533 — Stereo pair: gain applied identically to both channels

**Covers:** Audio-specific coverage (mono vs stereo)
**Type:** Functional

**Preconditions:** F-2501 stereo variant (`original_stereo`, both channels identical),
`delta_db = 4.0`.

**Steps:**
1. Call `match_levels(original_stereo, processed_stereo, sr, tolerance_lu=0.5)`.
2. Compare `matched_processed[:, 0]` to `matched_processed[:, 1]`.

**Expected result:** the two output channels remain identical to each other (±1e-9) — a
single scalar gain applied uniformly, not a per-channel-diverging process. `gain_applied_db
== -4.0` (±0.01), same as the mono case (stereo LUFS measurement of two identical channels is
mathematically equivalent to the mono case for this fixture).

---

### TC-2534 — Boundary: residual exactly at `tolerance_lu` counts as within tolerance (assumption, OQ-D)

**Covers:** Architecture §4.3 (`within_tolerance` boundary)
**Type:** Edge case / boundary — **[OPEN, see OQ-D]**

**Preconditions:** `measure_integrated_lufs` patched directly (not derived from a real
signal) so that: `original_lufs = -14.0` (fixed), first `processed` measurement returns
`-15.0` (1.0 LU gap), and the post-gain re-measurement of `matched_processed` is patched to
return exactly `-14.5` (0.5 LU residual — deliberately not a perfect match, to test the
tolerance comparison itself in isolation from the gain arithmetic).

**Steps:**
1. Call `match_levels(original, processed, sr, tolerance_lu=0.5)` with the patches above.
2. Read `within_tolerance`. Confirm no exception raised.

**Expected result (assuming inclusive `<=`, per OQ-D):** `within_tolerance is True`; no
`LevelMatchError` raised. **If python-developer implements exclusive (`<`) comparison, this
test must be rewritten to expect `LevelMatchError`** — flagged, do not guess silently.

---

### TC-2535 — Boundary: residual one thousandth of a LU over tolerance raises `LevelMatchError`

**Covers:** Architecture §4.3 ("Raises LevelMatchError if... the re-measured match falls
outside tolerance_lu")
**Type:** Edge case / boundary

**Preconditions:** Same patch setup as TC-2534, except the post-gain re-measurement returns
`-14.501` (0.501 LU residual — just outside tolerance regardless of inclusive/exclusive
convention).

**Steps:**
1. Call `match_levels(original, processed, sr, tolerance_lu=0.5)`.

**Expected result:** raises `LevelMatchError`. This is unambiguous under either boundary
convention (0.501 > 0.5 either way), unlike TC-2534.

---

### TC-2536 — Non-finite LUFS (silence) raises `LevelMatchError`, does not return a degraded result

**Covers:** Architecture §4.3 ("Raises LevelMatchError if either LUFS measurement is
non-finite")
**Type:** Failure mode

**Preconditions:** F-2503 (silent `original`).

**Steps:**
1. Call `match_levels(original, processed, sr, tolerance_lu=0.5)`.

**Expected result:** raises `LevelMatchError`. No `LevelMatchResult` with a placeholder/NaN
`gain_applied_db` is returned in its place.

---

### TC-2537 — Bimodal/gating-edge material can genuinely fail the re-verified match (documents the named edge case, §4.2)

**Covers:** Architecture §4.2 ("a block that crosses the relative gate threshold... is a
real but narrow edge case")
**Type:** Edge case (real signal, not mocked)

**Preconditions:** F-2502 (bimodal near-silent + loud construction).

**Steps:**
1. Call `match_levels(original, processed, sr, tolerance_lu=0.5)`.

**Expected result:** either (a) `LevelMatchError` is raised because the gating pattern
shifted enough that the residual exceeds 0.5 LU, or (b) `within_tolerance is True` because
this particular construction did not shift the gate boundary enough. **This test's purpose
is to confirm the code path handles the case without crashing unexpectedly (e.g. no
`ZeroDivisionError`/`nan` propagating silently)** — assert only that the result is one of
these two well-defined outcomes, not a specific one; architecture explicitly frames this as
a "real but narrow edge case," not a deterministic-by-construction scenario like F-2501.

---

## Section 7 — Supplementary: `human_review_capture.py` and `build_validation_report()` (AC8, AC9)

These are included for AC8/AC9 traceability completeness; full `build_validation_report()`
integration testing (real files, real human review) is explicitly deferred per architecture
§9 ("the human-listening re-run itself is out of scope for STORY-025's own acceptance").

### TC-2538 — Templated/auto-generated note text is rejected (anti-templating denylist)

**Covers:** AC8, architecture §6.2
**Type:** Functional / negative control

**Preconditions:** A `<track>.review.json` fixture with
`"note": "REJECT — real-world validation on Sunday Club; the source remained musically
weak..."` (the exact old auto-generated phrase architecture §6.2 names as denylisted).

**Steps:**
1. Call `capture_human_review(track_path, interactive=False)`.

**Expected result:** raises `HumanReviewRequiredError` (or an equivalent explicit rejection —
architecture does not name a distinct exception for this specific case; assert at minimum
that no `HumanReviewRecord` is returned) — a stale copy-paste of the old template text must
not be accepted as if a human authored it.

---

### TC-2539 — Note shorter than 10 characters is rejected

**Covers:** Architecture §6.2 ("at least 10 characters")
**Type:** Edge case / boundary

**Preconditions:** Review file with `"note": "ok good."` (9 characters after stripping).

**Steps:**
1. Call `capture_human_review(track_path, interactive=False)`.

**Expected result:** raises (review rejected as insufficiently substantive). A 10-character
note (boundary) should be accepted if it doesn't match the denylist — companion boundary
case: `"note": "acceptable"` (10 chars) should pass validation length-wise.

---

### TC-2540 — Non-interactive environment does not fall through to a silent default when no review file exists

**Covers:** Architecture §6.1 ("a non-interactive environment cannot produce a 'real' human
review")
**Type:** Failure mode — **[OPEN, see OQ-E for exact raise point]**

**Preconditions:** No `<track>.review.json` present; `interactive=True` but stdin is mocked
to report `isatty() == False`.

**Steps:**
1. Call `capture_human_review(track_path, interactive=True)`.

**Expected result:** raises (an error in the `HumanReviewRequiredError` family, per OQ-E) —
no `HumanReviewRecord` with an empty/placeholder decision is returned, and no `input()` call
is silently skipped in favor of a default.

---

### TC-2541 — `build_validation_report()` with no `human_reviews` and `interactive_review=False` raises, naming the file

**Covers:** AC9, architecture §8 step 2
**Type:** Functional (structural — mock `pipeline.run`)

**Preconditions:** `pipeline.run` mocked (never actually invoked for real audio in this
test); `verify_stem_separation_environment` mocked to succeed trivially; one path in
`paths`, no corresponding entry in `human_reviews`, `interactive_review=False`.

**Steps:**
1. Call `build_validation_report(paths=[path], human_reviews=None, interactive_review=False)`.

**Expected result:** raises `HumanReviewRequiredError` whose message names the specific
`path` missing a review. `pipeline.run` is **not** called for that file (the check happens
before the pipeline invocation, per §8 step 2 ordering — "if absent... raise... this is the
'no default bypass' requirement").

---

## Coverage checklist

**Correctness** — Happy path per AC covered (§1–§3, §6). Boundary values at/under/over
threshold covered for all three flags (TC-2504, TC-2506, TC-2507) and the LUFS tolerance
(TC-2534, TC-2535). Idempotency: not applicable in the DSP sense — this module does not
reprocess already-processed audio; `evaluate_quality_review` is called once per
mastering run. Bypass/disabled: N/A — there is no "disabled" mode for quality review; the
closest analogue, `human_review=None`, is exhaustively covered (§3) as `pending_human_review`
rather than a silent bypass.

**Audio-specific** — Mono/stereo: TC-2533 (match_levels stereo). Sample rates: F-2501/§6
fixtures parametrized at 44100 Hz; 48000 Hz is not separately re-derived because
`match_levels`'s correctness argument (uniform gain shifts LUFS by exactly the gain amount)
is sample-rate-independent — recommend python-developer parametrize TC-2531/2532 over both
rates as a cheap regression check, but no new analytical derivation is needed per rate.
Silence/near-silence: TC-2509, TC-2536. Full-scale/clipping input: not applicable to this
story's scope (this module measures deltas between already-processed audio; clipping
detection is `_true_peak`/true-peak-limiter territory, out of scope per requirements'
"redesigning... measurement implementations" exclusion). Very quiet input: covered by
F-2502's near-silent section. DC offset: explicitly out of scope — DC handling is the
responsibility of `measure_integrated_lufs`/`measure_seven_band_balance`'s own
implementations (already tested by their originating stories); this story only reuses them.
Very short file: TC-2522 (environment-check fixture-duration case) covers the short-file
failure mode for that module; `match_levels`/`compute_grounded_metrics` do not define their
own minimum-duration behavior beyond what `measure_integrated_lufs` already enforces
(non-finite LUFS on too-short/too-quiet input is exercised via TC-2509/TC-2536).

**Failure modes** — Corrupt/truncated file: N/A at this module's level (file I/O is not this
story's contract — audio arrives as already-loaded `np.ndarray`); the file-existence/duration
case that *is* in this story's contract (`verify_stem_separation_environment`'s fixture) is
covered by TC-2522. Missing file: same — TC-2522's fixture-duration case is the closest
analogue in scope; a literal missing-`fixture_path` case is flagged under OQ-C. Wrong channel
count: not separately tested — `measure_integrated_lufs`/`measure_seven_band_balance`'s own
channel-count validation is out of this story's reuse-only scope.

**Units and precision** — Every test above states LUFS vs. dB vs. dBTP-equivalent explicitly
per field (`spectral_rms_shift_db` in dB, `dr_delta` in DR units, `artifact_density_delta`
dimensionless 0–1, `gain_applied_db`/`lufs_*` in LU/dB). `peak_delta_db_unmatched` is
explicitly tested (TC-2510) as *not* level-matched, distinguishing it from every other
before/after field in this module, which is exactly the naming hazard architecture §7.5 flags.

---

## Traceability table

| Acceptance criterion (requirements.md) | Test cases |
|---|---|
| AC1 — spectral-balance delta from `measure_seven_band_balance` | TC-2501, TC-2502, TC-2507, TC-2520, TC-2528 |
| AC2 — dynamics delta from `measure_dynamic_range` | TC-2503, TC-2504, TC-2529 |
| AC3 — no new ad hoc metric invented | TC-2501, TC-2511, TC-2513, TC-2528, TC-2529, TC-2530 |
| AC4 — artifact-density before/after included in decision inputs | TC-2505, TC-2506, TC-2511 |
| AC5 — LUFS measured + level-matched before any delta | TC-2508, TC-2531, TC-2532, TC-2533 |
| AC6 — reject/fail loudly on unmatched levels, not silently compute | TC-2509, TC-2535, TC-2536 |
| AC7 — environment-verification before stem-first trust | TC-2521–TC-2527 |
| AC8 — `human_decision`/`human_note` reflect a real person, not templated/empty | TC-2515–TC-2517, TC-2538–TC-2540 |
| AC9 — no default bypass to a trusted verdict without human review | TC-2515, TC-2541 |
| Gate 1 Finding 1 (artifact_density_regression PROVISIONAL audit) | TC-2506, TC-2511 |
| Gate 1 Finding 2 (spectral_shift_flag_db PROVISIONAL audit) | TC-2507, TC-2511 |
| Gate 1 Finding 4 (`clip_offset_seconds=30.0` action item) | TC-2521, TC-2522, TC-2523 |
| Reproducibility (NFR) | TC-2519 |

Gaps visible in this table: no test case independently re-validates AC1/AC2's *underlying*
measurement correctness (seven-band, DR) — this is intentional, per architecture's
"reuse, not reimplement" boundary; those functions' own correctness is STORY-001/STORY-002's
test suite's responsibility, not this one's.
