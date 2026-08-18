"""AC4 -- dynamic range preservation. TC-030..TC-035."""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering import pipeline
from suno_mastering.analysis.dynamic_range import measure_dynamic_range

from .conftest import make_dynamic_track, write_wav


def test_tc030_dr8_boundary_construction(default_config, tmp_wav_dir, out_dir):
    sr = 44100
    A = 0.1
    P = A * 10 ** (8 / 20)
    audio = make_dynamic_track(sr, 60.0, body_amplitude=A, transient_amplitude=P,
                                transient_period_s=1.0, transient_len_ms=5.0, freq=220)
    dr = measure_dynamic_range(audio, sr, default_config)
    assert abs(dr - 8) <= 1  # module's own rounding rule tolerance

    path = write_wav(tmp_wav_dir / "tc030.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)
    assert result.after.dynamic_range_db >= 8


def test_tc031_dr14_source_3db_reduction_binds(default_config, tmp_wav_dir, out_dir):
    sr = 44100
    A = 0.05
    P = A * 10 ** (14 / 20)
    audio = make_dynamic_track(sr, 60.0, body_amplitude=A, transient_amplitude=P,
                                transient_period_s=1.0, transient_len_ms=5.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc031.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.after.dynamic_range_db >= 11
    assert result.report.solver["source_dr"] is not None
    assert result.report.solver["achieved_dr"] is not None


def test_tc032_dr9_source_dr8_floor_binds(default_config, tmp_wav_dir, out_dir):
    sr = 44100
    A = 0.09
    P = A * 10 ** (9 / 20)
    audio = make_dynamic_track(sr, 60.0, body_amplitude=A, transient_amplitude=P,
                                transient_period_s=1.0, transient_len_ms=5.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc032.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    # naive "3dB max reduction" would allow DR6; DR8 floor must win
    assert result.after.dynamic_range_db >= 8


def test_tc033_solver_backs_off_loudness_to_protect_dr(default_config, tmp_wav_dir, out_dir):
    sr = 44100
    A = 0.02  # far below -13.5 LUFS target
    P = A * 10 ** (8 / 20)
    audio = make_dynamic_track(sr, 60.0, body_amplitude=A, transient_amplitude=P,
                                transient_period_s=1.0, transient_len_ms=5.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc033.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.after.dynamic_range_db >= 8
    if result.after.integrated_lufs < -14.5:
        rationale = result.report.solver["rationale"]
        assert rationale is not None
        assert "DR" in rationale


def test_tc034_ac4_baseline_uses_true_original_dr(default_config, tmp_wav_dir, out_dir):
    """Regression guard for architecture.md's flagged risk: the DR floor
    used by the solver must be computed from stage[2]'s D0 (true original
    DR), not the stage-6-entry DR after EQ/stereo correction."""
    sr = 44100
    A = 0.03
    P = A * 10 ** (12 / 20)
    audio = make_dynamic_track(sr, 60.0, body_amplitude=A, transient_amplitude=P,
                                transient_period_s=1.0, transient_len_ms=5.0, freq=220)
    path = write_wav(tmp_wav_dir / "tc034.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    d0 = result.before.dynamic_range_db
    expected_floor = max(default_config.dr_floor, d0 - default_config.dr_max_reduction_db)
    assert abs(result.report.solver["dr_floor_used"] - expected_floor) < 0.01
    assert result.report.solver["source_dr"] == d0


def test_tc035_report_shows_source_and_output_dr(default_config, tmp_wav_dir, out_dir):
    sr = 44100
    audio = make_dynamic_track(sr, 40.0, body_amplitude=0.08, transient_amplitude=0.3, freq=220)
    path = write_wav(tmp_wav_dir / "tc035.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.before.dynamic_range_db is not None
    assert result.after.dynamic_range_db is not None
    assert result.report.solver["source_dr"] == result.before.dynamic_range_db
    assert result.report.solver["achieved_dr"] == result.after.dynamic_range_db
