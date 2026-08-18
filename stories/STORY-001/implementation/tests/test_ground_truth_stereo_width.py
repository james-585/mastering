"""STORY-003 ground-truth tests -- stereo width / correlation / mono-sum
(AC9), test-cases.md TC-050 through TC-057.

TC-054 is the DEF-203 derivation-of-record test (stories/STORY-002/
defects.md). DEF-203 was FIXED in STORY-004: the broadband comparator now
uses the channel-mean denominator (not channel-sum), giving a unified
rho=0 floor of -3.0103 dB for both broadband and per-band. Updated from
the prior not-a-defect closure values (-3.0103/-6.0206) to the correct
channel-mean predictions (0.0/-3.0103/-inf).
"""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.analysis.stereo_phase import correlation_coefficient, analyze_stereo_phase
from suno_mastering.analysis.mono_sum import measure_mono_sum
from suno_mastering.analysis.per_band_stereo_width import measure_per_band_stereo_width
from suno_mastering.analysis.loudness import measure_integrated_lufs

from .ref_helpers import (
    pink_noise_mono, inverted_stereo, independent_noise_stereo, ref_config,
)
from .conftest import to_stereo

pytestmark = pytest.mark.ground_truth

SR = 44100


def test_tc050_identical_lr_correlation_one_width_zero():
    """AC9a. For L=R, S_LR = S_LL = S_RR exactly (real, in-phase), so
    width = 1 - |S_LL|/sqrt(S_LL*S_LL) = 0 in every band. The 1e-6 epsilon
    on correlation is required: correlation_coefficient computes num/denom
    from two independently-rounded floating-point sums, which can read
    fractionally over 1.0 on the single MOST correct possible input."""
    mono = pink_noise_mono(SR, 3.0, seed=1)
    left, right = mono, mono
    corr = correlation_coefficient(left, right)
    assert corr == pytest.approx(1.0, abs=1e-6)

    audio = to_stereo(mono)
    result = measure_per_band_stereo_width(audio, SR, ref_config())
    for b in result.bands:
        assert b.width < 0.05, f"band {b.band}: width={b.width}"


def test_tc051_inverted_r_correlation_minus_one_mono_sum_silent():
    """AC9b. mono_sum of L=-R is identically zero, so measure_integrated_lufs
    on it returns exactly -inf (same mechanism as STORY-001's existing
    test_tc017)."""
    mono = pink_noise_mono(SR, 3.0, seed=1)
    audio = inverted_stereo(mono)
    left, right = audio[:, 0], audio[:, 1]
    corr = correlation_coefficient(left, right)
    assert corr == pytest.approx(-1.0, abs=1e-6)

    result = measure_mono_sum(audio, SR, ref_config())
    assert result.mono_sum_level_change_db == float("-inf")
    assert result.mono_sum_excess_cancellation is True


def test_tc051_note_per_band_width_is_phase_blind_by_design():
    """Documents (does not regress) that per_band_stereo_width is
    magnitude-based (phase-blind, |Re{S_LR}|) by design -- it reads ~0 for
    BOTH rho=+1 and rho=-1, since both are "fully correlated in magnitude,"
    just opposite sign (architecture.md Section 7.5). Asserting it
    distinguishes TC-050 from this case would assert incorrect behavior."""
    mono = pink_noise_mono(SR, 3.0, seed=1)
    audio = inverted_stereo(mono)
    result = measure_per_band_stereo_width(audio, SR, ref_config())
    for b in result.bands:
        assert b.width < 0.05, f"band {b.band}: width={b.width} (expected ~0, phase-blind design)"


def test_tc052_uncorrelated_noise_correlation_near_zero_width_high():
    """AC9c. Independent, equal-power noise drives S_LR -> 0 in expectation
    as sample count grows, so width = 1 - |S_LR|/sqrt(S_LL*S_RR) -> 1.
    width>=0.8 is a generous, architecture-reasoned starting figure -- run
    once, inspect the actual measured value (recorded in defects.md if it
    needs tightening)."""
    audio = independent_noise_stereo(SR, 5.0, sigma=0.05, seed=3)
    left, right = audio[:, 0], audio[:, 1]
    corr = correlation_coefficient(left, right)
    assert corr == pytest.approx(0.0, abs=0.05)

    result = measure_per_band_stereo_width(audio, SR, ref_config())
    for b in result.bands:
        assert b.width >= 0.8, f"band {b.band}: width={b.width}"


def test_tc053_uncorrelated_stereo_no_false_positive_cancellation():
    """Negative control -- direct DEF-101 false-positive guard, already
    partially shipped as test_tc313; recorded here for AC9 traceability."""
    audio = independent_noise_stereo(SR, 5.0, sigma=0.05, seed=3)
    result = measure_mono_sum(audio, SR, ref_config())
    assert result.mono_sum_level_change_db == pytest.approx(-3.0103, abs=0.5)
    assert result.any_cancellation is False


