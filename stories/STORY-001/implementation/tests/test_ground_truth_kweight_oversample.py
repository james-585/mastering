"""STORY-003 ground-truth tests -- k_weight / oversample internal-machinery
coverage (requirements.md's recommended additional coverage, confirmed
in-scope by architecture.md Section 9 item 3), test-cases.md TC-070-072.
"""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.analysis.true_peak import oversample
from suno_mastering.analysis.loudness_range import k_weight

from .conftest import nyquist_adjacent_sine, sine

pytestmark = pytest.mark.ground_truth

SR = 44100


def test_tc070_oversample_recovers_known_intersample_peak():
    """Same sr/4 construction as TC-010 guarantees a continuous-time peak of
    exactly 1.0 at inter-sample points; this ground-truths the
    interpolation filter in isolation from the peak-search/guard-region
    logic layered on top of it in measure_true_peak."""
    fixture = nyquist_adjacent_sine(SR, 2.0, amplitude=1.0)
    oversampled = oversample(fixture, SR, factor=8)
    assert abs(float(np.max(np.abs(oversampled))) - 1.0) < 0.05


def test_tc071_k_weight_matches_bs1770_anchor_points():
    """10kHz (well above the shelf's ~1.7kHz center, on its plateau): ~+4dB
    (BS.1770-4 Annex 1's own published high-shelf gain, g_db~=3.9998 in the
    shipped coefficients).

    1kHz: CORRECTION to test-cases.md TC-071's own stated expected value
    (flagged as a test-cases.md defect, not applied here): TC-071 states
    "1kHz: ~=0dB (+/-0.5dB)" for the K-WEIGHTING FILTER ALONE. Measured
    directly (this QA pass): k_weight's own gain at 1kHz is ~+0.70dB, not
    ~0dB -- confirmed independently by test_ground_truth_loudness.py's
    TC-004 finding (the measured integrated-LUFS net offset at 1kHz is
    ~-0.0354dB, i.e. the -0.691dB BS.1770 fixed offset is nearly, but not
    exactly, cancelled by a K-weighting gain of ~+0.6556dB at 1kHz -- both
    measurements agree to within ~0.05dB, self-consistent). "1kHz is
    calibration-neutral" is a true statement about the COMBINED system
    (K-weighting gain + the -0.691dB fixed offset), not about the
    K-weighting filter's own gain in isolation -- test-cases.md's TC-071
    conflates the two, the same class of error as TC-003/004's own -0.691dB
    confusion (see test_ground_truth_loudness.py)."""
    for freq, expected_db, tol in [(1000.0, 0.70, 0.3), (10000.0, 4.0, 1.0)]:
        tone = sine(freq, SR, 2.5, amplitude=0.3)
        weighted = k_weight(tone, SR)
        input_rms = float(np.sqrt(np.mean(tone ** 2)))
        output_rms = float(np.sqrt(np.mean(weighted ** 2)))
        gain_db = 20.0 * np.log10(output_rms / input_rms)
        assert abs(gain_db - expected_db) < tol, f"freq={freq}: gain_db={gain_db}"


def test_tc072_k_weight_low_frequency_attenuation_sanity_floor_only():
    """Sanity-floor-only assertion (NOT a full ground-truth test -- the
    precise literature-sourced attenuation figure at 20Hz is not sourced by
    this document, per test-cases.md's own flagged open question 3):
    attenuation is strictly negative (the filter attenuates, not amplifies,
    at 20Hz) and larger in magnitude than at a frequency closer to the
    corner -- distinguishes a correctly-implemented high-pass from a
    null/no-op filter without needing the precise published figure."""
    def gain_db(freq):
        tone = sine(freq, SR, 2.5, amplitude=0.3)
        weighted = k_weight(tone, SR)
        input_rms = float(np.sqrt(np.mean(tone ** 2)))
        output_rms = float(np.sqrt(np.mean(weighted ** 2)))
        return 20.0 * np.log10(output_rms / input_rms)

    gain_20hz = gain_db(20.0)
    gain_60hz = gain_db(60.0)  # closer to the ~38Hz corner
    assert gain_20hz < 0.0
    assert gain_20hz < gain_60hz  # more negative further from the corner
