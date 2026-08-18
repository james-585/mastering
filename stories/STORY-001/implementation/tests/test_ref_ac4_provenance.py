"""STORY-002 AC4 -- source format/provenance detection. TC-250-TC-254."""
from __future__ import annotations

import pytest

from suno_mastering.io import reference_ingest

from .ref_helpers import (
    pink_noise_stereo, write_wav, write_flac, write_mp3_ffmpeg,
    write_mp3_vbr_no_header, ref_config, ffmpeg_available,
)


def test_tc250_wav_reports_lossless_no_bitrate(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    p = write_wav(tmp_path / "t.wav", audio, 44100)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    assert r.provenance.container == "wav"
    assert r.provenance.lossless is True
    assert r.provenance.bitrate_kbps is None


def test_tc251_flac_reports_lossless(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    p = write_flac(tmp_path / "t.flac", audio, 44100)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    assert r.provenance.container == "flac"
    assert r.provenance.lossless is True


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_tc252_mp3_clean_cbr_reports_lossy_with_bitrate(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    p = write_mp3_ffmpeg(tmp_path / "t.mp3", audio, 44100, bitrate_kbps=320)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    assert r.provenance.container == "mp3"
    assert r.provenance.lossless is False
    assert r.provenance.bitrate_kbps == 320


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_tc253_mp3_no_reliable_bitrate_tag_reports_unknown_not_fail(tmp_path):
    audio = pink_noise_stereo(44100, 5.0)
    p = write_mp3_vbr_no_header(tmp_path / "t.mp3", audio, 44100)
    r = reference_ingest.ingest_reference_track(p, ref_config())
    assert r.provenance.container == "mp3"
    assert r.provenance.lossless is False
    # best-effort: either a genuine VBR average was recovered, or None
    # ("bitrate unknown") -- never a fabricated/blocking failure either way.
    assert r.provenance.bitrate_kbps is None or isinstance(r.provenance.bitrate_kbps, int)


def test_tc254_format_label_renders_inline_per_track(tmp_path):
    from suno_mastering.reference_analysis import pipeline as ref_pipeline
    from suno_mastering.report.reference_builder import build_reference_set_report
    from suno_mastering.report.reference_render import render_markdown

    ref_dir = tmp_path / "refs"
    ref_dir.mkdir()
    audio = pink_noise_stereo(44100, 5.0, seed=1)
    write_wav(ref_dir / "a.wav", audio, 44100)
    write_flac(ref_dir / "b.flac", audio, 44100)
    if ffmpeg_available():
        write_mp3_ffmpeg(ref_dir / "c.mp3", audio, 44100, bitrate_kbps=192)

    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(ref_dir), config=config)
    report = build_reference_set_report(result, config)
    md = render_markdown(report)

    assert "WAV, lossless" in md
    assert "FLAC, lossless" in md
    if ffmpeg_available():
        assert "MP3, lossy" in md
        assert "192" in md
