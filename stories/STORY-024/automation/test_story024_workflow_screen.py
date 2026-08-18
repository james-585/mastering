"""STORY-024 automation: CLI workflow screen test cases TC-024-01 .. TC-024-05."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "implementation"))
sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[2] / "STORY-001" / "implementation"),
)

from workflow_screen import (
    ScreenContext,
    render_error,
    render_run_header,
    render_screen,
    render_summary,
)

from suno_mastering import cli


def _verified_result(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        output_path=str(tmp_path / "mastered.wav"),
        integrity_verified=True,
        report=SimpleNamespace(
            solver={
                "achieved_lufs": -13.9,
                "achieved_true_peak_dbtp": -1.02,
                "achieved_dr": 9.0,
            }
        ),
        quality_review=SimpleNamespace(decision="pass", summary="all gates clear"),
    )


def test_tc024_01_start_of_run_screen_shows_operation_and_context():
    screen = render_run_header(
        input_file="track.wav",
        model="htdemucs_6s",
        profile="demucs-default-v1",
        stem_enabled=True,
    )

    assert "STAGE: Stem Split" in screen
    assert "track.wav" in screen
    assert "htdemucs_6s" in screen
    assert "demucs-default-v1" in screen
    assert "RUNNING" in screen


def test_tc024_01a_reference_workflow_sequence_is_exposed():
    flow = render_run_header(
        input_file="track.wav",
        model="htdemucs_6s",
        profile="demucs-default-v1",
        stem_enabled=True,
    )

    for label in (
        "Stem Split",
        "Lochness EQ",
        "Tighten Low End",
        "Reintegrate Lows",
        "Loudness Normalization",
        "Ready for Release",
    ):
        assert label in flow


def test_tc024_02_in_progress_state_keeps_stage_and_context_visible():
    context = ScreenContext(
        operation="master",
        input_file="track.wav",
        model="htdemucs_6s",
        state="running",
        detail="stem analysis",
    )

    screen = render_screen("Stem analysis", context)

    assert "STAGE: Stem analysis" in screen
    assert "RUNNING - stem analysis" in screen
    assert "track.wav" in screen


def test_tc024_02_invalid_state_is_rejected():
    with pytest.raises(ValueError):
        render_screen("Stage", ScreenContext(operation="master", state="maybe"))


def test_tc024_03_failure_screen_names_blocking_reason_and_next_action(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.wav"

    exit_code = cli.main([str(missing), "--no-progress"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "RUN FAILED" in captured.err
    assert "FileNotFoundError" in captured.err
    assert "does-not-exist.wav" in captured.err
    assert "action:" in captured.err


def test_tc024_03_render_error_gives_dependency_guidance():
    from suno_mastering.errors import DependencyError

    screen = render_error(DependencyError("demucs missing"))

    assert "FAILED" in screen
    assert "demucs missing" in screen
    assert "pip install demucs torch" in screen


def test_tc024_04_success_summary_reflects_verified_result(tmp_path):
    screen = render_summary(_verified_result(tmp_path))

    assert "RUN SUMMARY" in screen
    assert "-13.90 LUFS" in screen
    assert "-1.02 dBTP" in screen
    assert "integrity: PASSED" in screen
    assert "COMPLETE" in screen
    assert "quality review: PASS" in screen


def test_tc024_04_summary_never_fakes_completion(tmp_path):
    result = _verified_result(tmp_path)
    result.integrity_verified = False

    screen = render_summary(result)

    assert "COMPLETE" not in screen
    assert "BLOCKED" in screen
    assert "FAILED - input hash changed" in screen


def test_tc024_05_cli_only_no_gui_dependency():
    # The module must be importable and render pure text with no GUI imports.
    import workflow_screen

    source = Path(workflow_screen.__file__).read_text(encoding="utf-8")
    for gui_marker in ("tkinter", "PyQt", "wx", "pygame"):
        assert gui_marker not in source

    screen = render_screen("Stage", ScreenContext(operation="master", state="waiting"))
    assert json.dumps(screen)  # plain serialisable text, suitable for log capture


def test_tc024_01_cli_start_screen_end_to_end(tmp_path, capsys, monkeypatch):
    input_path = tmp_path / "input.wav"
    input_path.write_bytes(b"sentinel")

    def fake_master(input_file, output_dir=None, config=None, reporter=None):
        return SimpleNamespace(
            output_path=str(tmp_path / "mastered.wav"),
            integrity_verified=True,
            quality_review=None,
            report=SimpleNamespace(
                solver={
                    "achieved_lufs": -14.0,
                    "achieved_true_peak_dbtp": -1.0,
                    "achieved_dr": 8.0,
                }
            ),
        )

    monkeypatch.setattr(cli, "master", fake_master)
    exit_code = cli.main(
        [
            str(input_path),
            "--split-stems",
            "--stem-model",
            "htdemucs_6s",
            "--no-progress",
            "--no-report",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "STAGE: Stem Split" in captured.out
    assert "model:   htdemucs_6s" in captured.out
    assert "RUN SUMMARY" in captured.out
    assert "COMPLETE" in captured.out
    assert input_path.read_bytes() == b"sentinel"
