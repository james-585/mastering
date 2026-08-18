import numpy as np

from demucs_tuning import (
    DEFAULT_DEMUCS_PROFILE,
    benchmark_demucs_config,
    select_default_demucs_profile,
)


def _make_fixture() -> np.ndarray:
    rng = np.random.default_rng(7)
    length = 16384
    left = rng.normal(0.0, 0.1, size=length)
    right = rng.normal(0.0, 0.1, size=length)
    stereo = np.column_stack([left, right]).astype(np.float64)
    stereo += np.sin(np.linspace(0.0, 50.0, length, dtype=np.float64))[:, None] * 0.05
    return stereo


def test_tc020_01_benchmark_profile_output():
    fixture = _make_fixture()
    result = benchmark_demucs_config(fixture, 44100, DEFAULT_DEMUCS_PROFILE)

    assert result["status"] in {"valid", "rejected"}
    assert "runtime_s" in result
    assert "peak_memory_mb" in result
    assert "artifact_score" in result
    assert result["runtime_s"] >= 0.0
    assert result["peak_memory_mb"] >= 0.0
    assert np.isfinite(result["artifact_score"])


def test_tc020_02_reject_unstable_profile():
    fixture = _make_fixture()
    unstable_profile = {
        "shift_count": 0,
        "overlap": 0.95,
        "segment_length": 128,
        "profile_version": "story020-invalid",
    }

    result = benchmark_demucs_config(fixture, 44100, unstable_profile)
    assert result["status"] == "rejected"
    assert result["failure_reason"]


def test_tc020_03_deterministic_repeated_runs():
    fixture = _make_fixture()
    first = benchmark_demucs_config(fixture, 44100, DEFAULT_DEMUCS_PROFILE)
    second = benchmark_demucs_config(fixture, 44100, DEFAULT_DEMUCS_PROFILE)

    assert first["status"] == second["status"] == "valid"
    assert abs(first["artifact_score"] - second["artifact_score"]) < 1e-6
    assert abs(first["runtime_s"] - second["runtime_s"]) < 0.25
    assert abs(first["peak_memory_mb"] - second["peak_memory_mb"]) < 1.0


def test_tc020_04_default_profile_selection():
    good = {
        "profile": {"shift_count": 2, "overlap": 0.25, "segment_length": 2048, "profile_version": "story020-a"},
        "status": "valid",
        "artifact_score": 0.93,
        "runtime_s": 0.25,
        "peak_memory_mb": 220.0,
    }
    better = {
        "profile": {"shift_count": 3, "overlap": 0.50, "segment_length": 4096, "profile_version": "story020-b"},
        "status": "valid",
        "artifact_score": 0.96,
        "runtime_s": 0.35,
        "peak_memory_mb": 260.0,
    }
    rejected = {
        "profile": {"shift_count": 5, "overlap": 0.75, "segment_length": 8192, "profile_version": "story020-c"},
        "status": "rejected",
        "artifact_score": 0.5,
        "runtime_s": 0.8,
        "peak_memory_mb": 350.0,
        "failure_reason": "phase_mismatch",
    }

    profile = select_default_demucs_profile([good, better, rejected])
    assert profile["profile_version"] == "story020-b"
    assert profile["shift_count"] == 3
