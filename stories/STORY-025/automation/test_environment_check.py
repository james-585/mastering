"""TC-2521 - TC-2527: verify_stem_separation_environment() (architecture.md
§5.2, Gate 1 Finding 4)."""
from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from environment_check import EnvironmentVerificationError, verify_stem_separation_environment
from suno_mastering.errors import DependencyError
from suno_mastering.io.stem_separation import StemBundle

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REAL_FIXTURE = _REPO_ROOT / "Reference Tracks" / "Sunday Club.wav"


def test_tc2521_clip_offset_seconds_default_is_30():
    default = inspect.signature(verify_stem_separation_environment).parameters["clip_offset_seconds"].default
    assert default == 30.0


def test_tc2522_short_fixture_raises_rather_than_truncating(tmp_path):
    sr = 44100
    n = int(sr * 20.0)
    audio = 0.1 * np.sin(2 * np.pi * 440.0 * np.arange(n) / sr)
    fixture_path = tmp_path / "short_fixture.wav"
    sf.write(str(fixture_path), np.column_stack([audio, audio]), sr)

    with pytest.raises(EnvironmentVerificationError) as excinfo:
        verify_stem_separation_environment(
            fixture_path=fixture_path, clip_seconds=8.0, clip_offset_seconds=30.0
        )

    message = str(excinfo.value)
    assert "38" in message
    assert "20" in message


def test_tc2523_clip_read_starting_at_offset_not_file_start(tmp_path, monkeypatch):
    import environment_check as ec

    sr = 44100
    silence = np.zeros(int(sr * 30.0))
    tone = 0.3 * np.sin(2 * np.pi * 440.0 * np.arange(int(sr * 15.0)) / sr)
    audio = np.concatenate([silence, tone])
    fixture_path = tmp_path / "intro_silence_fixture.wav"
    sf.write(str(fixture_path), np.column_stack([audio, audio]), sr)

    captured = {}

    def fake_split_stems(clip, sr_, model_name=None):
        captured["clip"] = clip
        # Divide evenly so the stems sum back to reconstruct clip (§5.2.1
        # reconstruction check) -- this test is about the offset, not reconstruction.
        share = clip / 4.0
        stems = {"drums": share.copy(), "bass": share.copy(), "other": share.copy(), "vocals": share.copy()}
        return StemBundle(stems, {"torch_version": "2.13.0+cpu", "demucs_version": "4.1.0"})

    monkeypatch.setattr(ec, "split_stems", fake_split_stems)

    result = verify_stem_separation_environment(
        fixture_path=fixture_path, clip_seconds=8.0, clip_offset_seconds=30.0
    )

    mono = captured["clip"].mean(axis=1)
    assert float(np.max(np.abs(mono))) > 0.05  # drawn from the tone region, not silence
    assert result.available is True


def test_tc2524_degenerate_zero_stem_raises(tmp_path, monkeypatch):
    import environment_check as ec

    sr = 44100
    n = int(sr * 40.0)
    audio = 0.1 * np.sin(2 * np.pi * 440.0 * np.arange(n) / sr)
    fixture_path = tmp_path / "fixture.wav"
    sf.write(str(fixture_path), np.column_stack([audio, audio]), sr)

    def fake_split_stems(clip, sr_, model_name=None):
        zeros = np.zeros_like(clip)
        stems = {"drums": zeros, "bass": clip.copy(), "other": clip.copy(), "vocals": clip.copy()}
        return StemBundle(stems, {"torch_version": "2.13.0+cpu", "demucs_version": "4.1.0"})

    monkeypatch.setattr(ec, "split_stems", fake_split_stems)

    with pytest.raises(EnvironmentVerificationError):
        verify_stem_separation_environment(fixture_path=fixture_path)


def test_tc2525_nan_in_stem_raises(tmp_path, monkeypatch):
    import environment_check as ec

    sr = 44100
    n = int(sr * 40.0)
    audio = 0.1 * np.sin(2 * np.pi * 440.0 * np.arange(n) / sr)
    fixture_path = tmp_path / "fixture.wav"
    sf.write(str(fixture_path), np.column_stack([audio, audio]), sr)

    def fake_split_stems(clip, sr_, model_name=None):
        bad = clip.copy()
        bad[0, 0] = np.nan
        stems = {"drums": bad, "bass": clip.copy(), "other": clip.copy(), "vocals": clip.copy()}
        return StemBundle(stems, {"torch_version": "2.13.0+cpu", "demucs_version": "4.1.0"})

    monkeypatch.setattr(ec, "split_stems", fake_split_stems)

    with pytest.raises(EnvironmentVerificationError):
        verify_stem_separation_environment(fixture_path=fixture_path)


def test_tc2526_import_failure_raises_no_silent_fallback(tmp_path, monkeypatch):
    import environment_check as ec

    sr = 44100
    n = int(sr * 40.0)
    audio = 0.1 * np.sin(2 * np.pi * 440.0 * np.arange(n) / sr)
    fixture_path = tmp_path / "fixture.wav"
    sf.write(str(fixture_path), np.column_stack([audio, audio]), sr)

    def fake_split_stems(clip, sr_, model_name=None):
        raise DependencyError("demucs/torch not installed")

    monkeypatch.setattr(ec, "split_stems", fake_split_stems)

    with pytest.raises(EnvironmentVerificationError) as excinfo:
        verify_stem_separation_environment(fixture_path=fixture_path)
    assert "demucs" in str(excinfo.value).lower() or "torch" in str(excinfo.value).lower()


@pytest.mark.slow
@pytest.mark.skipif(not _REAL_FIXTURE.exists(), reason="Reference Tracks/Sunday Club.wav fixture not present")
def test_tc2527_real_demucs_environment_smoke_test():
    result = verify_stem_separation_environment()

    assert result.available is True
    assert result.stem_count == 6
    assert result.elapsed_s < 30.0
