"""AC8 -- before/after report. TC-070..TC-074."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone

import numpy as np
import pytest

from suno_mastering import pipeline
from suno_mastering.analysis.types import (
    ArtifactDetectionResult,
    ArtifactFlag,
    BandMeasurement,
    ClippingResult,
    FrequencyBalanceResult,
    Measurements,
    StereoPhaseResult,
)
from suno_mastering.io.ingest import compute_file_hash

from .conftest import make_dynamic_track, rms_amplitude_for_dbfs_sine, write_wav


def _run(tmp_wav_dir, out_dir, config, name="track.wav", **kw):
    sr = kw.pop("sr", 44100)
    dur = kw.pop("dur", 30.0)
    audio = make_dynamic_track(sr, dur, **kw)
    path = write_wav(tmp_wav_dir / name, audio, sr)
    return pipeline.master(path, output_dir=out_dir, config=config), path


def test_tc070_report_covers_all_six_criteria_side_by_side(tmp_wav_dir, out_dir, default_config):
    result, _ = _run(tmp_wav_dir, out_dir, default_config, body_amplitude=0.1, transient_amplitude=0.4)
    for m in (result.before, result.after):
        assert m.integrated_lufs is not None
        assert m.true_peak_dbtp is not None
        assert m.dynamic_range_db is not None
        assert m.frequency_balance is not None
        assert m.stereo_phase is not None
        assert m.clipping is not None


def test_tc071_corrective_action_log_completeness(tmp_wav_dir, out_dir, default_config):
    sr = 32000  # non-standard, forces resample
    dur = 30.0
    body = rms_amplitude_for_dbfs_sine(-28.0)
    audio = make_dynamic_track(sr, dur, body_amplitude=body, transient_amplitude=0.9, freq=220)
    # inject muddiness by adding a strong 300Hz component
    n = len(audio)
    t = np.arange(n) / sr
    boost = 0.3 * np.sin(2 * np.pi * 300 * t)
    audio[:, 0] += boost
    audio[:, 1] += boost
    path = write_wav(tmp_wav_dir / "tc071.wav", audio, sr)
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.report.resample_action is not None
    assert result.report.resample_action["sample_rate"] == 44100
    assert result.report.dither_seed == default_config.dither_seed
    assert "achieved_lufs" in result.report.solver
    assert "gain_db_applied" in result.report.solver


def test_tc072_no_rationale_when_band_reached_cleanly(tmp_wav_dir, out_dir, default_config):
    result, _ = _run(
        tmp_wav_dir, out_dir, default_config, name="tc072.wav",
        body_amplitude=rms_amplitude_for_dbfs_sine(-20.0), transient_amplitude=0.4,
    )
    if -14.5 <= result.after.integrated_lufs <= -13.5:
        assert result.report.solver["rationale"] is None


def test_tc073_source_hash_recorded_correctly(tmp_wav_dir, out_dir, default_config):
    sr = 44100
    audio = make_dynamic_track(sr, 20.0, body_amplitude=0.1, transient_amplitude=0.4)
    path = write_wav(tmp_wav_dir / "tc073.wav", audio, sr)

    expected_hash = compute_file_hash(str(path))
    result = pipeline.master(path, output_dir=out_dir, config=default_config)

    assert result.input_hash == expected_hash
    assert result.report.input_hash == expected_hash
    assert result.output_hash is not None
    assert result.report.output_hash == result.output_hash
    assert result.report.tool_version == default_config.tool_version
    assert result.report.config_summary is not None


def test_tc074_report_renders_human_readable(tmp_wav_dir, out_dir, default_config):
    from suno_mastering.report.render import render_markdown
    result, _ = _run(tmp_wav_dir, out_dir, default_config, name="tc074.wav",
                      body_amplitude=0.1, transient_amplitude=0.4)
    md = render_markdown(result.report)
    assert "LUFS" in md
    assert "dBTP" in md
    for label in ("loudness", "peak", "dynamic range", "band", "stereo", "clip"):
        assert label.lower() in md.lower()


def test_tc074a_report_has_end_user_summary(tmp_wav_dir, out_dir, default_config):
    from suno_mastering.report.render import render_markdown
    result, _ = _run(
        tmp_wav_dir, out_dir, default_config, name="tc074a.wav",
        body_amplitude=0.1, transient_amplitude=0.4,
    )
    md = render_markdown(result.report)
    assert "At a glance" in md
    assert "Demuddification" in md
    assert "overall result" in md.lower()


def test_tc074b_report_includes_artifact_detections_and_plausibility_warnings():
    from suno_mastering.report.render import render_markdown
    from suno_mastering.report.builder import ReportData

    base_measurement = Measurements(
        sample_rate=44100,
        channels=2,
        duration_seconds=10.0,
        is_mono=False,
        integrated_lufs=-13.5,
        true_peak_dbtp=-1.2,
        dynamic_range_db=8.0,
        frequency_balance=FrequencyBalanceResult(
            low_end=BandMeasurement((20, 120), 0.0, 0.0, 0.0, False),
            low_mid_mud=BandMeasurement((120, 500), -0.5, 0.0, -0.5, False),
            presence_harsh=BandMeasurement((500, 5000), -1.0, 0.0, -1.0, False),
        ),
        stereo_phase=StereoPhaseResult(
            is_mono=False,
            overall_correlation=0.85,
            mono_compatible=True,
            windows=[],
            widened_regions=[],
        ),
        clipping=ClippingResult(
            sample_peak_clipped_count=0,
            sample_peak_clip_events=0,
            inter_sample_over_count=0,
            inter_sample_peak_dbtp=-3.0,
            severity="none",
        ),
        artifact_detection=ArtifactDetectionResult(
            total_artifacts_found=1,
            artifact_flags=[
                ArtifactFlag(
                    timestamp_start_s=12.0,
                    timestamp_end_s=16.0,
                    artifact_type="DIGITAL_HAZE",
                    confidence_score=0.91,
                    details={"tmi_hf": 0.09, "cc_hf_lf": 0.44},
                )
            ],
            overall_artifact_density_score=0.29,
            detected_at=datetime.now(timezone.utc),
        ),
        plausibility_warnings=[
            "DIGITAL_HAZE detected at 00:12 (TMI_HF=0.09, CC_HF_LF=0.44, confidence 0.91) — stationary HF generation noise"
        ],
    )

    report = ReportData(
        tool_version="test",
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        input_path="input.wav",
        output_path="output.wav",
        input_hash="in",
        output_hash="out",
        config_summary={"spectral_correction_scope": "sub and low_mid only"},
        before=base_measurement,
        after=base_measurement,
        resample_action=None,
        eq_actions=[],
        stereo_actions=[],
        solver={
            "target_lufs": -13.5,
            "achieved_lufs": -13.5,
            "achieved_true_peak_dbtp": -1.0,
            "achieved_dr": 8.0,
            "source_dr": 9.0,
            "dr_floor_used": 8.0,
            "gain_db_applied": 0.0,
            "outer_iterations": 1,
            "peak_convergence_iterations": 0,
            "below_soft_band": False,
            "below_documented_lufs_floor": False,
            "rationale": None,
        },
        dither_seed=123,
        integrity_verified=True,
    )

    md = render_markdown(report)
    assert "Artifact summary" in md
    assert "DIGITAL_HAZE" in md
    assert "density score" in md.lower()
    assert "stationary HF generation noise" in md


def test_tc074c_report_summarises_issue_counts_instead_of_dumping_every_flag():
    from suno_mastering.report.render import render_markdown
    from suno_mastering.report.builder import ReportData

    artifact_detection = ArtifactDetectionResult(
        total_artifacts_found=3,
        artifact_flags=[
            ArtifactFlag(0.0, 1.0, "STATIONARY_WHISTLE", 0.93, {"frequency_hz": 6000.0}),
            ArtifactFlag(9.0, 10.0, "STATIONARY_WHISTLE", 0.88, {"frequency_hz": 5400.0}),
            ArtifactFlag(18.0, 19.0, "SMEARED_TRANSIENT", 0.72, {"rise_time_ms": 31.0}),
        ],
        overall_artifact_density_score=0.58,
        detected_at=datetime.now(timezone.utc),
    )
    measurement = Measurements(
        sample_rate=44100,
        channels=2,
        duration_seconds=20.0,
        is_mono=False,
        integrated_lufs=-13.0,
        true_peak_dbtp=-1.1,
        dynamic_range_db=8.4,
        frequency_balance=FrequencyBalanceResult(
            low_end=BandMeasurement((20, 120), 1.0, 0.0, 1.0, False),
            low_mid_mud=BandMeasurement((120, 500), -0.5, 0.0, -0.5, False),
            presence_harsh=BandMeasurement((500, 5000), -0.8, 0.0, -0.8, False),
        ),
        stereo_phase=StereoPhaseResult(False, 0.82, True, [], []),
        clipping=ClippingResult(0, 0, 0, -2.0, "none"),
        artifact_detection=artifact_detection,
        plausibility_warnings=[
            "STATIONARY_WHISTLE detected at 00:00 (6000.0 Hz, confidence 0.93) — consider re-generating track"
        ],
    )

    report = ReportData(
        tool_version="test",
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        input_path="input.wav",
        output_path="output.wav",
        input_hash="in",
        output_hash="out",
        config_summary={"spectral_correction_scope": "sub and low_mid only"},
        before=measurement,
        after=measurement,
        resample_action=None,
        eq_actions=[],
        stereo_actions=[],
        solver={
            "target_lufs": -13.5,
            "achieved_lufs": -13.5,
            "achieved_true_peak_dbtp": -1.0,
            "achieved_dr": 8.0,
            "source_dr": 9.0,
            "dr_floor_used": 8.0,
            "gain_db_applied": 0.0,
            "outer_iterations": 1,
            "peak_convergence_iterations": 0,
            "below_soft_band": False,
            "below_documented_lufs_floor": False,
            "rationale": None,
        },
        dither_seed=123,
        integrity_verified=True,
    )

    md = render_markdown(report)
    assert "Most common issue types" in md
    assert "STATIONARY_WHISTLE" in md
    assert "SMEARED_TRANSIENT" in md
    assert "Summary" in md
    assert "Raw flag dump" not in md
