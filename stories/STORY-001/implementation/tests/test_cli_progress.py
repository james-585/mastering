from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import suno_mastering
from suno_mastering import cli
from suno_mastering.analysis.types import ArtifactDetectionResult, ArtifactFlag
from suno_mastering.config import RepairWhistlesConfig
from suno_mastering.mastering.whistle_repair import apply_whistle_repair


def test_repair_whistles_defaults_to_off():
    from suno_mastering.config import RepairWhistlesConfig

    cfg = RepairWhistlesConfig()
    assert cfg.enabled is False


def test_cli_accepts_progress_and_summary_flags():
    parser = cli.build_arg_parser()
    args = parser.parse_args([
        "--verbose",
        "--progress",
        "--json-summary",
        "--no-report",
        "--dry-run",
        "input.wav",
    ])

    assert args.verbose is True
    assert args.progress is True
    assert args.json_summary is True
    assert args.no_report is True
    assert args.dry_run is True
    assert args.input == "input.wav"

    default_args = parser.parse_args(["input.wav"])
    assert default_args.progress is True


def test_cli_accepts_cpp_toggle_flags():
    parser = cli.build_arg_parser()
    args = parser.parse_args([
        "--repair-whistles",
        "--shape-transients",
        "--collapse-swish",
        "input.wav",
    ])

    assert args.repair_whistles is True
    assert args.shape_transients is True
    assert args.collapse_swish is True

    off_args = parser.parse_args([
        "--no-repair-whistles",
        "--no-shape-transients",
        "--no-collapse-swish",
        "input.wav",
    ])

    assert off_args.repair_whistles is False
    assert off_args.shape_transients is False
    assert off_args.collapse_swish is False


def test_cli_prompt_yes_no_supports_interactive_toggle_selection(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("builtins.input", lambda prompt: "n")

    assert cli._prompt_yes_no("Repair whistles?", default=True) is False
    assert cli._prompt_yes_no("Shape transients?", default=False) is False

    monkeypatch.setattr("builtins.input", lambda prompt: "y")
    assert cli._prompt_yes_no("Collapse swish?", default=False) is True


def test_cli_does_not_prompt_for_legacy_cpp_dsp_by_default(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    prompts = []

    def _boom(prompt):
        prompts.append(prompt)
        raise AssertionError("legacy C++ prompt should not appear in normal CLI flow")

    monkeypatch.setattr("builtins.input", _boom)
    args = SimpleNamespace(repair_whistles=None, shape_transients=None, collapse_swish=None)
    cfg = cli.MasteringConfig()

    cli._prompt_artifact_toggles(args, cfg)
    assert prompts == []


def test_artifact_summary_truncates_long_console_output():
    from suno_mastering.analysis.artifact_detection import summarize_artifacts_for_display

    flags = []
    for idx in range(12):
        flags.append(ArtifactFlag(
            timestamp_start_s=float(idx) * 0.25,
            timestamp_end_s=float(idx) * 0.25 + 0.2,
            artifact_type="STATIONARY_WHISTLE",
            confidence_score=0.9,
            details={"frequency_hz": 6400.0 + idx, "prominence_db": 12.0},
        ))

    result = ArtifactDetectionResult(
        total_artifacts_found=len(flags),
        artifact_flags=flags,
        overall_artifact_density_score=0.9,
        detected_at=datetime.utcnow(),
    )

    summary = summarize_artifacts_for_display(result)
    assert len(summary) <= 6
    assert any("more" in line.lower() for line in summary)


def test_repair_whistles_noop_when_no_matching_flags():
    sr = 44100
    tone = np.full(8192, 0.25, dtype=np.float64)
    cfg = RepairWhistlesConfig(enabled=False, confidence_threshold=0.8, prominence_floor_db=10.0)
    result, actions = apply_whistle_repair(tone, sr, None, cfg)
    assert np.max(np.abs(result - tone)) <= 1e-6
    assert actions[-1].frequencies_notched == []


def test_repair_whistles_only_forward_detector_confirmed_stationary_whistles():
    sr = 44100
    audio = np.sin(2.0 * np.pi * 1000.0 * np.arange(8192, dtype=np.float64) / sr).astype(np.float64)
    flag = ArtifactFlag(
        timestamp_start_s=0.1,
        timestamp_end_s=0.2,
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=0.9,
        details={"frequency_hz": 6400.0, "prominence_db": 12.0},
    )
    result = ArtifactDetectionResult(
        total_artifacts_found=1,
        artifact_flags=[flag],
        overall_artifact_density_score=0.1,
        detected_at=datetime.utcnow(),
    )
    cfg = RepairWhistlesConfig(enabled=False, confidence_threshold=0.8, prominence_floor_db=10.0)
    repaired, actions = apply_whistle_repair(audio, sr, result, cfg)
    assert repaired.shape == audio.shape
    assert actions[-1].frequencies_notched == [6400.0]


def test_repair_whistles_respects_flagged_time_window_locality():
    sr = 44100
    n_samples = 10 * sr
    t = np.arange(n_samples, dtype=np.float64) / sr
    rng = np.random.default_rng(0)
    audio = rng.standard_normal(n_samples).astype(np.float64)
    whistle = np.zeros_like(audio)
    window = (t >= 4.0) & (t <= 6.0)
    whistle[window] = 0.25 * np.sin(2.0 * np.pi * 6400.0 * t[window])
    audio = audio + whistle

    flag = ArtifactFlag(
        timestamp_start_s=4.0,
        timestamp_end_s=6.0,
        artifact_type="STATIONARY_WHISTLE",
        confidence_score=0.9,
        details={"frequency_hz": 6400.0, "prominence_db": 12.0},
    )
    detection = ArtifactDetectionResult(
        total_artifacts_found=1,
        artifact_flags=[flag],
        overall_artifact_density_score=0.1,
        detected_at=datetime.utcnow(),
    )
    cfg = RepairWhistlesConfig(enabled=False, confidence_threshold=0.8, prominence_floor_db=10.0, crossfade_ms=50.0)

    repaired, actions = apply_whistle_repair(audio, sr, detection, cfg)

    skirt_samples = max(1, int(round(cfg.crossfade_ms / 1000.0 * sr)))
    window_start = int(round((4.0 - 0.05) * sr))
    window_end = int(round((6.0 + 0.05) * sr))

    outside = np.ones(n_samples, dtype=bool)
    outside[max(0, window_start - skirt_samples):min(n_samples, window_end + skirt_samples)] = False

    assert np.array_equal(repaired[outside], audio[outside])
    assert np.any(np.abs(repaired[~outside] - audio[~outside]) > 0.0)
    assert actions[-1].frequencies_notched == [6400.0]


def test_suno_dsp_build_dir_is_added_to_python_path(monkeypatch, tmp_path):
    repo_root = tmp_path / "repo"
    build_dir = repo_root / "build" / "Release"
    build_dir.mkdir(parents=True)
    (build_dir / "suno_dsp.cp314-win_amd64.pyd").write_bytes(b"fake-extension")

    test_package_path = repo_root / "stories" / "STORY-001" / "implementation" / "suno_mastering" / "__init__.py"
    test_package_path.parent.mkdir(parents=True)

    monkeypatch.setattr(suno_mastering, "__file__", str(test_package_path))
    original_sys_path = list(sys.path)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if str(build_dir) != p])

    suno_mastering._ensure_suno_dsp_on_path()

    assert str(build_dir) in sys.path
    monkeypatch.setattr(sys, "path", original_sys_path)


