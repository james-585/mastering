import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from suno_mastering_release import cli as release_cli


REPO_ROOT = Path(__file__).resolve().parents[4]
IMPLEMENTATION_ROOT = REPO_ROOT / "stories" / "STORY-018" / "implementation"
CLI_ENTRY = [sys.executable, "-m", "suno_mastering_release"]
PYTHONPATH_FOR_SUBPROCESS = (
    str(REPO_ROOT)
    + ";"
    + str(REPO_ROOT / "stories" / "STORY-001" / "implementation")
    + ";"
    + str(IMPLEMENTATION_ROOT)
)


@pytest.fixture
def sample_wav_path(tmp_path):
    wav_path = tmp_path / "sample.wav"
    import numpy as np
    import soundfile as sf

    sr = 48000
    duration_s = 8.0
    t = np.arange(int(sr * duration_s)) / sr
    body = 0.08 * np.sin(2 * np.pi * 220.0 * t)
    transient = np.full_like(body, 0.08)
    period = max(1, int(sr * 0.5))
    transient_len = max(1, int(0.01 * sr))
    for start in range(period, len(body) - transient_len, period):
        transient[start:start + transient_len] = 0.6
    audio = np.column_stack([body + transient, body + transient]).astype("float64")
    sf.write(wav_path, audio, sr, subtype="PCM_24")
    return wav_path


def test_story018_cli_help_contract():
    result = subprocess.run(
        CLI_ENTRY + ["--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_FOR_SUBPROCESS},
    )
    assert result.returncode == 0
    help_text = result.stdout + result.stderr
    for token in ["input", "output-dir", "--mode", "--help"]:
        assert token in help_text.lower()


def test_story018_valid_run_creates_summary_and_audio(sample_wav_path, tmp_path, monkeypatch):
    output_dir = tmp_path / "out"

    class DummyReport:
        solver = {
            "achieved_lufs": -14.2,
            "achieved_true_peak_dbtp": -1.7,
            "achieved_dr": 9.0,
        }

    class DummyResult:
        output_path = str(output_dir / "mastered.wav")
        report = DummyReport()
        quality_review = SimpleNamespace(decision="pass", summary="Pass: the mastering result is clearer and more controlled than the source.")

    def fake_master(*_args, **_kwargs):
        output_dir.mkdir(parents=True, exist_ok=True)
        mastered_path = output_dir / "mastered.wav"
        mastered_path.write_bytes(b"RIFF")
        return DummyResult()

    monkeypatch.setattr(release_cli.pipeline_mod, "master", fake_master)

    result_code = release_cli.main([str(sample_wav_path), "--output-dir", str(output_dir), "--mode", "release"])
    assert result_code == 0

    output_files = list(output_dir.rglob("*"))
    assert any(p.suffix.lower() == ".wav" for p in output_files)
    assert any(p.name.endswith("summary.json") or p.name.endswith("audit.json") or p.name.endswith("report.md") for p in output_files)

    summary = next((p for p in output_files if p.name.endswith("summary.json") or p.name.endswith("audit.json")), None)
    if summary is not None:
        payload = json.loads(summary.read_text(encoding="utf-8"))
        assert "mode" in payload or "summary" in payload or "audit" in payload
        summary_payload = payload.get("summary", payload)
        assert "stage_order" in summary_payload
        assert "achievements" in summary_payload
        assert any(item["stage"] == "transient_restoration" for item in summary_payload["achievements"])


def test_story018_invalid_input_rejected_cleanly(tmp_path):
    bad_path = tmp_path / "missing.wav"
    result = subprocess.run(
        CLI_ENTRY + [str(bad_path), "--mode", "release"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={**dict(__import__("os").environ), "PYTHONPATH": PYTHONPATH_FOR_SUBPROCESS},
    )
    assert result.returncode != 0
    text = (result.stdout + result.stderr).lower()
    assert "not found" in text or "does not exist" in text or "missing" in text or "error" in text


def test_story018_repeated_runs_are_repeatable(sample_wav_path, tmp_path, monkeypatch):
    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"

    class DummyReport:
        solver = {
            "achieved_lufs": -14.2,
            "achieved_true_peak_dbtp": -1.7,
            "achieved_dr": 9.0,
        }

    class DummyResult:
        def __init__(self, out_dir: Path):
            self.output_path = str(out_dir / "mastered.wav")
            self.report = DummyReport()
            self.quality_review = SimpleNamespace(decision="pass", summary="Pass: stable and controlled")

    def fake_master(input_path, output_dir=None, config=None):
        out_dir = Path(output_dir) if output_dir else Path(input_path).parent / "release_candidate_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "mastered.wav").write_bytes(b"")
        return DummyResult(out_dir)

    monkeypatch.setattr(release_cli.pipeline_mod, "master", fake_master)

    result1 = release_cli.main([str(sample_wav_path), "--output-dir", str(run_a), "--mode", "release"])
    assert result1 == 0

    result2 = release_cli.main([str(sample_wav_path), "--output-dir", str(run_b), "--mode", "release"])
    assert result2 == 0

    files_a = sorted(p.name for p in run_a.rglob("*"))
    files_b = sorted(p.name for p in run_b.rglob("*"))
    assert files_a == files_b
