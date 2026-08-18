"""AC5 -- mono compatibility. TC-040..TC-047."""
from __future__ import annotations

import math

import numpy as np
import pytest

from suno_mastering.analysis.stereo_phase import analyze_stereo_phase, correlation_coefficient
from suno_mastering.mastering.stereo_correct import correct_stereo_widened_elements

from .conftest import sine


def _mid_side_stereo(sr, duration_s, a_mid, a_side, freq_mid=300.0, freq_side=907.0):
    """Build L=M+S, R=M-S from two DIFFERENT, (approximately) orthogonal
    frequencies for M and S. The closed-form rho=(E[M^2]-E[S^2])/(E[M^2]+E[S^2])
    from test-cases.md's construction note only holds when M and S are
    uncorrelated -- if M and S were both scalar multiples of the *same*
    waveform (fully correlated), L and R would always read +-1.0
    correlation regardless of the amplitude ratio, not the intended
    fractional rho. Using two distinct, non-harmonically-related
    frequencies keeps Cov(M,S) ~= 0 over the fixture duration."""
    n = int(round(duration_s * sr))
    t = np.arange(n) / sr
    mid = a_mid * np.sin(2 * np.pi * freq_mid * t)
    side = a_side * np.sin(2 * np.pi * freq_side * t)
    left = mid + side
    right = mid - side
    return np.stack([left, right], axis=1)


def test_tc040_fully_out_of_phase_reads_minus1(default_config):
    sr = 44100
    left = sine(440, sr, 10.0, amplitude=1.0)
    right = -left
    audio = np.stack([left, right], axis=1)
    corr = correlation_coefficient(left, right)
    assert abs(corr - (-1.0)) < 0.01

    result = analyze_stereo_phase(audio, sr, default_config)
    assert abs(result.overall_correlation - (-1.0)) < 0.01
    assert result.mono_compatible is False

    # DEF-006: for a fully out-of-phase pair, mid=(L+R)/2 is exactly zero in
    # every window, so every window's ratio is +inf (mid_energy ~ 0), and
    # `_debounce_regions()`'s `mean_ratio` -- which averages only the
    # np.isfinite() ratios in a widened region -- degenerates to
    # np.mean([]) (a RuntimeWarning "Mean of empty slice" plus NaN), even
    # though `StereoWidenedRegion.mean_ratio` is typed as a plain float.
    # This fixture reliably reproduces it (every widened region here has
    # zero finite ratios); assert the field stays finite so this doesn't
    # silently propagate NaN to any future report/threshold consumer.
    for region in result.widened_regions:
        assert np.isfinite(region.mean_ratio), (
            "StereoWidenedRegion.mean_ratio is NaN -- see defects.md DEF-006 "
            "(np.mean([]) over an all-infinite-ratio widened region)"
        )


def test_tc041_widened_element_at_minus0_3_corrected_to_floor(default_config):
    sr = 44100
    r = math.sqrt((1 - (-0.3)) / (1 + (-0.3)))
    a_mid = 0.3
    a_side = a_mid * r
    audio = _mid_side_stereo(sr, 1.0, a_mid, a_side)  # 1s >= 750ms debounce

    result = analyze_stereo_phase(audio, sr, default_config)
    widened = [w for w in result.windows if w.is_widened]
    assert len(widened) >= 2
    assert len(result.widened_regions) >= 1
    region = result.widened_regions[0]
    assert abs(region.region_correlation - (-0.3)) < 0.05
    assert region.mean_ratio > 0.6
    assert region.needs_correction is True

    corrected_audio, actions = correct_stereo_widened_elements(audio, sr, result.widened_regions, default_config)
    assert len(actions) == 1
    assert actions[0].corrected_correlation >= -0.01  # >= 0.0 floor (small numerical tolerance)
    # minimum correction: side scale factor should be well above 0 (not collapsed to mono)
    assert actions[0].side_scale_factor > 0.3


def test_tc042_widened_within_0_to_0_3_not_force_corrected(default_config):
    sr = 44100
    rho = 0.15
    r = math.sqrt((1 - rho) / (1 + rho))
    a_mid = 0.3
    a_side = a_mid * r
    audio = _mid_side_stereo(sr, 1.0, a_mid, a_side)

    result = analyze_stereo_phase(audio, sr, default_config)
    assert len(result.widened_regions) >= 1
    region = result.widened_regions[0]
    assert region.region_correlation >= 0.0
    assert region.mean_ratio > 0.6  # still classified as widened
    assert region.needs_correction is False  # already >= floor, no mandatory narrowing

    corrected_audio, actions = correct_stereo_widened_elements(audio, sr, result.widened_regions, default_config)
    assert actions == []
    assert np.allclose(corrected_audio, audio)


