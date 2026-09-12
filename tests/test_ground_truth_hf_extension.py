"""STORY-003 ground-truth tests -- HF extension / rolloff (AC6),
test-cases.md TC-020 through TC-029. This is DEF-201's defect surface.

Every test in this file uses ref_config(hf_min_duration_s=2.0) (architecture.md
Section 1.3/7.3) so 2-5s fixtures reach the real scan path instead of the
insufficient_duration fallback.

**AC11/AC6 sequencing note**: TC-024 (test_tc024_pink_noise_no_cutoff) is the
designated failing-test-first case for DEF-201 (stories/STORY-002/defects.md).
It is run here against the CURRENT, UNMODIFIED shipped code
(hf_rolloff_threshold_db=6.0, reference_analysis/config.py) and is EXPECTED
TO FAIL at the time this file is first run in this pass -- do not silently
skip/weaken it to force a pass. See defects.md's DEF-201 entry for the
recorded actual-vs-expected numbers from this exact run.
"""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.analysis.hf_extension import measure_hf_extension

from .ref_helpers import (
    brickwall_lowpass_noise_mono,
    brickwall_lowpass_noise_with_floor_mono, white_noise_mono, pink_noise_mono,
    tilted_noise_mono, tilt_nonstationary_no_cutoff_mono, steep_air_band_brickwall_mono,
    lowpassed_white_noise,
    to_stereo, ref_config,
)

pytestmark = pytest.mark.ground_truth

SR = 44100


