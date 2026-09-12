"""STORY-003 ground-truth tests -- true peak (AC5) and clipping (AC1's
detect_clipping coverage), test-cases.md TC-010 through TC-019.
"""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.analysis.true_peak import measure_true_peak
from suno_mastering.analysis.clipping import detect_clipping
from suno_mastering.config import MasteringConfig

from .conftest import nyquist_adjacent_sine, sine, to_stereo, default_config  # noqa: F401

pytestmark = pytest.mark.ground_truth

SR = 44100


def _sample_peak_dbfs(audio: np.ndarray) -> float:
    return 20.0 * np.log10(max(float(np.max(np.abs(audio))), 1e-12))


def test_tc010_nyquist_adjacent_sine_exact_intersample_overshoot_margin():
    """AC5a. At exactly sr/4 Hz with a 45-degree phase offset, every discrete
    sample lands at +/-1/sqrt(2) (sample peak exactly -3.0103 dBFS), while
    the continuous-time signal's true peak of 1.0 (0 dBTP exactly) occurs at
    instants exactly halfway between consecutive samples -- the classic,
    EXACT (not approximate) inter-sample-overshoot construction, giving an
    analytically known 3.0103 dB margin."""
    fixture = nyquist_adjacent_sine(SR, duration_s=2.0, amplitude=1.0)
    audio = to_stereo(fixture)
    config = MasteringConfig()

    sample_peak_dbfs = _sample_peak_dbfs(audio)
    assert sample_peak_dbfs == pytest.approx(-3.0103, abs=0.01)

    result = measure_true_peak(audio, SR, config)
    assert result.dbtp == pytest.approx(0.0, abs=0.05)
    assert result.dbtp - sample_peak_dbfs >= 2.9


def test_tc011_true_peak_and_sample_peak_return_different_values():
    """AC5b, direct regression guard: an assertion that dbtp == sample peak
    on this fixture MUST fail (i.e. true peak is not degenerating to sample
    peak)."""
    fixture = nyquist_adjacent_sine(SR, duration_s=2.0, amplitude=1.0)
    audio = to_stereo(fixture)
    config = MasteringConfig()
    sample_peak_dbfs = _sample_peak_dbfs(audio)
    result = measure_true_peak(audio, SR, config)
    assert result.dbtp != pytest.approx(sample_peak_dbfs, abs=0.5)


def test_tc012_negative_control_low_frequency_sine_no_overshoot():
    """A low-frequency (100 Hz) sine is smooth relative to the sample
    interval -- its peak is already well-represented by sampled points, so
    no genuine inter-sample overshoot exists. Proves TC-010's positive
    result is measuring a real effect, not a fixed bias."""
    fixture = sine(100, SR, 2.5, amplitude=0.5)
    audio = to_stereo(fixture)
    config = MasteringConfig()
    sample_peak_dbfs = _sample_peak_dbfs(audio)
    result = measure_true_peak(audio, SR, config)
    assert abs(result.dbtp - sample_peak_dbfs) < 0.1


def test_tc013_intersample_over_nonzero_with_zero_sample_clipping():
    """True-peak-vs-clipping separation: amplitude 1.05 at the exact sr/4
    inter-sample-overshoot construction pushes the CONTINUOUS peak to 1.05
    (above full scale) while every SAMPLED value stays at
    1.05/sqrt(2)~=0.742 (comfortably under clip_sample_threshold=0.999)."""
    fixture = nyquist_adjacent_sine(SR, duration_s=2.0, amplitude=1.05)
    audio = to_stereo(fixture)
    config = MasteringConfig()
    result = detect_clipping(audio, SR, config)
    assert result.sample_peak_clipped_count == 0
    assert result.inter_sample_over_count > 0
    assert result.inter_sample_peak_dbtp == pytest.approx(20 * np.log10(1.05), abs=0.1)
    assert result.severity == "minor"


def test_tc014_dc_offset_shifts_sample_peak_by_exact_offset():
    """Pure arithmetic: max(sine + dc) = amplitude + dc = 0.3 + 0.5 = 0.8 by
    construction -- no measurement uncertainty involved."""
    fixture = sine(100, SR, 2.5, amplitude=0.3) + 0.5
    peak_dbfs = _sample_peak_dbfs(fixture)
    assert peak_dbfs == pytest.approx(20 * np.log10(0.8), abs=0.01)


# --- Clipping (detect_clipping), AC1 coverage ------------------------------

def test_tc016_exact_clipped_sample_count_from_contiguous_run():
    """clip_sample_threshold=0.999; the background -20 dBFS sine (amplitude
    ~=0.1) never approaches this threshold, so every one of 50 forced
    full-scale samples -- and only those 50 -- is counted, and since they
    are contiguous, exactly 1 clip event is reported."""
    from .conftest import dbfs_to_amplitude

    n = int(3.0 * SR)
    mono = sine(1000, SR, 3.0, amplitude=dbfs_to_amplitude(-20.0) * (2 ** 0.5))
    mono[1000:1050] = 1.0
    audio = to_stereo(mono)
    config = MasteringConfig()
    result = detect_clipping(audio, SR, config)
    assert result.sample_peak_clipped_count == 50
    assert result.sample_peak_clip_events == 1


def test_tc017_clip_event_grouping_distinguishes_run_from_isolated_spikes():
    """Same 50-sample total, but at 50 widely-spaced, non-adjacent indices:
    count logic is unaffected by arrangement (still 50), but each isolated
    sample is its own contiguous run of length 1 -> 50 events."""
    from .conftest import dbfs_to_amplitude

    mono = sine(1000, SR, 3.0, amplitude=dbfs_to_amplitude(-20.0) * (2 ** 0.5))
    for i in range(50):
        mono[i * 500] = 1.0
    audio = to_stereo(mono)
    config = MasteringConfig()
    result = detect_clipping(audio, SR, config)
    assert result.sample_peak_clipped_count == 50
    assert result.sample_peak_clip_events == 50


def test_tc018_negative_control_clean_signal_zero_clips_severity_none():
    from .conftest import dbfs_to_amplitude

    mono = sine(1000, SR, 3.0, amplitude=dbfs_to_amplitude(-20.0) * (2 ** 0.5))
    audio = to_stereo(mono)
    config = MasteringConfig()
    result = detect_clipping(audio, SR, config)
    assert result.sample_peak_clipped_count == 0
    assert result.sample_peak_clip_events == 0
    assert result.inter_sample_over_count == 0
    assert result.severity == "none"


def test_tc019_stereo_linking_clip_on_either_channel_counts():
    """detect_clipping's own linking logic takes max(|L|,|R|) per sample
    before thresholding -- a right-channel-only clip is still counted, not
    silently missed because the left channel is clean."""
    from .conftest import dbfs_to_amplitude

    base = sine(1000, SR, 3.0, amplitude=dbfs_to_amplitude(-20.0) * (2 ** 0.5))
    left = base.copy()
    right = base.copy()
    right[2000:2020] = 1.0
    audio = np.stack([left, right], axis=1)
    config = MasteringConfig()
    result = detect_clipping(audio, SR, config)
    assert result.sample_peak_clipped_count == 20