def test_cli_prints_stem_first_mastering_workflow(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake-wave-data")

    fake_result = SimpleNamespace(
        output_path=str(tmp_path / "output" / "mastered.wav"),
        report=SimpleNamespace(
            solver={
                "achieved_lufs": -14.2,
                "achieved_true_peak_dbtp": -1.1,
                "achieved_dr": 9.0,
            }
        ),
    )

    monkeypatch.setattr(cli, "master", lambda *args, **kwargs: fake_result)

    exit_code = cli.main([
        "--split-stems",
        "--json-summary",
        "--no-report",
        str(input_path),
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Mastering workflow:" not in output
    assert "Live stage-progress will be shown during the mastering run." in output
    assert "The workflow is driven by the active reporter" in output
    assert "[Stage 1]" in output


def test_cli_main_prints_progress_and_json_summary(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake-wave-data")

    fake_result = SimpleNamespace(
        output_path=str(tmp_path / "output" / "mastered.wav"),
        report=SimpleNamespace(
            solver={
                "achieved_lufs": -14.2,
                "achieved_true_peak_dbtp": -1.1,
                "achieved_dr": 9.0,
            }
        ),
        quality_review=SimpleNamespace(
            decision="pass",
            summary="Pass: the final mix remains controlled and more believable than the source.",
        ),
    )

    monkeypatch.setattr(cli, "master", lambda *args, **kwargs: fake_result)

    exit_code = cli.main([
        "--verbose",
        "--json-summary",
        "--no-report",
        str(input_path),
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "[Stage 1]" in output
    assert "|" in output
    assert "100%" in output
    assert "Summary:" in output
    assert '"achieved_lufs": -14.2' in output
    assert "Quality review:" in output
    assert "PASS" in output


def test_cli_main_surfaces_quality_review_decision(monkeypatch, tmp_path, capsys):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"fake-wave-data")

    fake_result = SimpleNamespace(
        output_path=str(tmp_path / "output" / "mastered.wav"),
        report=SimpleNamespace(
            solver={
                "achieved_lufs": -14.2,
                "achieved_true_peak_dbtp": -1.1,
                "achieved_dr": 9.0,
            }
        ),
        quality_review=SimpleNamespace(
            decision="refine",
            summary="Refine: the result is close but needs a small corrective pass.",
        ),
    )

    monkeypatch.setattr(cli, "master", lambda *args, **kwargs: fake_result)

    exit_code = cli.main([
        "--json-summary",
        "--no-report",
        str(input_path),
    ])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Quality review:" in output
    assert "REFINE" in output
    assert "needs a small corrective pass" in output