def test_tc019_method_field_declared_as_cliff_detection():
    """Regression check: the HF extension result must expose the active method name."""
    mono = brickwall_lowpass_noise_mono(SR, duration_s=3.0, cutoff_hz=15000.0, seed=1, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.method == "cliff_detection"


def test_tc020_brickwall_15k_detected_within_tolerance():
    """AC6a. A true brickwall (spectral-domain rectangular cutoff, zero
    energy above cutoff_hz) has a threshold-crossing frequency that is
    INDEPENDENT of how deep the threshold is -- both a 6dB and a 40dB
    crossing sit at cutoff_hz to within a few Welch-PSD leakage bins.
    Passes both before and after the DEF-201 threshold fix -- this is NOT
    the defect's regression fixture."""
    mono = brickwall_lowpass_noise_mono(SR, duration_s=3.0, cutoff_hz=15000.0, seed=1, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.insufficient_duration is False
    assert result.hf_band_limit_hz == pytest.approx(15000.0, abs=config.hf_rolloff_test_tolerance_hz)
    assert result.stable is True


def test_tc021_brickwall_8k_detected_within_tolerance():
    """AC6b. Same derivation as TC-020, cutoff_hz=8000.0."""
    mono = brickwall_lowpass_noise_mono(SR, duration_s=3.0, cutoff_hz=8000.0, seed=1, amplitude=0.3)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.insufficient_duration is False
    assert result.hf_band_limit_hz == pytest.approx(8000.0, abs=config.hf_rolloff_test_tolerance_hz)


def test_tc022_full_band_white_noise_reports_no_cutoff():
    """AC6c, negative control. White noise has a flat power spectral density
    by construction; on the 1/24-octave log-frequency grid used by the v1.5a
    cliff detector, flat-PSD noise produces slightly RISING power per band
    (bandwidth proportional to frequency), so no window in the search range
    shows the sustained 8 dB drop required by hf_cliff_required_drop_db --
    total_drop is negative across every candidate window and _gate_scan
    returns None. hf_band_limit_hz must therefore be None (architecture.md
    Section 3.3/3.5, hf_extension.py module docstring: "No cliff found
    anywhere in the search range -> hf_band_limit_hz = None. Never Nyquist,
    never a fallback value").

    v1.5a change: the superseded threshold-crossing design (DEF-201) would
    have returned a near-Nyquist value; the cliff detector correctly returns
    None for flat-spectrum input. All per-segment results are also None
    (each segment independently sees flat white noise with no cliff)."""
    mono = white_noise_mono(SR, duration_s=3.0, seed=1, amplitude=0.2)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.insufficient_duration is False
    assert result.hf_band_limit_hz is None
    assert all(s is None for s in result.per_segment_hf_band_limit_hz), (
        f"Expected all per-segment results to be None for flat white noise; "
        f"got {result.per_segment_hf_band_limit_hz}"
    )


def test_tc023_finite_stopband_floor_probes_whether_deepened_threshold_is_too_deep():
    """AC6 extended (test-cases.md TC-023 / v1.2). Negative control that the
    infinite-floor brickwall fixtures (TC-020/021/024) structurally CANNOT
    provide: a finite (27 dB down, not silent) stopband, matching a
    realistic mid-quality lossy-encoder anti-aliasing floor. Zeroing this
    gap is the entire point of this test -- see defects.md DEF-201 for the
    threshold-sweep table this test's result feeds into. Written against
    whatever hf_rolloff_threshold_db the shipped config currently carries --
    intentionally NOT hardcoded to a particular pre/post-fix value, so this
    test's outcome (pass or fail) is itself the reported evidence, not
    assumed."""
    mono = brickwall_lowpass_noise_with_floor_mono(
        SR, duration_s=3.0, cutoff_hz=16000.0, floor_below_db=27.0, seed=1, passband_sigma=0.15
    )
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.insufficient_duration is False
    assert result.hf_band_limit_hz == pytest.approx(16000.0, abs=config.hf_rolloff_test_tolerance_hz), (
        f"measured hf_band_limit_hz={result.hf_band_limit_hz} against a fixture whose real "
        f"cutoff is 16000 Hz with a 27 dB-down (non-silent) stopband floor -- see "
        f"defects.md DEF-201 threshold-sweep table for context."
    )


def test_tc024_pink_noise_no_cutoff():
    """AC6d -- the literal DEF-201 regression fixture. Pink noise has a
    naturally declining (-3 dB/octave) spectrum by construction, but this
    decline is a smooth tilt, not a cutoff -- a correct detector must not
    mistake ordinary spectral tilt for a real high-frequency rolloff. This
    is exactly DEF-201's defect surface: a shallow threshold (6 dB, the
    currently-shipped default) crosses within the first ~1-2 octaves above
    the reference band on any material with ordinary tilt, reporting a
    false mid-band "cutoff".

    v1.5a behavior: pink noise on the 1/24-octave log grid has approximately
    FLAT power per band (the -3 dB/octave PSD decline is exactly offset by
    the 3 dB/octave bandwidth increase), so no window satisfies the 8 dB
    monotonic-drop requirement -- _gate_scan returns None and
    hf_band_limit_hz is None (architecture.md Section 3.3/3.5).

    THIS TEST WAS EXPECTED TO FAIL against the unmodified shipped code
    (hf_rolloff_threshold_db=6.0) -- see stories/STORY-002/defects.md's
    DEF-201 entry for the actual recorded rolloff_hz value from that run,
    and the post-fix value once python-developer applies a corrected
    threshold."""
    mono = pink_noise_mono(SR, duration_s=3.0, seed=1)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.insufficient_duration is False
    assert result.hf_band_limit_hz is None, (
        f"DEF-201 regression: pink noise (no real cutoff) reported hf_band_limit_hz="
        f"{result.hf_band_limit_hz} -- expected None (no cliff detected) under v1.5a "
        f"cliff detection (architecture.md Section 3.3/3.5)."
    )
    assert all(s is None for s in result.per_segment_hf_band_limit_hz), (
        f"Expected all per-segment results to be None for pink noise; "
        f"got {result.per_segment_hf_band_limit_hz}"
    )


def test_tc025_drift_detection_fires_on_changing_cutoff():
    """AC6e. Three-step cutoff progression (15 kHz -> 12 kHz -> 8 kHz, 1.5s
    each = 4.5s total) ensures the whole-track gate finds 15 kHz (i_max at
    the highest qualifying candidate), while per-segment agreement is limited
    to the segments that contain 15 kHz material.

    Segment breakdown (~5 x 0.9s each over 4.5s total):
      - Seg 0 (~0-0.9s): pure 15 kHz -> agrees (|delta| = 0 Hz <= 2000 Hz)
      - Seg 1 (~0.9-1.8s): mixed 15 kHz/12 kHz -> i_max still 15 kHz -> agrees
        (pre-slope ~2 dB/octave at 15k < 12 dB/octave gate limit; drop to zero)
      - Seg 2 (~1.8-2.7s): pure 12 kHz -> disagrees (|15k-12k| = 3000 Hz > 2000 Hz)
      - Seg 3 (~2.7-3.6s): mixed 12 kHz/8 kHz -> disagrees regardless (both
        cutoffs are outside the +/-2000 Hz tolerance from the whole-track 15k value)
      - Seg 4 (~3.6-4.5s): pure 8 kHz -> disagrees (|15k-8k| = 7000 Hz > 2000 Hz)
    Confidence <= 2/5 = 0.4 < hf_cliff_confidence_stable_floor (0.6) -> stable=False.

    v1.5a change from the v1.4 two-step fixture (15k/8k, equal 2s each):
    Under v1.5a, i_max selects the HIGHEST qualifying candidate (15 kHz),
    and the boundary segment of the equal split found 15 kHz as i_max in its
    own per-segment PSD (pre-slope ~3 dB/octave < 12 dB/octave gate limit),
    pushing confidence to exactly 3/5 = 0.6 = stable_floor -> stable=True
    (wrong). The three-step construction places both 12 kHz and 8 kHz outside
    the +/-2000 Hz tolerance, ensuring at most 2 out of 5 segments agree with
    the 15 kHz whole-track value.

    Per-segment spread assertion: the non-None per-segment values must span
    more than hf_stability_tolerance_hz (2000 Hz) -- derivable from the
    fixture's own construction (15k/12k/8k brickwall edges are separated by
    3000 Hz and 4000 Hz respectively, both exceeding the tolerance). This
    distinguishes genuine drift from a spurious low-confidence value.

    Threshold-independent (brickwall edges)."""
    p1 = brickwall_lowpass_noise_mono(SR, duration_s=1.5, cutoff_hz=15000.0, seed=1, amplitude=0.3)
    p2 = brickwall_lowpass_noise_mono(SR, duration_s=1.5, cutoff_hz=12000.0, seed=2, amplitude=0.3)
    p3 = brickwall_lowpass_noise_mono(SR, duration_s=1.5, cutoff_hz=8000.0, seed=3, amplitude=0.3)
    mono = np.concatenate([p1, p2, p3])
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR, config)
    assert result.stable is False, (
        f"Three-step drift (15k->12k->8k) should be unstable; "
        f"got confidence={result.hf_band_limit_confidence:.3f} (stable_floor=0.6), "
        f"stable={result.stable}, per_segment={result.per_segment_hf_band_limit_hz}"
    )
    assert result.hf_band_limit_hz is not None, (
        f"Whole-track gate must find the 15 kHz cliff; got None. "
        f"per_segment={result.per_segment_hf_band_limit_hz}"
    )
    # Correctness: the per-segment vector must contain at least two distinct
    # non-None values spanning more than hf_stability_tolerance_hz -- derivable
    # from the construction (min separation between any two cutoffs is 3000 Hz
    # > 2000 Hz). This proves the instability reflects genuine multi-step drift,
    # not a single-value confidence quirk.
    non_none_segs = [s for s in result.per_segment_hf_band_limit_hz if s is not None]
    assert len(non_none_segs) >= 2, (
        f"Expected at least 2 non-None per-segment values; got {result.per_segment_hf_band_limit_hz}"
    )
    seg_spread_hz = max(non_none_segs) - min(non_none_segs)
    assert seg_spread_hz > config.hf_stability_tolerance_hz, (
        f"Per-segment spread {seg_spread_hz:.0f} Hz must exceed "
        f"hf_stability_tolerance_hz={config.hf_stability_tolerance_hz:.0f} Hz; "
        f"got per_segment={result.per_segment_hf_band_limit_hz}"
    )


# --- TC-026/027/028/029: DEF-201 blast-radius migration/due-diligence -----
# These are process/documentation checks per architecture.md Section 2.5 /
# Section 6 step 3 -- the actual re-fixturing of test_tc304/test_tc305 in
# test_ref_ac10_verification_bars.py (from lowpassed_white_noise onto
# brickwall_lowpass_noise_mono) is explicitly python-developer's action,
# performed together with the one-line hf_rolloff_threshold_db config
# change (architecture.md Section 6 step 3) -- NOT done here, since this
# pass does not apply the DEF-201 fix. Recorded as skipped placeholders so
# the traceability table has a concrete anchor and so a future run of this
# file after the fix lands is a visible reminder to un-skip/convert these.

@pytest.mark.skip(reason="TC-026: migration of test_tc304 onto brickwall_lowpass_noise_mono is "
                          "performed by python-developer together with the DEF-201 config fix "
                          "(architecture.md Section 6 step 3) -- not yet applied this pass. See "
                          "defects.md DEF-201.")
def test_tc026_migration_test_tc304_16k_placeholder():
    pass


@pytest.mark.skip(reason="TC-027: same as TC-026, for test_tc305 (12 kHz). See defects.md DEF-201.")
def test_tc027_migration_test_tc305_12k_placeholder():
    pass


def test_tc028_tc307_tc308_unaffected_by_threshold_depth_baseline():
    """TC-028 due-diligence, run now as a BASELINE (pre-fix) confirmation
    that these two existing tests are unaffected by threshold depth, per
    architecture.md Section 2.5's own claim (test_tc307 only asserts
    insufficient_duration; test_tc308's stability spread, ~8000 Hz between
    16000/10000 Hz cutoffs via lowpassed_white_noise, still comfortably
    exceeds hf_stability_tolerance_hz=2000 even after a threshold shift).
    Re-verify again after the fix lands as part of the full regression
    suite -- not repeated here.

    Part 2 (stability) fixture change from v1.4: the original equal 20s/20s
    split (half1=20s at 16k, half2=20s at 10k) gave 3/5 = 0.6 agreement
    under v1.5a because the boundary segment found 16k as i_max in its mixed
    PSD (pre-slope < 12 dB/octave limit -> gate admissible), pushing
    confidence exactly to hf_cliff_confidence_stable_floor -> stable=True
    (wrong). Fixed by using half1=5s at 16k, half2=20s at 10k (total 25s,
    5 segments of 5s each): only the first pure-16k segment agrees; the
    remaining four pure-10k segments all disagree -> confidence = 1/5 = 0.2
    < 0.6 -> stable=False."""
    from .ref_helpers import lowpassed_white_noise

    config = ref_config(hf_min_duration_s=3.0, hf_stability_segment_count=2)
    mono = lowpassed_white_noise(SR, 2.9, cutoff_hz=16000.0, amplitude=0.3)
    result = measure_hf_extension(to_stereo(mono), SR, config)
    assert result.insufficient_duration is True

    half1 = lowpassed_white_noise(SR, 5.0, cutoff_hz=16000.0, seed=1, amplitude=0.3)
    half2 = lowpassed_white_noise(SR, 20.0, cutoff_hz=10000.0, seed=2, amplitude=0.3)
    mono2 = np.concatenate([half1, half2])
    result2 = measure_hf_extension(to_stereo(mono2), SR, ref_config(hf_min_duration_s=2.0))
    assert result2.stable is False, (
        f"16k/10k two-segment drift should be unstable; "
        f"got confidence={result2.hf_band_limit_confidence:.3f}, "
        f"stable={result2.stable}, per_segment={result2.per_segment_hf_band_limit_hz}"
    )
    assert result2.hf_band_limit_hz is not None


@pytest.mark.skip(reason="TC-029: suspected_transcode behavior-change documentation/expectation-"
                          "setting check against the real five-track reference set -- not run "
                          "this pass (no code change applied yet to compare before/after). "
                          "See architecture.md Section 2.5 item 2 and defects.md DEF-201.")
def test_tc029_suspected_transcode_change_is_expected_not_regression_placeholder():
    pass


# --- TC-430 / TC-431 / TC-432: hf_band_limit_robustness_db (DEF-206 fix) -----
# Three fixtures for architecture.md §11.7.  All use hf_stability_segment_count=1
# so the single per-segment margin equals the whole-track two-sided j* margin,
# making §11.7's by-construction derivations apply directly to the measured field.
# (With the default 5-segment count the per-segment minimum is a min-of-N draw;
# the 1-segment config is the clean way to pin the two-sided formula without
# fighting Welch noise on the aggregation.)
# NOTE: DEF-206 cannot be formally closed (H7 criterion 2 -- test-before-fix --
# is not met: the field shipped before these tests were written). These tests
# provide regression coverage and validate the implementation against §11.7's
# derivations, but the formal DEF-206 entry remains Open per HANDOFF.md H7.


def test_tc430_robustness_rightward_dominated():
    """TC-430 (architecture.md §11.7 Fixture 1): rightward-margin-dominated case.

    Signal: brickwall lowpass at 16 kHz with a finite stopband floor set
    exactly hf_cliff_required_drop_db + 2.0 dB = 8.0 + 2.0 = 10.0 dB below
    the passband level.

    Two-sided margin derivation (§11.7):
      rightward_margin = L - suffix_max[j*]
          ≈ (passband - 8.0) - (passband - 10.0) = 2.0 dB  (by construction)
      leftward_margin = levels_db[j*-1] - L
          ≈ hf_cliff_required_drop_db = 8.0 dB  (j*-1 ≈ passband anchor)
      min(2.0, 8.0) = 2.0 dB  → rightward-dominated

    Probe measured 1.878 dB (floor noise adds ~0.12 dB to passband, slightly
    narrowing the gap from the nominal 2.0 dB; this is within the ±0.5
    tolerance). hf_stability_segment_count=1 ensures the single per-segment
    margin IS the whole-track margin -- §11.7's derivation applies directly.

    Exercises the rightward-margin branch of _floor_onset_index's two-sided
    formula (architecture.md §11.3.1). Does NOT validate the gate anchor
    (i_max from _gate_scan) -- see DEF-205 (Open/Architectural)."""
    required_drop_db = 8.0  # hf_cliff_required_drop_db default
    floor_below_db = required_drop_db + 2.0  # = 10.0; rightward margin = 2.0 by construction

    mono = brickwall_lowpass_noise_with_floor_mono(
        SR, duration_s=3.0, cutoff_hz=16000.0, floor_below_db=floor_below_db,
        seed=1, passband_sigma=0.15
    )
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, (
        f"Fixture must detect the 16 kHz cliff (floor is {floor_below_db:.0f} dB down, "
        f"well above the {required_drop_db:.0f} dB gate bar); got None."
    )
    assert result.hf_band_limit_robustness_db is not None, (
        "hf_band_limit_robustness_db must be non-None when hf_band_limit_hz is detected"
    )
    assert result.hf_band_limit_robustness_db == pytest.approx(2.0, abs=0.5), (
        f"TC-430: expected rightward-dominated two-sided margin ≈ 2.0 ± 0.5 dB "
        f"(floor set {floor_below_db:.0f} dB down, rightward = floor_below - 8.0 = "
        f"{floor_below_db - required_drop_db:.1f} dB by construction); "
        f"got {result.hf_band_limit_robustness_db:.4f} dB. "
        f"If this fails low, check whether floor noise pulled the passband level up "
        f"(expected ~0.12 dB for floor_below_db=10 per brickwall_lowpass_noise_with_floor_mono's "
        f"own docstring)."
    )


def test_tc431_robustness_leftward_dominated():
    """TC-431 (architecture.md §11.7 Fixture 2): leftward-margin-dominated case.

    Signal: clean brickwall lowpass at 16 kHz with a digital-zero stopband
    (FFT-zero above cutoff_hz → suffix_max[j*] ≈ _MIN_POWER ≈ −200 dBFS).

    Two-sided margin derivation (§11.7):
      rightward_margin = L - suffix_max[j*]
          ≈ L - (−200) >> 50 dB  (suffix_max is at the numerical floor)
      leftward_margin = levels_db[j*-1] - L
          = hf_cliff_required_drop_db = 8.0 dB exactly
          (j*-1 = i_max by construction: brickwall places j* one band above i_max,
           so levels_db[j*-1] = levels_db[i_max] = passband anchor;
           L = passband_anchor - 8.0 → leftward = 8.0 exactly)
      min(large, 8.0) = 8.0 dB  → leftward-dominated

    Probe verified: whole-track margin = 8.0000 dB exactly; leftward = 8.0 dB;
    rightward = 107.9 dB (suffix_max at −181 dBFS ≈ 10*log10(1e-20)).
    Both 1-segment and 5-segment runs return exactly 8.0 (no noise, exact floor).

    This value is *derived*, not tuned: it equals hf_cliff_required_drop_db
    because the gate criterion structurally ensures levels_db[i_max] - L = 8.0
    when j* = i_max + 1 (architecture.md §11.3.1). Exercises the leftward-margin
    branch of the two-sided formula."""
    mono = brickwall_lowpass_noise_mono(
        SR, duration_s=3.0, cutoff_hz=16000.0, seed=1, amplitude=0.3
    )
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, (
        "Fixture must detect the 16 kHz cliff (digital-zero stopband); got None."
    )
    assert result.hf_band_limit_robustness_db is not None, (
        "hf_band_limit_robustness_db must be non-None when hf_band_limit_hz is detected"
    )
    assert result.hf_band_limit_robustness_db == pytest.approx(8.0, abs=1.0), (
        f"TC-431: expected leftward-dominated two-sided margin ≈ 8.0 ± 1.0 dB "
        f"(= hf_cliff_required_drop_db, derived per §11.7); "
        f"got {result.hf_band_limit_robustness_db:.4f} dB. "
        f"A value well below 7.0 dB would indicate j*-1 is not at the passband anchor — "
        f"check _floor_onset_index's j*-1 look-up."
    )


def test_tc432_robustness_none_branch():
    """TC-432 (architecture.md §11.7 Fixture 3): None-branch coverage.

    Every signal that produces hf_band_limit_hz = None must also produce
    hf_band_limit_robustness_db = None (architecture.md §11 and
    HfExtensionResult docstring: 'None when hf_band_limit_hz is None, or when
    no segment found a cliff').

    Fixtures (reusing existing generators — no new fixture creation per §11.7):
      1. Pink noise  (TC-024's signal: –3 dB/oct tilt, no cliff → None)
      2. White noise (TC-022's signal: flat PSD, no cliff → None)
      3. Tilted noise (–6 dB/oct, full band to Nyquist, DEF-204 negative control)
      4. Tilt-nonstationary (changing slope, no lowpass, STORY-004 §5.1)

    hf_stability_segment_count=1 used consistently with TC-430/TC-431."""
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)

    # Pink noise
    mono_pink = pink_noise_mono(SR, duration_s=3.0, seed=1)
    result_pink = measure_hf_extension(to_stereo(mono_pink), SR, config)
    assert result_pink.hf_band_limit_hz is None, (
        f"DEF-201 regression: pink noise should produce hf_band_limit_hz=None; "
        f"got {result_pink.hf_band_limit_hz}"
    )
    assert result_pink.hf_band_limit_robustness_db is None, (
        f"None-branch: pink noise hf_band_limit_robustness_db must be None when "
        f"hf_band_limit_hz is None; got {result_pink.hf_band_limit_robustness_db}"
    )

    # White noise
    mono_white = white_noise_mono(SR, duration_s=3.0, seed=1)
    result_white = measure_hf_extension(to_stereo(mono_white), SR, config)
    assert result_white.hf_band_limit_hz is None, (
        f"White noise should produce hf_band_limit_hz=None; got {result_white.hf_band_limit_hz}"
    )
    assert result_white.hf_band_limit_robustness_db is None, (
        f"None-branch: white noise hf_band_limit_robustness_db must be None; "
        f"got {result_white.hf_band_limit_robustness_db}"
    )

    # Tilted noise (–6 dB/oct, no cliff)
    mono_tilt = tilted_noise_mono(SR, duration_s=3.0, slope_db_per_octave=6.0, seed=0)
    result_tilt = measure_hf_extension(to_stereo(mono_tilt), SR, config)
    assert result_tilt.hf_band_limit_hz is None, (
        f"Tilted noise (–6 dB/oct, full band) should produce hf_band_limit_hz=None; "
        f"got {result_tilt.hf_band_limit_hz}"
    )
    assert result_tilt.hf_band_limit_robustness_db is None, (
        f"None-branch: tilted noise hf_band_limit_robustness_db must be None; "
        f"got {result_tilt.hf_band_limit_robustness_db}"
    )

    # Tilt-nonstationary (changing slope per segment, no lowpass anywhere)
    mono_ns = tilt_nonstationary_no_cutoff_mono(SR, seg_duration_s=2.0, n_segments=2, seed=0)
    result_ns = measure_hf_extension(to_stereo(mono_ns), SR, config)
    assert result_ns.hf_band_limit_hz is None, (
        f"Tilt-nonstationary (no cliff) should produce hf_band_limit_hz=None; "
        f"got {result_ns.hf_band_limit_hz}"
    )
    assert result_ns.hf_band_limit_robustness_db is None, (
        f"None-branch: tilt-nonstationary hf_band_limit_robustness_db must be None; "
        f"got {result_ns.hf_band_limit_robustness_db}"
    )