def test_tc054_def203_monosum_floors_derived_from_first_principles():
    """AC9d, the DEF-203 derivation-of-record test (FIXED, not not-a-defect).

    DEF-203 (STORY-004) changed the broadband comparator from BS.1770's
    channel-SUMMED denominator to the CHANNEL-MEAN denominator, making
    broadband and per-band consistent. Let L, R be zero-mean, equal-power
    (Var(L)=Var(R)=sigma^2) channels with correlation rho.
    mono_sum=(L+R)/2, so Var(mono_sum)=sigma^2*(1+rho)/2.

    Both broadband mono_sum_level_change_db AND per-band delta_db now use
    the CHANNEL-MEAN denominator (P_mean=(P_L+P_R)/2=sigma^2):
      mono_sum_level_change_db = LUFS(mono_sum) - channel_mean_lufs(L, R)
                                = 10*log10((1+rho)/2)
      delta_db = 10*log10((1+rho)/2)  (per-band, unchanged from before)

    Unified table (single formula, same rho=0 floor for both):
      rho=+1: mono_sum_level_change_db=0.0 dB; delta_db=0.0 dB
      rho=0:  mono_sum_level_change_db=-3.0103 dB; delta_db=-3.0103 dB
      rho=-1: both -> -inf

    Tolerance basis: broadband +/-0.1 dB (~0.01-0.02 dB expected
    finite-sample noise, O(1/sqrt(N)) in rho). Per-band +/-1.0 dB (Welch/
    CSD band-power estimates have materially more variance; matches DEF-101's
    own observed -0.26..+0.32 dB per-band spread on an 8s fixture)."""
    config = ref_config()

    # rho = +1: identical L=R; mono_sum=L, channel_mean=LUFS(L), change=0 dB
    audio_p1 = to_stereo(pink_noise_mono(SR, 5.0, seed=1))
    result_p1 = measure_mono_sum(audio_p1, SR, config)
    assert result_p1.mono_sum_level_change_db == pytest.approx(0.0, abs=0.1)
    for b in result_p1.band_cancellations:
        assert b.delta_db == pytest.approx(0.0, abs=1.0), f"band {b.band}: delta_db={b.delta_db}"

    # rho = 0: independent equal-power noise; channel-mean floor = -3.0103 dB
    audio_p0 = independent_noise_stereo(SR, 8.0, sigma=0.05, seed=1)
    result_p0 = measure_mono_sum(audio_p0, SR, config)
    assert result_p0.mono_sum_level_change_db == pytest.approx(-3.0103, abs=0.1)
    for b in result_p0.band_cancellations:
        assert b.delta_db == pytest.approx(-3.0103, abs=1.0), f"band {b.band}: delta_db={b.delta_db}"

    # rho = -1: inverted; mono_sum=0, LUFS=-inf
    audio_pm1 = inverted_stereo(pink_noise_mono(SR, 5.0, seed=1))
    result_pm1 = measure_mono_sum(audio_pm1, SR, config)
    assert result_pm1.mono_sum_level_change_db == float("-inf")


def test_tc055_both_silent_correlation_reads_one_by_design():
    """Documented degenerate case: correlation_coefficient returns exactly
    1.0 when both channels are silent/null (by design -- "treat as
    compatible, not undefined"), not NaN or an error."""
    n = int(2.0 * SR)
    left = np.zeros(n)
    right = np.zeros(n)
    corr = correlation_coefficient(left, right)
    assert corr == pytest.approx(1.0)


def test_tc056_analyze_stereo_phase_public_api_matches_helper():
    """AC9a/AC9b extended to the public analyze_stereo_phase entry point,
    not just the internal correlation_coefficient helper -- closes the gap
    that architecture.md Section 7.5 ground-truths only the internal
    helper."""
    config = ref_config()

    mono = pink_noise_mono(SR, 3.0, seed=1)
    audio_identical = to_stereo(mono)
    result_identical = analyze_stereo_phase(audio_identical, SR, config)
    assert result_identical.overall_correlation == pytest.approx(1.0, abs=1e-6)
    assert result_identical.mono_compatible is True

    audio_inverted = inverted_stereo(mono)
    result_inverted = analyze_stereo_phase(audio_inverted, SR, config)
    assert result_inverted.overall_correlation == pytest.approx(-1.0, abs=1e-6)
    assert result_inverted.mono_compatible is False


def test_tc057_mono_sum_both_silent_degenerate_case_does_not_crash():
    """Requirements.md's degenerate-case section, extended to mono_sum: does
    the both-channels-silent case crash, and what does the double -inf
    broadband subtraction actually produce? Recorded as a finding, not
    assumed."""
    n = int(2.0 * SR)
    audio = np.zeros((n, 2))
    result = measure_mono_sum(audio, SR, ref_config())
    # Not asserted to a specific value beyond "does not raise" -- see this
    # test's own docstring / defects.md for what was actually observed.
    assert result is not None
    print(f"TC-057 finding: mono_sum_level_change_db={result.mono_sum_level_change_db}, "
          f"mono_sum_excess_cancellation={result.mono_sum_excess_cancellation}")