def test_tc043_single_transient_not_sustained_debounce(default_config):
    sr = 44100
    duration = 3.0
    n = int(duration * sr)
    left = np.zeros(n)
    right = np.zeros(n)
    # narrow/mono-compatible background content
    base = 0.05 * sine(300, sr, duration)
    left += base
    right += base
    # one hard-panned transient spanning ~200ms, single window only
    transient_start = int(1.5 * sr)
    transient_len = int(0.2 * sr)
    left[transient_start:transient_start + transient_len] += 0.5
    right[transient_start:transient_start + transient_len] -= 0.5
    audio = np.stack([left, right], axis=1)

    result = analyze_stereo_phase(audio, sr, default_config)
    flagged_windows = [w for w in result.windows if w.is_widened]
    assert len(flagged_windows) >= 1
    # but not classified as a sustained widened element
    overlapping_regions = [
        r for r in result.widened_regions
        if r.start_time_s < (transient_start + transient_len) / sr and r.end_time_s > transient_start / sr
    ]
    assert overlapping_regions == []


def test_tc044_exactly_two_consecutive_windows_qualifies(default_config):
    sr = 44100
    # 750ms sustained (2 consecutive 500ms windows at 250ms hop, minimum qualifying duration)
    duration = 3.0
    n = int(duration * sr)
    left = 0.05 * sine(300, sr, duration)
    right = left.copy()
    widen_start = int(1.0 * sr)
    widen_len = int(0.75 * sr)
    # inject wide content: strong side energy
    left = left.copy()
    right = right.copy()
    seg_n = widen_len
    t = np.arange(seg_n) / sr
    wide = 0.4 * np.sin(2 * np.pi * 300 * t)
    left[widen_start:widen_start + widen_len] += wide
    right[widen_start:widen_start + widen_len] -= wide
    audio = np.stack([left, right], axis=1)

    result = analyze_stereo_phase(audio, sr, default_config)
    overlapping_regions = [
        r for r in result.widened_regions
        if r.start_time_s < (widen_start + widen_len) / sr and r.end_time_s > widen_start / sr
    ]
    assert len(overlapping_regions) >= 1


def test_tc045_mono_input_skips_stereo_checks(default_config):
    sr = 44100
    mono = sine(440, sr, 5.0, amplitude=0.3)
    result = analyze_stereo_phase(mono, sr, default_config)
    assert result.is_mono is True
    assert result.overall_correlation == 1.0
    assert result.mono_compatible is True
    assert result.widened_regions == []

    # stereo_correct should also not error/attempt correction on mono
    out, actions = correct_stereo_widened_elements(mono, sr, [], default_config)
    assert actions == []


def test_tc046_crossfade_smooth_no_discontinuity(default_config):
    sr = 44100
    r = math.sqrt((1 - (-0.3)) / (1 + (-0.3)))
    a_mid = 0.3
    a_side = a_mid * r
    audio = _mid_side_stereo(sr, 2.0, a_mid, a_side)

    from suno_mastering.analysis.stereo_phase import analyze_stereo_phase as analyze
    result = analyze(audio, sr, default_config)
    corrected, actions = correct_stereo_widened_elements(audio, sr, result.widened_regions, default_config)
    assert len(actions) >= 1

    side_before = (audio[:, 0] - audio[:, 1]) / 2.0
    side_after = (corrected[:, 0] - corrected[:, 1]) / 2.0
    gain_curve = np.divide(side_after, side_before, out=np.ones_like(side_before), where=np.abs(side_before) > 1e-9)

    crossfade_len = max(1, int(round(default_config.stereo_crossfade_ms / 1000.0 * sr)))
    region = result.widened_regions[0]
    start = region.start_sample
    boundary_window = gain_curve[max(0, start - crossfade_len):start + crossfade_len]
    deltas = np.diff(boundary_window)
    max_delta = np.max(np.abs(deltas)) if len(deltas) else 0.0

    # abrupt hard-cut of the same total magnitude would produce a single
    # delta equal to the full gain change in one sample.
    total_gain_change = np.max(boundary_window) - np.min(boundary_window)
    assert max_delta < total_gain_change * 0.5  # materially smoother than a hard cut

    # no clipping introduced
    assert np.max(np.abs(corrected)) <= 1.0 + 1e-9


def test_tc047_adjacent_close_regions_no_crash(default_config):
    sr = 44100
    duration = 3.0
    n = int(duration * sr)
    left = 0.02 * sine(300, sr, duration)
    right = left.copy()

    r = math.sqrt((1 - (-0.3)) / (1 + (-0.3)))
    a_mid, a_side = 0.3, 0.3 * r
    t = np.arange(int(0.8 * sr)) / sr
    base = np.sin(2 * np.pi * 300 * t)
    mid = a_mid * base
    side = a_side * base
    seg_left, seg_right = mid + side, mid - side

    region1_start = int(1.0 * sr)
    region2_start = region1_start + int(0.8 * sr) + int(0.05 * sr)  # < 100ms gap
    for start in (region1_start, region2_start):
        end = min(n, start + len(seg_left))
        length = end - start
        left[start:end] = seg_left[:length]
        right[start:end] = seg_right[:length]

    audio = np.stack([left, right], axis=1)
    result = analyze_stereo_phase(audio, sr, default_config)
    corrected, actions = correct_stereo_widened_elements(audio, sr, result.widened_regions, default_config)

    # no crash; verify each corrected region reaches >= 0.0
    for action in actions:
        assert action.corrected_correlation >= -0.01
    assert np.all(np.isfinite(corrected))
