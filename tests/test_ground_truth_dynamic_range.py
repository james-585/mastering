"""STORY-003 ground-truth tests -- dynamic range / LRA (AC7), test-cases.md
TC-030 through TC-036.

Fixture-length floors (architecture.md Section 1.3, a deliberate, derived
deviation from story.md's "2-5s" NFR for these two functions specifically):
measure_dynamic_range needs n_blocks>=5 to exercise its sort/exclude/2nd-
peak logic (n_blocks==5 exactly at dr_block_seconds*5=15s); LRA's two-level
case reuses DEF-107's own calibrated 18 LU / 30s+30s fixture pattern
(STORY-002's test_tc302), not an invented shorter separation.
"""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.analysis.dynamic_range import (
    measure_dynamic_range, _measure_dynamic_range_unrounded,
)
from suno_mastering.analysis.loudness_range import measure_loudness_range
from suno_mastering.config import MasteringConfig

from .conftest import sine, to_stereo
from .ref_helpers import calibrated_tone_mono, ref_config

pytestmark = pytest.mark.ground_truth

SR = 44100


def test_tc030_constant_level_sine_dr_near_zero():
    """AC7a (DR). The module's own "RMS" definition rescales by sqrt(2)
    specifically to make an ideal sine's peak-to-"RMS" ratio equal 1
    (sqrt(2)*RMS_sine = sqrt(2)*(A/sqrt(2)) = A = peak). For a
    constant-amplitude sine, every 3s block has (to within negligible
    finite-block-boundary phase effects) the same rescaled-RMS and the same
    peak, so DR = 20*log10(peak/rms) ~= 0."""
    mono = sine(1000, SR, 16.0, amplitude=10 ** (-12.0 / 20.0))  # -12 dBFS peak, >=15s -> n_blocks==5
    audio = to_stereo(mono)
    config = MasteringConfig()
    rounded = measure_dynamic_range(audio, SR, config)
    unrounded = _measure_dynamic_range_unrounded(audio, SR, config)
    assert rounded == 0
    assert abs(unrounded - 0.0) < 0.1


def test_tc031_very_short_file_falls_back_to_crest_factor_same_answer():
    """Boundary: 1s duration -> n_blocks=0 at dr_block_seconds=3.0, triggers
    the n_blocks<1 single-block crest-factor fallback. Same numeric answer
    as TC-030 (peak == rescaled-RMS for an ideal sine), reached via a
    different code branch -- confirms the fallback branch is itself
    correct, not merely that the two branches happen to agree here."""
    mono = sine(1000, SR, 1.0, amplitude=10 ** (-12.0 / 20.0))
    audio = to_stereo(mono)
    config = MasteringConfig()
    rounded = measure_dynamic_range(audio, SR, config)
    unrounded = _measure_dynamic_range_unrounded(audio, SR, config)
    assert rounded == 0
    assert abs(unrounded - 0.0) < 0.1


def test_tc032_constant_level_sine_lra_near_zero():
    """AC7a (LRA). K-weighted per-window mean-square power for a
    constant-amplitude sine is essentially identical across every full 3s
    window, so the doubly-gated P95-P10 spread should be near-zero."""
    mono = sine(1000, SR, 6.0, amplitude=10 ** (-12.0 / 20.0))
    audio = to_stereo(mono)
    result = measure_loudness_range(audio, SR, ref_config())
    assert abs(result.lra_lu - 0.0) < 0.2


def test_tc033_two_level_18lu_separation_lra_approximates_it():
    """AC7b. Reuses the DEF-107-calibrated 18 LU two-level fixture
    (STORY-002 test_tc302's own construction) -- per DEF-107 the relative
    gate compares against the mean of all passing blocks, not directly
    against either cluster's own level; 18 LU sits between the correct-gate
    exclusion boundary (~23.01 LU) and the incorrect -10 LU-gate exclusion
    boundary (~13.01 LU), so it discriminates a correct implementation from
    a miscopied one (see TC-034)."""
    a = calibrated_tone_mono(SR, 30.0, dbfs_rms=-10.0)
    b = calibrated_tone_mono(SR, 30.0, dbfs_rms=-28.0)  # 18 LU separation
    audio = to_stereo(np.concatenate([a, b]))
    config = ref_config()
    result = measure_loudness_range(audio, SR, config)
    assert result.lra_lu == pytest.approx(18.0, abs=config.lra_tolerance_lu)


def test_tc034_forced_incorrect_gate_collapses_lra():
    """AC7b's discrimination purpose, regression guard: under an incorrectly
    narrower -10 LU relative gate, the quiet cluster (18 dB below the loud
    cluster) is excluded entirely, leaving only the loud cluster's own
    internal (near-zero) spread."""
    a = calibrated_tone_mono(SR, 30.0, dbfs_rms=-10.0)
    b = calibrated_tone_mono(SR, 30.0, dbfs_rms=-28.0)
    audio = to_stereo(np.concatenate([a, b]))
    wrong_config = ref_config(lra_relative_gate_lu=-10.0)
    result = measure_loudness_range(audio, SR, wrong_config)
    assert result.lra_lu < 5.0


def test_tc035_lra_differs_from_naive_peak_to_trough():
    """AC7c. A transient far shorter than one LRA analysis window (3s)
    contributes negligible additional power to that window's mean-square,
    so it cannot meaningfully move the K-weighted, doubly-gated,
    percentile-based LRA statistic -- this is the entire point of using a
    windowed/gated/percentile statistic instead of raw peak-to-trough."""
    sr = SR
    base = sine(1000, sr, 30.0, amplitude=10 ** (-20.0 / 20.0))  # constant -20 dBFS-peak tone
    audio_mono = base.copy()
    glitch_start = int(15.0 * sr)
    glitch_len = int(0.005 * sr)
    audio_mono[glitch_start:glitch_start + glitch_len] = 1.0  # 5ms full-scale glitch

    lra = measure_loudness_range(to_stereo(audio_mono), sr, ref_config())
    naive_peak_to_trough_db = 0.0 - (-20.0)  # peak 0 dBFS vs. background -20 dBFS

    assert lra.lra_lu < 3.0
    assert (naive_peak_to_trough_db - lra.lra_lu) > 10.0


def test_tc036_very_short_file_lra_returns_documented_zero_result():
    """Boundary/edge case: LRA's own documented early-return behavior for
    an empty array and for an array shorter than one 3s LRA window."""
    empty = np.zeros((0, 2))
    result_empty = measure_loudness_range(empty, SR, ref_config())
    assert result_empty.lra_lu == 0.0
    assert result_empty.n_gated_blocks == 0
    assert result_empty.self_consistency_delta_lu == 0.0

    short_mono = sine(1000, SR, 1.0, amplitude=0.1)  # shorter than one 3s window
    result_short = measure_loudness_range(to_stereo(short_mono), SR, ref_config())
    assert result_short.lra_lu == 0.0
    assert result_short.n_gated_blocks == 0
    assert result_short.self_consistency_delta_lu == 0.0
