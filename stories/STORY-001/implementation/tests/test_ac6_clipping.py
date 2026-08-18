"""AC6 -- clipping/distortion detection and non-regression. TC-050..TC-054."""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering import pipeline
from suno_mastering.analysis.clipping import detect_clipping
from suno_mastering.analysis.true_peak import measure_true_peak

from .conftest import make_dynamic_track, rms_amplitude_for_dbfs_sine, write_wav


def test_tc050_full_scale_square_wave_all_clipped(default_config):
    sr = 44100
    n = sr  # 1 second
    square = np.ones(n)
    square[1::2] = -1.0
    audio = np.stack([square, square], axis=1)

    result = detect_clipping(audio, sr, default_config)
    assert result.sample_peak_clipped_count == n
    assert result.severity in ("moderate", "severe")


def test_tc051_already_clipped_source_detected_no_error(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 30.0, body_amplitude=0.1, transient_amplitude=0.4, freq=220)
    clip_start = int(10 * sr)
    clip_len = int(2 * sr)
    audio[clip_start:clip_start + clip_len, :] = 1.0

    before = detect_clipping(audio, sr, default_config)
    assert before.sample_peak_clipped_count >= clip_len

    path = write_wav(tmp_wav_dir / "tc051.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)
    assert result.before.clipping.sample_peak_clipped_count >= clip_len
    assert result.before.clipping.severity != "none"


def test_tc052_mastering_never_amplifies_existing_clipping(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 30.0, body_amplitude=0.1, transient_amplitude=0.4, freq=220)
    clip_start = int(10 * sr)
    clip_len = int(2 * sr)
    audio[clip_start:clip_start + clip_len, :] = 1.0

    path = write_wav(tmp_wav_dir / "tc052.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.after.true_peak_dbtp <= default_config.true_peak_ceiling_dbtp + 0.01


def test_tc053_no_new_clipping_on_near_ceiling_quiet_source(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    body = rms_amplitude_for_dbfs_sine(-25.0)
    transient = 10 ** (-0.8 / 20)  # just under -1dBFS
    audio = make_dynamic_track(sr, 30.0, body_amplitude=body, transient_amplitude=transient, freq=220)

    path = write_wav(tmp_wav_dir / "tc053.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.after.true_peak_dbtp <= default_config.true_peak_ceiling_dbtp + 0.01


def test_tc054_near_silent_no_false_positive_clipping(default_config):
    sr = 44100
    n = int(30 * sr)
    rng = np.random.default_rng(1234)
    noise_amp = rms_amplitude_for_dbfs_sine(-90.0) / np.sqrt(2)  # approx -90dBFS RMS noise
    audio = rng.normal(0, noise_amp, size=(n, 2))

    result = detect_clipping(audio, sr, default_config)
    assert result.sample_peak_clipped_count == 0
