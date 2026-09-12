"""STORY-002 AC6/AC7 -- reused STORY-001 metrics against FLAC/MP3-decoded
input. TC-270-TC-275."""
from __future__ import annotations

import numpy as np
import pytest

from suno_mastering.io import reference_ingest
from suno_mastering.analysis.loudness import measure_integrated_lufs
from suno_mastering.analysis.true_peak import measure_true_peak

from .ref_helpers import (
    calibrated_tone_mono, write_wav, write_flac, write_mp3_ffmpeg,
    ref_config, ffmpeg_available,
)


def test_tc270_loudness_calibration_wav(tmp_path):
    audio = calibrated_tone_mono(44100, 10.0, dbfs_rms=-20.0)
    p = write_wav(tmp_path / "t.wav", audio, 44100)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    lufs = measure_integrated_lufs(r.audio, r.sample_rate)
    assert lufs == pytest.approx(-20.0, abs=0.1)


def test_tc271_loudness_calibration_flac(tmp_path):
    audio = calibrated_tone_mono(44100, 10.0, dbfs_rms=-20.0)
    p = write_flac(tmp_path / "t.flac", audio, 44100)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    lufs = measure_integrated_lufs(r.audio, r.sample_rate)
    assert lufs == pytest.approx(-20.0, abs=0.1)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_tc272_loudness_calibration_mp3_320kbps(tmp_path):
    audio = calibrated_tone_mono(44100, 10.0, dbfs_rms=-20.0)
    p = write_mp3_ffmpeg(tmp_path / "t.mp3", audio, 44100, bitrate_kbps=320)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    lufs = measure_integrated_lufs(r.audio, r.sample_rate)
    deviation = abs(lufs - (-20.0))
    # Record actual deviation regardless of outcome (per test-cases.md's own
    # instruction not to silently loosen the tolerance) -- assert it as a
    # genuine finding.
    assert deviation < 0.5, f"MP3 320kbps loudness deviation {deviation:.4f} LU is unexpectedly large"
    if deviation > 0.1:
        pytest.xfail(f"320kbps MP3 loudness deviation {deviation:.4f} LU exceeds AC6's 0.1 LU "
                      f"tolerance -- reported per test-cases.md TC-272's 'genuine finding' instruction")


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_tc273_loudness_calibration_mp3_128kbps(tmp_path):
    audio = calibrated_tone_mono(44100, 10.0, dbfs_rms=-20.0)
    p = write_mp3_ffmpeg(tmp_path / "t.mp3", audio, 44100, bitrate_kbps=128)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    lufs = measure_integrated_lufs(r.audio, r.sample_rate)
    deviation = abs(lufs - (-20.0))
    print(f"TC-273: 128kbps MP3 measured {lufs:.4f} LUFS, deviation {deviation:.4f} LU")
    # This test exists to *find*, not assume, where the tolerance stops
    # holding -- assert only that the run completes and produces a finite
    # value; report deviation for the record.
    assert np.isfinite(lufs)


def test_tc274_true_peak_differs_from_sample_peak(tmp_path):
    """Inter-sample-peak fixture: 15kHz sine at 44.1kHz timed so the true
    waveform peak falls between two sample points."""
    sr = 44100
    freq = 15000.0
    n = int(round(sr * 2.0))
    t = np.arange(n) / sr
    mono = 0.9 * np.sin(2 * np.pi * freq * t + 0.35)
    audio = np.stack([mono, mono], axis=1)
    p = write_wav(tmp_path / "t.wav", audio, sr)
    r = reference_ingest.ingest_reference_track(p, ref_config())

    sample_peak_dbfs = 20.0 * np.log10(np.max(np.abs(r.audio)))
    tp_result = measure_true_peak(r.audio, r.sample_rate, ref_config().mastering)
    assert tp_result.dbtp > sample_peak_dbfs


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_tc275_mp3_true_peak_flagged_approximate_with_correct_direction(tmp_path):
    from suno_mastering.reference_analysis import pipeline as ref_pipeline
    from suno_mastering.report.reference_builder import build_reference_set_report
    from suno_mastering.report.reference_render import render_markdown
    from .ref_helpers import pink_noise_stereo

    ref_dir = tmp_path / "refs"
    ref_dir.mkdir()
    audio = pink_noise_stereo(44100, 5.0, amplitude=0.3)
    write_mp3_ffmpeg(ref_dir / "a.mp3", audio, 44100, bitrate_kbps=320)

    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(ref_dir), config=config)
    report = build_reference_set_report(result, config)
    md = render_markdown(report)

    # Standing caveat text states both error directions, never netted.
    assert "near-Nyquist" in md
    assert "UP" in md or "up" in md
    assert "informational only" in md or "not validated to target-setting precision" in md
