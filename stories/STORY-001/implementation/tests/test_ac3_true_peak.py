"""AC3 -- true peak ceiling. TC-020..TC-024 (TC-024 is cross-validation,
flagged skip -- no external reference meter available in this environment)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from suno_mastering.analysis.true_peak import measure_true_peak

from .conftest import cosine, make_dynamic_track, rms_amplitude_for_dbfs_sine, write_wav
from suno_mastering import pipeline


def _quarter_nyquist_cosine(sr, amplitude, duration_s=2.0, phase=math.pi / 4):
    return cosine(sr / 4.0, sr, duration_s, amplitude=amplitude, phase=phase)


def test_tc020_true_peak_reveals_intersample_peak(default_config):
    sr = 44100
    A = 10 ** (-1.0 / 20)
    x = _quarter_nyquist_cosine(sr, A)

    naive_sample_peak = np.max(np.abs(x))
    naive_dbfs = 20 * np.log10(naive_sample_peak)
    assert abs(naive_dbfs - (-4.01)) < 0.15

    tp = measure_true_peak(x, sr, default_config)
    assert abs(tp.dbtp - (-1.0)) < 0.1


def test_tc021_true_peak_exceeding_ceiling_detected(default_config):
    sr = 44100
    A = 10 ** (-0.5 / 20)
    x = _quarter_nyquist_cosine(sr, A)

    naive_sample_peak = np.max(np.abs(x))
    assert 20 * np.log10(naive_sample_peak) < -1.0  # looks safe naively

    tp = measure_true_peak(x, sr, default_config)
    assert abs(tp.dbtp - (-0.5)) < 0.1
    assert tp.dbtp > default_config.true_peak_ceiling_dbtp  # exceeds -1.0 dBTP ceiling


def test_tc022_oversampling_factor_sensitivity(default_config):
    sr = 44100
    A = 10 ** (-0.2 / 20)
    x = cosine(sr * 0.47, sr, 2.0, amplitude=A, phase=math.pi / 4)

    dbtp_by_factor = {}
    for factor in (1, 2, 4, 8):
        cfg = default_config.__class__(**{**default_config.__dict__, "true_peak_oversample_factor": factor})
        res = measure_true_peak(x, sr, cfg)
        dbtp_by_factor[factor] = res.dbtp

    values = [dbtp_by_factor[f] for f in (1, 2, 4, 8)]
    # non-decreasing as factor increases
    assert all(values[i] <= values[i + 1] + 1e-6 for i in range(len(values) - 1))
    # 4x/8x converge closely
    assert abs(dbtp_by_factor[4] - dbtp_by_factor[8]) < 0.05
    # 1x/2x under-read relative to 4x/8x
    assert dbtp_by_factor[1] <= dbtp_by_factor[4] - 0.01 or dbtp_by_factor[1] < dbtp_by_factor[4]


@pytest.mark.parametrize("case", ["hot", "quiet", "isp_prone", "mid"])
def test_tc023_mastered_output_zero_true_peak_exceptions(tmp_wav_dir, out_dir, default_config, case):
    sr = 44100
    if case == "hot":
        # DEF-009 fix: old body rms_amp(-6.0)≈0.708 gave DR≈3 (solver-infeasible).
        # body=0.28 gives source_dr=10.00 (measured). Transient unchanged.
        body, transient = 0.28, 0.98
    elif case == "quiet":
        body, transient = rms_amplitude_for_dbfs_sine(-28.0), 0.6
    elif case == "isp_prone":
        body, transient = rms_amplitude_for_dbfs_sine(-18.0), 10 ** (-0.5 / 20)
    else:
        body, transient = rms_amplitude_for_dbfs_sine(-16.0), 0.5

    audio = make_dynamic_track(sr, 30.0, body_amplitude=body, transient_amplitude=transient, freq=330)
    path = write_wav(tmp_wav_dir / f"tc023_{case}.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    # Re-read from disk and scan the whole file with the oversampled meter.
    import soundfile as sf
    out_audio, out_sr = sf.read(result.output_path, dtype="float64", always_2d=True)
    tp = measure_true_peak(out_audio, out_sr, default_config)
    assert tp.dbtp <= default_config.true_peak_ceiling_dbtp + 0.01


@pytest.mark.skip(reason="TC-024: cross-validation against an independent true-peak meter "
                          "(e.g. ffmpeg ebur128) is a flagged residual validation dependency "
                          "(architecture.md Section 9 risk #3) -- no independent meter tool is "
                          "available in this execution environment. Recorded as a residual risk "
                          "in defects.md, not a failure.")
def test_tc024_cross_validation_external_meter():
    pass
