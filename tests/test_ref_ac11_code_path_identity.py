"""STORY-002 AC11 -- code-path identity with STORY-001. TC-330-TC-333.

Per architecture.md Section 8/Section 12: "the single most important test
in this story's suite." Verifies STORY-001's ingest.py -> analysis.measure_all()
path and STORY-002's reference_ingest.py -> analysis.measure_all() path
produce field-for-field identical Measurements for the same underlying
audio, both stereo and mono (the mono `always_2d`-then-squeeze convention
trap architecture.md Section 6 calls out explicitly)."""
from __future__ import annotations

import math

import pytest

from suno_mastering.io import ingest as story001_ingest
from suno_mastering.io import reference_ingest
from suno_mastering import analysis
from suno_mastering.analysis.dynamic_range import (
    measure_dynamic_range, _measure_dynamic_range_unrounded,
)
from suno_mastering.config import MasteringConfig

from .ref_helpers import pink_noise_stereo, pink_noise_mono, write_wav, ref_config


def test_tc330_stereo_wav_measurements_equal_across_both_ingest_paths(tmp_path):
    audio = pink_noise_stereo(44100, 20.0, amplitude=0.2)
    p = write_wav(tmp_path / "t.wav", audio, 44100)

    story001_result = story001_ingest.ingest(p, MasteringConfig())
    m1 = analysis.measure_all(story001_result.audio, story001_result.sample_rate, MasteringConfig())

    ref_result = reference_ingest.ingest_reference_track(p, ref_config())
    m2 = analysis.measure_all(ref_result.audio, ref_result.sample_rate, ref_config().mastering)

    assert m1.integrated_lufs == pytest.approx(m2.integrated_lufs, rel=1e-9, abs=1e-9)
    assert m1.true_peak_dbtp == pytest.approx(m2.true_peak_dbtp, rel=1e-9, abs=1e-9)
    assert m1.dynamic_range_db == m2.dynamic_range_db
    assert m1.frequency_balance.low_end.relative_db == pytest.approx(m2.frequency_balance.low_end.relative_db, rel=1e-9, abs=1e-9)
    assert m1.frequency_balance.low_mid_mud.relative_db == pytest.approx(m2.frequency_balance.low_mid_mud.relative_db, rel=1e-9, abs=1e-9)
    assert m1.frequency_balance.presence_harsh.relative_db == pytest.approx(m2.frequency_balance.presence_harsh.relative_db, rel=1e-9, abs=1e-9)
    assert m1.stereo_phase.overall_correlation == pytest.approx(m2.stereo_phase.overall_correlation, rel=1e-9, abs=1e-9)
    assert m1.stereo_phase.mono_compatible == m2.stereo_phase.mono_compatible


def test_tc331_mono_wav_measurements_equal_across_both_ingest_paths(tmp_path):
    """Exercises the `always_2d`-then-squeeze convention trap named in
    architecture.md Section 6 as 'the single most likely place to introduce
    an AC11 regression' -- a stereo-only test would not catch a shape
    mismatch that only manifests for mono input."""
    audio = pink_noise_mono(44100, 20.0, amplitude=0.2)
    p = write_wav(tmp_path / "mono.wav", audio, 44100, subtype="PCM_16")

    story001_result = story001_ingest.ingest(p, MasteringConfig())
    m1 = analysis.measure_all(story001_result.audio, story001_result.sample_rate, MasteringConfig())

    ref_result = reference_ingest.ingest_reference_track(p, ref_config())
    m2 = analysis.measure_all(ref_result.audio, ref_result.sample_rate, ref_config().mastering)

    assert story001_result.audio.ndim == 1
    assert ref_result.audio.ndim == 1
    assert m1.is_mono is True and m2.is_mono is True
    assert m1.integrated_lufs == pytest.approx(m2.integrated_lufs, rel=1e-9, abs=1e-9)
    assert m1.true_peak_dbtp == pytest.approx(m2.true_peak_dbtp, rel=1e-9, abs=1e-9)
    assert m1.dynamic_range_db == m2.dynamic_range_db
    assert m1.stereo_phase.overall_correlation == m2.stereo_phase.overall_correlation
    assert m1.stereo_phase.mono_compatible == m2.stereo_phase.mono_compatible


@pytest.mark.parametrize("amplitude,transient", [
    (0.05, 0.4), (0.15, 0.9), (0.3, 0.35),
])
def test_tc332_dr_extract_not_fork_rounded_matches_floor_of_unrounded(amplitude, transient):
    """extract-don't-fork: measure_dynamic_range() == floor(unrounded + 0.5)
    for every fixture, confirming one computation underneath both entry
    points, not a coincidentally-matching reimplementation."""
    import numpy as np
    from .ref_helpers import sine, to_stereo

    sr = 44100
    n = int(20 * sr)
    body = sine(220, sr, 20.0, amplitude=amplitude)
    period = int(1.0 * sr)
    tlen = int(0.005 * sr)
    for start in range(period, n - tlen, period):
        body[start:start + tlen] = transient
    audio = to_stereo(body)

    config = MasteringConfig()
    rounded = measure_dynamic_range(audio, sr, config)
    unrounded = _measure_dynamic_range_unrounded(audio, sr, config)
    assert rounded == math.floor(unrounded + 0.5)


def test_tc333_flac_sourced_equals_wav_sourced_measurement(tmp_path):
    from .ref_helpers import write_flac

    audio = pink_noise_stereo(44100, 15.0, amplitude=0.2)
    wav_path = write_wav(tmp_path / "t.wav", audio, 44100)
    flac_path = write_flac(tmp_path / "t.flac", audio, 44100)

    r_wav = reference_ingest.ingest_reference_track(wav_path, ref_config())
    r_flac = reference_ingest.ingest_reference_track(flac_path, ref_config())
    m_wav = analysis.measure_all(r_wav.audio, r_wav.sample_rate, ref_config().mastering)
    m_flac = analysis.measure_all(r_flac.audio, r_flac.sample_rate, ref_config().mastering)

    # abs=1e-4 (not 1e-9): FLAC's own 24-bit PCM quantization round-trips
    # sample values ~1.2e-7 apart from the WAV PCM_24 writer's own rounding
    # (confirmed directly against the decoded arrays) -- a real, tiny,
    # lossless-quantization-boundary difference, not a code bug, that the
    # true-peak FIR oversampling chain amplifies to ~4e-6 dB. TC-330/331's
    # same-source-file identity tests use the tight 1e-9 tolerance since
    # there both paths decode the exact same file; this test is the only
    # one comparing two independently-quantized encodes of the same audio.
    assert m_wav.integrated_lufs == pytest.approx(m_flac.integrated_lufs, rel=1e-9, abs=1e-4)
    assert m_wav.true_peak_dbtp == pytest.approx(m_flac.true_peak_dbtp, rel=1e-9, abs=1e-4)
    assert m_wav.dynamic_range_db == m_flac.dynamic_range_db