# --- Steep-air-band fixture (§5.1 NEW — REQUIRED, v1.5a Gate 1 Blocker closure) -----

def test_steep_air_band_brickwall_20k_48k():
    """STORY-004 §5.1 NEW — REQUIRED (v1.5a, closes Gate 1 v1.5 Blocker empirically).
    SR=48000. Signal: flat noise below 4 kHz, A(f) = (f/4000)^(-a) above it where
    a = 10.5/(20*log10(2)) ≈ 1.7441, brickwalled at 20 kHz. Power decline above 4 kHz:
    -10.5 dB/oct — between 6 dB/oct (ordinary-tilt range) and 12 dB/oct (gate-rejection
    ceiling), so the 20 kHz brickwall candidate is gate-admissible while exercising the
    steep-air-band case that tilted_then_brickwall_mono's 6 dB/oct slope cannot.

    Construction-time verification (§5.1): levels_db[i] − levels_db[i+24] must read
    10–11 dB/oct for every octave window whose upper band center falls in 10–20 kHz
    (window kept strictly below the 20 kHz brickwall to avoid straddling it and reading
    an inflated slope into the zero stopband).

    Expected: hf_band_limit_hz ≈ 20000 ± 879.1 Hz.
    Tolerance derivation: 1.5 × 20000 × (2^(1/24) − 1) = 879.1 Hz (§5.1 derived table).
    Literal 879.1 used: hf_rolloff_test_tolerance_hz defaults to 500.0 Hz, which is too
    tight for a near-Nyquist target at 48 kHz.

    H7 criterion 2 (test-before-fix) is not met: v1.5 code is no longer available. Per
    TC-432 precedent, documented rather than claimed. Under v1.5's trailing-octave tracker,
    Welch noise could push individual octave windows from the 10.5 dB/oct pre-slope above
    the 12 dB/oct freeze threshold, anchoring passband_level mid-spectrum (~8–15 kHz) and
    producing a wrong number. v1.5a's freeze_index = i_max from _gate_scan resolves this
    (architecture.md §6 risk 13 retired).
    """
    from suno_mastering.analysis._psd import compute_psd, log_band_levels_db

    SR_48K = 48000
    cutoff_hz = 20000.0
    tolerance_hz = 879.1  # derived: 1.5 × 20000 × (2^(1/24) − 1)

    mono = steep_air_band_brickwall_mono(
        SR_48K, duration_s=3.0, shelf_hz=4000.0, slope_db_per_octave=10.5,
        cutoff_hz=cutoff_hz, seed=0, amplitude=0.2,
    )

    # Construction-time slope verification (§5.1): 10–11 dB/oct in 10–20 kHz region.
    # Sweep upper band (i+24) from 10 kHz to 20 kHz; lower band (i) is ~5–10 kHz,
    # well above the 4 kHz shelf, so the slope is purely from the tilt region.
    # Upper bound: band's top edge = center * 2^(1/48); must stay below cutoff so the
    # octave window does not straddle the brickwall (which inflates the measured slope).
    freqs_v, psd_v = compute_psd(mono, SR_48K)
    centers_v, levels_v = log_band_levels_db(freqs_v, psd_v, 1500.0, SR_48K / 2.0)
    band_edge_limit_hz = cutoff_hz / (2.0 ** (1.0 / 48.0))  # ≈ 19714 Hz: upper band edge < cutoff
    check_idxs = [i for i in range(len(centers_v) - 24)
                  if 10000.0 <= centers_v[i + 24] < band_edge_limit_hz]
    assert check_idxs, "No 10–20 kHz bands found for slope verification (grid misconfigured?)"
    for i in check_idxs:
        slope = levels_v[i] - levels_v[i + 24]
        assert 10.0 <= slope <= 11.5, (
            f"Slope {slope:.3f} dB/oct at upper center {centers_v[i + 24]:.0f} Hz "
            f"outside 10–11.5 dB/oct range (§5.1 target 10–11 dB/oct ± 0.5 dB Welch margin, "
            f"still firmly below the 12 dB/oct gate-rejection ceiling). "
            f"Expected ~10.5 dB/oct from (f/4000)^(-1.7441) shaping."
        )

    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0)
    result = measure_hf_extension(audio, SR_48K, config)

    assert result.insufficient_duration is False
    assert result.hf_band_limit_hz is not None, (
        "Steep-air-band+brickwall@20kHz/48kHz must detect a cliff (got None). "
        "10.5 dB/oct pre-slope is gate-admissible (< 12 dB/oct ceiling)."
    )
    assert result.hf_band_limit_hz == pytest.approx(cutoff_hz, abs=tolerance_hz), (
        f"Expected {cutoff_hz:.0f} ± {tolerance_hz:.1f} Hz; "
        f"got {result.hf_band_limit_hz:.1f} Hz. "
        f"A value in 8–15 kHz would indicate v1.5 regression (early tracker freeze)."
    )
    assert result.stable is True, (
        f"Expected stable=True; got confidence={result.hf_band_limit_confidence:.3f}, "
        f"stable={result.stable}, per_segment={result.per_segment_hf_band_limit_hz}"
    )
    assert result.hf_band_limit_robustness_db is not None, (
        "hf_band_limit_robustness_db must be non-None when cliff is detected (DEF-206)"
    )


