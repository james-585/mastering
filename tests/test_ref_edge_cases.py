"""STORY-002 edge case inputs. TC-350-TC-356."""
from __future__ import annotations

import math

import numpy as np
import pytest

from suno_mastering.analysis.loudness_range import measure_loudness_range
from suno_mastering.reference_analysis import pipeline as ref_pipeline

from .ref_helpers import (
    to_stereo, sine, pink_noise_stereo, pink_noise_mono, write_wav, write_flac, ref_config,
)


def test_tc350_near_silence_lra_defined_behavior_not_crash():
    sr = 44100
    rng = np.random.default_rng(0)
    n = int(60 * sr)
    mono = rng.normal(0.0, 10 ** (-85.0 / 20.0), n)  # -85dBFS-ish, below -70 LUFS absolute gate
    audio = to_stereo(mono)
    result = measure_loudness_range(audio, sr, ref_config())
    assert math.isfinite(result.lra_lu)  # no NaN/inf propagating out
    assert result.lra_lu >= 0.0


def test_tc351_full_scale_clipping_input_all_fields_populate(tmp_path):
    sr = 44100
    n = int(60 * sr)
    t = np.arange(n) / sr
    mono = np.clip(1.3 * np.sin(2 * np.pi * 100 * t), -1.0, 1.0)
    audio = to_stereo(mono)
    p = write_wav(tmp_path / "clip.wav", audio, sr)
    m = ref_pipeline.analyze_track(p, ref_config(hf_min_duration_s=30.0))
    assert math.isfinite(m.core.integrated_lufs)
    assert math.isfinite(m.core.true_peak_dbtp)
    assert m.core.true_peak_dbtp >= -0.5  # clipped signal reads at/above ~0 dBTP
    assert m.dynamic_range_db_exact is not None


def test_tc352_very_quiet_input_no_division_blowup(tmp_path):
    sr = 44100
    audio = pink_noise_stereo(sr, 60.0, amplitude=10 ** (-45.0 / 20.0))
    p = write_wav(tmp_path / "quiet.wav", audio, sr)
    m = ref_pipeline.analyze_track(p, ref_config())
    assert math.isfinite(m.core.integrated_lufs)
    for b in m.seven_band.bands:
        assert math.isfinite(b.relative_db)
    for b in m.per_band_stereo_width.bands:
        assert 0.0 <= b.width <= 1.0
    assert math.isfinite(m.mono_sum.mono_sum_level_change_db)


def test_tc353_dc_offset_present_no_crash(tmp_path):
    sr = 44100
    audio = pink_noise_stereo(sr, 60.0, amplitude=0.1) + 0.02
    p = write_wav(tmp_path / "dc.wav", audio, sr)
    m = ref_pipeline.analyze_track(p, ref_config())
    for b in m.seven_band.bands:
        assert math.isfinite(b.relative_db)
    assert m.hf_extension is not None


def test_tc354_very_short_file_below_lra_window(tmp_path):
    sr = 44100
    audio = pink_noise_stereo(sr, 2.0, amplitude=0.1)
    p = write_wav(tmp_path / "short.wav", audio, sr)
    m = ref_pipeline.analyze_track(p, ref_config())
    assert m.lra.n_gated_blocks == 0
    assert m.lra.lra_lu == 0.0
    assert math.isfinite(m.core.integrated_lufs)  # other AC1 fields still populate


def test_tc355_short_file_above_lra_window_below_hf_minimum(tmp_path):
    sr = 44100
    audio = pink_noise_stereo(sr, 15.0, amplitude=0.1)
    p = write_wav(tmp_path / "midshort.wav", audio, sr)
    m = ref_pipeline.analyze_track(p, ref_config())  # default hf_min_duration_s=30
    assert m.lra.n_gated_blocks > 0  # LRA populates (15s > 3s window)
    assert m.hf_extension.insufficient_duration is True  # HF does not (15s < 30s)


def test_tc356_mono_flac_reference_track(tmp_path):
    sr = 44100
    audio = pink_noise_mono(sr, 60.0, amplitude=0.15)
    p = write_flac(tmp_path / "mono.flac", audio, sr)
    m = ref_pipeline.analyze_track(p, ref_config())
    assert m.core.is_mono
    assert m.per_band_stereo_width is None
    assert m.mono_sum is None
    assert math.isfinite(m.core.integrated_lufs)
    assert m.provenance.container == "flac"
