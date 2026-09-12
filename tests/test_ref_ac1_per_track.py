"""STORY-002 AC1 -- per-track measurement report. TC-200-TC-204."""
from __future__ import annotations

import math

import pytest

from suno_mastering.reference_analysis import pipeline as ref_pipeline

from .ref_helpers import (
    pink_noise_stereo, pink_noise_mono, write_flac, write_mp3_ffmpeg,
    write_wav, ref_config, ffmpeg_available,
)


def _assert_ac1_fields_populated(m, expect_stereo_fields: bool):
    core = m.core
    assert core.integrated_lufs is not None and math.isfinite(core.integrated_lufs)
    assert m.lra.lra_lu is not None
    assert core.true_peak_dbtp is not None and math.isfinite(core.true_peak_dbtp)
    assert m.dynamic_range_db_exact is not None
    assert core.dynamic_range_db is not None
    assert len(m.seven_band.bands) == 7
    for band in ("sub", "low", "low_mid", "mid", "high_mid", "high", "air"):
        assert any(b.band == band for b in m.seven_band.bands), f"missing band {band}"
    assert m.hf_extension is not None  # rolloff_hz/.stable present (may be None if short)
    assert core.stereo_phase.overall_correlation is not None
    assert m.provenance.container in ("wav", "flac", "mp3")
    assert m.provenance.lossless in (True, False)

    if expect_stereo_fields:
        assert m.per_band_stereo_width is not None
        assert len(m.per_band_stereo_width.bands) == 7
        assert m.mono_sum is not None
        assert m.mono_sum.mono_sum_level_change_db is not None
        assert all(hasattr(b, "cancellation") for b in m.mono_sum.band_cancellations)
    else:
        assert m.per_band_stereo_width is None
        assert m.mono_sum is None


def test_tc200_full_per_track_report_stereo(tmp_path):
    """TC-200: stereo WAV, all AC1 fields populated."""
    audio = pink_noise_stereo(44100, 60.0, amplitude=0.15)
    p = write_wav(tmp_path / "ref.wav", audio, 44100)
    m = ref_pipeline.analyze_track(p, ref_config())
    _assert_ac1_fields_populated(m, expect_stereo_fields=True)
    assert not m.core.is_mono


def test_tc201_mono_track_stereo_fields_null(tmp_path):
    """TC-201: mono reference track -- stereo-only fields explicitly None,
    not a crash, not a degenerate 1.0/'no change' value."""
    audio = pink_noise_mono(44100, 60.0, amplitude=0.15)
    p = write_wav(tmp_path / "mono.wav", audio, 44100)
    m = ref_pipeline.analyze_track(p, ref_config())
    _assert_ac1_fields_populated(m, expect_stereo_fields=False)
    assert m.core.is_mono
    # STORY-001's existing mono short-circuit surfaces unchanged.
    assert m.core.stereo_phase.overall_correlation == 1.0
    assert m.core.stereo_phase.mono_compatible is True


def test_tc202_48khz_stereo_air_band_resolves_to_nyquist(tmp_path):
    """TC-202: 48kHz stereo track -- air band upper edge resolves to 24000Hz,
    not hardcoded 22050Hz."""
    audio = pink_noise_stereo(48000, 60.0, amplitude=0.15)
    p = write_wav(tmp_path / "ref48.wav", audio, 48000)
    m = ref_pipeline.analyze_track(p, ref_config())
    _assert_ac1_fields_populated(m, expect_stereo_fields=True)
    air = next(b for b in m.seven_band.bands if b.band == "air")
    assert air.range_hz[1] == pytest.approx(24000.0)


def test_tc203_flac_matches_wav_field_completeness_and_values(tmp_path):
    """TC-203: FLAC input produces the same field set as WAV; measurement
    values equal within 1e-6 relative tolerance (lossless decode-path check)."""
    audio = pink_noise_stereo(44100, 30.0, amplitude=0.15)
    wav_path = write_wav(tmp_path / "ref.wav", audio, 44100)
    flac_path = write_flac(tmp_path / "ref.flac", audio, 44100)

    m_wav = ref_pipeline.analyze_track(wav_path, ref_config())
    m_flac = ref_pipeline.analyze_track(flac_path, ref_config())

    _assert_ac1_fields_populated(m_flac, expect_stereo_fields=True)
    assert m_flac.core.integrated_lufs == pytest.approx(m_wav.core.integrated_lufs, rel=1e-6)
    assert m_flac.core.true_peak_dbtp == pytest.approx(m_wav.core.true_peak_dbtp, rel=1e-6)
    assert m_flac.provenance.container == "flac"
    assert m_flac.provenance.lossless is True


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available for MP3 fixture encoding")
def test_tc204_mp3_320kbps_produces_same_field_set(tmp_path):
    """TC-204: MP3 (320kbps) input produces the same field set as WAV;
    provenance reports lossy/mp3. HF-extension is still measured per-track
    even though it will be excluded from the aggregate per AC5."""
    audio = pink_noise_stereo(44100, 30.0, amplitude=0.15)
    mp3_path = write_mp3_ffmpeg(tmp_path / "ref.mp3", audio, 44100, bitrate_kbps=320)

    m = ref_pipeline.analyze_track(mp3_path, ref_config())
    _assert_ac1_fields_populated(m, expect_stereo_fields=True)
    assert m.provenance.lossless is False
    assert m.provenance.container == "mp3"
    # AC1: HF-extension reported per-track regardless of aggregate exclusion.
    assert m.hf_extension.hf_band_limit_hz is not None or m.hf_extension.insufficient_duration