# --- TC-431b / TC-430b: DEF-206 coverage gaps identified in STORY-004 QA pass -----
# TC-431b closes gap 1: TC-431 passes by algebraic identity on a clean brickwall
#   (j*-1 = i_max always, so leftward_margin = hf_cliff_required_drop_db = 8.0
#   regardless of what levels_db[j*-1] contains). A gradual-transition fixture
#   makes j* land 2+ bands past i_max so levels_db[j*-1] is in the rolloff zone.
# TC-430b closes gap 2: TC-430 and TC-431 both use segment_count=1 so
#   min(segment_margins) over N segments was never exercised.


def test_tc431b_robustness_leftward_discriminating():
    """TC-431b (DEF-206 gap 1): discriminating fixture for the leftward-margin look-up.

    TC-431 uses a digital-zero brickwall where j* = i_max + 1 by construction,
    making j*-1 = i_max and leftward_margin = levels_db[i_max] - L =
    hf_cliff_required_drop_db = 8.0 algebraically — independent of the actual
    levels_db[j*-1] value. An implementation that hardcoded hf_cliff_required_drop_db
    would return 8.0 and pass TC-431 identically.

    This fixture uses lowpassed_white_noise (order-8 zero-phase Butterworth, effective
    order-16 frequency response) so the transition from passband to floor spans 2+
    log-frequency bands. Specifically, at 15 kHz cutoff / SR=44100 on the 1/24-octave
    grid (effective order-16 Butterworth magnitude response):

      band at i_max (~15000 Hz): passband_level (0 dBr reference)
      band at i_max+1 (~15440 Hz): ~−5.5 dBr  → suffix_max > L = −8.0 dBr
      band at i_max+2 (~15887 Hz): ~−8.9 dBr  → suffix_max[i_max+2] < L → j* = i_max+2

    j*-1 = i_max+1 (in the rolloff zone), NOT i_max.
      leftward_margin  = levels_db[i_max+1] − L ≈ −5.5 − (−8.0) = 2.5 dB
      rightward_margin = L − suffix_max[j*]  ≈ −8.0 − (−8.9) = 0.9 dB
      margin_db = min(2.5, 0.9) ≈ 0.9 dB   (well below 8.0)

    Assert 0 < robustness_db < 7.0: a hardcoded implementation returns 8.0 and fails
    the upper bound; a correct implementation reads levels_db[j*-1] and returns ~0.9 dB.
    """
    mono = lowpassed_white_noise(SR, duration_s=3.0, cutoff_hz=15000.0, seed=1, order=8)
    audio = to_stereo(mono)
    config = ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    result = measure_hf_extension(audio, SR, config)

    assert result.hf_band_limit_hz is not None, (
        "TC-431b: order-8 Butterworth lowpass at 15 kHz must produce a detectable cliff "
        "(>8 dB drop exists across any 1/3-octave window past cutoff); got None."
    )
    assert result.hf_band_limit_robustness_db is not None, (
        "hf_band_limit_robustness_db must be non-None when hf_band_limit_hz is detected."
    )
    assert 0.0 < result.hf_band_limit_robustness_db < 7.0, (
        f"TC-431b: gradual Butterworth rolloff places j* 2+ bands past i_max, so "
        f"levels_db[j*-1] is in the transition zone (below passband_level), giving "
        f"leftward_margin < hf_cliff_required_drop_db (8.0 dB). "
        f"Expected 0 < robustness_db < 7.0; got {result.hf_band_limit_robustness_db:.4f} dB. "
        f"A value at or above 7.0 — especially exactly 8.0 — indicates the implementation "
        f"hardcoded hf_cliff_required_drop_db instead of reading levels_db[j*-1] directly."
    )


