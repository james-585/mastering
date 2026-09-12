"""STORY-002 AC3 -- Suno-export side-by-side comparison. TC-240-TC-242."""
from __future__ import annotations

import dataclasses

from suno_mastering.reference_analysis import pipeline as ref_pipeline
from suno_mastering.report.reference_builder import build_reference_set_report

from .ref_helpers import pink_noise_stereo, write_wav, ref_config


def _make_reference_folder(tmp_path, n=5, sr=44100, duration=8.0):
    d = tmp_path / "refs"
    d.mkdir()
    for i in range(n):
        audio = pink_noise_stereo(sr, duration, seed=i, amplitude=0.1 + 0.01 * i)
        write_wav(d / f"ref{i}.wav", audio, sr)
    return str(d)


def test_tc240_suno_export_measured_and_compared(tmp_path):
    ref_dir = _make_reference_folder(tmp_path)
    export_audio = pink_noise_stereo(44100, 8.0, seed=99, amplitude=0.3)
    export_path = write_wav(tmp_path / "export.wav", export_audio, 44100)

    config = ref_config(hf_min_duration_s=3.0)
    result = ref_pipeline.analyze_set(ref_dir, suno_export_path=export_path, config=config)
    report = build_reference_set_report(result, config)

    assert report.comparison is not None
    assert report.comparison["track"].track_path == export_path
    gaps = report.comparison["gaps"]
    assert gaps["integrated_lufs"] is not None
    assert "gap" in gaps["integrated_lufs"]
    assert "reference_median" in gaps["integrated_lufs"]
    assert "suno_export_value" in gaps["integrated_lufs"]


def test_tc241_comparison_omitted_not_errored_without_export(tmp_path):
    ref_dir = _make_reference_folder(tmp_path)
    config = ref_config(hf_min_duration_s=3.0)
    result = ref_pipeline.analyze_set(ref_dir, config=config)
    report = build_reference_set_report(result, config)
    assert report.comparison is None
    assert len(report.per_track) == 5
    assert len(report.aggregates) > 0


def test_tc242_comparison_track_uses_identical_r2_path(tmp_path):
    ref_dir = _make_reference_folder(tmp_path)
    export_audio = pink_noise_stereo(44100, 8.0, seed=99, amplitude=0.3)
    export_path = write_wav(tmp_path / "export.wav", export_audio, 44100)
    config = ref_config(hf_min_duration_s=3.0)

    result = ref_pipeline.analyze_set(ref_dir, suno_export_path=export_path, config=config)
    via_r4 = result.comparison

    via_r2_standalone = ref_pipeline.analyze_track(export_path, config)

    # field-for-field identical -- [R4] introduces no measurement divergence
    assert via_r4.core == via_r2_standalone.core
    assert via_r4.dynamic_range_db_exact == via_r2_standalone.dynamic_range_db_exact
    assert via_r4.lra == via_r2_standalone.lra
    assert via_r4.seven_band == via_r2_standalone.seven_band
    assert via_r4.hf_extension == via_r2_standalone.hf_extension
    assert via_r4.per_band_stereo_width == via_r2_standalone.per_band_stereo_width
    assert via_r4.mono_sum == via_r2_standalone.mono_sum
