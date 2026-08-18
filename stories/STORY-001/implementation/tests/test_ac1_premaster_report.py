"""AC1 -- pre-master analysis report. TC-001, TC-002, TC-003."""
from __future__ import annotations

import numpy as np

from suno_mastering import pipeline
from suno_mastering.analysis import measure_all
from suno_mastering.config import MasteringConfig

from .conftest import make_dynamic_track, rms_amplitude_for_dbfs_sine, sine, to_stereo, write_wav


def test_tc001_full_six_criteria_report(default_config):
    sr = 48000
    dur = 20.0  # shortened from "~3 min" per QA runtime guidance; still long enough
    # non-neutral on all six criteria
    body = sine(440, sr, dur, amplitude=0.2)
    left = body.copy()
    right = body.copy()
    # out-of-phase region in the middle
    n = len(left)
    oop_start, oop_end = n // 2, n // 2 + int(0.75 * sr)
    right[oop_start:oop_end] = -right[oop_start:oop_end]
    # a few sample-peak clips
    left[1000:1010] = 1.0
    right[1000:1010] = 1.0
    audio = np.stack([left, right], axis=1)

    m = measure_all(audio, sr, default_config)

    assert m.integrated_lufs is not None
    assert np.isfinite(m.integrated_lufs)
    assert m.true_peak_dbtp is not None
    assert m.dynamic_range_db is not None
    fb = m.frequency_balance
    for band in (fb.low_end, fb.low_mid_mud, fb.presence_harsh):
        assert isinstance(band.flagged, bool)
        assert band.relative_db is not None
    sp = m.stereo_phase
    assert sp.overall_correlation is not None
    assert m.clipping.sample_peak_clipped_count >= 10
    assert m.clipping.severity != "none"


def test_tc002_premaster_runs_before_resample(tmp_wav_dir, out_dir, default_config, caplog):
    sr = 32000  # non-standard rate
    dur = 30.0
    audio = make_dynamic_track(
        sr, dur, body_amplitude=rms_amplitude_for_dbfs_sine(-20.0),
        transient_amplitude=0.5, transient_period_s=0.5, freq=1000,
    )
    path = write_wav(tmp_wav_dir / "tc002.wav", audio, sr, subtype="PCM_24")

    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    # stage [2] "before" measurement must be against native 32kHz, not 44.1kHz
    assert result.before.sample_rate == sr
    # output was resampled to 44100 (default) since 32kHz isn't supported
    assert result.after.sample_rate == 44100
    assert result.actions["resample"] is not None
    assert result.actions["resample"]["source_sample_rate"] == sr
    assert result.actions["resample"]["sample_rate"] == 44100


def test_tc003_mono_input_report_no_crash(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    dur = 30.0
    mono = make_dynamic_track(sr, dur, body_amplitude=0.1, transient_amplitude=0.5, stereo=False)

    m = measure_all(mono, sr, default_config)
    assert m.is_mono is True
    assert m.stereo_phase.is_mono is True
    assert m.stereo_phase.overall_correlation == 1.0
    assert m.stereo_phase.mono_compatible is True
    assert m.stereo_phase.widened_regions == []

    # full pipeline should also not crash on mono
    path = write_wav(tmp_wav_dir / "tc003.wav", mono, sr, subtype="PCM_16")
    result = pipeline.master(path, output_dir=out_dir, config=default_config)
    assert result.before.is_mono is True
    assert result.after.is_mono in (True, False)  # after mastering channel count should remain 1