def test_tc430b_robustness_multi_segment_min_aggregation():
    """TC-430b (DEF-206 gap 2): min-across-segments aggregation is exercised.

    TC-430 and TC-431 both use hf_stability_segment_count=1, so the per-segment
    minimum aggregation in §11.5.1 (min(segment_margins) over N segments) was
    never tested. This fixture uses segment_count=2 with intentionally mismatched
    per-segment floors, making the correct min clearly distinguishable from a
    first-segment-only or maximum implementation:

      Segment 1 (first 2s): floor_below_db = 20 dB
        rightward_margin ≈ 20 − 8 = 12 dB, leftward_margin ≈ 8.0 (brickwall)
        segment_margin_1 = min(12, 8) = 8.0 dB

      Segment 2 (second 2s): floor_below_db = 10 dB
        rightward_margin ≈ 10 − 8 = 2.0 dB, leftward_margin ≈ 8.0 (brickwall)
        segment_margin_2 = min(2, 8) = 2.0 dB

      min(8.0, 2.0) = 2.0 dB → robustness_db ≈ 2.0

    If the implementation returns first-segment only or maximum, it returns ≈ 8.0 dB
    and fails the < 5.0 upper bound. Per the min-of-N bound (§11.5.1), the correct
    implementation should satisfy 0 < robustness_db <= single_segment_value.
    """
    cutoff_hz = 16000.0
    passband_sigma = 0.15

    part1 = brickwall_lowpass_noise_with_floor_mono(
        SR, duration_s=2.0, cutoff_hz=cutoff_hz, floor_below_db=20.0,
        seed=3, passband_sigma=passband_sigma,
    )
    part2 = brickwall_lowpass_noise_with_floor_mono(
        SR, duration_s=2.0, cutoff_hz=cutoff_hz, floor_below_db=10.0,
        seed=4, passband_sigma=passband_sigma,
    )
    mono = np.concatenate([part1, part2])
    audio = to_stereo(mono)

    # Single-segment baseline: whole 4s audio as one segment (upper-bound reference).
    single_result = measure_hf_extension(
        audio, SR, ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=1)
    )
    assert single_result.hf_band_limit_hz is not None, (
        "TC-430b single-segment baseline: 4s of brickwall at 16 kHz must detect a cliff."
    )
    assert single_result.hf_band_limit_robustness_db is not None, (
        "TC-430b single-segment baseline: robustness_db must be non-None when cliff detected."
    )

    # Two-segment run: first segment (deep floor) vs second segment (shallow floor).
    multi_result = measure_hf_extension(
        audio, SR, ref_config(hf_min_duration_s=2.0, hf_stability_segment_count=2)
    )
    assert multi_result.hf_band_limit_hz is not None, (
        "TC-430b: 2-segment run must detect the 16 kHz cliff; got None."
    )
    assert multi_result.hf_band_limit_robustness_db is not None, (
        "TC-430b: hf_band_limit_robustness_db must be non-None when cliff detected on "
        "a 2-segment run. None here means min(segment_margins) was not reached — "
        "check whether per_segment_results contributed any non-None margins."
    )
    multi_val = multi_result.hf_band_limit_robustness_db
    assert multi_val > 0.0, (
        f"TC-430b: multi-segment robustness must be positive; got {multi_val:.4f} dB."
    )
    assert multi_val < 5.0, (
        f"TC-430b: 2-segment min is dominated by segment 2's shallow-floor rightward_margin "
        f"≈ 2.0 dB. Got {multi_val:.4f} dB — a value ≥ 5.0 dB indicates the implementation "
        f"is NOT computing min(segment_margins): it is returning segment 1 only (≈ 8.0 dB), "
        f"the maximum (≈ 8.0 dB), or the whole-track margin instead of the per-segment min. "
        f"See architecture.md §11.5.1 `min(segment_margins)`."
    )
    # min-of-N bound: multi-segment robustness should not substantially exceed
    # the single-segment whole-track reference (Welch variance on 2s sub-segments
    # may spread values; allow 1.0 dB of slack above the single-segment estimate).
    single_val = single_result.hf_band_limit_robustness_db
    assert multi_val <= single_val + 1.0, (
        f"TC-430b: 2-segment min ({multi_val:.4f} dB) exceeds the 1-segment reference "
        f"({single_val:.4f} dB) by more than 1.0 dB. min-of-N should be ≤ any single "
        f"draw from the same distribution; this suggests the aggregation is returning "
        f"a maximum or a count-insensitive path. See architecture.md §11.5.1."
    )
