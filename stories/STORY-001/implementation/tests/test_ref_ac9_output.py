"""STORY-002 AC9 -- human- and machine-readable output. TC-290-TC-293.

Note (per DEF-101's own fix notes / architecture.md v2 Section 9):
schema_version was bumped to "1.1" in the shipped code for the DEF-101 fix's
additive BandCancellation.excess_delta_db field + renamed config field, NOT
the "1.0" test-cases.md v1 TC-292 originally asserted -- see
stories/STORY-002/defects.md's DEF-106 entry.

DEF-205 update (STORY-003 QA pass): schema_version was bumped AGAIN, "1.1"
-> "1.2", for STORY-003's additive Measurements.sanity_warnings /
ReferenceMeasurements.sanity_warnings fields (architecture.md Section 4.4/
AC13, same DEF-101 additive-field-bump precedent). This test now asserts
the correct, current "1.2" value -- see stories/STORY-002/defects.md's
DEF-205 entry.
"""
from __future__ import annotations

import json

from suno_mastering.reference_analysis import pipeline as ref_pipeline
from suno_mastering.report.reference_builder import build_reference_set_report
from suno_mastering.report.reference_render import render_markdown, render_json

from .ref_helpers import pink_noise_stereo, write_wav, ref_config


def _make_set(tmp_path, n=5, with_export=True):
    d = tmp_path / "refs"
    d.mkdir()
    for i in range(n):
        write_wav(d / f"r{i}.wav", pink_noise_stereo(44100, 5.0, seed=i), 44100)
    export_path = None
    if with_export:
        export_path = write_wav(tmp_path / "export.wav", pink_noise_stereo(44100, 5.0, seed=99), 44100)
    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(d), suno_export_path=export_path, config=config)
    return build_reference_set_report(result, config)


def test_tc290_markdown_renders_all_sections(tmp_path):
    report = _make_set(tmp_path)
    md = render_markdown(report)
    assert "Per-track measurements" in md
    assert "Aggregate statistics" in md
    assert "Suno-export comparison" in md


def test_tc291_json_valid_and_matches_documented_schema(tmp_path):
    report = _make_set(tmp_path)
    js = render_json(report)
    parsed = json.loads(js)
    for key in ("schema_version", "generated_at_utc", "decoder_identity", "tool_version",
                "config_summary", "per_track", "aggregates", "comparison", "failures"):
        assert key in parsed, f"missing top-level key {key}"


def test_tc292_schema_version_matches_current_shipped_value(tmp_path):
    report = _make_set(tmp_path)
    assert report.schema_version == "2.2"  # bumped for STORY-005 (DEF-205) additive fields


def test_tc293_decoder_identity_populated(tmp_path):
    from .ref_helpers import write_mp3_ffmpeg, ffmpeg_available
    import pytest
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")
    d = tmp_path / "refs"
    d.mkdir()
    write_mp3_ffmpeg(d / "a.mp3", pink_noise_stereo(44100, 5.0), 44100, bitrate_kbps=192)
    config = ref_config(hf_min_duration_s=2.0)
    result = ref_pipeline.analyze_set(str(d), config=config)
    report = build_reference_set_report(result, config)
    assert report.decoder_identity
    assert "mp3" in report.decoder_identity
    decoder = report.decoder_identity["mp3"]
    assert decoder.startswith("libsndfile-") or decoder.startswith("ffmpeg-")


def test_tc294_no_cliff_hf_result_renders_clear_message(tmp_path):
    report = _make_set(tmp_path)
    md = render_markdown(report)
    assert "No artificial band-limit detected" in md
    hf_rows = [line for line in md.splitlines() if "hf_extension_hf_band_limit_hz" in line]
    assert hf_rows
    assert any("No artificial band-limit detected" in line for line in hf_rows)
